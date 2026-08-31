from __future__ import annotations

import numpy as np
import pytest

from smartscan.metrics.statistics import (
    bootstrap_mean_ci,
    brier_score,
    compare_runs,
    expected_calibration_error,
    kaplan_meier,
    paired_compare,
    require_available,
    restricted_mean_survival,
)
from smartscan.types import MetricsReport, MetricValue, SmartScanError


def test_brier_and_ece_known_values() -> None:
    p = np.array([0.0, 1.0, 1.0, 0.0])
    y = np.array([0.0, 1.0, 1.0, 0.0])
    assert brier_score(p, y) == pytest.approx(0.0)
    assert expected_calibration_error(p, y, n_bins=2) == pytest.approx(0.0)
    with pytest.raises(SmartScanError):
        brier_score(np.array([]), np.array([]))
    with pytest.raises(SmartScanError):
        expected_calibration_error(p, y, n_bins=1)


def test_kaplan_meier_and_rmst() -> None:
    times = np.array([1.0, 2.0, 3.0, 4.0])
    event = np.array([True, False, True, False])
    t, s = kaplan_meier(times, event)
    assert t[0] == pytest.approx(1.0)
    rmst = restricted_mean_survival(t, s, tau=4.0)
    assert rmst > 0.0
    assert restricted_mean_survival(np.array([]), np.array([]), tau=2.0) == pytest.approx(2.0)
    with pytest.raises(SmartScanError):
        kaplan_meier(np.array([-1.0]), np.array([True]))
    empty_t, empty_s = kaplan_meier(np.array([]), np.array([]))
    assert empty_t.size == 0


def test_bootstrap_and_compare_edge_cases() -> None:
    mean, low, high = bootstrap_mean_ci(np.array([4.0]), seed=0)
    assert mean == low == high == 4.0
    mean, low, high = bootstrap_mean_ci(np.array([1.0, 3.0, 5.0]), seed=1, n_boot=200)
    assert low <= mean <= high
    empty = MetricsReport(metrics={"pd": MetricValue(name="Pd", available=False)})
    summary = compare_runs([empty], metric_key="pd", seed=0)
    assert summary["n_unavailable"] == 1
    with pytest.raises(SmartScanError):
        compare_runs([], metric_key="pd")
    with pytest.raises(SmartScanError):
        paired_compare([empty], [], metric_key="pd")
    paired = paired_compare([empty], [empty], metric_key="pd", seed=0)
    assert paired["n_skipped"] == 1
    with pytest.raises(SmartScanError):
        expected_calibration_error(np.array([]), np.array([]), n_bins=4)
    with pytest.raises(SmartScanError):
        restricted_mean_survival(np.array([1.0]), np.array([0.5]), tau=float("inf"))
    assert restricted_mean_survival(np.array([1.0]), np.array([0.5]), tau=0.0) == 0.0
    t, s = kaplan_meier(np.array([1.0, 1.0, 3.0]), np.array([True, True, True]))
    assert restricted_mean_survival(np.array([1.0, 1.0, 3.0]), np.array([0.8, 0.5, 0.2]), tau=2.0) > 0
    with pytest.raises(SmartScanError):
        bootstrap_mean_ci(np.array([]), seed=0)
    with pytest.raises(SmartScanError):
        paired_compare([], [], metric_key="pd")
    with pytest.raises(SmartScanError):
        require_available(MetricValue(name="Pd", available=False, unavailable_reason="x"))
    assert require_available(MetricValue(name="Pd", value=0.5, available=True)) == 0.5
