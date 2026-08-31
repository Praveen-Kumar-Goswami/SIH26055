# Stage 3 report — metrics engine and sensitivity

`implementation_complete`: **true**

`performance_gate_passed`: **not applicable** (Stage 3 has no scheduler performance gate)

## Files created or changed, grouped by purpose

### Metrics engine
- `src/smartscan/metrics/schemas.py` — MetricValue helpers, BandOccupancyEvent, tables, EvaluationResult
- `src/smartscan/metrics/matching.py` — occupancy-run capture units and one-to-one detection matching
- `src/smartscan/metrics/engine.py` — `evaluate_strategy` / `evaluate_run`, JSON/CSV I/O
- `src/smartscan/metrics/sensitivity.py` — controlled analytic/MC Pd vs SNR sweep
- `src/smartscan/metrics/statistics.py` — Brier/ECE, Kaplan–Meier/RMST, run-level bootstrap, `compare_runs`
- `src/smartscan/metrics/__init__.py` — public exports

### CLI, coverage, docs
- `src/smartscan/cli.py` — `metrics` and `sensitivity` subcommands
- `pyproject.toml` — `smartscan.metrics` included in coverage
- `README.md`, `docs/BUILD_CONTRACT.md`
- `docs/stage_reports/STAGE_3_REPORT.md` — this report

### Tests
- `tests/unit/test_metrics.py`, `test_sensitivity.py`, `test_statistics.py`
- `tests/integration/test_metrics_cli.py`

## Commands executed and actual exit status

| Command | Exit status |
| --- | --- |
| `ruff check src tests scripts` | 0 |
| `mypy src` | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov=smartscan.metrics --cov-fail-under=90` | 0 |
| `pytest tests --cov=smartscan.metrics --cov-fail-under=95` | 0 |
| `python -m smartscan.cli metrics --truth artifacts/runs/stage1_demo.npz --log artifacts/runs/stage2_seq.npz --output artifacts/runs/stage3_seq_metrics.json` | 0 |
| `python -m smartscan.cli sensitivity --receiver-config configs/receiver.yaml --target-pd 0.90 --output artifacts/runs/sensitivity.json` | 0 |

No unrun check is claimed as passed.

## Tests, coverage, acceptance-gate evidence

- **138 passed**, 0 failed
- Combined line coverage **rf + data + receiver + metrics: 98.46%** (threshold 90%)
- **`smartscan.metrics`: 99.63%** (threshold 95%)
  - engine 99%, matching 100%, schemas 100%, sensitivity 99%, statistics 100%
- Golden fixture: exact BandOccupancyEvent boundaries; Pd = 1/3; Pfa = 1/1; intercept rate numerator 1 over T=0.02 s; interception 1/2
- One detection overlapping two disjoint events matches the earlier-start event only; overlapping emitter threat weights use max aggregation
- Perfect / never-visits-active / all-noise / all-active / zero-event / incomplete-final-dwell cases
- Pd uses only occupied completed dwells; Pfa uses only noise-only completed dwells; occupancy in other bands does not reclassify a dwell
- Analytic sensitivity SNR at Pd=0.90 agrees with inverted Stage 2 `analytic_pd`; higher target Pd ⇒ higher SNR; higher Pfa ⇒ lower SNR; physical mode reports consistent receiver-input dBm
- Forecast metrics unavailable with reasons when absent; when present, `p_hit` and `p_active` scores differ; intercept-time coverage is reduced by right-censoring
- Missed events lower interception ratio and raise all-event penalized delay; they do not vanish from a successful-only mean
- JSON round-trip preserves schema and full-precision scalars

Official sequential demo evaluation (Stage 1 truth + Stage 2 sequential log, detector seed 42):

| Metric | Value | Numerator/denominator |
| --- | --- | --- |
| Pd | 0 | 0/16 |
| Pfa | 0 | 0/206 |
| Sensitivity (analytic) | 4.02077 dB | at target Pd 0.90, M=8, pfa=1e-3 |
| Average intercept rate | 0 /s | 0/2 s |
| Average reward | unavailable | `no_observable_reward_in_decision_log` |
| Correct predictions | unavailable | `pre_action_forecasts_absent` |
| Average intercept-time error | unavailable | `pre_action_forecasts_absent` |
| event_interception_ratio | 0 | 0/5 |
| wasted_dwell_fraction | 0.927928 | 206/222 |
| tuning_fraction | 0.1115 | 223/2000 |
| threat_weighted_capture | 0 | 0/5 |
| all_event_penalized_delay_s | 2 s | 10/5, horizon 2 s |

MC sensitivity CLI (n_trials=2000, seed=12345): SNR dB at Pd=0.90 is **4.10606** (within 0.1 dB of the analytic threshold).

## Reproducibility

- Stage 1 truth fingerprint: `0a1189f223baa22d3d9823764518a402ef0f0a3832ea5c48fdfca5b118b20c05`
- Stage 2 sequential log: `artifacts/runs/stage2_seq.npz` (receiver seed 42, schedule seed 0)
- Metrics content fingerprint (excludes `created_at`): `0985cbe6b7f9f22e58cafd13a17e07fd3a856bb8fefca66347b1e7a716ef7a79`
- `stage3_seq_metrics.json` artifact SHA-256: `e8dfc60565d1d9170d8e71ab099f4307c48578c95c599da60c55a7892db23288` (includes volatile `created_at`)
- `sensitivity.json` artifact SHA-256: `395e1a18adfef6687837e7b34973060272f77418a0c9a657dcfd0cd085c00c3b`
- Sensitivity seed: **12345**; target Pd **0.90**; M **8**; pfa **1e-3**
- Schema: `1.0.0`
- Runtime: Python 3.11.9 in `.venv`
- Git SHA: **none** (repository is not a git repo yet)

## Known limitations (not blockers)

- Official demo detections remain H0 (Stage 1 powers ~1e-12 W vs normalized noise 1), so Pd, intercept rate, and interception ratio are zero on the demo artifacts. Golden high-SNR fixtures exercise the formulas.
- Forecast metrics are correctly unavailable until Stage 5 writes `p_active`, `p_hit`, and intercept-time forecasts. They are never filled with zero.
- `evaluation_score` is intercept ratio minus wasted-dwell fraction, not a learned reward. Component metrics stay visible.
- Miss-penalty / KM horizon defaults to episode duration (2 s on the demo).
- JSON `artifact_sha256` of the metrics file changes if `created_at` changes; use `content_fingerprint` for semantic identity.

## Stop condition

Stage 3 is complete. Stage 4 has not been started. Waiting for an explicit instruction to execute Stage 4.
