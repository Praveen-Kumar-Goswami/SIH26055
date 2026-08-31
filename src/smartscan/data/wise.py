"""Optional J.C. Wise-compatible local catalog importer.

Does not scrape or fabricate catalog rows. Unknown fields stay unknown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smartscan.types import SmartScanError

HZ_MIN = 1.0e6
HZ_MAX = 1.0e11

WISE_COLUMNS = (
    "source_record_id",
    "emitter_family",
    "frequency_min_hz",
    "frequency_max_hz",
    "pri_s",
    "prf_hz",
    "pulse_width_s",
    "scan_type",
    "scan_period_s",
    "public_threat_priority",
    "source_reference",
    "license_note",
)


class WiseRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_record_id: str
    emitter_family: str
    frequency_min_hz: float
    frequency_max_hz: float
    pri_s: float | None = None
    prf_hz: float | None = None
    pulse_width_s: float | None = None
    scan_type: str | None = None
    scan_period_s: float | None = None
    public_threat_priority: float | None = None
    source_reference: str | None = None
    license_note: str | None = None

    @field_validator("source_record_id", "emitter_family")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        if not str(value).strip():
            raise SmartScanError("source_record_id and emitter_family must be nonempty.")
        return str(value).strip()

    @model_validator(mode="after")
    def _ranges(self) -> WiseRecord:
        for name, value in (
            ("frequency_min_hz", float(self.frequency_min_hz)),
            ("frequency_max_hz", float(self.frequency_max_hz)),
        ):
            if value != value or value in {float("inf"), float("-inf")}:
                raise SmartScanError(f"{name} must be finite.")
            if value < HZ_MIN or value > HZ_MAX:
                raise SmartScanError(
                    f"{name}={value} is outside {HZ_MIN:.0e}-{HZ_MAX:.0e} Hz. "
                    "Check units; values belong in hertz, not GHz/MHz."
                )
        if self.frequency_max_hz <= self.frequency_min_hz:
            raise SmartScanError(
                f"{self.source_record_id}: frequency_max_hz must exceed frequency_min_hz."
            )
        for opt_name, opt_value in (
            ("pri_s", self.pri_s),
            ("prf_hz", self.prf_hz),
            ("pulse_width_s", self.pulse_width_s),
            ("scan_period_s", self.scan_period_s),
        ):
            if opt_value is None:
                continue
            if opt_value != opt_value or opt_value <= 0 or opt_value == float("inf"):
                raise SmartScanError(
                    f"{self.source_record_id}: {opt_name} must be finite and positive."
                )
        if self.pri_s is not None and self.prf_hz is not None:
            expected = 1.0 / self.pri_s
            rel = abs(expected - self.prf_hz) / max(expected, self.prf_hz)
            if rel > 0.05:
                raise SmartScanError(
                    f"{self.source_record_id}: PRI and PRF disagree "
                    f"(1/pri={expected:.6g} vs prf={self.prf_hz:.6g})."
                )
        if self.public_threat_priority is not None and (
            self.public_threat_priority != self.public_threat_priority
            or self.public_threat_priority < 0
        ):
            raise SmartScanError(
                f"{self.source_record_id}: public_threat_priority must be finite and nonnegative."
            )
        return self


class WiseValidationResult(BaseModel):
    ok: bool
    n_records: int
    records: list[WiseRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def validate_wise(path: str | Path) -> WiseValidationResult:
    file_path = Path(path)
    if not file_path.is_file():
        raise SmartScanError(f"Wise catalog file not found: {file_path}")
    rows = _read_table(file_path)
    records: list[WiseRecord] = []
    errors: list[str] = []
    for i, row in enumerate(rows):
        try:
            records.append(WiseRecord.model_validate(_normalize_row(row)))
        except Exception as exc:
            errors.append(f"row {i}: {exc}")
    return WiseValidationResult(ok=not errors, n_records=len(records), records=records, errors=errors)


def _read_table(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "records" in payload:
            payload = payload["records"]
        if not isinstance(payload, list):
            raise SmartScanError("Wise JSON must be a list of records.")
        rows: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise SmartScanError("Wise JSON records must be objects.")
            rows.append({str(key): val for key, val in item.items()})
        return rows
    if suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        frame = pd.read_csv(path, sep=sep)
        return [{str(key): val for key, val in row.items()} for row in frame.to_dict(orient="records")]
    raise SmartScanError(f"Unsupported Wise catalog suffix {suffix}; use .csv or .json.")


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        key_s = str(key).strip()
        if key_s not in WISE_COLUMNS:
            continue
        if value is None or (isinstance(value, float) and value != value):
            out[key_s] = None
        elif isinstance(value, str) and value.strip() == "":
            out[key_s] = None
        else:
            out[key_s] = value
    required = ("source_record_id", "emitter_family", "frequency_min_hz", "frequency_max_hz")
    missing = [name for name in required if name not in out or out[name] is None]
    if missing:
        raise SmartScanError(f"Missing required fields: {missing}.")
    return out
