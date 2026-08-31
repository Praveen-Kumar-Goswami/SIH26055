"""End-to-end persist of a Stage 1–3 baseline run into the domain store."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from smartscan.config import SimulateConfig
from smartscan.metrics.engine import evaluate_strategy
from smartscan.receiver.detector import load_receiver_config
from smartscan.receiver.scanner import run_schedule
from smartscan.receiver.schedules import make_schedule
from smartscan.rf.environment import simulate
from smartscan.storage.artifacts import ArtifactStore
from smartscan.storage.db import (
    StorageSettings,
    create_engine_from_url,
    create_session_factory,
    upgrade_database,
)
from smartscan.storage.repositories import RunRepository
from smartscan.storage.tracking import ExperimentTracker, MLflowTracker, NoOpTracker
from smartscan.types import ReceiverConfig, SmartScanError


def build_repository(
    settings: StorageSettings,
    *,
    tracker: ExperimentTracker | None = None,
    track: bool = False,
    upgrade: bool = False,
) -> RunRepository:
    """Open a RunRepository from settings. Optionally run Alembic first."""

    settings.assert_db_separation()
    settings.ensure_directories()
    if upgrade:
        upgrade_database(settings.domain_db_url)
    engine = create_engine_from_url(settings.domain_db_url)
    factory = create_session_factory(engine)
    store = ArtifactStore(settings.artifact_root)
    if tracker is None:
        if track and settings.mlflow_enabled:
            tracker = MLflowTracker.from_settings(settings)
        else:
            tracker = NoOpTracker()
    return RunRepository(factory, store, tracker)


def persist_baseline_run(
    *,
    simulate_config: SimulateConfig | dict[str, object],
    receiver_config: ReceiverConfig | dict[str, object],
    strategy: str,
    receiver_seed: int = 42,
    schedule_seed: int = 0,
    dwell_steps: int = 8,
    band_order: tuple[int, ...] | None = None,
    repo: RunRepository,
    track: bool = True,
) -> UUID:
    """Simulate, scan, evaluate, and persist one baseline. No fake ML metrics."""

    if isinstance(simulate_config, dict):
        sim = SimulateConfig.model_validate(simulate_config)
    else:
        sim = simulate_config
    cfg = (
        receiver_config
        if isinstance(receiver_config, ReceiverConfig)
        else load_receiver_config(receiver_config)
    )
    truth = simulate(sim)
    scenario_id = repo.create_scenario(truth, truth.provenance)
    seeds = {
        "scenario": int(sim.seed),
        "receiver": int(receiver_seed),
        "schedule": int(schedule_seed),
    }
    try:
        from smartscan.ml.strategy_registry import canonicalize_strategy_id

        stored_strategy = canonicalize_strategy_id(strategy)
    except SmartScanError:
        stored_strategy = str(strategy)
    domain_run_id = repo.start_run(
        scenario_id,
        cfg,
        stored_strategy,
        seeds,
        protocol_id="live_session",
        duration_s=float(sim.duration_s),
    )
    try:
        schedule: Any
        try:
            schedule = make_schedule(
                stored_strategy,
                dwell_steps=dwell_steps,
                schedule_seed=schedule_seed,
                band_order=band_order,
            )
        except SmartScanError:
            from smartscan.ml.policies import make_policy

            schedule = make_policy(
                stored_strategy,
                dwell_steps=dwell_steps,
                schedule_seed=schedule_seed,
                band_order=band_order,
                n_bands=truth.band_plan.n_bands,
                dwell_bins=cfg.dwell_bins,
            )
        run = run_schedule(
            truth,
            schedule,
            cfg,
            receiver_seed=receiver_seed,
            default_dwell_steps=dwell_steps,
        )
        repo.attach_logs(domain_run_id, run.observations, run.decisions)
        result = evaluate_strategy(
            truth, run.observations, run.decisions, receiver_config=cfg
        )
        repo.save_metrics(domain_run_id, result)
        repo.complete_run(domain_run_id, track=track)
    except Exception as exc:
        repo.fail_run(domain_run_id, str(exc))
        if isinstance(exc, SmartScanError):
            raise
        raise SmartScanError(f"Baseline persist failed for {domain_run_id}: {exc}") from exc
    return domain_run_id
