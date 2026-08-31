from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from smartscan.config import TrainConfig, load_yaml, project_root
from smartscan.ml.bundle import SchedulerBundle, load_bundle, ppo_predict_fn, save_bundle
from smartscan.ml.calibrate import IsotonicCalibrator
from smartscan.ml.dataset import collect_exploration
from smartscan.ml.features import FeatureBuilder, ObservationNormalizer, observation_size
from smartscan.ml.policies import ContextualThompsonSchedule
from smartscan.ml.predictor import HitHazardNet, HitHazardPredictor, RecencyPredictor
from smartscan.ml.train import train_predictor
from smartscan.rf.bands import named_band_plan
from smartscan.types import SmartScanError


def test_train_config_smoke_loads() -> None:
    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    assert cfg.timesteps == 256
    assert cfg.device == "cpu"


def test_train_full_config_budget_frozen() -> None:
    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_full.yaml"))
    assert cfg.timesteps == 200000
    assert cfg.eval_cadence == 10000
    assert cfg.early_stopping_patience == 5
    train_pairs = [(s.scenario_id, tuple(s.seeds)) for s in cfg.train_scenarios]
    val_pairs = [(s.scenario_id, tuple(s.seeds)) for s in cfg.val_scenarios]
    assert train_pairs == [
        ("sparse", (0, 1, 2, 3, 4, 5)),
        ("dense", (0, 1, 2, 3)),
        ("agile_threat", (0, 1, 2, 3, 4, 5)),
    ]
    assert val_pairs == [
        ("sparse", (200, 201)),
        ("dense", (200,)),
        ("agile_threat", (200, 201)),
    ]
    assert cfg.test_scenarios == []
    held_out_seeds = set(range(1000, 1030))
    train_seeds = {seed for spec in cfg.train_scenarios for seed in spec.seeds}
    val_seeds = {seed for spec in cfg.val_scenarios for seed in spec.seeds}
    assert not (train_seeds & held_out_seeds)
    assert not (val_seeds & held_out_seeds)


def test_dataset_splits_are_scenario_seed_not_rows() -> None:
    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    cfg.duration_s = 0.04
    cfg.collect_strategies = ["sequential"]
    cfg.mc_rollouts = 2
    rows, manifest = collect_exploration(cfg)
    assert rows
    keys = {(row.scenario_id, row.seed, row.split) for row in rows}
    # All rows from the same scenario+seed share one split.
    by_pair: dict[tuple[str, int], set[str]] = {}
    for row in rows:
        by_pair.setdefault((row.scenario_id, row.seed), set()).add(row.split)
    assert all(len(v) == 1 for v in by_pair.values())
    assert manifest.n_rows == len(rows)
    assert keys


def test_predictor_trains_on_tiny_cpu() -> None:
    pytest.importorskip("torch")
    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    cfg.duration_s = 0.04
    cfg.n_epochs_predictor = 1
    cfg.collect_strategies = ["sequential"]
    rows, _manifest = collect_exploration(cfg)
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    predictor, hit_cal, _act, metrics = train_predictor(rows, cfg, n_bands=n_bands)
    assert metrics
    builder = FeatureBuilder(n_bands=n_bands, dt_s=0.001, dwell_bins=tuple(cfg.dwell_bins))
    rec = RecencyPredictor(n_bands=n_bands, horizon_s=0.05)
    rec_fc = rec.forecast_next_intercept(
        builder,
        band=0,
        dwell_steps=8,
        proposed_schedule=[(0, 8)],
        horizon_s=0.05,
        pfa=0.001,
        dt_s=0.001,
        step=0,
        n_steps=40,
        settled_band=None,
        last_target_band=None,
        last_dwell_steps=None,
    )
    assert 0.0 <= rec_fc.p_hit_within_dwell <= 1.0
    feats = builder.vector(step=0, n_steps=40, settled_band=None, last_target_band=None, last_dwell_steps=None)
    nn_fc = predictor.forecast_next_intercept(
        feats,
        band=0,
        dwell_steps=8,
        proposed_schedule=[(0, 8)],
        horizon_s=0.05,
        snr_db=None,
        dt_s=0.001,
        start_step=0,
        tune_cost_steps=1,
    )
    assert np.isfinite(nn_fc.p_hit_within_dwell)
    del hit_cal


def test_bundle_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    import torch

    plan = named_band_plan("demo_2_18")
    bins = (1, 2, 4, 8, 16)
    n_in = observation_size(plan.n_bands)
    net = HitHazardNet(n_in=n_in, n_bands=plan.n_bands, n_dwell=5, n_bins=8, hidden=16)
    predictor = HitHazardPredictor(net, dwell_bins=bins)
    ident = IsotonicCalibrator.identity()
    normalizer = ObservationNormalizer(size=n_in)
    cts = ContextualThompsonSchedule(n_bands=plan.n_bands, dwell_bins=bins, seed=0)
    ppo_state = {
        "action_net.weight": torch.zeros(n_actions_safe(plan.n_bands, bins), n_in),
        "action_net.bias": torch.zeros(n_actions_safe(plan.n_bands, bins)),
    }
    bundle = SchedulerBundle(
        band_plan=plan,
        dwell_bins=bins,
        receiver_ibw_hz=1e8,
        feature_schema_payload={"size": n_in},
        predictor=predictor,
        recency_ok=True,
        hit_calibrator=ident,
        active_calibrator=ident,
        normalizer=normalizer,
        cts=cts,
        ppo_state=ppo_state,
        config={"seed": 0},
        model_version="test",
    )
    dest = tmp_path / "bundle"
    save_bundle(bundle, dest)
    loaded = load_bundle(dest)
    fn = ppo_predict_fn(loaded)
    action_a = fn(np.zeros(n_in, dtype=np.float32))
    action_b = fn(np.zeros(n_in, dtype=np.float32))
    assert action_a == action_b
    loaded.assert_compatible(plan, bins, 1e8)
    with pytest.raises(SmartScanError):
        loaded.assert_compatible(plan, (1, 2), 1e8)


def n_actions_safe(n_bands: int, bins: tuple[int, ...]) -> int:
    from smartscan.ml.actions import n_actions

    return n_actions(n_bands, bins)


def test_recency_time_error_beats_constant_horizon_on_periodic_hits() -> None:
    """Scheduler-level recency MAE vs a naive constant-horizon forecast."""

    from smartscan.ml.observable import ObservableTransition

    builder = FeatureBuilder(n_bands=4, dt_s=0.001, dwell_bins=(8,))
    rec = RecencyPredictor(n_bands=4, horizon_s=1.0)
    horizon = 1.0
    actuals = []
    rec_err = []
    naive_err = []
    now = 0
    for k in range(12):
        hit_time = (k + 1) * 100
        tr = ObservableTransition(
            decision_id=f"d{k}",
            start_step=now,
            tune_end_step=now,
            end_step=hit_time,
            target_band=1,
            dwell_steps=hit_time - now,
            hit=True,
            measured_snr_db=5.0,
            n_steps=2000,
            n_bands=4,
            dt_s=0.001,
            settled_band_before=1,
            last_target_band=1,
        )
        fc = rec.forecast_next_intercept(
            builder,
            band=1,
            dwell_steps=8,
            proposed_schedule=[(1, 8)],
            horizon_s=horizon,
            pfa=0.001,
            dt_s=0.001,
            step=now,
            n_steps=2000,
            settled_band=1,
            last_target_band=1,
            last_dwell_steps=8,
        )
        actual = (hit_time - now) * 0.001
        actuals.append(actual)
        rec_err.append(abs(fc.time_to_next_completed_intercept_s - actual))
        naive_err.append(abs(horizon - actual))
        builder.observe(tr)
        now = hit_time
    assert float(np.mean(rec_err[3:])) <= float(np.mean(naive_err[3:])) + 1e-9


def test_tiny_ppo_and_seed_backends() -> None:
    pytest.importorskip("stable_baselines3")
    from smartscan.ml.train import seed_ml_backends, train_ppo

    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    cfg.duration_s = 0.05
    cfg.timesteps = 64
    cfg.ppo_n_steps = 8
    cfg.ppo_batch_size = 8
    cfg.ppo_n_epochs = 1
    cfg.mc_rollouts = 2
    cfg.eval_cadence = 0
    cfg.early_stopping_patience = 0
    seed_ml_backends(cfg.seed)
    state, normalizer, meta = train_ppo(cfg)
    assert state
    assert normalizer.size > 0
    assert meta["checkpoint"] == "final"


def test_ppo_validation_callback_on_tiny_budget() -> None:
    pytest.importorskip("stable_baselines3")
    from smartscan.config import ScenarioSeedSpec
    from smartscan.ml.train import train_ppo

    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    cfg.duration_s = 0.04
    cfg.timesteps = 24
    cfg.ppo_n_steps = 8
    cfg.ppo_batch_size = 8
    cfg.ppo_n_epochs = 1
    cfg.mc_rollouts = 2
    cfg.eval_cadence = 8
    cfg.val_scenarios = [ScenarioSeedSpec(scenario_id="sparse", seeds=[0])]
    cfg.train_scenarios = [ScenarioSeedSpec(scenario_id="sparse", seeds=[0])]
    state, _normalizer, meta = train_ppo(cfg)
    assert state
    assert meta["n_val_evals"] >= 1
    assert meta["timesteps_completed"] >= 24
    assert meta["checkpoint"] in {"best_validation", "final"}
    assert meta["val_curve"]
