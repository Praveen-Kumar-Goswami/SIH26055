# Frozen metric definitions

Schema version follows `smartscan.types.SCHEMA_VERSION`. Names and denominators are frozen in Stage 3 (`smartscan.metrics.engine.evaluate_strategy`). Stages 5–7 fill forecast fields; they must not invent parallel metrics or silently change denominators.

Unavailable values are `available=false` with a reason. They are never NaN, Inf, or a fabricated zero.

## Seven required figures of merit

| Key | Display name | Definition |
| --- | --- | --- |
| `pd` | Pd | TP occupied completed dwells / all occupied completed dwells. Stratify by dwell, SNR, occupied fraction in support tables. Controlled sensitivity sweeps isolate the detector. |
| `pfa` | Pfa | False-alarm detections in noise-only completed dwells / all noise-only completed dwells. |
| `sensitivity` | Sensitivity | SNR dB where controlled Pd reaches the configured target (default 0.90). Also receiver-input dBm when physical-noise mode is configured. Not the scheduler-conditioned Pd. |
| `average_intercept_rate` | Average intercept rate | Distinct band-occupancy events first detected on the correct band / simulated seconds. |
| `average_reward` | Average reward/cost | Mean realized observable reward per completed decision. Components are listed separately. Unavailable until rewards exist. |
| `correct_predictions` | Correct predictions | 100 × (TP+TN) / scored decisions using pre-action `p_active` versus post-run usable-dwell occupancy. `p_hit` Brier/ECE is reported separately. |
| `average_intercept_time_error` | Average intercept-time error | MAE between the pre-action time-to-next-completed-hit forecast and the first future completed hit inside the declared horizon. Always report censoring and coverage. |

## Supporting outputs

Event interception ratio = captured band-occupancy events / all band-occupancy events.

Also reported: mean/median first-detection delay from event start; censored/penalized all-event delay; missed-event count; wasted-dwell fraction; tuning fraction; threat-weighted capture (evaluator-only weights); hit-forecast Brier/ECE for `p_hit` versus observable hit/miss; activity-forecast Brier/ECE for `p_active` versus occupancy truth.

## No survivorship bias

Successful-event delay and forecast MAE must show denominator and coverage. Missed or unvisited opportunities are never dropped. They are censored and included in an all-event penalized/RMST-style statistic.

## Intercept-time target

At each decision start, predict elapsed seconds to the end of the first future completed command that returns `hit=true` under the proposed scheduler. Stage 2 emits one decision per completed dwell, so this is a scheduler-level target, not a sub-dwell timestamp. Right-censor at the declared forecast or episode horizon.

## Capture unit

Capture units are `BandOccupancyEvent`s (maximal occupancy runs per band), not emitter events. One detection matches at most one event in the same band, ordered by detection time then event start.

## Comparison

`compare_runs` / `paired_compare` resample whole runs or seeds, never time steps. Held-out Stage 5/7 gates use the frozen keys above plus paired CIs and a Pfa Newcombe guardrail. Thresholds live in `configs/benchmark_final.yaml` and must not be relaxed to pass a run.

## Dashboard

Plot payloads must include units, denominators, and CIs when present. Unavailable metrics render as “Not available”, never a win badge or a filled-in zero.
