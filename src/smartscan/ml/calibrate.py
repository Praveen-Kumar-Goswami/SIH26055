"""Isotonic and identity calibrators. Fit on validation only, never the held-out test split."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from smartscan.types import SmartScanError


def _pav_isotonic(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Nondecreasing PAV fit. ``x`` must be sorted."""

    n = int(x.size)
    if n == 0:
        raise SmartScanError("Calibrator requires at least one validation pair.")
    weights = np.ones(n, dtype=np.float64)
    values = y.astype(np.float64).copy()
    blocks = [[i] for i in range(n)]
    i = 0
    while i < len(blocks) - 1:
        a = blocks[i]
        b = blocks[i + 1]
        mean_a = float(np.average(values[a], weights=weights[a]))
        mean_b = float(np.average(values[b], weights=weights[b]))
        if mean_a <= mean_b + 1e-15:
            i += 1
            continue
        merged = a + b
        blocks[i] = merged
        del blocks[i + 1]
        if i:
            i -= 1
    fitted = np.empty(n, dtype=np.float64)
    for block in blocks:
        fitted[block] = float(np.average(values[block], weights=weights[block]))
    return x, np.clip(fitted, 0.0, 1.0)


@dataclass
class IsotonicCalibrator:
    x: np.ndarray
    y_fit: np.ndarray

    def predict(self, p: np.ndarray | float) -> np.ndarray:
        raw = np.asarray(p, dtype=np.float64).reshape(-1)
        raw = np.clip(raw, 0.0, 1.0)
        if self.x.size == 0:
            return raw.astype(np.float64)
        out = np.interp(raw, self.x, self.y_fit, left=float(self.y_fit[0]), right=float(self.y_fit[-1]))
        clipped: np.ndarray = np.clip(np.asarray(out, dtype=np.float64), 0.0, 1.0)
        return clipped

    def predict_one(self, p: float) -> float:
        return float(self.predict(p)[0])

    def state_dict(self) -> dict[str, list[float]]:
        return {"x": self.x.tolist(), "y_fit": self.y_fit.tolist()}

    @classmethod
    def from_state(cls, payload: dict[str, object]) -> IsotonicCalibrator:
        return cls(
            x=np.asarray(payload["x"], dtype=np.float64),
            y_fit=np.asarray(payload["y_fit"], dtype=np.float64),
        )

    @classmethod
    def identity(cls) -> IsotonicCalibrator:
        return cls(x=np.asarray([0.0, 1.0]), y_fit=np.asarray([0.0, 1.0]))

    @classmethod
    def fit(cls, probabilities: np.ndarray, labels: np.ndarray) -> IsotonicCalibrator:
        p = np.asarray(probabilities, dtype=np.float64).reshape(-1)
        y = np.asarray(labels, dtype=np.float64).reshape(-1)
        if p.size != y.size or p.size == 0:
            return cls.identity()
        order = np.argsort(p, kind="mergesort")
        x_sorted = p[order]
        y_sorted = y[order]
        # Collapse duplicate x
        uniq_x: list[float] = []
        uniq_y: list[float] = []
        i = 0
        n = int(x_sorted.size)
        while i < n:
            j = i + 1
            while j < n and float(x_sorted[j]) == float(x_sorted[i]):
                j += 1
            uniq_x.append(float(x_sorted[i]))
            uniq_y.append(float(np.mean(y_sorted[i:j])))
            i = j
        xs, ys = _pav_isotonic(np.asarray(uniq_x), np.asarray(uniq_y))
        return cls(x=xs, y_fit=ys)


def brier_score(probabilities: np.ndarray, labels: np.ndarray) -> float:
    p = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    y = np.asarray(labels, dtype=np.float64).reshape(-1)
    if p.size == 0 or p.size != y.size:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def expected_calibration_error(
    probabilities: np.ndarray,
    labels: np.ndarray,
    *,
    n_bins: int = 10,
) -> float:
    """Uniform-bin ECE. Returns 0 on empty input."""

    p = np.clip(np.asarray(probabilities, dtype=np.float64).reshape(-1), 0.0, 1.0)
    y = np.asarray(labels, dtype=np.float64).reshape(-1)
    if p.size == 0 or p.size != y.size:
        return 0.0
    bins = np.linspace(0.0, 1.0, int(n_bins) + 1)
    ece = 0.0
    n = float(p.size)
    for i in range(int(n_bins)):
        lo, hi = float(bins[i]), float(bins[i + 1])
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        if not np.any(mask):
            continue
        acc = float(np.mean(y[mask]))
        conf = float(np.mean(p[mask]))
        ece += (float(np.sum(mask)) / n) * abs(acc - conf)
    return float(ece)
