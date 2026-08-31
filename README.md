# SIH26055 Smart Scan Strategy for Electronic Warfare

Offline-first prototype of a narrow-instantaneous-bandwidth receiver scanning a much wider spectrum. **Stages 1–7 are implemented.** The project is **engineering-complete**. The frozen held-out **performance gate is not passed**. Champion is **not set**.

Problem statement: [SIH 2026 SIH26055](https://sih.gov.in/sih2026PS). Specification: `docs/SIH26055_BUILD_SPEC.md`. Contracts: `docs/BUILD_CONTRACT.md`. Metrics: `docs/METRICS.md`. Oracle rules: `docs/ORACLE_BOUNDARY.md`. Tracking: `docs/MLFLOW.md`. Data: `docs/DATA_SOURCES.md`. License: `LICENSE`. Notices: `THIRD_PARTY_NOTICES.md`.

`implementation_complete` and `performance_gate_passed` are separate. Do not treat a working dashboard as a scheduler win.

## Objective

Control a single receiver channel whose instantaneous bandwidth is much smaller than the scan span. Compare seven public scan strategies on synthetic (and optional licensed) RF ground truth. Persist runs, replay them without re-deciding, and report frozen metrics honestly — including **Not available** / **Not recorded** when a figure of merit was not computed or not in that protocol.

## Architecture

Linear path only:

1. Stage 1 `GroundTruth` (simulator or optional TSRD adapter)
2. Stage 2 receiver (`ObservationLog` / `DecisionLog`)
3. Stage 5 strategy (`make_policy` / PPO bundle) on those logs
4. Stage 3 `evaluate_strategy` (frozen figures of merit)
5. Stage 4 SQLite domain store + local MLflow
6. Stage 6 Streamlit dashboard over those services
7. Stage 7 frozen evidence pack, offline demo, one-command launch

There is one metrics engine, one log schema, one public strategy registry, and one bundle format. The dashboard and CLI do not reimplement detector or metric formulas.

## Setup

**Python 3.11** is required (developed on 3.11.9). From the repository root:

```text
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip uv
uv sync --frozen --extra dev
```

If `uv.lock` must change, review it and record the reason. Equivalent pip install: `python -m pip install -e ".[dev]"`.

Copy `.env.example` to `.env` only if you need local overrides. Unit tests never need `HF_TOKEN`, network access, or the 70 GB Turing corpus.

## Dashboard and offline demo

```text
python -m smartscan.cli doctor
python -m smartscan.cli db upgrade
python -m smartscan.cli demo --offline
python -m smartscan.cli dashboard --host 127.0.0.1 --port 8501
```

`demo --offline` upgrades the local DB, rebuilds matched demo logs if `truth.npz` or strategy recordings are missing, loads frozen bundle checksums, and does **not** download or retrain PPO.

Then open `http://127.0.0.1:8501`. Landing page → Enter Control Center. Hamburger navigation:

1. Configure & Run
2. Scan Replay
3. Smart Decision
4. Metrics Compare
5. Run History
6. Model & Data Lineage

Doctor and Quick Guide are reachable from the same shell.

## Seven public strategies

Authoritative IDs (`TOTAL_PUBLIC_STRATEGIES = 7`) live in `src/smartscan/ml/strategy_registry.py`:

| ID | Kind | Notes |
|---|---|---|
| `sequential` | rule | Documented band order |
| `random` | rule | Uniform random legal commands |
| `fixed-priority` | rule | Public priority list only |
| `reactive` | adaptive statistical | Hit-recency + exploration; receiver-visible only |
| `contextual-thompson` | adaptive statistical | Thompson sampling on observable features |
| `periodic-intercept` | adaptive statistical | Search then stare using **previous hits only** (SIH periodic-scan outline). Not in the frozen v2/v3/v4 gate tables |
| `ppo` | learned RL | Live weights: SmartScanScheduler **v4 candidate** |

`periodic-intercept` is a real policy (`PeriodicInterceptSchedule`). It must not read GroundTruth occupancy, future activity, true emitter IDs, true periods, or evaluator matches.

## Model status vs historical gate

Keep these separate. They are **not** one generic “model” field.

| Role | Identity | Path | Gate |
|---|---|---|---|
| **Active PPO (live)** | SmartScanScheduler **v4**, alias **candidate** | `artifacts/models/scheduler_v4` | not a gate protocol |
| **Official historical gate** | SmartScanScheduler **v2** | `artifacts/models/scheduler_full` + `artifacts/models/held_out_gate.json` | **Not Passed** (`performance_gate_passed=false`) |
| Research v3 | `scheduler_v3` | `artifacts/ml_improve/fresh_test_gate.json` | failed (different protocol; seeds 8000–8007, 0.2 s) |
| Research v4 eval | same v4 weights, research seeds 9000–9007 | `artifacts/ml_improve/fresh_test_v4_gate.json` | failed (different protocol; not a live dashboard session) |

`best-available` currently resolves to **candidate** (v4), never implying Champion. Champion/production aliases require a passing held-out gate. That did not happen. Metrics Compare must not rank AIR across incompatible protocols (v2 0.4 s seeds 1000–1029 vs v3/v4 0.2 s different seeds). Historical missing `periodic-intercept` AIR is **Not recorded**, not `0`.

Redistributable bundles (v2/v3/v4 weights, gate JSON, demo recordings, benchmark summaries) are committed. Local SQLite, MLflow artifact dirs, training datasets, and smoke checkpoints stay gitignored.

## Metrics

Frozen names and formulas: `docs/METRICS.md`. Zero denominators and missing forecasts are `available=false` with a reason — never silent `0` / NaN / Inf in the UI. Display **Not available** when appropriate.

## Reproducibility

```text
python -m smartscan.cli simulate --config configs/demo.yaml
python -m smartscan.cli run --config configs/demo.yaml --strategy sequential --persist --track
python -m smartscan.cli run --config configs/demo.yaml --strategy best-available --persist --track
python -m smartscan.cli benchmark --config configs/benchmark_final.yaml --manifest held_out_manifest.json --track
```

`benchmark` refuses to run if `configs/benchmark_final.yaml` or `configs/held_out_manifest.json` differ from `configs/frozen_hashes.json`. CI does not run the 30-seed eval; set `SMARTSCAN_FULL_BENCH=1` or use the `benchmark` CLI.

`best-available` prints `resolved_source` as `champion`, `candidate`, or `contextual_thompson`. A fallback is never renamed champion.

## Additional commands

```text
python -m smartscan.cli inspect-ground-truth artifacts/runs/stage1_demo.npz
python -m smartscan.cli import-turing --input /path/train.h5 --band-plan demo_2_18 --output data/processed/sample.npz
python -m smartscan.cli validate-wise --input /path/catalog.csv
python -m smartscan.cli receive --truth artifacts/runs/stage1_demo.npz --strategy sequential --seed 42 --output artifacts/runs/stage2_seq.npz
python -m smartscan.cli metrics --truth artifacts/runs/stage1_demo.npz --log artifacts/runs/stage2_seq.npz --output artifacts/runs/stage3_seq_metrics.json
python -m smartscan.cli sensitivity --receiver-config configs/receiver.yaml --target-pd 0.90 --output artifacts/runs/sensitivity.json
python -m smartscan.cli runs list --strategy sequential --order-by avg_intercept_rate
python -m smartscan.cli runs verify <domain_run_id>
python -m smartscan.cli mlflow reconcile --all
python -m smartscan.cli mlflow serve
python -m smartscan.cli collect --config configs/train_smoke.yaml
python -m smartscan.cli train-predictor --config configs/train_smoke.yaml --track
python -m smartscan.cli train-contextual-bandit --config configs/train_smoke.yaml --track
python -m smartscan.cli train-scheduler --config configs/train_smoke.yaml --track
python -m smartscan.cli evaluate --config configs/benchmark_final.yaml --model models:/SmartScanScheduler@candidate --seeds 30 --track
python -m smartscan.cli models promote --name SmartScanScheduler --version <version> --require-gate
python scripts/doctor.py
python scripts/make_demo_data.py
```

## Retraining (not required for the demo)

Smoke configs (`configs/train_smoke.yaml`, 256 PPO steps) are for tests and wiring. They are not performance claims.

Full training uses `configs/train_full.yaml` (200k PPO steps, CPU). Train/val catalogs do not overlap frozen held-out seeds 1000–1029. Do not retune thresholds or regenerate `held_out_manifest.json` to chase a gate pass.

Champion promotion requires `--require-gate` and `performance_gate_passed=true`. That is currently false.

## Benchmark interpretation

The frozen held-out set is 30 paired seeds (1000–1029) across sparse, dense, agile_threat, unseen_random, and tsrd_synthetic. Strategies: sequential, uniform random, fixed-priority, reactive, contextual Thompson, PPO candidate, plus oracle ceiling labeled **unattainable**. `periodic-intercept` is **not** in that frozen table.

Gate thresholds are in `configs/benchmark_final.yaml`. Failure keeps the model **candidate**. `docs/evidence/held_out_gate_summary.json` records reasons without dropping hard families.

Do not cherry-pick seeds. Do not compare v3/v4 research AIR to v2 gate AIR as a like-for-like improvement.

## MLflow

Local only. See `docs/MLFLOW.md`. Domain DB `data/smartscan.db`, MLflow `data/mlflow.db`, artifacts `artifacts/mlflow/`, UI `127.0.0.1:5000`. `mlflow reconcile` repairs interrupted links without duplicates.

## Detector mathematics

Internal calculations are linear. This is **not** CFAR (no reference cells).

```text
rho[n]  = signal_power_w[n, band] / noise_power_w
M       = samples_per_step * dwell_steps
Under H0:  Z ~ Gamma(shape=M, scale=1)
threshold  = GammaPPF(1 - pfa_design; shape=M, scale=1)
Under H1:  2Z ~ ncx2(df=2M, nc=2 * samples_per_step * sum(rho))
detection  = (Z >= threshold)
```

Normalized noise mode uses `noise_power_w=1` unless overridden. Physical mode uses `k * T0 * IBW * 10^(NF/10)`. Stage 5 training/benchmark overrides `noise_power_w` to `1e-13` so builtin emitter powers (~1e-12 W) are detectable. That is a receiver-config choice, not a change to Stage 1 truth.

Tune cost is integer steps (default 1 ms). A requested physical latency that is not an integer multiple of `dt` is rejected. Same-band commands skip retune only when the receiver is already settled. One hit/miss is emitted at dwell completion; the intercept timestamp is that decision's `end_step`.

## Band and time mathematics

Time is integer-indexed. `N = round(T/dt)` only when `T/dt` is an integer within `1e-9`; otherwise the config is rejected. Periodic behaviour uses `n % period_steps`. Reporting times are `t[n] = n * dt`.

A band occupies the half-open interval `[edge[k], edge[k+1])`. Mapping uses `searchsorted(..., side="right")` minus one, with an explicit high-edge exclusion. Exactly 18 GHz is out of range on both shipped profiles.

Shipped profiles: `demo_2_18` (sixteen 1 GHz bands, 2–18 GHz); `turing_0_18` (eighteen 1 GHz bands, 0–18 GHz). Overlapping emitters combine with logical OR for occupancy and linear addition for power. Decibel values are never summed.

## Emitter classes

Exactly four public types. An `OnOffGate` may be composed into any of them; it is not a fifth type.

1. `ContinuousEmitter` — fixed frequency, optional gate and `[start_step, end_step)`
2. `CircularScanEmitter` — `phase_step[n] = (phase0_steps + n) mod period_steps`; beamwidth maps to integer phase bins
3. `SectorScanEmitter` — triangular sweep over `[theta_min, theta_max]` including endpoints; illumination uses wrap-free angular distance
4. `FrequencyAgileEmitter` — `hop_bands[(phase_offset + n // dwell_steps) mod L]`

Events are maximal emitter-band illumination intervals `[start_step, end_step)`. Optional `threat_weight` is evaluator-only and never policy-visible.

Built-in scenarios: `sparse`, `dense`, `agile_threat`, `edge_zero`. Same config and seed must reproduce the same `content_fingerprint`. `--seed` is the detector seed; `--schedule-seed` (default 0) is independent.

## Project structure

```text
src/smartscan/          package (rf, receiver, metrics, storage, ml, dashboard, release)
configs/                demo, dashboard, receiver, frozen hashes, held-out manifest
tests/                  unit + integration
scripts/                doctor, demo data, browser QA
artifacts/models/       redistributable v2/v3/v4 bundles + held_out_gate.json
artifacts/demo/         matched offline demo recordings
artifacts/benchmark_final/  frozen summary JSON/CSV
docs/                   contracts, metrics, oracle, MLflow, stage reports, final audit
```

## Public data limitations

TSRD is optional, gated, and large. Tests use a handful of synthetic PDWs. Amplitude is published as dB; this project defaults to `10 log10(power_W / 1 W)` and records that assumption in provenance. Scan-mode files are observations: missing pulses are not non-transmissions. For `demo_2_18`, pulses below 2 GHz are dropped and counted, never remapped.

The J.C. Wise radar emitter database is not redistributed. Supply a local CSV/JSON that matches `docs/DATA_SOURCES.md`. Tests ship only a clearly synthetic schema example.

## Quality

```text
uv lock --check
ruff check src tests scripts
mypy src
pytest tests --cov=smartscan --cov-fail-under=85
```

Critical packages (rf, data, receiver, metrics, storage, ml, dashboard) retain a 90% target in stage reports. Full held-out eval and full PPO training are explicit opt-in (`SMARTSCAN_FULL_BENCH=1`, `SMARTSCAN_FULL_TRAIN=1`), not silent skips used as proof.

## v1 scope and extension points

v1 is one receiver channel, two-dimensional frequency-time scheduling, and radar-style event detection.

Not in v1 (extension points, not implied capabilities):

- Emitter identification or deinterleaving of concurrent emitters beyond occupancy events
- Geolocation / TDOA / AOA geolocation
- Communications-waveform classification
- Coordinated multi-receiver or multi-platform control
- Online / in-the-field learning from classified intercepts
- A claimed scheduler win while `performance_gate_passed` is false

## Known limitations

- Official v2 held-out PPO did not clear the frozen multi-seed gate. Alias remains candidate. v3 and v4 research gates also failed on their own protocols.
- Champion is unset. `best-available` = candidate v4, not champion.
- Oracle ceiling is unattainable and not a deployable baseline.
- Demo live runs are duration-capped; the 60 s / 60_000-step CPU probe is a sequential scan, not PPO training.
- `periodic-intercept` is live/demo only; historical v2/v3/v4 evidence tables do not contain it.
- Combined-package coverage can sit below 90% because `improve_cycle.py` (training) is not exercised in CI. The required gate remains `--cov-fail-under=85`.
- Historical research JSON under `artifacts/ml_improve/` may contain the original machine’s absolute `bundle_dir` paths. AIR and gate booleans were not rewritten.
- Provenance records `git_sha=null` when `.git` is absent.
- Combined 90% package coverage is not a release blocker; do not train PPO solely to raise it.
