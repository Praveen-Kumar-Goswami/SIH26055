"""Agility, novelty, and public-catalog threat from observable hits only."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class AgilityEstimator:
    """Smoothed hop-transition matrix from temporally adjacent observed hits."""

    n_bands: int
    prior: float = 0.1
    counts: np.ndarray = field(init=False)
    last_hit_band: int | None = None

    def __post_init__(self) -> None:
        n = int(self.n_bands)
        self.counts = np.full((n, n), float(self.prior), dtype=np.float64)

    def observe_hit(self, band: int) -> None:
        band_i = int(band)
        if self.last_hit_band is not None and 0 <= self.last_hit_band < self.n_bands:
            if 0 <= band_i < self.n_bands:
                self.counts[self.last_hit_band, band_i] += 1.0
        self.last_hit_band = band_i

    def next_scores(self) -> np.ndarray:
        row_sums = np.sum(self.counts, axis=1, keepdims=True)
        probs = self.counts / np.maximum(row_sums, 1e-12)
        if self.last_hit_band is None:
            return np.full(self.n_bands, 1.0 / float(self.n_bands), dtype=np.float64)
        row = np.asarray(probs[int(self.last_hit_band)], dtype=np.float64)
        return row.copy()

    def snapshot(self) -> AgilityEstimator:
        out = AgilityEstimator(n_bands=self.n_bands, prior=self.prior)
        out.counts = self.counts.copy()
        out.last_hit_band = self.last_hit_band
        return out


@dataclass
class NoveltyEstimator:
    """Bounded novelty from unexpected band / timing / SNR. Unknown is not hostile."""

    n_bands: int
    window: int = 32
    hit_bands: list[int] = field(default_factory=list)
    snrs: list[float] = field(default_factory=list)
    intervals_s: list[float] = field(default_factory=list)
    last_hit_time_s: float | None = None

    def observe(self, *, band: int, hit: bool, time_s: float, snr_db: float | None) -> None:
        if not hit:
            return
        self.hit_bands.append(int(band))
        if snr_db is not None and np.isfinite(snr_db):
            self.snrs.append(float(snr_db))
        if self.last_hit_time_s is not None:
            self.intervals_s.append(float(time_s) - float(self.last_hit_time_s))
        self.last_hit_time_s = float(time_s)
        self.hit_bands = self.hit_bands[-self.window :]
        self.snrs = self.snrs[-self.window :]
        self.intervals_s = self.intervals_s[-self.window :]

    def score(self, *, band: int, snr_db: float | None, time_s: float) -> float:
        if not self.hit_bands:
            return 0.5
        band_i = int(band)
        freq = float(sum(1 for item in self.hit_bands if item == band_i)) / float(len(self.hit_bands))
        band_surprise = float(np.clip(1.0 - freq, 0.0, 1.0))
        snr_surprise = 0.0
        if snr_db is not None and len(self.snrs) >= 4:
            med = float(np.median(self.snrs))
            mad = float(np.median(np.abs(np.asarray(self.snrs) - med))) + 1e-6
            z = abs(float(snr_db) - med) / (1.4826 * mad)
            snr_surprise = float(np.clip(z / 6.0, 0.0, 1.0))
        timing_surprise = 0.0
        if self.last_hit_time_s is not None and len(self.intervals_s) >= 4:
            gap = float(time_s) - float(self.last_hit_time_s)
            med_g = float(np.median(self.intervals_s))
            mad_g = float(np.median(np.abs(np.asarray(self.intervals_s) - med_g))) + 1e-6
            z_t = abs(gap - med_g) / (1.4826 * mad_g)
            timing_surprise = float(np.clip(z_t / 6.0, 0.0, 1.0))
        raw = 0.5 * band_surprise + 0.25 * snr_surprise + 0.25 * timing_surprise
        return float(np.clip(raw, 0.0, 1.0))

    def snapshot(self) -> NoveltyEstimator:
        out = NoveltyEstimator(n_bands=self.n_bands, window=self.window)
        out.hit_bands = list(self.hit_bands)
        out.snrs = list(self.snrs)
        out.intervals_s = list(self.intervals_s)
        out.last_hit_time_s = self.last_hit_time_s
        return out


def assess_threat(
    *,
    public_catalog_priority: float | None,
    novelty: float,
    default: float = 1.0,
) -> float:
    """Public catalog match plus novelty. Hidden simulator labels are never used.

    Unknown catalog match stays at the neutral default of 1.0.
    """

    if public_catalog_priority is None:
        catalog = float(default)
    else:
        catalog = float(np.clip(public_catalog_priority, 0.0, 10.0))
    mixed = 0.8 * catalog + 0.2 * (default + novelty)
    return float(np.clip(mixed, 0.0, 10.0))
