# Stage 6 report — offline Streamlit / Plotly dashboard

`implementation_complete`: **true**

`performance_gate_passed`: **false** (Stage 5 held-out gate; unchanged). The dashboard shows **candidate** status and the failed criteria. It does not display a scheduler win badge.

Stage 6 is a thin UI over Stage 1–5 services. Simulator, detector, metrics, storage, predictor, and policy logic were not reimplemented in dashboard files. The dashboard does not retrain models. Evaluation overlay occupancy is labeled “not available to policy” and is not used for actions, rewards, or persistence.

## Files created or changed, grouped by purpose

### Dashboard application
- `src/smartscan/dashboard/__init__.py` — package export (`LAYOUT_MAX_WIDTH_PX`)
- `src/smartscan/dashboard/layout.py` — 1366×768 layout caps, Okabe–Ito palette
- `src/smartscan/dashboard/services.py` — Stage 1–5 orchestration, overlay-safe runs, doctor, demo bundle, exports
- `src/smartscan/dashboard/plots.py` — replay / bar / paired-delta Plotly figures from typed payloads
- `src/smartscan/dashboard/pages.py` — six required views
- `src/smartscan/dashboard/app.py` — Streamlit chrome, overlay toggle, doctor action
- `configs/dashboard.yaml` — 127.0.0.1, duration/band caps, agile_threat demo profile

### Config, CLI, scripts
- `src/smartscan/config.py` — `DashboardConfig`
- `src/smartscan/cli.py` — `dashboard` and `doctor`; description Stage 1–6
- `scripts/make_demo_data.py` — Stage 1 demo plus matched Stage 6 replay bundle
- `scripts/doctor.py` — Stage 1 path checks plus dashboard `doctor_report()`
- `scripts/dashboard_ui_closeout.py` — Playwright 1366×768 rendered-browser close-out
- `pyproject.toml` — streamlit/plotly main dependencies; coverage omit `app.py` / `pages.py` only
- `.gitignore` — `artifacts/demo/*` with `.gitkeep`
- `artifacts/demo/.gitkeep`
- `artifacts/dashboard_ui/` — viewport screenshots and `closeout.json`

### Tests
- `tests/unit/test_dashboard_services.py` — Stage API use, overlay invariance, honest unavailable/gate cells, path sandbox
- `tests/unit/test_dashboard_plots.py` — metric/unit/denominator/CI payload, overlay traces, 1366 layout constants
- `tests/integration/test_dashboard_app.py` — CLI launch argv, doctor, AppTest smoke (six views, demo load, overlay, missing PPO, doctor)

### Docs
- `docs/BUILD_CONTRACT.md` — Stage 6 public service/CLI contract
- `README.md` — Stage 6 status, `dashboard` / `doctor` commands, coverage line includes `smartscan.dashboard`
- `docs/stage_reports/STAGE_6_REPORT.md` — this report

## Commands executed and actual exit status

| Command | Exit status |
| --- | --- |
| `python -m pip install "streamlit>=1.36" "plotly>=5.22"` | 0 (venv previously lacked them) |
| `ruff check src tests scripts` | 0 |
| `mypy src` | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov=smartscan.metrics --cov=smartscan.storage --cov=smartscan.ml --cov=smartscan.dashboard --cov-fail-under=90` | 0 |
| `python scripts/make_demo_data.py` | 0 |
| `python -m smartscan.cli doctor` | 0 (`ok=true`; alias **candidate**) |
| `python -m smartscan.cli dashboard --host 127.0.0.1 --port 8501` | running (Uvicorn on 127.0.0.1:8501) |
| `python scripts/dashboard_ui_closeout.py` | 0 (`ok=true`, viewport 1366×768) |
| `ruff check src tests scripts` (after UI close-out edits) | 0 |
| `mypy src` (after UI close-out edits) | 0 |
| `pytest tests/unit/test_dashboard_services.py tests/unit/test_dashboard_plots.py tests/integration/test_dashboard_app.py` | 0 (**19 passed**) |

No unrun check is claimed as passed.

## Tests, coverage, acceptance-gate evidence

Final suite (workspace `.venv`, Python 3.11.9):

- **264 passed**, 0 failed
- Combined coverage **rf + data + receiver + metrics + storage + ml + dashboard: 92.78%** (threshold 90%)
- Streamlit **1.62.0**, Plotly **7.0.0**

Dashboard evidence:

- Services call `simulate`, `run_policy_episode`, `evaluate_strategy`, `make_policy`; `GammaPPF` / `ncx2` are absent from `services.py`
- Overlay on/off yields identical action signatures and rewards; occupancy appears only in the replay frame when overlay is on, with “not available to policy”
- Unavailable metrics render **Not available** (never a fabricated 0/win); bars omit unavailable series
- `performance_gate_passed=false` → `highlight_win=false`, alias **candidate**, failed criteria listed
- Missing PPO bundle raises an actionable `SmartScanError`; AppTest run does not traceback
- Unreachable or empty DB does not crash history (upgrade-on-read + error payload)
- Path sandbox rejects `.env` / token paths and files outside `artifacts/`, `data/`, `configs/`
- Export JSON includes schema version, fingerprints, and metric cells; it does not embed `occupied` arrays
- AppTest: default launch, load agile_threat demo, Metrics Compare (candidate warning), Scan Replay, Smart Decision, Run History, Model & Data Lineage, overlay toggle, missing-model PPO run, sidebar doctor
- AppTest expander **Failed criteria (held-out gate)** is present after the close-out layout change

## Rendered-browser close-out (1366×768)

Launched with `python -m smartscan.cli dashboard` on `http://127.0.0.1:8501`. Chromium (Playwright, headless, `device_scale_factor=1`) used viewport **1366×768**, loaded the agile_threat demo, and visited all six views.

Evidence (captured 2026-08-30T10:27:34Z):

| View | Screenshot | horizontalOverflowPx | clipped / overlap |
| --- | --- | --- | --- |
| Configure & Run | `artifacts/dashboard_ui/configure_and_run.png` | 0 | none |
| Scan Replay | `artifacts/dashboard_ui/scan_replay.png` | 0 | none |
| Smart Decision | `artifacts/dashboard_ui/smart_decision.png` | 0 | none |
| Metrics Compare | `artifacts/dashboard_ui/metrics_compare.png` | 0 | none |
| Run History | `artifacts/dashboard_ui/run_history.png` | 0 | none |
| Model & Data Lineage | `artifacts/dashboard_ui/model_and_data_lineage.png` | 0 | none |

Machine-readable log: `artifacts/dashboard_ui/closeout.json` (`ok=true`, `failures=[]`).

Confirmed in the rendered app:

- All six views reachable from the sidebar; no horizontal overflow (`scrollWidth=1366`); no controls outside the viewport; no independent overlapping widgets
- **candidate** + `performance_gate_passed=false — no scheduler win badge` on every view; failed held-out criteria listed in an expander (opened on Metrics Compare)
- **Not available** for missing `p_active` (Smart Decision) and missing forecast metrics (Metrics Compare table + reasons expander)
- Overlay caption **not available to policy** on Scan Replay with overlay on
- Offline: request interceptor aborted non-localhost URLs; **zero** remote requests were attempted (`blocked_non_local=[]`). Streamlit launch now passes `--browser.gatherUsageStats false`

Layout close-out edits made so the laptop viewport actually fits: failed-criteria expander (instead of seven always-on captions), main-block max-width CSS, Streamlit Deploy toolbar hidden, comparison-table cells show **Not available** with reasons in an expander (long reason strings were clipping in 8-column cells).

## Reproducibility

| Item | Value |
| --- | --- |
| Python | 3.11.9 (`.venv`) |
| Dashboard config | `configs/dashboard.yaml` |
| Demo scenario / seed | `agile_threat` / `42` |
| Demo duration / dt | `0.2 s` / `0.001 s` |
| Demo strategies | sequential, random, fixed-priority, reactive, contextual-thompson, ppo |
| Demo truth fingerprint | `db732d9f71deb18c9021528e4517f80d9979504d425ff47cb00a88e75f9d2d70` |
| Stage 1 `stage1_demo.npz` fingerprint | `0a1189f223baa22d3d9823764518a402ef0f0a3832ea5c48fdfca5b118b20c05` |
| Live duration / band caps | `max_duration_s=2.0`, `max_n_bands=16` |
| Host | `127.0.0.1:8501` (`--browser.gatherUsageStats false`) |
| Model dir | `artifacts/models/scheduler_full` |
| Held-out gate | `artifacts/models/held_out_gate.json`, `performance_gate_passed=false` |
| Held-out manifest fingerprint | `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4` (unchanged) |
| Doctor alias | candidate (`performance_gate_passed=False`) |
| Git SHA | none (workspace is not a git repository) |

Launch: `python -m smartscan.cli dashboard` (binds 127.0.0.1, headless Streamlit). Offline demo: `python scripts/make_demo_data.py` then **Load agile_threat demo**.

## Known limitations (not blockers for `implementation_complete`)

- Stage 5 **performance gate remains failed**. Metrics Compare must not be read as a scheduler win. Failed criteria (verbatim from the gate file): AIR vs sequential −0.4595; AIR vs random −0.2857; AIR and event-interception-ratio inferior to fixed-priority; no primary paired delta vs best non-oracle with 95% CI excluding zero; Pfa Newcombe upper 0.00318164; family improvement does not include agile_threat.
- Scan Replay’s SNR subplot sits below the 768 px fold; the page scrolls vertically. Horizontal overflow is 0. Replay speed, step, pause, and overlay controls are fully in view.
- Horizon MC in live dashboard runs uses `mc_rollouts: 8` from `configs/dashboard.yaml` (faster than the Stage 5 train default of 128). Recorded demo replay is the intended large-run path.
- Playwright is a close-out tool (`scripts/dashboard_ui_closeout.py`), not a dashboard runtime dependency.

## Stop condition

Stage 6 UI close-out is done. Stage 7 was not started.

`implementation_complete=true`
