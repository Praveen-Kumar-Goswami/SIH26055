"""Map SIH statement needs and robustness cases to code, tests, and evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smartscan.config import project_root

COVERAGE: list[dict[str, Any]] = [
    {
        "need": "Wideband search with a narrow instantaneous-bandwidth receiver",
        "code": [
            "src/smartscan/rf/bands.py",
            "src/smartscan/receiver/scanner.py",
            "src/smartscan/ml/policies.py",
        ],
        "tests": [
            "tests/unit/test_bands.py",
            "tests/unit/test_scanner.py",
            "tests/unit/test_contracts.py",
        ],
        "evidence": "configs/receiver.yaml scan_span_hz/receiver_ibw_hz >= 10",
    },
    {
        "need": "Truth per band and time slot",
        "code": ["src/smartscan/rf/environment.py", "src/smartscan/types.py"],
        "tests": ["tests/unit/test_environment.py", "tests/unit/test_io.py"],
        "evidence": "GroundTruth occupied/signal_power_w + content_fingerprint",
    },
    {
        "need": "Receiver hits and misses",
        "code": ["src/smartscan/receiver/detector.py", "src/smartscan/receiver/logs.py"],
        "tests": ["tests/unit/test_detector.py", "tests/unit/test_logs.py"],
        "evidence": "ObservationLog.detection and DecisionLog.hit",
    },
    {
        "need": "Intercept-time prediction",
        "code": ["src/smartscan/ml/predictor.py", "src/smartscan/ml/forecast.py"],
        "tests": ["tests/unit/test_ml_observable.py", "tests/unit/test_metrics.py"],
        "evidence": "average_intercept_time_error on DecisionLog forecasts",
    },
    {
        "need": "Interception-ratio prediction",
        "code": ["src/smartscan/ml/forecast.py", "src/smartscan/receiver/logs.py"],
        "tests": ["tests/unit/test_ml_estimators.py"],
        "evidence": "DecisionLog predicted_interception_ratio + CI",
    },
    {
        "need": "Periodic and frequency-agile emitters",
        "code": ["src/smartscan/rf/emitters.py", "src/smartscan/ml/periodicity.py"],
        "tests": ["tests/unit/test_emitters.py", "tests/unit/test_ml_estimators.py"],
        "evidence": "CircularScanEmitter / FrequencyAgileEmitter + agility scores",
    },
    {
        "need": "Optimal intercept of a periodic-scan emitter (search then phase-aligned dwell)",
        "code": ["src/smartscan/ml/periodicity.py", "src/smartscan/ml/policies.py"],
        "tests": ["tests/unit/test_periodic_intercept.py"],
        "evidence": "PeriodicInterceptSchedule from observable hits; not in the frozen gate set",
    },
    {
        "need": "New or threatening activity priority (assessed, not hidden labels)",
        "code": ["src/smartscan/ml/novelty.py", "src/smartscan/dashboard/pages.py"],
        "tests": ["tests/unit/test_ml_estimators.py", "tests/unit/test_dashboard_services.py"],
        "evidence": "public_priorities and novelty; evaluator threat_weight never policy-visible",
    },
    {
        "need": "Seven required figures of merit",
        "code": ["src/smartscan/metrics/engine.py", "src/smartscan/metrics/schemas.py"],
        "tests": ["tests/unit/test_metrics.py", "tests/unit/test_dashboard_plots.py"],
        "evidence": "docs/METRICS.md and artifacts/benchmark_final/seed_metrics.csv",
    },
    {
        "need": "Referenced public data adapters (TSRD optional; Wise optional)",
        "code": ["src/smartscan/data/turing.py", "src/smartscan/data/wise.py"],
        "tests": ["tests/unit/test_turing.py", "tests/unit/test_wise.py"],
        "evidence": "docs/DATA_SOURCES.md; tiny fixture tests; no fabricated Wise corpus",
    },
    {
        "need": "Reproducible comparative evidence (SQLite, MLflow, frozen splits)",
        "code": [
            "src/smartscan/storage/repositories.py",
            "src/smartscan/ml/evaluate.py",
            "src/smartscan/release/benchmark.py",
        ],
        "tests": [
            "tests/unit/test_storage_repositories.py",
            "tests/unit/test_ml_gate.py",
            "tests/unit/test_release.py",
        ],
        "evidence": "configs/frozen_hashes.json and docs/evidence/held_out_gate_summary.json",
    },
    {
        "need": "Protocol-separated evaluation evidence (never mix AIR across v2/v3/v4)",
        "code": [
            "src/smartscan/experiment_protocol.py",
            "src/smartscan/dashboard/identity.py",
            "src/smartscan/ml/strategy_registry.py",
        ],
        "tests": [
            "tests/unit/test_experiment_protocol.py",
            "tests/unit/test_strategy_audit.py",
        ],
        "evidence": "v2_frozen_gate / v3_research / v4_research; CROSS_PROTOCOL_MESSAGE",
    },
]

ROBUSTNESS: list[dict[str, Any]] = [
    {
        "area": "Environment",
        "case": "zero emitters",
        "tests": ["tests/integration/test_scenarios.py", "tests/unit/test_scanner.py"],
        "notes": "edge_zero scenario",
    },
    {
        "area": "Environment",
        "case": "one continuous",
        "tests": ["tests/unit/test_emitters.py", "tests/unit/test_environment.py"],
        "notes": "ContinuousEmitter",
    },
    {
        "area": "Environment",
        "case": "overlapping scans",
        "tests": ["tests/unit/test_scanner.py", "tests/integration/test_scenarios.py"],
        "notes": "dense / overlapping power is linear",
    },
    {
        "area": "Environment",
        "case": "many agile emitters",
        "tests": ["tests/unit/test_emitters.py", "tests/integration/test_scenarios.py"],
        "notes": "agile_threat",
    },
    {
        "area": "Environment",
        "case": "late unseen activity",
        "tests": ["tests/integration/test_scenarios.py"],
        "notes": "agile_threat late emitter",
    },
    {
        "area": "Timing",
        "case": "one-step events",
        "tests": ["tests/unit/test_turing.py"],
        "notes": "zero pulse-width impulse in TOA bin",
    },
    {
        "area": "Timing",
        "case": "long events",
        "tests": ["tests/unit/test_events.py", "tests/unit/test_metrics.py"],
        "notes": "maximal occupancy runs",
    },
    {
        "area": "Timing",
        "case": "boundary hops",
        "tests": ["tests/unit/test_emitters.py"],
        "notes": "FrequencyAgileEmitter hop closes event",
    },
    {
        "area": "Timing",
        "case": "final incomplete dwell",
        "tests": ["tests/unit/test_scanner.py", "tests/unit/test_metrics.py"],
        "notes": "n_incomplete_commands; incomplete excluded from FoMs",
    },
    {
        "area": "Timing",
        "case": "invalid noninteger latency",
        "tests": ["tests/unit/test_detector.py", "tests/unit/test_bands.py"],
        "notes": "duration_s/dt_s and tune latency must be integer steps",
    },
    {
        "area": "Detection",
        "case": "very low/high SNR",
        "tests": ["tests/unit/test_detector.py", "tests/unit/test_sensitivity.py"],
        "notes": "analytic Pd and Monte Carlo",
    },
    {
        "area": "Detection",
        "case": "pfa extremes within allowed config",
        "tests": ["tests/unit/test_detector.py", "tests/unit/test_logs.py"],
        "notes": "pfa_design 1e-3 default; rejected out of range",
    },
    {
        "area": "Detection",
        "case": "partial dwell",
        "tests": ["tests/unit/test_scanner.py"],
        "notes": "incomplete during tuning or final dwell",
    },
    {
        "area": "Detection",
        "case": "seed replay",
        "tests": ["tests/unit/test_io.py", "tests/integration/test_receive.py"],
        "notes": "same seeds reproduce logs",
    },
    {
        "area": "Data",
        "case": "missing/gated TSRD",
        "tests": ["tests/unit/test_turing.py", "tests/unit/test_turing_loader.py"],
        "notes": "tests never require HF_TOKEN or the 70 GB corpus",
    },
    {
        "area": "Data",
        "case": "one legal local .h5",
        "tests": ["tests/conftest.py", "tests/integration/test_scenarios.py"],
        "notes": "tiny generated PulseTrain fixture",
    },
    {
        "area": "Data",
        "case": "stare truth vs scan observations",
        "tests": ["tests/unit/test_turing.py"],
        "notes": "occupancy_is_observation_not_truth",
    },
    {
        "area": "Data",
        "case": "clipped 0-2 GHz",
        "tests": ["tests/unit/test_turing.py"],
        "notes": "demo_2_18 drops below 2 GHz; turing_0_18 keeps it",
    },
    {
        "area": "Data",
        "case": "invalid Wise schema",
        "tests": ["tests/unit/test_wise.py"],
        "notes": "wise_bad.csv GHz-as-Hz rejected",
    },
    {
        "area": "Data",
        "case": "corrupt checksum",
        "tests": ["tests/unit/test_storage_artifacts.py", "tests/unit/test_storage_repositories.py"],
        "notes": "checksum fail-closed",
    },
    {
        "area": "Persistence",
        "case": "empty DB migration",
        "tests": ["tests/unit/test_storage_schema.py"],
        "notes": "alembic upgrade empty directory",
    },
    {
        "area": "Persistence",
        "case": "interrupted MLflow link",
        "tests": ["tests/unit/test_storage_tracking.py"],
        "notes": "onesided then reconcile",
    },
    {
        "area": "Persistence",
        "case": "MLflow offline",
        "tests": ["tests/unit/test_storage_tracking.py"],
        "notes": "NoOpTracker / disabled tracker",
    },
    {
        "area": "Persistence",
        "case": "moved project root",
        "tests": ["tests/unit/test_release.py"],
        "notes": "SMARTSCAN_ROOT override",
    },
    {
        "area": "Persistence",
        "case": "duplicate retry",
        "tests": ["tests/unit/test_storage_tracking.py", "tests/integration/test_storage_cli.py"],
        "notes": "mlflow reconcile does not duplicate",
    },
    {
        "area": "ML",
        "case": "missing/corrupt bundle",
        "tests": ["tests/unit/test_dashboard_services.py", "tests/unit/test_release.py"],
        "notes": "checksum rejection; CTS fallback",
    },
    {
        "area": "ML",
        "case": "wrong BandPlan/IBW",
        "tests": ["tests/unit/test_ml_train_bundle.py"],
        "notes": "SchedulerBundle.assert_compatible",
    },
    {
        "area": "ML",
        "case": "absent champion",
        "tests": ["tests/unit/test_release.py", "tests/unit/test_storage_tracking.py"],
        "notes": "best-available stays candidate when gate is false",
    },
    {
        "area": "ML",
        "case": "checksum rejection of untrusted bundle",
        "tests": ["tests/unit/test_dashboard_services.py"],
        "notes": "corrupt checksums.json",
    },
    {
        "area": "ML",
        "case": "CPU-only deterministic evaluation",
        "tests": ["tests/unit/test_ml_train_bundle.py", "tests/unit/test_ml_gate.py"],
        "notes": "device cpu; frozen seeds",
    },
    {
        "area": "Dashboard",
        "case": "invalid input",
        "tests": ["tests/unit/test_dashboard_services.py"],
        "notes": "validate_run_request caps and path sandbox",
    },
    {
        "area": "Dashboard",
        "case": "long run",
        "tests": ["tests/unit/test_dashboard_services.py"],
        "notes": "max_duration_s live cap",
    },
    {
        "area": "Dashboard",
        "case": "no prior runs",
        "tests": ["tests/integration/test_dashboard_app.py"],
        "notes": "history empty does not crash",
    },
    {
        "area": "Dashboard",
        "case": "unavailable metric",
        "tests": ["tests/unit/test_dashboard_services.py", "tests/unit/test_dashboard_plots.py"],
        "notes": "Not available; never fabricated zero",
    },
    {
        "area": "Dashboard",
        "case": "failed gate",
        "tests": ["tests/unit/test_dashboard_services.py"],
        "notes": "candidate alias; no win badge",
    },
    {
        "area": "Dashboard",
        "case": "offline replay",
        "tests": ["tests/unit/test_dashboard_services.py", "tests/integration/test_stage7_cli.py"],
        "notes": "demo --offline loads matched runs",
    },
    {
        "area": "Dashboard",
        "case": "cross-protocol ranking refused",
        "tests": ["tests/unit/test_experiment_protocol.py"],
        "notes": "AIR from different protocols cannot be paired",
    },
    {
        "area": "ML",
        "case": "bundle generation fingerprints distinct",
        "tests": ["tests/unit/test_experiment_protocol.py"],
        "notes": "load v2/v3/v4 verify fingerprint",
    },
]


def _check_paths(paths: list[str], root: Path) -> list[str]:
    return [p for p in paths if not (root / p).is_file()]


def write_requirements_coverage(path: Path | None = None) -> dict[str, Any]:
    root = project_root()
    rows = []
    gaps = []
    for item in COVERAGE:
        missing = _check_paths(list(item["code"]) + list(item["tests"]), root)
        rows.append({**item, "missing_paths": missing, "ok": not missing})
        if missing:
            gaps.append({"need": item["need"], "missing": missing})
    robust_rows = []
    robust_gaps = []
    for item in ROBUSTNESS:
        missing = _check_paths(list(item["tests"]), root)
        robust_rows.append({**item, "missing_paths": missing, "ok": not missing})
        if missing:
            robust_gaps.append({"area": item["area"], "case": item["case"], "missing": missing})
    payload = {
        "schema_version": "1.0.0",
        "n_needs": len(rows),
        "n_gaps": len(gaps),
        "rows": rows,
        "gaps": gaps,
        "robustness": {
            "n_cases": len(robust_rows),
            "n_gaps": len(robust_gaps),
            "rows": robust_rows,
            "gaps": robust_gaps,
        },
    }
    dest = path or (root / "docs" / "evidence" / "requirements_coverage.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    robust_dest = dest.parent / "robustness_matrix.json"
    robust_dest.write_text(
        json.dumps(payload["robustness"], indent=2, sort_keys=True), encoding="utf-8"
    )
    return payload
