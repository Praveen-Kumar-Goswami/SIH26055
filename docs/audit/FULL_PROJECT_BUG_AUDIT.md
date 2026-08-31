# Full project bug audit — SmartScan stability pass

Date: 2026-08-31  
Scope: repository-wide protocol, strategy, dashboard, storage, and evidence consistency.  
Constraints honoured: no PPO retraining, no v5, no hyperparameter tuning, no landing-page edits, no scientific metric-formula changes, no rewrite of frozen evidence files.

Status values: `FIXED` | `WONTFIX` | `REMAINING` | `VERIFIED-OK`

---

## BUG-001

| Field | Value |
|---|---|
| ID | BUG-001 |
| Severity | CRITICAL |
| File | `src/smartscan/dashboard/pages.py`, `src/smartscan/dashboard/services.py` |
| Component | Metrics Compare |
| Description | Metrics Compare mixed v2 frozen held-out AIR with v3/v4 research AIR in one ranking table. Judges could treat v2 PPO 5.00 and v4 PPO 7.97 as a single leaderboard. |
| Reproduction | Open Metrics Compare with the previous three-column AIR table. |
| Root cause | No experiment-protocol object. UI concatenated independent evidence JSON files. |
| Fix | `ExperimentProtocol` registry; Metrics Compare **Evidence set / protocol** selector switches the entire dataset. Cross-protocol pairing raises `CROSS_PROTOCOL_MESSAGE`. |
| Test added | `tests/unit/test_experiment_protocol.py`, `test_recorded_air_evals_match_published_v3_v4`, `test_comparison_table_refuses_cross_protocol_pairing` |
| Status | FIXED |

## BUG-002

| Field | Value |
|---|---|
| ID | BUG-002 |
| Severity | CRITICAL |
| File | `src/smartscan/dashboard/ui/chrome.py`, `src/smartscan/dashboard/ui/components.py` |
| Component | Top status / command bar |
| Description | A generic Model/Gate chip made “Gate Failed” look like the current sequential/random run crashed. Live PPO v4 and official v2 gate were one ambiguous “model”. |
| Reproduction | Run sequential; read command bar Model/Gate chips. |
| Root cause | One `model` label served both `active_model_bundle` and `gate_evidence_bundle`. |
| Fix | Command bar groups: Current run / Active PPO model (v4 candidate) / Official frozen gate (`v2_frozen_gate`, Not Passed). `dashboard/identity.py` keeps the two roles apart. |
| Test added | `tests/unit/test_dashboard_ui.py` command-bar HTML assertions; identity test in `test_dashboard_config_loads_v4_live_path` |
| Status | FIXED |

## BUG-003

| Field | Value |
|---|---|
| ID | BUG-003 |
| Severity | HIGH |
| File | (missing) now `src/smartscan/experiment_protocol.py` |
| Component | Experiment protocol |
| Description | Protocol identity (seeds, episode length, bundle, purpose, frozen/gate flags) was duplicated in UI copy and comments, not a single contract. |
| Reproduction | Grep dashboard for “v2 held-out”, “v3”, “v4”, “0.4 s”, “9000”. |
| Root cause | No authoritative `ExperimentProtocol`. |
| Fix | Frozen registry: `v2_frozen_gate`, `v3_research`, `v4_research`, `live_session`. Historical files not renamed. |
| Test added | `tests/unit/test_experiment_protocol.py` |
| Status | FIXED |

## BUG-004

| Field | Value |
|---|---|
| ID | BUG-004 |
| Severity | HIGH |
| File | `src/smartscan/dashboard/services.py` `comparison_table` |
| Component | Live session metrics |
| Description | Live-session comparison inherited frozen-gate `highlight_win` / `performance_gate_passed`, so a demo run could look like the official gate. |
| Reproduction | `comparison_table(live_results)` previously surfaced gate flags. |
| Root cause | Gate JSON mixed into the live compare payload. |
| Fix | Live table always `highlight_win=False`, `performance_gate_passed=False`, `metric_source=LIVE RUN`. Paired stats require matching protocol/duration/dt. |
| Test added | `test_comparison_table_and_export`, `test_comparison_table_refuses_cross_protocol_pairing` |
| Status | FIXED |

## BUG-005

| Field | Value |
|---|---|
| ID | BUG-005 |
| Severity | HIGH |
| File | `src/smartscan/dashboard/ui/components.py` `frozen_air_cards` |
| Component | Metrics labeling |
| Description | PPO AIR 5.00/3.91/7.97 could appear without naming the protocol. |
| Reproduction | Frozen AIR chips labeled “PPO v2” only. |
| Root cause | Cards were v2-only and unlabeled for research protocols. |
| Fix | Labels include protocol id, e.g. `PPO v2 (v2_frozen_gate)`. Values come from evidence JSON via `protocol_air_table`. |
| Test added | `test_frozen_air_cards_show_held_out_means`, evidence parser tests |
| Status | FIXED |

## BUG-006

| Field | Value |
|---|---|
| ID | BUG-006 |
| Severity | HIGH |
| File | `src/smartscan/storage/models.py`, `repositories.py`, `db.py` |
| Component | Run history / SQLite |
| Description | Persisted runs lacked `protocol_id`, `model_version`, `bundle_fingerprint`, `duration_s`. History could not tell live_session from a frozen protocol. |
| Reproduction | `PRAGMA table_info(runs)` on a pre-audit DB. |
| Root cause | Schema never stored evaluation-protocol linkage. |
| Fix | Nullable columns + `ensure_run_protocol_columns` after Alembic. New writes use `live_session` (or inferred id only when seed+duration uniquely match). Unknown historical rows: `legacy_unknown`, no guessing. |
| Test added | `tests/unit/test_storage_schema.py` column assertions; persist matrix |
| Status | FIXED |

## BUG-007

| Field | Value |
|---|---|
| ID | BUG-007 |
| Severity | HIGH |
| File | `src/smartscan/release/resolve.py` |
| Component | best-available |
| Description | `best-available` could be read as Champion. `resolved_version` was a raw manifest string (`9`, `4.0.0-candidate`). |
| Reproduction | `python -m smartscan.cli doctor` before the audit. |
| Root cause | Version field was manifest text; Champion path unused but naming was unclear. |
| Fix | `resolved_source=candidate`, `resolved_model=SmartScanScheduler`, `resolved_version=v4`. Champion only if frozen gate passed (it has not). |
| Test added | `tests/unit/test_release.py` |
| Status | FIXED |

## BUG-008

| Field | Value |
|---|---|
| ID | BUG-008 |
| Severity | HIGH |
| File | `src/smartscan/dashboard/pages.py`, `experiment_protocol.py` |
| Component | periodic-intercept evidence |
| Description | Missing historical AIR could render as `Not available` or `0`, implying a failed evaluation. v2/v3/v4 pair sets never included periodic-intercept. |
| Reproduction | Metrics Compare v2 column for periodic-intercept. |
| Root cause | Missing key treated like any other strategy. |
| Fix | `NOT_RECORDED` / “Not recorded” for `missing_strategy_ids`. Never `0`. Not retrofitted into frozen JSON. |
| Test added | `test_v2_v3_v4_evidence_air_exact_and_periodic_not_recorded` |
| Status | FIXED |

## BUG-009

| Field | Value |
|---|---|
| ID | BUG-009 |
| Severity | MEDIUM |
| File | `src/smartscan/dashboard/pages.py` `render_replay` |
| Component | Scan Replay |
| Description | Switching replay strategy could keep old step cursor, play state, and decision index. |
| Reproduction | sequential → PPO → random without resetting the step slider. |
| Root cause | Widget keys survived across strategy changes. |
| Fix | `replay_strategy_seen`; reset `replay_step`, `replay_playing`, `dec_index` when the strategy changes. |
| Test added | AppTest replay path; session-key contract in `session.py` |
| Status | FIXED |

## BUG-010

| Field | Value |
|---|---|
| ID | BUG-010 |
| Severity | MEDIUM |
| File | `src/smartscan/dashboard/session.py`, `pages.py` |
| Component | Configure & Run state machine |
| Description | Primary chrome could imply Demo loaded and RUN COMPLETE at once. |
| Reproduction | Load demo then Validate & Run; command bar vs status widgets. |
| Root cause | `run_status` set independently of a phase enum. |
| Fix | Phases EMPTY / DEMO_LOADED / VALIDATING / RUNNING / COMPLETE / ERROR. `set_phase` is the only writer of primary `run_status`. |
| Test added | `test_session_keys_are_unique` |
| Status | FIXED |

## BUG-011

| Field | Value |
|---|---|
| ID | BUG-011 |
| Severity | MEDIUM |
| File | `src/smartscan/ml/strategy_registry.py`, `ml/policies.py` |
| Component | Strategy registry |
| Description | Risk of a second public strategy list drifting from CLI/dashboard/factory. |
| Reproduction | Compare `DEMO_STRATEGIES`, `PUBLIC_STRATEGIES`, `make_policy` keys. |
| Root cause | Historical Stage-2 `make_schedule` subset vs live `make_policy`. |
| Fix | Canonical registry remains `strategy_registry.py` (exactly 7). `policies.py` re-exports. Held-out baselines stay 5 names (no periodic-intercept in frozen gate set). |
| Test added | `tests/unit/test_strategy_audit.py` |
| Status | VERIFIED-OK (single registry; subset for frozen gate is intentional) |

## BUG-012

| Field | Value |
|---|---|
| ID | BUG-012 |
| Severity | MEDIUM |
| File | `src/smartscan/experiment_protocol.py` `generation_from_bundle_path` |
| Component | Model resolution |
| Description | Generation tag was inferred from directory name (`scheduler_v4` / `scheduler_full`). Wrong folder could load the wrong weights if checksums were skipped. |
| Reproduction | Point `SMARTSCAN_MODEL_DIR` at another generation’s directory. |
| Root cause | Path heuristic plus separate checksum files. |
| Fix | `inspect_bundle_dir` / `assert_bundle_generation` verify checksums. Fingerprints: v2 `81751a75…`, v3 `e89adc33…`, v4 `a6742907…`. `check_run_bundle_linkage` errors if a run’s version disagrees with a known fingerprint. |
| Test added | `test_load_v2_v3_v4_fingerprints_are_distinct` |
| Status | FIXED |

## BUG-013

| Field | Value |
|---|---|
| ID | BUG-013 |
| Severity | LOW |
| File | `src/smartscan/dashboard/session.py` |
| Component | Session state |
| Description | Legacy `state["seq"]` still written on demo load, unused by replay. |
| Reproduction | Load demo; inspect `st.session_state.smartscan["seq"]`. |
| Root cause | Earlier sequential-vs-PPO pairing. |
| Fix | Documented as unused by replay; not deleted (avoid breaking old session blobs). |
| Test added | SESSION_KEYS documentation |
| Status | WONTFIX (documented; not a user-visible mix-up) |

## BUG-014

| Field | Value |
|---|---|
| ID | BUG-014 |
| Severity | CRITICAL |
| File | `src/smartscan/experiment_protocol.py` `require_same_protocol_id` |
| Component | Statistics |
| Description | Accidental paired ΔAIR / ranking across protocols. |
| Reproduction | Compare v2 PPO 5.00 vs v4 PPO 7.97 as “+59%”. |
| Root cause | Same metric name, different seeds/duration/manifest. |
| Fix | `protocols_comparable` / `require_same_protocol_id`. Live compare refuses mixed protocol_id, duration, or dt. |
| Test added | `test_cross_protocol_comparison_is_refused` |
| Status | FIXED |

## BUG-015

| Field | Value |
|---|---|
| ID | BUG-015 |
| Severity | MEDIUM |
| File | `src/smartscan/dashboard/pages.py` `render_decision` |
| Component | Smart Decision |
| Description | Replaying sequential could be read as a PPO explanation because the active bundle is always v4. |
| Reproduction | Replay sequential; read PREDICTED panel. |
| Root cause | No caption separating run strategy from active PPO bundle. |
| Fix | Explicit captions: current run strategy vs active PPO bundle; non-PPO note that predicted fields are from that strategy’s log. |
| Test added | AppTest Smart Decision captions; strategy matrix `explain_decision` |
| Status | FIXED |

## BUG-016

| Field | Value |
|---|---|
| ID | BUG-016 |
| Severity | MEDIUM |
| File | `src/smartscan/cli.py` `_cmd_doctor`, `services.doctor_report` |
| Component | CLI doctor |
| Description | Doctor did not report strategy count, live vs gate identity, protocol evidence, or orphan artifacts. |
| Reproduction | `python -m smartscan.cli doctor` before this pass. |
| Root cause | Doctor was DB/MLflow/bundle presence only. |
| Fix | Doctor++: 7/7 strategies, active v4 candidate, official `v2_frozen_gate FAILED`, periodic-intercept implementation OK / evidence Not recorded, distinct fingerprints, integrity, orphans listed not deleted. |
| Test added | `test_cli_doctor_runs`, `test_doctor_does_not_crash_without_mlflow_ui` |
| Status | FIXED |

## BUG-017

| Field | Value |
|---|---|
| ID | BUG-017 |
| Severity | LOW |
| File | `artifacts/models/` |
| Component | Artifact store |
| Description | Extra directories `cts_smoke`, `predictor_smoke`, `scheduler_smoke`, `.gitkeep` are not production bundles. |
| Reproduction | `python -m smartscan.cli doctor` orphan line. |
| Root cause | Smoke/dev leftovers. |
| Fix | Reported only. **Not deleted.** |
| Test added | `artifact_integrity_report` in doctor |
| Status | VERIFIED-OK (warning only) |

## BUG-018

| Field | Value |
|---|---|
| ID | BUG-018 |
| Severity | LOW |
| File | doctor `mlflow_ui` check |
| Component | MLflow UI |
| Description | MLflow UI is not reachable unless `mlflow serve` is running. Tracking DB still exists. |
| Reproduction | doctor `mlflow_ui ok=false` |
| Root cause | Optional local UI process. |
| Fix | Non-blocking doctor check. Domain↔fingerprint linkage still validated. |
| Test added | `test_doctor_does_not_crash_without_mlflow_ui` |
| Status | VERIFIED-OK (expected offline) |

## BUG-019

| Field | Value |
|---|---|
| ID | BUG-019 |
| Severity | HIGH |
| File | dashboard imports (`PERIODIC_INTERCEPT_STRATEGY`, historical IndentationError) |
| Component | Dashboard import |
| Description | Prior sessions crashed on `IndentationError` / missing `PERIODIC_INTERCEPT_STRATEGY` import. |
| Reproduction | `python -c "import smartscan.dashboard.app"` |
| Root cause | Registry split; syntax errors in pages. |
| Fix | Canonical import from `strategy_registry`; import smoke test. |
| Test added | `tests/unit/test_dashboard_import.py` |
| Status | FIXED |

## BUG-020

| Field | Value |
|---|---|
| ID | BUG-020 |
| Severity | MEDIUM |
| File | `src/smartscan/dashboard/pages.py` `render_history` |
| Component | Run History |
| Description | History UI did not show or filter `protocol_id`. |
| Reproduction | Persist a live run; history table had no protocol column. |
| Root cause | `list_history` omitted protocol fields. |
| Fix | `protocol_id`, `model_version`, `bundle_fingerprint`, `duration_s`, `receiver_config_hash` in history; protocol filter dropdown. |
| Test added | persist/reload matrix; schema tests |
| Status | FIXED |

## BUG-021

| Field | Value |
|---|---|
| ID | BUG-021 |
| Severity | LOW |
| File | `src/smartscan/dashboard/session.py` |
| Component | Configure state |
| Description | `PHASE_VALIDATING` was defined and unused. |
| Reproduction | Code search. |
| Root cause | Incomplete state machine. |
| Fix | Set VALIDATING then RUNNING on Validate & Run. |
| Test added | session phase test |
| Status | FIXED |

## BUG-022

| Field | Value |
|---|---|
| ID | BUG-022 |
| Severity | MEDIUM |
| File | `src/smartscan/dashboard/services.py` duck-typed `comparison_table` |
| Component | Plots / compare |
| Description | `comparison_table` assumed `protocol_id`/`duration_s`/`dt_s` on every row object. Plot unit tests use stubs and crashed. |
| Reproduction | `test_plot_payload_requires_all_metrics_strategies_and_ci` |
| Root cause | New fields without `getattr` defaults. |
| Fix | `getattr(..., None or 0)` for protocol/duration/dt. |
| Test added | existing plot test now passes |
| Status | FIXED |

## BUG-023

| Field | Value |
|---|---|
| ID | BUG-023 |
| Severity | HIGH (process / coverage gate) |
| File | `src/smartscan/ml/improve_cycle.py` |
| Component | Quality gates |
| Description | Combined package coverage `rf+data+receiver+metrics+storage+ml+dashboard --cov-fail-under=90` is **87%**. `improve_cycle.py` is 0% (v3/v4 training orchestration). This audit forbids running that training. |
| Reproduction | `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov=smartscan.metrics --cov=smartscan.storage --cov=smartscan.ml --cov=smartscan.dashboard --cov-fail-under=90` |
| Root cause | Large untested training module; coverage omit list does not include it. Gate not lowered. |
| Fix | None in this task (would require executing/training code). Primary gate `pytest tests --cov=smartscan --cov-fail-under=85` **passes at 86.72%**. |
| Test added | n/a |
| Status | REMAINING (pre-existing; out of scope) |

## BUG-024

| Field | Value |
|---|---|
| ID | BUG-024 |
| Severity | LOW |
| File | `scripts/stability_audit_browser.py` |
| Component | Browser click matrix |
| Description | Playwright verified landing, hamburger open/close/refresh, six views, demo load, Metrics Compare protocol banner / Not recorded, command bar groups, no traceback. It did not click every slider, seed, speed, step, overlay, and history filter combination. |
| Reproduction | Compare Phase 30 list vs `artifacts/stability_audit_browser.json`. |
| Root cause | Time-bounded audit script. |
| Fix | Main judge paths covered; remaining clicks are AppTest/widget-key covered in pytest. |
| Test added | `scripts/stability_audit_browser.py`; `tests/integration/test_dashboard_app.py` |
| Status | VERIFIED-OK for six views + hamburger; incomplete vs an exhaustive click matrix |

## BUG-025

| Field | Value |
|---|---|
| ID | BUG-025 |
| Severity | LOW |
| File | `artifacts/demo/` |
| Component | Offline demo |
| Description | Recorded demo bundle may omit periodic-intercept (and live v4 PPO vs historical v2 replay). Configure warns and asks Validate & Run. |
| Reproduction | Load agile_threat demo; warning if strategies missing. |
| Root cause | Demo artifacts frozen earlier; this audit does not rebuild a new official benchmark. |
| Fix | UI warning already present. `demo --offline` does not retrain. |
| Test added | configure missing-strategy warning (existing) |
| Status | VERIFIED-OK (honest warning; no fabricated demo AIR) |

## BUG-026

| Field | Value |
|---|---|
| ID | BUG-026 |
| Severity | MEDIUM |
| File | `src/smartscan/dashboard/ui/landing.py` |
| Component | Landing chips |
| Description | Landing still says “v2 held-out not passed” via `render_gate_status_html`. That is intentional: **landing must not be edited** in this task. Control-center command bar uses the new wording. |
| Reproduction | Introduction page PERFORMANCE GATE chip. |
| Root cause | Constraint: do not modify landing. |
| Fix | None (constraint). Control center is unambiguous. |
| Test added | `test_nav_keys_preserved_and_tour_is_short` still expects landing chip text |
| Status | WONTFIX (explicit constraint) |

## BUG-027

| Field | Value |
|---|---|
| ID | BUG-027 |
| Severity | LOW |
| File | `src/smartscan/experiment_protocol.py` `fingerprint_field("scenario_manifest_fingerprint")` |
| Component | Protocol fingerprints |
| Description | `configs/held_out_manifest.json` has no `content_fingerprint` key. Compatibility used a missing field and compared `None == None` across protocols until fixed. |
| Reproduction | `v2.fingerprint_field("scenario_manifest_fingerprint")` returned None. |
| Root cause | Historical manifest schema. |
| Fix | Fall back to `sha256_file` of the manifest. File contents not rewritten. |
| Test added | fingerprint_field assertions |
| Status | FIXED |

---

## Search notes (Phase 1)

| Token | Result |
|---|---|
| TODO / FIXME / HACK | No outstanding product TODOs in `src/smartscan` for this audit path |
| NotImplemented | `src/smartscan/rf/emitters.py` abstract emitter hook only |
| periodic-intercept / PUBLIC_STRATEGIES / STRATEGY_REGISTRY / make_policy | Canonical in `strategy_registry.py` + `policies.make_policy` |
| performance_gate / scheduler_full / held_out | Frozen v2 evidence; unread as live model |
| v2 / v3 / v4 / candidate / champion | Separated: live v4 candidate, gate v2 failed, champion unset |
| Hardcoded AIR 5.00 / 9.25 / 7.97 / 3.91 / 14.00 / 8.44 in `src/` | **None** (readers parse evidence JSON) |

## Evidence files (unchanged)

- `artifacts/models/held_out_gate.json` (v2)
- `artifacts/ml_improve/fresh_test_gate.json` (v3)
- `artifacts/ml_improve/fresh_test_v4_gate.json` (v4)
- `configs/held_out_manifest.json`, `configs/fresh_test_manifest.json`, `configs/fresh_test_v4_manifest.json`
- `configs/frozen_hashes.json`

No historical AIR row was edited.
