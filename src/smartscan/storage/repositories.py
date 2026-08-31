"""Domain repositories: scenarios, runs, logs, metrics, MLflow reconcile."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from smartscan.metrics.engine import evaluate_strategy, load_metrics
from smartscan.metrics.schemas import EvaluationResult
from smartscan.receiver.detector import load_receiver_config, receiver_config_hash
from smartscan.receiver.logs import DecisionLog, ObservationLog, ReceiverRun, load_receiver_run
from smartscan.rf.io import load_ground_truth
from smartscan.storage.artifacts import ArtifactRef, ArtifactStore
from smartscan.storage.constants import (
    EXPERIMENT_BASELINES,
    INDEXED_METRIC_KEYS,
    METRIC_ORDER_ALIASES,
    PROTECTED_MODEL_ALIASES,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_CREATED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
    SCHEMA_VERSION,
    SYNC_ERROR,
    SYNC_PENDING,
    SYNC_SYNCED,
    VALIDATION_VALIDATED,
)
from smartscan.storage.db import current_git_sha, session_scope
from smartscan.storage.models import (
    ArtifactRow,
    DataSourceRow,
    DecisionLogRow,
    GroundTruthRow,
    MetricsRow,
    ModelVersionRow,
    ObservationLogRow,
    ReceiverConfigRow,
    RunRow,
    ScenarioRow,
    TrainingRunRow,
    dumps_json,
    loads_json,
    utcnow,
)
from smartscan.storage.tracking import (
    ExperimentTracker,
    NoOpTracker,
    TrackingPayload,
    finite_metrics,
    warn_tracking_failure,
)
from smartscan.types import (
    GroundTruth,
    MetricsReport,
    MetricValue,
    Provenance,
    ReceiverConfig,
    RunIdentity,
    SmartScanError,
    content_fingerprint,
    strip_volatile,
)


@dataclass
class RunFilters:
    strategy: str | None = None
    scenario_id: UUID | None = None
    scenario_name: str | None = None
    status: str | None = None
    protocol_id: str | None = None
    model_version: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    metric_min: dict[str, float] | None = None
    metric_max: dict[str, float] | None = None


@dataclass
class RunSummary:
    domain_run_id: UUID
    strategy: str
    status: str
    sync_status: str
    scenario_id: UUID
    scenario_name: str
    seeds: dict[str, int]
    git_sha: str | None
    mlflow_run_id: str | None
    created_at: datetime
    metrics: dict[str, float | None]
    protocol_id: str | None = None
    model_version: str | None = None
    bundle_fingerprint: str | None = None
    duration_s: float | None = None
    receiver_config_hash: str | None = None


@dataclass
class StoredRun:
    identity: RunIdentity
    status: str
    sync_status: str
    strategy: str
    scenario_id: UUID
    receiver_config: ReceiverConfig
    truth: GroundTruth
    observations: ObservationLog | None
    decisions: DecisionLog | None
    evaluation: EvaluationResult | None
    error_summary: str | None
    tracking_error: str | None
    artifacts: list[ArtifactRef] = field(default_factory=list)


@dataclass
class RecomputeReport:
    domain_run_id: UUID
    ok: bool
    checksum_ok: bool
    content_fingerprint_match: bool
    recomputed_fingerprint: str
    stored_fingerprint: str | None
    metric_mismatches: dict[str, tuple[float | None, float | None]]


@dataclass
class ReconcileResult:
    domain_run_id: UUID
    sync_status: str
    mlflow_run_id: str | None
    error: str | None = None


def resolve_metric_key(name: str) -> str:
    key = METRIC_ORDER_ALIASES.get(name)
    if key is None:
        raise SmartScanError(
            f"Unknown metric {name!r}. Use one of: {', '.join(INDEXED_METRIC_KEYS)} "
            "or avg_intercept_rate."
        )
    return key


def indexed_scalars(result: EvaluationResult | MetricsReport) -> dict[str, float | None]:
    report = result.report if isinstance(result, EvaluationResult) else result
    out: dict[str, float | None] = {}
    for key in INDEXED_METRIC_KEYS:
        metric = report.metrics.get(key)
        out[key] = _scalar(metric)
    return out


def _scalar(metric: MetricValue | None) -> float | None:
    if metric is None or not metric.available or metric.value is None:
        return None
    value = float(metric.value)
    if value != value or abs(value) == float("inf"):
        return None
    return value


class RunRepository:
    """Application-facing persistence. Public Stage 1–3 types are not forked."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_store: ArtifactStore,
        tracker: ExperimentTracker | None = None,
    ) -> None:
        self._sessions = session_factory
        self.artifacts = artifact_store
        self.tracker: ExperimentTracker = tracker or NoOpTracker()

    def create_scenario(
        self,
        ground_truth: GroundTruth,
        provenance: Provenance | dict[str, Any] | None = None,
    ) -> UUID:
        """Persist GroundTruth bytes under the artifact root; reuse by fingerprint."""

        truth = ground_truth
        if not truth.content_fingerprint:
            truth.content_fingerprint = truth.compute_content_fingerprint()
        fingerprint = truth.content_fingerprint
        prov_model = _as_provenance(provenance or truth.provenance)
        with session_scope(self._sessions) as session:
            existing = session.scalar(
                select(GroundTruthRow).where(GroundTruthRow.content_fingerprint == fingerprint)
            )
            if existing is not None:
                dest = self.artifacts.root / existing.relative_path
                if not dest.is_file():
                    ref = self.artifacts.put_ground_truth(
                        existing.relative_path, truth, overwrite=True
                    )
                    existing.artifact_sha256 = ref.sha256
                return existing.scenario_id
            source_id = self._upsert_data_source(session, prov_model)
            config_hash = content_fingerprint(strip_volatile(dict(truth.scenario_config)))
            scenario = ScenarioRow(
                name=str(truth.scenario_config.get("scenario_id", "unnamed")),
                config_json=dumps_json(strip_volatile(dict(truth.scenario_config))),
                band_plan_json=dumps_json(truth.band_plan.model_dump(mode="json")),
                seed=int(truth.seed),
                source_id=source_id,
                config_hash=config_hash,
            )
            session.add(scenario)
            session.flush()
            rel = f"ground_truth/{fingerprint[:16]}.npz"
            ref = self.artifacts.put_ground_truth(rel, truth, overwrite=False)
            row = GroundTruthRow(
                scenario_id=scenario.id,
                schema_version=truth.schema_version,
                n_steps=truth.n_steps,
                n_bands=truth.band_plan.n_bands,
                dt_s=float(truth.dt_s),
                relative_path=ref.relative_path,
                artifact_sha256=ref.sha256,
                content_fingerprint=fingerprint,
            )
            session.add(row)
            session.flush()
            return scenario.id

    def start_run(
        self,
        scenario_id: UUID,
        receiver_config: ReceiverConfig,
        strategy: str,
        seeds: dict[str, int],
        *,
        protocol_id: str | None = None,
        model_version: str | None = None,
        bundle_fingerprint: str | None = None,
        duration_s: float | None = None,
    ) -> UUID:
        cfg = (
            receiver_config
            if isinstance(receiver_config, ReceiverConfig)
            else load_receiver_config(receiver_config)
        )
        config_hash = receiver_config_hash(cfg)
        domain_run_id = uuid.uuid4()
        with session_scope(self._sessions) as session:
            scenario = session.get(ScenarioRow, scenario_id)
            if scenario is None:
                raise SmartScanError(f"Unknown scenario_id {scenario_id}.")
            rc = session.scalar(
                select(ReceiverConfigRow).where(ReceiverConfigRow.config_hash == config_hash)
            )
            if rc is None:
                rc = ReceiverConfigRow(
                    config_json=dumps_json(cfg.model_dump(mode="json")),
                    config_hash=config_hash,
                )
                session.add(rc)
                session.flush()
            now = utcnow()
            from smartscan.experiment_protocol import infer_protocol_id

            seed_i = int(seeds["scenario"]) if "scenario" in seeds else None
            resolved_protocol = infer_protocol_id(
                seed=seed_i,
                duration_s=duration_s,
                explicit=protocol_id,
                for_new_write=True,
            )
            run = RunRow(
                domain_run_id=domain_run_id,
                scenario_id=scenario_id,
                receiver_config_id=rc.id,
                strategy=str(strategy),
                seeds_json=dumps_json({str(k): int(v) for k, v in seeds.items()}),
                status=RUN_STATUS_CREATED,
                sync_status=SYNC_PENDING,
                git_sha=current_git_sha(),
                schema_version=SCHEMA_VERSION,
                created_at=now,
                updated_at=now,
                protocol_id=resolved_protocol,
                model_version=model_version,
                bundle_fingerprint=bundle_fingerprint,
                duration_s=None if duration_s is None else float(duration_s),
            )
            session.add(run)
            session.flush()
            run.status = RUN_STATUS_RUNNING
            run.started_at = utcnow()
            run.updated_at = utcnow()
        return domain_run_id

    def attach_logs(
        self,
        domain_run_id: UUID,
        observation_log: ObservationLog,
        decision_log: DecisionLog,
    ) -> None:
        run_obj = ReceiverRun(observations=observation_log, decisions=decision_log)
        rel = f"runs/{domain_run_id}/receiver_run.npz"
        ref = self.artifacts.put_receiver_run(rel, run_obj)
        n_p_hit = sum(1 for row in decision_log.rows if row.p_hit is not None)
        n_p_active = sum(1 for row in decision_log.rows if row.p_active is not None)
        n_ttf = sum(
            1 for row in decision_log.rows if row.time_to_next_completed_intercept_s is not None
        )
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            if session.scalar(
                select(ObservationLogRow).where(ObservationLogRow.run_id == domain_run_id)
            ):
                raise SmartScanError(f"Logs already attached for {domain_run_id}.")
            session.add(
                ObservationLogRow(
                    run_id=domain_run_id,
                    relative_path=ref.relative_path,
                    artifact_sha256=ref.sha256,
                    schema_version=observation_log.schema_version,
                    n_rows=len(observation_log.rows),
                )
            )
            session.add(
                DecisionLogRow(
                    run_id=domain_run_id,
                    relative_path=ref.relative_path,
                    artifact_sha256=ref.sha256,
                    schema_version=decision_log.schema_version,
                    n_rows=len(decision_log.rows),
                    n_with_p_hit=n_p_hit,
                    n_with_p_active=n_p_active,
                    n_with_time_forecast=n_ttf,
                )
            )
            session.add(
                ArtifactRow(
                    run_id=domain_run_id,
                    artifact_type="receiver_run",
                    relative_path=ref.relative_path,
                    artifact_sha256=ref.sha256,
                    media_type="application/x-npz",
                    metadata_json=dumps_json({"n_observations": len(observation_log.rows)}),
                )
            )
            run.updated_at = utcnow()

    def save_metrics(
        self,
        domain_run_id: UUID,
        metrics_report: EvaluationResult | MetricsReport,
    ) -> None:
        """Persist full metrics JSON plus indexed scalars. Not the RF engine helper."""

        result = _as_evaluation(metrics_report)
        rel = f"runs/{domain_run_id}/metrics.json"
        payload = json.dumps(result.model_dump(mode="json"), sort_keys=True, allow_nan=False)
        ref = self.artifacts.put_bytes(rel, payload.encode("utf-8"))
        digest = ref.sha256
        result.report.artifact_sha256["metrics_json"] = digest
        scalars = indexed_scalars(result)
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            if session.scalar(select(MetricsRow).where(MetricsRow.run_id == domain_run_id)):
                raise SmartScanError(f"Metrics already saved for {domain_run_id}.")
            session.add(
                MetricsRow(
                    run_id=domain_run_id,
                    schema_version=result.report.metric_schema_version,
                    report_json=payload,
                    relative_path=rel,
                    artifact_sha256=digest,
                    content_fingerprint=result.content_fingerprint,
                    pd=scalars["pd"],
                    pfa=scalars["pfa"],
                    sensitivity=scalars["sensitivity"],
                    average_intercept_rate=scalars["average_intercept_rate"],
                    average_reward=scalars["average_reward"],
                    correct_predictions=scalars["correct_predictions"],
                    average_intercept_time_error=scalars["average_intercept_time_error"],
                    event_interception_ratio=scalars["event_interception_ratio"],
                )
            )
            session.add(
                ArtifactRow(
                    run_id=domain_run_id,
                    artifact_type="metrics_json",
                    relative_path=rel,
                    artifact_sha256=digest,
                    media_type="application/json",
                    metadata_json=dumps_json({"content_fingerprint": result.content_fingerprint}),
                )
            )
            run.updated_at = utcnow()

    def complete_run(self, domain_run_id: UUID, *, track: bool = True) -> None:
        self._attach_environment_snapshot(domain_run_id)
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            if run.status == RUN_STATUS_FAILED:
                raise SmartScanError(f"Cannot complete failed run {domain_run_id}.")
            run.status = RUN_STATUS_COMPLETED
            run.completed_at = utcnow()
            run.updated_at = utcnow()
        if track:
            self._try_track(domain_run_id)

    def fail_run(self, domain_run_id: UUID, error: str) -> None:
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            run.status = RUN_STATUS_FAILED
            run.error_summary = str(error)
            run.completed_at = utcnow()
            run.updated_at = utcnow()

    def get_run(self, domain_run_id: UUID, verify_checksums: bool = True) -> StoredRun:
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            gt_row = session.scalar(
                select(GroundTruthRow).where(GroundTruthRow.scenario_id == run.scenario_id)
            )
            if gt_row is None:
                raise SmartScanError(f"No ground truth for scenario {run.scenario_id}.")
            obs_row = session.scalar(
                select(ObservationLogRow).where(ObservationLogRow.run_id == domain_run_id)
            )
            dec_row = session.scalar(
                select(DecisionLogRow).where(DecisionLogRow.run_id == domain_run_id)
            )
            metrics_row = session.scalar(
                select(MetricsRow).where(MetricsRow.run_id == domain_run_id)
            )
            rc = session.get(ReceiverConfigRow, run.receiver_config_id)
            if rc is None:
                raise SmartScanError(f"Missing receiver config for {domain_run_id}.")
            artifact_rows = list(
                session.scalars(select(ArtifactRow).where(ArtifactRow.run_id == domain_run_id))
            )
            pending: list[tuple[str, str]] = [
                (gt_row.relative_path, gt_row.artifact_sha256),
            ]
            if obs_row is not None:
                pending.append((obs_row.relative_path, obs_row.artifact_sha256))
            if dec_row is not None:
                pending.append((dec_row.relative_path, dec_row.artifact_sha256))
            if metrics_row is not None:
                pending.append((metrics_row.relative_path, metrics_row.artifact_sha256))
            for row in artifact_rows:
                pending.append((row.relative_path, row.artifact_sha256))
            seen: set[tuple[str, str]] = set()
            unique_pending: list[tuple[str, str]] = []
            for item in pending:
                if item in seen:
                    continue
                seen.add(item)
                unique_pending.append(item)
            if verify_checksums:
                failures: list[str] = []
                for relative, digest in unique_pending:
                    try:
                        self.artifacts.verify(relative, digest)
                    except SmartScanError as exc:
                        failures.append(str(exc))
                if failures:
                    raise SmartScanError(
                        "Checksum verification failed; refusing partially trusted data. "
                        + " | ".join(failures)
                    )
            truth = load_ground_truth(self.artifacts.resolve(gt_row.relative_path))
            loaded_obs: ObservationLog | None = None
            loaded_dec: DecisionLog | None = None
            if obs_row is not None:
                loaded = load_receiver_run(self.artifacts.resolve(obs_row.relative_path))
                loaded_obs = loaded.observations
                loaded_dec = loaded.decisions
            evaluation: EvaluationResult | None = None
            if metrics_row is not None:
                evaluation = load_metrics(self.artifacts.resolve(metrics_row.relative_path))
            receiver = load_receiver_config(loads_json(rc.config_json))
            identity = RunIdentity(
                domain_run_id=run.domain_run_id,
                config_hash=rc.config_hash,
                content_fingerprint=gt_row.content_fingerprint,
                artifact_sha256=obs_row.artifact_sha256 if obs_row else gt_row.artifact_sha256,
                seeds=loads_json(run.seeds_json),
                git_sha=run.git_sha,
                mlflow_run_id=run.mlflow_run_id,
            )
            return StoredRun(
                identity=identity,
                status=run.status,
                sync_status=run.sync_status,
                strategy=run.strategy,
                scenario_id=run.scenario_id,
                receiver_config=receiver,
                truth=truth,
                observations=loaded_obs,
                decisions=loaded_dec,
                evaluation=evaluation,
                error_summary=run.error_summary,
                tracking_error=run.tracking_error,
                artifacts=[
                    ArtifactRef(relative_path=row.relative_path, sha256=row.artifact_sha256)
                    for row in artifact_rows
                ],
            )

    def list_runs(
        self,
        filters: RunFilters | None = None,
        order_by_metric: str | None = None,
    ) -> list[RunSummary]:
        filt = filters or RunFilters()
        with session_scope(self._sessions) as session:
            stmt = (
                select(RunRow, ScenarioRow, MetricsRow, ReceiverConfigRow)
                .join(ScenarioRow, RunRow.scenario_id == ScenarioRow.id)
                .join(ReceiverConfigRow, RunRow.receiver_config_id == ReceiverConfigRow.id)
                .outerjoin(MetricsRow, MetricsRow.run_id == RunRow.domain_run_id)
            )
            if filt.strategy is not None:
                stmt = stmt.where(RunRow.strategy == filt.strategy)
            if filt.scenario_id is not None:
                stmt = stmt.where(RunRow.scenario_id == filt.scenario_id)
            if filt.scenario_name is not None:
                stmt = stmt.where(ScenarioRow.name == filt.scenario_name)
            if filt.status is not None:
                stmt = stmt.where(RunRow.status == filt.status)
            if filt.protocol_id is not None:
                stmt = stmt.where(RunRow.protocol_id == filt.protocol_id)
            if filt.created_after is not None:
                stmt = stmt.where(RunRow.created_at >= filt.created_after)
            if filt.created_before is not None:
                stmt = stmt.where(RunRow.created_at <= filt.created_before)
            if filt.model_version is not None:
                stmt = stmt.join(
                    ModelVersionRow, ModelVersionRow.source_run_id == RunRow.domain_run_id
                ).where(
                    (ModelVersionRow.version == filt.model_version)
                    | (ModelVersionRow.alias == filt.model_version)
                    | (ModelVersionRow.registered_name == filt.model_version)
                )
            for key, minimum in (filt.metric_min or {}).items():
                column = getattr(MetricsRow, resolve_metric_key(key))
                stmt = stmt.where(column >= float(minimum))
            for key, maximum in (filt.metric_max or {}).items():
                column = getattr(MetricsRow, resolve_metric_key(key))
                stmt = stmt.where(column <= float(maximum))
            if order_by_metric:
                metric_key = resolve_metric_key(order_by_metric)
                column = getattr(MetricsRow, metric_key)
                stmt = stmt.order_by(column.is_(None), column.desc(), RunRow.created_at.desc())
            else:
                stmt = stmt.order_by(RunRow.created_at.desc())
            rows = session.execute(stmt).all()
            summaries: list[RunSummary] = []
            for run, scenario, metrics, receiver in rows:
                metric_map: dict[str, float | None] = {key: None for key in INDEXED_METRIC_KEYS}
                if metrics is not None:
                    for key in INDEXED_METRIC_KEYS:
                        metric_map[key] = getattr(metrics, key)
                summaries.append(
                    RunSummary(
                        domain_run_id=run.domain_run_id,
                        strategy=run.strategy,
                        status=run.status,
                        sync_status=run.sync_status,
                        scenario_id=run.scenario_id,
                        scenario_name=scenario.name,
                        seeds=loads_json(run.seeds_json),
                        git_sha=run.git_sha,
                        mlflow_run_id=run.mlflow_run_id,
                        created_at=run.created_at,
                        metrics=metric_map,
                        protocol_id=getattr(run, "protocol_id", None),
                        model_version=getattr(run, "model_version", None),
                        bundle_fingerprint=getattr(run, "bundle_fingerprint", None),
                        duration_s=getattr(run, "duration_s", None),
                        receiver_config_hash=receiver.config_hash,
                    )
                )
            return summaries

    def recompute_and_verify(self, domain_run_id: UUID) -> RecomputeReport:
        stored = self.get_run(domain_run_id, verify_checksums=True)
        if stored.observations is None or stored.decisions is None:
            raise SmartScanError(f"Cannot recompute {domain_run_id}: logs are not attached.")
        recomputed = evaluate_strategy(
            stored.truth,
            stored.observations,
            stored.decisions,
            receiver_config=stored.receiver_config,
        )
        stored_fp = stored.evaluation.content_fingerprint if stored.evaluation else None
        mismatches: dict[str, tuple[float | None, float | None]] = {}
        if stored.evaluation is not None:
            old_scalars = indexed_scalars(stored.evaluation)
            new_scalars = indexed_scalars(recomputed)
            for key in INDEXED_METRIC_KEYS:
                if old_scalars[key] != new_scalars[key]:
                    mismatches[key] = (old_scalars[key], new_scalars[key])
        fp_match = stored_fp == recomputed.content_fingerprint if stored_fp else False
        ok = fp_match and not mismatches
        return RecomputeReport(
            domain_run_id=domain_run_id,
            ok=ok,
            checksum_ok=True,
            content_fingerprint_match=fp_match,
            recomputed_fingerprint=recomputed.content_fingerprint,
            stored_fingerprint=stored_fp,
            metric_mismatches=mismatches,
        )

    def reconcile_mlflow(
        self,
        domain_run_id: UUID | None = None,
        *,
        all_pending: bool = False,
    ) -> list[ReconcileResult]:
        targets = self._reconcile_targets(domain_run_id, all_pending=all_pending)
        results: list[ReconcileResult] = []
        for run_id in targets:
            results.append(self._reconcile_one(run_id))
        return results

    def record_training_run(
        self,
        domain_run_id: UUID,
        *,
        algorithm: str,
        split: dict[str, Any] | None = None,
        hyperparameters: dict[str, Any] | None = None,
        model_bundle_path: str | None = None,
        model_bundle_sha256: str | None = None,
        mlflow_experiment_id: str | None = None,
        mlflow_run_id: str | None = None,
    ) -> UUID:
        training_id = uuid.uuid4()
        with session_scope(self._sessions) as session:
            self._require_run(session, domain_run_id)
            session.add(
                TrainingRunRow(
                    id=training_id,
                    run_id=domain_run_id,
                    algorithm=algorithm,
                    split_json=dumps_json(split or {}),
                    hyperparameters_json=dumps_json(hyperparameters or {}),
                    model_bundle_path=model_bundle_path,
                    model_bundle_sha256=model_bundle_sha256,
                    mlflow_experiment_id=mlflow_experiment_id,
                    mlflow_run_id=mlflow_run_id,
                )
            )
        return training_id

    def register_domain_model_version(
        self,
        *,
        registered_name: str,
        version: str,
        source_run_id: UUID,
        bundle_checksum: str,
        alias: str | None = None,
        validation_status: str = "unvalidated",
    ) -> UUID:
        if (
            alias is not None
            and alias.casefold() in PROTECTED_MODEL_ALIASES
            and validation_status != VALIDATION_VALIDATED
        ):
            raise SmartScanError(
                f"Refusing to assign {alias!r} to an unvalidated model bundle."
            )
        row_id = uuid.uuid4()
        with session_scope(self._sessions) as session:
            self._require_run(session, source_run_id)
            session.add(
                ModelVersionRow(
                    id=row_id,
                    registered_name=registered_name,
                    version=str(version),
                    alias=alias,
                    source_run_id=source_run_id,
                    bundle_checksum=bundle_checksum,
                    validation_status=validation_status,
                )
            )
        return row_id

    def _try_track(self, domain_run_id: UUID) -> None:
        payload = self._tracking_payload(domain_run_id)
        try:
            existing = self.tracker.find_by_domain_id(domain_run_id)
            mlflow_id = existing or self.tracker.log_run(payload)
            experiment_id = None
            getter = getattr(self.tracker, "experiment_id", None)
            if callable(getter):
                experiment_id = getter(payload.experiment)
        except Exception as exc:
            warn_tracking_failure(domain_run_id, exc)
            with session_scope(self._sessions) as session:
                run = self._require_run(session, domain_run_id)
                run.sync_status = SYNC_ERROR
                run.tracking_error = str(exc)
                run.updated_at = utcnow()
            return
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            if mlflow_id:
                run.mlflow_run_id = mlflow_id
                run.mlflow_experiment_id = experiment_id
                run.sync_status = SYNC_SYNCED
                run.tracking_error = None
            else:
                run.sync_status = SYNC_PENDING
            run.updated_at = utcnow()

    def _reconcile_one(self, domain_run_id: UUID) -> ReconcileResult:
        payload = self._tracking_payload(domain_run_id)
        try:
            found = self.tracker.find_all_by_domain_id(domain_run_id)
            mlflow_id: str | None = found[0] if found else self.tracker.log_run(payload)
            experiment_id: str | None = None
            getter = getattr(self.tracker, "experiment_id", None)
            if callable(getter):
                experiment_id = getter(payload.experiment)
        except Exception as exc:
            warn_tracking_failure(domain_run_id, exc)
            with session_scope(self._sessions) as session:
                run = self._require_run(session, domain_run_id)
                run.sync_status = SYNC_ERROR
                run.tracking_error = str(exc)
                run.updated_at = utcnow()
            return ReconcileResult(
                domain_run_id=domain_run_id,
                sync_status=SYNC_ERROR,
                mlflow_run_id=None,
                error=str(exc),
            )
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            if mlflow_id:
                run.mlflow_run_id = mlflow_id
                run.mlflow_experiment_id = experiment_id
                run.sync_status = SYNC_SYNCED
                run.tracking_error = None
                status = SYNC_SYNCED
            else:
                run.sync_status = SYNC_PENDING
                status = SYNC_PENDING
            run.updated_at = utcnow()
            linked = run.mlflow_run_id
        return ReconcileResult(
            domain_run_id=domain_run_id, sync_status=status, mlflow_run_id=linked
        )

    def _reconcile_targets(
        self, domain_run_id: UUID | None, *, all_pending: bool
    ) -> list[UUID]:
        with session_scope(self._sessions) as session:
            if domain_run_id is not None:
                self._require_run(session, domain_run_id)
                return [domain_run_id]
            if not all_pending:
                raise SmartScanError("reconcile_mlflow requires a domain_run_id or all_pending=True.")
            rows = session.scalars(
                select(RunRow.domain_run_id).where(RunRow.sync_status.in_((SYNC_PENDING, SYNC_ERROR)))
            ).all()
            return list(rows)

    def _tracking_payload(self, domain_run_id: UUID) -> TrackingPayload:
        with session_scope(self._sessions) as session:
            run = self._require_run(session, domain_run_id)
            scenario = session.get(ScenarioRow, run.scenario_id)
            gt_row = session.scalar(
                select(GroundTruthRow).where(GroundTruthRow.scenario_id == run.scenario_id)
            )
            rc = session.get(ReceiverConfigRow, run.receiver_config_id)
            metrics_row = session.scalar(
                select(MetricsRow).where(MetricsRow.run_id == domain_run_id)
            )
            obs_row = session.scalar(
                select(ObservationLogRow).where(ObservationLogRow.run_id == domain_run_id)
            )
            files: list[Path] = []
            if metrics_row is not None:
                files.append(self.artifacts.resolve(metrics_row.relative_path))
            if obs_row is not None:
                files.append(self.artifacts.resolve(obs_row.relative_path))
            if gt_row is not None:
                files.append(self.artifacts.resolve(gt_row.relative_path))
            params = {
                "strategy": run.strategy,
                "schema_version": run.schema_version,
                "scenario_name": scenario.name if scenario else "",
            }
            seeds = loads_json(run.seeds_json)
            for key, value in seeds.items():
                params[f"seed_{key}"] = str(value)
            if rc is not None:
                params["receiver_config_hash"] = rc.config_hash
            if gt_row is not None:
                params["n_steps"] = str(gt_row.n_steps)
                params["n_bands"] = str(gt_row.n_bands)
                params["dt_s"] = str(gt_row.dt_s)
            tags = {
                "domain_run_id": str(domain_run_id),
                "status": run.status,
                "strategy": run.strategy,
            }
            if run.git_sha:
                tags["git_sha"] = run.git_sha
            if gt_row is not None:
                tags["content_fingerprint"] = gt_row.content_fingerprint
            if rc is not None:
                tags["receiver_config_hash"] = rc.config_hash
            metric_values: dict[str, float] = {}
            if metrics_row is not None:
                tags["metrics_content_fingerprint"] = metrics_row.content_fingerprint
                raw = {
                    key: getattr(metrics_row, key) for key in INDEXED_METRIC_KEYS
                }
                metric_values = finite_metrics(raw)
            return TrackingPayload(
                domain_run_id=domain_run_id,
                experiment=EXPERIMENT_BASELINES,
                params=params,
                metrics=metric_values,
                tags=tags,
                artifact_files=files,
            )

    def _attach_environment_snapshot(self, domain_run_id: UUID) -> None:
        from smartscan.config import project_root

        root = project_root()
        lock = root / "uv.lock"
        if lock.is_file():
            ref = self.artifacts.put_file(f"runs/{domain_run_id}/uv.lock", lock)
            self._add_artifact_row(domain_run_id, "uv.lock", ref, "text/plain")
        freeze = _pip_freeze()
        if freeze:
            ref = self.artifacts.put_bytes(
                f"runs/{domain_run_id}/pip-freeze.txt", freeze.encode("utf-8")
            )
            self._add_artifact_row(domain_run_id, "pip_freeze", ref, "text/plain")

    def _add_artifact_row(
        self, domain_run_id: UUID, artifact_type: str, ref: ArtifactRef, media_type: str
    ) -> None:
        with session_scope(self._sessions) as session:
            existing = session.scalar(
                select(ArtifactRow).where(
                    ArtifactRow.run_id == domain_run_id,
                    ArtifactRow.artifact_type == artifact_type,
                    ArtifactRow.relative_path == ref.relative_path,
                )
            )
            if existing is not None:
                existing.artifact_sha256 = ref.sha256
                return
            session.add(
                ArtifactRow(
                    run_id=domain_run_id,
                    artifact_type=artifact_type,
                    relative_path=ref.relative_path,
                    artifact_sha256=ref.sha256,
                    media_type=media_type,
                    metadata_json="{}",
                )
            )

    def _upsert_data_source(self, session: Session, provenance: Provenance) -> UUID | None:
        payload = strip_volatile(provenance.model_dump(mode="json"))
        fingerprint = content_fingerprint(payload)
        existing = session.scalar(
            select(DataSourceRow).where(DataSourceRow.fingerprint == fingerprint)
        )
        if existing is not None:
            return existing.id
        row = DataSourceRow(
            source=provenance.source,
            type=str(payload.get("source", provenance.source)),
            version=provenance.dataset_version,
            license=None,
            provenance_json=dumps_json(payload),
            fingerprint=fingerprint,
        )
        session.add(row)
        session.flush()
        return row.id

    def _require_run(self, session: Session, domain_run_id: UUID) -> RunRow:
        run = session.get(RunRow, domain_run_id)
        if run is None:
            raise SmartScanError(f"Unknown domain_run_id {domain_run_id}.")
        return run


def _as_provenance(value: Provenance | dict[str, Any]) -> Provenance:
    if isinstance(value, Provenance):
        return value
    return Provenance.model_validate(value)


def _as_evaluation(value: EvaluationResult | MetricsReport) -> EvaluationResult:
    if isinstance(value, EvaluationResult):
        return value
    raise SmartScanError(
        "Repository save_metrics requires a Stage 3 EvaluationResult "
        "(full MetricsReport JSON plus tables), not a MetricsReport alone."
    )


def _pip_freeze() -> str | None:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
