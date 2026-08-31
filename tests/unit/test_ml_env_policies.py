from __future__ import annotations

import numpy as np
import pytest

from smartscan.config import TrainConfig
from smartscan.ml.env import SmartScanEnv
from smartscan.ml.policies import (
    ContextualThompsonSchedule,
    PeriodicInterceptSchedule,
    ReactiveSchedule,
    make_policy,
)
from smartscan.ml.runner import run_policy_episode
from smartscan.receiver.detector import load_receiver_config
from smartscan.receiver.schedules import SequentialSchedule
from smartscan.rf.environment import simulate
from smartscan.types import SmartScanError


def _cfg() -> TrainConfig:
    return TrainConfig(
        seed=0,
        duration_s=0.05,
        dt_s=0.001,
        noise_power_w=1e-13,
        mc_rollouts=4,
        horizon_steps=20,
        train_scenarios=[],
    )


def test_make_policy_refuses_oracle_without_flag() -> None:
    with pytest.raises(SmartScanError, match="evaluator-only"):
        make_policy("oracle-ceiling", dwell_steps=8, allow_oracle=False)


def test_reactive_and_cts_and_sequential_compatible_logs() -> None:
    cfg = _cfg()
    truth = simulate(
        {
            "seed": 0,
            "dt_s": 0.001,
            "duration_s": 0.05,
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
    for schedule in (
        SequentialSchedule(8),
        ReactiveSchedule(8, seed=0),
        PeriodicInterceptSchedule(8, seed=0),
        ContextualThompsonSchedule(n_bands=16, dwell_bins=(1, 2, 4, 8, 16), seed=1),
    ):
        run = run_policy_episode(truth, schedule, receiver, cfg=cfg, receiver_seed=0)
        assert run.decisions.rows
        assert all(row.p_hit is not None for row in run.decisions.rows)
        assert all(row.reward is not None for row in run.decisions.rows)
        assert run.decisions.predicted_interception_ratio is not None


def test_gym_env_checker_and_oracle_info_prefix() -> None:
    gymnasium = pytest.importorskip("gymnasium")
    from gymnasium.utils.env_checker import check_env

    env = SmartScanEnv(_cfg(), record_forecast=False)
    check_env(env, skip_render_check=True)
    obs, info = env.reset(seed=0)
    assert obs.dtype == np.float32
    assert gymnasium.spaces.Box
    terminated = False
    truncated = False
    last_info = info
    for _ in range(30):
        action = int(env.action_space.sample())
        obs, reward, terminated, truncated, last_info = env.step(action)
        assert np.all(np.isfinite(obs))
        assert np.isfinite(reward)
        policy_info = env.strip_oracle_info(last_info)
        assert all(not k.startswith("oracle_") for k in policy_info)
        if terminated or truncated:
            break
    assert terminated or truncated
    assert any(str(k).startswith("oracle_") for k in last_info)


def test_action_decode_matches_space() -> None:
    env = SmartScanEnv(_cfg(), record_forecast=False)
    env.reset(seed=1)
    n = int(env.action_space.n)
    obs, reward, term, trunc, info = env.step(n - 1)
    del obs, reward, term, trunc, info
    with pytest.raises(SmartScanError):
        env.step(n)


def test_env_records_horizon_and_receiver_run() -> None:
    env = SmartScanEnv(_cfg(), record_forecast=True)
    env.reset(seed=2)
    terminated = False
    for _ in range(40):
        _, _, terminated, truncated, _ = env.step(0)
        if terminated or truncated:
            break
    run = env.receiver_run()
    assert run.decisions.rows
    assert run.decisions.predicted_interception_ratio is not None
    with pytest.raises(SmartScanError):
        fresh = SmartScanEnv(_cfg(), record_forecast=False)
        fresh.step(0)


def test_oracle_ceiling_and_ppo_wrapper() -> None:
    cfg = _cfg()
    truth = simulate(
        {
            "seed": 0,
            "dt_s": 0.001,
            "duration_s": 0.05,
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
    ceiling = make_policy(
        "oracle-ceiling",
        dwell_steps=8,
        allow_oracle=True,
        occupied=truth.occupied,
    )
    run = run_policy_episode(truth, ceiling, receiver, cfg=cfg, receiver_seed=0)
    assert run.decisions.rows
    from smartscan.ml.features import FeatureBuilder

    builder = FeatureBuilder(n_bands=truth.band_plan.n_bands, dt_s=0.001, dwell_bins=(1, 2, 4, 8, 16))
    ppo = make_policy(
        "ppo",
        dwell_steps=8,
        n_bands=truth.band_plan.n_bands,
        dwell_bins=(1, 2, 4, 8, 16),
        ppo_predict=lambda _obs: 0,
        feature_builder=builder,
    )
    run2 = run_policy_episode(truth, ppo, receiver, cfg=cfg, receiver_seed=0)
    assert run2.decisions.rows
    with pytest.raises(SmartScanError):
        make_policy("oracle-ceiling", dwell_steps=8, allow_oracle=True, occupied=None)
    with pytest.raises(SmartScanError):
        make_policy("ppo", dwell_steps=8)


def test_episode_catalog_and_frozen_stats() -> None:
    from smartscan.config import ScenarioSeedSpec
    from smartscan.ml.env import episode_catalog

    cfg = TrainConfig(
        seed=0,
        duration_s=0.05,
        dt_s=0.001,
        train_scenarios=[
            ScenarioSeedSpec(scenario_id="sparse", seeds=[0, 1]),
            ScenarioSeedSpec(scenario_id="dense", seeds=[0]),
        ],
    )
    pairs = episode_catalog(cfg, "train")
    assert pairs == [("sparse", 0), ("sparse", 1), ("dense", 0)]
    env = SmartScanEnv(cfg, record_forecast=False, freeze_obs_stats=True)
    env.reset(seed=0)
    count0 = env.normalizer.count
    env.step(0)
    assert env.normalizer.count == count0


def test_builder_backed_predictor_signature() -> None:
    pytest.importorskip("torch")
    from smartscan.ml.features import FeatureBuilder, observation_size
    from smartscan.ml.predictor import (
        BuilderBackedHazardPredictor,
        HitHazardNet,
        HitHazardPredictor,
    )

    n_in = observation_size(4)
    net = HitHazardNet(n_in=n_in, n_bands=4, n_dwell=1, n_bins=4, hidden=8)
    inner = HitHazardPredictor(net, dwell_bins=(8,))
    wrapped = BuilderBackedHazardPredictor(inner)
    builder = FeatureBuilder(n_bands=4, dt_s=0.001, dwell_bins=(8,))
    fc = wrapped.forecast_next_intercept(
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
    assert 0.0 <= fc.p_hit_within_dwell <= 1.0
