from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from smartscan.storage.db import (
    StorageSettings,
    alembic_ini_path,
    assert_separate_sqlite,
    create_engine_from_url,
    current_git_sha,
    sqlite_path_from_url,
    sqlite_url,
    upgrade_database,
)
from smartscan.storage.models import EXPECTED_TABLES, RunRow
from smartscan.types import SmartScanError


def test_alembic_upgrade_empty_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "empty" / "smartscan.db"
    url = sqlite_url(db_path)
    upgrade_database(url)
    engine = create_engine_from_url(url)
    names = set(inspect(engine).get_table_names())
    assert set(EXPECTED_TABLES).issubset(names)
    assert "alembic_version" in names
    with engine.connect() as conn:
        pragma = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert int(pragma) == 1
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "0001"
        cols = {str(row[1]) for row in conn.execute(text("PRAGMA table_info(runs)")).fetchall()}
        assert "protocol_id" in cols
        assert "model_version" in cols
        assert "bundle_fingerprint" in cols
        assert "duration_s" in cols
    engine.dispose()


def test_alembic_offline_sql(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    url = sqlite_url(tmp_path / "off.db")
    cfg = Config(str(alembic_ini_path()))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(alembic_ini_path().parent / "alembic"))
    command.upgrade(cfg, "head", sql=True)


def test_foreign_keys_and_uniques(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "fk.db")
    upgrade_database(url)
    engine = create_engine_from_url(url)
    import uuid

    from smartscan.storage.db import create_session_factory, session_scope

    factory = create_session_factory(engine)
    with pytest.raises(IntegrityError):
        with session_scope(factory) as session:
            session.add(
                RunRow(
                    domain_run_id=uuid.uuid4(),
                    scenario_id=uuid.uuid4(),
                    receiver_config_id=uuid.uuid4(),
                    strategy="sequential",
                    seeds_json="{}",
                    status="running",
                )
            )
    engine.dispose()


def test_postgres_url_accepted_without_connect() -> None:
    from sqlalchemy.engine.url import make_url

    parsed = make_url("postgresql+psycopg://user:pass@localhost:5432/smartscan")
    assert parsed.get_backend_name() == "postgresql"
    engine = create_engine_from_url("sqlite:///:memory:")
    assert engine.dialect.name == "sqlite"
    engine.dispose()


def test_refuse_shared_sqlite_file(tmp_path: Path) -> None:
    path = tmp_path / "same.db"
    url = sqlite_url(path)
    with pytest.raises(SmartScanError, match="must not share"):
        assert_separate_sqlite(url, url)


def test_sqlite_path_helpers(tmp_path: Path) -> None:
    path = (tmp_path / "x.db").resolve()
    url = sqlite_url(path)
    assert sqlite_path_from_url(url) == path
    assert sqlite_path_from_url("postgresql://localhost/db") is None
    assert sqlite_path_from_url("sqlite:///:memory:") is None


def test_settings_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "domain.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "art"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", sqlite_url(tmp_path / "mlflow.db"))
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    settings = StorageSettings.from_env(root=tmp_path)
    settings.ensure_directories()
    assert settings.domain_db_path == (tmp_path / "domain.db").resolve()
    assert settings.artifact_root == (tmp_path / "art").resolve()
    assert "mlflow.db" in settings.mlflow_tracking_uri


def test_settings_reject_same_db_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = str(tmp_path / "one.db")
    monkeypatch.setenv("SMARTSCAN_DB", shared)
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", sqlite_url(tmp_path / "one.db"))
    with pytest.raises(SmartScanError, match="must not share"):
        StorageSettings.from_env(root=tmp_path)


def test_git_sha_without_repo(tmp_path: Path) -> None:
    assert current_git_sha(tmp_path) is None
