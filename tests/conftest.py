from __future__ import annotations

from pathlib import Path

import pytest

from smartscan.config import load_yaml, project_root
from smartscan.receiver.detector import load_receiver_config
from smartscan.storage.artifacts import ArtifactStore
from smartscan.storage.db import (
    create_engine_from_url,
    create_session_factory,
    sqlite_url,
    upgrade_database,
)
from smartscan.storage.repositories import RunRepository
from smartscan.storage.tracking import NoOpTracker
from tests.fixtures.tsrd import write_tsrd_fixture

TINY_SIM = {
    "seed": 42,
    "dt_s": 0.001,
    "duration_s": 0.04,
    "band_plan_id": "demo_2_18",
    "scenario_id": "sparse",
}


@pytest.fixture
def tsrd_stare_path(tmp_path: Path) -> Path:
    return write_tsrd_fixture(tmp_path / "stare.h5", mode="stare")


@pytest.fixture
def tsrd_scan_path(tmp_path: Path) -> Path:
    return write_tsrd_fixture(tmp_path / "scan.h5", mode="scan")


@pytest.fixture
def receiver_config():
    return load_receiver_config(load_yaml(project_root() / "configs" / "receiver.yaml"))


@pytest.fixture
def domain_repo(tmp_path: Path) -> RunRepository:
    url = sqlite_url(tmp_path / "smartscan.db")
    upgrade_database(url)
    engine = create_engine_from_url(url)
    store = ArtifactStore(tmp_path / "store")
    return RunRepository(create_session_factory(engine), store, NoOpTracker())
