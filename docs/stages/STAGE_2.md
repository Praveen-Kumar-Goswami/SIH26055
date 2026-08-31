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
