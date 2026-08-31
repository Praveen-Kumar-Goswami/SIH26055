"""Brier/ECE, Kaplan–Meier/RMST, and run-level bootstrap helpers.

Resampling uses whole runs or seeds, never individual time steps.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from smartscan.seeding import spawn_generator
from smartscan.types import MetricsReport, MetricValue, SmartScanError


def brier_score(probabilities: np.ndarray, labels: np.ndarray) -> float:
    p = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    y = np.asarray(labels, dtype=np.float64).reshape(-1)
    if p.size == 0 or p.size != y.size:
        raise SmartScanError("Brier score requires nonempty aligned probability and label arrays.")
    return float(np.mean((p - y) ** 2))


def expected_calibration_error(
    probabilities: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> float:
    if n_bins < 2:
        raise SmartScanError("ECE requires at least two bins.")
    p = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    y = np.asarray(labels, dtype=np.float64).reshape(-1)
    if p.size == 0 or p.size != y.size:
        raise SmartScanError("ECE requires nonempty aligned probability and label arrays.")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = float(p.size)
    ece = 0.0
    for i in range(n_bins):
        left = edges[i]
        right = edges[i + 1]
        if i == n_bins - 1:
            mask = (p >= left) & (p <= right)
        else:
            mask = (p >= left) & (p < right)
        count = int(np.sum(mask))
        if count == 0:
            continue
        acc = float(np.mean(y[mask]))
        conf = float(np.mean(p[mask]))
        ece += (count / total) * abs(acc - conf)
    return float(ece)


def kaplan_meier(
    times: np.ndarray,
    event: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Right-censored KM. ``event`` is 1 for capture, 0 for censoring."""

    t = np.asarray(times, dtype=np.float64).reshape(-1)
    e = np.asarray(event, dtype=bool).reshape(-1)
    if t.size == 0 or t.size != e.size:
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
    if np.any(~np.isfinite(t)) or np.any(t < 0):
        raise SmartScanError("Kaplan–Meier times must be finite and nonnegative.")
    order = np.argsort(t, kind="mergesort")
    t = t[order]
    e = e[order]
    unique: list[float] = []
    survival: list[float] = []
    s = 1.0
    n = int(t.size)
    i = 0
    while i < n:
        t_i = float(t[i])
        at_risk = n - i
        deaths = 0
        j = i
        while j < n and float(t[j]) == t_i:
            if bool(e[j]):
                deaths += 1
            j += 1
        if deaths > 0:
            s *= 1.0 - deaths / float(at_risk)
            unique.append(t_i)
            survival.append(float(s))
        i = j
    return np.asarray(unique, dtype=np.float64), np.asarray(survival, dtype=np.float64)


def restricted_mean_survival(
    event_times: np.ndarray,
    survival: np.ndarray,
    tau: float,
    *,
    s0: float = 1.0,
) -> float:
    """∫_0^τ S(u) du for a right-continuous KM step function."""

    if tau < 0 or not np.isfinite(tau):
        raise SmartScanError(f"RMST horizon must be finite and nonnegative, got {tau}.")
    if tau == 0.0:
        return 0.0
    times = np.asarray(event_times, dtype=np.float64).reshape(-1)
    surv = np.asarray(survival, dtype=np.float64).reshape(-1)
    t_prev = 0.0
    s_prev = float(s0)
    area = 0.0
    for t_i, s_i in zip(times.tolist(), surv.tolist(), strict=True):
        if t_i <= t_prev:
            s_prev = float(s_i)
            continue
        clip = min(float(t_i), float(tau))
        area += s_prev * (clip - t_prev)
        if float(t_i) >= float(tau):
            return float(area)
        t_prev = float(t_i)
        s_prev = float(s_i)
    area += s_prev * (float(tau) - t_prev)
    return float(area)


def delay_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "p90": None, "std": None, "count": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p90": float(np.quantile(arr, 0.90)),
        "std": float(np.std(arr, ddof=0)),
        "count": float(arr.size),
    }


def bootstrap_mean_ci(
    values: np.ndarray,
    *,
    seed: int,
    n_boot: int = 2000,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Run/seed-level bootstrap of the mean. Returns (mean, ci_low, ci_high)."""

    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        raise SmartScanError("bootstrap_mean_ci requires at least one run-level value.")
    mean = float(np.mean(arr))
    if arr.size == 1:
        return mean, mean, mean
    rng = spawn_generator(seed)
    samples = np.empty(n_boot, dtype=np.float64)
    n = arr.size
    for i in range(n_boot):
        draw = rng.integers(0, n, size=n)
        samples[i] = float(np.mean(arr[draw]))
    low = float(np.quantile(samples, alpha / 2.0))
    high = float(np.quantile(samples, 1.0 - alpha / 2.0))
    return mean, low, high


def metric_scalar(report: MetricsReport, key: str) -> float | None:
    item = report.metrics.get(key)
    if item is None or not item.available or item.value is None:
        return None
    return float(item.value)


def compare_runs(
    reports: list[MetricsReport],
    *,
    metric_key: str,
    seed: int = 0,
) -> dict[str, Any]:
    """Summarize one metric across whole runs. Does not resample time steps."""

    if not reports:
        raise SmartScanError("compare_runs requires at least one MetricsReport.")
    values: list[float] = []
    unavailable = 0
    for report in reports:
        scalar = metric_scalar(report, metric_key)
        if scalar is None:
            unavailable += 1
        else:
            values.append(scalar)
    result: dict[str, Any] = {
        "metric_key": metric_key,
        "n_runs": len(reports),
        "n_available": len(values),
        "n_unavailable": unavailable,
        "values": values,
    }
    if not values:
        result["mean"] = None
        result["ci_low"] = None
        result["ci_high"] = None
        result["unavailable_reason"] = "metric_unavailable_on_all_runs"
        return result
    mean, low, high = bootstrap_mean_ci(np.asarray(values), seed=seed)
    result["mean"] = mean
    result["ci_low"] = low
    result["ci_high"] = high
    return result


def paired_compare(
    reports_a: list[MetricsReport],
    reports_b: list[MetricsReport],
    *,
    metric_key: str,
    seed: int = 0,
) -> dict[str, Any]:
    """Paired seed/run comparison. Lengths must match."""

    if len(reports_a) != len(reports_b):
        raise SmartScanError("paired_compare requires equal-length run lists.")
    if not reports_a:
        raise SmartScanError("paired_compare requires at least one pair.")
    deltas: list[float] = []
    skipped = 0
    for left, right in zip(reports_a, reports_b, strict=True):
        a = metric_scalar(left, metric_key)
        b = metric_scalar(right, metric_key)
        if a is None or b is None:
            skipped += 1
            continue
        deltas.append(a - b)
    payload: dict[str, Any] = {
        "metric_key": metric_key,
        "n_pairs": len(reports_a),
        "n_scored": len(deltas),
        "n_skipped": skipped,
        "deltas": deltas,
    }
    if not deltas:
        payload["mean_delta"] = None
        payload["ci_low"] = None
        payload["ci_high"] = None
        payload["unavailable_reason"] = "no_paired_available_values"
        return payload
    mean, low, high = bootstrap_mean_ci(np.asarray(deltas), seed=seed)
    payload["mean_delta"] = mean
    payload["ci_low"] = low
    payload["ci_high"] = high
    return payload


def require_available(metric: MetricValue) -> float:
    if not metric.available or metric.value is None:
        raise SmartScanError(f"Metric {metric.name!r} is unavailable: {metric.unavailable_reason}.")
    return float(metric.value)


def newcombe_diff_upper(
    x1: int,
    n1: int,
    x2: int,
    n2: int,
    *,
    alpha: float = 0.05,
) -> float:
    """One-sided Newcombe (Wilson-score) upper bound for p1 - p2.

    Used for delta_Pfa = Pfa_PPO - Pfa_best. ``x`` are event counts, ``n`` trials.
    """

    if n1 <= 0 or n2 <= 0:
        raise SmartScanError("Newcombe CI requires positive trial counts.")
    if x1 < 0 or x2 < 0 or x1 > n1 or x2 > n2:
        raise SmartScanError("Newcombe counts must lie in [0, n].")
    from scipy.stats import norm

    z = float(norm.ppf(1.0 - alpha))
    p1 = x1 / n1
    p2 = x2 / n2
    # Wilson interval endpoints
    def wilson_bounds(p: float, n: int) -> tuple[float, float]:
        z2 = z * z
        denom = 1.0 + z2 / n
        center = (p + z2 / (2.0 * n)) / denom
        half = (z * np.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom
        return max(0.0, center - half), min(1.0, center + half)

    l1, u1 = wilson_bounds(p1, n1)
    l2, u2 = wilson_bounds(p2, n2)
    # Newcombe: upper for p1-p2 uses u1 - l2
    return float(u1 - l2)

