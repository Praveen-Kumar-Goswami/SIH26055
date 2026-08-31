"""Held-out benchmark, paired CIs, and the Stage 5 performance gate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from smartscan.config import BenchmarkConfig, SimulateConfig, TrainConfig, load_yaml, project_root
from smartscan.metrics.engine import evaluate_strategy
from smartscan.metrics.statistics import newcombe_diff_upper, paired_compare
from smartscan.ml.forecast import naive_ratio_forecast
from smartscan.ml.policies import NON_ORACLE_STRATEGIES, make_policy
from smartscan.ml.runner import run_policy_episode
from smartscan.receiver.detector import load_receiver_config
from smartscan.rf.environment import simulate
from smartscan.types import GroundTruth, ReceiverConfig, SmartScanError, content_fingerprint

PRIMARY_AIR = "average_intercept_rate"
PRIMARY_RATIO = "event_interception_ratio"
PRIMARY_DELAY = "successful_event_median_delay_s"


@dataclass
class SeedRow:
    scenario_id: str
    seed: int
    strategy: str
    metrics: dict[str, float | None]
    pfa_num: float = 0.0
    pfa_den: float = 0.0


@dataclass
class GateResult:
    performance_gate_passed: bool
    reasons: list[str] = field(default_factory=list)
    comparisons: dict[str, Any] = field(default_factory=dict)
    family_pass: dict[str, bool] = field(default_factory=dict)


def load_held_out_manifest(path: str | Path) -> dict[str, Any]:
    loaded: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise SmartScanError("Held-out manifest must be a JSON object.")
    payload: dict[str, Any] = loaded
    payload["content_fingerprint"] = content_fingerprint(
        {k: v for k, v in payload.items() if k != "content_fingerprint"}
    )
    return payload


def _receiver(bench: BenchmarkConfig) -> ReceiverConfig:
    payload = dict(load_yaml(project_root() / bench.receiver_config))
    payload["noise_power_w"] = float(bench.noise_power_w)
    return load_receiver_config(payload)


def _metric(result: Any, key: str) -> float | None:
    item = result.report.metrics.get(key)
    if item is None or not item.available or item.value is None:
        return None
    return float(item.value)


def _delay_metric(result: Any) -> float | None:
    item = result.report.metrics.get("successful_event_delay_median_s")
    if item is None or not item.available or item.value is None:
        return None
    return float(item.value)


def run_held_out_pair(
    *,
    truth: GroundTruth,
    receiver: ReceiverConfig,
    train_cfg: TrainConfig,
    strategy: str,
    seed: int,
    bundle_predict: Any | None = None,
    feature_builder: Any | None = None,
    allow_oracle: bool = False,
    predictor: Any | None = None,
) -> tuple[Any, Any]:
    occupied = truth.occupied if allow_oracle else None
    schedule = make_policy(
        strategy,
        dwell_steps=train_cfg.default_dwell_steps,
        schedule_seed=seed,
        band_order=tuple(train_cfg.public_priorities),
        n_bands=truth.band_plan.n_bands,
        dwell_bins=tuple(int(x) for x in train_cfg.dwell_bins),
        occupied=occupied,
        allow_oracle=allow_oracle,
        ppo_predict=bundle_predict,
        feature_builder=feature_builder,
        predictor=predictor if strategy == "ppo" else None,
        include_predictor_obs=bool(getattr(train_cfg, "include_predictor_obs", False))
        if strategy == "ppo"
        else False,
        include_action_history=int(getattr(train_cfg, "include_action_history", 0) or 0)
        if strategy == "ppo"
        else 0,
        include_neural_predictor_obs=bool(
            getattr(train_cfg, "include_neural_predictor_obs", False)
        )
        if strategy == "ppo"
        else False,
    )
    run = run_policy_episode(
        truth,
        schedule,
        receiver,
        cfg=train_cfg,
        receiver_seed=seed,
        predictor=predictor,
    )
    evaluation = evaluate_strategy(
        truth, run.observations, run.decisions, receiver_config=receiver
    )
    return run, evaluation


def evaluate_held_out(
    bench: BenchmarkConfig,
    train_cfg: TrainConfig,
    manifest: dict[str, Any],
    *,
    ppo_predict: Any | None = None,
    feature_builder_factory: Any | None = None,
    include_oracle: bool = True,
    predictor: Any | None = None,
) -> tuple[list[SeedRow], GateResult]:
    receiver = _receiver(bench)
    pairs: list[tuple[str, int]] = []
    for item in manifest.get("pairs", []):
        pairs.append((str(item["scenario_id"]), int(item["seed"])))
    if not pairs:
        raise SmartScanError("held_out_manifest.json has no pairs.")
    if len(pairs) < 30:
        raise SmartScanError("Held-out manifest must contain at least 30 paired seeds.")
    strategies = list(NON_ORACLE_STRATEGIES) + (["ppo"] if ppo_predict is not None else [])
    if include_oracle:
        strategies = strategies + ["oracle-ceiling"]
    rows: list[SeedRow] = []
    for scenario_id, seed in pairs:
        sid = scenario_id
        if scenario_id == "unseen_random":
            sid = "random"
        if scenario_id == "tsrd_synthetic":
            sid = "sparse"
        sim = SimulateConfig(
            seed=seed,
            dt_s=bench.dt_s,
            duration_s=bench.duration_s,
            band_plan_id=bench.band_plan_id,
            scenario_id=sid,
        )
        if scenario_id == "tsrd_synthetic":
            from smartscan.data.turing import import_turing
            from smartscan.ml.tsrd_sample import write_tiny_tsrd

            tmp = project_root() / "artifacts" / "runs" / f"heldout_tsrd_{seed}.h5"
            write_tiny_tsrd(tmp)
            truth = import_turing(tmp, band_plan_id=bench.band_plan_id, dt_s=bench.dt_s)
        else:
            truth = simulate(sim)
        for strategy in strategies:
            fb = feature_builder_factory() if feature_builder_factory is not None else None
            run, evaluation = run_held_out_pair(
                truth=truth,
                receiver=receiver,
                train_cfg=train_cfg,
                strategy=strategy,
                seed=seed,
                bundle_predict=ppo_predict if strategy == "ppo" else None,
                feature_builder=fb,
                allow_oracle=strategy == "oracle-ceiling",
                predictor=predictor if strategy == "ppo" else None,
            )
            pfa = evaluation.report.metrics.get("pfa")
            rows.append(
                SeedRow(
                    scenario_id=scenario_id,
                    seed=seed,
                    strategy=strategy,
                    metrics={
                        PRIMARY_AIR: _metric(evaluation, PRIMARY_AIR),
                        PRIMARY_RATIO: _metric(evaluation, PRIMARY_RATIO),
                        "median_delay": _delay_metric(evaluation),
                        "pfa": _metric(evaluation, "pfa"),
                        "average_intercept_time_error": _metric(
                            evaluation, "average_intercept_time_error"
                        ),
                        "intercept_time_forecast_coverage": _metric(
                            evaluation, "intercept_time_forecast_coverage"
                        ),
                        "predicted_interception_ratio": run.decisions.predicted_interception_ratio,
                    },
                    pfa_num=float(pfa.numerator or 0.0) if pfa is not None else 0.0,
                    pfa_den=float(pfa.denominator or 0.0) if pfa is not None else 0.0,
                )
            )
    gate = score_performance_gate(rows, bench)
    return rows, gate


def _values(rows: list[SeedRow], strategy: str, key: str, scenario: str | None = None) -> list[float]:
    out: list[float] = []
    for row in rows:
        if row.strategy != strategy:
            continue
        if scenario is not None and row.scenario_id != scenario:
            continue
        val = row.metrics.get(key)
        if val is None:
            continue
        out.append(float(val))
    return out


def _paired_reports(values_a: list[float], values_b: list[float], seed: int) -> dict[str, Any]:
    from smartscan.types import MetricsReport, MetricValue

    def as_reports(vals: list[float]) -> list[MetricsReport]:
        return [
            MetricsReport(metrics={"x": MetricValue(name="x", value=v, available=True)})
            for v in vals
        ]

    if len(values_a) != len(values_b) or not values_a:
        return {"mean_delta": None, "ci_low": None, "ci_high": None, "n_scored": 0}
    return paired_compare(as_reports(values_a), as_reports(values_b), metric_key="x", seed=seed)


def score_performance_gate(rows: list[SeedRow], bench: BenchmarkConfig) -> GateResult:
    reasons: list[str] = []
    comparisons: dict[str, Any] = {}
    ppo = _values(rows, "ppo", PRIMARY_AIR)
    seq = _values(rows, "sequential", PRIMARY_AIR)
    rnd = _values(rows, "random", PRIMARY_AIR)
    if not ppo or not seq or not rnd:
        return GateResult(
            performance_gate_passed=False,
            reasons=["missing PPO or baseline seed rows"],
            comparisons={},
        )
    mean_ppo = float(np.mean(ppo))
    mean_seq = float(np.mean(seq))
    mean_rnd = float(np.mean(rnd))
    comparisons["air_means"] = {
        name: float(np.mean(_values(rows, name, PRIMARY_AIR)))
        for name in sorted({r.strategy for r in rows})
        if _values(rows, name, PRIMARY_AIR)
    }
    comparisons["air_means"].update({"ppo": mean_ppo, "sequential": mean_seq, "random": mean_rnd})
    rel_seq = (mean_ppo - mean_seq) / max(abs(mean_seq), 1e-12)
    rel_rnd = (mean_ppo - mean_rnd) / max(abs(mean_rnd), 1e-12)
    comparisons["air_rel_vs_sequential"] = rel_seq
    comparisons["air_rel_vs_random"] = rel_rnd
    if rel_seq < bench.vs_sequential_air_rel:
        reasons.append(
            f"AIR vs sequential {rel_seq:.4f} < required {bench.vs_sequential_air_rel}"
        )
    if rel_rnd < bench.vs_random_air_rel:
        reasons.append(f"AIR vs random {rel_rnd:.4f} < required {bench.vs_random_air_rel}")

    ppo_delay = _values(rows, "ppo", "median_delay")
    seq_delay = _values(rows, "sequential", "median_delay")
    if ppo_delay and seq_delay:
        # Lower delay is better: reduction = (seq - ppo) / seq
        mean_pd = float(np.mean(ppo_delay))
        mean_sd = float(np.mean(seq_delay))
        delay_red = (mean_sd - mean_pd) / max(abs(mean_sd), 1e-12)
        comparisons["delay_reduction_vs_sequential"] = delay_red
        if delay_red < bench.vs_sequential_delay_rel:
            reasons.append(
                f"delay reduction vs sequential {delay_red:.4f} < {bench.vs_sequential_delay_rel}"
            )
    else:
        reasons.append("median delay unavailable; cannot score delay gate")

    non_oracle = [s for s in NON_ORACLE_STRATEGIES]
    best_name = None
    best_mean = -1e18
    for name in non_oracle:
        vals = _values(rows, name, PRIMARY_AIR)
        if vals and float(np.mean(vals)) > best_mean:
            best_mean = float(np.mean(vals))
            best_name = name
    comparisons["best_non_oracle"] = best_name
    if best_name is None:
        reasons.append("no non-oracle baseline scores")
        return GateResult(False, reasons, comparisons)

    # Paired CIs vs best
    keys = [PRIMARY_AIR, PRIMARY_RATIO, "median_delay"]
    ci_exclude_zero = False
    for key in keys:
        a = _values(rows, "ppo", key)
        b = _values(rows, best_name, key)
        n = min(len(a), len(b))
        cmp_ = _paired_reports(a[:n], b[:n], bench.bootstrap_seed)
        comparisons[f"vs_best_{key}"] = cmp_
        if cmp_.get("ci_low") is not None and cmp_.get("ci_high") is not None:
            lo, hi = float(cmp_["ci_low"]), float(cmp_["ci_high"])
            if key == "median_delay":
                # ppo - best; negative is improvement
                if hi < 0:
                    ci_exclude_zero = True
            else:
                if lo > 0:
                    ci_exclude_zero = True
        if key != "median_delay" and a and b:
            rel = (float(np.mean(a)) - float(np.mean(b))) / max(abs(float(np.mean(b))), 1e-12)
            if rel < -bench.vs_best_noninferior_rel:
                reasons.append(f"{key} inferior to {best_name} by {rel:.4f}")
    if not ci_exclude_zero:
        reasons.append("no primary paired delta vs best non-oracle has 95% CI excluding zero")

    # Pfa Newcombe
    ppo_n = sum(r.pfa_num for r in rows if r.strategy == "ppo")
    ppo_pfa_den = sum(r.pfa_den for r in rows if r.strategy == "ppo")
    best_n = sum(r.pfa_num for r in rows if r.strategy == best_name)
    best_pfa_den = sum(r.pfa_den for r in rows if r.strategy == best_name)
    if ppo_pfa_den <= 0 or best_pfa_den <= 0:
        reasons.append("Pfa denominators empty; cannot score Newcombe guardrail")
    else:
        upper = newcombe_diff_upper(int(ppo_n), int(ppo_pfa_den), int(best_n), int(best_pfa_den))
        limit = max(bench.pfa_newcombe_abs, bench.pfa_newcombe_rel * bench.pfa_design)
        comparisons["pfa_newcombe_upper"] = upper
        comparisons["pfa_newcombe_limit"] = limit
        comparisons["pfa_counts"] = {
            "ppo": [ppo_n, ppo_pfa_den],
            best_name: [best_n, best_pfa_den],
        }
        if upper > limit:
            reasons.append(f"Pfa Newcombe upper {upper:.6g} > limit {limit:.6g}")

    family_pass: dict[str, bool] = {}
    families = sorted({r.scenario_id for r in rows})
    for fam in families:
        ppo_f = _values(rows, "ppo", PRIMARY_AIR, fam)
        seq_f = _values(rows, "sequential", PRIMARY_AIR, fam)
        if ppo_f and seq_f:
            rel = (float(np.mean(ppo_f)) - float(np.mean(seq_f))) / max(
                abs(float(np.mean(seq_f))), 1e-12
            )
            family_pass[fam] = rel >= bench.vs_sequential_air_rel
        else:
            family_pass[fam] = False
    comparisons["family_pass"] = family_pass
    n_family = sum(1 for ok in family_pass.values() if ok)
    if n_family < 2 or not family_pass.get("agile_threat", False):
        reasons.append("improvement must hold in at least two families including agile_threat")

    pred_err: list[float] = []
    naive_err: list[float] = []
    time_err = _values(rows, "ppo", "average_intercept_time_error")
    coverage = _values(rows, "ppo", "intercept_time_forecast_coverage")
    n_bands = 16
    horizon_cmds = max(1, int(round(float(bench.duration_s) / max(float(bench.dt_s) * 8.0, 1e-9))))
    naive = naive_ratio_forecast(n_bands, horizon_cmds)
    for row in rows:
        if row.strategy != "ppo":
            continue
        true = row.metrics.get(PRIMARY_RATIO)
        pred = row.metrics.get("predicted_interception_ratio")
        if true is None or pred is None:
            continue
        pred_err.append(abs(float(pred) - float(true)))
        naive_err.append(abs(float(naive) - float(true)))
    comparisons["forecast"] = {
        "ratio_mae": float(np.mean(pred_err)) if pred_err else None,
        "naive_ratio_mae": float(np.mean(naive_err)) if naive_err else None,
        "time_error_mean": float(np.mean(time_err)) if time_err else None,
        "forecast_coverage_mean": float(np.mean(coverage)) if coverage else None,
        "n_forecast_scored": len(pred_err),
    }

    passed = len(reasons) == 0
    return GateResult(passed, reasons, comparisons, family_pass)
