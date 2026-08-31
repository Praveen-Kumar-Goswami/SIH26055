"""Stage 3 metric schemas. JSON-safe scalars; unavailable is null plus reason."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from smartscan.types import SCHEMA_VERSION, MetricsReport, MetricValue

METRIC_SCHEMA_VERSION = SCHEMA_VERSION

FROZEN_METRIC_KEYS: tuple[str, ...] = (
    "pd",
    "pfa",
    "sensitivity",
    "average_intercept_rate",
    "average_reward",
    "correct_predictions",
    "average_intercept_time_error",
)

FROZEN_METRIC_NAMES: dict[str, str] = {
    "pd": "Pd",
    "pfa": "Pfa",
    "sensitivity": "Sensitivity",
    "average_intercept_rate": "Average intercept rate",
    "average_reward": "Average reward/cost",
    "correct_predictions": "Correct predictions",
    "average_intercept_time_error": "Average intercept-time error",
}

ZERO_DENOMINATOR = "zero_denominator"
FORECASTS_ABSENT = "pre_action_forecasts_absent"
REWARD_ABSENT = "no_observable_reward_in_decision_log"
SENSITIVITY_NOT_ATTACHED = "controlled_sensitivity_sweep_not_attached"
NO_ELIGIBLE_FORECASTS = "no_uncensored_intercept_time_forecasts"


class MetricsConfig(BaseModel):
    """Evaluator knobs. Not policy-visible."""

    model_config = ConfigDict(extra="forbid")

    activity_threshold: float = 0.5
    miss_penalty_horizon_s: float | None = None
    ece_bins: int = 10
    target_pd: float = 0.90
    samples_per_step: int = 1
    dwell_steps: int = 8
    pfa_design: float = 1e-3
    include_analytic_sensitivity: bool = True


class BandOccupancyEvent(BaseModel):
    """Maximal contiguous occupancy on one band. Official capture unit."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    band: int
    start_step: int
    end_step: int
    threat_weight: float = 1.0


class MatchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    decision_id: str
    band: int
    event_start_step: int
    event_end_step: int
    detection_end_step: int
    delay_s: float
    threat_weight: float


class MissedEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    band: int
    start_step: int
    end_step: int
    duration_s: float
    nearest_decision_id: str | None = None
    nearest_visit_start_step: int | None = None
    nearest_gap_steps: int | None = None


class PdStratum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dwell_steps: int
    occupied_fraction_bin: str
    snr_bin: str
    true_positives: int
    occupied_completed: int
    pd: float | None


class PerBandStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: int
    active_fraction: float
    dwell_fraction: float
    intercept_ratio: float | None
    n_events: int
    n_matched: int
    n_missed: int
    mean_revisit_gap_s: float | None
    hit_brier: float | None = None
    activity_brier: float | None = None


class CensoringSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    miss_penalty_horizon_s: float
    km_censor_rule: str = "unmatched_events_censored_at_event_end"
    forecast_count: int = 0
    eligible_count: int = 0
    forecast_coverage: float | None = None
    km_rmst_s: float | None = None
    all_event_penalized_delay_s: float | None = None
    n_km_captured: int = 0
    n_km_censored: int = 0


class SensitivityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snr_db: float
    pd_analytic: float
    pd_hat: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


class SensitivityCurve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_pd: float
    m_samples: int
    pfa_design: float
    snr_db_at_target: float
    receiver_input_dbm: float | None = None
    noise_mode: Literal["normalized", "physical"] = "normalized"
    monotone: bool = True
    seed: int | None = None
    n_trials: int | None = None
    points: list[SensitivityPoint] = Field(default_factory=list)


class MetricsTables(BaseModel):
    """Raw counts/events kept outside the summary metric dictionary."""

    model_config = ConfigDict(extra="forbid")

    band_occupancy_events: list[BandOccupancyEvent] = Field(default_factory=list)
    matches: list[MatchRecord] = Field(default_factory=list)
    missed_events: list[MissedEventRecord] = Field(default_factory=list)
    pd_strata: list[PdStratum] = Field(default_factory=list)
    per_band: list[PerBandStats] = Field(default_factory=list)
    evaluation_score_components: dict[str, float | None] = Field(default_factory=dict)
    support: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Full Stage 3 output: MetricsReport plus referenced tables."""

    model_config = ConfigDict(extra="forbid")

    report: MetricsReport
    tables: MetricsTables
    censoring: CensoringSummary
    sensitivity: SensitivityCurve | None = None
    content_fingerprint: str
    notes: list[str] = Field(default_factory=list)


def unavailable(
    name: str,
    reason: str,
    *,
    numerator: float | None = None,
    denominator: float | None = None,
    unit: str = "",
) -> MetricValue:
    return MetricValue(
        name=name,
        numerator=numerator,
        denominator=denominator,
        value=None,
        unit=unit,
        available=False,
        unavailable_reason=reason,
    )


def ratio_metric(
    name: str,
    numerator: float,
    denominator: float,
    *,
    unit: str = "",
    scale: float = 1.0,
) -> MetricValue:
    if denominator == 0.0:
        return unavailable(name, ZERO_DENOMINATOR, numerator=numerator, denominator=0.0, unit=unit)
    return MetricValue(
        name=name,
        numerator=float(numerator),
        denominator=float(denominator),
        value=float(scale * numerator / denominator),
        unit=unit,
        available=True,
        unavailable_reason=None,
    )
