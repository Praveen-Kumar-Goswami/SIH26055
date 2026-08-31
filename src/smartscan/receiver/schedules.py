"""Open-loop schedules. They never read GroundTruth occupancy or emitter IDs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from smartscan.seeding import spawn_generator
from smartscan.types import ScanCommand, SmartScanError


@dataclass(frozen=True)
class ScheduleView:
    """Policy-visible inputs at a decision boundary.

    Last-command outcome fields are optional so Stage 2 open-loop schedules
    keep working unchanged. Adaptive Stage 5 policies may read them; they
    still must not read GroundTruth occupancy.
    """

    step: int
    n_steps: int
    n_bands: int
    settled_band: int | None
    last_target_band: int | None
    dwell_bins: tuple[int, ...]
    default_dwell_steps: int
    decision_index: int
    last_hit: bool | None = None
    last_measured_snr_db: float | None = None
    last_dwell_steps: int | None = None
    last_tune_cost_steps: int | None = None
    last_start_step: int | None = None
    last_end_step: int | None = None
    last_decision_id: str | None = None
    dt_s: float = 0.001


class Schedule(Protocol):
    def next_command(self, view: ScheduleView) -> ScanCommand:
        """Return the next band+dwell command. Must not read oracle truth."""


class SequentialSchedule:
    """Cycle bands 0..K-1 with a fixed dwell."""

    def __init__(self, dwell_steps: int) -> None:
        if dwell_steps <= 0:
            raise SmartScanError("SequentialSchedule dwell_steps must be positive.")
        self.dwell_steps = int(dwell_steps)

    def next_command(self, view: ScheduleView) -> ScanCommand:
        _validate_view(view)
        if view.last_target_band is None:
            band = 0
        else:
            band = (view.last_target_band + 1) % view.n_bands
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=self.dwell_steps,
        )


class UniformRandomSchedule:
    """Uniform random band and dwell bin. Uses only its own RNG."""

    def __init__(self, seed: int) -> None:
        self._rng = spawn_generator(seed)
        self.seed = int(seed)

    def next_command(self, view: ScheduleView) -> ScanCommand:
        _validate_view(view)
        if not view.dwell_bins:
            raise SmartScanError("UniformRandomSchedule requires nonempty dwell_bins.")
        band = int(self._rng.integers(0, view.n_bands))
        dwell = int(self._rng.choice(np.asarray(view.dwell_bins, dtype=np.int64)))
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=band,
            dwell_steps=dwell,
        )


class FixedPrioritySchedule:
    """Cycle a caller-supplied public band list. Never reads activity truth."""

    def __init__(self, band_order: tuple[int, ...], dwell_steps: int) -> None:
        if not band_order:
            raise SmartScanError("FixedPrioritySchedule requires a nonempty public band list.")
        if dwell_steps <= 0:
            raise SmartScanError("FixedPrioritySchedule dwell_steps must be positive.")
        self.band_order = tuple(int(b) for b in band_order)
        self.dwell_steps = int(dwell_steps)

    def next_command(self, view: ScheduleView) -> ScanCommand:
        _validate_view(view)
        for band in self.band_order:
            if band < 0 or band >= view.n_bands:
                raise SmartScanError(
                    f"Fixed-priority band {band} is outside 0..{view.n_bands - 1}."
                )
        index = view.decision_index % len(self.band_order)
        return ScanCommand(
            decision_id=f"d{view.decision_index:05d}",
            target_band=self.band_order[index],
            dwell_steps=self.dwell_steps,
        )


def make_schedule(
    strategy: str,
    *,
    dwell_steps: int,
    schedule_seed: int = 0,
    band_order: tuple[int, ...] | None = None,
) -> Schedule:
    name = strategy.strip().lower().replace("_", "-")
    if name in {"sequential", "seq"}:
        return SequentialSchedule(dwell_steps=dwell_steps)
    if name in {"random", "uniform-random", "uniform"}:
        return UniformRandomSchedule(seed=schedule_seed)
    if name in {"fixed-priority", "fixed", "priority"}:
        if not band_order:
            raise SmartScanError(
                "fixed-priority strategy requires a public --priority band list."
            )
        return FixedPrioritySchedule(band_order=band_order, dwell_steps=dwell_steps)
    raise SmartScanError(
        f"Unknown strategy {strategy!r}. Stage 2 open-loop make_schedule supports "
        "sequential, random, and fixed-priority. Use make_policy for reactive, "
        "contextual-thompson, periodic-intercept, or ppo."
    )


def _validate_view(view: ScheduleView) -> None:
    if view.n_bands <= 0:
        raise SmartScanError("ScheduleView.n_bands must be positive.")
    if view.default_dwell_steps <= 0:
        raise SmartScanError("default_dwell_steps must be positive.")
