# Stage 1 report — RF environment and public-data adapters

`implementation_complete`: **true**

`performance_gate_passed`: **not applicable** (Stage 1 has no scheduler performance gate)

## Files created or changed, grouped by purpose

### Repository foundation
- `pyproject.toml`, `uv.lock`, `.gitignore`, `.env.example`, `README.md`
- `configs/demo.yaml`, `configs/receiver.yaml`, placeholder train/benchmark YAMLs
- `src/smartscan/` src layout including later-stage package stubs
- `scripts/doctor.py`, `scripts/make_demo_data.py`

### Frozen contracts and docs
- `docs/SIH26055_BUILD_SPEC.md` (authoritative spec)
- `docs/BUILD_CONTRACT.md`, `docs/DATA_SOURCES.md`
- `docs/stages/STAGE_0_GLOBAL.md` through `STAGE_7.md`
- `src/smartscan/types.py`, `config.py`, `seeding.py`

### RF simulator
- `src/smartscan/rf/bands.py`, `emitters.py`, `events.py`, `environment.py`, `io.py`

### Data adapters
- `src/smartscan/data/turing.py`, `wise.py`, `provenance.py`

### CLI
- `src/smartscan/cli.py`, `__main__.py`

### Tests and fixtures
- `tests/unit/*`, `tests/integration/test_scenarios.py`
- `tests/fixtures/wise_synthetic.csv`, `wise_bad.csv`, `tsrd.py`, `tsrd_tiny.h5`, `expected_checksums.json`

## Commands executed and actual exit status

| Command | Exit status |
| --- | --- |
| `ruff check src tests scripts` | 0 |
| `mypy src` | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov-fail-under=90` | 0 |
| `python -m smartscan.cli simulate --config configs/demo.yaml --output artifacts/runs/stage1_demo.npz` | 0 |
| `python -m smartscan.cli inspect-ground-truth artifacts/runs/stage1_demo.npz` | 0 |
| `python -m smartscan.cli validate-wise --input tests/fixtures/wise_synthetic.csv` | 0 |
| `python -m smartscan.cli import-turing --input tests/fixtures/tsrd_tiny.h5 --band-plan demo_2_18 --output data/processed/sample.npz --duration 0.01` | 0 |
| `python scripts/doctor.py` | 0 |
| `uv lock --python 3.11` | 0 |

No unrun check is claimed as passed.

## Tests, coverage, acceptance-gate evidence

- **70 passed**, 0 failed
- Combined line coverage **smartscan.rf + smartscan.data: 96.74%** (threshold 90%)
  - `smartscan.rf`: bands 95%, emitters 96%, environment 96%, events 100%, io 100%
  - `smartscan.data`: turing 96%, wise 97%, provenance 100%
- T/dt non-integer configs rejected; exactly 18 GHz is out of range on both band plans
- Continuous, circular (illuminated-step count within one sample of beamwidth duty), sector endpoints/directions, wrap-free angular distance, agile hop at every dwell boundary, on/off gating
- Overlapping occupancy is OR; power is linear-sum; same-band adjacent hops stay one event
- Same seed/config → identical `content_fingerprint` across NPZ and HDF5; different seed changes fingerprint and occupancy; save/reload is bit-exact; `artifact_sha256` matches file bytes
- Built-ins `sparse`, `dense`, `agile_threat`, `edge_zero` validate; late emitter and evaluator-only threat weights present in `agile_threat`
- Tiny TSRD fixture: 10log10 energy aggregation, bin-boundary pulse width, namespaced labels, 0–2 GHz clip reported, NaN amplitude quarantined, stare vs scan observation flag
- Wise synthetic catalog validates; GHz-as-Hz unit errors rejected

Demo simulate printed per-band activity and created a reloadable artifact:

- `N=2000`, `K=16`, `dt=0.001`, `events=5`, `active_bands=2`
- `6-7GHz` occupied_frac=0.1000 (circular scan)
- `10-11GHz` occupied_frac=1.0000 (continuous)

## Reproducibility

- Seed: **42** (`configs/demo.yaml`)
- Band plan: `demo_2_18`
- Scenario: `sparse`
- `content_fingerprint`: `0a1189f223baa22d3d9823764518a402ef0f0a3832ea5c48fdfca5b118b20c05`
- Demo `artifact_sha256` (this machine, gzip/NPZ bytes): `b16cf5889a04481267e8eaa9b5d5795f24e25365a555e7be33778275ff1de701`
- Generator/schema: `1.0.0`
- Runtime: Python 3.11.9 in `.venv`
- Git SHA: **none** (repository is not a git repo yet)

## Known limitations (not blockers)

- TSRD Amplitude is published as dB; default conversion is `10 log10` power. Provenance records the assumption. `20log10_amplitude` is opt-in.
- `turing_deinterleaving_challenge.PulseTrain.load` is used when installed; tests use the published PulseTrain HDF5 layout without the 70 GB corpus or `HF_TOKEN`.
- Demo duration is 2 s at 1 ms. Stage 7 may lengthen the demo profile to 60 s.
- Stage 2+ (receiver, metrics, MLflow, scheduler, dashboard) are not built.

## Stop condition

Stage 1 is complete. Stage 2 has not been started. Waiting for an explicit instruction to execute Stage 2.
