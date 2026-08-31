# SIH26055 SmartScan — final project completion report

Date: 2026-08-31  
Python: 3.11.9  
Package: `smartscan`  
This pass did **not** train PPO, create v5, retune thresholds, rewrite frozen AIR, force Gate Passed, or set Champion.

## Architecture summary

Narrow-IBW receiver over a wide scan span. Stages 1–7: RF `GroundTruth` → receiver logs → strategy (`make_policy`) → frozen `evaluate_strategy` → SQLite + local MLflow → Streamlit dashboard → offline demo / held-out evidence.

Authoritative public strategies (`TOTAL_PUBLIC_STRATEGIES = 7`):

`sequential`, `random`, `fixed-priority`, `reactive`, `contextual-thompson`, `periodic-intercept`, `ppo`

Registry: `src/smartscan/ml/strategy_registry.py`. Live PPO: **v4 candidate** (`artifacts/models/scheduler_v4`). Official gate: **v2_frozen_gate** (`scheduler_full` + `held_out_gate.json`). Research protocols `v3_research` and `v4_research` are not mixed with the frozen gate or with live sessions.

## Bugs discovered this pass

See `docs/final/FINAL_BUG_REGISTER.md` and `docs/final/FINAL_PRE_FIX_SNAPSHOT.md`.

| ID | Severity | Status |
|---|---|---|
| F-01 gitignore excluded redistributable bundles | HIGH | FIXED |
| F-02 demo `truth.npz` missing; no rebuild | HIGH | FIXED |
| F-03 `.env.example` still pointed at v2 live path | MEDIUM | FIXED |
| F-04 README/BUILD_CONTRACT stale for submission | HIGH | FIXED |
| F-05 absolute `bundle_dir` in historical ml_improve JSON | LOW | WONTFIX (preserve evidence) |
| F-06 demo caption called live v4 PPO a “v2 replay” | HIGH | FIXED |

Prior stability-audit HIGH items (protocol mixing, identity split, Not recorded, header leakage) were already fixed in tree.

## Bugs remaining

- **CRITICAL: 0**
- **HIGH: 0**
- **LOW:** F-05 machine paths in historical JSON (AIR/gate booleans untouched)

## Strategy verification matrix

Executed in `tests/unit/test_strategy_audit.py::test_seven_strategy_persist_reload_replay_matrix` (factory/run/metrics/persist/reload via `get_run`/replay) and Playwright `scripts/final_browser_qa.py` (UI + replay selector). `periodic-intercept` is `PeriodicInterceptSchedule` (oracle tests in the same module).

```
Strategy              Factory Run Metrics Persist Reload Replay UI
-------------------------------------------------------------------
sequential             PASS    PASS PASS    PASS    PASS   PASS  PASS
random                 PASS    PASS PASS    PASS    PASS   PASS  PASS
fixed-priority         PASS    PASS PASS    PASS    PASS   PASS  PASS
reactive               PASS    PASS PASS    PASS    PASS   PASS  PASS
contextual-thompson    PASS    PASS PASS    PASS    PASS   PASS  PASS
periodic-intercept     PASS    PASS PASS    PASS    PASS   PASS  PASS
ppo                    PASS    PASS PASS    PASS    PASS   PASS  PASS
```

## Quality gates (post-fix, re-run after last product change)

| Check | Result |
|---|---|
| `uv lock --check` | exit 0 |
| `ruff check src tests scripts` | exit 0 |
| `mypy src` | exit 0 (84 files) |
| `pytest tests --cov=smartscan --cov-fail-under=85` | **361 passed**, 1 skipped, **86.74%** coverage, exit 0 |
| `python -c "import smartscan; import smartscan.ml.policies; import smartscan.dashboard.app"` | PASS |
| `python -m smartscan.cli doctor` | `ok=true` (MLflow UI not running is non-blocking) |
| `python -m smartscan.cli db upgrade` | exit 0 |
| `python -m smartscan.cli demo --offline` | `retrained=false` `downloaded=false` |

Combined-package 90% is not claimed: `improve_cycle.py` remains 0% (training; not exercised). Required gate stays 85%.

## Browser QA

Dashboard: `python -m smartscan.cli dashboard --host 127.0.0.1 --port 8503`  
Script: `scripts/final_browser_qa.py` → `artifacts/final_browser_qa.json`

| Viewport | Result |
|---|---|
| 1366 × 768 | PASS (`ok=true`, `failures=[]`) |
| 1920 × 1080 | PASS |

Landing, hamburger open/close/after refresh, Enter Control Center, Load demo, Persist checkbox, VALIDATE & RUN, all six views, Play/Pause/Step, seven replay strategies, Metrics Compare Not recorded + cross-protocol banner, Run History verify, Lineage, Doctor. No traceback, no horizontal overflow, no stale “historical v2 replay” caption.

## Model versions and fingerprints

| Role | Path | content_fingerprint | `load_bundle` |
|---|---|---|---|
| Official gate evidence v2 | `artifacts/models/scheduler_full` | `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746` | PASS |
| Research v3 | `artifacts/models/scheduler_v3` | `e89adc332b7d0532d08fa4d4d694c1dd42cd253a95f6329f2d983d8fc5b4a82f` | PASS |
| Live PPO v4 | `artifacts/models/scheduler_v4` | `a674290744dd6a18f290a2cc248ccd7c9455d77bd5cc0bf4f05a2b33196a9fe7` | PASS |

`uv.lock` SHA-256: `963c937790bd1a0496b7749bb1a1e64be2d435aec47994ba4c9432e4ca88d7b1` (unchanged this pass).

Demo truth fingerprint after rebuild: `db732d9f71deb18c9021528e4517f80d9979504d425ff47cb00a88e75f9d2d70`  
Demo strategies: all seven, including `periodic-intercept`.

## Protocol separation

| Protocol | Bundle | Seeds | Duration | periodic-intercept | Gate |
|---|---|---|---|---|---|
| `v2_frozen_gate` | v2 | 1000–1029 | 0.4 s | Not recorded | **failed** (official) |
| `v3_research` | v3 | 8000–8007 | 0.2 s | Not recorded | failed |
| `v4_research` | v4 | 9000–9007 | 0.2 s | Not recorded | failed |
| `live_session` | v4 weights | session | live/demo | recorded in demo | not a gate |

`performance_gate_passed=false` in `held_out_gate.json`. `champion_set=false`. `best-available` → `candidate` / SmartScanScheduler **v4**.

## Database and MLflow

- `db upgrade` exit 0 on `data/smartscan.db`
- Doctor: `db_mlflow_linkage` no cross-version fingerprints; `no_cross_version_bundle` active ≠ gate
- Tracking DBs and `artifacts/mlflow/` / `artifacts/store/` remain local/gitignored
- MLflow UI not required for offline doctor

## Artifact integrity

Doctor `artifact_integrity ok=true`. Orphans reported (not deleted): `cts_smoke`, `predictor_smoke`, `scheduler_smoke`. Redistributable v2/v3/v4 bundles, `held_out_gate.json`, demo npz/json, and benchmark summaries are intended for git.

## Session state

Documented in `src/smartscan/dashboard/session.py` (`SESSION_KEYS`, `WIDGET_KEYS`). One primary `ui_phase`. Replay resets step/decision index on strategy change. Metrics evidence set selects one protocol.

## Documentation

Updated: `README.md`, `docs/BUILD_CONTRACT.md` current-state section, `.env.example`, root `THIRD_PARTY_NOTICES.md`. Existing: `docs/METRICS.md`, `docs/ORACLE_BOUNDARY.md`, `docs/MLFLOW.md`, `docs/DATA_SOURCES.md`, `LICENSE`.

## Git preparation

Initialized on `main` after this report. Secrets (`.env`, `*.db`, MLflow artifact store, 70 GB corpus) stay gitignored. GitHub target: private `Praveen-Kumar-Goswami/SIH26055`. Commit message: `feat: complete SIH26055 SmartScan prototype`. SHA is the `main` commit that contains this file.

## Remaining limitations (not bugs)

- Official and research gates all failed; no Champion
- `periodic-intercept` not in frozen historical tables
- Do not rank AIR across protocols
- `improve_cycle.py` untested in CI (do not train to raise coverage)
- Historical ml_improve JSON may contain original absolute paths
