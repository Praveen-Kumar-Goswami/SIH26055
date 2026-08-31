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
