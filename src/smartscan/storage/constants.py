"""Status, experiment, and metric-index constants for the domain store."""

from __future__ import annotations

from smartscan.metrics.schemas import FROZEN_METRIC_KEYS

SCHEMA_VERSION = "1.0.0"

RUN_STATUS_CREATED = "created"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUSES = (
    RUN_STATUS_CREATED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
)

SYNC_PENDING = "pending"
SYNC_SYNCED = "synced"
SYNC_ERROR = "error"
SYNC_STATUSES = (SYNC_PENDING, SYNC_SYNCED, SYNC_ERROR)

EXPERIMENT_BASELINES = "smartscan-baselines"
EXPERIMENT_PREDICTOR = "smartscan-predictor"
EXPERIMENT_SCHEDULER = "smartscan-scheduler"
EXPERIMENT_ML_IMPROVE = "smartscan-ml-improve"
MLFLOW_EXPERIMENTS = (
    EXPERIMENT_BASELINES,
    EXPERIMENT_PREDICTOR,
    EXPERIMENT_SCHEDULER,
    EXPERIMENT_ML_IMPROVE,
)

PROTECTED_MODEL_ALIASES = frozenset({"champion", "production"})

INDEXED_METRIC_KEYS: tuple[str, ...] = FROZEN_METRIC_KEYS + ("event_interception_ratio",)

METRIC_ORDER_ALIASES: dict[str, str] = {
    "pd": "pd",
    "pfa": "pfa",
    "sensitivity": "sensitivity",
    "average_intercept_rate": "average_intercept_rate",
    "avg_intercept_rate": "average_intercept_rate",
    "average_reward": "average_reward",
    "avg_reward": "average_reward",
    "correct_predictions": "correct_predictions",
    "average_intercept_time_error": "average_intercept_time_error",
    "avg_intercept_time_error": "average_intercept_time_error",
    "event_interception_ratio": "event_interception_ratio",
    "interception_ratio": "event_interception_ratio",
}

VALIDATION_UNVALIDATED = "unvalidated"
VALIDATION_VALIDATED = "validated"
VALIDATION_REJECTED = "rejected"
