# SIH26055 Seven-Stage Build Specification

SMART INDIA HACKATHON 2026  |  DRDO  |  SOFTWARE
SIH26055
Smart Scan Strategy for Electronic Warfare
Final seven-stage build specification for Codex or Cursor
Purpose: Use these prompts to build a complete, reproducible, offline-first prototype in seven controlled stages. This specification closes the mathematical, dataset, prediction, evaluation, oracle-leakage, and experiment-tracking gaps in the earlier draft.
Important: This is an implementation specification, not a guarantee of winning. A competitive result exists only when the generated repository passes every stage gate and the final held-out benchmark shows a real improvement without cherry-picking or fabricated numbers.
How to use this file
Attach this DOCX to Codex/Cursor for review. In the repository, keep the authoritative text at docs/SIH26055_BUILD_SPEC.md and exactly one bounded stage prompt per file under docs/stages/.
For each session say: Read the entire specification and current repository. Execute Stage N only. Do not begin Stage N+1.
If the agent cannot read DOCX reliably, copy the Global Execution Contract plus exactly one bounded prompt between its BEGIN and END markers.
Do not advance until implementation_complete=true and the stage report records executed tests and acceptance evidence. Record performance_gate_passed separately when applicable; failure blocks champion promotion and performance-ready claims, not completion of otherwise passing engineering work.
Keep docs/BUILD_CONTRACT.md and docs/stage_reports/STAGE_N_REPORT.md in the repository so later stages inherit frozen interfaces and explicit gate status.
Problem-statement contract
The project must model a narrow-instantaneous-bandwidth receiver scanning a much wider spectrum without reliable prior emitter intelligence. It must use simulated RF truth to produce hits and misses, predict intercept time and interception ratio for spatially scanning and frequency-agile emitters, learn a robust schedule from observable outcomes, prioritize new or threatening activity, and report the seven requested figures of merit.
Requirements traceability
Requirement
Stages
Evidence
Wideband search with narrow receiver
1, 2, 5, 7
Band plan, receiver-IBW/span invariant, tuning/dwell state machine, adaptive policy
Truth per band and time slot
1
Deterministic occupancy, power and event records
Receiver hits and misses
2
Seeded Pfa-controlled energy detector and observation logs
Intercept-time prediction
3, 5
Scheduler-level forecast schema, completed-command hazard model and censored error metric
Interception-ratio prediction
3, 5
Horizon forecast with calibrated uncertainty
Periodic and frequency-agile emitters
1, 5
Exact simulator classes and observable pattern estimators
New/threatening emitter priority
1, 5, 6
Assessed/public features, novelty scores and evaluator-only weighted evidence
Seven required metrics
3, 6, 7
Frozen definitions, dashboard and final benchmark
Referenced data sources
1, 4, 7
TSRD adapter; optional properly licensed J.C. Wise-compatible importer
Reproducible comparative evidence
4, 5, 7
SQLite, MLflow, fixed splits, multi-seed baselines
Locked seven-stage architecture
Stage
Build boundary
Frozen output
1
RF environment + data adapters
GroundTruth, EventTable, scenario/data provenance
2
Receiver + detection
ObservationLog, DecisionLog, open-loop schedules
3
Metrics + forecast evaluation
MetricsReport, sensitivity curve, event matching
4
Persistence + MLflow
Queryable runs, checksummed artifacts, tracking links
5
Prediction + smart scheduler
Completed-command hazard predictor, contextual bandit, PPO policy, registered bundle
6
Interactive dashboard
Offline run/replay/compare/registry interface
7
Integration + benchmark hardening
One-command demo and held-out evidence pack
Locked technology choices
Layer
Choice
Runtime
Python 3.11; src-layout package; pyproject.toml plus uv.lock; platform-neutral paths
Science/data
NumPy, SciPy, pandas, h5py, PyYAML, Pydantic
Detection
Seeded Pfa-controlled noncoherent energy detector using scipy.stats gamma/ncx2
Persistence
SQLite application DB, SQLAlchemy 2.x, Alembic, checksummed NPZ/HDF5 artifacts
ML/RL
PyTorch predictor, Gymnasium, Contextual Thompson Sampling, Stable-Baselines3 PPO
Experiments
Local MLflow server with SQLite backend and local artifact store
UI
Streamlit + Plotly; offline-first; no cloud service required
Quality
pytest, pytest-cov, Ruff, mypy; deterministic smoke and integration profiles
Target repository layout
smart-scan-ew/├── pyproject.toml├── uv.lock├── README.md├── .env.example├── configs/│   ├── demo.yaml│   ├── receiver.yaml│   ├── train_smoke.yaml│   ├── train_full.yaml│   └── benchmark_final.yaml├── data/{raw,processed}/              # ignored except tiny fixtures├── artifacts/{runs,models,mlflow}/    # ignored except demo manifest├── docs/{SIH26055_BUILD_SPEC.md,BUILD_CONTRACT.md,DATA_SOURCES.md,stages/,stage_reports/}├── src/smartscan/│   ├── config.py  types.py  seeding.py  cli.py│   ├── rf/{bands.py,emitters.py,environment.py,events.py,io.py}│   ├── data/{provenance.py,turing.py,wise.py}│   ├── receiver/{detector.py,scanner.py,schedules.py,logs.py}│   ├── metrics/{engine.py,sensitivity.py,schemas.py,statistics.py}│   ├── storage/{models.py,repositories.py,artifacts.py,migrations.py,tracking.py}│   ├── ml/{features.py,predictor.py,periodicity.py,novelty.py,env.py,train.py,evaluate.py,bundle.py}│   └── dashboard/{app.py,pages.py,plots.py,services.py}├── tests/{unit,integration,fixtures}/└── scripts/{doctor.py,make_demo_data.py}
Frozen data contracts
These contracts are created in Stage 1 and may only be extended compatibly. Later stages must import them; they must not create competing versions.
Contract
Required fields/meaning
BandPlan
band_edges_hz[K+1], band_names[K], profile_id, scan_span_hz; half-open intervals [low, high)
GroundTruth
dt_s, n_steps, BandPlan, occupied[N,K], signal_power_w[N,K], EventTable, provenance, content_fingerprint, artifact_sha256
EventTable
event_id, emitter_id, band, start_step inclusive, end_step exclusive, source, optional evaluator-only synthetic threat weight
ReceiverConfig
receiver_ibw_hz, scan_span_hz, tune_latency_steps, dwell_bins, noise mode; scan_span_hz/receiver_ibw_hz >= 10; one receiver channel in v1
ScanCommand
decision_id, target_band, dwell_steps; dwell is usable integration time after tuning
ObservationLog
per-step physical state, tuned band, SNR, threshold, detection; no policy-visible oracle labels
DecisionLog
one row per completed command with pre-action p_hit, p_active, scheduler-level intercept-time forecast, action, observable hit/miss, costs and timestamps
MetricsReport
seven official metrics, interception ratio, delay/censoring statistics, per-band and uncertainty outputs
RunIdentity
UUID domain_run_id plus config hash, semantic content fingerprints, artifact SHA-256, seeds, git SHA and optional mlflow_run_id
Frozen metric definitions
Required figure
Exact project definition
Pd
Operational Pd = TP occupied completed dwells / all occupied completed dwells; stratify by dwell, SNR and occupied fraction. Controlled sweeps isolate the detector.
Pfa
False-alarm detections in noise-only completed dwells / all noise-only completed dwells.
Sensitivity
SNR dB where controlled Pd reaches the configured target, default 0.90; also receiver-input dBm when physical-noise mode is configured.
Average intercept rate
Distinct band-occupancy events first detected on the correct band / simulated seconds.
Average reward/cost
Mean realized observable reward per decision; also report each uncombined component.
Correct predictions
100 x correct pre-action p_active forecasts / scored decisions versus post-run dwell occupancy truth; keep p_hit calibration separate.
Average intercept-time error
MAE between pre-action time-to-next-completed-hit and the first future completed hit inside the declared horizon; report censoring and coverage.
Required supporting outputs: event interception ratio = captured band-occupancy events / all band-occupancy events; mean/median first-detection delay from event start; censored/penalized all-event delay; missed-event count; wasted-dwell fraction; tuning fraction; threat-weighted capture; hit-forecast Brier/ECE for p_hit versus observable hit/miss; and activity-forecast Brier/ECE for p_active versus post-run occupancy truth.
No survivorship bias: Successful-event delay and forecast MAE must show their denominator and coverage. Missed or unvisited opportunities are never silently discarded; report them as censored and include an all-event penalized/RMST-style statistic.
Intercept-time target: At each decision start, predict elapsed seconds to the end of the first future completed command that returns hit=true under the proposed scheduler. Stage 2 emits only one decision per completed dwell, so this is a scheduler-level target, not a sub-dwell timestamp. Right-censor at the declared forecast or episode horizon and always report coverage.
MLflow integration contract
MLflow is mandatory from Stage 4 onward and is linked to the application database, not mixed into the same schema.
Use data/smartscan.db for domain records and data/mlflow.db for MLflow metadata. Use artifacts/mlflow/ for MLflow artifacts. Both paths are configurable.
Run the local UI/API on 127.0.0.1:5000 by default with a database-backed store so Model Registry features work.
Store mlflow_run_id, experiment_id, registered model name/version/alias and sync_status on the domain run/training records. Tag MLflow runs with domain_run_id.
Log config, hyperparameters, seeds, dataset and ground-truth fingerprints, git SHA, environment lock, all metrics, curves, comparison tables and the complete model bundle.
Register SmartScanScheduler versions. Set candidate on every valid trained bundle; move champion only after the frozen held-out acceptance gate passes.
Provide a reconciliation command that finds one-sided records after an interrupted write. Tests use temporary SQLite files and temporary artifact roots.
Never commit tokens or credentials. Dataset access uses environment variables and tests never require a network connection.
Global Execution Contract - include with every stage
BEGIN GLOBAL EXECUTION CONTRACT
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
Keep large arrays and model files out of SQLite; store relative artifact paths plus SHA-256 checksums. Never load pickle, joblib, or Stable-Baselines3 bundles from untrusted paths. Load only locally generated, checksum-verified bundles from configured model roots, and use weights-only formats where supported.
Update docs/BUILD_CONTRACT.md only for compatible clarifications. Record any unavoidable interface change and migrate all callers/tests in the same stage.
At the end, write docs/stage_reports/STAGE_N_REPORT.md, state implementation_complete and any performance_gate_passed as separate booleans, and stop. Do not begin the next stage without a new user instruction.
END GLOBAL EXECUTION CONTRACT
STAGE 1 - RF Environment Simulator and Public-Data Adapters
BEGIN STAGE 1 PROMPT - COPY FROM HERE
You are the senior scientific Python engineer responsible for Stage 1 of SIH26055. Build a deterministic RF environment with perfect evaluation truth, frozen shared contracts and safe adapters for the referenced public radar data.
Scope: Create the repository foundation, band/time mathematics, four emitter classes, scenario I/O, event extraction, reproducible ground-truth artifacts, Turing TSRD ingestion and a J.C. Wise-compatible local catalog importer.
Do not build: Do not build the scanning receiver, detector, metrics engine, database, MLflow server, predictor, RL policy or dashboard.
Required work order
Inspect the repository. If it is empty, create the locked src layout, pyproject.toml, a reproducible Python 3.11 uv.lock, core/dev dependency groups, README skeleton, .gitignore and configs directory. Update the lock only with intentional dependency changes.
Materialize this specification as authoritative Markdown at docs/SIH26055_BUILD_SPEC.md, keep one executable prompt per file under docs/stages/, and write docs/BUILD_CONTRACT.md from the frozen architecture, data contracts and metric names. These files become the machine-readable handoff for later stages.
Implement and test time/band primitives before emitters. Implement emitters before scenarios. Implement deterministic save/reload before external-data adapters.
Run the unit and integration gates, create docs/stage_reports/STAGE_1_REPORT.md, then stop.
Mathematical and simulation contract
Time is integer indexed. Require T/dt to be an integer within a strict tolerance; otherwise reject the config. Set N = round(T/dt), t[n] = n*dt for reporting only, and use n % period_steps for all periodic behavior.
A band occupies [edge[k], edge[k+1]). Validate finite strictly increasing edges and use searchsorted with an explicit high-edge exclusion rule.
Ship two named profiles: demo_2_18 with sixteen 1 GHz bands from 2 to 18 GHz, and turing_0_18 with eighteen 1 GHz bands from 0 to 18 GHz. Every model/run stores its profile ID and exact edges.
Implement exactly four public emitter classes: ContinuousEmitter, CircularScanEmitter, SectorScanEmitter and FrequencyAgileEmitter. A reusable on/off gate may be composed into any class, but it is not a fifth public emitter type.
CircularScanEmitter: phase_step[n] = (phase0_steps + n) mod period_steps after mapping the receiver direction and beamwidth to integer phase bins. Its one-period sampled duty fraction must match the exact illuminated-step count within one sample.
SectorScanEmitter: implement a deterministic triangular sweep over [theta_min, theta_max], including endpoint behavior. Test both directions and wrap-free angular distance.
FrequencyAgileEmitter: active hop = hop_bands[(phase_offset + n // dwell_steps) mod L]. Validate positive dwell_steps, nonempty sequence and legal bands.
Overlapping emitters combine with logical OR for occupancy and linear addition for power. Never sum dB values. Keep emitter-level truth in an event table rather than Python objects inside an N x K array.
Extract maximal emitter-band illumination intervals as half-open [start_step, end_step). A hop or inactive gap closes an event; adjacent active samples from the same emitter and band remain one event.
Required GroundTruth artifact
occupied: bool array [N,K].
signal_power_w: float32 array [N,K] with finite nonnegative linear power.
events: tabular records with stable event_id, emitter_id, band, start_step, end_step, source and optional evaluator-only synthetic threat_weight/hidden metadata; these fields are never policy-visible.
scenario_config, BandPlan, dt_s, seed, generator version, source provenance, canonical content_fingerprint and artifact_sha256. The content fingerprint hashes semantic inputs; artifact SHA-256 hashes stored bytes.
Use compressed NPZ or HDF5 with an explicit schema_version. Reload must reproduce arrays bit-for-bit and the canonical event table exactly.
Reject NaN/Inf, negative power, invalid band references, zero/negative step counts, and conflicting emitter IDs with actionable validation messages.
Built-in scenarios
sparse: continuous plus circular-scan activity with low overlap.
dense: all four emitter types with simultaneous overlap and mixed SNR-relevant power.
agile_threat: periodic scanning, multi-band hopping, a late-arriving previously unseen emitter and differentiated evaluator-only synthetic threat weights for post-run analysis. Missing weights default to neutral 1.0 and no evaluator-only weight is policy-visible.
edge_zero: no emitters; used throughout receiver and metric tests.
A seeded random generator with bounded, validated distributions and no global RNG state.
Turing Synthetic Radar Dataset adapter
Implement smartscan.data.turing as an optional, streaming adapter. The dataset is large and gated; the project must remain fully testable without downloading it.
Accept a user-provided TSRD .h5 pulse-train path. Prefer the official turing_deinterleaving_challenge.PulseTrain.load API; do not guess or hard-code undocumented HDF5 internals.
Map PDW Time of Arrival (microseconds) to step indices and Centre Frequency (MHz) to BandPlan bins. Convert Amplitude dB according to verified dataset metadata, documenting whether it is 20log10 amplitude or 10log10 power. When filling signal_power_w, accumulate pulse energy as linear_power times pulse/bin overlap and divide by dt_s; use Pulse Width across bin boundaries. Quarantine and report ambiguous-unit records; preserve AoA and metadata in provenance/side tables.
TSRD emitter labels are local to each pulse train; namespace them with the pulse-train fingerprint so label 1 in two files is never treated as the same emitter.
Record source URI, receiver mode, original file SHA-256, dataset/repository version when known, transformation config, dropped/out-of-range/ambiguous counts and output content fingerprint. Default to stare mode for GroundTruth. Treat scan mode as receiver observations or an external baseline unless paired with corresponding stare truth; never interpret scan-mode non-detections as non-transmissions.
Support both BandPlan profiles. For demo_2_18, explicitly filter 0-2 GHz pulses and report coverage loss; never silently reinterpret the 0-18 GHz source.
Provide an integration command that operates on one local file and a unit-test fixture containing a few synthetic PDWs. No unit test may require HF_TOKEN, a Hugging Face login, network access or the 70 GB corpus.
Document that TSRD models emitted electromagnetic-environment truth rather than this project's narrowband receiver. Stage 2 must still apply the project receiver/detector to the converted truth.
J.C. Wise-compatible catalog adapter
Treat the legacy Radar Emitter Database reference as an optional user-supplied local CSV/JSON source because availability and redistribution rights may vary. Do not scrape a website and do not fabricate a catalog.
Define and document a stable input schema: source_record_id, emitter_family, frequency_min_hz, frequency_max_hz, optional PRI/PRF, pulse_width, scan_type, scan_period_s, optional public threat_priority, source_reference and license_note.
Validate units/ranges, preserve each raw record's provenance and map only legally supplied records into scenario templates or observable catalog features. Unknown fields remain unknown; do not fill with invented values.
Ship only a tiny clearly synthetic schema example under tests/fixtures, not real database content.
CLI and documentation deliverables
python -m smartscan.cli simulate --config configs/demo.yaml --output artifacts/runs/stage1_demo.npzpython -m smartscan.cli inspect-ground-truth artifacts/runs/stage1_demo.npzpython -m smartscan.cli import-turing --input /path/train.h5 --band-plan demo_2_18 --output data/processed/sample.npzpython -m smartscan.cli validate-wise --input /path/catalog.csv
README Stage 1 section with equations, units, schemas, commands, public-data limitations and exact replay instructions.
docs/DATA_SOURCES.md with TSRD access/provenance notes and the optional J.C. Wise-compatible schema.
No generated large data in git. Keep only tiny deterministic fixtures and their expected checksums.
Tests and acceptance gate
T/dt validation and half-open band-edge behavior, including exactly 18 GHz being out of range.
Continuous duty cycle, circular sampled duty count, sector endpoints/direction, agile hop at every boundary and on/off gating.
Overlapping occupancy/power and separate emitter events.
Same semantic seed/config produces an identical content_fingerprint even if compression bytes differ; save/reload preserves arrays and canonical events bit-for-bit; artifact_sha256 verifies exact stored bytes; a different seed changes semantic truth and its content fingerprint.
All four built-in scenarios validate, including zero emitters and a late new emitter.
Tiny TSRD fixture converts with correct units, pulse-width energy aggregation, namespaced labels and reported clipping/ambiguity; stare-truth and scan-observation handling are tested; Wise schema validates and rejects bad units/ranges.
Ruff, mypy and Stage 1 pytest suite pass with at least 90% line coverage for smartscan.rf and smartscan.data.
The demo command exits 0, prints per-band activity/event counts and creates a reloadable artifact with a checksum.
Stage 1 is complete only when: The deterministic simulator, four emitter classes, frozen contracts, both band profiles, replayable artifacts and both safe data-adapter paths exist and every listed test passes.
Required completion report
Create docs/stage_reports/STAGE_1_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 1. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 1 PROMPT - STOP COPYING
STAGE 2 - Scanning Receiver and Statistically Consistent Detection
BEGIN STAGE 2 PROMPT - COPY FROM HERE
You are the senior receiver-modeling engineer for Stage 2. Extend the Stage 1 package with a narrowband scanning receiver whose tuning cost, dwell integration, seeded noise and hit/miss decisions are mathematically explicit and reproducible.
Scope: Build the ScanCommand state machine, Pfa-controlled noncoherent energy detector, receiver/decision logs and sequential, uniform-random and fixed-priority open-loop schedules.
Do not build: Do not build metric aggregation, persistence, MLflow, the learned predictor, RL training or dashboard. Do not alter Stage 1 truth to make detection easier.
Prerequisite check
Run Stage 1 tests and load the demo artifact before editing. If a critical Stage 1 interface bug blocks work, make the smallest compatible fix, add a regression test and record it in the Stage 2 report.
Receiver state machine
ReceiverConfig must include receiver_ibw_hz and scan_span_hz, require scan_span_hz/receiver_ibw_hz >= 10, and require receiver_ibw_hz no wider than the selected band. Version 1 models one tunable receiver channel; retain receiver_id/channel fields as an extension point, but do not claim coordinated multi-receiver scheduling.
At a decision boundary accept ScanCommand(target_band, dwell_steps). The action is always the pair band plus dwell; do not leave dwell implicit for later stages.
Changing bands enters TUNING for tune_latency_steps, during which tuned_band is null, integrated energy is zero and detection is impossible. Commanding the current band may use zero retune cost only if the receiver is already settled.
After tuning, enter DWELLING for exactly dwell_steps usable integration steps. Emit one hit/miss decision at dwell completion; per-step logs remain available for replay. The observable intercept timestamp is that completed decision's end_step, so later stages must not infer a sub-dwell hit time from this log.
Define latency and dwell in integer steps. Default dt is 1 ms and default tune latency is exactly one step (1 ms). Reject a requested physical latency that is not an integer multiple of dt instead of silently rounding it.
Allow dwell bins configured in steps with positive min/max validation. The Stage 5 default will be [1, 2, 4, 8, 16].
Use a local numpy.random.Generator created from the receiver seed. Given truth, commands and seed, logs must be identical.
Energy, noise and Pfa-control contract
Use a Pfa-controlled noncoherent energy detector with M equivalent independent complex samples per completed dwell. Keep all internal probability calculations in linear units; convert to dB only at boundaries and reports. Do not call it CFAR unless noise reference cells or adaptive background estimation are actually implemented.
rho[n]     = signal_power_w[n, band] / noise_power_wM          = samples_per_step * dwell_stepsrho_eff    = mean(rho over the usable dwell)Under H0:  Z ~ Gamma(shape=M, scale=1)threshold  = GammaPPF(1 - pfa_design; shape=M, scale=1)Under H1:  2Z ~ NoncentralChiSquare(df=2M, nc=2M*rho_eff)Pd(rho)    = SF_NCX2(2*threshold; df=2M, nc=2M*rho)detection  = (Z >= threshold)
Sample Z with the seeded RNG using gamma for H0 and 0.5 times noncentral-chi-square for H1. This makes designed Pfa and analytic Pd testable.
For time-varying/partial activity, noncentrality is 2 * samples_per_step * sum(rho[n]) over usable dwell steps. Do not label an entire dwell strong because one sample was active.
Support a normalized noise-power mode for fast tests and an optional physical mode noise_power = k*T0*receiver_ibw_hz*noise_factor. Store receiver_ibw_hz, temperature and noise figure when physical mode is used.
Measured SNR is a noisy estimate derived from normalized energy and clearly labeled as an estimate. Truth SNR may appear only in the evaluator/debug record, never policy-visible observations.
Multiple simultaneous emitters already arrive as Stage 1 linear power. The receiver does not inspect true emitter IDs when deciding a hit.
Set default pfa_design to a configurable value such as 1e-3. Do not tune thresholds on held-out benchmark truth.
Logs and interfaces
ObservationLog per step: step, receiver_state, commanded_band, tuned_band, decision_id, dwell_progress, integrated_energy, measured_snr_db and detection flag. Oracle fields must live in a separate evaluation join, not this policy-visible structure.
DecisionLog per completed command: start/tune/dwell/end steps, target band, dwell length, measured summary, hit/miss, receiver seed, and nullable pre-action p_hit, p_active, time_to_next_completed_intercept_s, forecast_horizon_s, uncertainty and model version fields for Stage 5.
Every log carries GroundTruth fingerprint, receiver-config hash and a schema version. Validate monotonic steps and one terminal decision per command.
Schedules implement one protocol and produce ScanCommand objects: SequentialSchedule, UniformRandomSchedule and FixedPrioritySchedule. Fixed priority uses only its supplied public list, never truth activity.
Expose a runner that applies any schedule to GroundTruth and returns both logs without importing later stages.
CLI and example
python -m smartscan.cli receive --truth artifacts/runs/stage1_demo.npz --strategy sequential --seed 42 --output artifacts/runs/stage2_seq.npzpython -m smartscan.cli receive --truth artifacts/runs/stage1_demo.npz --strategy random --seed 42 --output artifacts/runs/stage2_random.npz
Print completed dwells, hits, misses, false alarms under the evaluator join, tuning fraction and average measured SNR. These are diagnostic counts, not the final Stage 3 figures of merit.
Tests and acceptance gate
Exact state-transition and off-by-one tests for same-band dwell, cross-band tuning, final simulation boundary and invalid commands; ReceiverConfig rejects scan_span_hz/receiver_ibw_hz below 10 and receiver_ibw_hz wider than a target band.
No integration/detection during tuning and exactly one decision at the end of each complete dwell; every hit timestamp equals that decision's end_step.
Analytic threshold and Pd curve checks against scipy.stats for several M and SNR values.
Noise-only Monte Carlo Pfa estimate contains pfa_design within a predeclared 95% binomial confidence/tolerance rule; strong-signal Pd approaches the analytic value. Use enough trials and a deterministic seed, not an exact-count assertion.
Partial-dwell power yields the expected noncentrality; overlapping power is handled in linear units; dB round trips are accurate.
Same truth, schedule and seed reproduce identical logs. Changing only receiver seed changes stochastic detections but not commanded bands.
Sequential, random and fixed-priority schedules cover their documented behavior and never read GroundTruth occupancy when choosing commands.
Stage 1 and Stage 2 tests, Ruff and mypy pass; smartscan.receiver has at least 90% line coverage.
Stage 2 is complete only when: A user can load Stage 1 truth, run a band-plus-dwell schedule through an exact tuning/dwell state machine, obtain seeded statistically valid hits/misses and replay the same logs.
Required completion report
Create docs/stage_reports/STAGE_2_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 2. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 2 PROMPT - STOP COPYING
STAGE 3 - Metrics Engine and Forecast-Evaluation Contracts
BEGIN STAGE 3 PROMPT - COPY FROM HERE
You are the performance-analysis engineer for Stage 3. Build one authoritative metrics engine that separates detector quality, scheduler coverage and predictor accuracy, while computing every figure requested by SIH26055 with explicit denominators and censoring.
Scope: Build event matching, the seven frozen figures of merit, interception-ratio/delay support statistics, controlled sensitivity sweeps, confidence summaries and stable JSON/CSV schemas.
Do not build: Do not build a database, MLflow, predictor, RL policy or dashboard. Forecast-dependent metrics must return a typed not-available result until Stage 5 supplies valid pre-action forecasts; never substitute zero.
Input and interval rules
Accept only Stage 1 GroundTruth plus Stage 2 ObservationLog/DecisionLog with matching fingerprints, dt, band plan and schema versions. Reject mismatches before calculation.
Derive BandOccupancyEvents as maximal contiguous intervals where occupied[:,band] is true. These are the official capture units because one energy-detection decision cannot identify multiple simultaneous emitters in the same band.
Keep Stage 1 emitter-level events for diagnostics and threat analysis, but never count one binary detection as successful identification of every overlapping emitter.
All intervals are half-open [start_step,end_step). A completed decision's usable integration interval excludes tuning and includes only its dwell steps; its detection timestamp is decision end. For forecast scoring, actual time_to_next_completed_intercept_s is elapsed time from forecast decision start to the end of the first future completed command with hit=true; right-censor at the declared forecast or episode horizon.
Match detections and BandOccupancyEvents one-to-one within each band, ordered by detection time then event start. A detection must overlap the event's active interval through its usable dwell; one detection may not capture multiple disjoint events.
False alarms are completed decisions with detection=true and no truth occupancy anywhere in the usable dwell. Incomplete end-of-run dwells are excluded and reported.
Implement the seven required figures exactly
Return a versioned MetricsReport with numerator, denominator, value and unit for every metric.
Operational Pd: true-positive occupied completed decisions divided by all occupied completed decisions. A true positive is a detection whose usable dwell overlaps occupancy. Stratify by dwell_steps, mean SNR and occupied-step fraction; the controlled sensitivity sweep, not this scheduler-conditioned rate, isolates detector behavior.
Pfa: false-alarm noise-only completed decisions divided by all noise-only completed decisions. Never mix per-step and per-dwell denominators.
Sensitivity: run the detector in a controlled single-band Monte Carlo SNR sweep using fixed M, pfa_design and seeds; enforce a monotone Pd estimate or analytic curve and interpolate the SNR dB at target Pd, default 0.90. Save the full curve and confidence intervals. In physical-noise mode also report equivalent receiver-input power in dBm using the configured IBW, temperature and noise figure.
Average intercept rate: number of matched BandOccupancyEvents divided by total simulated seconds.
Average reward/cost: mean of the realized observable per-decision reward passed in the DecisionLog. If no reward exists before Stage 5, compute a clearly named evaluation_score from normalized components but leave average_reward unavailable. Never hide components behind one scalar.
Percentage of correct predictions: 100*(TP+TN)/scored decisions using pre-action p_active, threshold default 0.5, versus the post-run truth label that the commanded band's usable dwell contained occupancy. Report precision/recall and activity Brier/ECE on p_active. Separately report hit Brier/ECE on p_hit versus observable hit/miss; never use p_hit as the activity forecast.
Average intercept-time error: MAE between pre-action time_to_next_completed_intercept_s and elapsed time to the first future completed hit under the executed schedule. Score only forecasts with an observed hit inside their declared horizon; treat the rest as right-censored and report forecast count, eligible count, coverage and a censored/RMST-style companion statistic.
Required support metrics
event_interception_ratio = matched BandOccupancyEvents / all BandOccupancyEvents. This is the realized interception ratio required for the Stage 5 horizon forecast target.
successful_event_delay_s: mean, median, p90 and standard deviation of detection_end - event_start for matched events.
missed_event_count and missed-event table with band, interval, duration and nearest receiver visit for debugging.
all_event_penalized_delay_s using a benchmark-configured finite horizon for misses, plus a Kaplan-Meier/restricted-mean time-to-capture estimate with censoring at event end. State the horizon and censoring rule in output.
per-band active fraction, dwell fraction, intercept ratio, separate p_hit and p_active calibration, revisit gap and missed count.
tuning fraction, wasted-dwell fraction, incomplete-decision count and throughput.
threat-weighted capture as an evaluator-only secondary metric. For each BandOccupancyEvent formed from overlapping emitter events, use the maximum available synthetic evaluator threat weight or documented public/assessed weight; default to neutral 1.0. Report sum(captured weights)/sum(all weights), and never expose evaluator-only weights to the policy.
bootstrap 95% confidence intervals and paired multi-seed comparison helpers. Resampling uses whole runs/seeds, never individual time steps as independent samples.
Schemas and behavior
Use dataclasses or Pydantic models with JSON-safe scalar values and explicit null plus reason for unavailable metrics.
Keep raw counts/events outside the summary dictionary but reference their relative artifact paths and checksums.
Round only for display. Persist full-precision values. Define behavior for zero denominators as unavailable, not NaN/Inf and not zero.
Include metric_schema_version, config hash, all input content fingerprints, artifact SHA-256 values and created_at in UTC. created_at and absolute paths are volatile metadata and are excluded from canonical content fingerprints.
Provide evaluate_strategy(...) and compare_runs(...) APIs usable unchanged by persistence, MLflow and dashboard stages.
CLI and golden examples
python -m smartscan.cli metrics --truth artifacts/runs/stage1_demo.npz --log artifacts/runs/stage2_seq.npz --output artifacts/runs/stage3_seq_metrics.jsonpython -m smartscan.cli sensitivity --receiver-config configs/receiver.yaml --target-pd 0.90 --output artifacts/runs/sensitivity.json
Tests and acceptance gate
Hand-authored small truth/log fixtures with exact expected event boundaries, one-to-one matches and all seven metric numerators/denominators.
One detection overlapping two disjoint events captures at most one; simultaneous emitter events merged into one band-occupancy interval are not double counted, and overlapping evaluator threat weights use the frozen maximum-weight aggregation rule.
Perfect detector/schedule, never-visits-active, all-noise, all-active, zero-event and incomplete-final-dwell cases.
Pfa uses only noise-only completed decisions; Pd uses only occupied completed decisions; results are unchanged by unrelated steps in other bands.
Sensitivity threshold agrees with Stage 2 analytic Pd within declared tolerance and changes monotonically with target Pd/Pfa settings; physical mode reports a consistent receiver-input dBm value.
Forecast metrics are unavailable with a reason when predictions are absent, score only pre-action forecasts when present, keep p_hit and p_active scoring separate, and show reduced coverage for right-censored intercept-time forecasts.
Missed events affect interception ratio and all-event delay; they cannot disappear from a successful-only mean.
JSON round-trip preserves schema and full-precision scalars; Stage 1-3 suites, Ruff and mypy pass; smartscan.metrics has at least 95% line coverage.
Stage 3 is complete only when: Every requested figure has one frozen formula, one denominator, edge-case behavior and a golden test; the engine clearly distinguishes Pd, event interception ratio, intercept delay and forecast error.
Required completion report
Create docs/stage_reports/STAGE_3_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 3. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 3 PROMPT - STOP COPYING
STAGE 4 - Queryable Persistence and Local MLflow Tracking
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
STAGE 5 - Observable Intercept Prediction and Smart ML Scheduler
BEGIN STAGE 5 PROMPT - COPY FROM HERE
You are the machine-learning and sequential-decision lead for Stage 5. Build a scheduler that predicts when and where a hit is likely, forecasts interception ratio, prioritizes new/threatening activity and chooses both band and dwell while learning only from receiver-visible outcomes.
Scope: Build the observable feature pipeline, censored completed-command hit-hazard predictor, periodic/agile/novelty estimators, horizon forecaster, Gymnasium environment, PPO scheduler, five non-oracle baselines, reproducible training/evaluation and MLflow model lineage.
Do not build: Do not build or redesign the dashboard. Do not expose GroundTruth occupancy, emitter IDs, hidden threat labels, future activity or post-run matches to the predictor, policy observation or reward. Do not call an oracle upper bound a deployable baseline.
Oracle-leakage firewall
Create an ObservableTransition type containing only command/action timing, receiver state, hit/miss, measured SNR, public/derived catalog features and history available at that decision time.
RewardCalculator, FeatureBuilder, HitHazardPredictor and policy receive ObservableTransition/history only. They may not accept GroundTruth, truth event tables or emitter configuration in their public signatures.
The physical Stage 2 receiver may read truth to synthesize measurements. The Stage 3 evaluator may join truth after the episode. Neither permission crosses the observable boundary.
Do not reward I_new_true_event or use a truth event ID. Reward detected hits, observable assessed priority and costs. Repeated-hit control must rely on observable recent-hit state, not oracle event continuity.
Add a leakage test that replaces truth/evaluator fields with objects that raise on access while replaying a fixed receiver-output stream; features, actions and rewards must remain identical.
Add a causality test: changing future log rows cannot change a prediction recorded at an earlier decision.
Training-data construction from hits and misses
Generate exploration logs with sequential, uniform-random, fixed-priority and reactive schedules over Stage 1 scenario families. Use Stage 2 stochastic detection and persist every run through Stage 4/MLflow.
Freeze train/validation/test scenario configurations and seed lists before model fitting. Split by complete scenario plus seed, never by individual rows, to prevent temporal and configuration leakage.
For each forecast origin, build features only from rows strictly before its action. The immediate chosen command's terminal hit/miss trains q_hit. For scheduler-level survival labels, use the actual future completed-command sequence: the first hit end_step is the event time; if none occurs before the declared horizon, right-censor there. Unvisited bands remain unknown/masked, never negative examples.
Balance scenario families and include late new emitters, spatial periodic scans, frequency hops, sparse/dense overlap, SNR variation and catalog-known/unknown cases.
Save dataset manifest, row counts, split IDs, feature schema, source run IDs, semantic content_fingerprint and artifact SHA-256. MLflow logs these identifiers, not raw secrets or the full large corpus.
Observable feature vector
Use fixed-size per-band features for the model's BandPlan plus global receiver features. Include missingness masks; zero is not a substitute for unobserved.
Per band: time since last visit, time since last hit, last hit/miss, EWMA hit rate, miss streak, hit count, measured-SNR EWMA, visit count, recent dwell allocation and uncertainty/missing masks.
PeriodicityEstimator outputs estimated period, phase-to-next-window and confidence from irregular hit timestamps while ignoring unobserved intervals. Use a weighted autocorrelation/interval method with deterministic fallbacks.
AgilityEstimator builds a smoothed transition matrix from temporally adjacent observed hit bands and outputs likely next-band scores. It never reads the true hop sequence.
NoveltyEstimator returns a bounded novelty score from unexpected band/timing/SNR and optional observed PDW summaries. Use rolling robust statistics or an explicitly fitted lightweight model; unknown is not automatically hostile.
ThreatAssessor combines an optional public catalog match with observable novelty. Default assessed threat is neutral 1.0. Hidden simulator threat labels are evaluator-only.
Global: current/last settled band, tuning cost to each candidate, elapsed episode fraction, last dwell, remaining decision horizon and model/band-plan masks.
Censored HitHazardPredictor
Implement a small PyTorch multi-head network that outputs calibrated immediate-command hit probability q_hit(b,d) plus a discrete first-future-completed-hit hazard h[j] over command completion bins for a proposed observable schedule, with uncertainty. Keep the model small enough for CPU training and live inference.
p_hit_within_dwell(b,d) = q_hit(b,d)h[j] = P(first future completed hit at command j | no earlier hit, proposed schedule)S[j] = product_i<=j (1 - h[i])E[t_next|hit] = sum_j completion_time_s[j] * h[j] * S[j-1] / max(1 - S[J], eps)
Use masked discrete-time survival negative log-likelihood over future completed commands: event-time loss at the first completed hit, right-censor survival loss when no hit occurs before the declared horizon, and no fabricated miss labels for unchosen/unobserved bands.
Calibrate q_hit as p_hit on validation hit/miss outcomes. Derive and separately calibrate p_active with Stage 2 Pd/Pfa information; never reuse one probability under both names. Do not use the held-out test split, and save both calibrators in the model bundle.
Expose forecast_next_intercept(observable_state, band, dwell, proposed_schedule, horizon) returning p_hit_within_dwell, p_active, time_to_next_completed_intercept_s, right_censor_horizon_s, uncertainty and model_version.
Under the documented detector-mixture approximation p_hit = p_active*Pd_operating + (1-p_active)*Pfa, derive p_active = clip((p_hit-Pfa)/max(Pd_operating-Pfa, eps), 0, 1) for the applicable dwell/SNR stratum. Mark it unavailable when Pd_operating <= Pfa or calibration is unsupported; calibrate it separately and keep it distinct from truth.
Provide a simple non-neural recency/EWMA predictor as a required forecast baseline, with separate hit-Brier, activity-Brier, time-error and ratio-forecast results.
Interception-ratio horizon forecast
Implement HorizonForecaster(observable_state, proposed policy/schedule, horizon_steps, seed) using q_hit, completed-command hazards and detector calibration, without GroundTruth.
Run deterministic Monte Carlo rollouts (configurable, default 128) to estimate expected distinct observable intercepts and latent activity opportunities over the horizon. Return predicted_interception_ratio clipped to [0,1], predicted intercept count, predicted opportunity count and 90% interval.
Record the forecast before the evaluated horizon begins. After the run, Stage 3 compares it with truth-based event_interception_ratio and reports absolute error/coverage. Never retroactively overwrite a forecast.
Also expose decision-level p_hit, p_active and expected time to the next completed hit so the scheduler and dashboard can explain each choice even when the run-level ratio forecast is uncertain.
Gymnasium environment and action
Wrap the existing Stage 2 receiver; do not reimplement RF or detection. reset(seed, scenario reference) returns the observable feature vector and records all component seeds.
Use Discrete(K*L), where L is the configured dwell-bin list and action decodes as band = action // L, dwell_bin = action % L. The saved bundle is tied to exact BandPlan and dwell bins and refuses incompatible input.
Observation space is a finite float32 Box with normalization statistics saved in the bundle. Validate no NaN/Inf and deterministic shape.
step(action) advances through tuning plus the full dwell, returns the next observable state and one reward, and appends both per-step and per-decision logs.
info may contain evaluator handles after episode end, but policy callbacks/replay buffers must strip truth fields. Name evaluator-only keys with an explicit oracle_ prefix and test they never enter observations/rewards.
Observable reward and priority
priority = assessed_threat * p_hit + lambda_novelty*novelty + lambda_uncertainty*uncertaintyreward   = w_hit*I(hit) + w_priority*I(hit)*priority           - c_tune*tuning_seconds - c_time*command_seconds           - c_repeat*I(recent_same_band_no_hit) - c_false_like*I(low_confidence_hit)
All terms are computable from the current action and receiver output. Log each component separately and normalize coefficients in config so seconds and unitless terms are not mixed silently.
A novelty/uncertainty bonus must be bounded to prevent endless exploration. Unknown threat gets neutral assessed_threat; it does not receive hidden hostile status.
Do not directly optimize Stage 3 truth metrics inside step(). Use them only in periodic validation/evaluation outside the replay buffer.
Include ablations for predictor features and priority terms so any claimed improvement can be traced to observable mechanisms.
Policies and baselines
Train PPO from Stable-Baselines3 with fully seeded Python/NumPy/PyTorch/Gymnasium behavior, saved normalization and deterministic evaluation mode.
Required non-oracle baselines on identical band/dwell contracts: Sequential fixed dwell, Uniform Random, Fixed Priority using only supplied public priorities, Reactive hit-recency with configurable exploration, and Contextual Thompson Sampling using the same observable features and updates only from completed hit/miss outcomes. The contextual bandit is the strong learned fallback; PPO is compared with the best non-oracle baseline.
Optional Oracle Ceiling may read truth only in the evaluator, is labeled unattainable, is excluded from the win comparison and is never stored as a deployable model.
All policies produce the same ObservationLog/DecisionLog and are persisted through Stage 4 with identical scenario and receiver seeds for paired comparisons.
Training profiles and MLflow lineage
configs/train_smoke.yaml: tiny deterministic CPU run that completes quickly, proves the loop and is not used for performance claims.
configs/train_full.yaml: documented timestep budget, parallel environments if safe, evaluation cadence, early stopping, hyperparameters and fixed validation seeds.
Log predictor, contextual-bandit and PPO runs to separate MLflow experiments with parent/child linkage. Log params, reward components, learning curves, full Stage 3 metrics, seed-level rows, split/data fingerprints, git SHA, package lock, model signatures and artifacts.
Create one versioned model bundle containing predictor, separate hit/activity calibrators, periodic/agile/novelty state, contextual-bandit state, PPO checkpoint, normalization, BandPlan, receiver IBW, dwell bins, feature schema, config and checksums. Prefer PyTorch state_dict/weights-only storage; load the SB3 checkpoint only from a locally generated checksum-verified bundle, never an arbitrary upload.
Log the bundle through an MLflow model interface (a tested pyfunc wrapper or equivalent) and register it as SmartScanScheduler. Set alias candidate after structural validation. Set champion only after the final held-out gate below passes.
Store registered model name, version, aliases and source mlflow_run_id in the Stage 4 model_versions table. The same bundle loaded from MLflow or its local path must produce identical actions for a fixed input/seed.
Evaluation design - no cherry-picking
Before full training, write configs/benchmark_final.yaml and a hashed held_out_manifest.json containing at least 30 paired seeds across sparse, dense, agile_threat, unseen parameter combinations and one TSRD-derived local sample when legally available.
Do not tune on the final manifest. Hyperparameter/model selection uses validation scenarios only. Run every strategy on identical truth and receiver-noise seeds.
Report every seed, mean/median, 95% paired bootstrap confidence interval and failure case. Primary metrics are average intercept rate, event interception ratio and all-event/ successful-event delay; Pfa is a guardrail.
Compare PPO with every baseline, explicitly including Contextual Thompson Sampling, and with the best non-oracle result rather than only sequential/random. Keep the oracle ceiling visually and numerically separate.
CLI deliverables
python -m smartscan.cli collect --config configs/train_smoke.yamlpython -m smartscan.cli train-predictor --config configs/train_smoke.yaml --trackpython -m smartscan.cli train-contextual-bandit --config configs/train_smoke.yaml --trackpython -m smartscan.cli train-scheduler --config configs/train_smoke.yaml --trackpython -m smartscan.cli evaluate --config configs/benchmark_final.yaml --model models:/SmartScanScheduler@candidate --seeds 30 --trackpython -m smartscan.cli models promote --name SmartScanScheduler --version <version> --require-gate
Tests and acceptance gate
Gymnasium env_checker passes; action decode, observation bounds, episode truncation and deterministic replay are tested.
Oracle-firewall and future-causality tests pass; unvisited bands are masked/censored rather than labeled misses.
Survival-loss golden cases for hit at each bin, right-censored miss, missing band and numerical stability; forecast probabilities are finite and monotonic with dwell horizon.
Synthetic periodic hit stream recovers period/phase within declared tolerance; agile transition and novelty tests use only observable sequences.
Horizon forecast is deterministic for a seed, bounded, recorded before evaluation and outperforms the naive forecast on held-out ratio MAE or calibration. The scheduler-level time-to-next-completed-hit predictor beats the naive recency baseline on held-out MAE with stated horizon and coverage.
All five non-oracle baselines and PPO generate compatible persisted logs/metrics. Model-bundle and MLflow-registry round trips reproduce fixed actions/forecasts.
Final held-out benchmark: versus sequential and random, PPO improves mean average-intercept-rate by at least 5% relative and reduces successful-event median delay by at least 10%. Versus the best non-oracle baseline, at least one primary paired delta has a 95% CI excluding zero while other primary metrics are non-inferior within 2% relative. For delta_Pfa = Pfa_PPO - Pfa_best, the predeclared one-sided 95% Newcombe/binomial upper confidence bound must be <= max(0.001 absolute, 0.20*pfa_design); report counts and the interval.
The improvement must hold in at least two scenario families, including agile_threat, and use all predeclared seeds. If it fails, set performance_gate_passed=false, do not promote champion and make no superiority claim. Stage 5 may still set implementation_complete=true only if all engineering, test, oracle-firewall and evaluation deliverables pass; the structurally valid model remains candidate.
Stage 1-5 suites, Ruff and mypy pass. Critical observable/reward/predictor logic has at least 90% line coverage.
Stage 5 status: Set implementation_complete=true only when explicit forecasts, observable band-plus-dwell scheduling, reproducible lineage, tests and the oracle firewall pass. Record performance_gate_passed separately. A failed performance gate leaves the model candidate and champion absent, but does not erase completed engineering work.
Required completion report
Create docs/stage_reports/STAGE_5_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 5. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 5 PROMPT - STOP COPYING
STAGE 6 - Offline Interactive Dashboard
BEGIN STAGE 6 PROMPT - COPY FROM HERE
You are the senior Streamlit and scientific-visualization engineer for Stage 6. Build a stable laptop-friendly interface that lets judges run/replay identical scenarios, understand each scan decision and compare the learned scheduler with all non-oracle baselines using the frozen metrics.
Scope: Build a thin Streamlit/Plotly application over Stage 1-5 services, with scenario execution, replay, forecast/priority explanations, exact metric comparison, run history and MLflow model lineage.
Do not build: Do not reimplement simulator, detector, metrics, database, predictor or policy logic inside UI files. Do not retrain a model from the dashboard. Do not expose truth as if it were available to the live policy.
Application structure
Keep dashboard code thin: services call existing CLI/domain APIs; plots accept typed results. Cache immutable ground truth/model loads by fingerprint and never cache mutable DB sessions.
Provide one command: python -m smartscan.cli dashboard. Default to 127.0.0.1 and an offline demo profile.
Use a professional neutral/dark theme, color-blind-safe palette, readable 14-inch laptop layout, consistent units and no military imagery or decorative clutter.
Every long action has progress/status, cancel-safe behavior where possible and a clear error with next action. Missing MLflow server/model/data must not crash the app.
Required views
View
Required behavior
1. Configure & Run
Scenario/source, band plan, dt/duration, receiver IBW/settings, strategy/model, seed; validate then persist/track one run.
2. Scan Replay
Band-time occupancy evaluation overlay, receiver tuned band, tuning gaps, hit/miss markers, SNR and pause/step/speed controls.
3. Smart Decision
Chosen band+dwell, separate p_hit/p_active, time to next completed hit, horizon interception-ratio interval, periodic/agile cues, novelty/threat/uncertainty and reward components.
4. Metrics Compare
All seven frozen figures plus interception ratio/delay, denominators, confidence intervals and paired baseline deltas.
5. Run History
Filter/query Stage 4 runs, verify artifact status, load replay and select identical-seed comparisons.
6. Model & Data Lineage
MLflow run, registered version/alias, source/data fingerprints, git SHA, config and link/open-local-UI action.
Truth and observability presentation
Default live view shows only receiver-observable data. A separate toggle labeled Evaluation overlay may reveal Stage 1 truth after a run/replay; display a persistent 'not available to policy' label.
Never use the overlay state to influence action generation, prediction or run persistence. Add a test that the same seed/model actions are identical with the overlay on or off.
Show predictions at the timestamp they were made, not recomputed with future history. Make uncertainty and unavailable/low-coverage states visible.
Explain threat as assessed/public priority and novelty; never label an emitter hostile from hidden simulator truth in the live view.
Metric visualization rules
Use a numerical comparison table as the primary evidence. Include numerator/denominator or coverage in tooltips/details. Do not use a radar chart as the only comparison because units differ.
Use bars/dot plots for comparable normalized metrics, line/interval plots for sensitivity/calibration and paired-delta plots for multi-seed evidence. Label higher-is-better or lower-is-better explicitly.
Never truncate axes to exaggerate small deltas. Show all selected strategies, the seed count and 95% CI. Keep the oracle ceiling separate and clearly unattainable if shown.
Unavailable metrics display 'Not available' plus reason. Do not render NaN, zero or a green win badge for missing data.
Highlight a scheduler win only when the Stage 5 record has performance_gate_passed=true; otherwise display candidate status and failed criteria honestly.
Required user flow
Load the precomputed agile_threat demonstration bundle and its matched sequential, random, fixed-priority, reactive, contextual-Thompson and champion/candidate runs.
Replay sequential and learned decisions over identical truth/receiver seeds.
Inspect a learned band+dwell choice with separate p_hit and p_active, expected time to the next completed hit, priority and uncertainty.
Open Metrics Compare and see all seven figures plus event interception ratio/delay and paired evidence.
Open Model & Data Lineage and verify the MLflow/domain run linkage and model alias.
Exports and safeguards
Export selected MetricsReport/comparison as JSON and CSV with schema version, run IDs and fingerprints. Do not export large truth arrays through the browser by default.
Escape/validate user paths and YAML; restrict file selection to configured data/artifact roots. Never display environment secrets or HF tokens.
Cap live duration/band count using demo-config limits and offer recorded replay for larger runs.
Provide a data/model status panel and a 'doctor' action that checks DB migrations, artifact checksums, MLflow reachability and champion/candidate availability.
Tests and acceptance gate
Service-layer unit tests prove the dashboard calls Stage 1-5 APIs and never duplicates metric/detector formulas.
Streamlit AppTest smoke tests cover default launch, demo load, run validation, compare table, history filters, missing model, unavailable MLflow and corrupt artifact states.
Overlay on/off yields identical actions/rewards; unavailable metrics and failed gates are represented honestly.
Plot tests confirm every required metric, unit, denominator/coverage metadata, selected strategies and CI fields are passed through.
A fresh local app launches with no network, loads the precomputed demo and completes the required user flow without a Python traceback.
Stage 1-6 suites, Ruff and mypy pass. Dashboard critical path fits a common 1366x768 viewport without horizontal scrolling or clipped controls in the rendered browser test.
Stage 6 is complete only when: A user can run or replay one matched experiment, understand the smart band+dwell decision, compare every metric with all baselines, and verify MLflow/model/data lineage entirely offline.
Required completion report
Create docs/stage_reports/STAGE_6_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 6. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 6 PROMPT - STOP COPYING
STAGE 7 - End-to-End Integration, Robustness and Final Evidence
BEGIN STAGE 7 PROMPT - COPY FROM HERE
You are the technical lead for the final Stage 7. Convert the six working stages into one reproducible submission-grade repository by fixing integration defects, freezing evidence, proving offline operation and removing every critical TODO from the main path.
Scope: Run clean-state integration, harden edge cases/performance, execute the predeclared final benchmark, package the champion/candidate and precomputed demo, finish documentation and provide one-command launch paths.
Do not build: Do not introduce a new major algorithm, change frozen metric definitions, tune on final test seeds, replace working modules wholesale, fabricate results or widen scope into a presentation/pitch deck.
Start with a clean-state audit
Recreate the Python 3.11 environment from the dependency lock established in Stage 1 using frozen/no-update mode. Any lock change must be intentional, reviewed and recorded. Run database migrations, project doctor, all static checks and all tests before making fixes; record failures in the Stage 7 report.
Verify one linear dependency path only: Stage 1 truth -> Stage 2 receiver -> Stage 5 strategy -> Stage 3 metrics -> Stage 4 DB/MLflow -> Stage 6 dashboard. Remove parallel implementations and circular imports.
Confirm the champion alias exists only if Stage 5 performance_gate_passed=true. Define strategy best-available as champion when present, otherwise structurally valid candidate, otherwise contextual_thompson; print the resolved strategy/model/version and never rename a fallback champion.
Freeze configs/benchmark_final.yaml and held_out_manifest.json hashes. Refuse to run final evidence if either differs from the Stage 5 precommit record unless the change is explicitly documented as invalidating prior results.
Mandatory end-to-end commands
python -m smartscan.cli doctorpython -m smartscan.cli db upgradepython -m smartscan.cli simulate --config configs/demo.yamlpython -m smartscan.cli run --config configs/demo.yaml --strategy sequential --persist --trackpython -m smartscan.cli run --config configs/demo.yaml --strategy best-available --persist --trackpython -m smartscan.cli benchmark --config configs/benchmark_final.yaml --manifest held_out_manifest.json --trackpython -m smartscan.cli demo --offlinepython -m smartscan.cli dashboard
Make each command cross-platform, documented and idempotent where appropriate. The best-available run must print whether it resolved to champion, candidate or contextual_thompson. demo --offline must start or load the local services/data it needs without downloading or retraining.
Final benchmark evidence
Run all predeclared seeds and scenario families for Sequential, Uniform Random, Fixed Priority, Reactive, Contextual Thompson Sampling and the frozen candidate/champion model with paired truth and receiver seeds.
Persist raw seed-level MetricsReports, comparison CSV/JSON, paired deltas, confidence intervals, gate result, model/data/config fingerprints, runtime/memory and package/git provenance.
Generate a concise machine-readable requirements-coverage report mapping every SIH statement need to code path, test, run ID and evidence artifact.
If the performance gate fails on rerun, keep the model candidate, record implementation_complete separately from performance_gate_passed=false and make the dashboard show the failed criteria. The build may be technically complete, but it is not performance-ready until the gate passes.
Do not select a favorable subset of seeds or show only the easiest scenario. Include failures and per-family results.
Robustness matrix
Area
Required cases
Environment
zero emitters; one continuous; overlapping scans; many agile emitters; late unseen activity
Timing
one-step events; long events; boundary hops; final incomplete dwell; invalid noninteger latency
Detection
very low/high SNR; pfa extremes within allowed config; partial dwell; seed replay
Data
missing/gated TSRD; one legal local .h5; stare truth vs scan observations; clipped 0-2 GHz; invalid Wise schema; corrupt checksum
Persistence
empty DB migration; interrupted MLflow link; MLflow offline; moved project root; duplicate retry
ML
missing/corrupt bundle; wrong BandPlan/IBW; absent champion; checksum rejection of untrusted bundle; CPU-only deterministic evaluation
Dashboard
invalid input; long run; no prior runs; unavailable metric; failed gate; offline replay
Performance and resource hardening
Benchmark the demo profile (60 s at 1 ms = 60,000 steps, sixteen bands) on CPU. Record wall time and peak RSS. Target less than 60 seconds and less than 2 GB on the documented reference machine; if unavailable, report measured values and optimize obvious vectorization/storage issues.
Use bool/float32 arrays where safe, chunk external HDF5 reads, avoid per-step ORM inserts and batch/compress logs. Dashboard replay reads bounded windows.
Smoke training must be short and deterministic. Offline demo uses a frozen model and precomputed runs; it never waits for full training.
Add structured logs with domain_run_id/mlflow_run_id and actionable exceptions while avoiding secrets or massive array dumps.
Final repository and documentation
Complete README: problem summary, architecture, setup, data-source limitations, mathematical contracts, commands, retraining, benchmark interpretation, dashboard use, MLflow use, offline demo and known limitations.
Document the v1 scope explicitly: one receiver channel, two-dimensional frequency-time scheduling, radar-style event detection, and no emitter identification, geolocation, communications-waveform classification or coordinated multi-receiver control. List these as extension points rather than implied capabilities.
Keep docs/BUILD_CONTRACT.md, DATA_SOURCES.md, METRICS.md, ORACLE_BOUNDARY.md, MLFLOW.md and docs/stage_reports/STAGE_N_REPORT.md for N=1..7 current.
Verify the Stage-1 dependency lock, update it only for intentional reviewed dependency changes, and create license notices for dependencies/data adapters, .env.example and a strict .gitignore for tokens, databases, raw data, MLflow artifacts and large checkpoints.
Create artifacts/demo/manifest.json referencing the frozen matched runs and model bundle by checksum. Include only reasonably sized, legally redistributable synthetic demo artifacts.
Remove critical TODO/FIXME/placeholder paths, dead code, secret values, absolute machine paths and stale duplicate docs. Do not delete a known limitation; document it.
Add CI for unit/integration/static checks using only tiny fixtures. Mark large-data/full-training tests as explicit opt-in, not silently skipped proof.
Final acceptance gate
Fresh environment install, migrations, doctor, Ruff, mypy and complete offline pytest suite pass; overall coverage is at least 85% with higher thresholds retained for critical modules.
All seven requested metrics and support metrics reproduce from stored truth/logs, with exact schema versions and no denominator drift.
Every stored demo/benchmark run verifies checksums and recomputes metrics within documented floating-point tolerance; domain and MLflow records reconcile.
Turing adapter passes tiny fixture tests and, when the team supplies one authorized local file, a recorded integration test. J.C. Wise-compatible adapter validates a user file or clearly remains optional without fabricated data.
Oracle-boundary tests pass and the live policy behaves identically with evaluation overlay off/on.
The frozen final benchmark uses all predeclared seeds and records performance_gate_passed for champion status. Otherwise champion remains absent and the final report explicitly says which performance or Pfa guardrail criterion failed while retaining a separate implementation_complete result.
demo --offline loads matched precomputed runs and model; the dashboard completes the Stage 6 flow with no network, retraining or uncaught exception.
Requirements-coverage report has no unexplained gap. README commands are executed exactly as written on the clean environment.
Stage 7 is complete only when: A fresh clone can reproduce the stored evidence, launch the offline demo, trace every result through the application DB and MLflow, and honestly show whether the smart scheduler cleared the frozen multi-seed gate.
Required completion report
Create docs/stage_reports/STAGE_7_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 7. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 7 PROMPT - STOP COPYING
Implementation references
These links are supporting references for the coding agent. The repository must pin/record the exact versions it actually uses at build time.
Official SIH 2026 problem-statement portal - https://sih.gov.in/sih2026PS
Alan Turing Institute - Turing Synthetic Radar Dataset - https://huggingface.co/datasets/alan-turing-institute/turing-synthetic-radar-dataset
Alan Turing Institute - Turing Deinterleaving Challenge code and loader - https://github.com/alan-turing-institute/turing-deinterleaving-challenge
MLflow tracking server architecture - https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server/
MLflow Model Registry workflow - https://mlflow.org/docs/latest/ml/model-registry/workflow/
Gymnasium custom-environment documentation - https://gymnasium.farama.org/introduction/create_custom_env/
Stable-Baselines3 PPO documentation - https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html
Legacy J.C. Wise Radar Emitter Database reference (availability may vary; do not scrape or redistribute without rights) - http://www.radars.org.uk/
One-line instructions for the agent
Stage 1: Read the entire specification and current repository. Execute Stage 1 only. Do not begin Stage 2.
For later sessions replace the stage number. Always include the Global Execution Contract when copying a stage manually.
Final handoff check
Seven bounded prompts are present and each ends with a stop condition.
MLflow tracking/model-versioning is linked to the Stage 4 database via stable IDs.
Turing and J.C. Wise-compatible data paths are explicit, legal/offline-safe and testable without downloads.
Intercept-time and interception-ratio prediction are explicit Stage 5 deliverables.
Threat/new-emitter priority and periodic/agile handling use only observable/public information.
Pfa-controlled detection, metric denominators, probability semantics, censoring and multi-seed gates are mathematically frozen.
No stage can claim success without executed tests and recorded evidence.
