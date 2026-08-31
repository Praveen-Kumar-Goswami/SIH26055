"""Hand-authored Stage 3 golden fixtures and metric tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from smartscan.metrics.engine import (
    evaluate_strategy,
    load_metrics,
    save_metrics,
    save_metrics_csv,
)
from smartscan.metrics.matching import (
    derive_band_occupancy_events,
    dwell_occupied,
    match_detections,
    occupied_step_fraction,
)
from smartscan.metrics.schemas import FROZEN_METRIC_KEYS, MetricsConfig
from smartscan.metrics.statistics import compare_runs, paired_compare
from smartscan.receiver.logs import DecisionLog, ObservationLog
from smartscan.rf.events import extract_runs
from smartscan.types import (
    SCHEMA_VERSION,
    BandPlan,
    DecisionRow,
    EventRecord,
    EventTable,
    GroundTruth,
    ObservationRow,
    Provenance,
    SmartScanError,
)


def _plan(n_bands: int) -> BandPlan:
    edges = tuple(float(i) * 1e9 for i in range(n_bands + 1))
    return BandPlan(
        band_edges_hz=edges,
        band_names=tuple(f"{i}-{i + 1}GHz" for i in range(n_bands)),
        profile_id="metrics_fixture",
        scan_span_hz=float(n_bands * 1e9),
    )


def make_truth(
    occupied: np.ndarray,
    *,
    dt_s: float = 0.001,
    threat: dict[tuple[int, int, int], float] | None = None,
    extra_events: list[EventRecord] | None = None,
) -> GroundTruth:
    occupied = np.asarray(occupied, dtype=bool)
    n_steps, n_bands = occupied.shape
    recs: list[EventRecord] = []
    weights = threat or {}
    for band in range(n_bands):
        for start, end in extract_runs(occupied[:, band]):
            recs.append(
                EventRecord(
                    event_id=f"e{band}:{start}",
                    emitter_id=f"em{band}",
                    band=band,
                    start_step=int(start),
                    end_step=int(end),
                    source="synthetic",
                    threat_weight=float(weights.get((band, start, end), 1.0)),
                )
            )
    if extra_events:
        recs.extend(extra_events)
    truth = GroundTruth(
        dt_s=dt_s,
        n_steps=n_steps,
        band_plan=_plan(n_bands),
        occupied=occupied,
        signal_power_w=np.where(occupied, 1.0, 0.0).astype(np.float32),
        events=EventTable(recs),
        provenance=Provenance(source="metrics_fixture"),
        content_fingerprint="pending",
        artifact_sha256=None,
        scenario_config={"scenario_id": "metrics_fixture"},
        seed=0,
    )
    truth.content_fingerprint = truth.compute_content_fingerprint()
    return truth


def dec(
    decision_id: str,
    *,
    start: int,
    tune_end: int,
    end: int,
    band: int,
    hit: bool,
    **kwargs: object,
) -> DecisionRow:
    payload: dict[str, object] = {
        "decision_id": decision_id,
        "start_step": start,
        "tune_end_step": tune_end,
        "dwell_end_step": end,
        "end_step": end,
        "target_band": band,
        "dwell_steps": end - tune_end,
        "hit": hit,
    }
    payload.update(kwargs)
    return DecisionRow.model_validate(payload)


def logs_from_decisions(
    truth: GroundTruth,
    decisions: list[DecisionRow],
    *,
    incomplete: int = 0,
) -> tuple[ObservationLog, DecisionLog]:
    obs_rows: list[ObservationRow] = []
    for row in decisions:
        for step in range(row.start_step, row.tune_end_step):
            obs_rows.append(
                ObservationRow(
                    step=step,
                    receiver_state="TUNING",
                    commanded_band=row.target_band,
                    tuned_band=None,
                    decision_id=row.decision_id,
                    dwell_progress=0,
                    integrated_energy=0.0,
                    measured_snr_db=None,
                    detection=False,
                )
            )
        progress = 0
        for step in range(row.tune_end_step, row.end_step):
            progress += 1
            last = step == row.end_step - 1
            obs_rows.append(
                ObservationRow(
                    step=step,
                    receiver_state="DWELLING",
                    commanded_band=row.target_band,
                    tuned_band=row.target_band,
                    decision_id=row.decision_id,
                    dwell_progress=progress,
                    integrated_energy=1.0 if last else 0.0,
                    measured_snr_db=row.measured_snr_db if last else None,
                    detection=bool(row.hit) if last else False,
                )
            )
    obs = ObservationLog(
        rows=obs_rows,
        ground_truth_fingerprint=truth.content_fingerprint,
        receiver_config_hash="fixture_rx",
        schema_version=SCHEMA_VERSION,
        dt_s=truth.dt_s,
    )
    dlog = DecisionLog(
        rows=list(decisions),
        ground_truth_fingerprint=truth.content_fingerprint,
        receiver_config_hash="fixture_rx",
        schema_version=SCHEMA_VERSION,
        dt_s=truth.dt_s,
        n_incomplete_commands=incomplete,
    )
    obs.validate()
    dlog.validate()
    return obs, dlog


def test_band_occupancy_boundaries_and_max_threat() -> None:
    occupied = np.zeros((12, 2), dtype=bool)
    occupied[0:4, 0] = True
    occupied[6:10, 0] = True
    occupied[2:8, 1] = True
    extra = EventRecord(
        event_id="overlap-hi",
        emitter_id="em0b",
        band=0,
        start_step=0,
        end_step=4,
        source="synthetic",
        threat_weight=5.0,
    )
    truth = make_truth(occupied, extra_events=[extra])
    # First constructor already put threat 1.0 on e0:0; extra overlaps with weight 5.
    events = derive_band_occupancy_events(truth)
    by_id = {event.event_id: event for event in events}
    assert by_id["boe:b0:0:4"].start_step == 0
    assert by_id["boe:b0:0:4"].end_step == 4
    assert by_id["boe:b0:6:10"].start_step == 6
    assert by_id["boe:b1:2:8"].end_step == 8
    assert by_id["boe:b0:0:4"].threat_weight == 5.0
    assert len(events) == 3


def test_one_detection_captures_at_most_one_disjoint_event() -> None:
    occupied = np.zeros((12, 1), dtype=bool)
    occupied[0:4, 0] = True
    occupied[6:10, 0] = True
    truth = make_truth(occupied)
    events = derive_band_occupancy_events(truth)
    # Usable [2, 8) overlaps both disjoint events.
    row = dec("d0", start=2, tune_end=2, end=8, band=0, hit=True)
    matches, missed, _ = match_detections(events, [row], dt_s=0.001)
    assert len(matches) == 1
    assert matches[0].event_id == "boe:b0:0:4"
    assert len(missed) == 1
    assert missed[0].event_id == "boe:b0:6:10"


def test_golden_seven_metrics() -> None:
    occupied = np.zeros((20, 2), dtype=bool)
    occupied[0:10, 0] = True
    occupied[4:8, 1] = True
    truth = make_truth(occupied)
    decisions = [
        dec("d0", start=0, tune_end=1, end=5, band=0, hit=True),  # occupied TP, matches band-0 event
        dec("d1", start=5, tune_end=5, end=9, band=1, hit=False),  # occupied miss
        dec("d2", start=9, tune_end=9, end=12, band=0, hit=False),  # occupied, event already matched
        dec("d3", start=12, tune_end=13, end=17, band=1, hit=True),  # noise-only FA
    ]
    obs, dlog = logs_from_decisions(truth, decisions)
    result = evaluate_strategy(truth, obs, dlog, metrics_config=MetricsConfig())
    m = result.report.metrics
    for key in FROZEN_METRIC_KEYS:
        assert key in m
    assert m["pd"].numerator == 1
    assert m["pd"].denominator == 3
    assert m["pd"].value == pytest.approx(1 / 3)
    assert m["pfa"].numerator == 1
    assert m["pfa"].denominator == 1
    assert m["pfa"].value == pytest.approx(1.0)
    assert m["average_intercept_rate"].numerator == 1  # band0 event matched; band1 missed
    assert m["average_intercept_rate"].denominator == pytest.approx(0.02)
    assert m["event_interception_ratio"].numerator == 1
    assert m["event_interception_ratio"].denominator == 2
    assert m["average_reward"].available is False
    assert m["correct_predictions"].available is False
    assert m["average_intercept_time_error"].available is False
    assert m["sensitivity"].available is True
    assert result.tables.support["n_true_positives"] == 1
    assert result.tables.support["n_false_alarms"] == 1
    assert len(result.tables.missed_events) == 1
    assert result.tables.missed_events[0].band == 1


def test_perfect_and_never_visit_and_all_noise_all_active_zero_event() -> None:
    occupied = np.zeros((8, 2), dtype=bool)
    occupied[0:8, 0] = True
    perfect = make_truth(occupied)
    p_dec = [dec("d0", start=0, tune_end=0, end=8, band=0, hit=True)]
    obs, dlog = logs_from_decisions(perfect, p_dec)
    p = evaluate_strategy(perfect, obs, dlog)
    assert p.report.metrics["pd"].value == 1.0
    assert p.report.metrics["event_interception_ratio"].value == 1.0
    assert p.report.metrics["pfa"].available is False

    never = [
        dec("d0", start=0, tune_end=0, end=4, band=1, hit=False),
        dec("d1", start=4, tune_end=4, end=8, band=1, hit=False),
    ]
    obs, dlog = logs_from_decisions(perfect, never)
    n = evaluate_strategy(perfect, obs, dlog)
    assert n.report.metrics["pd"].available is False
    assert n.report.metrics["event_interception_ratio"].value == 0.0
    assert n.report.metrics["pfa"].value == 0.0

    quiet = make_truth(np.zeros((8, 2), dtype=bool))
    obs, dlog = logs_from_decisions(quiet, never)
    z = evaluate_strategy(quiet, obs, dlog)
    assert z.report.metrics["event_interception_ratio"].available is False
    assert z.report.metrics["pd"].available is False
    assert z.report.metrics["pfa"].denominator == 2
    assert z.tables.support["n_band_occupancy_events"] == 0

    full = make_truth(np.ones((8, 2), dtype=bool))
    all_active_dec = [
        dec("d0", start=0, tune_end=0, end=4, band=0, hit=True),
        dec("d1", start=4, tune_end=4, end=8, band=1, hit=True),
    ]
    obs, dlog = logs_from_decisions(full, all_active_dec)
    a = evaluate_strategy(full, obs, dlog)
    assert a.report.metrics["pfa"].available is False
    assert a.report.metrics["pd"].value == 1.0


def test_incomplete_excluded_and_unrelated_band_ignored() -> None:
    occupied = np.zeros((10, 2), dtype=bool)
    occupied[:, 1] = True  # occupancy only on band 1
    occupied[0:4, 0] = True
    truth = make_truth(occupied)
    decisions = [dec("d0", start=0, tune_end=1, end=5, band=0, hit=True)]
    obs, dlog = logs_from_decisions(truth, decisions, incomplete=1)
    result = evaluate_strategy(truth, obs, dlog)
    assert result.report.metrics["incomplete_decision_count"].value == 1
    # Band-1 occupancy during a band-0 dwell does not create extra occupied decisions.
    assert result.tables.support["n_occupied_completed"] == 1
    assert result.tables.support["n_noise_only_completed"] == 0


def test_misses_affect_penalized_not_successful_mean() -> None:
    occupied = np.zeros((10, 1), dtype=bool)
    occupied[0:4, 0] = True
    occupied[6:10, 0] = True
    truth = make_truth(occupied)
    decisions = [dec("d0", start=0, tune_end=0, end=4, band=0, hit=True)]
    obs, dlog = logs_from_decisions(truth, decisions)
    result = evaluate_strategy(
        truth, obs, dlog, metrics_config=MetricsConfig(miss_penalty_horizon_s=1.0)
    )
    succ = result.report.metrics["successful_event_delay_mean_s"]
    pen = result.report.metrics["all_event_penalized_delay_s"]
    assert succ.available is True
    assert succ.denominator == 1
    assert pen.denominator == 2
    assert pen.value is not None and succ.value is not None
    assert pen.value > succ.value
    assert result.report.metrics["missed_event_count"].value == 1


def test_forecast_metrics_score_when_present_and_stay_split() -> None:
    occupied = np.zeros((12, 1), dtype=bool)
    occupied[0:6, 0] = True
    truth = make_truth(occupied)
    decisions = [
        dec(
            "d0",
            start=0,
            tune_end=0,
            end=4,
            band=0,
            hit=True,
            p_active=0.9,
            p_hit=0.8,
            time_to_next_completed_intercept_s=0.004,
            forecast_horizon_s=0.02,
        ),
        dec(
            "d1",
            start=4,
            tune_end=4,
            end=8,
            band=0,
            hit=False,
            p_active=0.1,
            p_hit=0.2,
            time_to_next_completed_intercept_s=0.050,
            forecast_horizon_s=0.01,
        ),
        dec(
            "d2",
            start=8,
            tune_end=8,
            end=12,
            band=0,
            hit=False,
            p_active=0.2,
            p_hit=0.1,
            time_to_next_completed_intercept_s=0.002,
            forecast_horizon_s=0.02,
        ),
    ]
    obs, dlog = logs_from_decisions(truth, decisions)
    result = evaluate_strategy(truth, obs, dlog)
    m = result.report.metrics
    assert m["correct_predictions"].available is True
    # d0 active+pred, d1 inactive+pred neg? d1 usable [4,8) overlaps occupied [0,6) → occupied
    # d2 usable [8,12) no occupancy → inactive, p_active 0.2 → TN
    assert m["hit_brier"].available is True
    assert m["activity_brier"].available is True
    assert m["hit_brier"].value != m["activity_brier"].value
    assert m["average_intercept_time_error"].available is True
    # d0 actual 0.004 eligible; d1 horizon 0.01 no later hit → censored; d2 no later hit
    assert m["intercept_time_forecast_coverage"].numerator == 1
    assert m["intercept_time_forecast_coverage"].denominator == 3
    assert m["intercept_time_forecast_coverage"].value == pytest.approx(1 / 3)


def test_reward_mean_when_present() -> None:
    occupied = np.zeros((6, 1), dtype=bool)
    truth = make_truth(occupied)
    decisions = [
        dec("d0", start=0, tune_end=0, end=3, band=0, hit=False, reward=1.0),
        dec("d1", start=3, tune_end=3, end=6, band=0, hit=False, reward=3.0),
    ]
    obs, dlog = logs_from_decisions(truth, decisions)
    result = evaluate_strategy(truth, obs, dlog)
    assert result.report.metrics["average_reward"].value == pytest.approx(2.0)


def test_json_roundtrip_full_precision(tmp_path: Path) -> None:
    occupied = np.zeros((8, 1), dtype=bool)
    occupied[0:4, 0] = True
    truth = make_truth(occupied)
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=True)]
    )
    result = evaluate_strategy(truth, obs, dlog)
    path = tmp_path / "metrics.json"
    save_metrics(result, path)
    loaded = load_metrics(path)
    for key, metric in result.report.metrics.items():
        other = loaded.report.metrics[key]
        assert other.available == metric.available
        if metric.value is not None:
            assert other.value == metric.value
    csv_path = tmp_path / "metrics.csv"
    save_metrics_csv(result, csv_path)
    assert csv_path.is_file()


def test_fingerprint_and_dt_mismatch_rejected() -> None:
    occupied = np.zeros((4, 1), dtype=bool)
    truth = make_truth(occupied)
    other = make_truth(np.ones((4, 1), dtype=bool))
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=False)]
    )
    with pytest.raises(SmartScanError, match="fingerprint"):
        evaluate_strategy(other, obs, dlog)
    obs.dt_s = 0.002
    with pytest.raises(SmartScanError, match="ObservationLog dt_s"):
        evaluate_strategy(truth, obs, dlog)
    obs.dt_s = truth.dt_s
    dlog.dt_s = 0.002
    with pytest.raises(SmartScanError, match="dt_s"):
        evaluate_strategy(truth, obs, dlog)


def test_evaluate_run_and_unavailable_sensitivity() -> None:
    occupied = np.zeros((4, 1), dtype=bool)
    occupied[:, 0] = True
    truth = make_truth(occupied)
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=True)]
    )
    from smartscan.metrics.engine import evaluate_run
    from smartscan.receiver.logs import ReceiverRun

    result = evaluate_run(
        truth,
        ReceiverRun(observations=obs, decisions=dlog),
        metrics_config=MetricsConfig(include_analytic_sensitivity=False),
    )
    assert result.report.metrics["sensitivity"].available is False


def test_invalid_command_band_and_schema() -> None:
    occupied = np.zeros((4, 1), dtype=bool)
    truth = make_truth(occupied)
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=False)]
    )
    dlog.rows[0] = dec("d0", start=0, tune_end=0, end=4, band=9, hit=False)
    with pytest.raises(SmartScanError, match="target_band"):
        evaluate_strategy(truth, obs, dlog)
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=False)]
    )
    obs.schema_version = "0.0.0"
    with pytest.raises(SmartScanError, match="schema"):
        evaluate_strategy(truth, obs, dlog)
    obs.schema_version = SCHEMA_VERSION
    dlog.schema_version = "0.0.0"
    with pytest.raises(SmartScanError, match="schema"):
        evaluate_strategy(truth, obs, dlog)


def test_load_metrics_missing(tmp_path: Path) -> None:
    with pytest.raises(SmartScanError, match="not found"):
        load_metrics(tmp_path / "nope.json")


def test_compare_runs_bootstraps_whole_runs() -> None:
    occupied = np.zeros((6, 1), dtype=bool)
    occupied[:, 0] = True
    truth = make_truth(occupied)
    reports = []
    for hit in (True, True, False):
        obs, dlog = logs_from_decisions(
            truth, [dec("d0", start=0, tune_end=0, end=6, band=0, hit=hit)]
        )
        reports.append(evaluate_strategy(truth, obs, dlog).report)
    summary = compare_runs(reports, metric_key="pd", seed=0)
    assert summary["n_available"] == 3
    assert summary["mean"] == pytest.approx(2 / 3)
    paired = paired_compare(reports, reports, metric_key="pd", seed=1)
    assert paired["mean_delta"] == pytest.approx(0.0)


def test_end_step_and_horizon_rejected() -> None:
    occupied = np.zeros((4, 1), dtype=bool)
    truth = make_truth(occupied)
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=False)]
    )
    dlog.rows[0] = dec("d0", start=0, tune_end=0, end=8, band=0, hit=False)
    with pytest.raises(SmartScanError, match="end_step"):
        evaluate_strategy(truth, obs, dlog)
    obs, dlog = logs_from_decisions(
        truth, [dec("d0", start=0, tune_end=0, end=4, band=0, hit=False)]
    )
    with pytest.raises(SmartScanError, match="positive"):
        evaluate_strategy(
            truth, obs, dlog, metrics_config=MetricsConfig(miss_penalty_horizon_s=0.0)
        )


def test_remaining_engine_branches() -> None:
    occupied = np.zeros((10, 1), dtype=bool)
    occupied[0:8, 0] = True
    truth = make_truth(occupied)
    decisions = [
        dec("d0", start=0, tune_end=0, end=2, band=0, hit=True, measured_snr_db=-3.0),
        dec("d1", start=2, tune_end=2, end=4, band=0, hit=True, measured_snr_db=5.0),
        dec("d2", start=4, tune_end=4, end=6, band=0, hit=True, measured_snr_db=12.0),
        dec(
            "d3",
            start=6,
            tune_end=6,
            end=10,
            band=0,
            hit=False,
            time_to_next_completed_intercept_s=0.1,
        ),
    ]
    obs, dlog = logs_from_decisions(truth, decisions)
    result = evaluate_strategy(truth, obs, dlog)
    bins = {item.snr_bin for item in result.tables.pd_strata}
    assert "<0dB" in bins and "[0,10)dB" in bins and ">=10dB" in bins
    dlog.ground_truth_fingerprint = "nope"
    with pytest.raises(SmartScanError, match="DecisionLog fingerprint"):
        evaluate_strategy(truth, obs, dlog)

    from smartscan.metrics.engine import (
        ensure_frozen_keys,
        support_get_eligible,
        support_get_forecast_count,
    )
    from smartscan.metrics.schemas import CensoringSummary, EvaluationResult, MetricsTables
    from smartscan.types import MetricsReport

    empty = EvaluationResult(
        report=MetricsReport(metrics={}),
        tables=MetricsTables(),
        censoring=CensoringSummary(miss_penalty_horizon_s=1.0),
        content_fingerprint="x",
    )
    with pytest.raises(SmartScanError, match="missing frozen"):
        ensure_frozen_keys(empty)
    assert support_get_forecast_count({}) == 0.0
    assert support_get_eligible({}) == 0.0


def test_matching_edge_intervals() -> None:
    occupied = np.zeros((8, 1), dtype=bool)
    occupied[2:4, 0] = True
    truth = make_truth(occupied)
    empty_dwell = DecisionRow.model_construct(
        decision_id="empty",
        start_step=0,
        tune_end_step=3,
        dwell_end_step=3,
        end_step=3,
        target_band=0,
        dwell_steps=1,
        hit=False,
    )
    late = DecisionRow.model_construct(
        decision_id="late",
        start_step=10,
        tune_end_step=10,
        dwell_end_step=12,
        end_step=12,
        target_band=0,
        dwell_steps=2,
        hit=False,
    )
    assert dwell_occupied(truth, empty_dwell) is False
    assert occupied_step_fraction(truth, empty_dwell) == 0.0
    assert dwell_occupied(truth, late) is False
    events = derive_band_occupancy_events(truth)
    fa = dec("fa", start=5, tune_end=5, end=8, band=0, hit=True)
    matches, missed, _ = match_detections(events, [fa], dt_s=0.001)
    assert matches == []
    assert missed[0].nearest_gap_steps is not None
    assert missed[0].nearest_gap_steps >= 1
