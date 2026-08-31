# Stage 7 report — integration, frozen evidence, offline demo

`implementation_complete`: **true**

`performance_gate_passed`: **false** (frozen held-out rerun; unchanged thresholds and manifest). Alias remains **candidate**. Champion/production were not set. No scheduler-win claim is made.

Stage 7 is integration and packaging. It does not add a new algorithm, change frozen metric definitions, or tune on held-out seeds 1000–1029.

## Files created or changed, grouped by purpose

### Frozen hashes and release package
- `configs/frozen_hashes.json` — Stage 5 precommit SHA-256 / content fingerprint; final evidence refuses drift
- `src/smartscan/release/` — `frozen.py`, `resolve.py` (`best-available` → champion | candidate | contextual_thompson), `benchmark.py`, `demo.py`, `perf.py`, `coverage.py`
- `src/smartscan/cli.py` — `benchmark`, `demo --offline`, `run --strategy best-available`, doctor prints resolved strategy
- `src/smartscan/dashboard/services.py` — public `model_bundle_dir`; `run_experiment(..., track=)`
- `scripts/doctor.py` — prints resolved best-available

### Evidence pack
- `artifacts/benchmark_final/summary.json`, `held_out_gate.json`, `seed_metrics.csv`, `seed_metrics.json`, `comparisons.json`
- `docs/evidence/held_out_gate_summary.json`, `implementation_status.json`, `requirements_coverage.json`, `robustness_matrix.json`
- `artifacts/demo/manifest.json` — matched agile_threat runs plus model `bundle_content_fingerprint` and `truth.npz` SHA-256

### Docs, license, CI
- `README.md` — architecture, mandatory commands, retraining, gate interpretation, v1 extension points
- `docs/METRICS.md`, `docs/ORACLE_BOUNDARY.md`, `docs/MLFLOW.md`, `docs/THIRD_PARTY_NOTICES.md`, `LICENSE`
- `docs/BUILD_CONTRACT.md` — Stage 7 paragraph
- `.github/workflows/ci.yml` — ruff, mypy, pytest tiny fixtures; full bench/train opt-in
- `.gitignore` — benchmark pack, dashboard PNGs; keep `docs/evidence/` and `artifacts/demo/manifest.json`
- `.env.example` — `SMARTSCAN_MODEL_DIR` / `SMARTSCAN_DEMO_DIR`
- `pyproject.toml` — `full_bench` / `full_train` markers
- `docs/stage_reports/STAGE_7_REPORT.md` — this report

### Tests
- `tests/unit/test_release.py` — hash refuse, candidate ≠ champion, coverage gaps, mocked bench, short CPU probe
- `tests/integration/test_stage7_cli.py` — CLI help, doctor resolve lines, demo `--offline`, sequential persist source=explicit

## Commands executed and actual exit status

| Command | Exit status |
| --- | --- |
| `uv lock` | 0 (resolved 154 packages) |
| `uv lock --check` | 0 |
| `ruff check src tests scripts` | 0 |
| `mypy src` | 0 |
| `pytest tests --cov=smartscan --cov-fail-under=85` | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov=smartscan.metrics --cov=smartscan.storage --cov=smartscan.ml --cov=smartscan.dashboard --cov-fail-under=90` | 0 |
| `python -m smartscan.cli doctor` | 0 (`ok=true`; `resolved_source=candidate`; `performance_gate_passed=False`) |
| `python -m smartscan.cli db upgrade` | 0 |
| `python -m smartscan.cli simulate --config configs/demo.yaml` | 0 |
| `python -m smartscan.cli run --config configs/demo.yaml --strategy sequential --persist --track` | 0 (`resolved_source=explicit`) |
| `python -m smartscan.cli run --config configs/demo.yaml --strategy best-available --persist --track` | 0 (`resolved_source=candidate`, strategy `ppo`) |
| `python -m smartscan.cli benchmark --config configs/benchmark_final.yaml --manifest held_out_manifest.json --track` | 0 (`reused_existing_gate=false`, `n_seed_rows=210`, `performance_gate_passed=false`) |
| `python -m smartscan.cli demo --offline` | 0 (`retrained=false`, `downloaded=false`) |
| `python -m smartscan.cli dashboard` | long-running; HTTP 200 at `http://127.0.0.1:8501` (process started as `python -m smartscan.cli dashboard --host 127.0.0.1 --port 8501`) |

No unrun check is claimed as passed. The 60 s / 60_000-step RSS ctypes path was fixed after the first probe returned `peak_rss_bytes=None` (invalid process handle). The demo-profile numbers below are from the corrected `measure_demo_profile(duration_s=60)` on the same machine; held-out seed rows were not recomputed.

## Tests, coverage, acceptance-gate evidence

Workspace `.venv`, Python **3.11.9**, Windows 10.0.26200:

- **283 passed**, **1 skipped** (`full_bench` opt-in), 0 failed
- Overall `smartscan` coverage **91.36%** (gate 85%)
- Critical packages rf+data+receiver+metrics+storage+ml+dashboard **92.79%** (gate 90%)

Acceptance:

- Frozen hashes match Stage 5: manifest content fp `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4`, file SHA-256 `bb3439ddbf23dff9c73b6611049b97ab0f068fd73d52f148fad5f85f44081c83`, `benchmark_final.yaml` SHA-256 `2f8768768279e71444039df273704af278757509cdcf5470ca4e51bfc3fcef8b`
- `--manifest` name mismatch and hash drift refuse final evidence
- `best-available` with a valid PPO bundle and failed gate prints **candidate**, not champion
- Oracle ceiling remains labeled unattainable and is not a deployable alias
- Requirements-coverage and robustness matrix: **0 unexplained gaps** (10 statement needs, 36 robustness cases mapped to existing tests)
- Overlay contract unchanged (Stage 6 tests still pass)

## Held-out rerun (all 30 predeclared pairs)

`reused_existing_gate=false`. Eval wall **177.25 s**. Strategies per pair: sequential, random, fixed-priority, reactive, contextual-thompson, PPO candidate, oracle-ceiling (unattainable). **210** seed rows.

Held-out mean AIR:

| Strategy | Mean AIR |
| --- | --- |
| oracle-ceiling (unattainable) | 23.25 |
| fixed-priority | 14.00 |
| sequential | 9.25 |
| contextual-thompson | 7.75 |
| reactive | 7.08 |
| random | 7.00 |
| PPO candidate | 5.00 |

Failed criteria (unchanged class vs Stage 5):

- AIR vs sequential **-0.4595** < required 0.05
- AIR vs random **-0.2857** < required 0.05
- AIR inferior to fixed-priority by **-0.6429**
- event interception ratio inferior to fixed-priority by **-0.1221**
- no primary paired delta vs best non-oracle has 95% CI excluding zero
- Pfa Newcombe upper **0.00318** > limit 0.001
- family improvement does not hold in at least two families including `agile_threat` (`sparse` true; `agile_threat`/`dense`/`unseen_random`/`tsrd_synthetic` false)

## Demo-profile CPU probe (60 s @ 1 ms = 60_000 steps, 16 bands)

Sequential sparse seed 42:

- wall **1.07 s** (target &lt; 60 s) — within target
- peak working set **256_417_792 bytes** ≈ **0.239 GB** (target &lt; 2 GB) — within target
- 6666 completed decisions

## Reproducibility

- Held-out seeds: 1000–1029 as declared in `configs/held_out_manifest.json` (not subsetted)
- Demo simulate: `configs/demo.yaml` seed 42, `dt_s=0.001`, `duration_s=2.0`, scenario `sparse`
- Offline demo: `configs/dashboard.yaml` agile_threat seed 42, `duration_s=0.2`; truth fingerprint `db732d9f71deb18c9021528e4517f80d9979504d425ff47cb00a88e75f9d2d70`
- Bundle content fingerprint `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746`
- `git_sha`: **null** (this workspace is not a git checkout)
- Packages (provenance): numpy 2.4.6, scipy 1.17.1, torch 2.13.0+cpu, mlflow 3.15.2, streamlit 1.62.0, plotly 7.0.0

## Known limitations

- The smart scheduler did **not** clear the frozen multi-seed gate. The repository is submission-complete as engineering work, not performance-ready.
- Large PPO weights under `artifacts/models/scheduler_full` are gitignored; a fresh clone without that bundle resolves `best-available` to contextual-thompson until the bundle is restored or retrained.
- Default `configs/receiver.yaml` noise (`1.0`) makes sequential `cli run` on `demo.yaml` report near-zero Pd; PPO/dashboard paths use `noise_power_w: 1e-13` as in Stage 5. This is a receiver-config split, not a metric-definition change.
- CI does not download torch-scale artifacts or run the 30-seed eval (`SMARTSCAN_FULL_BENCH=1` is opt-in).
- No blocker for Stage 7 engineering completion. Performance gate remains the Stage 5 limiter.

## Final Streamlit Compatibility Cleanup

UI-only replacement of deprecated Streamlit `use_container_width`. No algorithm, model, metric, training, held-out benchmark, or frozen performance result was changed. Champion remains unset.

### Files changed
- `src/smartscan/dashboard/pages.py` — **5** `use_container_width=True` → `width="stretch"` (replay chart, compare table, AIR bar, paired-delta chart, history table). Zero `use_container_width=False` in this repository.
- `tests/unit/test_release.py` — isolate mocked benchmark writes under `SMARTSCAN_ROOT` so pytest cannot overwrite `artifacts/models/held_out_gate.json`. Not a benchmark rerun.

### Deprecated usages replaced
**5** (all `True` → `width="stretch"`). Project `src/` / `tests/` / `scripts/` now contain **0** `use_container_width` occurrences.

### Commands executed and exit status
| Command | Exit |
| --- | --- |
| `ruff check src tests scripts` | 0 |
| `mypy src` | 0 |
| `pytest tests/unit/test_dashboard_services.py tests/unit/test_dashboard_plots.py tests/integration/test_dashboard_app.py` | 0 (**19 passed**) |
| `pytest tests --cov=smartscan --cov-fail-under=85` | 0 (**283 passed**, 1 skipped, coverage **91.37%**) |
| `python -m smartscan.cli dashboard --host 127.0.0.1 --port 8501` | running; HTTP **200** |
| `python scripts/dashboard_ui_closeout.py` | 0 (`ok=true`, 1366×768, all six views) |

Streamlit server log after exercising all views: **0** `use_container_width` deprecation lines. One Windows `ConnectionResetError` on asyncio pipe shutdown occurred when Playwright closed a connection; the app did not traceback and `closeout.json` `failures=[]`.

### Dashboard launch result
`http://127.0.0.1:8501` loads. Six views reachable: Configure & Run, Scan Replay, Smart Decision, Metrics Compare, Run History, Model & Data Lineage. No horizontal overflow, no clipped controls, no overlapping widgets. Candidate status and failed held-out expander remain visible; no scheduler win badge. Overlay still labeled not available to policy. Requests stayed local (`blocked_non_local=[]`).

### Fingerprints unchanged
- held-out manifest content fp `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4`
- `held_out_manifest.json` SHA-256 `bb3439ddbf23dff9c73b6611049b97ab0f068fd73d52f148fad5f85f44081c83`
- `benchmark_final.yaml` SHA-256 `2f8768768279e71444039df273704af278757509cdcf5470ca4e51bfc3fcef8b`
- gate file `n_rows=210`, PPO mean AIR **5.0**, `performance_gate_passed=false`, alias **candidate**

## Final Submission UI Redesign

Presentation-only upgrade of the Streamlit dashboard for DRDO / SIH judging. **No Stage 8.** Scientific pipeline, PPO weights, frozen hashes, held-out gate, and metric formulas were not modified.

### Files changed
- `src/smartscan/dashboard/ui/` — new presentation modules: `help.py` (`HELP_TEXT`), `styles.py`, `components.py`, `chrome.py` (command bar, tour, pointer runtime), `landing.py` (offline canvas hero + explainer)
- `src/smartscan/dashboard/app.py` — landing-first entry, then control-center sidebar (`view_select` keys unchanged; visible labels via `NAV_LABELS`)
- `src/smartscan/dashboard/pages.py` — six views restyled; widget keys preserved (`load_demo`, `run_experiment`, `overlay_toggle`, `cfg_strategy`, …)
- `src/smartscan/dashboard/layout.py` — defence-tech palette + `NAV_LABELS` (1366×768 caps unchanged)
- `src/smartscan/dashboard/plots.py` — recorded-log scan-position marker and optional Plotly play frames (no new decisions)
- `src/smartscan/dashboard/services.py` — `dashboard_argv` local Streamlit theme flags; `DecisionExplanation.observable_agility_by_band` displays existing `FeatureBuilder.agility.next_scores()` (no new estimator)
- `.streamlit/config.toml` — dark graphite/teal theme, `gatherUsageStats = false`, no remote fonts
- `tests/unit/test_dashboard_ui.py` — help dictionary, offline asset scan, frozen AIR cards, fake-st render wrappers
- `tests/integration/test_dashboard_app.py` — click `enter_control_center` before existing widgets
- `scripts/dashboard_ui_closeout.py` — landing screenshots, CTA, numbered nav labels, cursor help, frozen AIR checks
- `artifacts/dashboard_ui/` — screenshots, `closeout.json`, `fingerprints_before.json`, `fingerprints_after.json`

### UI architecture
Two layers: (1) immersive landing, (2) operational control dashboard with the original six views. Session flag `entered_control_center` gates the layers. Internal radio values remain `Configure & Run`, `Scan Replay`, `Smart Decision`, `Metrics Compare`, `Run History`, `Model & Data Lineage`.

### Landing page
Full-width offline canvas (pseudo-3D spectrum → narrow IBW window → scheduler concept). Copy: SMART SCAN STRATEGY FOR ELECTRONIC WARFARE; OBSERVE → PREDICT → PRIORITIZE → SCAN → EVALUATE; status chips Operational Prototype / SmartScanScheduler v2 / Candidate / Performance gate Not Passed. Animated spectrum-vs-window explainer (~8 s CSS scan). Five-step how-it-works. CTA **ENTER CONTROL CENTER**. Architecture expander. Explicit non-claim that PPO beats baselines.

### Animations
Landing: canvas RF geometry, CSS receiver-window scan, staggered cards. Dashboard: Plotly scan-position play on **recorded** logs, hover elevation via theme, status chips. `prefers-reduced-motion` disables canvas loop and CSS scan. No Streamlit rerun loops.

### Custom cursor
Optional desktop halo injected into the parent document from a same-origin `st.iframe` runtime (no CDN). Expands on interactive elements. Disabled on coarse pointers and reduced motion. Native pointer remains visible.

### Contextual hover-help
Single dictionary `HELP_TEXT` in `smartscan.dashboard.ui.help`. After ~3.5 s dwell, a small tip appears offset from the cursor; it clears on move or click. Streamlit `help=` remains the accessible fallback.

### Dashboard improvements
Command bar: scenario / strategy / seed / Candidate / Gate Failed. Configure grouped SCENARIO / RECEIVER / STRATEGY / EXECUTION with **VALIDATE & RUN**. Scan Replay Play/Pause/Step/speed + timeline on recorded logs. Smart Decision splits OBSERVED / PREDICTED / EVALUATOR-ONLY. Metrics Compare always shows frozen held-out AIR (PPO 5.00, Sequential 9.25, Random 7.00, Fixed Priority 14.00) and delay improvement vs sequential with **Performance gate not passed**. History filters + selected-run details. Lineage flow diagram + fingerprints. Missing metrics render **Not available** plus why. Human-readable errors with expandable technical detail.

### Accessibility
System fonts only. `help=` / ARIA on key widgets. Tips `pointer-events: none`. Reduced-motion path. Native cursor not hidden. Touch devices skip the custom halo.

### Browser verification
Playwright Chromium, viewport **1366×768**, `scripts/dashboard_ui_closeout.py` exit **0**, `ok=true`, `failures=[]`. Landing CTA works. All six views reachable. Charts render. Cursor root present; dwell tip appears and clears on move. No horizontal overflow, no clipped controls, no overlapping widgets, no page/console errors.

### Offline verification
Route interceptor aborted non-local hosts. `blocked_non_local=[]`. CSS/JS scanned for Google Fonts / jsDelivr / unpkg. Theme and canvas are local.

### Screenshots produced
`artifacts/dashboard_ui/landing_hero.png`, `landing_explanation.png`, `configure_and_run.png`, `scan_replay.png`, `smart_decision.png`, `metrics_compare.png`, `run_history.png`, `model_and_data_lineage.png`

### Tests executed and exit codes
| Command | Exit |
| --- | --- |
| `ruff check src tests scripts` | 0 |
| `mypy src` | 0 |
| `pytest tests/unit/test_dashboard_ui.py tests/unit/test_dashboard_plots.py tests/unit/test_dashboard_services.py tests/integration/test_dashboard_app.py` | 0 (**25 passed**) |
| `pytest tests --cov=smartscan --cov-fail-under=85` | 0 (**289 passed**, 1 skipped, coverage **91.27%**) |
| `python -m smartscan.cli dashboard --host 127.0.0.1 --port 8501` | running; HTTP **200** at `http://127.0.0.1:8501` |
| `python scripts/dashboard_ui_closeout.py` | 0 |

Streamlit server log after exercising landing + six views: **0** `use_container_width` lines, **0** `st.components.v1.html` deprecation lines (hero/cursor use `st.iframe`).

### Fingerprints before/after
Identical (`artifacts/dashboard_ui/fingerprints_before.json` == `fingerprints_after.json`):

- held-out manifest content fp `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4`
- `held_out_manifest.json` SHA-256 `bb3439ddbf23dff9c73b6611049b97ab0f068fd73d52f148fad5f85f44081c83`
- `benchmark_final.yaml` SHA-256 `2f8768768279e71444039df273704af278757509cdcf5470ca4e51bfc3fcef8b`
- bundle content fingerprint `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746`
- demo truth fingerprint `db732d9f71deb18c9021528e4517f80d9979504d425ff47cb00a88e75f9d2d70`
- gate `n_rows=210`, PPO AIR **5.0**, sequential **9.25**, random **7.0**, fixed-priority **14.0**, `performance_gate_passed=false`

Stop condition: Stage 7 is complete. Do not begin a later stage.

## Landing page and navigation repair

Presentation-only. Collapsing Streamlit’s sidebar had made Control Center navigation unreachable. The default collapse control is no longer used. **No Stage 8.** No model, algorithm, RF, detector, metric, training, held-out, benchmark, or frozen artifact was changed.

### Navigation
A permanent `#ss-burger` control is injected into the parent document (top-left, always visible). It opens a glass drawer (`#ss-drawer`) with Mission Overview, the six Control Center views, Candidate / Not Passed / Offline, and Quick Guide. ESC, backdrop click, and the burger toggle close the drawer. Streamlit’s sidebar widgets stay mounted (`initial_sidebar_state="expanded"`) but are moved off-canvas so AppTest keys (`view_select`, `enter_control_center`, `load_demo`, …) still exist. Collapse arrows are hidden only after this replacement is in place.

### Landing
Darker first screen (`#05080B`). Offline parent-document canvas (z-index `-1`) draws a frequency–time field and a moving RX/SCAN window. Copy: SMART SCAN; “A receiver cannot listen everywhere at once.”; **ENTER CONTROL CENTER →** injected into `.ss-hero-stage` so it remains in the 1366×768 first viewport (Streamlit’s own button is kept for AppTest but visually parked). Scroll sections: problem, fixed vs dynamic, pipeline, honest Candidate / Not Passed status, Control Center preview. `prefers-reduced-motion` disables reveal/scan motion; the canvas loop pauses when the tab is hidden.

### Browser verification
Playwright Chromium, viewport **1366×768**, `scripts/dashboard_ui_closeout.py` exit **0**, `ok=true`, `failures=[]`. Sequence: hamburger open/close on landing → Enter Control Center → hamburger on all six views → refresh → drawer still opens. `cta_in_first_viewport=true`, `cta_not_covered_by_canvas=true`, `blocked_non_local=[]`, `page_errors=[]`.

### Screenshots
`landing_hero.png`, `landing_problem.png`, `landing_fixed.png`, `landing_pipeline.png`, `landing_status.png`, `landing_cta.png`, `landing_nav_open.png`, plus the six operational views.

### Scientific fingerprints
Unchanged vs `artifacts/dashboard_ui/fingerprints_before.json` / `fingerprints_after.json` (held-out manifest `4603deb9…`, benchmark yaml `2f876876…`, bundle `81751a75…`, demo truth `db732d9f…`, gate `n_rows=210`, PPO AIR **5.0**, `performance_gate_passed=false`, alias **candidate**).
