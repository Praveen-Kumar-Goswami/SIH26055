"""Band-occupancy events and one-to-one detection matching."""

from __future__ import annotations

from smartscan.metrics.schemas import BandOccupancyEvent, MatchRecord, MissedEventRecord
from smartscan.rf.events import extract_runs
from smartscan.types import DecisionRow, GroundTruth


def intervals_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    """Half-open [a0, a1) overlaps [b0, b1)."""

    return a0 < b1 and b0 < a1


def usable_interval(row: DecisionRow) -> tuple[int, int]:
    return int(row.tune_end_step), int(row.end_step)


def dwell_occupied(truth: GroundTruth, row: DecisionRow) -> bool:
    start, end = usable_interval(row)
    if end <= start:
        return False
    start = max(0, start)
    end = min(truth.n_steps, end)
    if end <= start:
        return False
    band = int(row.target_band)
    return bool(truth.occupied[start:end, band].any())


def occupied_step_fraction(truth: GroundTruth, row: DecisionRow) -> float:
    start, end = usable_interval(row)
    start = max(0, start)
    end = min(truth.n_steps, end)
    length = end - start
    if length <= 0:
        return 0.0
    return float(np_sum_occupied(truth, start, end, int(row.target_band))) / float(length)


def np_sum_occupied(truth: GroundTruth, start: int, end: int, band: int) -> int:
    return int(truth.occupied[start:end, band].sum())


def derive_band_occupancy_events(truth: GroundTruth) -> list[BandOccupancyEvent]:
    """Maximal contiguous occupancy per band. Official capture units."""

    emitter_records = truth.events.records()
    events: list[BandOccupancyEvent] = []
    n_bands = truth.band_plan.n_bands
    for band in range(n_bands):
        for start, end in extract_runs(truth.occupied[:, band]):
            weights: list[float] = []
            for record in emitter_records:
                if int(record.band) != band:
                    continue
                if intervals_overlap(start, end, int(record.start_step), int(record.end_step)):
                    weight = 1.0 if record.threat_weight is None else float(record.threat_weight)
                    weights.append(weight)
            events.append(
                BandOccupancyEvent(
                    event_id=f"boe:b{band}:{start}:{end}",
                    band=band,
                    start_step=int(start),
                    end_step=int(end),
                    threat_weight=max(weights) if weights else 1.0,
                )
            )
    return events


def match_detections(
    events: list[BandOccupancyEvent],
    decisions: list[DecisionRow],
    *,
    dt_s: float,
) -> tuple[list[MatchRecord], list[MissedEventRecord], set[str]]:
    """One-to-one matches within each band.

    Detections are considered in detection-time order. Each hit may capture at
    most one event, choosing the earliest-start overlapping unmatched event.
    """

    by_band_events: dict[int, list[BandOccupancyEvent]] = {}
    for event in events:
        by_band_events.setdefault(event.band, []).append(event)
    for bucket in by_band_events.values():
        bucket.sort(key=lambda item: (item.start_step, item.end_step, item.event_id))

    hits = [row for row in decisions if row.hit]
    hits.sort(key=lambda row: (row.end_step, row.start_step, row.decision_id))

    used_events: set[str] = set()
    matched_decisions: set[str] = set()
    matches: list[MatchRecord] = []

    for row in hits:
        candidates = by_band_events.get(int(row.target_band), [])
        u0, u1 = usable_interval(row)
        chosen: BandOccupancyEvent | None = None
        for event in candidates:
            if event.event_id in used_events:
                continue
            if intervals_overlap(u0, u1, event.start_step, event.end_step):
                chosen = event
                break
        if chosen is None:
            continue
        used_events.add(chosen.event_id)
        matched_decisions.add(row.decision_id)
        delay_s = float(row.end_step - chosen.start_step) * float(dt_s)
        matches.append(
            MatchRecord(
                event_id=chosen.event_id,
                decision_id=row.decision_id,
                band=chosen.band,
                event_start_step=chosen.start_step,
                event_end_step=chosen.end_step,
                detection_end_step=int(row.end_step),
                delay_s=delay_s,
                threat_weight=float(chosen.threat_weight),
            )
        )

    missed: list[MissedEventRecord] = []
    for event in events:
        if event.event_id in used_events:
            continue
        nearest_id, nearest_start, nearest_gap = _nearest_visit(event, decisions)
        missed.append(
            MissedEventRecord(
                event_id=event.event_id,
                band=event.band,
                start_step=event.start_step,
                end_step=event.end_step,
                duration_s=float(event.end_step - event.start_step) * float(dt_s),
                nearest_decision_id=nearest_id,
                nearest_visit_start_step=nearest_start,
                nearest_gap_steps=nearest_gap,
            )
        )
    return matches, missed, matched_decisions


def _nearest_visit(
    event: BandOccupancyEvent,
    decisions: list[DecisionRow],
) -> tuple[str | None, int | None, int | None]:
    best: tuple[int, int, str] | None = None
    for row in decisions:
        if int(row.target_band) != event.band:
            continue
        u0, u1 = usable_interval(row)
        if intervals_overlap(u0, u1, event.start_step, event.end_step):
            gap = 0
        elif u1 <= event.start_step:
            gap = event.start_step - u1
        else:
            gap = u0 - event.end_step
        candidate = (gap, int(row.end_step), row.decision_id)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return None, None, None
    gap, _, decision_id = best
    visit = next(row for row in decisions if row.decision_id == decision_id)
    return decision_id, int(visit.start_step), int(gap)
