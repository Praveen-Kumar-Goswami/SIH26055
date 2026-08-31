from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from tests.conftest import TINY_SIM

from smartscan.config import SimulateConfig
from smartscan.metrics.engine import evaluate_strategy
from smartscan.receiver.logs import ReceiverRun, save_receiver_run
from smartscan.receiver.scanner import run_schedule
from smartscan.receiver.schedules import make_schedule
from smartscan.rf.environment import simulate
from smartscan.rf.io import save_ground_truth
from smartscan.storage.constants import INDEXED_METRIC_KEYS
from smartscan.storage.db import session_scope
from smartscan.storage.models import GroundTruthRow, MetricsRow
from smartscan.storage.pipeline import persist_baseline_run
from smartscan.storage.repositories import RunFilters, RunRepository
from smartscan.storage.tracking import FailingTracker, NoOpTracker
from smartscan.types import MetricsReport, SmartScanError


def _persist(repo: RunRepository, receiver_config, *, strategy: str = "sequential", seed: int = 42):
    return persist_baseline_run(
        simulate_config=TINY_SIM,
        receiver_config=receiver_config,
        strategy=strategy,
        receiver_seed=seed,
        schedule_seed=0,
        dwell_steps=8,
        repo=repo,
        track=False,
    )


def test_roundtrip_hashes_and_metrics(domain_repo: RunRepository, receiver_config) -> None:
    truth = simulate(SimulateConfig.model_validate(TINY_SIM))
    schedule = make_schedule("sequential", dwell_steps=8, schedule_seed=0)
    run = run_schedule(truth, schedule, receiver_config, receiver_seed=42, default_dwell_steps=8)
    expected = evaluate_strategy(
        truth, run.observations, run.decisions, receiver_config=receiver_config
    )
    domain_run_id = _persist(domain_repo, receiver_config)
    stored = domain_repo.get_run(domain_run_id, verify_checksums=True)
    assert stored.identity.content_fingerprint == truth.content_fingerprint
    assert stored.identity.config_hash == run.observations.receiver_config_hash
    assert stored.observations is not None
    assert stored.decisions is not None
    assert stored.evaluation is not None
    assert stored.evaluation.content_fingerprint == expected.content_fingerprint
    for key in INDEXED_METRIC_KEYS:
        left = stored.evaluation.report.metrics[key]
        right = expected.report.metrics[key]
        assert left.available == right.available
        assert left.value == right.value
        assert left.numerator == right.numerator
        assert left.denominator == right.denominator
    report = domain_repo.recompute_and_verify(domain_run_id)
    assert report.ok
    assert report.content_fingerprint_match
    assert report.checksum_ok
    assert not report.metric_mismatches


def test_fingerprint_reuse_and_compression_sha(domain_repo: RunRepository, tmp_path: Path) -> None:
    a = simulate(SimulateConfig.model_validate(TINY_SIM))
    b = simulate(SimulateConfig.model_validate(TINY_SIM))
    assert a.content_fingerprint == b.content_fingerprint
    id1 = domain_repo.create_scenario(a, a.provenance)
    id2 = domain_repo.create_scenario(b, b.provenance)
    assert id1 == id2
    npz = tmp_path / "a.npz"
    h5 = tmp_path / "a.h5"
    save_ground_truth(a, npz)
    save_ground_truth(b, h5)
    assert a.content_fingerprint == b.content_fingerprint
    assert a.artifact_sha256 != b.artifact_sha256
    with session_scope(domain_repo._sessions) as session:
        rows = list(session.scalars(select(GroundTruthRow)))
        assert len(rows) == 1


def test_fail_run_stays_queryable(domain_repo: RunRepository, receiver_config) -> None:
    truth = simulate(SimulateConfig.model_validate(TINY_SIM))
    scenario_id = domain_repo.create_scenario(truth, truth.provenance)
    domain_run_id = domain_repo.start_run(
        scenario_id, receiver_config, "sequential", {"receiver": 1}
    )
    domain_repo.fail_run(domain_run_id, "boom")
    listed = domain_repo.list_runs(RunFilters(status="failed"))
    assert len(listed) == 1
    assert listed[0].domain_run_id == domain_run_id
    stored = domain_repo.get_run(domain_run_id, verify_checksums=True)
    assert stored.status == "failed"
    assert stored.error_summary == "boom"
    assert stored.observations is None


def test_checksum_fail_closed(domain_repo: RunRepository, receiver_config) -> None:
    domain_run_id = _persist(domain_repo, receiver_config)
    metrics_path = domain_repo.artifacts.resolve(f"runs/{domain_run_id}/metrics.json")
    metrics_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(SmartScanError, match="Checksum verification failed"):
        domain_repo.get_run(domain_run_id, verify_checksums=True)
    missing = domain_repo.artifacts.resolve(f"runs/{domain_run_id}/receiver_run.npz")
    missing.unlink()
    with pytest.raises(SmartScanError, match="Checksum verification failed"):
        domain_repo.get_run(domain_run_id, verify_checksums=True)


def test_list_sort_and_filter_metrics(domain_repo: RunRepository, receiver_config) -> None:
    first = _persist(domain_repo, receiver_config, strategy="sequential")
    second = persist_baseline_run(
        simulate_config={**TINY_SIM, "seed": 7},
        receiver_config=receiver_config,
        strategy="random",
        receiver_seed=1,
        schedule_seed=2,
        dwell_steps=8,
        repo=domain_repo,
        track=False,
    )
    with session_scope(domain_repo._sessions) as session:
        by_id = {row.run_id: row for row in session.scalars(select(MetricsRow))}
        by_id[first].pd = 0.2
        by_id[second].pd = 0.8
        by_id[first].average_intercept_rate = 1.0
        by_id[second].average_intercept_rate = 3.0
        by_id[first].event_interception_ratio = 0.1
        by_id[second].event_interception_ratio = 0.9
        for key in INDEXED_METRIC_KEYS:
            if getattr(by_id[first], key) is None and key not in {
                "pd",
                "average_intercept_rate",
                "event_interception_ratio",
            }:
                setattr(by_id[first], key, 0.0)
                setattr(by_id[second], key, 1.0)
    ordered = domain_repo.list_runs(order_by_metric="avg_intercept_rate")
    assert ordered[0].domain_run_id == second
    assert ordered[1].domain_run_id == first
    filtered = domain_repo.list_runs(
        RunFilters(strategy="random", metric_min={"pd": 0.5}, metric_max={"pd": 1.0})
    )
    assert [row.domain_run_id for row in filtered] == [second]
    for key in INDEXED_METRIC_KEYS:
        ranked = domain_repo.list_runs(order_by_metric=key)
        assert len(ranked) == 2
        assert ranked[0].metrics[key] >= ranked[1].metrics[key]


def test_mlflow_down_preserves_domain(domain_repo: RunRepository, receiver_config) -> None:
    domain_repo.tracker = FailingTracker("tracking down")
    with pytest.warns(UserWarning, match="MLflow tracking failed"):
        domain_run_id = persist_baseline_run(
            simulate_config=TINY_SIM,
            receiver_config=receiver_config,
            strategy="sequential",
            repo=domain_repo,
            track=True,
        )
    stored = domain_repo.get_run(domain_run_id, verify_checksums=True)
    assert stored.status == "completed"
    assert stored.sync_status == "error"
    assert stored.identity.mlflow_run_id is None
    listed = domain_repo.list_runs()
    assert listed[0].domain_run_id == domain_run_id


def test_save_metrics_rejects_bare_report(domain_repo: RunRepository, receiver_config) -> None:
    truth = simulate(SimulateConfig.model_validate(TINY_SIM))
    scenario_id = domain_repo.create_scenario(truth, truth.provenance)
    domain_run_id = domain_repo.start_run(
        scenario_id, receiver_config, "sequential", {"receiver": 0}
    )
    with pytest.raises(SmartScanError, match="EvaluationResult"):
        domain_repo.save_metrics(domain_run_id, MetricsReport())


def test_complete_failed_run_rejected(domain_repo: RunRepository, receiver_config) -> None:
    truth = simulate(SimulateConfig.model_validate(TINY_SIM))
    scenario_id = domain_repo.create_scenario(truth, truth.provenance)
    domain_run_id = domain_repo.start_run(
        scenario_id, receiver_config, "sequential", {"receiver": 0}
    )
    domain_repo.fail_run(domain_run_id, "nope")
    with pytest.raises(SmartScanError, match="Cannot complete"):
        domain_repo.complete_run(domain_run_id, track=False)


def test_unknown_metric_order_by(domain_repo: RunRepository) -> None:
    with pytest.raises(SmartScanError, match="Unknown metric"):
        domain_repo.list_runs(order_by_metric="not_a_metric")


def test_training_and_model_version_helpers(domain_repo: RunRepository, receiver_config) -> None:
    domain_run_id = _persist(domain_repo, receiver_config)
    training_id = domain_repo.record_training_run(
        domain_run_id, algorithm="ppo", hyperparameters={"lr": 0.001}
    )
    assert training_id is not None
    with pytest.raises(SmartScanError, match="champion"):
        domain_repo.register_domain_model_version(
            registered_name="smartscan-scheduler",
            version="1",
            source_run_id=domain_run_id,
            bundle_checksum="abc",
            alias="champion",
            validation_status="unvalidated",
        )
    mv = domain_repo.register_domain_model_version(
        registered_name="smartscan-scheduler",
        version="1",
        source_run_id=domain_run_id,
        bundle_checksum="abc",
        alias="staging",
        validation_status="unvalidated",
    )
    listed = domain_repo.list_runs(RunFilters(model_version="staging"))
    assert listed[0].domain_run_id == domain_run_id
    assert mv is not None


def test_attach_logs_twice(domain_repo: RunRepository, receiver_config, tmp_path: Path) -> None:
    truth = simulate(SimulateConfig.model_validate(TINY_SIM))
    scenario_id = domain_repo.create_scenario(truth, truth.provenance)
    domain_run_id = domain_repo.start_run(
        scenario_id, receiver_config, "sequential", {"receiver": 0}
    )
    schedule = make_schedule("sequential", dwell_steps=8)
    run = run_schedule(truth, schedule, receiver_config, receiver_seed=0, default_dwell_steps=8)
    domain_repo.attach_logs(domain_run_id, run.observations, run.decisions)
    with pytest.raises(SmartScanError, match="already attached"):
        domain_repo.attach_logs(domain_run_id, run.observations, run.decisions)
    save_receiver_run(ReceiverRun(observations=run.observations, decisions=run.decisions), tmp_path / "r.npz")


def test_noop_complete_leaves_pending(domain_repo: RunRepository, receiver_config) -> None:
    domain_repo.tracker = NoOpTracker()
    domain_run_id = persist_baseline_run(
        simulate_config=TINY_SIM,
        receiver_config=receiver_config,
        strategy="sequential",
        repo=domain_repo,
        track=True,
    )
    stored = domain_repo.get_run(domain_run_id)
    assert stored.sync_status == "pending"
    with pytest.raises(SmartScanError, match="all_pending"):
        domain_repo.reconcile_mlflow()
