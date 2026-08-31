# SIH26055 Build Contract

Frozen in Stage 1. Later stages import these interfaces; they must not fork competing versions. Compatible clarifications may be added. Unavoidable interface changes must be recorded here and migrated in the same stage.

## Global execution contract

Read the entire repository and this specification before editing. Preserve working prior-stage code and user changes.

Build only the requested stage. Use prior-stage public interfaces; do not duplicate or fork GroundTruth, logs, metrics, repositories or configuration models.

Use public, synthetic, or properly licensed user-supplied data only. Do not invent, scrape, or redistribute J.C. Wise or other restricted data without explicit rights, and never include classified emitter parameters.

Stay offline by default. External datasets are optional runtime inputs; unit tests use tiny generated fixtures and must pass without credentials or downloads.

Use pathlib and project-root-relative paths. Never write outside the repository or require administrator privileges.

Use fixed, explicitly recorded seeds for Python, NumPy, PyTorch, Gymnasium and policies. Same inputs and seed must reproduce the same artifacts and metrics within documented tolerance.

Canonical content fingerprints hash schema-versioned semantic inputs using sorted keys and normalized numeric forms while excluding volatile timestamps and absolute paths. Artifact SHA-256 hashes serialized bytes. Semantically identical content may retain its fingerprint even when compression changes artifact bytes.

Keep policy-visible observations, prediction features and rewards free of Stage-1 oracle truth, true emitter IDs/parameters and future data. Ground truth is allowed only inside the physical simulator and post-run evaluator.

Write type hints and docstrings for public APIs. Add tests before or with implementation. Run Ruff, mypy and relevant pytest suites before declaring completion.

Do not fabricate benchmark results or quietly relax thresholds. If an acceptance gate fails, report the failure and continue improving only within the current stage.

Keep large arrays and model files out of SQLite; store relative artifact paths plus SHA-256 checksums. Never load pickle, joblib, or Stable-Baselines3 bundles from untrusted paths.

At the end of a stage, write `docs/stage_reports/STAGE_N_REPORT.md`, state `implementation_complete` and any `performance_gate_passed` as separate booleans, and stop.

## Locked seven-stage architecture

| Stage | Build boundary | Frozen output |
| --- | --- | --- |
| 1 | RF environment + data adapters | GroundTruth, EventTable, scenario/data provenance |
| 2 | Receiver + detection | ObservationLog, DecisionLog, open-loop schedules |
| 3 | Metrics + forecast evaluation | MetricsReport, sensitivity curve, event matching |
| 4 | Persistence + MLflow | Queryable runs, checksummed artifacts, tracking links |
| 5 | Prediction + smart scheduler | Completed-command hazard predictor, contextual bandit, PPO policy, registered bundle |
| 6 | Interactive dashboard | Offline run/replay/compare/registry interface |
| 7 | Integration + benchmark hardening | One-command demo and held-out evidence pack |

## Frozen data contracts

| Contract | Required fields / meaning |
| --- | --- |
| BandPlan | `band_edges_hz[K+1]`, `band_names[K]`, `profile_id`, `scan_span_hz`; half-open `[low, high)` |
| GroundTruth | `dt_s`, `n_steps`, BandPlan, `occupied[N,K]`, `signal_power_w[N,K]`, EventTable, provenance, `content_fingerprint`, `artifact_sha256` |
| EventTable | `event_id`, `emitter_id`, `band`, `start_step` inclusive, `end_step` exclusive, `source`, optional evaluator-only `threat_weight` |
| ReceiverConfig | `receiver_ibw_hz`, `scan_span_hz`, `tune_latency_steps`, `dwell_bins`, noise mode; `scan_span_hz/receiver_ibw_hz >= 10`; one receiver channel in v1 |
| ScanCommand | `decision_id`, `target_band`, `dwell_steps` |
| ObservationLog | per-step physical state; no policy-visible oracle labels |
| DecisionLog | one row per completed command; nullable Stage 5 forecast fields |
| MetricsReport | seven official metrics plus supporting interception/delay/calibration outputs |
| RunIdentity | UUID `domain_run_id` plus hashes, seeds, git SHA, optional `mlflow_run_id` |

Python modules: `smartscan.types` (contracts), `smartscan.rf` (Stage 1), later stages import these names.

## Frozen metric names

Pd, Pfa, Sensitivity, Average intercept rate, Average reward/cost, Correct predictions, Average intercept-time error.

Supporting: event interception ratio, first-detection delay statistics, censored/penalized all-event delay, missed-event count, wasted-dwell fraction, tuning fraction, threat-weighted capture, hit-forecast Brier/ECE, activity-forecast Brier/ECE.

Formulas are implemented in Stage 3. Names and denominators are frozen here so Stages 2–7 do not invent parallel metrics.

## Evaluator-only fields

`threat_weight`, `hidden_metadata`, GroundTruth occupancy/power, true emitter identities and parameters. These must not appear in policy-visible observations, features, or rewards.

## Technology lock

Python 3.11, src layout, `pyproject.toml` + `uv.lock`. NumPy, SciPy, pandas, h5py, PyYAML, Pydantic. Later: SQLAlchemy 2 / Alembic / SQLite, MLflow, PyTorch, Gymnasium, Stable-Baselines3, Streamlit / Plotly. Quality: pytest, pytest-cov, Ruff, mypy.

## Stage 2 receiver and logs

`ObservationLog` (policy-visible, per step): `step`, `receiver_state` (`TUNING`/`DWELLING`), `commanded_band`, `tuned_band` (null while tuning), `decision_id`, `dwell_progress`, `integrated_energy`, `measured_snr_db` (estimate), `detection`. No occupancy or emitter IDs.

`DecisionLog` (one row per completed command): `start_step`, `tune_end_step`, `end_step` (intercept timestamp), `target_band`, `dwell_steps`, `hit`, measured SNR, receiver seed, nullable Stage 5 forecast fields. Incomplete end-of-run dwells produce no decision.

Open-loop schedules share `Schedule.next_command(ScheduleView)`: `SequentialSchedule`, `UniformRandomSchedule`, `FixedPrioritySchedule`. They must not read GroundTruth occupancy. `run_schedule` in `smartscan.receiver.scanner` is the Stage 2 runner.

`ReceiverConfig.noise_power_w` is an optional normalized-mode override (default 1.0). Physical mode uses Boltzmann noise `k*T0*IBW*F`.

CLI `--seed` is the detector RNG. `--schedule-seed` (default 0) seeds `UniformRandomSchedule` independently so changing only detector noise does not change commanded bands.

## Stage 3 metrics

`evaluate_strategy(truth, observations, decisions)` returns an `EvaluationResult` wrapping `MetricsReport`. Capture units are `BandOccupancyEvent`s (maximal occupancy runs per band), not emitter events. One detection matches at most one event in the same band, ordered by detection time then event start.

Frozen metrics and denominators:

- **Pd** — TP occupied completed dwells / occupied completed dwells
- **Pfa** — false-alarm noise-only completed dwells / noise-only completed dwells
- **Sensitivity** — SNR dB at target Pd on a controlled single-band curve (analytic or Monte Carlo); not the scheduler-conditioned Pd
- **Average intercept rate** — matched BandOccupancyEvents / simulated seconds
- **Average reward/cost** — mean DecisionLog.reward; unavailable until rewards exist. `evaluation_score` is intercept ratio minus wasted-dwell fraction, with components listed separately
- **Correct predictions** — 100×(TP+TN)/scored decisions using pre-action `p_active` vs usable-dwell occupancy; `p_hit` Brier/ECE is separate
- **Average intercept-time error** — MAE on uncensored pre-action time-to-next-completed-hit forecasts

Zero denominators and missing forecasts are `available=false` with a reason, never NaN/Inf/zero. `compare_runs` / `paired_compare` resample whole runs or seeds, never time steps.

## Stage 4 persistence and local MLflow

Domain records live in `data/smartscan.db`. MLflow metadata lives in `data/mlflow.db` (never the same file). Large arrays are stored under `artifacts/store/` with relative paths and SHA-256 checksums. `domain_run_id` is the project identity; MLflow runs are tagged with it and `mlflow_run_id` is stored back on the domain row. Domain and MLflow writes are not one ACID transaction: `sync_status` is `pending|synced|error`, and `mlflow reconcile` retries without duplicating runs.

Do not register an untrained placeholder as `champion` / `production`.

## Stage 5 prediction and scheduler

Policy-visible inputs are `ObservableTransition` plus the Stage 2 `ScheduleView`. `FeatureBuilder`, `RewardCalculator`, `HitHazardPredictor` and policies must not accept GroundTruth, truth event tables, or hidden threat labels.

Action space is `Discrete(K*L)` with `band = action // L` and `dwell_bin = action % L`. The saved bundle is tied to that BandPlan, IBW, and dwell-bin list.

Non-oracle baselines: sequential, uniform-random, fixed-priority (public list only), reactive hit-recency, contextual Thompson sampling, and live-only periodic-intercept (search then stare; not in the frozen held-out gate set). Oracle ceiling is evaluator-only, labeled unattainable, and is never stored as a deployable model.

`performance_gate_passed` is independent of `implementation_complete`. Champion/production aliases require a passing held-out gate.

## Stage 6 dashboard

The Streamlit UI is a thin client. `smartscan.dashboard.services` orchestrates Stage 1–5 APIs (`simulate`, `run_policy_episode`, `evaluate_strategy`, `make_policy`, repositories, bundle load). Plot and page modules must not reimplement detector or metric formulas.

Public service functions: `load_dashboard_config`, `run_experiment`, `build_replay_frame`, `explain_decision`, `comparison_table`, `load_performance_gate`, `prepare_demo_bundle` / `load_demo_bundle`, `export_comparison`, `doctor_report`, `lineage_panel`, `list_history`, `safe_user_path`, `model_bundle_dir`. CLI: `python -m smartscan.cli dashboard` (127.0.0.1) and `python -m smartscan.cli doctor`.

Evaluation overlay may show GroundTruth occupancy after a run; it must not change actions, rewards, or persistence. `performance_gate_passed=false` displays candidate status and failed criteria, never a scheduler win badge. Oracle ceiling is labeled unattainable and excluded from deployable comparison.

## Stage 7 release

`smartscan.release` freezes Stage 5 `configs/benchmark_final.yaml` and `configs/held_out_manifest.json` hashes in `configs/frozen_hashes.json`. `require_frozen_hashes()` refuses final evidence on drift. `best-available` resolves to champion only when `performance_gate_passed=true` and a valid PPO bundle exists; otherwise structurally valid candidate PPO; otherwise `contextual-thompson`. A fallback is never renamed champion.

CLI: `benchmark --config configs/benchmark_final.yaml --manifest held_out_manifest.json --track`, `demo --offline`, `run --strategy best-available`. Offline demo must not download or retrain. Full held-out evaluation uses all predeclared pairs; it is not a CI default (`SMARTSCAN_FULL_BENCH=1` opt-in). `implementation_complete` and `performance_gate_passed` remain separate booleans.

## Stage 4 public API

`RunRepository.create_scenario` / `start_run` / `attach_logs` / `save_metrics` / `complete_run` / `fail_run` / `get_run(verify_checksums=True)` / `list_runs` / `recompute_and_verify` / `reconcile_mlflow`. Tracking: `ExperimentTracker` with `MLflowTracker` and `NoOpTracker`. CLI `--order-by avg_intercept_rate` maps to frozen metric `average_intercept_rate`. Repository `save_metrics(domain_run_id, …)` is distinct from `smartscan.metrics.engine.save_metrics`.

## Current engineering vs scientific state (completion pass)

Public strategies are exactly seven: `sequential`, `random`, `fixed-priority`, `reactive`, `contextual-thompson`, `periodic-intercept`, `ppo`. Registry: `smartscan.ml.strategy_registry`. Live dashboard PPO weights are `artifacts/models/scheduler_v4` (candidate). Official frozen-gate evidence is `v2_frozen_gate` on `artifacts/models/scheduler_full` with `artifacts/models/held_out_gate.json`. Research protocols `v3_research` and `v4_research` are not interchangeable with the frozen gate. `performance_gate_passed` remains false; Champion is unset. Redistributable model bundles and demo logs are committed; local SQLite, MLflow artifact stores, and training datasets stay gitignored.
