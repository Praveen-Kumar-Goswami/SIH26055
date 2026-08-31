"""SQLAlchemy 2 typed mappings for the Smart Scan domain store.

SQLite holds metadata, scalar metrics, fingerprints, JSON config, and artifact
references. Large arrays live on disk under the artifact root.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from smartscan.storage.constants import SCHEMA_VERSION, SYNC_PENDING


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base shared with Alembic."""


class DataSourceRow(Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_data_sources_fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="synthetic")
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScenarioRow(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    band_plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_sources.id"), nullable=True
    )
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[DataSourceRow | None] = relationship()
    ground_truths: Mapped[list[GroundTruthRow]] = relationship(back_populates="scenario")


class GroundTruthRow(Base):
    __tablename__ = "ground_truths"
    __table_args__ = (
        UniqueConstraint("content_fingerprint", name="uq_ground_truths_content_fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scenarios.id"), nullable=False, index=True
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default=SCHEMA_VERSION)
    n_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    n_bands: Mapped[int] = mapped_column(Integer, nullable=False)
    dt_s: Mapped[float] = mapped_column(Float, nullable=False)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scenario: Mapped[ScenarioRow] = relationship(back_populates="ground_truths")


class ReceiverConfigRow(Base):
    __tablename__ = "receiver_configs"
    __table_args__ = (UniqueConstraint("config_hash", name="uq_receiver_configs_config_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunRow(Base):
    __tablename__ = "runs"

    domain_run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scenarios.id"), nullable=False, index=True
    )
    receiver_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("receiver_configs.id"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    seeds_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default=SYNC_PENDING)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mlflow_experiment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default=SCHEMA_VERSION)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    protocol_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bundle_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)

    scenario: Mapped[ScenarioRow] = relationship()
    receiver_config: Mapped[ReceiverConfigRow] = relationship()
    observation_log: Mapped[ObservationLogRow | None] = relationship(back_populates="run")
    decision_log: Mapped[DecisionLogRow | None] = relationship(back_populates="run")
    metrics_row: Mapped[MetricsRow | None] = relationship(back_populates="run")
    artifacts: Mapped[list[ArtifactRow]] = relationship(back_populates="run")


class ObservationLogRow(Base):
    __tablename__ = "observation_logs"
    __table_args__ = (UniqueConstraint("run_id", name="uq_observation_logs_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.domain_run_id"), nullable=False
    )
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default=SCHEMA_VERSION)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[RunRow] = relationship(back_populates="observation_log")


class DecisionLogRow(Base):
    __tablename__ = "decision_logs"
    __table_args__ = (UniqueConstraint("run_id", name="uq_decision_logs_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.domain_run_id"), nullable=False
    )
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default=SCHEMA_VERSION)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_with_p_hit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_with_p_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_with_time_forecast: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[RunRow] = relationship(back_populates="decision_log")


class MetricsRow(Base):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("run_id", name="uq_metrics_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.domain_run_id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default=SCHEMA_VERSION)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    pd: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    pfa: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    sensitivity: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    average_intercept_rate: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    average_reward: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    correct_predictions: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    average_intercept_time_error: Mapped[float | None] = mapped_column(
        Float, nullable=True, index=True
    )
    event_interception_ratio: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[RunRow] = relationship(back_populates="metrics_row")


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("run_id", "artifact_type", "relative_path", name="uq_artifacts_run_type_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.domain_run_id"), nullable=True, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[RunRow | None] = relationship(back_populates="artifacts")


class TrainingRunRow(Base):
    __tablename__ = "training_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.domain_run_id"), nullable=False, index=True
    )
    algorithm: Mapped[str] = mapped_column(String(128), nullable=False)
    split_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    hyperparameters_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    model_bundle_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model_bundle_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mlflow_experiment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelVersionRow(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("registered_name", "version", name="uq_model_versions_name_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registered_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.domain_run_id"), nullable=False
    )
    bundle_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unvalidated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


EXPECTED_TABLES: tuple[str, ...] = (
    "data_sources",
    "scenarios",
    "ground_truths",
    "receiver_configs",
    "runs",
    "observation_logs",
    "decision_logs",
    "metrics",
    "artifacts",
    "training_runs",
    "model_versions",
)


def dumps_json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"), default=str)


def loads_json(text: str) -> Any:
    import json

    return json.loads(text)
