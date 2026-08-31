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
