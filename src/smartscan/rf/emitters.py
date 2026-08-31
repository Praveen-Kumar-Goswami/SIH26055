"""Four public emitter classes plus a composable on/off gate."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from smartscan.config import duration_to_steps
from smartscan.rf.bands import frequency_to_band
from smartscan.types import BandPlan, SmartScanError

EmitterKind = Literal["continuous", "circular_scan", "sector_scan", "frequency_agile"]


def wrap_free_angular_distance_deg(a_deg: float | np.ndarray, b_deg: float) -> float | np.ndarray:
    """Smallest unsigned angular distance on the circle."""

    delta = np.abs(np.asarray(a_deg, dtype=np.float64) - b_deg) % 360.0
    dist = np.minimum(delta, 360.0 - delta)
    if np.ndim(dist) == 0:
        return float(dist)
    return dist


class OnOffGate(BaseModel):
    """Reusable on/off gate. Not a fifth public emitter type."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["always", "periodic", "windows"] = "always"
    period_steps: int | None = None
    on_steps: int | None = None
    phase_offset: int = 0
    windows: tuple[tuple[int, int], ...] | None = None

    @model_validator(mode="after")
    def _validate(self) -> OnOffGate:
        if self.kind == "periodic":
            if self.period_steps is None or self.on_steps is None:
                raise SmartScanError("periodic OnOffGate requires period_steps and on_steps.")
            if self.period_steps <= 0 or self.on_steps < 0 or self.on_steps > self.period_steps:
                raise SmartScanError("periodic OnOffGate has invalid period/on_steps.")
        if self.kind == "windows":
            if not self.windows:
                raise SmartScanError("windows OnOffGate requires at least one [start, end) window.")
            for start, end in self.windows:
                if end <= start:
                    raise SmartScanError(f"Invalid gate window [{start}, {end}).")
        return self

    def mask(self, n_steps: int) -> np.ndarray:
        if self.kind == "always":
            return np.ones(n_steps, dtype=bool)
        if self.kind == "periodic":
            assert self.period_steps is not None and self.on_steps is not None
            steps = np.arange(n_steps, dtype=np.int64)
            return ((steps + self.phase_offset) % self.period_steps) < self.on_steps
        mask = np.zeros(n_steps, dtype=bool)
        assert self.windows is not None
        for start, end in self.windows:
            lo = max(0, start)
            hi = min(n_steps, end)
            if hi > lo:
                mask[lo:hi] = True
        return mask


class Emitter(BaseModel, ABC):
    """Shared emitter fields. Oracle ``threat_weight`` is evaluator-only."""

    model_config = ConfigDict(extra="forbid")

    emitter_id: str
    power_w: float
    gate: OnOffGate = Field(default_factory=OnOffGate)
    start_step: int = 0
    end_step: int | None = None
    threat_weight: float | None = None
    source: str = "synthetic"

    @model_validator(mode="after")
    def _validate_power(self) -> Emitter:
        if not np.isfinite(self.power_w) or self.power_w < 0:
            raise SmartScanError(
                f"Emitter {self.emitter_id} power_w must be finite and nonnegative."
            )
        if not self.emitter_id:
            raise SmartScanError("emitter_id must be nonempty.")
        if self.start_step < 0:
            raise SmartScanError(f"Emitter {self.emitter_id} start_step must be >= 0.")
        if self.end_step is not None and self.end_step <= self.start_step:
            raise SmartScanError(f"Emitter {self.emitter_id} has empty [start_step, end_step).")
        if self.threat_weight is not None and (
            not np.isfinite(self.threat_weight) or self.threat_weight < 0
        ):
            raise SmartScanError(f"Emitter {self.emitter_id} threat_weight is invalid.")
        return self

    def active_mask(self, n_steps: int) -> np.ndarray:
        mask = self.gate.mask(n_steps)
        if self.start_step > 0:
            mask[: self.start_step] = False
        if self.end_step is not None:
            mask[self.end_step :] = False
        return mask

    @abstractmethod
    def kind(self) -> EmitterKind:
        raise NotImplementedError

    @abstractmethod
    def render(
        self, n_steps: int, band_plan: BandPlan, dt_s: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return occupied[N,K] and power[N,K] for this emitter only."""


class ContinuousEmitter(Emitter):
    frequency_hz: float

    def kind(self) -> EmitterKind:
        return "continuous"

    def render(
        self, n_steps: int, band_plan: BandPlan, dt_s: float
    ) -> tuple[np.ndarray, np.ndarray]:
        del dt_s
        band = frequency_to_band(self.frequency_hz, band_plan)
        occupied = np.zeros((n_steps, band_plan.n_bands), dtype=bool)
        power = np.zeros((n_steps, band_plan.n_bands), dtype=np.float32)
        active = self.active_mask(n_steps)
        occupied[active, band] = True
        power[active, band] = np.float32(self.power_w)
        return occupied, power


class CircularScanEmitter(Emitter):
    """Rotating beam. Illumination uses integer phase bins over one scan period."""

    frequency_hz: float
    scan_period_s: float
    beamwidth_deg: float
    receiver_azimuth_deg: float = 0.0
    phase0_steps: int = 0

    def kind(self) -> EmitterKind:
        return "circular_scan"

    def period_steps(self, dt_s: float) -> int:
        return duration_to_steps(self.scan_period_s, dt_s)

    def illuminated_bins(self, dt_s: float) -> np.ndarray:
        period_steps = self.period_steps(dt_s)
        n_illum = int(round((self.beamwidth_deg / 360.0) * period_steps))
        n_illum = int(np.clip(n_illum, 0, period_steps))
        look_bin = int(round((self.receiver_azimuth_deg % 360.0) / 360.0 * period_steps)) % period_steps
        offsets = np.arange(n_illum, dtype=np.int64) - (n_illum // 2)
        return np.unique((look_bin + offsets) % period_steps)

    def render(
        self, n_steps: int, band_plan: BandPlan, dt_s: float
    ) -> tuple[np.ndarray, np.ndarray]:
        if not np.isfinite(self.beamwidth_deg) or self.beamwidth_deg < 0 or self.beamwidth_deg > 360:
            raise SmartScanError(
                f"Emitter {self.emitter_id} beamwidth_deg must be in [0, 360]."
            )
        band = frequency_to_band(self.frequency_hz, band_plan)
        period_steps = self.period_steps(dt_s)
        illum = self.illuminated_bins(dt_s)
        steps = np.arange(n_steps, dtype=np.int64)
        phase = (self.phase0_steps + steps) % period_steps
        lit = np.isin(phase, illum) & self.active_mask(n_steps)
        occupied = np.zeros((n_steps, band_plan.n_bands), dtype=bool)
        power = np.zeros((n_steps, band_plan.n_bands), dtype=np.float32)
        occupied[lit, band] = True
        power[lit, band] = np.float32(self.power_w)
        return occupied, power


class SectorScanEmitter(Emitter):
    """Deterministic triangular sweep over ``[theta_min, theta_max]``."""

    frequency_hz: float
    scan_period_s: float
    theta_min_deg: float
    theta_max_deg: float
    beamwidth_deg: float
    receiver_azimuth_deg: float = 0.0
    phase0_steps: int = 0
    initial_direction: Literal[-1, 1] = 1

    def kind(self) -> EmitterKind:
        return "sector_scan"

    @model_validator(mode="after")
    def _validate_sector(self) -> SectorScanEmitter:
        if self.theta_max_deg == self.theta_min_deg:
            raise SmartScanError(f"Emitter {self.emitter_id} sector span is zero.")
        return self

    def pointing_deg(self, n_steps: int, dt_s: float) -> np.ndarray:
        period_steps = duration_to_steps(self.scan_period_s, dt_s)
        steps = np.arange(n_steps, dtype=np.int64)
        phase = (self.phase0_steps + steps) % period_steps
        frac = phase.astype(np.float64) / float(period_steps)
        if self.initial_direction < 0:
            frac = (frac + 0.5) % 1.0
        # Triangle 0 -> 1 -> 0 including endpoints.
        alpha = np.where(frac <= 0.5, 2.0 * frac, 2.0 - 2.0 * frac)
        span = self.theta_max_deg - self.theta_min_deg
        return self.theta_min_deg + alpha * span

    def render(
        self, n_steps: int, band_plan: BandPlan, dt_s: float
    ) -> tuple[np.ndarray, np.ndarray]:
        if not np.isfinite(self.beamwidth_deg) or self.beamwidth_deg < 0:
            raise SmartScanError(f"Emitter {self.emitter_id} beamwidth_deg is invalid.")
        band = frequency_to_band(self.frequency_hz, band_plan)
        pointing = self.pointing_deg(n_steps, dt_s)
        half = 0.5 * self.beamwidth_deg
        dist = np.asarray(wrap_free_angular_distance_deg(pointing, self.receiver_azimuth_deg), dtype=np.float64)
        lit = (dist <= half + 1e-12) & self.active_mask(n_steps)
        occupied = np.zeros((n_steps, band_plan.n_bands), dtype=bool)
        power = np.zeros((n_steps, band_plan.n_bands), dtype=np.float32)
        occupied[lit, band] = True
        power[lit, band] = np.float32(self.power_w)
        return occupied, power


class FrequencyAgileEmitter(Emitter):
    """Hop sequence: ``hop_bands[(phase_offset + n // dwell_steps) mod L]``."""

    hop_frequencies_hz: tuple[float, ...]
    dwell_steps: int
    phase_offset: int = 0

    def kind(self) -> EmitterKind:
        return "frequency_agile"

    @model_validator(mode="after")
    def _validate_hops(self) -> FrequencyAgileEmitter:
        if self.dwell_steps <= 0:
            raise SmartScanError(f"Emitter {self.emitter_id} dwell_steps must be positive.")
        if not self.hop_frequencies_hz:
            raise SmartScanError(f"Emitter {self.emitter_id} hop sequence is empty.")
        return self

    def hop_bands(self, band_plan: BandPlan) -> np.ndarray:
        return np.array(
            [frequency_to_band(freq, band_plan) for freq in self.hop_frequencies_hz],
            dtype=np.int64,
        )

    def render(
        self, n_steps: int, band_plan: BandPlan, dt_s: float
    ) -> tuple[np.ndarray, np.ndarray]:
        del dt_s
        hops = self.hop_bands(band_plan)
        length = hops.size
        steps = np.arange(n_steps, dtype=np.int64)
        hop_index = (self.phase_offset + steps // self.dwell_steps) % length
        bands = hops[hop_index]
        active = self.active_mask(n_steps)
        occupied = np.zeros((n_steps, band_plan.n_bands), dtype=bool)
        power = np.zeros((n_steps, band_plan.n_bands), dtype=np.float32)
        if np.any(active):
            occupied[steps[active], bands[active]] = True
            power[steps[active], bands[active]] = np.float32(self.power_w)
        return occupied, power


def emitter_from_dict(payload: dict[str, Any]) -> Emitter:
    kind = payload.get("kind")
    data = {key: value for key, value in payload.items() if key != "kind"}
    if "gate" in data and isinstance(data["gate"], dict):
        data["gate"] = OnOffGate.model_validate(data["gate"])
    if kind == "continuous":
        return ContinuousEmitter.model_validate(data)
    if kind == "circular_scan":
        return CircularScanEmitter.model_validate(data)
    if kind == "sector_scan":
        return SectorScanEmitter.model_validate(data)
    if kind == "frequency_agile":
        if "hop_frequencies_hz" in data:
            data["hop_frequencies_hz"] = tuple(data["hop_frequencies_hz"])
        return FrequencyAgileEmitter.model_validate(data)
    raise SmartScanError(f"Unknown emitter kind {kind!r}.")
