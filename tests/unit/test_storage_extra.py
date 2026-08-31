from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from tests.conftest import TINY_SIM

from smartscan.config import SimulateConfig
from smartscan.rf.environment import simulate
from smartscan.storage.artifacts import ArtifactStore
from smartscan.storage.db import StorageSettings, current_git_sha, sqlite_url
from smartscan.storage.models import dumps_json, loads_json
from smartscan.storage.pipeline import build_repository, persist_baseline_run
from smartscan.storage.repositories import RunFilters, RunRepository
from smartscan.storage.tracking import finite_metrics
from smartscan.types import SmartScanError


def test_persist_unknown_strategy_marks_failed(
    domain_repo: RunRepository, receiver_config
) -> None:
    with pytest.raises(SmartScanError):
        persist_baseline_run(
            simulate_config=TINY_SIM,
            receiver_config=receiver_config,
            strategy="not-a-strategy",
            repo=domain_repo,
            track=False,
        )
    listed = domain_repo.list_runs(RunFilters(status="failed"))
    assert len(listed) == 1
    stored = domain_repo.get_run(listed[0].domain_run_id)
    assert stored.status == "failed"
    with pytest.raises(SmartScanError, match="logs are not attached"):
        domain_repo.recompute_and_verify(listed[0].domain_run_id)


def test_unknown_ids(domain_repo: RunRepository, receiver_config) -> None:
    with pytest.raises(SmartScanError, match="Unknown scenario"):
        domain_repo.start_run(uuid4(), receiver_config, "sequential", {"receiver": 0})
    with pytest.raises(SmartScanError, match="Unknown domain_run_id"):
        domain_repo.get_run(uuid4())


def test_save_metrics_twice(domain_repo: RunRepository, receiver_config) -> None:
    domain_run_id = persist_baseline_run(
        simulate_config=dict(TINY_SIM),
        receiver_config=receiver_config,
        strategy="sequential",
        repo=domain_repo,
        track=False,
    )
    stored = domain_repo.get_run(domain_run_id)
    assert stored.evaluation is not None
    with pytest.raises(SmartScanError, match="already saved"):
        domain_repo.save_metrics(domain_run_id, stored.evaluation)


def test_list_date_and_scenario_filters(domain_repo: RunRepository, receiver_config) -> None:
    persist_baseline_run(
        simulate_config=TINY_SIM,
        receiver_config=receiver_config,
        strategy="sequential",
        repo=domain_repo,
        track=False,
    )
    now = datetime.now(UTC)
    assert domain_repo.list_runs(RunFilters(scenario_name="sparse"))
    assert not domain_repo.list_runs(RunFilters(created_after=now + timedelta(days=1)))
    assert domain_repo.list_runs(RunFilters(created_before=now + timedelta(days=1)))


def test_put_ground_truth_and_bad_receiver_run(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "art")
    truth = simulate(SimulateConfig.model_validate(TINY_SIM))
    ref = store.put_ground_truth("ground_truth/x.npz", truth)
    reused = store.put_ground_truth("ground_truth/x.npz", truth, overwrite=False)
    assert reused.reused
    assert reused.sha256 == ref.sha256
    store.put_file("copied.bin", store.resolve("ground_truth/x.npz"))
    with pytest.raises(SmartScanError, match="ReceiverRun"):
        store.put_receiver_run("runs/x.npz", object())


def test_build_repository_upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "d.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "a"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", sqlite_url(tmp_path / "m.db"))
    monkeypatch.setenv("MLFLOW_ENABLED", "0")
    settings = StorageSettings.from_env(root=tmp_path)
    repo = build_repository(settings, track=True, upgrade=True)
    assert isinstance(repo, RunRepository)


def test_finite_metrics_and_json_helpers() -> None:
    assert finite_metrics({"a": 1.0, "b": None, "c": float("nan"), "d": float("inf")}) == {"a": 1.0}
    payload = dumps_json({"z": 1, "a": 2})
    assert list(loads_json(payload).keys()) == ["a", "z"]


def test_git_sha_with_dummy_git_dir(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert current_git_sha(tmp_path) is None


def test_settings_db_url_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = sqlite_url(tmp_path / "custom.db")
    monkeypatch.setenv("SMARTSCAN_DB_URL", url)
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", sqlite_url(tmp_path / "ml.db"))
    settings = StorageSettings.from_env(root=tmp_path)
    assert settings.domain_db_url == url
