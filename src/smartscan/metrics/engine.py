"""Authoritative Stage 3 metrics engine.

Separates operational detector rates, scheduler capture, and forecast scores.
Forecast metrics are typed-unavailable until Stage 5 supplies pre-action values.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np

from smartscan.metrics.matching import (
    derive_band_occupancy_events,
    dwell_occupied,
    match_detections,
    occupied_step_fraction,
    usable_interval,
)
from smartscan.metrics.schemas import (
    FORECASTS_ABSENT,
    FROZEN_METRIC_KEYS,
    FROZEN_METRIC_NAMES,
    METRIC_SCHEMA_VERSION,
    NO_ELIGIBLE_FORECASTS,
    REWARD_ABSENT,
    ZERO_DENOMINATOR,
    BandOccupancyEvent,
    CensoringSummary,
    EvaluationResult,
    MatchRecord,
    MetricsConfig,
    MetricsTables,
    MissedEventRecord,
    PdStratum,
    PerBandStats,
    SensitivityCurve,
    ratio_metric,
    unavailable,
)
from smartscan.metrics.sensitivity import analytic_sensitivity_curve
from smartscan.metrics.statistics import (
    brier_score,
    delay_summary,
    expected_calibration_error,
    kaplan_meier,
    restricted_mean_survival,
)
from smartscan.receiver.logs import DecisionLog, ObservationLog, ReceiverRun
from smartscan.types import (
    DecisionRow,
    GroundTruth,
    MetricsReport,
    MetricValue,
    ReceiverConfig,
    SmartScanError,
    content_fingerprint,
    sha256_file,
    strip_volatile,
)


def evaluate_strategy(
    truth: GroundTruth,
    observations: ObservationLog,
    decisions: DecisionLog,
    *,
    metrics_config: MetricsConfig | None = None,
    receiver_config: ReceiverConfig | None = None,
    sensitivity: SensitivityCurve | None = None,
) -> EvaluationResult:
    """Compute the frozen figures of merit for one GroundTruth + receiver run."""

    cfg = metrics_config or MetricsConfig()
    _validate_inputs(truth, observations, decisions)
    dt = float(truth.dt_s)
    duration_s = float(truth.n_steps) * dt
    horizon_s = (
        float(cfg.miss_penalty_horizon_s) if cfg.miss_penalty_horizon_s is not None else duration_s
    )
    if horizon_s <= 0:
        raise SmartScanError("miss_penalty_horizon_s must be positive.")

    events = derive_band_occupancy_events(truth)
    matches, missed, _matched_ids = match_detections(events, decisions.rows, dt_s=dt)
    classified: list[str] = [_classify(truth, row) for row in decisions.rows]

    metrics: dict[str, MetricValue] = {}
    metrics["pd"] = _operational_pd(classified, decisions.rows)
    metrics["pfa"] = _operational_pfa(classified, decisions.rows)
    curve = sensitivity
    if curve is None and cfg.include_analytic_sensitivity:
        curve = analytic_sensitivity_curve(
            target_pd=cfg.target_pd,
            m_samples=cfg.samples_per_step * cfg.dwell_steps,
            pfa_design=cfg.pfa_design,
            receiver_config=receiver_config,
        )
    metrics["sensitivity"] = _sensitivity_metric(curve, cfg.target_pd)

    n_matched = len(matches)
    metrics["average_intercept_rate"] = ratio_metric(
        FROZEN_METRIC_NAMES["average_intercept_rate"],
        float(n_matched),
        duration_s,
        unit="1/s",
    )
    n_events = len(events)
    metrics["event_interception_ratio"] = ratio_metric(
        "event_interception_ratio",
        float(n_matched),
        float(n_events),
        unit="",
    )

    delays = [item.delay_s for item in matches]
    delay_stats = delay_summary(delays)
    for stat_name, unit in (
        ("mean", "s"),
        ("median", "s"),
        ("p90", "s"),
        ("std", "s"),
    ):
        key = f"successful_event_delay_{stat_name}_s"
        value = delay_stats[stat_name]
        if value is None:
            metrics[key] = unavailable(
                key, ZERO_DENOMINATOR, numerator=None, denominator=0.0, unit=unit
            )
        else:
            metrics[key] = MetricValue(
                name=key,
                numerator=float(value) * float(delay_stats["count"] or 0.0),
                denominator=float(delay_stats["count"] or 0.0),
                value=float(value),
                unit=unit,
                available=True,
            )

    metrics["missed_event_count"] = ratio_metric(
        "missed_event_count",
        float(len(missed)),
        1.0,
        unit="1",
    )

    penalized_values = list(delays) + [horizon_s] * len(missed)
    if n_events == 0:
        metrics["all_event_penalized_delay_s"] = unavailable(
            "all_event_penalized_delay_s",
            ZERO_DENOMINATOR,
            numerator=None,
            denominator=0.0,
            unit="s",
        )
        km_rmst: float | None = None
        n_km_captured = 0
        n_km_censored = 0
    else:
        metrics["all_event_penalized_delay_s"] = ratio_metric(
            "all_event_penalized_delay_s",
            float(sum(penalized_values)),
            float(n_events),
            unit="s",
        )
        km_times: list[float] = []
        km_event: list[bool] = []
        matched_ids = {item.event_id for item in matches}
        delay_by_event = {item.event_id: item.delay_s for item in matches}
        for event in events:
            if event.event_id in matched_ids:
                km_times.append(delay_by_event[event.event_id])
                km_event.append(True)
            else:
                km_times.append(float(event.end_step - event.start_step) * dt)
                km_event.append(False)
        times_arr, surv_arr = kaplan_meier(np.asarray(km_times), np.asarray(km_event))
        km_rmst = restricted_mean_survival(times_arr, surv_arr, horizon_s)
        n_km_captured = int(sum(km_event))
        n_km_censored = int(len(km_event) - n_km_captured)
        metrics["km_rmst_s"] = MetricValue(
            name="km_rmst_s",
            numerator=km_rmst,
            denominator=horizon_s,
            value=km_rmst,
            unit="s",
            available=True,
        )

    if n_events == 0:
        metrics["km_rmst_s"] = unavailable(
            "km_rmst_s", ZERO_DENOMINATOR, numerator=None, denominator=horizon_s, unit="s"
        )

    captured_w = sum(item.threat_weight for item in matches)
    total_w = sum(event.threat_weight for event in events)
    metrics["threat_weighted_capture"] = ratio_metric(
        "threat_weighted_capture",
        float(captured_w),
        float(total_w),
        unit="",
    )

    n_completed = len(decisions.rows)
    n_noise = sum(1 for label in classified if label == "noise")
    metrics["wasted_dwell_fraction"] = ratio_metric(
        "wasted_dwell_fraction",
        float(n_noise),
        float(n_completed),
        unit="",
    )
    n_tune = sum(1 for row in observations.rows if row.receiver_state == "TUNING")
    n_obs = len(observations.rows)
    metrics["tuning_fraction"] = ratio_metric(
        "tuning_fraction",
        float(n_tune),
        float(n_obs),
        unit="",
    )
    metrics["incomplete_decision_count"] = MetricValue(
        name="incomplete_decision_count",
        numerator=float(decisions.n_incomplete_commands),
        denominator=1.0,
        value=float(decisions.n_incomplete_commands),
        unit="1",
        available=True,
    )
    metrics["throughput"] = ratio_metric(
        "throughput",
        float(n_completed),
        duration_s,
        unit="1/s",
    )

    intercept_ratio_value = metrics["event_interception_ratio"].value
    wasted_value = metrics["wasted_dwell_fraction"].value
    components: dict[str, float | None] = {
        "event_interception_ratio": intercept_ratio_value,
        "wasted_dwell_fraction": wasted_value,
        "tuning_fraction": metrics["tuning_fraction"].value,
    }
    if intercept_ratio_value is None or wasted_value is None:
        metrics["evaluation_score"] = unavailable(
            "evaluation_score",
            "missing_evaluation_score_components",
            unit="1",
        )
        components["evaluation_score"] = None
    else:
        score = float(intercept_ratio_value) - float(wasted_value)
        metrics["evaluation_score"] = MetricValue(
            name="evaluation_score",
            numerator=score,
            denominator=1.0,
            value=score,
            unit="1",
            available=True,
        )
        components["evaluation_score"] = score

    rewards = [float(row.reward) for row in decisions.rows if row.reward is not None]
    if not rewards:
        metrics["average_reward"] = unavailable(
            FROZEN_METRIC_NAMES["average_reward"],
            REWARD_ABSENT,
            numerator=None,
            denominator=0.0,
            unit="1",
        )
    else:
        metrics["average_reward"] = ratio_metric(
            FROZEN_METRIC_NAMES["average_reward"],
            float(sum(rewards)),
            float(len(rewards)),
            unit="1",
        )

    _add_forecast_metrics(metrics, truth, decisions.rows, cfg, dt, duration_s, horizon_s)

    strata = _pd_strata(truth, classified, decisions.rows)
    per_band = _per_band_stats(truth, events, matches, missed, decisions.rows, dt, cfg)

    support = {
        "n_band_occupancy_events": n_events,
        "n_matched_events": n_matched,
        "n_completed_decisions": n_completed,
        "n_occupied_completed": sum(1 for label in classified if label == "occupied"),
        "n_noise_only_completed": n_noise,
        "n_true_positives": sum(
            1
            for label, row in zip(classified, decisions.rows, strict=True)
            if label == "occupied" and row.hit
        ),
        "n_false_alarms": sum(
            1
            for label, row in zip(classified, decisions.rows, strict=True)
            if label == "noise" and row.hit
        ),
        "duration_s": duration_s,
        "dt_s": dt,
        "miss_penalty_horizon_s": horizon_s,
        "activity_threshold": cfg.activity_threshold,
        "successful_event_delay": delay_stats,
    }

    f_count = int(support_get_forecast_count(metrics))
    eligible = int(support_get_eligible(metrics))
    coverage_metric = metrics.get("intercept_time_forecast_coverage")
    coverage = coverage_metric.value if coverage_metric is not None else None
    penalized = metrics["all_event_penalized_delay_s"].value
    km_value = metrics["km_rmst_s"].value
    censoring = CensoringSummary(
        miss_penalty_horizon_s=horizon_s,
        forecast_count=f_count,
        eligible_count=eligible,
        forecast_coverage=coverage,
        km_rmst_s=km_value,
        all_event_penalized_delay_s=penalized,
        n_km_captured=n_km_captured if n_events else 0,
        n_km_censored=n_km_censored if n_events else 0,
    )

    tables = MetricsTables(
        band_occupancy_events=events,
        matches=matches,
        missed_events=missed,
        pd_strata=strata,
        per_band=per_band,
        evaluation_score_components=components,
        support=support,
    )
    config_hash = content_fingerprint(cfg.model_dump())
    input_fingerprints = {
        "ground_truth": truth.content_fingerprint,
        "observation_log": observations.ground_truth_fingerprint,
        "decision_log": decisions.ground_truth_fingerprint,
        "receiver_config": observations.receiver_config_hash,
    }
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = MetricsReport(
        metric_schema_version=METRIC_SCHEMA_VERSION,
        metrics=metrics,
        config_hash=config_hash,
        input_fingerprints=input_fingerprints,
        artifact_sha256={
            "ground_truth": truth.artifact_sha256 or "",
            "receiver_run": decisions.artifact_sha256 or observations.artifact_sha256 or "",
        },
        created_at=created_at,
    )
    fingerprint = content_fingerprint(
        strip_volatile(
            {
                "metric_schema_version": METRIC_SCHEMA_VERSION,
                "metrics": {key: metrics[key].model_dump() for key in sorted(metrics)},
                "tables": tables.model_dump(),
                "censoring": censoring.model_dump(),
                "sensitivity": None if curve is None else curve.model_dump(),
                "config_hash": config_hash,
                "input_fingerprints": input_fingerprints,
            }
        )
    )
    notes = [
        "Operational Pd/Pfa are scheduler-conditioned dwell rates, not the controlled sensitivity curve.",
        "BandOccupancyEvents are the official capture units; emitter events are diagnostics only.",
        "Evaluator threat weights use max aggregation and are not policy-visible.",
        "Forecast metrics stay unavailable until pre-action p_active/p_hit/intercept-time fields are set.",
    ]
    result = EvaluationResult(
        report=report,
        tables=tables,
        censoring=censoring,
        sensitivity=curve,
        content_fingerprint=fingerprint,
        notes=notes,
    )
    ensure_frozen_keys(result)
    return result


def evaluate_run(
    truth: GroundTruth,
    run: ReceiverRun,
    **kwargs: Any,
) -> EvaluationResult:
    return evaluate_strategy(truth, run.observations, run.decisions, **kwargs)


def save_metrics(result: EvaluationResult, path: str | Path) -> EvaluationResult:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    dest.write_text(json.dumps(payload, sort_keys=True, allow_nan=False), encoding="utf-8")
    digest = sha256_file(dest)
    result.report.artifact_sha256["metrics_json"] = digest
    return result


def load_metrics(path: str | Path) -> EvaluationResult:
    src = Path(path)
    if not src.is_file():
        raise SmartScanError(f"Metrics JSON not found: {src}")
    payload = json.loads(src.read_text(encoding="utf-8"))
    return EvaluationResult.model_validate(payload)


def save_metrics_csv(result: EvaluationResult, path: str | Path) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "key",
                "name",
                "numerator",
                "denominator",
                "value",
                "unit",
                "available",
                "unavailable_reason",
            ],
        )
        writer.writeheader()
        for key, metric in result.report.metrics.items():
            writer.writerow(
                {
                    "key": key,
                    "name": metric.name,
                    "numerator": metric.numerator,
                    "denominator": metric.denominator,
                    "value": metric.value,
                    "unit": metric.unit,
                    "available": metric.available,
                    "unavailable_reason": metric.unavailable_reason,
                }
            )


def _validate_inputs(
    truth: GroundTruth,
    observations: ObservationLog,
    decisions: DecisionLog,
) -> None:
    if observations.ground_truth_fingerprint != truth.content_fingerprint:
        raise SmartScanError("ObservationLog fingerprint does not match GroundTruth.")
    if decisions.ground_truth_fingerprint != truth.content_fingerprint:
        raise SmartScanError("DecisionLog fingerprint does not match GroundTruth.")
    if observations.schema_version != truth.schema_version:
        raise SmartScanError(
            f"ObservationLog schema {observations.schema_version} != GroundTruth {truth.schema_version}."
        )
    if decisions.schema_version != truth.schema_version:
        raise SmartScanError(
            f"DecisionLog schema {decisions.schema_version} != GroundTruth {truth.schema_version}."
        )
    if abs(float(observations.dt_s) - float(truth.dt_s)) > 1e-12:
        raise SmartScanError("ObservationLog dt_s does not match GroundTruth.")
    if abs(float(decisions.dt_s) - float(truth.dt_s)) > 1e-12:
        raise SmartScanError("DecisionLog dt_s does not match GroundTruth.")
    n_bands = truth.band_plan.n_bands
    for row in decisions.rows:
        if row.target_band < 0 or row.target_band >= n_bands:
            raise SmartScanError(
                f"Decision {row.decision_id} target_band={row.target_band} outside 0..{n_bands - 1}."
            )
        if row.end_step > truth.n_steps:
            raise SmartScanError(
                f"Decision {row.decision_id} end_step={row.end_step} exceeds n_steps={truth.n_steps}."
            )


def _classify(truth: GroundTruth, row: DecisionRow) -> Literal["occupied", "noise"]:
    return "occupied" if dwell_occupied(truth, row) else "noise"


def _operational_pd(classified: list[str], rows: list[DecisionRow]) -> MetricValue:
    occupied = [
        row for label, row in zip(classified, rows, strict=True) if label == "occupied"
    ]
    tp = sum(1 for row in occupied if row.hit)
    return ratio_metric(FROZEN_METRIC_NAMES["pd"], float(tp), float(len(occupied)), unit="")


def _operational_pfa(classified: list[str], rows: list[DecisionRow]) -> MetricValue:
    noise = [row for label, row in zip(classified, rows, strict=True) if label == "noise"]
    fa = sum(1 for row in noise if row.hit)
    return ratio_metric(FROZEN_METRIC_NAMES["pfa"], float(fa), float(len(noise)), unit="")


def _sensitivity_metric(curve: SensitivityCurve | None, target_pd: float) -> MetricValue:
    if curve is None:
        return unavailable(
            FROZEN_METRIC_NAMES["sensitivity"],
            "controlled_sensitivity_sweep_not_attached",
            denominator=target_pd,
            unit="dB",
        )
    return MetricValue(
        name=FROZEN_METRIC_NAMES["sensitivity"],
        numerator=float(curve.snr_db_at_target),
        denominator=float(target_pd),
        value=float(curve.snr_db_at_target),
        unit="dB",
        available=True,
    )


def _occupied_bin(fraction: float) -> str:
    if fraction <= 0.25:
        return "(0,0.25]"
    if fraction <= 0.5:
        return "(0.25,0.5]"
    if fraction <= 0.75:
        return "(0.50,0.75]"
    return "(0.75,1]"


def _snr_bin(snr_db: float | None) -> str:
    if snr_db is None:
        return "unknown"
    if snr_db < 0:
        return "<0dB"
    if snr_db < 10:
        return "[0,10)dB"
    return ">=10dB"


def _pd_strata(
    truth: GroundTruth,
    classified: list[str],
    rows: list[DecisionRow],
) -> list[PdStratum]:
    buckets: dict[tuple[int, str, str], list[DecisionRow]] = {}
    for label, row in zip(classified, rows, strict=True):
        if label != "occupied":
            continue
        key = (
            int(row.dwell_steps),
            _occupied_bin(occupied_step_fraction(truth, row)),
            _snr_bin(row.measured_snr_db),
        )
        buckets.setdefault(key, []).append(row)
    strata: list[PdStratum] = []
    for (dwell, occ_bin, snr_bin), group in sorted(buckets.items()):
        tp = sum(1 for row in group if row.hit)
        den = len(group)
        strata.append(
            PdStratum(
                dwell_steps=dwell,
                occupied_fraction_bin=occ_bin,
                snr_bin=snr_bin,
                true_positives=tp,
                occupied_completed=den,
                pd=(tp / den) if den else None,
            )
        )
    return strata


def _per_band_stats(
    truth: GroundTruth,
    events: list[BandOccupancyEvent],
    matches: list[MatchRecord],
    missed: list[MissedEventRecord],
    rows: list[DecisionRow],
    dt: float,
    cfg: MetricsConfig,
) -> list[PerBandStats]:
    del cfg
    n_steps = truth.n_steps
    n_bands = truth.band_plan.n_bands
    matched_by_band: dict[int, int] = {}
    events_by_band: dict[int, int] = {}
    missed_by_band: dict[int, int] = {}
    for event in events:
        events_by_band[event.band] = events_by_band.get(event.band, 0) + 1
    for match in matches:
        matched_by_band[match.band] = matched_by_band.get(match.band, 0) + 1
    for miss in missed:
        missed_by_band[miss.band] = missed_by_band.get(miss.band, 0) + 1

    stats: list[PerBandStats] = []
    for band in range(n_bands):
        active = int(truth.occupied[:, band].sum())
        dwell_steps = 0
        starts: list[int] = []
        p_hit: list[float] = []
        y_hit: list[float] = []
        p_act: list[float] = []
        y_act: list[float] = []
        for row in rows:
            if int(row.target_band) != band:
                continue
            u0, u1 = usable_interval(row)
            dwell_steps += max(0, u1 - u0)
            starts.append(int(row.start_step))
            if row.p_hit is not None:
                p_hit.append(float(row.p_hit))
                y_hit.append(1.0 if row.hit else 0.0)
            if row.p_active is not None:
                p_act.append(float(row.p_active))
                y_act.append(1.0 if dwell_occupied(truth, row) else 0.0)
        n_ev = events_by_band.get(band, 0)
        n_match = matched_by_band.get(band, 0)
        ratio = None if n_ev == 0 else n_match / n_ev
        gap: float | None
        if len(starts) < 2:
            gap = None
        else:
            ordered = sorted(starts)
            diffs = [
                float(ordered[i + 1] - ordered[i]) * dt for i in range(len(ordered) - 1)
            ]
            gap = float(sum(diffs) / len(diffs))
        hit_brier = (
            brier_score(np.asarray(p_hit), np.asarray(y_hit)) if p_hit else None
        )
        act_brier = (
            brier_score(np.asarray(p_act), np.asarray(y_act)) if p_act else None
        )
        stats.append(
            PerBandStats(
                band=band,
                active_fraction=active / float(n_steps) if n_steps else 0.0,
                dwell_fraction=dwell_steps / float(n_steps) if n_steps else 0.0,
                intercept_ratio=ratio,
                n_events=n_ev,
                n_matched=n_match,
                n_missed=missed_by_band.get(band, 0),
                mean_revisit_gap_s=gap,
                hit_brier=hit_brier,
                activity_brier=act_brier,
            )
        )
    return stats


def _add_forecast_metrics(
    metrics: dict[str, MetricValue],
    truth: GroundTruth,
    rows: list[DecisionRow],
    cfg: MetricsConfig,
    dt: float,
    duration_s: float,
    horizon_s: float,
) -> None:
    activity = [(row, dwell_occupied(truth, row)) for row in rows if row.p_active is not None]
    hits = [(row, bool(row.hit)) for row in rows if row.p_hit is not None]
    times = [row for row in rows if row.time_to_next_completed_intercept_s is not None]

    if not activity:
        metrics["correct_predictions"] = unavailable(
            FROZEN_METRIC_NAMES["correct_predictions"],
            FORECASTS_ABSENT,
            numerator=None,
            denominator=0.0,
            unit="percent",
        )
        for key in ("activity_precision", "activity_recall", "activity_brier", "activity_ece"):
            metrics[key] = unavailable(key, FORECASTS_ABSENT, unit="")
    else:
        y = np.array([1.0 if occupied else 0.0 for _, occupied in activity], dtype=np.float64)
        p_vals: list[float] = []
        for row, _occupied in activity:
            prob = row.p_active
            assert prob is not None
            p_vals.append(float(prob))
        p = np.asarray(p_vals, dtype=np.float64)
        pred = p >= float(cfg.activity_threshold)
        y_bool = y >= 0.5
        tp = int(np.sum(pred & y_bool))
        tn = int(np.sum((~pred) & (~y_bool)))
        fp = int(np.sum(pred & (~y_bool)))
        fn = int(np.sum((~pred) & y_bool))
        n = int(y.size)
        metrics["correct_predictions"] = ratio_metric(
            FROZEN_METRIC_NAMES["correct_predictions"],
            float(tp + tn),
            float(n),
            unit="percent",
            scale=100.0,
        )
        metrics["activity_precision"] = ratio_metric(
            "activity_precision", float(tp), float(tp + fp), unit=""
        )
        metrics["activity_recall"] = ratio_metric(
            "activity_recall", float(tp), float(tp + fn), unit=""
        )
        brier = brier_score(p, y)
        ece = expected_calibration_error(p, y, n_bins=cfg.ece_bins)
        metrics["activity_brier"] = MetricValue(
            name="activity_brier",
            numerator=brier,
            denominator=float(n),
            value=brier,
            unit="1",
            available=True,
        )
        metrics["activity_ece"] = MetricValue(
            name="activity_ece",
            numerator=ece,
            denominator=float(n),
            value=ece,
            unit="1",
            available=True,
        )

    if not hits:
        for key in ("hit_brier", "hit_ece"):
            metrics[key] = unavailable(key, FORECASTS_ABSENT, unit="1")
    else:
        y_h = np.array([1.0 if hit else 0.0 for _, hit in hits], dtype=np.float64)
        p_hit_vals: list[float] = []
        for row, _hit in hits:
            prob = row.p_hit
            assert prob is not None
            p_hit_vals.append(float(prob))
        p_h = np.asarray(p_hit_vals, dtype=np.float64)
        hit_brier = brier_score(p_h, y_h)
        hit_ece = expected_calibration_error(p_h, y_h, n_bins=cfg.ece_bins)
        metrics["hit_brier"] = MetricValue(
            name="hit_brier",
            numerator=hit_brier,
            denominator=float(y_h.size),
            value=hit_brier,
            unit="1",
            available=True,
        )
        metrics["hit_ece"] = MetricValue(
            name="hit_ece",
            numerator=hit_ece,
            denominator=float(y_h.size),
            value=hit_ece,
            unit="1",
            available=True,
        )

    metrics["intercept_time_forecast_count"] = MetricValue(
        name="intercept_time_forecast_count",
        numerator=float(len(times)),
        denominator=1.0,
        value=float(len(times)),
        unit="1",
        available=True,
    )
    if not times:
        metrics["average_intercept_time_error"] = unavailable(
            FROZEN_METRIC_NAMES["average_intercept_time_error"],
            FORECASTS_ABSENT,
            numerator=None,
            denominator=0.0,
            unit="s",
        )
        metrics["intercept_time_forecast_coverage"] = unavailable(
            "intercept_time_forecast_coverage",
            FORECASTS_ABSENT,
            numerator=0.0,
            denominator=0.0,
            unit="",
        )
        metrics["intercept_time_censored_rmst_s"] = unavailable(
            "intercept_time_censored_rmst_s",
            FORECASTS_ABSENT,
            unit="s",
        )
        return

    abs_err: list[float] = []
    restricted: list[float] = []
    for index, row in enumerate(rows):
        if row.time_to_next_completed_intercept_s is None:
            continue
        declared = float(row.forecast_horizon_s) if row.forecast_horizon_s is not None else horizon_s
        cap = min(declared, duration_s)
        actual = _actual_time_to_hit(rows, index, dt)
        if actual is None or actual > cap:
            restricted.append(cap)
            continue
        abs_err.append(abs(float(row.time_to_next_completed_intercept_s) - actual))
        restricted.append(actual)

    metrics["average_intercept_time_error"] = (
        ratio_metric(
            FROZEN_METRIC_NAMES["average_intercept_time_error"],
            float(sum(abs_err)),
            float(len(abs_err)),
            unit="s",
        )
        if abs_err
        else unavailable(
            FROZEN_METRIC_NAMES["average_intercept_time_error"],
            NO_ELIGIBLE_FORECASTS,
            numerator=None,
            denominator=0.0,
            unit="s",
        )
    )
    metrics["intercept_time_forecast_coverage"] = ratio_metric(
        "intercept_time_forecast_coverage",
        float(len(abs_err)),
        float(len(times)),
        unit="",
    )
    metrics["intercept_time_censored_rmst_s"] = ratio_metric(
        "intercept_time_censored_rmst_s",
        float(sum(restricted)),
        float(len(restricted)),
        unit="s",
    )


def _actual_time_to_hit(rows: list[DecisionRow], index: int, dt: float) -> float | None:
    start = int(rows[index].start_step)
    for row in rows[index:]:
        if row.hit:
            return float(row.end_step - start) * dt
    return None


def support_get_forecast_count(metrics: dict[str, MetricValue]) -> float:
    item = metrics.get("intercept_time_forecast_count")
    if item is None or item.value is None:
        return 0.0
    return float(item.value)


def support_get_eligible(metrics: dict[str, MetricValue]) -> float:
    item = metrics.get("intercept_time_forecast_coverage")
    if item is None or not item.available or item.numerator is None:
        return 0.0
    return float(item.numerator)


def ensure_frozen_keys(result: EvaluationResult) -> None:
    missing = [key for key in FROZEN_METRIC_KEYS if key not in result.report.metrics]
    if missing:
        raise SmartScanError(f"MetricsReport missing frozen keys: {missing}")
