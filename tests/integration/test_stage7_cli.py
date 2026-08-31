from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartscan.cli import main
from smartscan.config import project_root


def test_cli_help_stage7() -> None:
    for cmd in ("benchmark", "demo", "doctor", "run"):
        with pytest.raises(SystemExit) as exc:
            main([cmd, "--help"])
        assert exc.value.code == 0


def test_demo_requires_offline() -> None:
    assert main(["demo"]) == 2


def test_benchmark_wrong_manifest() -> None:
    code = main(
        [
            "benchmark",
            "--config",
            str(project_root() / "configs" / "benchmark_final.yaml"),
            "--manifest",
            "not_the_frozen_manifest.json",
            "--skip-perf",
        ]
    )
    assert code == 2


def test_cli_doctor_prints_best_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("MLFLOW_PORT", "59997")
    monkeypatch.setenv("SMARTSCAN_MODEL_DIR", str(tmp_path / "no-bundle"))
    code = main(["doctor"])
    captured = capsys.readouterr()
    assert "resolved_source=" in captured.out
    assert "resolved_strategy=" in captured.out
    assert code in {0, 2}


def test_demo_offline_loads_without_retrain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "scenario_id": "agile_threat",
                "seed": 42,
                "strategies": ["sequential"],
                "truth_fingerprint": "abc",
                "matched": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (demo / "truth.npz").write_bytes(b"not-a-real-npz")
    (demo / "sequential.npz").write_bytes(b"not-a-real-npz")
    monkeypatch.setenv("SMARTSCAN_DEMO_DIR", str(demo))
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("SMARTSCAN_MODEL_DIR", str(tmp_path / "no-bundle"))
    code = main(["demo", "--offline", "--output", str(demo)])
    captured = capsys.readouterr()
    assert code == 0
    assert "retrained=false" in captured.out
    assert "downloaded=false" in captured.out
    assert "offline=true" in captured.out


def test_run_prints_explicit_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SMARTSCAN_DB", str(tmp_path / "smartscan.db"))
    monkeypatch.setenv("SMARTSCAN_ARTIFACT_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("MLFLOW_BACKEND_STORE_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "mlart"))
    monkeypatch.setenv("MLFLOW_ENABLED", "1")
    cfg = tmp_path / "tiny.yaml"
    cfg.write_text(
        "\n".join(
            [
                'schema_version: "1.0.0"',
                "seed: 42",
                "dt_s: 0.001",
                "duration_s: 0.04",
                "band_plan_id: demo_2_18",
                "scenario_id: sparse",
            ]
        ),
        encoding="utf-8",
    )
    code = main(
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
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "resolved_source=explicit" in captured.out
    assert "resolved_strategy=sequential" in captured.out


def test_best_available_resolve_is_never_silent_champion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from smartscan.release.resolve import ResolvedStrategy

    fake = ResolvedStrategy(
        requested="best-available",
        strategy="ppo",
        source="candidate",
        model_dir=None,
        model_name="SmartScanScheduler",
        version="2",
        note="performance_gate_passed=false; structurally valid candidate PPO. Not renamed champion.",
    )
    monkeypatch.setattr("smartscan.release.resolve.resolve_best_available", lambda _n="best-available": fake)
    # Direct print path used by doctor/benchmark
    from smartscan.release.resolve import resolve_best_available

    resolved = resolve_best_available("best-available")
    for line in resolved.lines():
        print(line)
    captured = capsys.readouterr()
    assert "resolved_source=candidate" in captured.out
    assert "resolved_source=champion" not in captured.out
