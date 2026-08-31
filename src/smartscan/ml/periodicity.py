"""Period and next-illumination estimates from irregular observed hits only."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from smartscan.types import SmartScanError

MIN_HITS_FOR_PERIOD = 3


@dataclass
class PeriodicityEstimator:
    """Weighted interval/autocorrelation period from hit timestamps.

    Unobserved gaps are ignored: only actual hit times enter the estimator.
    """

    dt_s: float
    max_period_s: float = 2.0
    hit_times_s: dict[int, list[float]] = field(default_factory=dict)

    def observe_hit(self, band: int, time_s: float) -> None:
        if time_s < 0 or not np.isfinite(time_s):
            raise SmartScanError(f"Hit time must be finite and nonnegative, got {time_s}.")
        self.hit_times_s.setdefault(int(band), []).append(float(time_s))

    def snapshot(self) -> PeriodicityEstimator:
        copied = PeriodicityEstimator(dt_s=self.dt_s, max_period_s=self.max_period_s)
        copied.hit_times_s = {band: list(times) for band, times in self.hit_times_s.items()}
        return copied

    def estimate(self, band: int, now_s: float) -> tuple[float, float, float]:
        """Return ``(period_s, phase_to_next_s, confidence)``. Unknown → (0, 0, 0)."""

        times = self.hit_times_s.get(int(band), [])
        if len(times) < MIN_HITS_FOR_PERIOD:
            return 0.0, 0.0, 0.0
        arr = np.asarray(times, dtype=np.float64)
        arr = np.sort(arr)
        intervals = np.diff(arr)
        intervals = intervals[np.isfinite(intervals) & (intervals > 1e-9)]
        if intervals.size == 0:
            return 0.0, 0.0, 0.0
        period = float(np.median(intervals))
        if period <= 0.0 or period > self.max_period_s:
            # Autocorrelation fallback on a coarse histogram of hit times.
            period = self._autocorr_period(arr)
            if period <= 0.0:
                return 0.0, 0.0, 0.0
        last = float(arr[-1])
        k = np.ceil((now_s - last) / period)
        next_time = last + max(1.0, k) * period
        if next_time < now_s:
            next_time = now_s
        phase = float(next_time - now_s)
        rel = float(np.std(intervals) / max(period, 1e-9))
        confidence = float(np.clip(1.0 / (1.0 + rel), 0.0, 1.0))
        n_bonus = min(len(times), 12) / 12.0
        confidence *= float(n_bonus)
        return float(period), float(phase), float(np.clip(confidence, 0.0, 1.0))

    def _autocorr_period(self, times: np.ndarray) -> float:
        span = float(times[-1] - times[0])
        if span <= 0.0:
            return 0.0
        n_bins = min(64, max(8, int(span / max(self.dt_s, 1e-6))))
        hist, _edges = np.histogram(times, bins=n_bins, range=(float(times[0]), float(times[-1])))
        centered = hist.astype(np.float64) - float(np.mean(hist))
        if float(np.dot(centered, centered)) <= 0.0:
            return 0.0
        corr = np.correlate(centered, centered, mode="full")
        mid = corr.size // 2
        right = corr[mid + 1 :]
        if right.size < 2:
            return 0.0
        lag = int(np.argmax(right)) + 1
        bin_s = span / float(n_bins)
        period = float(lag) * bin_s
        if period <= 0.0 or period > self.max_period_s:
            return 0.0
        return period
