"""Held-out evidence pack for Stage 7. Does not tune on frozen seeds."""

from __future__ import annotations

import csv
import json
import os
import platform
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from smartscan.config import BenchmarkConfig, load_yaml, project_root
from smartscan.ml.cli import load_train_config
from smartscan.release.coverage import write_requirements_coverage
from smartscan.release.frozen import require_frozen_hashes
from smartscan.release.perf import measure_demo_profile
from smartscan.release.resolve import resolve_best_available
from smartscan.storage.db import current_git_sha
from smartscan.types import SmartScanError

DEFAULT_OUT = "artifacts/benchmark_final"


def _write_csv(path: Path, rows: list[Any]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = ["scenario_id", "seed", "strategy"]
    metric_keys = sorted({k for row in rows for k in row.metrics})
    fieldnames = keys + metric_keys + ["pfa_num", "pfa_den"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = {
                "scenario_id": row.scenario_id,
                "seed": row.seed,
                "strategy": row.strategy,
                "pfa_num": row.pfa_num,
                "pfa_den": row.pfa_den,
            }
            payload.update({k: row.metrics.get(k) for k in metric_keys})
            writer.writerow(payload)


def _csv_from_seed_dicts(path: Path, seed_rows: list[dict[str, Any]]) -> None:
    if not seed_rows:
        path.write_text("", encoding="utf-8")
        return
    keys = ["scenario_id", "seed", "strategy"]
    metric_keys = sorted({k for row in seed_rows for k in (row.get("metrics") or {})})
    fieldnames = keys + metric_keys + ["pfa_num", "pfa_den"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in seed_rows:
            payload = {
                "scenario_id": row.get("scenario_id"),
                "seed": row.get("seed"),
                "strategy": row.get("strategy"),
                "pfa_num": row.get("pfa_num"),
                "pfa_den": row.get("pfa_den"),
            }
            payload.update({k: (row.get("metrics") or {}).get(k) for k in metric_keys})
            writer.writerow(payload)


def _provenance(*, wall_s: float, rss_bytes: int | None) -> dict[str, Any]:
    pkgs: dict[str, str] = {}
    for name in ("numpy", "scipy", "torch", "mlflow", "streamlit", "plotly"):
        try:
            mod = __import__(name)
            pkgs[name] = str(getattr(mod, "__version__", "unknown"))
        except Exception:
            pkgs[name] = "missing"
    return {
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_sha": current_git_sha(),
        "packages": pkgs,
        "eval_wall_s": wall_s,
        "peak_rss_bytes": rss_bytes,
    }


def _write_docs_summary(root: Path, summary: dict[str, Any], hashes: dict[str, str]) -> None:
    docs_ev = root / "docs" / "evidence"
    docs_ev.mkdir(parents=True, exist_ok=True)
    slim = {
        "performance_gate_passed": summary["gate"]["performance_gate_passed"],
        "reasons": summary["gate"]["reasons"],
        "family_pass": summary["gate"]["family_pass"],
        "resolved": summary["resolved"],
        "hashes": hashes,
        "n_seed_rows": summary["n_seed_rows"],
        "reused_existing_gate": summary["reused_existing_gate"],
        "implementation_complete": True,
        "oracle_ceiling": "unattainable evaluator-only; not a deployable baseline",
    }
    (docs_ev / "held_out_gate_summary.json").write_text(
        json.dumps(slim, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (docs_ev / "implementation_status.json").write_text(
        json.dumps(
            {
                "implementation_complete": True,
                "performance_gate_passed": bool(summary["gate"]["performance_gate_passed"]),
                "alias": "champion" if summary["gate"]["performance_gate_passed"] else "candidate",
                "resolved_source": summary["resolved"]["source"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def run_final_benchmark(
    *,
    config_path: Path,
    manifest_arg: str,
    track: bool = False,
    output_dir: Path | None = None,
    include_perf: bool = True,
    reuse_existing: bool = False,
    perf_duration_s: float | None = None,
) -> dict[str, Any]:
    """Run or package the frozen held-out benchmark. Never subsets seeds."""

    hashes = require_frozen_hashes()
    root = project_root()
    bench = BenchmarkConfig.model_validate(load_yaml(config_path))
    expected = Path(bench.manifest).name
    given = Path(manifest_arg).name
    if given != expected:
        raise SmartScanError(
            f"--manifest {manifest_arg} does not match frozen config manifest {bench.manifest}."
        )
    dest = output_dir or (root / DEFAULT_OUT)
    dest.mkdir(parents=True, exist_ok=True)
    resolved = resolve_best_available("best-available")
    gate_src = root / "artifacts" / "models" / "held_out_gate.json"
    reuse = reuse_existing or os.environ.get("SMARTSCAN_REUSE_HELD_OUT_GATE") == "1"

    if reuse and gate_src.is_file():
        gate_payload = json.loads(gate_src.read_text(encoding="utf-8"))
        if gate_payload.get("manifest_fingerprint") != hashes["held_out_manifest_content_fingerprint"]:
            raise SmartScanError("Existing gate file does not match frozen manifest fingerprint.")
        wall_s = 0.0
        rows_n = int(gate_payload.get("n_rows") or 0)
        (dest / "held_out_gate.json").write_text(
            json.dumps(gate_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        _csv_from_seed_dicts(dest / "seed_metrics.csv", list(gate_payload.get("seed_rows") or []))
        (dest / "seed_metrics.json").write_text(
            json.dumps(gate_payload.get("seed_rows") or [], indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        gate_obj = {
            "performance_gate_passed": gate_payload.get("performance_gate_passed"),
            "reasons": gate_payload.get("reasons") or [],
            "family_pass": gate_payload.get("family_pass") or {},
            "comparisons": gate_payload.get("comparisons") or {},
        }
        reused = True
    else:
        from smartscan.ml.bundle import load_bundle, ppo_predict_fn
        from smartscan.ml.evaluate import evaluate_held_out, load_held_out_manifest
        from smartscan.ml.features import FeatureBuilder
        from smartscan.ml.predictor import BuilderBackedHazardPredictor
        from smartscan.receiver.detector import load_receiver_config
        from smartscan.rf.bands import named_band_plan

        train_cfg = load_train_config(root / "configs" / "train_full.yaml")
        manifest = load_held_out_manifest(root / bench.manifest)
        ppo_predict = None
        fb_factory: Callable[[], FeatureBuilder] | None = None
        builder_predictor = None
        if resolved.strategy == "ppo" and resolved.model_dir:
            bundle = load_bundle(resolved.model_dir)
            ppo_predict = ppo_predict_fn(bundle)
            if bundle.predictor is not None:
                builder_predictor = BuilderBackedHazardPredictor(bundle.predictor)

            def make_feature_builder() -> FeatureBuilder:
                plan = named_band_plan(train_cfg.band_plan_id)
                rec_payload = dict(load_yaml(root / train_cfg.receiver_config))
                rec_payload["dwell_bins"] = list(train_cfg.dwell_bins)
                rec_payload["noise_power_w"] = float(train_cfg.noise_power_w)
                receiver = load_receiver_config(rec_payload)
                return FeatureBuilder(
                    n_bands=plan.n_bands,
                    dt_s=train_cfg.dt_s,
                    dwell_bins=tuple(int(x) for x in train_cfg.dwell_bins),
                    ewma_alpha=train_cfg.ewma_alpha,
                    tune_latency_steps=receiver.tune_latency_steps,
                    public_priorities={int(b): 2.0 for b in train_cfg.public_priorities},
                )

            fb_factory = make_feature_builder

        t0 = time.perf_counter()
        rows, gate = evaluate_held_out(
            bench,
            train_cfg,
            manifest,
            ppo_predict=ppo_predict,
            feature_builder_factory=fb_factory,
            include_oracle=True,
            predictor=builder_predictor,
        )
        wall_s = time.perf_counter() - t0
        payload = {
            "performance_gate_passed": gate.performance_gate_passed,
            "reasons": gate.reasons,
            "comparisons": gate.comparisons,
            "family_pass": gate.family_pass,
            "n_rows": len(rows),
            "manifest_fingerprint": manifest["content_fingerprint"],
            "seeds": "all_predeclared",
            "resolved": resolved.lines(),
            "oracle_ceiling": "unattainable evaluator-only; not a deployable baseline",
            "seed_rows": [
                {
                    "scenario_id": row.scenario_id,
                    "seed": row.seed,
                    "strategy": row.strategy,
                    "metrics": row.metrics,
                    "pfa_num": row.pfa_num,
                    "pfa_den": row.pfa_den,
                }
                for row in rows
            ],
        }
        text = json.dumps(payload, indent=2, sort_keys=True, default=str)
        (dest / "held_out_gate.json").write_text(text, encoding="utf-8")
        gate_src.parent.mkdir(parents=True, exist_ok=True)
        gate_src.write_text(text, encoding="utf-8")
        _write_csv(dest / "seed_metrics.csv", rows)
        (dest / "seed_metrics.json").write_text(
            json.dumps(payload["seed_rows"], indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        gate_obj = {
            "performance_gate_passed": gate.performance_gate_passed,
            "reasons": gate.reasons,
            "family_pass": gate.family_pass,
            "comparisons": gate.comparisons,
        }
        rows_n = len(rows)
        reused = False
        if track:
            from smartscan.storage.db import StorageSettings
            from smartscan.storage.pipeline import build_repository
            from smartscan.storage.tracking import TrackingPayload

            settings = StorageSettings.from_env()
            repo = build_repository(settings, track=True, upgrade=True)
            mlflow_id = repo.tracker.log_run(
                TrackingPayload(
                    domain_run_id=uuid4(),
                    experiment="smartscan-scheduler",
                    params={"kind": "stage7_held_out", "n_rows": str(rows_n)},
                    metrics={
                        "performance_gate_passed": 1.0 if gate.performance_gate_passed else 0.0
                    },
                    tags={
                        "stage": "7",
                        "kind": "held_out_eval",
                        "manifest_fp": hashes["held_out_manifest_content_fingerprint"],
                    },
                    artifact_files=[dest / "held_out_gate.json"],
                )
            )
            payload["mlflow_run_id"] = mlflow_id
            (dest / "held_out_gate.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
            )

    skip_perf = os.environ.get("SMARTSCAN_SKIP_PERF") == "1"
    if include_perf and not skip_perf:
        duration = 60.0 if perf_duration_s is None else float(perf_duration_s)
        perf: dict[str, Any] = measure_demo_profile(duration_s=duration)
    else:
        perf = {"skipped": True}
    summary = {
        "schema_version": "1.0.0",
        "reused_existing_gate": reused,
        "n_seed_rows": rows_n,
        "implementation_complete": True,
        "resolved": {
            "strategy": resolved.strategy,
            "source": resolved.source,
            "model": resolved.model_name,
            "version": resolved.version,
            "note": resolved.note,
        },
        "hashes": hashes,
        "gate": {
            "performance_gate_passed": gate_obj["performance_gate_passed"],
            "reasons": gate_obj["reasons"],
            "family_pass": gate_obj.get("family_pass") or {},
        },
        "comparisons": gate_obj.get("comparisons") or {},
        "oracle_ceiling": "unattainable evaluator-only; not a deployable baseline",
        "demo_profile_perf": perf,
        "provenance": _provenance(
            wall_s=wall_s,
            rss_bytes=(perf.get("peak_rss_bytes") if isinstance(perf, dict) else None),
        ),
    }
    (dest / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (dest / "comparisons.json").write_text(
        json.dumps(gate_obj.get("comparisons") or {}, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    _write_docs_summary(root, summary, hashes)
    write_requirements_coverage(root / "docs" / "evidence" / "requirements_coverage.json")
    return summary
