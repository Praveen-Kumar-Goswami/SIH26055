"""ObservationLog and DecisionLog containers, save/reload, evaluator diagnostics.

Oracle occupancy is joined only in diagnostic helpers, never stored on
policy-visible rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from smartscan.types import (
    SCHEMA_VERSION,
    DecisionRow,
    GroundTruth,
    ObservationRow,
    SmartScanError,
    sha256_file,
)

LOG_SCHEMA_VERSION = SCHEMA_VERSION


@dataclass
class ObservationLog:
    rows: list[ObservationRow]
    ground_truth_fingerprint: str
    receiver_config_hash: str
    schema_version: str = LOG_SCHEMA_VERSION
    dt_s: float = 0.001
    artifact_sha256: str | None = None

    def validate(self) -> None:
        prev = -1
        for row in self.rows:
            if row.step <= prev:
                raise SmartScanError(
                    f"ObservationLog steps must be strictly increasing, got {row.step} after {prev}."
                )
            prev = row.step


@dataclass
class DecisionLog:
    rows: list[DecisionRow]
    ground_truth_fingerprint: str
    receiver_config_hash: str
    schema_version: str = LOG_SCHEMA_VERSION
    dt_s: float = 0.001
    receiver_seed: int | None = None
    n_incomplete_commands: int = 0
    artifact_sha256: str | None = None
    predicted_interception_ratio: float | None = None
    predicted_intercept_count: float | None = None
    predicted_opportunity_count: float | None = None
    predicted_ratio_ci_low: float | None = None
    predicted_ratio_ci_high: float | None = None
    forecast_recorded_at_step: int | None = None
    forecast_horizon_steps: int | None = None

    def validate(self) -> None:
        seen: set[str] = set()
        prev_end = -1
        for row in self.rows:
            if row.decision_id in seen:
                raise SmartScanError(f"Duplicate decision_id {row.decision_id}.")
            seen.add(row.decision_id)
            if row.end_step <= row.start_step:
                raise SmartScanError(f"{row.decision_id} has empty interval.")
            if row.tune_end_step < row.start_step or row.tune_end_step > row.end_step:
                raise SmartScanError(f"{row.decision_id} tune_end_step is inconsistent.")
            if row.end_step < prev_end:
                raise SmartScanError("DecisionLog end_step values must be nondecreasing.")
            prev_end = row.end_step
            usable = row.end_step - row.tune_end_step
            if usable != row.dwell_steps:
                raise SmartScanError(
                    f"{row.decision_id} usable dwell {usable} != dwell_steps {row.dwell_steps}."
                )


@dataclass
class ReceiverRun:
    observations: ObservationLog
    decisions: DecisionLog
    artifact_sha256: str | None = field(default=None)


def save_receiver_run(run: ReceiverRun, path: str | Path) -> ReceiverRun:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run.observations.validate()
    run.decisions.validate()
    tmp = dest.with_name(dest.stem + ".writing.npz")
    if tmp.exists():
        tmp.unlink()
    meta = {
        "schema_version": run.observations.schema_version,
        "ground_truth_fingerprint": run.observations.ground_truth_fingerprint,
        "receiver_config_hash": run.observations.receiver_config_hash,
        "dt_s": run.observations.dt_s,
        "receiver_seed": run.decisions.receiver_seed,
        "n_incomplete_commands": run.decisions.n_incomplete_commands,
        "n_observations": len(run.observations.rows),
        "n_decisions": len(run.decisions.rows),
        "predicted_interception_ratio": run.decisions.predicted_interception_ratio,
        "predicted_intercept_count": run.decisions.predicted_intercept_count,
        "predicted_opportunity_count": run.decisions.predicted_opportunity_count,
        "predicted_ratio_ci_low": run.decisions.predicted_ratio_ci_low,
        "predicted_ratio_ci_high": run.decisions.predicted_ratio_ci_high,
        "forecast_recorded_at_step": run.decisions.forecast_recorded_at_step,
        "forecast_horizon_steps": run.decisions.forecast_horizon_steps,
    }
    obs_bytes = json.dumps(
        [row.model_dump() for row in run.observations.rows],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    dec_bytes = json.dumps(
        [row.model_dump() for row in run.decisions.rows],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    np.savez_compressed(
        tmp,
        meta_utf8=np.frombuffer(json.dumps(meta, sort_keys=True).encode("utf-8"), dtype=np.uint8),
        observations_utf8=np.frombuffer(obs_bytes, dtype=np.uint8),
        decisions_utf8=np.frombuffer(dec_bytes, dtype=np.uint8),
    )
    tmp.replace(dest)
    digest = sha256_file(dest)
    run.artifact_sha256 = digest
    run.observations.artifact_sha256 = digest
    run.decisions.artifact_sha256 = digest
    return run


def load_receiver_run(path: str | Path) -> ReceiverRun:
    src = Path(path)
    if not src.is_file():
        raise SmartScanError(f"Receiver log file not found: {src}")
    with np.load(src, allow_pickle=False) as payload:
        for key in ("meta_utf8", "observations_utf8", "decisions_utf8"):
            if key not in payload:
                raise SmartScanError(f"Receiver NPZ missing {key}.")
        meta = json.loads(bytes(payload["meta_utf8"]).decode("utf-8"))
        obs_raw = json.loads(bytes(payload["observations_utf8"]).decode("utf-8"))
        dec_raw = json.loads(bytes(payload["decisions_utf8"]).decode("utf-8"))
    observations = ObservationLog(
        rows=[ObservationRow.model_validate(item) for item in obs_raw],
        ground_truth_fingerprint=str(meta["ground_truth_fingerprint"]),
        receiver_config_hash=str(meta["receiver_config_hash"]),
        schema_version=str(meta.get("schema_version", LOG_SCHEMA_VERSION)),
        dt_s=float(meta.get("dt_s", 0.001)),
        artifact_sha256=sha256_file(src),
    )
    decisions = DecisionLog(
        rows=[DecisionRow.model_validate(item) for item in dec_raw],
        ground_truth_fingerprint=str(meta["ground_truth_fingerprint"]),
        receiver_config_hash=str(meta["receiver_config_hash"]),
        schema_version=str(meta.get("schema_version", LOG_SCHEMA_VERSION)),
        dt_s=float(meta.get("dt_s", 0.001)),
        receiver_seed=meta.get("receiver_seed"),
        n_incomplete_commands=int(meta.get("n_incomplete_commands", 0)),
        artifact_sha256=observations.artifact_sha256,
        predicted_interception_ratio=meta.get("predicted_interception_ratio"),
        predicted_intercept_count=meta.get("predicted_intercept_count"),
        predicted_opportunity_count=meta.get("predicted_opportunity_count"),
        predicted_ratio_ci_low=meta.get("predicted_ratio_ci_low"),
        predicted_ratio_ci_high=meta.get("predicted_ratio_ci_high"),
        forecast_recorded_at_step=meta.get("forecast_recorded_at_step"),
        forecast_horizon_steps=meta.get("forecast_horizon_steps"),
    )
    observations.validate()
    decisions.validate()
    return ReceiverRun(
        observations=observations,
        decisions=decisions,
        artifact_sha256=observations.artifact_sha256,
    )


def diagnostic_counts(truth: GroundTruth, run: ReceiverRun) -> dict[str, Any]:
    """Evaluator-only diagnostics for the CLI. Not Stage 3 figures of merit."""

    if truth.content_fingerprint != run.observations.ground_truth_fingerprint:
        raise SmartScanError("GroundTruth fingerprint does not match receiver logs.")
    n_tune = sum(1 for row in run.observations.rows if row.receiver_state == "TUNING")
    n_obs = max(len(run.observations.rows), 1)
    hits = 0
    misses = 0
    false_alarms = 0
    snrs: list[float] = []
    for row in run.decisions.rows:
        usable = slice(row.tune_end_step, row.end_step)
        occupied = bool(np.any(truth.occupied[usable, row.target_band]))
        if row.hit and not occupied:
            false_alarms += 1
        if occupied and row.hit:
            hits += 1
        if occupied and not row.hit:
            misses += 1
        if not occupied and not row.hit:
            pass
        if row.measured_snr_db is not None:
            snrs.append(float(row.measured_snr_db))
    return {
        "completed_dwells": len(run.decisions.rows),
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "n_detections": sum(1 for row in run.decisions.rows if row.hit),
        "tuning_fraction": n_tune / n_obs,
        "average_measured_snr_db": float(np.mean(snrs)) if snrs else None,
        "n_incomplete_commands": run.decisions.n_incomplete_commands,
        "n_observation_steps": len(run.observations.rows),
    }
