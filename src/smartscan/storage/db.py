"""Engine, SQLite URL helpers, Alembic upgrade, and storage settings."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from smartscan.config import project_root
from smartscan.types import SmartScanError


def sqlite_url(path: str | Path) -> str:
    """Return a SQLAlchemy SQLite URL for an absolute filesystem path."""

    resolved = Path(path).expanduser().resolve()
    return "sqlite:///" + resolved.as_posix()


def sqlite_path_from_url(url: str) -> Path | None:
    """Extract a filesystem path from a SQLite URL, or None if not SQLite."""

    if not url.startswith("sqlite:"):
        return None
    rest = url.split("://", 1)[-1]
    if rest.startswith("//"):
        rest = rest[2:]
    elif rest.startswith("/"):
        rest = rest[1:]
    if not rest or rest == ":memory:":
        return None
    return Path(rest).expanduser().resolve()


def assert_separate_sqlite(domain_url: str, mlflow_url: str) -> None:
    domain_path = sqlite_path_from_url(domain_url)
    mlflow_path = sqlite_path_from_url(mlflow_url)
    if domain_path is not None and mlflow_path is not None and domain_path == mlflow_path:
        raise SmartScanError(
            "Domain DB and MLflow DB must not share the same SQLite file "
            f"({domain_path}). Use data/smartscan.db and data/mlflow.db."
        )


def apply_sqlite_pragmas(engine: Engine) -> None:
    """Enable foreign keys on every SQLite connection."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine_from_url(url: str) -> Engine:
    """Create an engine. SQLite gets FK-on; PostgreSQL URLs are accepted as-is.

    Non-SQLite URLs are parsed and passed through without schema changes. The
    DBAPI driver is only imported if a connection is actually opened.
    """

    parsed = make_url(url)
    kwargs: dict[str, Any] = {"future": True}
    if parsed.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        engine = create_engine(parsed, **kwargs)
        apply_sqlite_pragmas(engine)
        return engine
    return create_engine(parsed, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def alembic_ini_path() -> Path:
    return Path(__file__).resolve().parent / "alembic.ini"


def upgrade_database(url: str, *, revision: str = "head") -> None:
    """Run Alembic migrations against *url* (empty file is allowed)."""

    from alembic import command
    from alembic.config import Config

    ini = alembic_ini_path()
    if not ini.is_file():
        raise SmartScanError(f"alembic.ini not found at {ini}")
    if url.startswith("sqlite:"):
        path = sqlite_path_from_url(url)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    command.upgrade(cfg, revision)
    ensure_run_protocol_columns(url)


OPTIONAL_RUN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("protocol_id", "VARCHAR(64)"),
    ("model_version", "VARCHAR(64)"),
    ("bundle_fingerprint", "VARCHAR(64)"),
    ("duration_s", "FLOAT"),
)


def ensure_run_protocol_columns(url: str) -> None:
    """Additive SQLite columns for protocol linkage. Safe on 0001 create_all DBs."""

    if not url.startswith("sqlite:"):
        return
    from sqlalchemy import text

    engine = create_engine_from_url(url)
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(runs)")).fetchall()
            if not rows:
                return
            existing = {str(row[1]) for row in rows}
            for name, decl in OPTIONAL_RUN_COLUMNS:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE runs ADD COLUMN {name} {decl}"))
    finally:
        engine.dispose()


def current_git_sha(root: Path | None = None) -> str | None:
    base = root or project_root()
    if not (base / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=base,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    sha = completed.stdout.strip()
    return sha or None


def _abs_under_root(raw: str, root: Path) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _mlflow_uri_from_raw(raw: str, root: Path) -> str:
    if raw.startswith("sqlite:///"):
        rest = raw[len("sqlite:///") :]
        path = Path(rest)
        if path.is_absolute() or (len(rest) >= 2 and rest[1] == ":"):
            return sqlite_url(path)
        return sqlite_url(root / rest)
    return raw


@dataclass(frozen=True)
class StorageSettings:
    """Project-root-relative domain DB, artifact store, and MLflow locations."""

    project_root: Path
    domain_db_path: Path
    domain_db_url: str
    artifact_root: Path
    mlflow_tracking_uri: str
    mlflow_artifact_root: Path
    mlflow_host: str = "127.0.0.1"
    mlflow_port: int = 5000
    mlflow_enabled: bool = True

    @classmethod
    def from_env(cls, root: Path | None = None) -> StorageSettings:
        base = (root or project_root()).resolve()
        db_raw = os.environ.get("SMARTSCAN_DB", "data/smartscan.db")
        domain_path = _abs_under_root(db_raw, base)
        if os.environ.get("SMARTSCAN_DB_URL"):
            domain_url = os.environ["SMARTSCAN_DB_URL"]
        else:
            domain_url = sqlite_url(domain_path)
        artifact_raw = os.environ.get("SMARTSCAN_ARTIFACT_ROOT", "artifacts/store")
        mlflow_raw = os.environ.get("MLFLOW_BACKEND_STORE_URI", "sqlite:///data/mlflow.db")
        mlflow_uri = _mlflow_uri_from_raw(mlflow_raw, base)
        mlflow_art = _abs_under_root(
            os.environ.get("MLFLOW_ARTIFACT_ROOT", "artifacts/mlflow"), base
        )
        host = os.environ.get("MLFLOW_HOST", "127.0.0.1")
        port = int(os.environ.get("MLFLOW_PORT", "5000"))
        enabled_raw = os.environ.get("MLFLOW_ENABLED", "1").strip().lower()
        enabled = enabled_raw not in {"0", "false", "no", "off"}
        settings = cls(
            project_root=base,
            domain_db_path=domain_path,
            domain_db_url=domain_url,
            artifact_root=_abs_under_root(artifact_raw, base),
            mlflow_tracking_uri=mlflow_uri,
            mlflow_artifact_root=mlflow_art,
            mlflow_host=host,
            mlflow_port=port,
            mlflow_enabled=enabled,
        )
        settings.assert_db_separation()
        return settings

    def assert_db_separation(self) -> None:
        assert_separate_sqlite(self.domain_db_url, self.mlflow_tracking_uri)

    def ensure_directories(self) -> None:
        self.domain_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.mlflow_artifact_root.mkdir(parents=True, exist_ok=True)
        mlflow_path = sqlite_path_from_url(self.mlflow_tracking_uri)
        if mlflow_path is not None:
            mlflow_path.parent.mkdir(parents=True, exist_ok=True)
