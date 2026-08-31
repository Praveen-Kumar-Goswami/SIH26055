"""MLflow experiment tracking linked by domain_run_id.

Domain DB writes and MLflow writes are not one ACID transaction. Reconcile
looks up an existing MLflow run by the ``domain_run_id`` tag before creating
a new one, so retries do not duplicate runs.
"""

from __future__ import annotations

import sys
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from smartscan.storage.constants import (
    EXPERIMENT_BASELINES,
    MLFLOW_EXPERIMENTS,
    PROTECTED_MODEL_ALIASES,
    VALIDATION_VALIDATED,
)
from smartscan.storage.db import StorageSettings, sqlite_url
from smartscan.types import SmartScanError


@dataclass
class TrackingPayload:
    domain_run_id: UUID
    experiment: str = EXPERIMENT_BASELINES
    params: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    artifact_files: list[Path] = field(default_factory=list)


class ExperimentTracker(Protocol):
    """Tracking backend. Production uses MLflow; tests may use NoOpTracker."""

    def log_run(self, payload: TrackingPayload) -> str | None:
        """Create or reuse an MLflow run. Returns mlflow_run_id or None."""

    def find_by_domain_id(self, domain_run_id: UUID) -> str | None:
        """Return an existing MLflow run id tagged with domain_run_id."""

    def find_all_by_domain_id(self, domain_run_id: UUID) -> list[str]:
        """Return every MLflow run tagged with domain_run_id (oldest first)."""

    def log_model_bundle(
        self,
        *,
        mlflow_run_id: str,
        local_dir: Path,
        artifact_path: str = "model",
    ) -> None:
        """Log a local bundle directory onto an existing MLflow run."""

    def register_model_version(
        self,
        *,
        name: str,
        source_run_id: str,
        artifact_path: str = "model",
        alias: str | None = None,
        validation_status: str = "unvalidated",
    ) -> str:
        """Register a version. Refuses champion/production unless validated."""

    def set_model_alias(
        self,
        name: str,
        alias: str,
        version: str,
        *,
        validation_status: str = "unvalidated",
    ) -> None:
        """Set a registry alias. Refuses champion/production unless validated."""


def as_mlflow_artifact_uri(path: str | Path) -> str:
    """Return a file:// URI so Windows drive letters are not treated as schemes."""

    return Path(path).resolve().as_uri()


def refuse_protected_alias(alias: str | None, validation_status: str) -> None:
    if alias is None:
        return
    if alias.casefold() in PROTECTED_MODEL_ALIASES and validation_status != VALIDATION_VALIDATED:
        raise SmartScanError(
            f"Refusing to assign {alias!r} to an unvalidated model bundle. "
            "Stage 4 does not register an untrained placeholder as champion."
        )


class NoOpTracker:
    """Disabled tracking. Simulations still persist to the domain store."""

    def log_run(self, payload: TrackingPayload) -> str | None:
        return None

    def find_by_domain_id(self, domain_run_id: UUID) -> str | None:
        return None

    def find_all_by_domain_id(self, domain_run_id: UUID) -> list[str]:
        return []

    def log_model_bundle(
        self,
        *,
        mlflow_run_id: str,
        local_dir: Path,
        artifact_path: str = "model",
    ) -> None:
        return None

    def register_model_version(
        self,
        *,
        name: str,
        source_run_id: str,
        artifact_path: str = "model",
        alias: str | None = None,
        validation_status: str = "unvalidated",
    ) -> str:
        refuse_protected_alias(alias, validation_status)
        return "0"

    def set_model_alias(
        self,
        name: str,
        alias: str,
        version: str,
        *,
        validation_status: str = "unvalidated",
    ) -> None:
        refuse_protected_alias(alias, validation_status)


def _is_deleted_experiment(experiment: Any) -> bool:
    return str(getattr(experiment, "lifecycle_stage", "") or "").lower() == "deleted"


class MLflowTracker:
    """Local file/SQLite MLflow backend. Model Registry is available via SQL store."""

    def __init__(
        self,
        tracking_uri: str,
        *,
        artifact_root: Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.tracking_uri = tracking_uri
        self.artifact_root = Path(artifact_root).resolve() if artifact_root is not None else None
        self.enabled = enabled
        self._ensured = False

    @classmethod
    def from_settings(cls, settings: StorageSettings) -> MLflowTracker:
        return cls(
            settings.mlflow_tracking_uri,
            artifact_root=settings.mlflow_artifact_root,
            enabled=settings.mlflow_enabled,
        )

    def _client(self) -> Any:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(self.tracking_uri)
        return MlflowClient(tracking_uri=self.tracking_uri)

    def ensure_experiments(self) -> None:
        if not self.enabled:
            return
        import mlflow

        mlflow.set_tracking_uri(self.tracking_uri)
        client = self._client()
        artifact: str | None = None
        if self.artifact_root is not None:
            self.artifact_root.mkdir(parents=True, exist_ok=True)
            artifact = as_mlflow_artifact_uri(self.artifact_root)
        for name in MLFLOW_EXPERIMENTS:
            existing = client.get_experiment_by_name(name)
            if existing is not None and _is_deleted_experiment(existing):
                client.restore_experiment(existing.experiment_id)
                continue
            if existing is None:
                if artifact:
                    client.create_experiment(name, artifact_location=artifact)
                else:
                    client.create_experiment(name)
        self._ensured = True

    def find_by_domain_id(self, domain_run_id: UUID) -> str | None:
        found = self.find_all_by_domain_id(domain_run_id)
        return found[0] if found else None

    def find_all_by_domain_id(self, domain_run_id: UUID) -> list[str]:
        if not self.enabled:
            return []
        import mlflow

        mlflow.set_tracking_uri(self.tracking_uri)
        self.ensure_experiments()
        client = self._client()
        tag = str(domain_run_id)
        found: list[str] = []
        for name in MLFLOW_EXPERIMENTS:
            experiment = client.get_experiment_by_name(name)
            if experiment is None or _is_deleted_experiment(experiment):
                continue
            runs = client.search_runs(
                [experiment.experiment_id],
                filter_string=f"tags.domain_run_id = '{tag}'",
                max_results=20,
            )
            for run in runs:
                run_id = str(run.info.run_id)
                if run_id not in found:
                    found.append(run_id)
        return found

    def log_run(self, payload: TrackingPayload) -> str | None:
        if not self.enabled:
            return None
        existing = self.find_by_domain_id(payload.domain_run_id)
        if existing is not None:
            return existing
        import mlflow

        mlflow.set_tracking_uri(self.tracking_uri)
        self.ensure_experiments()
        experiment = payload.experiment or EXPERIMENT_BASELINES
        client = self._client()
        record = client.get_experiment_by_name(experiment)
        if record is None or _is_deleted_experiment(record):
            self.ensure_experiments()
            record = client.get_experiment_by_name(experiment)
        if record is None:
            raise SmartScanError(f"MLflow experiment {experiment!r} is not available.")
        if _is_deleted_experiment(record):
            client.restore_experiment(record.experiment_id)
            record = client.get_experiment(record.experiment_id)
        mlflow.set_experiment(experiment_id=str(record.experiment_id))
        tags = dict(payload.tags)
        tags["domain_run_id"] = str(payload.domain_run_id)
        with mlflow.start_run(tags=tags) as active:
            for param_key, param_value in payload.params.items():
                mlflow.log_param(param_key, param_value)
            for metric_key, metric_value in payload.metrics.items():
                number = float(metric_value)
                if number != number or abs(number) == float("inf"):
                    continue
                mlflow.log_metric(metric_key, number)
            for path in payload.artifact_files:
                file_path = Path(path)
                if file_path.is_file():
                    mlflow.log_artifact(str(file_path))
            return str(active.info.run_id)

    def log_model_bundle(
        self,
        *,
        mlflow_run_id: str,
        local_dir: Path,
        artifact_path: str = "model",
    ) -> None:
        if not self.enabled:
            return
        import mlflow

        mlflow.set_tracking_uri(self.tracking_uri)
        source = Path(local_dir)
        if not source.is_dir():
            raise SmartScanError(f"Model bundle directory not found: {source}")
        with mlflow.start_run(run_id=mlflow_run_id):
            mlflow.log_artifacts(str(source), artifact_path=artifact_path)

    def register_model_version(
        self,
        *,
        name: str,
        source_run_id: str,
        artifact_path: str = "model",
        alias: str | None = None,
        validation_status: str = "unvalidated",
    ) -> str:
        refuse_protected_alias(alias, validation_status)
        if not self.enabled:
            return "0"
        from mlflow.exceptions import MlflowException

        client = self._client()
        try:
            client.get_registered_model(name)
        except MlflowException:
            client.create_registered_model(name)
        source = f"runs:/{source_run_id}/{artifact_path}"
        mv = client.create_model_version(name, source, run_id=source_run_id)
        version = str(mv.version)
        if alias:
            client.set_registered_model_alias(name, alias, version)
        return version

    def set_model_alias(
        self,
        name: str,
        alias: str,
        version: str,
        *,
        validation_status: str = "unvalidated",
    ) -> None:
        refuse_protected_alias(alias, validation_status)
        if not self.enabled:
            return
        client = self._client()
        client.set_registered_model_alias(name, alias, version)

    def experiment_id(self, name: str = EXPERIMENT_BASELINES) -> str | None:
        if not self.enabled:
            return None
        self.ensure_experiments()
        experiment = self._client().get_experiment_by_name(name)
        if experiment is None or _is_deleted_experiment(experiment):
            return None
        return str(experiment.experiment_id)


class FailingTracker:
    """Test double: tracking always fails while domain writes proceed."""

    def __init__(self, message: str = "mlflow unavailable") -> None:
        self.message = message

    def log_run(self, payload: TrackingPayload) -> str | None:
        raise RuntimeError(self.message)

    def find_by_domain_id(self, domain_run_id: UUID) -> str | None:
        raise RuntimeError(self.message)

    def find_all_by_domain_id(self, domain_run_id: UUID) -> list[str]:
        raise RuntimeError(self.message)

    def log_model_bundle(
        self,
        *,
        mlflow_run_id: str,
        local_dir: Path,
        artifact_path: str = "model",
    ) -> None:
        raise RuntimeError(self.message)

    def register_model_version(
        self,
        *,
        name: str,
        source_run_id: str,
        artifact_path: str = "model",
        alias: str | None = None,
        validation_status: str = "unvalidated",
    ) -> str:
        refuse_protected_alias(alias, validation_status)
        raise RuntimeError(self.message)

    def set_model_alias(
        self,
        name: str,
        alias: str,
        version: str,
        *,
        validation_status: str = "unvalidated",
    ) -> None:
        refuse_protected_alias(alias, validation_status)
        raise RuntimeError(self.message)


def mlflow_serve_argv(
    *,
    host: str = "127.0.0.1",
    port: int = 5000,
    backend_store_uri: str | None = None,
    artifacts_destination: str | None = None,
    root: Path | None = None,
) -> list[str]:
    """Build ``mlflow server`` argv. Paths are resolved from the project root."""

    from smartscan.config import project_root

    base = (root or project_root()).resolve()
    backend = backend_store_uri or sqlite_url(base / "data" / "mlflow.db")
    dest = artifacts_destination or str((base / "artifacts" / "mlflow").resolve())
    return [
        sys.executable,
        "-m",
        "mlflow",
        "server",
        "--host",
        host,
        "--port",
        str(port),
        "--backend-store-uri",
        backend,
        "--artifacts-destination",
        dest,
    ]


def warn_tracking_failure(domain_run_id: UUID, exc: BaseException) -> None:
    message = (
        f"MLflow tracking failed for domain_run_id={domain_run_id}; "
        f"the domain run is preserved. Reconcile later. ({exc})"
    )
    warnings.warn(message, UserWarning, stacklevel=2)


def finite_metrics(values: Mapping[str, float | None]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in values.items():
        if value is None:
            continue
        number = float(value)
        if number != number or abs(number) == float("inf"):
            continue
        out[key] = number
    return out
