from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from smartscan.config import RewardWeights, TrainConfig, load_yaml, project_root
from smartscan.ml.actions import (
    assert_legal_band_dwell,
    command_from_policy_action,
    decode_action,
    decode_multidiscrete,
    encode_action,
    logits_to_discrete_action,
    n_actions,
)
from smartscan.ml.calibrate import brier_score, expected_calibration_error
from smartscan.ml.features import (
    FeatureBuilder,
    ObservationNormalizer,
    compose_observation,
    observation_size,
)
from smartscan.ml.observable import ExplodingOracle, ObservableTransition, assert_no_oracle_payload
from smartscan.ml.protocol import (
    HELD_OUT_SEEDS,
    assert_disjoint_protocol,
    build_fresh_test_manifest,
    is_held_out_seed,
)
from smartscan.ml.reward import RewardCalculator
from smartscan.types import SmartScanError


def _tr(**kwargs: object) -> ObservableTransition:
    payload: dict[str, object] = {
        "decision_id": "d0",
        "start_step": 0,
        "tune_end_step": 1,
        "end_step": 9,
        "target_band": 3,
        "dwell_steps": 8,
        "hit": True,
        "measured_snr_db": 6.0,
        "n_steps": 200,
        "n_bands": 16,
        "dt_s": 0.001,
        "settled_band_before": None,
        "last_target_band": None,
    }
    payload.update(kwargs)
    return ObservableTransition(**payload)  # type: ignore[arg-type]


def test_improve_config_disjoint_and_avoids_held_out() -> None:
    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_improve.yaml"))
    info = assert_disjoint_protocol(cfg)
    assert info["n_train"] > 0 and info["n_val"] > 0
    assert info["n_dev_test"] > 0
    assert not info["held_out_seeds_used"]
    for spec in (*cfg.train_scenarios, *cfg.val_scenarios, *cfg.test_scenarios):
        for seed in spec.seeds:
            assert seed not in HELD_OUT_SEEDS
            assert not is_held_out_seed(seed)


def test_train_config_rejects_held_out_seeds() -> None:
    with pytest.raises(Exception, match="frozen evaluation"):
        TrainConfig(train_scenarios=[{"scenario_id": "sparse", "seeds": [1000]}])
    with pytest.raises(Exception, match="frozen evaluation"):
        TrainConfig(train_scenarios=[{"scenario_id": "sparse", "seeds": [9000]}])


def test_fresh_test_manifest_never_uses_held_out_or_improve_seeds() -> None:
    payload = build_fresh_test_manifest()
    assert payload["n_paired_seeds"] >= 30
    pairs = {(item["scenario_id"], int(item["seed"])) for item in payload["pairs"]}
    assert all(not is_held_out_seed(int(seed)) for _fam, seed in pairs)
    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_improve.yaml"))
    used = {
        (spec.scenario_id, int(seed))
        for spec in (*cfg.train_scenarios, *cfg.val_scenarios, *cfg.test_scenarios)
        for seed in spec.seeds
    }
    assert not (pairs & used)
    assert "8000" in str(payload["seeds"])


def test_reward_per_step_not_dominated_by_dt() -> None:
    tr = _tr()
    legacy = RewardCalculator(RewardWeights(time_cost_mode="dt_scaled")).compute(
        tr,
        p_hit=0.5,
        novelty=0.0,
        uncertainty=0.0,
        assessed_threat=1.0,
        recent_same_band_no_hit=False,
        low_confidence_hit=False,
    )
    scaled = RewardCalculator(
        RewardWeights(time_cost_mode="per_step", c_tune=0.08, c_time=0.06)
    ).compute(
        tr,
        p_hit=0.5,
        novelty=0.0,
        uncertainty=0.0,
        assessed_threat=1.0,
        recent_same_band_no_hit=False,
        low_confidence_hit=False,
    )
    assert scaled.cost_tune > legacy.cost_tune * 10
    assert scaled.cost_time > legacy.cost_time * 10
    assert scaled.cost_tune < scaled.reward_hit
    assert scaled.cost_time < scaled.reward_hit
    excess = RewardCalculator(
        RewardWeights(time_cost_mode="excess_dwell", c_tune=0.03, c_time=0.05)
    ).compute(
        _tr(end_step=8, dwell_steps=8),
        p_hit=0.5,
        novelty=0.0,
        uncertainty=0.0,
        assessed_threat=1.0,
        recent_same_band_no_hit=False,
        low_confidence_hit=False,
    )
    assert excess.cost_time == pytest.approx(0.0)
    long = RewardCalculator(
        RewardWeights(time_cost_mode="excess_dwell", c_tune=0.03, c_time=0.05)
    ).compute(
        _tr(end_step=17, dwell_steps=16),
        p_hit=0.5,
        novelty=0.0,
        uncertainty=0.0,
        assessed_threat=1.0,
        recent_same_band_no_hit=False,
        low_confidence_hit=False,
    )
    assert long.cost_time > 0.0


def test_multidiscrete_actions_are_legal_only() -> None:
    bins = (1, 2, 4, 8, 16)
    cmd = command_from_policy_action(
        np.asarray([8, 3]),
        decision_index=0,
        n_bands=16,
        dwell_bins=bins,
        layout="multidiscrete",
    )
    assert cmd.target_band == 8
    assert cmd.dwell_steps == 8
    assert_legal_band_dwell(cmd.target_band, cmd.dwell_steps, 16, bins)
    with pytest.raises(SmartScanError):
        decode_multidiscrete(np.asarray([16, 0]), 16, bins)
    with pytest.raises(SmartScanError):
        decode_multidiscrete(np.asarray([0, 9]), 16, bins)
    flat = encode_action(8, 8, 16, bins)
    band, dwell = decode_action(flat, 16, bins)
    assert (band, dwell) == (8, 8)
    import torch

    logits = torch.zeros(n_actions(16, bins))
    logits[flat] = 3.0
    assert logits_to_discrete_action(logits, 16, bins) == flat
    factor = torch.zeros(16 + 5)
    factor[8] = 4.0
    factor[16 + 3] = 4.0
    assert logits_to_discrete_action(factor, 16, bins) == flat


def test_composed_observation_masks_and_no_oracle() -> None:
    builder = FeatureBuilder(n_bands=4, dt_s=0.001, dwell_bins=(4, 8))
    vec = compose_observation(
        builder,
        step=0,
        n_steps=50,
        settled_band=None,
        last_target_band=None,
        last_dwell_steps=None,
        include_predictor_obs=True,
        include_action_history=4,
    )
    expected = observation_size(4, predictor_obs=True, action_history=4)
    assert vec.shape == (expected,)
    assert np.all(np.isfinite(vec))
    builder.observe(_tr(n_bands=4, target_band=1, hit=True))
    vec2 = compose_observation(
        builder,
        step=9,
        n_steps=50,
        settled_band=1,
        last_target_band=1,
        last_dwell_steps=8,
        include_predictor_obs=True,
        include_action_history=4,
    )
    assert vec2.shape == (expected,)
    assert np.all(np.isfinite(vec2))
    boom = ExplodingOracle()
    with pytest.raises(RuntimeError):
        _ = boom.occupied
    assert_no_oracle_payload({"p_hit": 0.2}, where="obs")
    with pytest.raises(SmartScanError):
        assert_no_oracle_payload({"oracle_events": 1}, where="obs")
    from smartscan.ml.predictor import RecencyPredictor

    rec = RecencyPredictor(n_bands=4, horizon_s=0.1)
    neural = compose_observation(
        builder,
        step=9,
        n_steps=50,
        settled_band=1,
        last_target_band=1,
        last_dwell_steps=8,
        predictor=rec,
        include_predictor_obs=True,
        include_neural_predictor_obs=True,
        include_action_history=0,
        default_dwell_steps=8,
    )
    assert neural.shape == (observation_size(4, predictor_obs=True, action_history=0),)


def test_action_history_is_causal() -> None:
    builder = FeatureBuilder(n_bands=4, dt_s=0.001, dwell_bins=(8,))
    builder.observe(_tr(n_bands=4, target_band=1, hit=True, end_step=9))
    snap = builder.snapshot()
    h1 = snap.action_history_features(4)
    builder.observe(
        _tr(
            n_bands=4,
            decision_id="d1",
            start_step=9,
            tune_end_step=9,
            end_step=17,
            target_band=2,
            hit=False,
        )
    )
    h2 = snap.action_history_features(4)
    assert np.allclose(h1, h2)


def test_normalizer_rejects_nan_and_persists() -> None:
    norm = ObservationNormalizer(size=4)
    with pytest.raises(SmartScanError, match="NaN"):
        norm.transform(np.array([1.0, np.nan, 0.0, 0.0]))
    x = np.arange(4, dtype=np.float64)
    norm.update(x)
    norm.update(x + 1)
    z = norm.transform(x)
    restored = ObservationNormalizer.from_state(norm.state_dict())
    assert np.allclose(restored.transform(x), z)
    assert restored.count == 2


def test_calibration_metrics() -> None:
    p = np.array([0.1, 0.9, 0.9, 0.1])
    y = np.array([0.0, 1.0, 1.0, 0.0])
    assert brier_score(p, y) < 0.05
    assert expected_calibration_error(p, y, n_bins=2) < 0.2
    assert expected_calibration_error(np.asarray([]), np.asarray([])) == 0.0


def test_residual_predictor_roundtrip_and_eval_mode() -> None:
    pytest.importorskip("torch")
    from smartscan.ml.predictor import HitHazardNet, HitHazardPredictor

    net = HitHazardNet(n_in=8, n_bands=4, n_dwell=2, n_bins=4, hidden=8, arch="residual_ln", dropout=0.1)
    net.train_mode()
    net.eval_mode()
    feats = np.zeros(8, dtype=np.float32)
    q, h, u = net.forward(feats, 0, 0, [(0, 8)])
    assert 0.0 < float(q.detach().squeeze()) < 1.0
    pred = HitHazardPredictor(net, dwell_bins=(4, 8))
    payload = pred.net.state_dict()
    net2 = HitHazardNet(n_in=8, n_bands=4, n_dwell=2, n_bins=4, hidden=8, arch="residual_ln", dropout=0.1)
    net2.load_state_dict(payload)
    net2.eval_mode()
    q2, _h2, _u2 = net2.forward(feats, 0, 0, [(0, 8)])
    assert abs(float(q.detach().squeeze()) - float(q2.detach().squeeze())) < 1e-6


def test_predictor_residual_trains_on_tiny_cpu() -> None:
    pytest.importorskip("torch")
    from smartscan.ml.dataset import collect_exploration
    from smartscan.ml.train import train_predictor
    from smartscan.rf.bands import named_band_plan

    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    cfg.duration_s = 0.04
    cfg.n_epochs_predictor = 1
    cfg.collect_strategies = ["sequential"]
    cfg.predictor_arch = "residual_ln"
    cfg.predictor_dropout = 0.1
    cfg.predictor_balance = True
    cfg.predictor_patience = 1
    rows, _manifest = collect_exploration(cfg)
    n_bands = named_band_plan(cfg.band_plan_id).n_bands
    predictor, _hit, _act, metrics = train_predictor(rows, cfg, n_bands=n_bands)
    assert "val_brier_cal" in metrics
    assert predictor.model_version == cfg.model_version


def test_tiny_ppo_with_composed_observation() -> None:
    pytest.importorskip("stable_baselines3")
    from smartscan.ml.train import train_ppo

    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    cfg.duration_s = 0.04
    cfg.timesteps = 32
    cfg.ppo_n_steps = 8
    cfg.ppo_batch_size = 8
    cfg.ppo_n_epochs = 1
    cfg.mc_rollouts = 2
    cfg.eval_cadence = 0
    cfg.include_predictor_obs = True
    cfg.include_action_history = 2
    cfg.balanced_family_sampling = True
    state, normalizer, meta = train_ppo(cfg)
    assert state
    assert normalizer.size == observation_size(16, predictor_obs=True, action_history=2)
    assert meta["checkpoint"] == "final"
    assert int(meta["normalizer_count"]) >= 2


def test_curriculum_catalog_and_protocol_write(tmp_path: Path) -> None:
    from smartscan.config import ScenarioSeedSpec
    from smartscan.ml.env import SmartScanEnv
    from smartscan.ml.protocol import write_fresh_test_manifest
    from smartscan.ml.train import selection_score

    cfg = TrainConfig(
        seed=0,
        duration_s=0.04,
        dt_s=0.001,
        mc_rollouts=2,
        train_scenarios=[
            ScenarioSeedSpec(scenario_id="sparse", seeds=[10]),
            ScenarioSeedSpec(scenario_id="dense", seeds=[10]),
        ],
        balanced_family_sampling=True,
        curriculum_families=[["sparse"], ["sparse", "dense"]],
        curriculum_episode_boundaries=[1],
    )
    env = SmartScanEnv(cfg, record_forecast=False)
    env.reset()
    env.reset()
    score = selection_score({"air": 2.0, "interception_ratio": 0.5, "delay": 0.1, "pfa": 0.0}, cfg)
    assert score == pytest.approx(2.0 * 1.0 + 0.5 * 0.5 + (-0.05) * 0.1)
    dest = tmp_path / "fresh.json"
    payload = write_fresh_test_manifest(dest, overwrite=False)
    again = write_fresh_test_manifest(dest, overwrite=False)
    assert payload["content_fingerprint"] == again["content_fingerprint"]
    with pytest.raises(SmartScanError):
        from smartscan.ml.protocol import assert_no_held_out_seeds

        assert_no_held_out_seeds([("sparse", 1000)], where="test")


def test_multidiscrete_env_samples_legal_commands() -> None:
    gymnasium = pytest.importorskip("gymnasium")
    from smartscan.ml.env import SmartScanEnv

    del gymnasium
    cfg = TrainConfig(
        seed=0,
        duration_s=0.04,
        dt_s=0.001,
        mc_rollouts=2,
        action_layout="multidiscrete",
        train_scenarios=[],
    )
    env = SmartScanEnv(cfg, record_forecast=False)
    obs, _info = env.reset(seed=0)
    assert obs.shape[0] == observation_size(16)
    for _ in range(4):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, _info = env.step(action)
        assert np.isfinite(reward)
        if terminated or truncated:
            break
    rows = env.receiver_run().decisions.rows
    bins = set(cfg.dwell_bins)
    for row in rows:
        assert 0 <= row.target_band < 16
        assert row.dwell_steps in bins


def test_v2_held_out_files_untouched_fingerprint() -> None:
    from smartscan.ml.evaluate import load_held_out_manifest

    payload = load_held_out_manifest(project_root() / "configs" / "held_out_manifest.json")
    assert payload["content_fingerprint"] == (
        "4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4"
    )
    assert payload["pairs"][0]["seed"] == 1000


def test_first_hit_only_and_coverage_reward() -> None:
    first = _tr(target_band=3, hit=True)
    farm = _tr(target_band=3, hit=True, start_step=9, end_step=18)
    weights = RewardWeights(
        first_hit_only=True,
        w_hit=1.0,
        w_coverage=0.2,
        coverage_window=16,
        c_action=0.05,
        c_repeat_hit=0.3,
        time_cost_mode="excess_dwell",
        c_tune=0.0,
        c_time=0.0,
    )
    calc = RewardCalculator(weights)
    from smartscan.ml.reward import is_coverage_visit, is_first_hit_on_visit

    assert is_first_hit_on_visit([], first)
    assert not is_first_hit_on_visit([first], farm)
    assert is_coverage_visit([], 3, 16)
    assert not is_coverage_visit([first], 3, 16)
    open_hit = calc.compute(
        first,
        p_hit=0.5,
        novelty=0.0,
        uncertainty=0.0,
        assessed_threat=1.0,
        recent_same_band_no_hit=False,
        low_confidence_hit=False,
        first_hit_on_visit=True,
        coverage_visit=True,
    )
    farmed = calc.compute(
        farm,
        p_hit=0.5,
        novelty=0.0,
        uncertainty=0.0,
        assessed_threat=1.0,
        recent_same_band_no_hit=False,
        low_confidence_hit=False,
        first_hit_on_visit=False,
        coverage_visit=False,
    )
    assert open_hit.reward_hit == pytest.approx(1.0)
    assert farmed.reward_hit == pytest.approx(0.0)
    assert open_hit.reward > farmed.reward
    assert farmed.cost_repeat >= 0.3
    assert open_hit.cost_time == pytest.approx(0.05)


def test_v4_config_and_fresh_manifest_disjoint(tmp_path: Path) -> None:
    from smartscan.ml.protocol import (
        FRESH_TEST_SEEDS,
        FRESH_TEST_V4_SEEDS,
        assert_disjoint_protocol,
        write_fresh_test_v4_manifest,
    )

    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_v4.yaml"))
    info = assert_disjoint_protocol(cfg)
    assert not info["held_out_seeds_used"]
    used = {
        int(seed)
        for spec in (*cfg.train_scenarios, *cfg.val_scenarios, *cfg.test_scenarios)
        for seed in spec.seeds
    }
    assert used.isdisjoint(set(FRESH_TEST_SEEDS))
    assert used.isdisjoint(set(FRESH_TEST_V4_SEEDS))
    dest = tmp_path / "v4.json"
    payload = write_fresh_test_v4_manifest(dest, overwrite=False)
    assert payload["seeds"][0] == 9000
    assert 8000 not in payload["seeds"]
    again = write_fresh_test_v4_manifest(dest, overwrite=False)
    assert again["content_fingerprint"] == payload["content_fingerprint"]


def test_behavioral_clone_one_epoch() -> None:
    pytest.importorskip("stable_baselines3")
    from smartscan.ml.train import collect_teacher_actions, train_ppo

    cfg = TrainConfig.model_validate(load_yaml(project_root() / "configs" / "train_smoke.yaml"))
    cfg.duration_s = 0.04
    cfg.timesteps = 16
    cfg.ppo_n_steps = 8
    cfg.ppo_batch_size = 8
    cfg.ppo_n_epochs = 1
    cfg.mc_rollouts = 1
    cfg.eval_cadence = 0
    cfg.action_layout = "multidiscrete"
    cfg.include_predictor_obs = True
    cfg.include_action_history = 2
    cfg.ppo_bc_epochs = 2
    cfg.ppo_bc_episodes = 1
    cfg.ppo_bc_teachers = ["sequential"]
    state, normalizer, meta = train_ppo(cfg)
    assert state
    assert meta.get("bc_loss") is not None
    obs, acts = collect_teacher_actions(
        cfg,
        predictor=None,
        normalizer=normalizer,
        n_episodes=1,
        teachers=["sequential"],
    )
    assert obs.shape[0] == acts.shape[0]
    assert acts.shape[1] == 2
    assert int(acts[0, 0]) == 0

