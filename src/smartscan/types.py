"""Frozen shared contracts for SIH26055.

Created in Stage 1. Later stages must import these types and may only extend
them compatibly. Policy-visible structures never carry Stage-1 oracle emitter
IDs, hidden threat labels, or future occupancy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"

# Evaluator-only keys must never enter policy observations, features, or rewards.
ORACLE_INFO_PREFIX = "oracle_"
EVALUATOR_ONLY_FIELDS = frozenset(
    {
        "threat_weight",
        "hidden_metadata",
        "true_emitter_id",
        "true_emitter_ids",
        "occupied",
        "signal_power_w",
        "ground_truth",
    }
)


def is_evaluator_only_key(key: str) -> bool:
    """True for frozen evaluator fields and any ``oracle_``-prefixed info key."""

    return key in EVALUATOR_ONLY_FIELDS or key.startswith(ORACLE_INFO_PREFIX)


class SmartScanError(ValueError):
    """Actionable validation error."""


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize *value* with sorted keys and normalized numeric forms."""

    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def content_fingerprint(value: Any) -> str:
    """SHA-256 of canonical JSON (semantic content, not artifact bytes)."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_digest(array: np.ndarray) -> str:
    contig = np.ascontiguousarray(array)
    return hashlib.sha256(contig.tobytes()).hexdigest()


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        # Volatile timestamps are excluded by callers; if present, keep ISO for debugging.
        return value.astimezone().isoformat()
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, np.ndarray):
        return {
            "ndarray_dtype": str(value.dtype),
            "ndarray_shape": list(value.shape),
            "ndarray_sha256": array_digest(value),
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if not np.isfinite(number):
            raise SmartScanError(f"Non-finite float is not canonicalizable: {number!r}")
        if number == 0.0:
            number = 0.0
        return format(number, ".17g")
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, pd.DataFrame):
        records = value.to_dict(orient="records")
        return _canonicalize(records)
    raise SmartScanError(f"Unsupported type for canonical JSON: {type(value)!r}")


class BandPlan(BaseModel):
    """Half-open frequency bins ``[edge[k], edge[k+1])``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    band_edges_hz: tuple[float, ...]
    band_names: tuple[str, ...]
    profile_id: str
    scan_span_hz: float

    @property
    def n_bands(self) -> int:
        return len(self.band_names)

    @model_validator(mode="after")
    def _validate_edges(self) -> BandPlan:
        edges = np.asarray(self.band_edges_hz, dtype=np.float64)
        if edges.ndim != 1 or edges.size < 2:
            raise SmartScanError("BandPlan.band_edges_hz must contain at least two edges.")
        if not np.all(np.isfinite(edges)):
            raise SmartScanError("BandPlan edges must be finite.")
        if not np.all(np.diff(edges) > 0):
            raise SmartScanError("BandPlan edges must be strictly increasing.")
        if len(self.band_names) != edges.size - 1:
            raise SmartScanError("band_names length must equal len(band_edges_hz) - 1.")
        expected_span = float(edges[-1] - edges[0])
        if not np.isclose(self.scan_span_hz, expected_span, rtol=0.0, atol=1e-3):
            raise SmartScanError(
                f"scan_span_hz={self.scan_span_hz} does not match edge span {expected_span}."
            )
        return self

    def bandwidths_hz(self) -> np.ndarray:
        edges = np.asarray(self.band_edges_hz, dtype=np.float64)
        return np.diff(edges)

    def band_index(self, frequency_hz: float) -> int:
        """Map a frequency to a band using searchsorted with high-edge exclusion."""

        from smartscan.rf.bands import frequency_to_band

        return frequency_to_band(frequency_hz, self)


class EventRecord(BaseModel):
    """One maximal emitter-band illumination interval, half-open ``[start, end)``."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    emitter_id: str
    band: int
    start_step: int
    end_step: int
    source: str
    threat_weight: float | None = Field(
        default=None,
        description="Evaluator-only synthetic threat weight. Never policy-visible.",
    )
    hidden_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Evaluator-only metadata. Never policy-visible.",
    )

    @model_validator(mode="after")
    def _validate_interval(self) -> EventRecord:
        if self.start_step < 0 or self.end_step <= self.start_step:
            raise SmartScanError(
                f"Invalid event interval [{self.start_step}, {self.end_step}) for {self.event_id}."
            )
        if self.band < 0:
            raise SmartScanError(f"Event {self.event_id} has negative band index.")
        if self.threat_weight is not None and (
            not np.isfinite(self.threat_weight) or self.threat_weight < 0
        ):
            raise SmartScanError(
                f"Event {self.event_id} threat_weight must be finite and nonnegative."
            )
        return self


class EventTable:
    """Canonical emitter-level event table."""

    columns = (
        "event_id",
        "emitter_id",
        "band",
        "start_step",
        "end_step",
        "source",
        "threat_weight",
        "hidden_metadata",
    )

    def __init__(self, records: Sequence[EventRecord] | pd.DataFrame | EventTable):
        frame: pd.DataFrame
        if isinstance(records, EventTable):
            frame = records._frame.copy(deep=True)
        elif isinstance(records, pd.DataFrame):
            frame = records.copy()
            for column in self.columns:
                if column not in frame.columns:
                    frame[column] = None if column in {"threat_weight", "hidden_metadata"} else ""
            frame = frame.loc[:, list(self.columns)].reset_index(drop=True)
        else:
            rows = [record.model_dump() for record in records]
            frame = pd.DataFrame(rows, columns=list(self.columns))
        self._frame: pd.DataFrame = frame
        self._canonicalize_inplace()

    def _canonicalize_inplace(self) -> None:
        if self._frame.empty:
            self._frame = pd.DataFrame(columns=list(self.columns))
            return
        self._frame["band"] = self._frame["band"].astype(int)
        self._frame["start_step"] = self._frame["start_step"].astype(int)
        self._frame["end_step"] = self._frame["end_step"].astype(int)
        self._frame.sort_values(
            ["start_step", "emitter_id", "band", "event_id"],
            inplace=True,
            kind="mergesort",
        )
        self._frame.reset_index(drop=True, inplace=True)

    @property
    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self._frame)

    def __len__(self) -> int:
        return int(len(self._frame))

    def records(self) -> list[EventRecord]:
        out: list[EventRecord] = []
        for row in self._frame.to_dict(orient="records"):
            hidden = row.get("hidden_metadata")
            if isinstance(hidden, float) and np.isnan(hidden):
                hidden = None
            weight = row.get("threat_weight")
            if weight is not None and isinstance(weight, float) and np.isnan(weight):
                weight = None
            out.append(
                EventRecord(
                    event_id=str(row["event_id"]),
                    emitter_id=str(row["emitter_id"]),
                    band=int(row["band"]),
                    start_step=int(row["start_step"]),
                    end_step=int(row["end_step"]),
                    source=str(row["source"]),
                    threat_weight=None if weight is None else float(weight),
                    hidden_metadata=hidden if isinstance(hidden, dict) else None,
                )
            )
        return out

    def canonical_records(self) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for record in self.records():
            dumped = record.model_dump()
            if dumped["threat_weight"] is None:
                dumped.pop("threat_weight")
            if not dumped.get("hidden_metadata"):
                dumped.pop("hidden_metadata", None)
            payload.append(dumped)
        return payload


class Provenance(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    source_uri: str | None = None
    original_file_sha256: str | None = None
    dataset_version: str | None = None
    transformation: dict[str, Any] = Field(default_factory=dict)
    dropped_counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    side_table_path: str | None = None
    side_table_sha256: str | None = None


class GroundTruth:
    """Perfect evaluation truth for one scenario realization."""

    def __init__(
        self,
        *,
        dt_s: float,
        n_steps: int,
        band_plan: BandPlan,
        occupied: np.ndarray,
        signal_power_w: np.ndarray,
        events: EventTable,
        provenance: Provenance,
        content_fingerprint: str,
        artifact_sha256: str | None,
        scenario_config: Mapping[str, Any],
        seed: int,
        generator_version: str = GENERATOR_VERSION,
        schema_version: str = SCHEMA_VERSION,
    ) -> None:
        self.dt_s = float(dt_s)
        self.n_steps = int(n_steps)
        self.band_plan = band_plan
        self.occupied = np.asarray(occupied, dtype=bool)
        self.signal_power_w = np.asarray(signal_power_w, dtype=np.float32)
        self.events = events if isinstance(events, EventTable) else EventTable(events)
        self.provenance = provenance
        self.content_fingerprint = content_fingerprint
        self.artifact_sha256 = artifact_sha256
        self.scenario_config = dict(scenario_config)
        self.seed = int(seed)
        self.generator_version = generator_version
        self.schema_version = schema_version
        validate_ground_truth_arrays(self)

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generator_version": self.generator_version,
            "seed": self.seed,
            "dt_s": self.dt_s,
            "n_steps": self.n_steps,
            "band_plan": self.band_plan.model_dump(),
            "scenario_config": strip_volatile(self.scenario_config),
            "occupied": self.occupied,
            "signal_power_w": self.signal_power_w,
            "events": self.events.canonical_records(),
            "provenance": strip_volatile(self.provenance.model_dump()),
        }

    def compute_content_fingerprint(self) -> str:
        return content_fingerprint(self.semantic_payload())


def strip_volatile(value: Any) -> Any:
    """Drop timestamps and absolute paths from nested mappings."""

    volatile_keys = {
        "created_at",
        "artifact_sha256",
        "absolute_path",
        "abs_path",
        "mlflow_run_id",
    }
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in volatile_keys:
                continue
            if key.endswith("_path") and _looks_absolute(item):
                continue
            out[str(key)] = strip_volatile(item)
        return out
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [strip_volatile(item) for item in value]
    return value


def _looks_absolute(item: Any) -> bool:
    if not isinstance(item, str):
        return False
    if len(item) >= 2 and item[1] == ":":
        return True
    return item.startswith("/") or item.startswith("\\\\")


def validate_ground_truth_arrays(truth: GroundTruth) -> None:
    n_steps = truth.n_steps
    n_bands = truth.band_plan.n_bands
    if truth.dt_s <= 0 or not np.isfinite(truth.dt_s):
        raise SmartScanError(f"dt_s must be finite and positive, got {truth.dt_s}.")
    if n_steps <= 0:
        raise SmartScanError("n_steps must be positive.")
    if truth.occupied.shape != (n_steps, n_bands):
        raise SmartScanError(
            f"occupied shape {truth.occupied.shape} != {(n_steps, n_bands)}."
        )
    if truth.signal_power_w.shape != (n_steps, n_bands):
        raise SmartScanError(
            f"signal_power_w shape {truth.signal_power_w.shape} != {(n_steps, n_bands)}."
        )
    if truth.signal_power_w.dtype != np.float32:
        raise SmartScanError("signal_power_w must be float32.")
    if not np.all(np.isfinite(truth.signal_power_w)):
        raise SmartScanError("signal_power_w contains NaN or Inf.")
    if np.any(truth.signal_power_w < 0):
        raise SmartScanError("signal_power_w contains negative power.")
    for record in truth.events.records():
        if record.band >= n_bands:
            raise SmartScanError(
                f"Event {record.event_id} band {record.band} is outside BandPlan."
            )
        if record.end_step > n_steps:
            raise SmartScanError(
                f"Event {record.event_id} end_step {record.end_step} exceeds n_steps={n_steps}."
            )


class ReceiverConfig(BaseModel):
    """Frozen receiver contract. Stage 2 implements the scanning detector."""

    model_config = ConfigDict(extra="forbid")

    receiver_ibw_hz: float
    scan_span_hz: float
    tune_latency_steps: int = 1
    dwell_bins: tuple[int, ...] = (1, 2, 4, 8, 16)
    noise_mode: Literal["normalized", "physical"] = "normalized"
    pfa_design: float = 1e-3
    samples_per_step: int = 1
    temperature_k: float | None = None
    noise_figure_db: float | None = None
    noise_power_w: float | None = None
    receiver_id: str = "rx0"
    n_channels: int = 1

    @model_validator(mode="after")
    def _validate(self) -> ReceiverConfig:
        if self.receiver_ibw_hz <= 0 or self.scan_span_hz <= 0:
            raise SmartScanError("receiver_ibw_hz and scan_span_hz must be positive.")
        ratio = self.scan_span_hz / self.receiver_ibw_hz
        if ratio < 10:
            raise SmartScanError(
                f"scan_span_hz/receiver_ibw_hz must be >= 10, got {ratio:.6g}."
            )
        if self.tune_latency_steps < 0:
            raise SmartScanError("tune_latency_steps must be >= 0.")
        if any(bin_size <= 0 for bin_size in self.dwell_bins):
            raise SmartScanError("dwell_bins must be positive integers.")
        if min(self.dwell_bins) < 1:
            raise SmartScanError("dwell_bins min must be >= 1.")
        if self.n_channels != 1:
            raise SmartScanError("Version 1 models exactly one receiver channel.")
        if self.samples_per_step <= 0:
            raise SmartScanError("samples_per_step must be positive.")
        if not (0.0 < self.pfa_design < 1.0):
            raise SmartScanError("pfa_design must be in (0, 1).")
        if self.noise_mode == "physical":
            if self.temperature_k is None or self.noise_figure_db is None:
                raise SmartScanError(
                    "physical noise mode requires temperature_k and noise_figure_db."
                )
        if self.noise_power_w is not None and (
            not np.isfinite(self.noise_power_w) or self.noise_power_w <= 0
        ):
            raise SmartScanError("noise_power_w must be finite and positive when set.")
        return self

    def validate_ibw_for_band(self, band_width_hz: float) -> None:
        if self.receiver_ibw_hz > band_width_hz + 1e-6:
            raise SmartScanError(
                f"receiver_ibw_hz={self.receiver_ibw_hz} is wider than band {band_width_hz} Hz."
            )


class ScanCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    target_band: int
    dwell_steps: int

    @field_validator("dwell_steps")
    @classmethod
    def _positive_dwell(cls, value: int) -> int:
        if value <= 0:
            raise SmartScanError("dwell_steps must be positive.")
        return value


class ObservationRow(BaseModel):
    """Policy-visible per-step receiver state. No oracle labels."""

    model_config = ConfigDict(extra="forbid")

    step: int
    receiver_state: str
    commanded_band: int | None
    tuned_band: int | None
    decision_id: str | None
    dwell_progress: int
    integrated_energy: float
    measured_snr_db: float | None
    detection: bool


class DecisionRow(BaseModel):
    """One completed command. Forecast fields are nullable until Stage 5."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    start_step: int
    tune_end_step: int
    dwell_end_step: int
    end_step: int
    target_band: int
    dwell_steps: int
    hit: bool
    measured_snr_db: float | None = None
    receiver_seed: int | None = None
    p_hit: float | None = None
    p_active: float | None = None
    time_to_next_completed_intercept_s: float | None = None
    forecast_horizon_s: float | None = None
    uncertainty: float | None = None
    model_version: str | None = None
    reward: float | None = None
    cost_tune_s: float | None = None
    cost_time_s: float | None = None
    assessed_threat: float | None = None
    novelty: float | None = None
    priority: float | None = None
    reward_hit: float | None = None
    reward_priority: float | None = None
    cost_repeat: float | None = None
    cost_false_like: float | None = None


class MetricValue(BaseModel):
    name: str
    numerator: float | None = None
    denominator: float | None = None
    value: float | None = None
    unit: str = ""
    available: bool = True
    unavailable_reason: str | None = None


class MetricsReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    metric_schema_version: str = SCHEMA_VERSION
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    config_hash: str | None = None
    input_fingerprints: dict[str, str] = Field(default_factory=dict)
    artifact_sha256: dict[str, str] = Field(default_factory=dict)
    created_at: str | None = None


class RunIdentity(BaseModel):
    domain_run_id: UUID
    config_hash: str
    content_fingerprint: str
    artifact_sha256: str
    seeds: dict[str, int] = Field(default_factory=dict)
    git_sha: str | None = None
    mlflow_run_id: str | None = None
