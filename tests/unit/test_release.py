from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from smartscan.config import project_root
from smartscan.ml.evaluate import GateResult, SeedRow
from smartscan.release.coverage import write_requirements_coverage
from smartscan.release.frozen import current_hashes, require_frozen_hashes
from smartscan.release.perf import measure_demo_profile, peak_rss_bytes
from smartscan.release.resolve import resolve_best_available
from smartscan.types import SmartScanError

FROZEN_FP = "4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4"


def test_frozen_hashes_match_stage5_record() -> None:
    hashes = require_frozen_hashes()
    assert hashes["held_out_manifest_content_fingerprint"] == FROZEN_FP
    now = current_hashes()
    assert now == hashes


def test_refuse_hash_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    cfg = root / "configs"
    cfg.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    record = {
        "held_out_manifest_sha256": "aaa",
        "benchmark_final_yaml_sha256": "bbb",
        "held_out_manifest_content_fingerprint": "ccc",
    }
    (cfg / "frozen_hashes.json").write_text(json.dumps(record), encoding="utf-8")
    (cfg / "held_out_manifest.json").write_text(json.dumps({"pairs": []}), encoding="utf-8")
    (cfg / "benchmark_final.yaml").write_text("schema_version: '1.0.0'\n", encoding="utf-8")
    monkeypatch.setenv("SMARTSCAN_ROOT", str(root))
    with pytest.raises(SmartScanError, match="Refusing final evidence"):
        require_frozen_hashes()


def test_moved_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTSCAN_ROOT", str(tmp_path))
    assert project_root() == tmp_path.resolve()


def test_resolve_explicit_is_not_champion() -> None:
    resolved = resolve_best_available("sequential")
    assert resolved.strategy == "sequential"
    assert resolved.source == "explicit"
    assert "not resolved through best-available" in resolved.note


def test_resolve_cts_when_bundle_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTSCAN_MODEL_DIR", str(tmp_path / "missing-bundle"))
    monkeypatch.setattr(
        "smartscan.release.resolve.load_performance_gate",
        lambda: {"performance_gate_passed": False, "alias": "candidate"},
    )
    resolved = resolve_best_available("best-available")
    assert resolved.strategy == "contextual-thompson"
    assert resolved.source == "contextual_thompson"
    assert "not champion" in resolved.note


def test_resolve_candidate_not_renamed_champion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "bundle"
    model_dir.mkdir()
    (model_dir / "manifest.json").write_text(
        json.dumps({"registered_name": "SmartScanScheduler", "model_version": "2", "has_ppo": True}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMARTSCAN_MODEL_DIR", str(model_dir))
    monkeypatch.setattr(
        "smartscan.release.resolve.load_performance_gate",
        lambda: {"performance_gate_passed": False, "alias": "candidate"},
    )
    monkeypatch.setattr("smartscan.release.resolve._try_bundle", lambda _path: object())
    resolved = resolve_best_available("best-available")
    assert resolved.strategy == "ppo"
    assert resolved.source == "candidate"
    assert resolved.source != "champion"
    assert "Not renamed champion" in resolved.note
    assert resolved.model_name == "SmartScanScheduler"


def test_resolve_champion_only_when_gate_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "bundle"
    model_dir.mkdir()
    (model_dir / "manifest.json").write_text(
        json.dumps({"registered_name": "SmartScanScheduler", "model_version": "9", "has_ppo": True}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SMARTSCAN_MODEL_DIR", str(model_dir))
    monkeypatch.setattr(
        "smartscan.release.resolve.load_performance_gate",
        lambda: {"performance_gate_passed": True, "alias": "champion"},
    )
    monkeypatch.setattr("smartscan.release.resolve._try_bundle", lambda _path: object())
    resolved = resolve_best_available("best-available")
    assert resolved.source == "champion"
    from smartscan.experiment_protocol import generation_from_bundle_path

    assert resolved.version == generation_from_bundle_path(model_dir)
    assert resolved.model_name == "SmartScanScheduler"


def test_requirements_coverage_has_no_gaps() -> None:
    payload = write_requirements_coverage(project_root() / "docs" / "evidence" / "requirements_coverage.json")
    assert payload["n_gaps"] == 0
    assert payload["robustness"]["n_gaps"] == 0
    assert payload["n_needs"] >= 10
    assert payload["robustness"]["n_cases"] >= 20


def test_demo_profile_probe_short() -> None:
    result = measure_demo_profile(duration_s=0.02)
    assert result["n_steps"] == 20
    assert result["n_bands"] == 16
    assert result["wall_s"] >= 0
    rss = peak_rss_bytes()
    assert rss is None or rss > 0


def test_benchmark_refuses_wrong_manifest_name() -> None:
    from smartscan.release.benchmark import run_final_benchmark

    with pytest.raises(SmartScanError, match="does not match frozen"):
        run_final_benchmark(
            config_path=project_root() / "configs" / "benchmark_final.yaml",
            manifest_arg="other_manifest.json",
            include_perf=False,
        )


def test_benchmark_mocked_eval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from smartscan.release import benchmark as bench_mod

    src = project_root()
    cfg = tmp_path / "configs"
    cfg.mkdir()
    for name in (
        "frozen_hashes.json",
        "held_out_manifest.json",
        "benchmark_final.yaml",
        "dashboard.yaml",
        "train_full.yaml",
    ):
        (cfg / name).write_bytes((src / "configs" / name).read_bytes())
    (tmp_path / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (tmp_path / "artifacts" / "models").mkdir(parents=True)
    monkeypatch.setenv("SMARTSCAN_ROOT", str(tmp_path))
    monkeypatch.setenv("SMARTSCAN_SKIP_PERF", "1")
    monkeypatch.setattr(bench_mod, "project_root", lambda: tmp_path)
    monkeypatch.setattr(
        bench_mod,
        "resolve_best_available",
        lambda _name="best-available": SimpleNamespace(
            strategy="contextual-thompson",
            source="contextual_thompson",
            model_dir=None,
            model_name=None,
            version=None,
            note="test",
            lines=lambda: ["resolved_source=contextual_thompson"],
        ),
    )
    rows = [
        SeedRow("sparse", 1000, "sequential", {"average_intercept_rate": 1.0}, 0, 1),
        SeedRow("sparse", 1000, "ppo", {"average_intercept_rate": 1.0}, 0, 1),
    ]
    gate = GateResult(False, ["synthetic failure"], {"air_means": {}}, {"sparse": False})

    def fake_eval(*args: object, **kwargs: object) -> tuple[list[SeedRow], GateResult]:
        return rows, gate

    import smartscan.ml.evaluate as eval_mod

    monkeypatch.setattr(eval_mod, "evaluate_held_out", fake_eval)

    out = tmp_path / "bench"
    summary = bench_mod.run_final_benchmark(
        config_path=tmp_path / "configs" / "benchmark_final.yaml",
        manifest_arg="held_out_manifest.json",
        track=False,
        output_dir=out,
        include_perf=False,
        reuse_existing=False,
    )
    assert summary["implementation_complete"] is True
    assert summary["gate"]["performance_gate_passed"] is False
    assert (out / "seed_metrics.csv").is_file()
    assert (out / "summary.json").is_file()


def test_benchmark_reuse_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from smartscan.release import benchmark as bench_mod

    gate_dir = tmp_path / "models"
    gate_dir.mkdir()
    payload = {
        "performance_gate_passed": False,
        "reasons": ["cached"],
        "family_pass": {"sparse": False},
        "comparisons": {},
        "n_rows": 2,
        "manifest_fingerprint": FROZEN_FP,
        "seed_rows": [
            {
                "scenario_id": "sparse",
                "seed": 1000,
                "strategy": "sequential",
                "metrics": {"average_intercept_rate": 1.0},
                "pfa_num": 0,
                "pfa_den": 1,
            }
        ],
    }
    gate_path = gate_dir / "held_out_gate.json"
    gate_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(bench_mod, "project_root", lambda: tmp_path)
    (tmp_path / "configs").mkdir()
    src = project_root()
    (tmp_path / "configs" / "frozen_hashes.json").write_bytes(
        (src / "configs" / "frozen_hashes.json").read_bytes()
    )
    (tmp_path / "configs" / "held_out_manifest.json").write_bytes(
        (src / "configs" / "held_out_manifest.json").read_bytes()
    )
    (tmp_path / "configs" / "benchmark_final.yaml").write_bytes(
        (src / "configs" / "benchmark_final.yaml").read_bytes()
    )
    (tmp_path / "configs" / "dashboard.yaml").write_bytes(
        (src / "configs" / "dashboard.yaml").read_bytes()
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setenv("SMARTSCAN_ROOT", str(tmp_path))
    monkeypatch.setenv("SMARTSCAN_SKIP_PERF", "1")
    (tmp_path / "artifacts" / "models").mkdir(parents=True)
    (tmp_path / "artifacts" / "models" / "held_out_gate.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    monkeypatch.setattr(
        bench_mod,
        "resolve_best_available",
        lambda _name="best-available": SimpleNamespace(
            strategy="ppo",
            source="candidate",
            model_dir=None,
            model_name="SmartScanScheduler",
            version="2",
            note="test",
            lines=lambda: ["resolved_source=candidate"],
        ),
    )
    out = tmp_path / "bench"
    summary = bench_mod.run_final_benchmark(
        config_path=tmp_path / "configs" / "benchmark_final.yaml",
        manifest_arg="held_out_manifest.json",
        output_dir=out,
        include_perf=False,
        reuse_existing=True,
    )
    assert summary["reused_existing_gate"] is True
    assert summary["n_seed_rows"] == 2
    assert summary["gate"]["reasons"] == ["cached"]


@pytest.mark.full_bench
def test_full_held_out_is_opt_in() -> None:
    import os

    if os.environ.get("SMARTSCAN_FULL_BENCH") != "1":
        pytest.skip("opt-in full 30-seed held-out; set SMARTSCAN_FULL_BENCH=1")
