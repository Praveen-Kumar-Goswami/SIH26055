"""Dashboard services: Stage 1–5 API orchestration only. No detector/metric formulas."""

from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from smartscan.config import (
    DashboardConfig,
    SimulateConfig,
    TrainConfig,
    load_yaml,
    project_root,
    resolve_under_root,
)
from smartscan.metrics.engine import evaluate_strategy, save_metrics, save_metrics_csv
from smartscan.metrics.schemas import FROZEN_METRIC_KEYS, FROZEN_METRIC_NAMES, METRIC_SCHEMA_VERSION
from smartscan.metrics.statistics import compare_runs, paired_compare
from smartscan.ml.policies import construct_live_policy
from smartscan.ml.strategy_registry import (
    LIVE_STRATEGIES,
    PUBLIC_STRATEGIES,
    canonicalize_run_strategy,
    canonicalize_strategy_id,
    strategy_kind,
    strategy_kind_label,
    strategy_rule,
)
from smartscan.receiver.detector import load_receiver_config
from smartscan.receiver.logs import ReceiverRun, load_receiver_run, save_receiver_run
from smartscan.rf.environment import simulate
from smartscan.rf.io import load_ground_truth, save_ground_truth
from smartscan.storage.db import StorageSettings, current_git_sha, sqlite_path_from_url
from smartscan.types import GroundTruth, MetricValue, ReceiverConfig, SmartScanError

ALLOWED_PATH_ROOTS = ("artifacts", "data", "configs")
DEMO_STRATEGIES: tuple[str, ...] = PUBLIC_STRATEGIES
ORACLE_LABEL = "oracle-ceiling (unattainable)"
OVERLAY_NOTICE = "Evaluation overlay — not available to policy"

COMPARE_KEYS: tuple[str, ...] = FROZEN_METRIC_KEYS + (
    "event_interception_ratio",
    "successful_event_delay_median_s",
    "all_event_penalized_delay_s",
    "missed_event_count",
    "wasted_dwell_fraction",
    "tuning_fraction",
)

HIGHER_IS_BETTER: dict[str, bool] = {
    "pd": True,
    "pfa": False,
    "sensitivity": False,
    "average_intercept_rate": True,
    "average_reward": True,
    "correct_predictions": True,
    "average_intercept_time_error": False,
    "event_interception_ratio": True,
    "successful_event_delay_median_s": False,
    "all_event_penalized_delay_s": False,
    "missed_event_count": False,
    "wasted_dwell_fraction": False,
    "tuning_fraction": False,
}

DISPLAY_NAMES: dict[str, str] = {
    **FROZEN_METRIC_NAMES,
    "event_interception_ratio": "Event interception ratio",
    "successful_event_delay_median_s": "Successful-event median delay",
    "all_event_penalized_delay_s": "All-event penalized delay",
    "missed_event_count": "Missed-event count",
    "wasted_dwell_fraction": "Wasted-dwell fraction",
    "tuning_fraction": "Tuning fraction",
}


def load_dashboard_config(path: str | Path | None = None) -> DashboardConfig:
    dest = Path(path) if path is not None else project_root() / "configs" / "dashboard.yaml"
    if dest.is_file():
        return DashboardConfig.model_validate(load_yaml(dest))
    return DashboardConfig()


def safe_user_path(path: str | Path, *, root: Path | None = None) -> Path:
    """Resolve a user path under artifacts/, data/, or configs/. Reject secrets files."""

    base = root or project_root()
    text = str(path)
    lowered = text.replace("\\", "/").lower()
    if any(token in lowered for token in (".env", "hf_token", "huggingface", "secret")):
        raise SmartScanError("Refusing to open a secrets or token path in the dashboard.")
    resolved = resolve_under_root(path, root=base)
    try:
        relative = resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise SmartScanError(f"Path {path} is outside the project root.") from exc
    if not relative.parts or relative.parts[0] not in ALLOWED_PATH_ROOTS:
        raise SmartScanError(
            f"File selection is limited to {', '.join(ALLOWED_PATH_ROOTS)} under the project root."
        )
    return resolved


def validate_run_request(
    cfg: DashboardConfig,
    *,
    duration_s: float,
    n_bands: int,
    strategy: str,
) -> list[str]:
    errors: list[str] = []
    if duration_s > float(cfg.max_duration_s) + 1e-12:
        errors.append(
            f"Live duration {duration_s}s exceeds the demo cap {cfg.max_duration_s}s. "
            "Reduce duration or open a recorded replay."
        )
    if n_bands > int(cfg.max_n_bands):
        errors.append(
            f"Band count {n_bands} exceeds the demo cap {cfg.max_n_bands}. Use a recorded replay."
        )
    try:
        name = canonicalize_run_strategy(strategy, allow_oracle=True)
    except SmartScanError as exc:
        errors.append(str(exc))
        return errors
    allowed = set(DEMO_STRATEGIES) | {"oracle-ceiling"}
    if name not in allowed:
        errors.append(f"Unknown strategy {strategy!r}. Choose one of: {', '.join(sorted(allowed))}.")
    return errors


@dataclass
class ExperimentResult:
    strategy: str
    seed: int
    receiver_seed: int
    truth: GroundTruth
    run: ReceiverRun
    evaluation: Any
    domain_run_id: UUID | None = None
    model_alias: str | None = None
    error: str | None = None
    protocol_id: str = "live_session"
    duration_s: float | None = None
    dt_s: float | None = None
    metric_source: str = "LIVE RUN"
    active_model_version: str | None = None
    bundle_fingerprint: str | None = None


@dataclass
class ReplayFrame:
    times_s: list[float]
    tuned_band: list[int | None]
    commanded_band: list[int | None]
    receiver_state: list[str]
    snr_db: list[float | None]
    detections: list[bool]
    hit_times_s: list[float]
    hit_bands: list[int]
    miss_times_s: list[float]
    miss_bands: list[int]
    occupied: list[list[int]] | None
    overlay_notice: str | None
    dt_s: float
    n_bands: int


@dataclass
class DecisionExplanation:
    decision_id: str
    index: int
    target_band: int
    dwell_steps: int
    hit: bool
    p_hit: float | None
    p_active: float | None
    p_active_unavailable: str | None
    time_to_next_completed_intercept_s: float | None
    uncertainty: float | None
    novelty: float | None
    assessed_threat: float | None
    priority: float | None
    reward: float | None
    reward_hit: float | None
    reward_priority: float | None
    cost_tune_s: float | None
    cost_time_s: float | None
    cost_repeat: float | None
    cost_false_like: float | None
    horizon_ratio: float | None
    horizon_ci_low: float | None
    horizon_ci_high: float | None
    period_s: float | None
    phase_to_next: float | None
    agility_score: float | None
    recorded_at_step: int
    observable_agility_by_band: tuple[float, ...] = ()
    strategy_id: str = ""
    strategy_kind: str = ""
    strategy_kind_label: str = ""
    strategy_rule: str = ""
    periodicity_confidence: float | None = None


def _receiver(cfg: DashboardConfig) -> ReceiverConfig:
    payload = dict(load_yaml(project_root() / cfg.receiver_config))
    payload["noise_power_w"] = float(cfg.noise_power_w)
    return load_receiver_config(payload)


def _train_cfg(dash: DashboardConfig, duration_s: float, dt_s: float) -> TrainConfig:
    yaml_path = project_root() / dash.train_config
    if yaml_path.is_file():
        train = TrainConfig.model_validate(load_yaml(yaml_path))
    else:
        train = TrainConfig()
    train.duration_s = float(duration_s)
    train.dt_s = float(dt_s)
    train.mc_rollouts = int(dash.mc_rollouts)
    train.horizon_steps = int(dash.horizon_steps)
    train.public_priorities = list(dash.public_priorities)
    train.noise_power_w = float(dash.noise_power_w)
    train.band_plan_id = dash.band_plan_id
    return train


def model_bundle_dir(dash: DashboardConfig | None = None) -> Path:
    """Resolved *active* PPO bundle directory. Honors SMARTSCAN_MODEL_DIR."""

    from smartscan.dashboard.identity import active_model_bundle_dir

    return active_model_bundle_dir(dash)


def _model_dir(dash: DashboardConfig) -> Path:
    return model_bundle_dir(dash)


def _try_load_bundle(model_dir: Path) -> Any | None:
    if not model_dir.is_dir():
        return None
    from smartscan.ml.bundle import load_bundle

    return load_bundle(model_dir)


def _make_schedule(
    strategy: str,
    *,
    dash: DashboardConfig,
    receiver: ReceiverConfig,
    n_bands: int,
    seed: int,
    dt_s: float,
    occupied: Any | None,
    allow_oracle: bool,
) -> Any:
    name = canonicalize_run_strategy(strategy, allow_oracle=True)
    model_dir = None
    if name == "ppo":
        dest = _model_dir(dash)
        if _try_load_bundle(dest) is None:
            raise SmartScanError(
                f"PPO bundle not found at {dash.model_dir}. Select a baseline or run train-scheduler."
            )
        model_dir = dest
    return construct_live_policy(
        name,
        dwell_steps=int(dash.dwell_steps),
        schedule_seed=int(seed),
        band_order=tuple(dash.public_priorities),
        n_bands=n_bands,
        dwell_bins=tuple(int(x) for x in receiver.dwell_bins),
        dt_s=float(dt_s),
        tune_latency_steps=int(receiver.tune_latency_steps),
        public_priorities=tuple(int(b) for b in dash.public_priorities),
        model_dir=model_dir,
        occupied=occupied,
        allow_oracle=allow_oracle,
    )


def run_experiment(
    dash: DashboardConfig,
    *,
    scenario_id: str,
    seed: int,
    strategy: str,
    duration_s: float | None = None,
    dt_s: float | None = None,
    receiver_seed: int | None = None,
    persist: bool = False,
    track: bool = True,
    evaluation_overlay: bool = False,
    band_plan_id: str | None = None,
) -> ExperimentResult:
    """Simulate, scan, and evaluate. Overlay never affects actions or persistence."""

    duration = float(duration_s if duration_s is not None else dash.demo_duration_s)
    dt = float(dt_s if dt_s is not None else dash.demo_dt_s)
    rseed = int(receiver_seed if receiver_seed is not None else seed)
    plan_id = band_plan_id if band_plan_id is not None else dash.band_plan_id
    sim = SimulateConfig(
        seed=int(seed),
        dt_s=dt,
        duration_s=duration,
        band_plan_id=plan_id,
        scenario_id=scenario_id,
    )
    truth = simulate(sim)
    problems = validate_run_request(
        dash, duration_s=duration, n_bands=truth.band_plan.n_bands, strategy=strategy
    )
    if problems:
        raise SmartScanError(problems[0])
    name = canonicalize_run_strategy(strategy, allow_oracle=True)
    receiver = _receiver(dash)
    allow_oracle = name == "oracle-ceiling"
    occupied = truth.occupied if allow_oracle else None
    schedule = _make_schedule(
        name,
        dash=dash,
        receiver=receiver,
        n_bands=truth.band_plan.n_bands,
        seed=int(seed),
        dt_s=dt,
        occupied=occupied,
        allow_oracle=allow_oracle,
    )
    from smartscan.ml.runner import run_policy_episode

    train = _train_cfg(dash, duration, dt)
    train.band_plan_id = plan_id
    predictor = None
    if name == "ppo":
        bundle = _try_load_bundle(_model_dir(dash))
        if bundle is not None:
            cfg = bundle.config if isinstance(bundle.config, dict) else {}
            if cfg:
                train = train.model_copy(
                    update={
                        "include_predictor_obs": bool(cfg.get("include_predictor_obs", False)),
                        "include_action_history": int(cfg.get("include_action_history") or 0),
                        "include_neural_predictor_obs": bool(
                            cfg.get("include_neural_predictor_obs", False)
                        ),
                        "action_layout": str(cfg.get("action_layout") or train.action_layout),
                    }
                )
            if bundle.predictor is not None:
                from smartscan.ml.predictor import BuilderBackedHazardPredictor

                predictor = BuilderBackedHazardPredictor(bundle.predictor)
    run = run_policy_episode(
        truth,
        schedule,
        receiver,
        cfg=train,
        receiver_seed=rseed,
        predictor=predictor,
        record_horizon=True,
    )
    evaluation = evaluate_strategy(
        truth, run.observations, run.decisions, receiver_config=receiver
    )
    domain_id = None
    if persist:
        domain_id = _persist(
            sim,
            receiver,
            name,
            rseed,
            int(seed),
            truth,
            run,
            evaluation,
            track=track,
            duration_s=duration,
            strategy_is_ppo=name == "ppo",
        )
    alias = "candidate" if name == "ppo" else None
    del evaluation_overlay
    from smartscan.dashboard.identity import active_model_status
    from smartscan.experiment_protocol import PROTOCOL_LIVE_SESSION, SOURCE_LIVE_RUN

    active = active_model_status(dash)
    return ExperimentResult(
        strategy=name,
        seed=int(seed),
        receiver_seed=rseed,
        truth=truth,
        run=run,
        evaluation=evaluation,
        domain_run_id=domain_id,
        model_alias=alias,
        protocol_id=PROTOCOL_LIVE_SESSION,
        duration_s=duration,
        dt_s=dt,
        metric_source=SOURCE_LIVE_RUN,
        active_model_version=str(active.get("generation") or "v4"),
        bundle_fingerprint=active.get("content_fingerprint") if name == "ppo" else None,
    )


def _persist(
    sim: SimulateConfig,
    receiver: ReceiverConfig,
    strategy: str,
    receiver_seed: int,
    schedule_seed: int,
    truth: GroundTruth,
    run: ReceiverRun,
    evaluation: Any,
    track: bool = True,
    *,
    duration_s: float | None = None,
    strategy_is_ppo: bool = False,
) -> UUID:
    from smartscan.dashboard.identity import active_model_status
    from smartscan.experiment_protocol import PROTOCOL_LIVE_SESSION
    from smartscan.storage.pipeline import build_repository

    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=track, upgrade=True)
    scenario_id = repo.create_scenario(truth, truth.provenance)
    seeds = {
        "scenario": int(sim.seed),
        "receiver": int(receiver_seed),
        "schedule": int(schedule_seed),
    }
    active = active_model_status()
    domain_run_id = repo.start_run(
        scenario_id,
        receiver,
        strategy,
        seeds,
        protocol_id=PROTOCOL_LIVE_SESSION,
        model_version=str(active.get("generation") or "v4") if strategy_is_ppo else None,
        bundle_fingerprint=active.get("content_fingerprint") if strategy_is_ppo else None,
        duration_s=float(duration_s if duration_s is not None else sim.duration_s),
    )
    repo.attach_logs(domain_run_id, run.observations, run.decisions)
    repo.save_metrics(domain_run_id, evaluation)
    repo.complete_run(domain_run_id, track=track)
    return domain_run_id


def action_signature(result: ExperimentResult) -> list[tuple[str, int, int, float | None]]:
    return [
        (row.decision_id, int(row.target_band), int(row.dwell_steps), row.reward)
        for row in result.run.decisions.rows
    ]


def build_replay_frame(result: ExperimentResult, *, evaluation_overlay: bool) -> ReplayFrame:
    truth = result.truth
    obs = result.run.observations.rows
    times = [float(row.step) * float(truth.dt_s) for row in obs]
    occupied: list[list[int]] | None = None
    notice: str | None = None
    if evaluation_overlay:
        occupied = [[int(v) for v in truth.occupied[i]] for i in range(truth.n_steps)]
        notice = OVERLAY_NOTICE
    hits_t: list[float] = []
    hits_b: list[int] = []
    miss_t: list[float] = []
    miss_b: list[int] = []
    for row in result.run.decisions.rows:
        t = float(row.end_step) * float(truth.dt_s)
        if row.hit:
            hits_t.append(t)
            hits_b.append(int(row.target_band))
        else:
            miss_t.append(t)
            miss_b.append(int(row.target_band))
    return ReplayFrame(
        times_s=times,
        tuned_band=[row.tuned_band for row in obs],
        commanded_band=[row.commanded_band for row in obs],
        receiver_state=[row.receiver_state for row in obs],
        snr_db=[row.measured_snr_db for row in obs],
        detections=[bool(row.detection) for row in obs],
        hit_times_s=hits_t,
        hit_bands=hits_b,
        miss_times_s=miss_t,
        miss_bands=miss_b,
        occupied=occupied,
        overlay_notice=notice,
        dt_s=float(truth.dt_s),
        n_bands=int(truth.band_plan.n_bands),
    )


def explain_decision(result: ExperimentResult, index: int) -> DecisionExplanation:
    rows = result.run.decisions.rows
    if not rows:
        raise SmartScanError("No completed decisions to explain.")
    idx = max(0, min(int(index), len(rows) - 1))
    row = rows[idx]
    from smartscan.ml.features import FeatureBuilder
    from smartscan.ml.observable import transition_from_decision

    n_bands = result.truth.band_plan.n_bands
    dash = load_dashboard_config()
    receiver = _receiver(dash)
    builder = FeatureBuilder(
        n_bands=n_bands,
        dt_s=result.truth.dt_s,
        dwell_bins=tuple(int(x) for x in receiver.dwell_bins),
        public_priorities={int(b): 2.0 for b in dash.public_priorities},
    )
    n_steps = result.truth.n_steps
    last_target = None
    for prev in rows[:idx]:
        tr = transition_from_decision(
            prev,
            n_steps=n_steps,
            n_bands=n_bands,
            dt_s=result.truth.dt_s,
            settled_band_before=last_target,
            last_target_band=last_target,
        )
        builder.observe(tr)
        last_target = tr.target_band
    period = None
    phase = None
    agility = None
    conf: float | None = None
    if 0 <= int(row.target_band) < n_bands:
        now_s = float(row.start_step) * float(result.truth.dt_s)
        period_v, phase_v, conf_v = builder.periodicity.estimate(int(row.target_band), now_s)
        period = float(period_v) if period_v else None
        phase = float(phase_v) if phase_v else None
        conf = float(conf_v) if conf_v else None
        agility = float(builder.agility.next_scores()[int(row.target_band)])
    p_active_reason = None if row.p_active is not None else "p_active unavailable on this decision"
    dec = result.run.decisions
    try:
        sid = canonicalize_strategy_id(result.strategy)
        kind = strategy_kind(sid)
        kind_label = strategy_kind_label(sid)
        rule = strategy_rule(sid)
    except SmartScanError:
        sid = str(result.strategy)
        kind = ""
        kind_label = "Not available"
        rule = "Not available"
    return DecisionExplanation(
        decision_id=row.decision_id,
        index=idx,
        target_band=int(row.target_band),
        dwell_steps=int(row.dwell_steps),
        hit=bool(row.hit),
        p_hit=row.p_hit,
        p_active=row.p_active,
        p_active_unavailable=p_active_reason,
        time_to_next_completed_intercept_s=row.time_to_next_completed_intercept_s,
        uncertainty=row.uncertainty,
        novelty=row.novelty,
        assessed_threat=row.assessed_threat,
        priority=row.priority,
        reward=row.reward,
        reward_hit=row.reward_hit,
        reward_priority=row.reward_priority,
        cost_tune_s=row.cost_tune_s,
        cost_time_s=row.cost_time_s,
        cost_repeat=row.cost_repeat,
        cost_false_like=row.cost_false_like,
        horizon_ratio=dec.predicted_interception_ratio,
        horizon_ci_low=dec.predicted_ratio_ci_low,
        horizon_ci_high=dec.predicted_ratio_ci_high,
        period_s=period,
        phase_to_next=phase,
        agility_score=agility,
        recorded_at_step=int(row.start_step),
        observable_agility_by_band=tuple(float(x) for x in builder.agility.next_scores()),
        strategy_id=sid,
        strategy_kind=kind,
        strategy_kind_label=kind_label,
        strategy_rule=rule,
        periodicity_confidence=conf,
    )


def metric_cell(report: Any, key: str) -> dict[str, Any]:
    item = report.metrics.get(key) if report is not None else None
    if not isinstance(item, MetricValue):
        return {
            "key": key,
            "name": DISPLAY_NAMES.get(key, key),
            "value": None,
            "available": False,
            "unavailable_reason": "metric_absent",
            "numerator": None,
            "denominator": None,
            "unit": "",
            "higher_is_better": HIGHER_IS_BETTER.get(key),
            "display": "Not available",
        }
    if not item.available or item.value is None:
        reason = item.unavailable_reason or "unavailable"
        return {
            "key": key,
            "name": DISPLAY_NAMES.get(key, item.name),
            "value": None,
            "available": False,
            "unavailable_reason": reason,
            "numerator": item.numerator,
            "denominator": item.denominator,
            "unit": item.unit,
            "higher_is_better": HIGHER_IS_BETTER.get(key),
            "display": f"Not available ({reason})",
        }
    return {
        "key": key,
        "name": DISPLAY_NAMES.get(key, item.name),
        "value": float(item.value),
        "available": True,
        "unavailable_reason": None,
        "numerator": item.numerator,
        "denominator": item.denominator,
        "unit": item.unit,
        "higher_is_better": HIGHER_IS_BETTER.get(key),
        "display": f"{item.value:.6g}",
    }


def comparison_table(results: list[ExperimentResult], *, include_oracle: bool = False) -> dict[str, Any]:
    shown = [item for item in results if include_oracle or item.strategy != "oracle-ceiling"]
    oracle = [item for item in results if item.strategy == "oracle-ceiling"]
    from smartscan.experiment_protocol import (
        CROSS_PROTOCOL_MESSAGE,
        PROTOCOL_LIVE_SESSION,
        SOURCE_LIVE_RUN,
        require_same_protocol_id,
    )

    rows: list[dict[str, Any]] = []
    for key in COMPARE_KEYS:
        rows.append(
            {
                "key": key,
                "name": DISPLAY_NAMES.get(key, key),
                "higher_is_better": HIGHER_IS_BETTER.get(key),
                "direction": (
                    "higher-is-better"
                    if HIGHER_IS_BETTER.get(key) is True
                    else "lower-is-better"
                    if HIGHER_IS_BETTER.get(key) is False
                    else "informational"
                ),
                "cells": {item.strategy: metric_cell(item.evaluation.report, key) for item in shown},
            }
        )
    paired: dict[str, Any] = {}
    cross_protocol = False
    protocol_ids = {
        str(getattr(item, "protocol_id", None) or PROTOCOL_LIVE_SESSION) for item in shown
    }
    durations = {round(float(getattr(item, "duration_s", 0.0) or 0.0), 9) for item in shown}
    dts = {round(float(getattr(item, "dt_s", 0.0) or 0.0), 12) for item in shown}
    comparable = len(protocol_ids) <= 1 and len(durations) <= 1 and len(dts) <= 1
    ppo = next((item for item in shown if item.strategy == "ppo"), None)
    seq = next((item for item in shown if item.strategy == "sequential"), None)
    if ppo is not None and seq is not None:
        if not comparable:
            cross_protocol = True
            for key in (
                "average_intercept_rate",
                "event_interception_ratio",
                "successful_event_delay_median_s",
            ):
                paired[key] = {"unavailable_reason": CROSS_PROTOCOL_MESSAGE}
        else:
            try:
                require_same_protocol_id(
                    str(getattr(ppo, "protocol_id", None) or PROTOCOL_LIVE_SESSION),
                    str(getattr(seq, "protocol_id", None) or PROTOCOL_LIVE_SESSION),
                )
                for key in (
                    "average_intercept_rate",
                    "event_interception_ratio",
                    "successful_event_delay_median_s",
                ):
                    try:
                        paired[key] = paired_compare(
                            [ppo.evaluation.report],
                            [seq.evaluation.report],
                            metric_key=key,
                            seed=0,
                        )
                    except SmartScanError:
                        paired[key] = {"unavailable_reason": "cannot_pair"}
            except SmartScanError as exc:
                cross_protocol = True
                for key in (
                    "average_intercept_rate",
                    "event_interception_ratio",
                    "successful_event_delay_median_s",
                ):
                    paired[key] = {"unavailable_reason": str(exc)}
    summaries = {}
    if shown and comparable:
        for key in ("average_intercept_rate", "event_interception_ratio"):
            summaries[key] = compare_runs(
                [item.evaluation.report for item in shown], metric_key=key, seed=0
            )
    return {
        "schema_version": METRIC_SCHEMA_VERSION,
        "n_seeds": 1,
        "strategies": [item.strategy for item in shown],
        "rows": rows,
        "paired_vs_sequential": paired,
        "summaries": summaries,
        "oracle_separate": [
            {
                "strategy": ORACLE_LABEL,
                "label": "Evaluator-only upper reference",
                "air": metric_cell(item.evaluation.report, "average_intercept_rate"),
            }
            for item in oracle
        ],
        "highlight_win": False,
        "performance_gate_passed": False,
        "failed_criteria": [],
        "metric_source": SOURCE_LIVE_RUN,
        "protocol_id": next(iter(protocol_ids), PROTOCOL_LIVE_SESSION),
        "cross_protocol": cross_protocol,
        "cross_protocol_message": CROSS_PROTOCOL_MESSAGE if cross_protocol else None,
    }


def load_performance_gate(path: str | Path | None = None) -> dict[str, Any]:
    dash = load_dashboard_config()
    dest = Path(path) if path is not None else project_root() / dash.gate_path
    if not dest.is_file():
        return {
            "found": False,
            "performance_gate_passed": False,
            "reasons": ["held-out gate file is missing"],
            "alias": "candidate",
            "highlight_win": False,
            "n_rows": None,
        }
    payload = json.loads(dest.read_text(encoding="utf-8"))
    passed = bool(payload.get("performance_gate_passed"))
    return {
        "found": True,
        "performance_gate_passed": passed,
        "reasons": list(payload.get("reasons") or []),
        "family_pass": payload.get("family_pass") or {},
        "comparisons": payload.get("comparisons") or {},
        "manifest_fingerprint": payload.get("manifest_fingerprint"),
        "alias": "champion" if passed else "candidate",
        "highlight_win": passed,
        "path": str(dest),
        "n_rows": payload.get("n_rows"),
    }


def load_recorded_air_evals() -> dict[str, Any]:
    """Recorded v2/v3/v4 AIR as separate protocol objects. Never a mixed ranking."""

    from smartscan.experiment_protocol import (
        PROTOCOL_V2_FROZEN_GATE,
        PROTOCOL_V3_RESEARCH,
        PROTOCOL_V4_RESEARCH,
        load_protocol_air_means,
    )

    columns = []
    for protocol_id in (
        PROTOCOL_V2_FROZEN_GATE,
        PROTOCOL_V3_RESEARCH,
        PROTOCOL_V4_RESEARCH,
    ):
        loaded = load_protocol_air_means(protocol_id)
        proto = loaded["protocol"]
        columns.append(
            {
                "id": proto.protocol_id,
                "title": proto.display_name,
                "detail": (
                    f"{proto.as_banner()['bundle']} · seeds {proto.as_banner()['seeds']} · "
                    f"{proto.as_banner()['episode']} · {proto.purpose}"
                ),
                "air": loaded["air"],
                "oracle_air": loaded["oracle_air"],
                "available": loaded["available"],
                "gate_passed": loaded["gate_passed"],
                "n_rows": loaded["n_rows"],
                "path": loaded["path"],
                "protocol": proto,
                "metric_source": proto.metric_source,
            }
        )
    return {"columns": columns, "strategies": list(PUBLIC_STRATEGIES)}


def recorded_air_table(evals: dict[str, Any], *, protocol_id: str) -> dict[str, list[str]]:
    """One protocol only. Refuses to emit a cross-protocol ranking table."""

    from smartscan.experiment_protocol import protocol_air_table

    del evals
    return protocol_air_table(protocol_id)


def _mlflow_ui_status(host: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, int(port)), timeout=0.2):
            return {"reachable": True, "detail": f"{host}:{port} accepting connections"}
    except OSError:
        return {
            "reachable": False,
            "detail": (
                f"MLflow UI is not reachable at {host}:{port}. "
                "Start it with python -m smartscan.cli mlflow serve. "
                "The local tracking DB can still be inspected offline."
            ),
        }


def lineage_panel(dash: DashboardConfig | None = None) -> dict[str, Any]:
    cfg = dash or load_dashboard_config()
    root = project_root()
    from smartscan.dashboard.identity import dashboard_identity
    from smartscan.experiment_protocol import registered_protocols
    from smartscan.ml.strategy_registry import STRATEGY_REGISTRY, TOTAL_PUBLIC_STRATEGIES

    identity = dashboard_identity(cfg)
    active = identity["active_model_bundle"]
    gate_ev = identity["gate_evidence_bundle"]
    settings = StorageSettings.from_env()
    mlflow_path = sqlite_path_from_url(settings.mlflow_tracking_uri)
    gate = load_performance_gate(root / cfg.gate_path)
    catalog = [
        {
            "id": name,
            "kind": STRATEGY_REGISTRY[name]["kind"],
            "kind_label": strategy_kind_label(name),
            "requires_bundle": bool(STRATEGY_REGISTRY[name]["requires_bundle"]),
            "held_out_baseline": bool(STRATEGY_REGISTRY[name]["held_out_baseline"]),
        }
        for name in PUBLIC_STRATEGIES
    ]
    return {
        "git_sha": current_git_sha(root),
        "active_model_bundle": active,
        "gate_evidence_bundle": gate_ev,
        "bundle": {
            "present": active.get("ok"),
            "path": active.get("path"),
            "ok": active.get("ok"),
            "content_fingerprint": active.get("content_fingerprint"),
            "model_version": active.get("model_version"),
            "registered_name": active.get("registered_name"),
            "role": "active_model_bundle",
            "generation": active.get("generation"),
        },
        "gate": gate,
        "alias": "candidate",
        "champion_set": False,
        "mlflow_db": str(mlflow_path) if mlflow_path is not None else settings.mlflow_tracking_uri,
        "mlflow_db_exists": bool(mlflow_path is not None and mlflow_path.is_file()),
        "mlflow_ui": _mlflow_ui_status(settings.mlflow_host, settings.mlflow_port),
        "mlflow_open_url": f"http://{settings.mlflow_host}:{settings.mlflow_port}",
        "domain_db": str(settings.domain_db_path),
        "domain_db_exists": settings.domain_db_path.is_file(),
        "strategy_catalog": catalog,
        "total_public_strategies": TOTAL_PUBLIC_STRATEGIES,
        "protocols": {pid: proto.as_banner() for pid, proto in registered_protocols().items()},
    }


def doctor_report(dash: DashboardConfig | None = None) -> dict[str, Any]:
    cfg = dash or load_dashboard_config()
    root = project_root()
    checks: list[dict[str, Any]] = []

    def _add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    _add("project_root", (root / "pyproject.toml").is_file(), str(root))
    settings: StorageSettings | None = None
    try:
        from smartscan.storage.db import upgrade_database

        settings = StorageSettings.from_env()
        upgrade_database(settings.domain_db_url)
        _add("db_migrations", True, settings.domain_db_url)
    except Exception as exc:
        _add("db_migrations", False, str(exc))
        settings = None
    lineage = lineage_panel(cfg)
    from smartscan.experiment_protocol import (
        NOT_RECORDED,
        PROTOCOL_V2_FROZEN_GATE,
        PROTOCOL_V3_RESEARCH,
        PROTOCOL_V4_RESEARCH,
        TOTAL_PUBLIC_STRATEGIES,
        artifact_integrity_report,
        assert_distinct_bundle_fingerprints,
        check_run_bundle_linkage,
        inspect_bundle_dir,
        load_protocol_air_means,
        registered_protocols,
    )
    from smartscan.ml.policies import PeriodicInterceptSchedule
    from smartscan.ml.strategy_registry import PUBLIC_STRATEGIES as PUB

    _add(
        "strategy_registry",
        len(PUB) == TOTAL_PUBLIC_STRATEGIES == 7,
        f"Strategies: {len(PUB)}/{TOTAL_PUBLIC_STRATEGIES} OK",
    )
    _add(
        "protocol_registry",
        set(registered_protocols())
        >= {PROTOCOL_V2_FROZEN_GATE, PROTOCOL_V3_RESEARCH, PROTOCOL_V4_RESEARCH},
        "v2_frozen_gate / v3_research / v4_research / live_session",
    )
    _add(
        "periodic_intercept_impl",
        callable(PeriodicInterceptSchedule),
        "Periodic-intercept: implementation OK",
    )
    try:
        import plotly  # noqa: F401
        import streamlit  # noqa: F401

        _add("dashboard_dependencies", True, "streamlit+plotly import OK")
    except ImportError as exc:
        _add("dashboard_dependencies", False, str(exc))
    active = lineage["active_model_bundle"]
    _add(
        "active_ppo_bundle",
        bool(active.get("ok")),
        (
            f"Active PPO: {active.get('generation')} {active.get('alias')} "
            f"fingerprint={active.get('content_fingerprint') or 'missing'}"
        ),
    )
    gate_ev = lineage["gate_evidence_bundle"]
    _add(
        "official_gate",
        bool(gate_ev.get("gate_file_found")),
        (
            f"Official gate: {gate_ev.get('protocol_id')} "
            f"{gate_ev.get('generation')} {gate_ev.get('gate_status')}"
        ),
    )
    _add("mlflow_db", bool(lineage["mlflow_db_exists"]), str(lineage["mlflow_db"]))
    _add("mlflow_ui", bool(lineage["mlflow_ui"]["reachable"]), str(lineage["mlflow_ui"]["detail"]))
    _add("champion_unset", True, "Champion: NONE")
    for pid in (PROTOCOL_V2_FROZEN_GATE, PROTOCOL_V3_RESEARCH, PROTOCOL_V4_RESEARCH):
        loaded = load_protocol_air_means(pid)
        proto = registered_protocols()[pid]
        _add(
            f"protocol_{pid}",
            bool(loaded["available"]),
            (
                f"{proto.display_name} gate_passed={loaded['gate_passed']} "
                f"periodic-intercept={NOT_RECORDED}"
            ),
        )
    infos = [
        inspect_bundle_dir(root / "artifacts/models/scheduler_full"),
        inspect_bundle_dir(root / "artifacts/models/scheduler_v3"),
        inspect_bundle_dir(root / "artifacts/models/scheduler_v4"),
    ]
    try:
        present = [item for item in infos if item.get("ok")]
        if len(present) >= 2:
            assert_distinct_bundle_fingerprints(present)
        _add(
            "bundle_fingerprints_distinct",
            True,
            "v2/v3/v4 fingerprints are distinct when present",
        )
    except SmartScanError as exc:
        _add("bundle_fingerprints_distinct", False, str(exc))
    integrity = artifact_integrity_report(root)
    _add(
        "artifact_integrity",
        bool(integrity["ok"]),
        (
            "missing=" + ",".join(integrity["missing"][:6])
            if integrity["missing"] or integrity["stale"] or integrity["duplicate"]
            else "known bundles and evidence files checksum OK"
        ),
    )
    orphans = list(integrity.get("orphans") or [])
    _add(
        "orphan_artifact_warnings",
        True,
        ("none" if not orphans else "candidates (not deleted): " + ", ".join(orphans[:12])),
    )
    mismatch = None
    if active.get("content_fingerprint") and gate_ev.get("content_fingerprint"):
        if active.get("content_fingerprint") == gate_ev.get("content_fingerprint"):
            mismatch = "active bundle fingerprint equals frozen v2 gate bundle"
    _add("no_cross_version_bundle", mismatch is None, mismatch or "active and gate bundles differ")
    linkage_errors: list[str] = []
    try:
        from smartscan.storage.pipeline import build_repository
        from smartscan.storage.repositories import RunFilters

        if settings is not None:
            repo = build_repository(settings, track=False, upgrade=False)
            for row in repo.list_runs(RunFilters())[:50]:
                err = check_run_bundle_linkage(
                    model_version=row.model_version,
                    bundle_fingerprint=row.bundle_fingerprint,
                )
                if err:
                    linkage_errors.append(f"{row.domain_run_id}: {err}")
    except Exception as exc:
        linkage_errors.append(str(exc))
    _add(
        "db_mlflow_linkage",
        not linkage_errors,
        "no cross-version run fingerprints"
        if not linkage_errors
        else "; ".join(linkage_errors[:4]),
    )
    blocking = [
        item
        for item in checks
        if not item["ok"] and item["name"] not in {"mlflow_ui", "orphan_artifact_warnings"}
    ]
    return {
        "ok": len(blocking) == 0,
        "checks": checks,
        "lineage": lineage,
        "artifact_integrity": integrity,
        "total_public_strategies": TOTAL_PUBLIC_STRATEGIES,
        "active_model_version": active.get("generation"),
        "official_gate_model_version": "v2",
        "official_gate_status": "failed" if not gate_ev.get("performance_gate_passed") else "passed",
        "champion_set": False,
        "periodic_intercept": {
            "implementation": "OK",
            "evidence": {
                "v2": NOT_RECORDED,
                "v3": NOT_RECORDED,
                "v4": NOT_RECORDED,
            },
        },
        "next_action": "python -m smartscan.cli demo --offline, then python -m smartscan.cli dashboard.",
    }


def list_history(
    *,
    strategy: str | None = None,
    status: str | None = None,
    scenario: str | None = None,
    protocol_id: str | None = None,
) -> list[dict[str, Any]]:
    from smartscan.storage.pipeline import build_repository
    from smartscan.storage.repositories import RunFilters

    filt_strategy = strategy
    if strategy:
        try:
            filt_strategy = canonicalize_strategy_id(strategy)
        except SmartScanError:
            filt_strategy = strategy
    try:
        settings = StorageSettings.from_env()
        repo = build_repository(settings, track=False, upgrade=True)
        rows = repo.list_runs(
            RunFilters(
                strategy=filt_strategy,
                status=status,
                scenario_name=scenario,
                protocol_id=protocol_id,
            )
        )
    except Exception as exc:
        return [{"error": str(exc), "next_action": "Run python -m smartscan.cli db upgrade."}]
    return [
        {
            "domain_run_id": str(row.domain_run_id),
            "strategy": row.strategy,
            "protocol_id": row.protocol_id or "legacy_unknown",
            "model_version": row.model_version,
            "bundle_fingerprint": row.bundle_fingerprint,
            "duration_s": row.duration_s,
            "receiver_config_hash": row.receiver_config_hash,
            "status": row.status,
            "sync_status": row.sync_status,
            "scenario_name": row.scenario_name,
            "seeds": row.seeds,
            "git_sha": row.git_sha,
            "mlflow_run_id": row.mlflow_run_id,
            "metrics": row.metrics,
        }
        for row in rows
    ]


def verify_history_run(domain_run_id: str) -> dict[str, Any]:
    from smartscan.storage.pipeline import build_repository

    try:
        repo = build_repository(StorageSettings.from_env(), track=False, upgrade=True)
        report = repo.recompute_and_verify(UUID(domain_run_id))
    except Exception as exc:
        raise SmartScanError(f"{exc} Next action: run python -m smartscan.cli db upgrade.") from exc
    return {
        "domain_run_id": str(report.domain_run_id),
        "ok": report.ok,
        "checksum_ok": report.checksum_ok,
        "content_fingerprint_match": report.content_fingerprint_match,
        "stored_fingerprint": report.stored_fingerprint,
        "recomputed_fingerprint": report.recomputed_fingerprint,
        "metric_mismatches": {k: list(v) for k, v in report.metric_mismatches.items()},
    }


def demo_dir(cfg: DashboardConfig | None = None) -> Path:
    dash = cfg or load_dashboard_config()
    override = os.environ.get("SMARTSCAN_DEMO_DIR")
    if override:
        return Path(override)
    return project_root() / dash.demo_dir


def demo_bundle_is_complete(dest: Path) -> bool:
    """True when matched demo logs can be loaded without regenerating."""

    manifest_path = dest / "manifest.json"
    if not manifest_path.is_file() or not (dest / "truth.npz").is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(manifest, dict):
        return False
    names = manifest.get("strategies") or []
    if not names:
        return False
    return all((dest / f"{name}.npz").is_file() for name in names)


def prepare_demo_bundle(
    cfg: DashboardConfig | None = None,
    *,
    dest: Path | None = None,
    include_ppo: bool = True,
) -> dict[str, Any]:
    """Write matched agile_threat runs for the offline demo."""

    dash = cfg or load_dashboard_config()
    out = dest or demo_dir(dash)
    out.mkdir(parents=True, exist_ok=True)
    strategies = list(LIVE_STRATEGIES)
    model_dir = _model_dir(dash)
    if include_ppo and model_dir.is_dir():
        strategies.append("ppo")
    results: list[ExperimentResult] = []
    truth: GroundTruth | None = None
    for name in strategies:
        item = run_experiment(
            dash,
            scenario_id=dash.demo_scenario_id,
            seed=int(dash.demo_seed),
            strategy=name,
            duration_s=float(dash.demo_duration_s),
            dt_s=float(dash.demo_dt_s),
            receiver_seed=int(dash.demo_seed),
            persist=False,
            evaluation_overlay=False,
        )
        results.append(item)
        truth = item.truth
        save_receiver_run(item.run, out / f"{name}.npz")
        save_metrics(item.evaluation, out / f"{name}_metrics.json")
    assert truth is not None
    save_ground_truth(truth, out / "truth.npz")
    manifest = {
        "schema_version": "1.0.0",
        "scenario_id": dash.demo_scenario_id,
        "seed": dash.demo_seed,
        "receiver_seed": dash.demo_seed,
        "duration_s": dash.demo_duration_s,
        "dt_s": dash.demo_dt_s,
        "truth_fingerprint": truth.content_fingerprint,
        "strategies": [item.strategy for item in results],
        "matched": True,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def load_demo_bundle(
    cfg: DashboardConfig | None = None, *, dest: Path | None = None
) -> list[ExperimentResult]:
    from smartscan.experiment_protocol import PROTOCOL_LIVE_SESSION, SOURCE_LIVE_RUN
    from smartscan.metrics.engine import load_metrics

    dash = cfg or load_dashboard_config()
    out = dest or demo_dir(dash)
    if not demo_bundle_is_complete(out):
        prepare_demo_bundle(dash, dest=out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    truth = load_ground_truth(out / "truth.npz")
    receiver = _receiver(dash)
    loaded: list[ExperimentResult] = []

    for name in manifest.get("strategies", []):
        run_path = out / f"{name}.npz"
        metrics_path = out / f"{name}_metrics.json"
        if not run_path.is_file():
            continue
        run = load_receiver_run(run_path)
        if metrics_path.is_file():
            evaluation = load_metrics(metrics_path)
        else:
            evaluation = evaluate_strategy(
                truth, run.observations, run.decisions, receiver_config=receiver
            )
        loaded.append(
            ExperimentResult(
                strategy=str(name),
                seed=int(manifest["seed"]),
                receiver_seed=int(manifest["receiver_seed"]),
                truth=truth,
                run=run,
                evaluation=evaluation,
                model_alias="candidate" if name == "ppo" else None,
                protocol_id=PROTOCOL_LIVE_SESSION,
                duration_s=float(manifest.get("duration_s") or dash.demo_duration_s),
                dt_s=float(manifest.get("dt_s") or dash.demo_dt_s),
                metric_source=SOURCE_LIVE_RUN,
            )
        )
    return loaded


def export_comparison(
    results: list[ExperimentResult],
    *,
    json_path: Path,
    csv_path: Path | None = None,
) -> dict[str, str]:
    table = comparison_table(results)
    gate = load_performance_gate()
    payload = {
        "schema_version": METRIC_SCHEMA_VERSION,
        "git_sha": current_git_sha(),
        "performance_gate_passed": gate.get("performance_gate_passed"),
        "run_ids": [str(item.domain_run_id) if item.domain_run_id else None for item in results],
        "truth_fingerprints": [item.truth.content_fingerprint for item in results],
        "strategies": [item.strategy for item in results],
        "table": table,
        "metrics": {
            item.strategy: {key: metric_cell(item.evaluation.report, key) for key in COMPARE_KEYS}
            for item in results
        },
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    written = {"json": str(json_path)}
    if csv_path is not None and results:
        save_metrics_csv(results[0].evaluation, csv_path)
        extra = csv_path.with_suffix(".compare.csv")
        lines = ["strategy,key,value,available,unavailable_reason,numerator,denominator,unit"]
        for item in results:
            for key in COMPARE_KEYS:
                cell = metric_cell(item.evaluation.report, key)
                value = "" if cell["value"] is None else repr(cell["value"])
                num = "" if cell["numerator"] is None else repr(cell["numerator"])
                den = "" if cell["denominator"] is None else repr(cell["denominator"])
                lines.append(
                    ",".join(
                        [
                            item.strategy,
                            key,
                            value,
                            str(cell["available"]).lower(),
                            str(cell["unavailable_reason"] or "").replace(",", ";"),
                            num,
                            den,
                            str(cell["unit"] or ""),
                        ]
                    )
                )
        extra.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written["csv"] = str(csv_path)
        written["compare_csv"] = str(extra)
    return written


def dashboard_argv(host: str, port: int, app_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        host,
        "--server.port",
        str(int(port)),
        "--browser.serverAddress",
        host,
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--theme.base",
        "dark",
        "--theme.primaryColor",
        "#3AA8B5",
        "--theme.backgroundColor",
        "#05080B",
        "--theme.secondaryBackgroundColor",
        "#0A161C",
        "--theme.textColor",
        "#E8EEF2",
    ]


