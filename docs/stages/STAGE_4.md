BEGIN STAGE 4 PROMPT - COPY FROM HERE
You are the data-platform and MLOps engineer for Stage 4. Build a durable local experiment backbone so every simulation, baseline, training run, evaluation, metric, artifact and model version can be reproduced and queried later.
Scope: Build the SQLite/SQLAlchemy domain store, migrations, checksummed artifact store, repository services and local MLflow tracking/model-registry foundation linked by stable run IDs.
Do not build: Do not build the learned predictor, train PPO or build the dashboard. Stage 4 may log Stage 1-3 baseline runs to prove integration, but it must not create fake ML results.
Storage separation and identity
Use data/smartscan.db for application/domain records and data/mlflow.db for MLflow metadata. Never point both systems at the same SQLite file.
Use UUID domain_run_id as the project identity. When MLflow is enabled, create/tag an MLflow run with domain_run_id and store mlflow_run_id back on the domain record.
Store large arrays/logs/model bundles under a configurable artifact root using project-relative paths and artifact SHA-256. SQLite stores metadata, scalar metrics, canonical semantic content_fingerprint values, JSON config and artifact references only.
Use UTC-aware timestamps, status transitions (created/running/completed/failed), error summaries and schema versions. A failed run remains queryable.
Use SQLAlchemy 2.x typed mappings, session boundaries and Alembic migrations. SQLite foreign keys are enabled. Repository code must also accept a PostgreSQL URL without schema redesign, but PostgreSQL setup is not required.
Minimum domain schema
Table
Minimum purpose/fields
data_sources
source/type/version/license/provenance/fingerprint
scenarios
name/config/band plan/seed/source ID/config hash
ground_truths
scenario ID/schema/shape/dt/path/artifact SHA-256/content fingerprint
receiver_configs
normalized parameters/config hash
runs
domain ID/scenario/receiver/strategy/seeds/status/git SHA/MLflow IDs
observation_logs
run ID/path/checksum/schema/row counts
decision_logs
run ID/path/checksum/schema/row counts plus pre-action forecast columns
metrics
run ID/schema/full JSON plus indexed scalar columns for all seven metrics and interception ratio
artifacts
run ID/type/path/checksum/media type/metadata
training_runs
run ID/algorithm/split/hyperparameters/model bundle/MLflow experiment and run IDs
model_versions
registered name/version/alias/source run/bundle checksum/validation status
Repository and service API
create_scenario(ground_truth, provenance) -> scenario_idstart_run(scenario_id, receiver_config, strategy, seeds) -> domain_run_idattach_logs(domain_run_id, observation_log, decision_log)save_metrics(domain_run_id, metrics_report)complete_run(domain_run_id) / fail_run(domain_run_id, error)get_run(domain_run_id, verify_checksums=True)list_runs(filters, order_by_metric)recompute_and_verify(domain_run_id)reconcile_mlflow(domain_run_id | all)
Write artifacts atomically through a temporary file then rename; calculate checksum from final bytes. Reject path traversal and absolute paths in persisted references.
Use canonical JSON with sorted keys, normalized numeric forms and volatile timestamps/absolute paths excluded for config and semantic content fingerprints. Store the committed dependency lock plus installed-package snapshot as artifacts on completed benchmark/training runs.
Loading with verify_checksums=True must fail clearly on missing/corrupt artifacts and never return partially trusted data.
Make list/query helpers support scenario, strategy, date, status, model version and required metric ranges.
MLflow implementation
Add mlflow as a dependency and a smartscan.storage.tracking.ExperimentTracker interface with MLflowTracker and disabled/no-op implementations. Production/demo config enables MLflow; unit tests may use a temporary SQLite tracking URI directly.
Provide a local serve command equivalent to: mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///data/mlflow.db --artifacts-destination artifacts/mlflow. Resolve all paths from the project root.
Create named experiments such as smartscan-baselines, smartscan-predictor and smartscan-scheduler. Log Stage 1-3 configs, fingerprints, counts and metrics for persisted baselines.
Use a database-backed MLflow store so the Model Registry is available in Stage 5. Create helper APIs to log a model bundle, register a version, set tags and aliases, but do not register an untrained placeholder as champion.
Domain DB writes and MLflow writes cannot be one ACID transaction. Use sync_status values pending/synced/error and a deterministic reconcile command that can safely retry without duplicating runs.
The project must still run simulations/evaluation when the MLflow server is down: mark tracking error, preserve the domain run, show a clear warning and allow reconciliation later.
CLI and example
python -m smartscan.cli db upgradepython -m smartscan.cli mlflow servepython -m smartscan.cli run --config configs/demo.yaml --strategy sequential --persist --trackpython -m smartscan.cli runs list --strategy sequential --order-by avg_intercept_ratepython -m smartscan.cli runs verify <domain_run_id>python -m smartscan.cli mlflow reconcile --all
Tests and acceptance gate
Alembic upgrade from an empty temporary directory creates the expected schema; foreign keys and unique constraints work.
Stage 1-3 run round-trips through repositories with identical config hashes, arrays/log checksums, metric scalars and full MetricsReport.
Semantically identical inputs share a content_fingerprint; identical serialized bytes share artifact_sha256. Compression-only byte changes may retain the content fingerprint while changing artifact_sha256. Document deduplication policy and detect corrupt/missing files.
Relative-path and traversal tests work on Windows/POSIX path forms without escaping the artifact root.
Temporary MLflow SQLite backend receives params, metrics, tags and artifacts; domain and MLflow IDs link in both directions.
Simulated interrupted one-sided writes produce pending/error and reconcile to exactly one linked MLflow run.
MLflow unavailable does not lose the domain run; a later reconciliation succeeds.
Query sorting/filtering works for all seven scalar metrics and interception ratio. Stage 1-4 suites, Ruff and mypy pass; storage code has at least 90% line coverage.
Stage 4 is complete only when: A baseline run can be created, checked, queried, reloaded and recomputed from local storage, while its linked MLflow run exposes the same provenance, metrics and artifacts in the local UI.
Required completion report
Create docs/stage_reports/STAGE_4_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 4. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 4 PROMPT - STOP COPYING
