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
