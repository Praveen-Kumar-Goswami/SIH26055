from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from tests.conftest import TINY_SIM

from smartscan.storage.db import sqlite_url
from smartscan.storage.pipeline import persist_baseline_run
from smartscan.storage.repositories import RunRepository
from smartscan.storage.tracking import (
    FailingTracker,
    MLflowTracker,
    NoOpTracker,
    TrackingPayload,
    as_mlflow_artifact_uri,
    mlflow_serve_argv,
    refuse_protected_alias,
)
from smartscan.types import SmartScanError


@pytest.fixture
def mlflow_tracker(tmp_path: Path) -> MLflowTracker:
    return MLflowTracker(
        sqlite_url(tmp_path / "mlflow.db"),
        artifact_root=tmp_path / "mlartifacts",
        enabled=True,
    )


def test_serve_argv_resolves_from_root(tmp_path: Path) -> None:
    argv = mlflow_serve_argv(root=tmp_path, host="127.0.0.1", port=5000)
    assert argv[1:4] == ["-m", "mlflow", "server"]
    assert "--host" in argv and "127.0.0.1" in argv
    assert "--port" in argv and "5000" in argv
    assert "--backend-store-uri" in argv
    assert "--artifacts-destination" in argv
    dest = argv[argv.index("--artifacts-destination") + 1]
    assert Path(dest) == (tmp_path / "artifacts" / "mlflow").resolve()
    assert as_mlflow_artifact_uri(tmp_path).startswith("file:")


def test_refuse_champion_alias() -> None:
    with pytest.raises(SmartScanError, match="champion"):
        refuse_protected_alias("champion", "unvalidated")
    with pytest.raises(SmartScanError, match="production"):
        NoOpTracker().set_model_alias("m", "production", "1", validation_status="unvalidated")
    with pytest.raises(SmartScanError, match="champion"):
        MLflowTracker("sqlite:///:memory:", enabled=False).register_model_version(
            name="x",
            source_run_id="abc",
            alias="champion",
            validation_status="unvalidated",
        )


def test_mlflow_roundtrip_ids_and_no_duplicate(
    domain_repo: RunRepository, receiver_config, mlflow_tracker: MLflowTracker
) -> None:
    domain_repo.tracker = mlflow_tracker
    domain_run_id = persist_baseline_run(
        simulate_config=TINY_SIM,
        receiver_config=receiver_config,
        strategy="sequential",
        repo=domain_repo,
        track=True,
    )
    stored = domain_repo.get_run(domain_run_id, verify_checksums=True)
    assert stored.sync_status == "synced"
    assert stored.identity.mlflow_run_id
    mlflow_id = stored.identity.mlflow_run_id
    assert mlflow_tracker.find_by_domain_id(domain_run_id) == mlflow_id
    again = domain_repo.reconcile_mlflow(domain_run_id)
    assert again[0].mlflow_run_id == mlflow_id
    assert mlflow_tracker.find_all_by_domain_id(domain_run_id) == [mlflow_id]

    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(mlflow_tracker.tracking_uri)
    client = MlflowClient(tracking_uri=mlflow_tracker.tracking_uri)
    run = client.get_run(mlflow_id)
    assert run.data.tags["domain_run_id"] == str(domain_run_id)
    assert "strategy" in run.data.params
    assert run.data.metrics  # real Stage 3 scalars, including zeros
    assert client.list_artifacts(mlflow_id)


def test_interrupted_onesided_then_reconcile(
    domain_repo: RunRepository, receiver_config, mlflow_tracker: MLflowTracker
) -> None:
    domain_repo.tracker = NoOpTracker()
    domain_run_id = persist_baseline_run(
        simulate_config=TINY_SIM,
        receiver_config=receiver_config,
        strategy="sequential",
        repo=domain_repo,
        track=True,
    )
    assert domain_repo.get_run(domain_run_id).sync_status == "pending"

    import mlflow

    mlflow.set_tracking_uri(mlflow_tracker.tracking_uri)
    mlflow_tracker.ensure_experiments()
    mlflow.set_experiment("smartscan-baselines")
    with mlflow.start_run(tags={"domain_run_id": str(domain_run_id)}) as active:
        mlflow.log_param("precreated", "1")
        pre_id = active.info.run_id

    domain_repo.tracker = mlflow_tracker
    result = domain_repo.reconcile_mlflow(domain_run_id)
    assert result[0].sync_status == "synced"
    assert result[0].mlflow_run_id == pre_id
    assert mlflow_tracker.find_all_by_domain_id(domain_run_id) == [pre_id]


def test_unavailable_then_reconcile(
    domain_repo: RunRepository, receiver_config, mlflow_tracker: MLflowTracker
) -> None:
    domain_repo.tracker = FailingTracker("down")
    with pytest.warns(UserWarning, match="MLflow tracking failed"):
        domain_run_id = persist_baseline_run(
            simulate_config=TINY_SIM,
            receiver_config=receiver_config,
            strategy="sequential",
            repo=domain_repo,
            track=True,
        )
    assert domain_repo.get_run(domain_run_id).status == "completed"
    assert domain_repo.get_run(domain_run_id).sync_status == "error"
    domain_repo.tracker = mlflow_tracker
    results = domain_repo.reconcile_mlflow(domain_run_id)
    assert results[0].sync_status == "synced"
    assert results[0].mlflow_run_id is not None
    all_pending = domain_repo.reconcile_mlflow(all_pending=True)
    assert all(item.sync_status == "synced" for item in all_pending)


def test_log_bundle_and_register_staging(mlflow_tracker: MLflowTracker, tmp_path: Path) -> None:
    payload = TrackingPayload(
        domain_run_id=uuid4(),
        params={"strategy": "sequential"},
        metrics={"pd": 0.0},
        tags={"status": "completed"},
    )
    run_id = mlflow_tracker.log_run(payload)
    assert run_id is not None
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "weights.json").write_text("{}", encoding="utf-8")
    mlflow_tracker.log_model_bundle(mlflow_run_id=run_id, local_dir=bundle)
    version = mlflow_tracker.register_model_version(
        name="smartscan-scheduler",
        source_run_id=run_id,
        artifact_path="model",
        alias="staging",
        validation_status="unvalidated",
    )
    assert version
    mlflow_tracker.set_model_alias(
        "smartscan-scheduler", "staging", version, validation_status="unvalidated"
    )


def test_log_run_restores_deleted_baseline_experiment(mlflow_tracker: MLflowTracker) -> None:
    mlflow_tracker.ensure_experiments()
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(mlflow_tracker.tracking_uri)
    client = MlflowClient(tracking_uri=mlflow_tracker.tracking_uri)
    experiment = client.get_experiment_by_name("smartscan-baselines")
    assert experiment is not None
    client.delete_experiment(experiment.experiment_id)
    deleted = client.get_experiment(experiment.experiment_id)
    assert str(deleted.lifecycle_stage).lower() == "deleted"
    run_id = mlflow_tracker.log_run(
        TrackingPayload(domain_run_id=uuid4(), metrics={"pd": 0.0}, params={"strategy": "sequential"})
    )
    assert run_id is not None
    restored = client.get_experiment_by_name("smartscan-baselines")
    assert restored is not None
    assert str(restored.lifecycle_stage).lower() == "active"
    assert client.get_run(run_id).info.experiment_id == restored.experiment_id


def test_disabled_tracker_and_failing_helpers() -> None:
    tracker = MLflowTracker("sqlite:///:memory:", enabled=False)
    payload = TrackingPayload(domain_run_id=uuid4())
    assert tracker.log_run(payload) is None
    assert tracker.find_by_domain_id(payload.domain_run_id) is None
    tracker.log_model_bundle(mlflow_run_id="x", local_dir=Path("."))
    assert tracker.register_model_version(name="n", source_run_id="x") == "0"
    tracker.set_model_alias("n", "staging", "1")
    fail = FailingTracker("x")
    with pytest.raises(RuntimeError):
        fail.log_model_bundle(mlflow_run_id="a", local_dir=Path("."))
    with pytest.raises(RuntimeError):
        fail.register_model_version(name="n", source_run_id="x")
    with pytest.raises(RuntimeError):
        fail.set_model_alias("n", "staging", "1")
    noop = NoOpTracker()
    noop.log_model_bundle(mlflow_run_id="a", local_dir=Path("."))
    assert noop.register_model_version(name="n", source_run_id="x") == "0"
    noop.set_model_alias("n", "staging", "1")
    assert noop.log_run(payload) is None
