"""Maximal half-open emitter-band illumination events."""

from __future__ import annotations

import numpy as np

from smartscan.rf.emitters import Emitter
from smartscan.types import EventRecord, EventTable


def extract_runs(active: np.ndarray) -> list[tuple[int, int]]:
    """Return maximal True runs as half-open ``[start, end)``."""

    if active.size == 0:
        return []
    padded = np.diff(active.astype(np.int8), prepend=0, append=0)
    starts = np.flatnonzero(padded == 1)
    ends = np.flatnonzero(padded == -1)
    return [(int(start), int(end)) for start, end in zip(starts, ends, strict=True)]


def events_from_occupancy(
    *,
    emitter: Emitter,
    occupied: np.ndarray,
    n_steps: int,
) -> list[EventRecord]:
    records: list[EventRecord] = []
    n_bands = occupied.shape[1]
    for band in range(n_bands):
        for start, end in extract_runs(occupied[:n_steps, band]):
            records.append(
                EventRecord(
                    event_id=f"{emitter.emitter_id}:b{band}:{start}",
                    emitter_id=emitter.emitter_id,
                    band=band,
                    start_step=start,
                    end_step=end,
                    source=emitter.source,
                    threat_weight=emitter.threat_weight,
                )
            )
    return records


def combine_events(groups: list[list[EventRecord]]) -> EventTable:
    flat = [record for group in groups for record in group]
    return EventTable(flat)
