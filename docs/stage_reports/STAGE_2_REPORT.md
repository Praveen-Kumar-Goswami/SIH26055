# Stage 2 report — scanning receiver and open-loop schedules

`implementation_complete`: **true**

`performance_gate_passed`: **not applicable** (Stage 2 has no scheduler performance gate)

## Files created or changed, grouped by purpose

### Receiver implementation
- `src/smartscan/receiver/detector.py` — Pfa-controlled noncoherent energy detector (not CFAR), Gamma/ncx2 sampling, physical/normalized noise, integer latency
- `src/smartscan/receiver/scanner.py` — TUNING/DWELLING state machine and `run_schedule`
- `src/smartscan/receiver/schedules.py` — Sequential, UniformRandom, FixedPriority; `ScheduleView` protocol
- `src/smartscan/receiver/logs.py` — ObservationLog / DecisionLog / NPZ save-reload / evaluator diagnostics
- `src/smartscan/receiver/__init__.py` — public exports

### Frozen contracts and CLI
- `src/smartscan/types.py` — `noise_power_w`, stricter `ReceiverConfig` / dwell validation
- `src/smartscan/cli.py` — `receive` (`--seed` detector, `--schedule-seed` independent)
- `src/smartscan/config.py` — receiver YAML docstring
- `configs/receiver.yaml` — IBW 100 MHz, span 16 GHz, dwell bins `[1,2,4,8,16]`, `pfa_design=1e-3`, normalized noise

### Docs
- `README.md` — Stage 2 status, detector equations, `receive` commands
- `docs/BUILD_CONTRACT.md` — ObservationLog/DecisionLog fields, three schedules, seed split
- `docs/stage_reports/STAGE_2_REPORT.md` — this report

### Tests
- `tests/unit/test_detector.py`, `test_scanner.py`, `test_schedules.py`, `test_logs.py`
- `tests/integration/test_receive.py`
- `pyproject.toml` — `smartscan.receiver` included in coverage (no longer omitted)

## Commands executed and actual exit status

| Command | Exit status |
| --- | --- |
| `ruff check src tests scripts` | 0 |
| `mypy src` | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov-fail-under=90` | 0 |
| `python -m smartscan.cli inspect-ground-truth artifacts/runs/stage1_demo.npz` | 0 |
| `python -m smartscan.cli receive --truth artifacts/runs/stage1_demo.npz --strategy sequential --seed 42 --output artifacts/runs/stage2_seq.npz` | 0 |
| `python -m smartscan.cli receive --truth artifacts/runs/stage1_demo.npz --strategy random --seed 42 --output artifacts/runs/stage2_random.npz` | 0 |

No unrun check is claimed as passed.

## Tests, coverage, acceptance-gate evidence

- **113 passed**, 0 failed
- Combined line coverage **smartscan.rf + smartscan.data + smartscan.receiver: 97.69%** (threshold 90%)
  - `smartscan.receiver`: detector 100%, scanner 100%, schedules 100%, logs 100%
  - Stage 1 packages remain above 90%
- Same-band dwell uses zero retune only after the receiver is settled; first command always retunes; cross-band TUNING has null `tuned_band`, energy 0, no detection
- Exactly one hit/miss per completed dwell; intercept timestamp is `end_step`; incomplete end-of-run tune/dwell produces no DecisionRow
- `scan_span_hz/receiver_ibw_hz < 10` and IBW wider than the target band are rejected; invalid band commands fail
- Threshold and Pd match `scipy.stats` Gamma PPF / ncx2 SF; noise-only Monte Carlo (n=40000, M=8, pfa=1e-3, seed=12345) 95% binomial CI contains `pfa_design`; strong-signal Pd approaches analytic Pd
- Partial-dwell noncentrality is `2 * samples_per_step * sum(rho)`; overlapping power is linear; dB round-trips are accurate
- Same truth/schedule/seed replays identical logs; changing only receiver seed changes detections, not commanded bands; `--schedule-seed` is independent
- Sequential, uniform-random, and fixed-priority never read GroundTruth occupancy

Official demo receive (Stage 1 truth, `configs/receiver.yaml`, detector seed 42, schedule seed 0, default dwell 8):

| Strategy | completed_dwells | detections | hits | misses | false_alarms | tuning_fraction | n_incomplete |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sequential | 222 | 0 | 0 | 16 | 0 | 0.1115 | 1 |
| random | 252 | 0 | 0 | 23 | 0 | 0.1155 | 1 |

Hits/misses/false alarms are evaluator-join diagnostics, not Stage 3 figures of merit.

## Reproducibility

- Detector seed: **42** (`--seed`)
- Schedule seed: **0** (`--schedule-seed`)
- Receiver config: `configs/receiver.yaml` (`pfa_design=1e-3`, normalized noise)
- Stage 1 truth: `artifacts/runs/stage1_demo.npz`
- `content_fingerprint`: `0a1189f223baa22d3d9823764518a402ef0f0a3832ea5c48fdfca5b118b20c05`
- `receiver_config_hash`: `410388f9a0fe40192e29f6c3718a6edbe5db20ce7a83f9e79fe48284d2de67aa`
- sequential `artifact_sha256`: `ab5133186569d54eb9ff9a7ad00e6efad32c16e3c5f400960a4f5df90164e517`
- random `artifact_sha256`: `34b6968ad0837fab9c0e31d7269aead68ad84e7587ecc2a72401d21922d3a93b`
- Schema: `1.0.0`
- Runtime: Python 3.11.9 in `.venv`
- Git SHA: **none** (repository is not a git repo yet)

## Known limitations (not blockers)

- Official demo emitters are ~1e-12 W against normalized `noise_power_w=1`, so the Stage 1 demo is effectively H0 at the receiver. Detector Pd/Pfa are validated on synthetic high-SNR fixtures. Stage 1 truth was not altered to make detection easier.
- Physical thermal noise (`k*T0*IBW*F`) is opt-in via `noise_mode: physical`.
- CLI diagnostic counts (hits/misses/false alarms/tuning fraction/average measured SNR) are not the Stage 3 metric suite.
- A scripted test schedule may raise `StopIteration` when it runs out of commands; production sequential/random/priority schedules never exhaust.

## Stop condition

Stage 2 is complete. Stage 3 has not been started. Waiting for an explicit instruction to execute Stage 3.
