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
