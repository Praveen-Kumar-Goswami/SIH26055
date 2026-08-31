"""Command-line interface for Stages 1–7."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from smartscan.config import SimulateConfig, load_yaml, project_root
from smartscan.rf.environment import per_band_activity, simulate
from smartscan.rf.io import inspect_summary, load_ground_truth, save_ground_truth
from smartscan.types import SmartScanError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="smartscan",
        description="SIH26055 Smart Scan — Stage 1–7 RF, receiver, metrics, storage, scheduler, dashboard, and release.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sim = sub.add_parser("simulate", help="Render GroundTruth from a scenario config.")
    sim.add_argument("--config", required=True, type=Path)
    sim.add_argument("--output", type=Path, default=None)

    ins = sub.add_parser("inspect-ground-truth", help="Print per-band activity and fingerprints.")
    ins.add_argument("artifact", type=Path)

    turing = sub.add_parser("import-turing", help="Convert a local TSRD pulse-train HDF5 file.")
    turing.add_argument("--input", required=True, type=Path)
    turing.add_argument("--band-plan", default="demo_2_18")
    turing.add_argument("--output", required=True, type=Path)
    turing.add_argument("--dt", type=float, default=0.001)
    turing.add_argument("--duration", type=float, default=None)
    turing.add_argument("--mode", choices=("auto", "stare", "scan"), default="auto")

    wise = sub.add_parser("validate-wise", help="Validate a local Wise-compatible catalog.")
    wise.add_argument("--input", required=True, type=Path)

    recv = sub.add_parser("receive", help="Run an open-loop scan schedule on GroundTruth.")
    recv.add_argument("--truth", required=True, type=Path)
    recv.add_argument(
        "--strategy",
        default="sequential",
        help="sequential, random, fixed-priority, reactive, periodic-intercept, contextual-thompson, or ppo.",
    )
    recv.add_argument("--seed", type=int, default=42, help="Receiver/detector seed.")
    recv.add_argument(
        "--schedule-seed",
        type=int,
        default=0,
        help="Random-schedule seed. Independent of --seed so detector noise can vary alone.",
    )
    recv.add_argument("--output", required=True, type=Path)
    recv.add_argument("--receiver-config", type=Path, default=Path("configs/receiver.yaml"))
    recv.add_argument("--dwell", type=int, default=8)
    recv.add_argument(
        "--priority",
        type=str,
        default=None,
        help="Comma-separated public band indices for fixed-priority.",
    )

    met = sub.add_parser("metrics", help="Evaluate Stage 3 figures of merit for a receiver run.")
    met.add_argument("--truth", required=True, type=Path)
    met.add_argument("--log", required=True, type=Path)
    met.add_argument("--output", required=True, type=Path)
    met.add_argument("--csv", type=Path, default=None)
    met.add_argument("--receiver-config", type=Path, default=Path("configs/receiver.yaml"))
    met.add_argument("--miss-horizon-s", type=float, default=None)

    sens = sub.add_parser("sensitivity", help="Controlled detector Pd vs SNR sweep.")
    sens.add_argument("--receiver-config", type=Path, default=Path("configs/receiver.yaml"))
    sens.add_argument("--target-pd", type=float, default=0.90)
    sens.add_argument("--output", required=True, type=Path)
    sens.add_argument("--seed", type=int, default=12345)
    sens.add_argument("--n-trials", type=int, default=2000)
    sens.add_argument("--analytic-only", action="store_true")

    dbp = sub.add_parser("db", help="Domain database migrations.")
    db_sub = dbp.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="Apply Alembic migrations to the domain store.")

    mlf = sub.add_parser("mlflow", help="Local MLflow server and reconcile.")
    mlf_sub = mlf.add_subparsers(dest="mlflow_command", required=True)
    serve = mlf_sub.add_parser("serve", help="Start a local MLflow tracking server.")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    recon = mlf_sub.add_parser("reconcile", help="Link domain runs to MLflow without duplicates.")
    recon.add_argument("--all", action="store_true")
    recon.add_argument("--run", dest="domain_run_id", default=None)

    runp = sub.add_parser("run", help="Simulate, scan, evaluate, and optionally persist a baseline.")
    runp.add_argument("--config", required=True, type=Path)
    runp.add_argument(
        "--strategy",
        default="sequential",
        help=(
            "Strategy name (sequential, random, fixed-priority, reactive, "
            "periodic-intercept, contextual-thompson, ppo), or best-available."
        ),
    )
    runp.add_argument("--persist", action="store_true")
    runp.add_argument("--track", action="store_true")
    runp.add_argument("--seed", type=int, default=42, help="Receiver/detector seed.")
    runp.add_argument("--schedule-seed", type=int, default=0)
    runp.add_argument("--dwell", type=int, default=8)
    runp.add_argument("--receiver-config", type=Path, default=Path("configs/receiver.yaml"))
    runp.add_argument("--priority", type=str, default=None)

    runsp = sub.add_parser("runs", help="Query and verify persisted domain runs.")
    runs_sub = runsp.add_subparsers(dest="runs_command", required=True)
    lst = runs_sub.add_parser("list", help="List persisted runs.")
    lst.add_argument("--strategy", default=None)
    lst.add_argument("--status", default=None)
    lst.add_argument("--order-by", dest="order_by", default=None)
    lst.add_argument("--scenario", default=None)
    ver = runs_sub.add_parser("verify", help="Reload artifacts and recompute Stage 3 metrics.")
    ver.add_argument("domain_run_id")

    col = sub.add_parser("collect", help="Generate Stage 5 exploration logs and a dataset manifest.")
    col.add_argument("--config", required=True, type=Path)
    col.add_argument("--output", type=Path, default=None)

    tp = sub.add_parser("train-predictor", help="Train the censored hit-hazard predictor.")
    tp.add_argument("--config", required=True, type=Path)
    tp.add_argument("--track", action="store_true")
    tp.add_argument("--output", type=Path, default=None)

    tb = sub.add_parser("train-contextual-bandit", help="Train contextual Thompson sampling.")
    tb.add_argument("--config", required=True, type=Path)
    tb.add_argument("--track", action="store_true")
    tb.add_argument("--output", type=Path, default=None)

    ts = sub.add_parser("train-scheduler", help="Train PPO and write a SmartScanScheduler bundle.")
    ts.add_argument("--config", required=True, type=Path)
    ts.add_argument("--track", action="store_true")
    ts.add_argument("--output", type=Path, default=None)

    improve = sub.add_parser(
        "ml-improve",
        help="Offline ML improvement cycle (train/val only; never the frozen 1000–1029 held-out set).",
    )
    improve.add_argument(
        "--phase",
        choices=(
            "diagnose",
            "predictor",
            "hpo",
            "train",
            "fresh-test",
            "train-v4",
            "fresh-test-v4",
            "all",
        ),
        default="all",
    )
    improve.add_argument("--track", action="store_true")
    improve.add_argument("--hpo-timesteps", type=int, default=1536)
    improve.add_argument("--seeds", default="41,42,43", help="Independent PPO training seeds.")

    ev = sub.add_parser("evaluate", help="Held-out Stage 5 benchmark (does not tune on this manifest).")
    ev.add_argument("--config", required=True, type=Path)
    ev.add_argument("--model", default=None)
    ev.add_argument("--seeds", type=int, default=30)
    ev.add_argument("--track", action="store_true")
    ev.add_argument("--train-config", type=Path, default=None)
    ev.add_argument("--output", type=Path, default=None)

    md = sub.add_parser("models", help="MLflow model registry aliases.")
    md_sub = md.add_subparsers(dest="models_command", required=True)
    promo = md_sub.add_parser("promote", help="Set candidate or champion alias.")
    promo.add_argument("--name", default="SmartScanScheduler")
    promo.add_argument("--version", required=True)
    promo.add_argument("--require-gate", action="store_true")
    promo.add_argument("--gate", type=Path, default=None)

    dash = sub.add_parser("dashboard", help="Launch the offline Streamlit dashboard.")
    dash.add_argument("--host", default=None)
    dash.add_argument("--port", type=int, default=None)

    sub.add_parser("doctor", help="Check DB, artifacts, MLflow, and model alias status.")

    benchp = sub.add_parser(
        "benchmark",
        help="Frozen held-out evidence pack. Refuses if Stage 5 hashes drifted.",
    )
    benchp.add_argument("--config", required=True, type=Path)
    benchp.add_argument("--manifest", required=True)
    benchp.add_argument("--track", action="store_true")
    benchp.add_argument("--output", type=Path, default=None)
    benchp.add_argument("--skip-perf", action="store_true", help="Skip the 60 s / 60_000-step CPU probe.")
    benchp.add_argument(
        "--reuse-gate",
        action="store_true",
        help="Reuse artifacts/models/held_out_gate.json if the fingerprint matches (tests/dev only).",
    )

    demop = sub.add_parser("demo", help="Offline demo: load matched runs and model. Never retrains.")
    demop.add_argument("--offline", action="store_true")
    demop.add_argument("--output", type=Path, default=None)
    demop.add_argument("--rebuild", action="store_true", help="Regenerate artifacts/demo even if present.")

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "simulate":
            return _cmd_simulate(args)
        if args.command == "inspect-ground-truth":
            return _cmd_inspect(args)
        if args.command == "import-turing":
            return _cmd_import_turing(args)
        if args.command == "validate-wise":
            return _cmd_validate_wise(args)
        if args.command == "receive":
            return _cmd_receive(args)
        if args.command == "metrics":
            return _cmd_metrics(args)
        if args.command == "sensitivity":
            return _cmd_sensitivity(args)
        if args.command == "db":
            if args.db_command == "upgrade":
                return _cmd_db_upgrade()
        if args.command == "mlflow":
            if args.mlflow_command == "serve":
                return _cmd_mlflow_serve(args)
            if args.mlflow_command == "reconcile":
                return _cmd_mlflow_reconcile(args)
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "runs":
            if args.runs_command == "list":
                return _cmd_runs_list(args)
            if args.runs_command == "verify":
                return _cmd_runs_verify(args)
        if args.command == "collect":
            from smartscan.ml.cli import cmd_collect

            return cmd_collect(args)
        if args.command == "train-predictor":
            from smartscan.ml.cli import cmd_train_predictor

            return cmd_train_predictor(args)
        if args.command == "train-contextual-bandit":
            from smartscan.ml.cli import cmd_train_contextual_bandit

            return cmd_train_contextual_bandit(args)
        if args.command == "train-scheduler":
            from smartscan.ml.cli import cmd_train_scheduler

            return cmd_train_scheduler(args)
        if args.command == "ml-improve":
            from smartscan.ml.cli import cmd_ml_improve

            return cmd_ml_improve(args)
        if args.command == "evaluate":
            from smartscan.ml.cli import cmd_evaluate

            return cmd_evaluate(args)
        if args.command == "models":
            if args.models_command == "promote":
                from smartscan.ml.cli import cmd_models_promote

                return cmd_models_promote(args)
        if args.command == "dashboard":
            return _cmd_dashboard(args)
        if args.command == "doctor":
            return _cmd_doctor()
        if args.command == "benchmark":
            return _cmd_benchmark(args)
        if args.command == "demo":
            return _cmd_demo(args)
    except SmartScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


def _cmd_simulate(args: argparse.Namespace) -> int:
    config_path = _resolve(args.config)
    payload = load_yaml(config_path)
    config = SimulateConfig.model_validate(payload)
    truth = simulate(config)
    output = args.output or (Path(config.output) if config.output else None)
    if output is None:
        output = project_root() / "artifacts" / "runs" / "stage1_demo.npz"
    output = _resolve_output(output)
    save_ground_truth(truth, output)
    _print_simulate(truth, output)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    truth = load_ground_truth(_resolve(args.artifact))
    summary = inspect_summary(truth)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print()
    print(
        f"profile={summary['profile_id']} N={summary['n_steps']} K={summary['n_bands']} "
        f"dt={summary['dt_s']}s events={summary['n_events']}"
    )
    print(f"content_fingerprint={summary['content_fingerprint']}")
    print(f"artifact_sha256={summary['artifact_sha256']}")
    for row in summary["bands"]:
        print(
            f"  band {row['band']:2d} {row['name']}: "
            f"occupied_frac={row['occupied_fraction']:.4f} events={row['event_count']}"
        )
    return 0


def _cmd_import_turing(args: argparse.Namespace) -> int:
    from smartscan.data.turing import import_turing

    truth = import_turing(
        _resolve(args.input),
        band_plan_id=args.band_plan,
        dt_s=args.dt,
        duration_s=args.duration,
        receiver_mode=args.mode,
    )
    output = _resolve_output(args.output)
    save_ground_truth(truth, output)
    _print_simulate(truth, output)
    dropped = truth.provenance.dropped_counts
    print(f"dropped_counts={json.dumps(dropped, sort_keys=True)}")
    print(f"receiver_mode={truth.provenance.transformation.get('receiver_mode')}")
    return 0


def _cmd_validate_wise(args: argparse.Namespace) -> int:
    from smartscan.data.wise import validate_wise

    result = validate_wise(_resolve(args.input))
    payload = {
        "ok": result.ok,
        "n_records": result.n_records,
        "errors": result.errors,
        "source_record_ids": [record.source_record_id for record in result.records],
    }
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 2


def _cmd_receive(args: argparse.Namespace) -> int:
    from smartscan.config import load_yaml
    from smartscan.dashboard.services import load_dashboard_config, model_bundle_dir
    from smartscan.ml.policies import construct_live_policy
    from smartscan.ml.strategy_registry import parse_cli_strategy
    from smartscan.receiver.detector import load_receiver_config
    from smartscan.receiver.logs import diagnostic_counts, save_receiver_run
    from smartscan.receiver.scanner import run_schedule

    name = parse_cli_strategy(str(args.strategy), allow_best_available=False)
    truth = load_ground_truth(_resolve(args.truth))
    cfg = load_receiver_config(load_yaml(_resolve(args.receiver_config)))
    band_order = None
    if args.priority:
        band_order = tuple(int(part.strip()) for part in args.priority.split(",") if part.strip())
    dash = load_dashboard_config()
    if band_order is None:
        band_order = tuple(int(b) for b in dash.public_priorities)
    model_dir = model_bundle_dir(dash) if name == "ppo" else None
    schedule = construct_live_policy(
        name,
        dwell_steps=args.dwell,
        schedule_seed=args.schedule_seed,
        band_order=band_order,
        n_bands=truth.band_plan.n_bands,
        dwell_bins=cfg.dwell_bins,
        dt_s=float(truth.dt_s),
        tune_latency_steps=int(cfg.tune_latency_steps),
        public_priorities=tuple(int(b) for b in dash.public_priorities),
        model_dir=model_dir,
    )
    run = run_schedule(truth, schedule, cfg, receiver_seed=args.seed, default_dwell_steps=args.dwell)
    output = _resolve_output(args.output)
    save_receiver_run(run, output)
    diag = diagnostic_counts(truth, run)
    print(f"wrote {output}")
    print(f"truth_fingerprint={truth.content_fingerprint}")
    print(f"receiver_config_hash={run.observations.receiver_config_hash}")
    print(f"receiver_seed={args.seed} schedule_seed={args.schedule_seed} strategy={name}")
    print(f"completed_dwells={diag['completed_dwells']} detections={diag['n_detections']}")
    print(
        f"hits={diag['hits']} misses={diag['misses']} false_alarms={diag['false_alarms']} "
        "(evaluator join; not Stage 3 FoMs)"
    )
    print(f"tuning_fraction={diag['tuning_fraction']:.4f}")
    snr = diag["average_measured_snr_db"]
    print(f"average_measured_snr_db={snr if snr is not None else 'n/a'}")
    print(f"n_incomplete_commands={diag['n_incomplete_commands']}")
    print(f"artifact_sha256={run.artifact_sha256}")
    return 0


def _cmd_metrics(args: argparse.Namespace) -> int:
    from smartscan.metrics.engine import evaluate_strategy, save_metrics, save_metrics_csv
    from smartscan.metrics.schemas import FROZEN_METRIC_KEYS, MetricsConfig
    from smartscan.receiver.detector import load_receiver_config
    from smartscan.receiver.logs import load_receiver_run

    truth = load_ground_truth(_resolve(args.truth))
    run = load_receiver_run(_resolve(args.log))
    receiver = None
    cfg_path = _resolve(args.receiver_config)
    if cfg_path.is_file():
        receiver = load_receiver_config(load_yaml(cfg_path))
    metrics_config = MetricsConfig(miss_penalty_horizon_s=args.miss_horizon_s)
    result = evaluate_strategy(
        truth,
        run.observations,
        run.decisions,
        metrics_config=metrics_config,
        receiver_config=receiver,
    )
    output = _resolve_output(args.output)
    save_metrics(result, output)
    if args.csv is not None:
        save_metrics_csv(result, _resolve_output(args.csv))
    print(f"wrote {output}")
    print(f"content_fingerprint={result.content_fingerprint}")
    print(f"truth_fingerprint={truth.content_fingerprint}")
    print(
        f"n_band_occupancy_events={result.tables.support['n_band_occupancy_events']} "
        f"matched={result.tables.support['n_matched_events']} "
        f"missed={len(result.tables.missed_events)}"
    )
    for key in FROZEN_METRIC_KEYS:
        print(f"  {_format_metric(key, result.report.metrics[key])}")
    extra = (
        "event_interception_ratio",
        "wasted_dwell_fraction",
        "tuning_fraction",
        "threat_weighted_capture",
        "all_event_penalized_delay_s",
    )
    for key in extra:
        print(f"  {_format_metric(key, result.report.metrics[key])}")
    print(
        "horizon="
        f"{result.censoring.miss_penalty_horizon_s:g}s "
        f"km_censor={result.censoring.km_censor_rule}"
    )
    return 0


def _cmd_sensitivity(args: argparse.Namespace) -> int:
    from smartscan.metrics.sensitivity import run_sensitivity_sweep
    from smartscan.receiver.detector import load_receiver_config

    cfg = load_receiver_config(load_yaml(_resolve(args.receiver_config)))
    dwell_steps = 8 if 8 in cfg.dwell_bins else (min(cfg.dwell_bins) if cfg.dwell_bins else 8)
    m_samples = int(cfg.samples_per_step) * int(dwell_steps)
    if args.analytic_only:
        n_trials = 0
        monte = False
    else:
        n_trials = int(args.n_trials)
        monte = True
    curve = run_sensitivity_sweep(
        target_pd=float(args.target_pd),
        m_samples=m_samples,
        pfa_design=float(cfg.pfa_design),
        seed=int(args.seed),
        n_trials=max(n_trials, 1) if monte else 0,
        receiver_config=cfg,
        monte_carlo=monte,
    )
    output = _resolve_output(args.output)
    output.write_text(json.dumps(curve.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {output}")
    print(
        f"sensitivity_snr_db={curve.snr_db_at_target:.6g} at Pd={curve.target_pd} "
        f"M={curve.m_samples} pfa={curve.pfa_design}"
    )
    if curve.receiver_input_dbm is not None:
        print(f"receiver_input_dbm={curve.receiver_input_dbm:.6g}")
    return 0


def _cmd_db_upgrade() -> int:
    from smartscan.storage.db import StorageSettings, upgrade_database

    settings = StorageSettings.from_env()
    settings.ensure_directories()
    upgrade_database(settings.domain_db_url)
    print(f"upgraded {settings.domain_db_url}")
    return 0


def _cmd_mlflow_serve(args: argparse.Namespace) -> int:
    import subprocess

    from smartscan.storage.db import StorageSettings
    from smartscan.storage.tracking import mlflow_serve_argv

    settings = StorageSettings.from_env()
    settings.ensure_directories()
    host = args.host or settings.mlflow_host
    port = int(args.port or settings.mlflow_port)
    argv = mlflow_serve_argv(
        host=host,
        port=port,
        backend_store_uri=settings.mlflow_tracking_uri,
        artifacts_destination=str(settings.mlflow_artifact_root),
        root=settings.project_root,
    )
    print(" ".join(argv))
    return int(subprocess.call(argv))


def _cmd_mlflow_reconcile(args: argparse.Namespace) -> int:
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository

    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=True, upgrade=False)
    run_id = UUID(args.domain_run_id) if args.domain_run_id else None
    if run_id is None and not args.all:
        print("error: pass --all or --run <domain_run_id>", file=sys.stderr)
        return 2
    results = repo.reconcile_mlflow(run_id, all_pending=bool(args.all))
    print(f"reconciled={len(results)}")
    for item in results:
        print(
            f"  {item.domain_run_id} sync_status={item.sync_status} "
            f"mlflow_run_id={item.mlflow_run_id or '-'} "
            f"error={item.error or '-'}"
        )
    return 0 if all(item.sync_status != "error" for item in results) else 2


def _cmd_run(args: argparse.Namespace) -> int:
    from smartscan.config import SimulateConfig, load_yaml
    from smartscan.receiver.detector import load_receiver_config
    from smartscan.release.resolve import resolve_best_available
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository, persist_baseline_run

    persist = bool(args.persist or args.track)
    if not persist:
        print(
            "error: python -m smartscan.cli run requires --persist (and optionally --track)",
            file=sys.stderr,
        )
        return 2
    from smartscan.ml.strategy_registry import parse_cli_strategy

    requested = parse_cli_strategy(str(args.strategy), allow_best_available=True)
    resolved = resolve_best_available(requested)
    for line in resolved.lines():
        print(line)
    payload = load_yaml(_resolve(args.config))
    sim = SimulateConfig.model_validate(payload)
    receiver = load_receiver_config(load_yaml(_resolve(args.receiver_config)))
    band_order = None
    if args.priority:
        band_order = tuple(int(part.strip()) for part in args.priority.split(",") if part.strip())
    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=bool(args.track), upgrade=True)
    if resolved.strategy == "ppo":
        from smartscan.dashboard.services import load_dashboard_config, run_experiment

        dash = load_dashboard_config()
        result = run_experiment(
            dash,
            scenario_id=sim.scenario_id,
            seed=int(sim.seed),
            strategy="ppo",
            duration_s=float(sim.duration_s),
            dt_s=float(sim.dt_s),
            receiver_seed=int(args.seed),
            persist=True,
            track=bool(args.track),
            evaluation_overlay=False,
            band_plan_id=sim.band_plan_id,
        )
        if result.domain_run_id is None:
            raise SmartScanError("PPO persist did not return a domain_run_id.")
        domain_run_id = result.domain_run_id
    else:
        domain_run_id = persist_baseline_run(
            simulate_config=sim,
            receiver_config=receiver,
            strategy=resolved.strategy,
            receiver_seed=int(args.seed),
            schedule_seed=int(args.schedule_seed),
            dwell_steps=int(args.dwell),
            band_order=band_order,
            repo=repo,
            track=bool(args.track),
        )
    stored = repo.get_run(domain_run_id, verify_checksums=True)
    print(f"domain_run_id={domain_run_id}")
    print(f"status={stored.status} sync_status={stored.sync_status}")
    print(f"strategy={stored.strategy}")
    print(f"content_fingerprint={stored.identity.content_fingerprint}")
    print(f"receiver_config_hash={stored.identity.config_hash}")
    print(f"mlflow_run_id={stored.identity.mlflow_run_id or '-'}")
    if stored.tracking_error:
        print(f"tracking_warning={stored.tracking_error}")
    if stored.evaluation is not None:
        from smartscan.metrics.schemas import FROZEN_METRIC_KEYS

        for key in FROZEN_METRIC_KEYS:
            print(f"  {_format_metric(key, stored.evaluation.report.metrics[key])}")
        extra = stored.evaluation.report.metrics.get("event_interception_ratio")
        if extra is not None:
            print(f"  {_format_metric('event_interception_ratio', extra)}")
    return 0


def _cmd_runs_list(args: argparse.Namespace) -> int:
    from smartscan.storage.constants import INDEXED_METRIC_KEYS
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository
    from smartscan.storage.repositories import RunFilters

    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=False, upgrade=False)
    filters = RunFilters(strategy=args.strategy, status=args.status, scenario_name=args.scenario)
    rows = repo.list_runs(filters, order_by_metric=args.order_by)
    print(f"n_runs={len(rows)}")
    header = ["domain_run_id", "strategy", "status", "sync"] + list(INDEXED_METRIC_KEYS)
    print("\t".join(header))
    for row in rows:
        cells = [
            str(row.domain_run_id),
            row.strategy,
            row.status,
            row.sync_status,
        ]
        for key in INDEXED_METRIC_KEYS:
            value = row.metrics.get(key)
            cells.append("-" if value is None else f"{value:.6g}")
        print("\t".join(cells))
    return 0


def _cmd_runs_verify(args: argparse.Namespace) -> int:
    from smartscan.storage.db import StorageSettings
    from smartscan.storage.pipeline import build_repository

    settings = StorageSettings.from_env()
    repo = build_repository(settings, track=False, upgrade=False)
    report = repo.recompute_and_verify(UUID(args.domain_run_id))
    print(f"domain_run_id={report.domain_run_id}")
    print(f"ok={str(report.ok).lower()}")
    print(f"checksum_ok={str(report.checksum_ok).lower()}")
    print(f"content_fingerprint_match={str(report.content_fingerprint_match).lower()}")
    print(f"stored_fingerprint={report.stored_fingerprint}")
    print(f"recomputed_fingerprint={report.recomputed_fingerprint}")
    if report.metric_mismatches:
        print("metric_mismatches:")
        for key, (old, new) in report.metric_mismatches.items():
            print(f"  {key}: stored={old} recomputed={new}")
        return 2
    return 0 if report.ok else 2


def _cmd_dashboard(args: argparse.Namespace) -> int:
    import subprocess

    from smartscan.dashboard.services import dashboard_argv, load_dashboard_config

    cfg = load_dashboard_config()
    host = args.host or cfg.host
    port = int(args.port or cfg.port)
    app = Path(__file__).resolve().parent / "dashboard" / "app.py"
    argv = dashboard_argv(host, port, app)
    print(" ".join(argv))
    return int(subprocess.call(argv))


def _cmd_doctor() -> int:
    from smartscan.dashboard.services import doctor_report
    from smartscan.release.resolve import resolve_best_available

    report = doctor_report()
    print(f"ok={str(report['ok']).lower()}")
    for item in report["checks"]:
        print(f"  {item['name']} ok={str(item['ok']).lower()} {item['detail']}")
    print(f"Strategies: {report.get('total_public_strategies')}/7 OK")
    print("Active PPO:")
    print(f"{report.get('active_model_version')} candidate")
    print("Official gate:")
    print("v2_frozen_gate")
    gate_status = str(report.get("official_gate_status") or "failed")
    print("FAILED" if gate_status == "failed" else gate_status.upper())
    periodic = report.get("periodic_intercept") or {}
    print("Periodic-intercept:")
    print(f"implementation {periodic.get('implementation', 'OK')}")
    evidence = periodic.get("evidence") or {}
    print(f"v2 evidence: {evidence.get('v2', 'Not recorded')}")
    print(f"v3 evidence: {evidence.get('v3', 'Not recorded')}")
    print(f"v4 evidence: {evidence.get('v4', 'Not recorded')}")
    print(f"total_public_strategies={report.get('total_public_strategies')}")
    print(f"active_model_version={report.get('active_model_version')}")
    print(f"official_gate_model_version={report.get('official_gate_model_version')}")
    print(f"official_gate_status={report.get('official_gate_status')}")
    print(f"champion_set={str(report.get('champion_set')).lower()}")
    resolved = resolve_best_available("best-available")
    for line in resolved.lines():
        print(line)
    print(f"next_action={report['next_action']}")
    return 0 if report["ok"] else 2


def _cmd_benchmark(args: argparse.Namespace) -> int:
    from smartscan.release.benchmark import run_final_benchmark

    summary = run_final_benchmark(
        config_path=_resolve(args.config),
        manifest_arg=str(args.manifest),
        track=bool(args.track),
        output_dir=_resolve_output(args.output) if args.output else None,
        include_perf=not bool(args.skip_perf),
        reuse_existing=bool(args.reuse_gate),
    )
    print(f"implementation_complete={str(summary['implementation_complete']).lower()}")
    print(
        "performance_gate_passed="
        f"{str(summary['gate']['performance_gate_passed']).lower()}"
    )
    resolved = summary["resolved"]
    print(f"resolved_strategy={resolved['strategy']}")
    print(f"resolved_source={resolved['source']}")
    print(f"resolved_model={resolved['model'] or '-'}")
    print(f"resolved_version={resolved['version'] or '-'}")
    print(f"n_seed_rows={summary['n_seed_rows']}")
    print(f"reused_existing_gate={str(summary['reused_existing_gate']).lower()}")
    for reason in summary["gate"]["reasons"]:
        print(f"  reason: {reason}")
    perf = summary.get("demo_profile_perf") or {}
    if isinstance(perf, dict) and not perf.get("skipped"):
        print(f"demo_profile_wall_s={perf.get('wall_s')}")
        print(f"demo_profile_peak_rss_bytes={perf.get('peak_rss_bytes')}")
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from smartscan.release.demo import run_offline_demo

    if not args.offline:
        print("error: demo requires --offline (no download or retrain)", file=sys.stderr)
        return 2

    dest = _resolve_output(args.output) if args.output else None
    payload = run_offline_demo(dest=dest, rebuild=bool(args.rebuild))
    print(f"offline={str(payload['offline']).lower()}")
    print(f"retrained={str(payload['retrained']).lower()}")
    print(f"downloaded={str(payload['downloaded']).lower()}")
    print(f"demo_dir={payload['demo_dir']}")
    print(f"resolved_strategy={payload['resolved_strategy']}")
    print(f"resolved_source={payload['resolved_source']}")
    print(f"resolved_model={payload['resolved_model'] or '-'}")
    print(f"resolved_version={payload['resolved_version'] or '-'}")
    manifest = payload.get("manifest") or {}
    if manifest.get("truth_fingerprint"):
        print(f"truth_fingerprint={manifest['truth_fingerprint']}")
    checksums = payload.get("bundle_checksums") or {}
    if checksums.get("content_fingerprint"):
        print(f"bundle_content_fingerprint={checksums['content_fingerprint']}")
    print(f"next={payload['next']}")
    return 0


def _format_metric(key: str, metric: object) -> str:
    from smartscan.types import MetricValue

    assert isinstance(metric, MetricValue)
    if not metric.available or metric.value is None:
        return f"{key}: unavailable ({metric.unavailable_reason})"
    num = metric.numerator
    den = metric.denominator
    shown = f"{metric.value:.6g}"
    extra = ""
    if num is not None and den is not None:
        extra = f"  [{num:.6g}/{den:.6g}]"
    unit = f" {metric.unit}" if metric.unit else ""
    return f"{key}={shown}{unit}{extra}"


def _print_simulate(truth: object, output: Path) -> None:
    from smartscan.types import GroundTruth

    assert isinstance(truth, GroundTruth)
    activity = per_band_activity(truth.occupied)
    active_bands = sum(1 for row in activity if row["occupied_steps"] > 0)
    print(f"wrote {output}")
    print(f"seed={truth.seed} N={truth.n_steps} K={truth.band_plan.n_bands} dt={truth.dt_s}")
    print(f"active_bands={active_bands} events={len(truth.events)}")
    print(f"content_fingerprint={truth.content_fingerprint}")
    print(f"artifact_sha256={truth.artifact_sha256}")
    for row, name in zip(activity, truth.band_plan.band_names, strict=True):
        if row["occupied_steps"] == 0:
            continue
        print(
            f"  {name}: occupied_frac={row['occupied_fraction']:.4f} "
            f"steps={row['occupied_steps']}"
        )


def _resolve(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (project_root() / path).resolve()


def _resolve_output(path: Path) -> Path:
    resolved = _resolve(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


if __name__ == "__main__":
    raise SystemExit(main())
