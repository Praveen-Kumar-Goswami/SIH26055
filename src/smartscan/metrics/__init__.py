"""Metrics engine: event matching, seven figures of merit, sensitivity sweeps."""

from __future__ import annotations

from smartscan.metrics.engine import (
    evaluate_run,
    evaluate_strategy,
    load_metrics,
    save_metrics,
    save_metrics_csv,
)
from smartscan.metrics.matching import (
    derive_band_occupancy_events,
    dwell_occupied,
    match_detections,
)
from smartscan.metrics.schemas import (
    FROZEN_METRIC_KEYS,
    METRIC_SCHEMA_VERSION,
    BandOccupancyEvent,
    EvaluationResult,
    MetricsConfig,
    MetricsTables,
    SensitivityCurve,
)
from smartscan.metrics.sensitivity import (
    analytic_sensitivity_curve,
    analytic_snr_db_at_target_pd,
    run_sensitivity_sweep,
)
from smartscan.metrics.statistics import (
    bootstrap_mean_ci,
    compare_runs,
    newcombe_diff_upper,
    paired_compare,
)

__all__ = [
    "FROZEN_METRIC_KEYS",
    "METRIC_SCHEMA_VERSION",
    "BandOccupancyEvent",
    "EvaluationResult",
    "MetricsConfig",
    "MetricsTables",
    "SensitivityCurve",
    "analytic_sensitivity_curve",
    "analytic_snr_db_at_target_pd",
    "bootstrap_mean_ci",
    "compare_runs",
    "derive_band_occupancy_events",
    "dwell_occupied",
    "evaluate_run",
    "evaluate_strategy",
    "load_metrics",
    "match_detections",
    "newcombe_diff_upper",
    "paired_compare",
    "run_sensitivity_sweep",
    "save_metrics",
    "save_metrics_csv",
]
