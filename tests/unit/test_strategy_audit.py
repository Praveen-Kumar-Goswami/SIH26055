from __future__ import annotations

import inspect
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from smartscan.config import TrainConfig
from smartscan.dashboard.services import DEMO_STRATEGIES, explain_decision, run_experiment
from smartscan.metrics.engine import evaluate_strategy
from smartscan.ml.features import FeatureBuilder
from smartscan.ml.observable import ExplodingOracle
from smartscan.ml.policies import (
    PERIODIC_INTERCEPT_STRATEGY,
    PUBLIC_STRATEGIES,
    ContextualThompsonSchedule,
    PeriodicInterceptSchedule,
    ReactiveSchedule,
    construct_live_policy,
    make_policy,
)
from smartscan.ml.strategy_registry import (
    HELD_OUT_BASELINE_STRATEGIES,
    LIVE_STRATEGIES,
    STRATEGY_REGISTRY,
    canonicalize_strategy_id,
    parse_cli_strategy,
    public_strategy_count,
)
from smartscan.receiver.detector import load_receiver_config
from smartscan.receiver.schedules import ScheduleView, make_schedule
from smartscan.rf.environment import simulate
from smartscan.types import SmartScanError


def _view(**kwargs: object) -> ScheduleView:
    payload: dict[str, object] = {
        "step": 0,
        "n_steps": 400,
        "n_bands": 4,
        "settled_band": None,
        "last_target_band": None,
        "dwell_bins": (2, 8),
        "default_dwell_steps": 8,
        "decision_index": 0,
        "dt_s": 0.01,
    }
    payload.update(kwargs)
    return ScheduleView(**payload)  # type: ignore[arg-type]


def _receiver():
    return load_receiver_config(
        {
            "receiver_ibw_hz": 1e8,
            "scan_span_hz": 16e9,
            "dwell_bins": [1, 2, 4, 8, 16],
            "noise_power_w": 1e-13,
        }
    )


def test_public_strategy_count_and_exact_set() -> None:
    assert public_strategy_count() == 7
    assert len(PUBLIC_STRATEGIES) == 7
    assert set(PUBLIC_STRATEGIES) == {
        "sequential",
        "random",
        "fixed-priority",
        "reactive",
        "contextual-thompson",
        "periodic-intercept",
        "ppo",
    }
    assert PERIODIC_INTERCEPT_STRATEGY == "periodic-intercept"
    assert list(DEMO_STRATEGIES) == list(PUBLIC_STRATEGIES)
    assert list(LIVE_STRATEGIES) == [name for name in PUBLIC_STRATEGIES if name != "ppo"]
    assert len(HELD_OUT_BASELINE_STRATEGIES) == 5
    assert "periodic-intercept" not in HELD_OUT_BASELINE_STRATEGIES
    assert set(STRATEGY_REGISTRY) == set(PUBLIC_STRATEGIES)


def test_aliases_are_not_public_ids() -> None:
    for alias in (
        "fixed_priority",
        "fixedpriority",
        "contextual_thompson",
        "thompson",
        "periodic_intercept",
        "periodic",
        "PPO",
        "ppo-v3",
        "cts",
        "scheduler",
    ):
        if alias.lower().replace("_", "-") in PUBLIC_STRATEGIES:
            continue
        if alias == "PPO":
            assert canonicalize_strategy_id(alias) == "ppo"
            continue
        if alias in {"fixed_priority", "contextual_thompson", "periodic_intercept"}:
            assert canonicalize_strategy_id(alias) in PUBLIC_STRATEGIES
            assert alias not in PUBLIC_STRATEGIES
            continue
        mapped = canonicalize_strategy_id(alias) if alias not in {"fixedpriority", "ppo-v3"} else None
        if alias in {"thompson", "periodic", "cts", "scheduler"}:
            assert mapped in PUBLIC_STRATEGIES
            assert alias not in PUBLIC_STRATEGIES
        else:
            with pytest.raises(SmartScanError, match="Unknown strategy"):
                canonicalize_strategy_id(alias)


@pytest.mark.parametrize("strategy", list(PUBLIC_STRATEGIES))
def test_make_policy_constructs_every_public_strategy(strategy: str) -> None:
    kwargs: dict[str, object] = {
        "dwell_steps": 8,
        "schedule_seed": 0,
        "band_order": (8, 4, 10),
        "n_bands": 16,
        "dwell_bins": (1, 2, 4, 8, 16),
    }
    if strategy == "ppo":
        builder = FeatureBuilder(n_bands=16, dt_s=0.001, dwell_bins=(1, 2, 4, 8, 16))
        kwargs["ppo_predict"] = lambda _obs: 0
        kwargs["feature_builder"] = builder
    policy = make_policy(strategy, **kwargs)  # type: ignore[arg-type]
    assert hasattr(policy, "next_command")
    if strategy == "contextual-thompson":
        assert isinstance(policy, ContextualThompsonSchedule)
    if strategy == "periodic-intercept":
        assert isinstance(policy, PeriodicInterceptSchedule)
    if strategy == "reactive":
        assert isinstance(policy, ReactiveSchedule)


@pytest.mark.parametrize("strategy", list(PUBLIC_STRATEGIES))
def test_every_public_strategy_executes_legal_logs(strategy: str) -> None:
    from smartscan.ml.runner import run_policy_episode

    cfg = TrainConfig(
        seed=0,
        duration_s=0.05,
        dt_s=0.001,
        noise_power_w=1e-13,
        mc_rollouts=2,
        horizon_steps=16,
        public_priorities=[8, 4, 10],
    )
    truth = simulate(
        {
            "seed": 1,
            "dt_s": 0.001,
            "duration_s": 0.05,
            "band_plan_id": "demo_2_18",
            "scenario_id": "sparse",
        }
    )
    receiver = _receiver()
    kwargs: dict[str, object] = {
        "dwell_steps": 8,
        "schedule_seed": 3,
        "band_order": (8, 4, 10),
        "n_bands": truth.band_plan.n_bands,
        "dwell_bins": tuple(int(x) for x in receiver.dwell_bins),
    }
    if strategy == "ppo":
        kwargs["ppo_predict"] = lambda _obs: 0
        kwargs["feature_builder"] = FeatureBuilder(
            n_bands=truth.band_plan.n_bands,
            dt_s=0.001,
            dwell_bins=tuple(int(x) for x in receiver.dwell_bins),
        )
    policy = make_policy(strategy, **kwargs)  # type: ignore[arg-type]
    run = run_policy_episode(truth, policy, receiver, cfg=cfg, receiver_seed=0)
    assert run.decisions.rows
    assert run.observations.rows
    n_bands = truth.band_plan.n_bands
    bins = set(int(x) for x in receiver.dwell_bins)
    last_t = -1
    for row in run.observations.rows:
        assert 0 <= int(row.step)
        if row.tuned_band is not None:
            assert 0 <= int(row.tuned_band) < n_bands
        if row.measured_snr_db is not None:
            assert np.isfinite(row.measured_snr_db)
        assert int(row.step) >= last_t
        last_t = int(row.step)
    for row in run.decisions.rows:
        assert 0 <= int(row.target_band) < n_bands
        assert int(row.dwell_steps) in bins
        assert np.isfinite(row.start_step)
        if row.reward is not None:
            assert np.isfinite(row.reward)
        if row.p_hit is not None:
            assert np.isfinite(row.p_hit)
    evaluation = evaluate_strategy(
        truth, run.observations, run.decisions, receiver_config=receiver
    )
    assert evaluation.report.metrics
    air = evaluation.report.metrics["average_intercept_rate"]
    if air.value is not None:
        assert np.isfinite(air.value)


def test_contextual_thompson_is_not_an_alias_of_other_policies() -> None:
    cts = make_policy(
        "contextual-thompson", dwell_steps=8, n_bands=4, dwell_bins=(8,), schedule_seed=0
    )
    assert type(cts).__name__ == "ContextualThompsonSchedule"
    assert type(make_policy("random", dwell_steps=8, schedule_seed=0)).__name__ != type(cts).__name__
    assert type(make_policy("reactive", dwell_steps=8, schedule_seed=0)).__name__ != type(cts).__name__
    assert type(make_policy("periodic-intercept", dwell_steps=8)).__name__ != type(cts).__name__


def test_periodic_intercept_not_alias_of_sequential() -> None:
    periodic = PeriodicInterceptSchedule(dwell_steps=8, seed=0)
    seq = make_policy("sequential", dwell_steps=8)
    p_last: int | None = None
    s_last: int | None = None
    last_id = None
    step = 0
    for i in range(4):
        p_view = _view(
            decision_index=i,
            step=step,
            last_target_band=p_last,
            last_hit=False,
            last_decision_id=last_id,
            last_end_step=step if i else None,
        )
        s_view = _view(decision_index=i, step=step, last_target_band=s_last)
        pc = periodic.next_command(p_view)
        sc = seq.next_command(s_view)
        p_last = int(pc.target_band)
        s_last = int(sc.target_band)
        last_id = pc.decision_id
        step += 10
    for j, end in enumerate((40, 50, 60)):
        p_view = _view(
            decision_index=4 + j,
            step=end,
            last_target_band=2,
            last_hit=True,
            last_decision_id=f"hit{j}",
            last_end_step=end,
            settled_band=2,
        )
        s_view = _view(decision_index=4 + j, step=end, last_target_band=s_last)
        pc = periodic.next_command(p_view)
        sc = seq.next_command(s_view)
        last_id = pc.decision_id
        p_last = int(pc.target_band)
        s_last = int(sc.target_band)
    p_view = _view(
        decision_index=10,
        step=62,
        last_target_band=p_last,
        last_hit=True,
        last_decision_id=last_id,
        last_end_step=60,
        settled_band=2,
    )
    s_view = _view(decision_index=10, step=62, last_target_band=s_last)
    pc = periodic.next_command(p_view)
    sc = seq.next_command(s_view)
    assert pc.target_band == 2
    assert pc.dwell_steps == 8
    assert (int(sc.target_band), int(sc.dwell_steps)) != (int(pc.target_band), int(pc.dwell_steps))


def test_cli_parse_rejects_unknown_and_accepts_public() -> None:
    for name in PUBLIC_STRATEGIES:
        assert parse_cli_strategy(name) == name
    assert parse_cli_strategy("best-available", allow_best_available=True) == "best-available"
    with pytest.raises(SmartScanError, match="Public strategies"):
        parse_cli_strategy("nope")
    with pytest.raises(SmartScanError, match="Public strategies"):
        parse_cli_strategy("best-available", allow_best_available=False)


def test_stage2_make_schedule_is_documented_subset() -> None:
    assert make_schedule("sequential", dwell_steps=4)
    with pytest.raises(SmartScanError, match="Unknown strategy"):
        make_schedule("periodic-intercept", dwell_steps=4)
    with pytest.raises(SmartScanError, match="make_policy"):
        make_schedule("ppo", dwell_steps=4)
    with pytest.raises(SmartScanError, match="make_policy"):
        make_schedule("reactive", dwell_steps=4)


def test_construct_live_policy_and_lightweight_import() -> None:
    src = inspect.getsource(construct_live_policy)
    assert "streamlit" not in src.lower()
    policy = construct_live_policy(
        "periodic-intercept", dwell_steps=8, schedule_seed=0, n_bands=4, dwell_bins=(2, 8)
    )
    assert isinstance(policy, PeriodicInterceptSchedule)
    with pytest.raises(SmartScanError, match="PPO bundle not found"):
        construct_live_policy("ppo", dwell_steps=8, model_dir=None)
    v4 = Path(__file__).resolve().parents[2] / "artifacts" / "models" / "scheduler_v4"
    if (v4 / "manifest.json").is_file():
        ppo = construct_live_policy(
            "ppo",
            dwell_steps=8,
            n_bands=16,
            dwell_bins=(1, 2, 4, 8, 16),
            model_dir=v4,
            public_priorities=(8, 4, 10),
        )
        assert ppo.include_predictor_obs is True
        assert int(ppo.include_action_history) == 4
        assert ppo.include_neural_predictor_obs is False
        assert ppo.builder.ewma_alpha == pytest.approx(0.3)


def test_oracle_firewall_for_adaptive_strategies() -> None:
    boom = ExplodingOracle()
    builder = FeatureBuilder(n_bands=4, dt_s=0.01, dwell_bins=(2, 8))
    policies = [
        make_policy("reactive", dwell_steps=8, schedule_seed=0),
        make_policy("contextual-thompson", dwell_steps=8, n_bands=4, dwell_bins=(2, 8), schedule_seed=0),
        make_policy("periodic-intercept", dwell_steps=8, schedule_seed=0),
        make_policy(
            "ppo",
            dwell_steps=8,
            n_bands=4,
            dwell_bins=(2, 8),
            ppo_predict=lambda _obs: 0,
            feature_builder=builder,
        ),
    ]
    real = _view(decision_index=0, step=0)
    wrapped = SimpleNamespace(**{item.name: getattr(real, item.name) for item in fields(real)})
    wrapped.occupied = boom
    wrapped.events = boom
    wrapped.true_period_s = boom
    wrapped.ground_truth = boom
    wrapped.hopping_schedule = boom
    for policy in policies:
        cmd = policy.next_command(wrapped)  # type: ignore[arg-type]
        assert 0 <= int(cmd.target_band) < 4
        assert int(cmd.dwell_steps) in {2, 8}
    periodic_src = inspect.getsource(PeriodicInterceptSchedule.next_command) + inspect.getsource(
        PeriodicInterceptSchedule._ingest
    )
    assert "occupied" not in periodic_src
    assert "true_period" not in periodic_src
    assert ".events" not in periodic_src
    with pytest.raises(RuntimeError, match="oracle leak"):
        _ = boom.occupied


def test_dashboard_dropdown_matches_registry() -> None:
    from smartscan.dashboard.pages import VIEWS
    from smartscan.dashboard.services import DEMO_STRATEGIES as demo

    assert tuple(demo) == PUBLIC_STRATEGIES
    assert "Configure & Run" in VIEWS
    assert "Scan Replay" in VIEWS


def test_all_public_strategies_dashboard_run_replay_metrics(tmp_path: Path) -> None:
    from smartscan.dashboard.services import (
        build_replay_frame,
        comparison_table,
        load_dashboard_config,
    )
    from smartscan.dashboard.ui.components import display_metric

    cfg = load_dashboard_config()
    cfg.demo_duration_s = 0.04
    cfg.demo_dt_s = 0.001
    cfg.mc_rollouts = 2
    cfg.horizon_steps = 16
    cfg.max_duration_s = 2.0
    cfg.demo_dir = str(tmp_path / "demo")
    results = []
    for name in PUBLIC_STRATEGIES:
        item = run_experiment(
            cfg,
            scenario_id="agile_threat",
            seed=5,
            strategy=name,
            duration_s=0.04,
            evaluation_overlay=False,
        )
        assert item.strategy == name
        if name != "ppo":
            assert item.model_alias is None
        else:
            assert item.model_alias == "candidate"
        frame = build_replay_frame(item, evaluation_overlay=False)
        assert frame.occupied is None
        assert frame.times_s
        assert len(frame.tuned_band) == len(frame.times_s)
        expl = explain_decision(item, 0)
        assert expl.strategy_id == name
        assert expl.strategy_rule
        assert expl.strategy_rule != "Not available"
        if expl.p_active is None:
            assert expl.p_active_unavailable
        if expl.period_s is None:
            assert display_metric(expl.period_s) == "Not available"
        results.append(item)
    table = comparison_table(results)
    assert set(table["strategies"]) == set(PUBLIC_STRATEGIES)
    keys = {row["key"] for row in table["rows"]}
    assert "average_intercept_rate" in keys
    assert "event_interception_ratio" in keys
    assert "pd" in keys
    assert "pfa" in keys


def test_seven_strategy_persist_reload_replay_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from smartscan.dashboard.services import build_replay_frame, load_dashboard_config
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository

    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv(
        "MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    )
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    cfg = load_dashboard_config()
    cfg.demo_duration_s = 0.04
    cfg.demo_dt_s = 0.001
    cfg.mc_rollouts = 2
    cfg.horizon_steps = 16
    cfg.max_duration_s = 2.0
    cfg.demo_dir = str(tmp_path / "demo")
    matrix: dict[str, dict[str, str]] = {}
    for name in PUBLIC_STRATEGIES:
        item = run_experiment(
            cfg,
            scenario_id="agile_threat",
            seed=11,
            strategy=name,
            duration_s=0.04,
            persist=True,
            track=False,
        )
        factory = "PASS"
        run_ok = "PASS" if item.run.decisions.rows and item.run.observations.rows else "FAIL"
        metrics_ok = "PASS" if item.evaluation.report.metrics else "FAIL"
        assert item.domain_run_id is not None
        assert item.protocol_id == "live_session"
        settings = StorageSettings.from_env()
        repo = build_repository(settings, track=False, upgrade=True)
        stored = repo.get_run(item.domain_run_id)
        persist_ok = (
            "PASS"
            if stored.strategy == name
            and stored.observations is not None
            and stored.decisions is not None
            and stored.evaluation is not None
            else "FAIL"
        )
        frame = build_replay_frame(item, evaluation_overlay=False)
        replay_ok = "PASS" if frame.times_s and len(frame.tuned_band) == len(frame.times_s) else "FAIL"
        expl = explain_decision(item, 0)
        assert expl.strategy_id == name
        matrix[name] = {
            "factory": factory,
            "run": run_ok,
            "metrics": metrics_ok,
            "persist": persist_ok,
            "replay": replay_ok,
        }
    for name in PUBLIC_STRATEGIES:
        assert matrix[name] == {
            "factory": "PASS",
            "run": "PASS",
            "metrics": "PASS",
            "persist": "PASS",
            "replay": "PASS",
        }


def test_periodic_intercept_persist_roundtrip(
    domain_repo: object, receiver_config: object
) -> None:
    from tests.conftest import TINY_SIM

    from smartscan.storage.pipeline import persist_baseline_run
    from smartscan.storage.repositories import RunFilters, RunRepository

    assert isinstance(domain_repo, RunRepository)
    domain_run_id = persist_baseline_run(
        simulate_config=TINY_SIM,
        receiver_config=receiver_config,  # type: ignore[arg-type]
        strategy="periodic-intercept",
        repo=domain_repo,
        track=False,
    )
    stored = domain_repo.get_run(domain_run_id)
    assert stored.strategy == "periodic-intercept"
    listed = domain_repo.list_runs(RunFilters(strategy="periodic-intercept"))
    assert listed
    assert listed[0].strategy == "periodic-intercept"
    alias_id = persist_baseline_run(
        simulate_config={**TINY_SIM, "seed": 7},
        receiver_config=receiver_config,  # type: ignore[arg-type]
        strategy="periodic",
        repo=domain_repo,
        track=False,
    )
    assert domain_repo.get_run(alias_id).strategy == "periodic-intercept"
