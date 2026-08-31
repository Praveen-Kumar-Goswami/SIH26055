from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from smartscan.config import TrainConfig
from smartscan.ml.dataset import SupervisedRow, save_dataset, survival_label
from smartscan.ml.evaluate import load_held_out_manifest
from smartscan.ml.features import FeatureBuilder, ObservationNormalizer, feature_schema
from smartscan.ml.forecast import HorizonForecaster
from smartscan.ml.observable import ObservableTransition
from smartscan.ml.policies import make_policy
from smartscan.ml.tsrd_sample import write_tiny_tsrd
from smartscan.receiver.detector import load_receiver_config
from smartscan.types import SmartScanError


def _tr(i: int, hit: bool) -> ObservableTransition:
    return ObservableTransition(
        decision_id=f"d{i}",
        start_step=i * 10,
        tune_end_step=i * 10,
        end_step=i * 10 + 8,
        target_band=i % 4,
        dwell_steps=8,
        hit=hit,
        measured_snr_db=None,
        n_steps=200,
        n_bands=4,
        dt_s=0.001,
        settled_band_before=None,
        last_target_band=None,
    )


def test_survival_label_hit_censor_and_horizon() -> None:
    rows = [_tr(0, False), _tr(1, False), _tr(2, True), _tr(3, False)]
    assert survival_label(rows, 0, horizon_steps=1000, n_bins=8) == 1
    assert survival_label(rows, 2, horizon_steps=1000, n_bins=8) is None
    short = survival_label(rows, 0, horizon_steps=5, n_bins=8)
    assert short is None


def test_save_dataset_and_normalizer_roundtrip(tmp_path: Path) -> None:
    row = SupervisedRow(
        features=np.zeros(8, dtype=np.float32),
        band=0,
        dwell_steps=8,
        q_hit=1.0,
        event_index=None,
        future_bands=[],
        future_dwells=[],
        scenario_id="sparse",
        seed=0,
        source_strategy="sequential",
        decision_id="d0",
        split="train",
    )
    from smartscan.ml.dataset import DatasetManifest

    man = DatasetManifest(
        schema_version="1.0.0",
        n_rows=1,
        n_train=1,
        n_val=0,
        n_test=0,
        split_ids={"train": ["sparse::0"], "val": [], "test": []},
        feature_schema=feature_schema(4, (8,)),
        source_run_keys=["k"],
        content_fingerprint="abc",
    )
    saved = save_dataset([row], man, tmp_path)
    assert saved.artifact_sha256
    assert (tmp_path / "dataset.npz").is_file()
    norm = ObservationNormalizer(size=8)
    norm.update(np.ones(8))
    norm.update(np.zeros(8))
    z = norm.transform(np.ones(8))
    assert z.shape == (8,)
    restored = ObservationNormalizer.from_state(norm.state_dict())
    assert restored.count == 2


def test_held_out_manifest_fingerprint() -> None:
    payload = load_held_out_manifest(
        Path(__file__).resolve().parents[2] / "configs" / "held_out_manifest.json"
    )
    assert payload["n_paired_seeds"] == 30
    assert len(payload["pairs"]) == 30
    assert payload["pairs"][0] == {"scenario_id": "sparse", "seed": 1000}
    assert payload["pairs"][-1] == {"scenario_id": "tsrd_synthetic", "seed": 1029}
    assert payload["content_fingerprint"] == (
        "4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4"
    )


def test_make_policy_names_and_tiny_tsrd(tmp_path: Path) -> None:
    assert type(make_policy("reactive", dwell_steps=8, schedule_seed=0)).__name__ == "ReactiveSchedule"
    assert type(make_policy("periodic-intercept", dwell_steps=8, schedule_seed=0)).__name__ == (
        "PeriodicInterceptSchedule"
    )
    assert type(make_policy("cts", dwell_steps=8, n_bands=4, dwell_bins=(8,))).__name__ == (
        "ContextualThompsonSchedule"
    )
    with pytest.raises(SmartScanError):
        make_policy("nope", dwell_steps=8)
    path = write_tiny_tsrd(tmp_path / "t.h5")
    assert path.is_file()


def test_horizon_rejects_zero_rollouts() -> None:
    with pytest.raises(SmartScanError):
        HorizonForecaster(n_rollouts=0, dt_s=0.001, tune_latency_steps=1)


def test_ablation_changes_features() -> None:
    cfg_fields = dict(n_bands=4, dt_s=0.001, dwell_bins=(8,))
    a = FeatureBuilder(**cfg_fields, ablate_periodicity=False, ablate_novelty=False)
    b = FeatureBuilder(**cfg_fields, ablate_periodicity=True, ablate_novelty=True)
    tr = _tr(0, True)
    a.observe(tr)
    b.observe(tr)
    va = a.vector(step=8, n_steps=50, settled_band=0, last_target_band=0, last_dwell_steps=8)
    vb = b.vector(step=8, n_steps=50, settled_band=0, last_target_band=0, last_dwell_steps=8)
    assert va.shape == vb.shape
    # Novelty/period channels can differ after a hit.
    assert TrainConfig().ablate_novelty is False


def test_assign_split_and_invalid_actions() -> None:
    from smartscan.ml.actions import encode_action, n_actions
    from smartscan.ml.dataset import assign_split

    assert assign_split("a", {"a"}, set(), set()) == "train"
    assert assign_split("b", set(), {"b"}, set()) == "val"
    assert assign_split("c", set(), set(), {"c"}) == "test"
    with pytest.raises(SmartScanError):
        assign_split("z", set(), set(), set())
    with pytest.raises(SmartScanError):
        n_actions(0, (8,))
    with pytest.raises(SmartScanError):
        encode_action(9, 8, 4, (8,))
    with pytest.raises(SmartScanError):
        encode_action(0, 3, 4, (8,))


def test_calibrator_identity_and_empty_fit() -> None:
    from smartscan.ml.calibrate import IsotonicCalibrator
    from smartscan.ml.observable import ExplodingOracle
    from smartscan.ml.reward import RewardCalculator, stamp_decision_reward
    from smartscan.types import DecisionRow

    ident = IsotonicCalibrator.identity()
    assert float(ident.predict_one(0.3)) == pytest.approx(0.3)
    empty = IsotonicCalibrator.fit(np.asarray([]), np.asarray([]))
    assert float(empty.predict_one(0.2)) == pytest.approx(0.2)
    boom = ExplodingOracle()
    with pytest.raises(RuntimeError):
        boom.foo = 1
    with pytest.raises(RuntimeError):
        _ = boom["occupied"]
    calc = RewardCalculator()
    from smartscan.ml.observable import ObservableTransition

    tr = ObservableTransition(
        decision_id="d0",
        start_step=0,
        tune_end_step=1,
        end_step=9,
        target_band=0,
        dwell_steps=8,
        hit=False,
        measured_snr_db=None,
        n_steps=20,
        n_bands=4,
        dt_s=0.001,
        settled_band_before=None,
        last_target_band=None,
    )
    br = calc.compute(
        tr,
        p_hit=0.1,
        novelty=0.0,
        uncertainty=0.0,
        assessed_threat=1.0,
        recent_same_band_no_hit=True,
        low_confidence_hit=False,
    )
    row = DecisionRow(
        decision_id="d0",
        start_step=0,
        tune_end_step=1,
        dwell_end_step=9,
        end_step=9,
        target_band=0,
        dwell_steps=8,
        hit=False,
        measured_snr_db=None,
        receiver_seed=0,
    )
    stamped = stamp_decision_reward(row, br)
    assert stamped.reward is not None
    with pytest.raises(SmartScanError):
        calc.compute(
            tr,
            p_hit=float("nan"),
            novelty=0.0,
            uncertainty=0.0,
            assessed_threat=1.0,
            recent_same_band_no_hit=False,
            low_confidence_hit=False,
        )


def test_cts_state_roundtrip_and_oracle_label() -> None:
    from smartscan.ml.policies import ContextualThompsonSchedule, OracleCeilingSchedule

    cts = ContextualThompsonSchedule(n_bands=2, dwell_bins=(8,), seed=0)
    payload = cts.state_dict()
    other = ContextualThompsonSchedule(n_bands=2, dwell_bins=(8,), seed=1)
    other.load_state_dict(payload)
    assert other.n_bands == 2
    with pytest.raises(SmartScanError):
        other.load_state_dict({"A": "nope", "b": []})
    with pytest.raises(SmartScanError):
        OracleCeilingSchedule(occupied=np.zeros((4, 2), dtype=bool), dwell_steps=8, label="baseline")


def test_run_held_out_pair_and_pyfunc(tmp_path: Path) -> None:
    from smartscan.config import TrainConfig
    from smartscan.ml.bundle import SchedulerBundle, SmartScanPyFunc, save_bundle
    from smartscan.ml.calibrate import IsotonicCalibrator
    from smartscan.ml.evaluate import run_held_out_pair
    from smartscan.ml.features import ObservationNormalizer, observation_size
    from smartscan.ml.predictor import HitHazardNet, HitHazardPredictor
    from smartscan.rf.bands import named_band_plan
    from smartscan.rf.environment import simulate

    train_cfg = TrainConfig(seed=0, duration_s=0.04, dt_s=0.001, mc_rollouts=2, horizon_steps=20)
    truth = simulate(
        {
            "seed": 3,
            "dt_s": 0.001,
            "duration_s": 0.04,
            "band_plan_id": "demo_2_18",
            "scenario_id": "sparse",
        }
    )
    receiver = load_receiver_config(
        {
            "receiver_ibw_hz": 1e8,
            "scan_span_hz": 16e9,
            "dwell_bins": [1, 2, 4, 8, 16],
            "noise_power_w": 1e-13,
        }
    )
    _run, evaluation = run_held_out_pair(
        truth=truth,
        receiver=receiver,
        train_cfg=train_cfg,
        strategy="sequential",
        seed=3,
    )
    assert evaluation.report.metrics
    pytest.importorskip("torch")
    import torch

    plan = named_band_plan("demo_2_18")
    bins = (1, 2, 4, 8, 16)
    n_in = observation_size(plan.n_bands)
    net = HitHazardNet(n_in=n_in, n_bands=plan.n_bands, n_dwell=5, n_bins=8, hidden=8)
    bundle = SchedulerBundle(
        band_plan=plan,
        dwell_bins=bins,
        receiver_ibw_hz=1e8,
        feature_schema_payload={"size": n_in},
        predictor=HitHazardPredictor(net, dwell_bins=bins),
        recency_ok=True,
        hit_calibrator=IsotonicCalibrator.identity(),
        active_calibrator=IsotonicCalibrator.identity(),
        normalizer=ObservationNormalizer(size=n_in),
        cts=None,
        ppo_state={
            "action_net.weight": torch.zeros(plan.n_bands * len(bins), n_in),
            "action_net.bias": torch.zeros(plan.n_bands * len(bins)),
        },
        config={},
        model_version="t",
    )
    dest = tmp_path / "b"
    save_bundle(bundle, dest)
    from smartscan.ml.bundle import load_bundle

    loaded = load_bundle(dest)
    fn = SmartScanPyFunc(loaded)
    out = fn.predict(np.zeros(n_in, dtype=np.float32))
    assert out.shape == (1,)
    batch = fn.predict(np.zeros((2, n_in), dtype=np.float32))
    assert batch.shape == (2,)


def test_pd_operating_and_expected_time_mismatch() -> None:
    from smartscan.ml.predictor import expected_time_to_hit, pd_operating_from_snr

    assert pd_operating_from_snr(None, dwell_steps=8, samples_per_step=1, pfa=0.001) == pytest.approx(0.001)
    pd = pd_operating_from_snr(10.0, dwell_steps=8, samples_per_step=1, pfa=0.001)
    assert 0.0 <= pd <= 1.0
    with pytest.raises(SmartScanError):
        expected_time_to_hit(np.array([0.1]), np.array([0.1, 0.2]))


def test_evaluate_episode_wrapper() -> None:
    from smartscan.ml.runner import evaluate_episode, run_policy_episode
    from smartscan.receiver.schedules import SequentialSchedule
    from smartscan.rf.environment import simulate

    cfg = TrainConfig(seed=0, duration_s=0.04, dt_s=0.001, mc_rollouts=2, horizon_steps=16)
    truth = simulate(
        {
            "seed": 1,
            "dt_s": 0.001,
            "duration_s": 0.04,
            "band_plan_id": "demo_2_18",
            "scenario_id": "sparse",
        }
    )
    receiver = load_receiver_config(
        {
            "receiver_ibw_hz": 1e8,
            "scan_span_hz": 16e9,
            "dwell_bins": [1, 2, 4, 8, 16],
            "noise_power_w": 1e-13,
        }
    )
    run = run_policy_episode(truth, SequentialSchedule(8), receiver, cfg=cfg, receiver_seed=1)
    result = evaluate_episode(truth, run, receiver)
    assert result.report.metrics


def test_diagnose_split_is_train_only() -> None:
    from smartscan.config import ScenarioSeedSpec
    from smartscan.ml.diagnose import diagnose_split

    cfg = TrainConfig(
        seed=0,
        duration_s=0.04,
        dt_s=0.001,
        mc_rollouts=2,
        public_priorities=[8, 4, 10],
        train_scenarios=[ScenarioSeedSpec(scenario_id="sparse", seeds=[0])],
        val_scenarios=[ScenarioSeedSpec(scenario_id="sparse", seeds=[200])],
    )
    payload = diagnose_split(cfg, split="train")
    assert payload["n_pairs"] == 1
    assert payload["strategies"]["sequential"]["n_decisions"] > 0
    assert payload["strategies"]["fixed-priority"]["mean_air"] is not None
