from __future__ import annotations

from pathlib import Path

import pytest
from tests.conftest import TINY_SIM

from smartscan.cli import main
from smartscan.storage.db import sqlite_url


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", sqlite_url(tmp_path / "mlflow.db"))
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("MLFLOW_ENABLED", "1")


def test_cli_db_upgrade_and_persist_list_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch, tmp_path)
    cfg = tmp_path / "tiny.yaml"
    cfg.write_text(
        "\n".join(
            [
                'schema_version: "1.0.0"',
                f"seed: {TINY_SIM['seed']}",
                f"dt_s: {TINY_SIM['dt_s']}",
                f"duration_s: {TINY_SIM['duration_s']}",
                f"band_plan_id: {TINY_SIM['band_plan_id']}",
                f"scenario_id: {TINY_SIM['scenario_id']}",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["db", "upgrade"]) == 0
    assert main(
        [
            "run",
            "--config",
            str(cfg),
            "--strategy",
            "sequential",
            "--persist",
            "--track",
            "--seed",
            "42",
        ]
    ) == 0
    assert main(["runs", "list", "--strategy", "sequential", "--order-by", "avg_intercept_rate"]) == 0
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository

    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=False)
    rows = repo.list_runs()
    assert len(rows) == 1
    domain_run_id = str(rows[0].domain_run_id)
    assert main(["runs", "verify", domain_run_id]) == 0
    assert main(["mlflow", "reconcile", "--all"]) == 0
    assert main(["mlflow", "reconcile", "--run", domain_run_id]) == 0


def test_cli_run_requires_persist() -> None:
    assert main(["run", "--config", "configs/demo.yaml"]) == 2


def test_cli_mlflow_serve_uses_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch, tmp_path)
    captured: dict[str, list[str]] = {}

    def fake_call(argv: list[str]) -> int:
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr("subprocess.call", fake_call)
    assert main(["mlflow", "serve", "--host", "127.0.0.1", "--port", "5000"]) == 0
    argv = captured["argv"]
    assert "-m" in argv and "mlflow" in argv and "server" in argv
    assert "--backend-store-uri" in argv
    assert "--artifacts-destination" in argv


def test_cli_reconcile_requires_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, tmp_path)
    assert main(["db", "upgrade"]) == 0
    assert main(["mlflow", "reconcile"]) == 2
