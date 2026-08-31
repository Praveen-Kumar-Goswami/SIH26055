# Project stability report — SmartScan

Date: 2026-08-31  
Task: repository-wide bug audit, experiment-protocol reconciliation, strategy verification, dashboard consistency.  
**No PPO retraining. No v5. No Champion promotion. No landing-page edits. No metric-formula changes.**

---

## Totals

| Class | Count |
|---|---|
| Bugs discovered (this audit log) | 27 |
| CRITICAL | 3 (BUG-001, BUG-002, BUG-014) — all FIXED |
| HIGH | 8 product + 1 process (BUG-023 coverage) |
| MEDIUM | 10 |
| LOW | 6 |

### Disposition

| Status | Count | IDs |
|---|---|---|
| FIXED | 20 | 001–010, 012, 014–016, 019–022, 027 |
| VERIFIED-OK | 4 | 011, 017, 018, 025 |
| WONTFIX (constraint or leftover) | 2 | 013 (`state["seq"]`), 026 (landing copy frozen) |
| REMAINING | 1 | 023 (combined `--cov-fail-under=90` vs `improve_cycle.py` at 0%) |

**CRITICAL remaining:** 0  
**HIGH remaining (product):** 0  
**HIGH remaining (process):** 1 — package coverage 90% gate, pre-existing untested training module, out of scope

---

## Per-bug fix / test evidence

See `docs/audit/FULL_PROJECT_BUG_AUDIT.md` for full records. Summary:

| ID | Sev | Fixed? | Test evidence |
|---|---|---|---|
| BUG-001 | CRIT | yes | `test_experiment_protocol.py`, Metrics Compare selector, Playwright `periodic_not_recorded` |
| BUG-002 | CRIT | yes | command-bar HTML tests; Playwright command bar groups |
| BUG-003 | HIGH | yes | protocol registry unit tests |
| BUG-004 | HIGH | yes | `comparison_table` tests |
| BUG-005 | HIGH | yes | `frozen_air_cards` + evidence AIR exactness |
| BUG-006 | HIGH | yes | schema pragma + persist matrix |
| BUG-007 | HIGH | yes | `test_release.py`; doctor `resolved_version=v4` |
| BUG-008 | HIGH | yes | Not recorded ≠ 0 in protocol tables |
| BUG-009 | MED | yes | replay reset + AppTest |
| BUG-010 | MED | yes | `test_session_keys_are_unique` |
| BUG-011 | MED | n/a | 7/7 registry tests |
| BUG-012 | MED | yes | v2/v3/v4 fingerprint test |
| BUG-013 | LOW | documented | SESSION_KEYS |
| BUG-014 | CRIT | yes | `require_same_protocol_id` |
| BUG-015 | MED | yes | Smart Decision captions + AppTest |
| BUG-016 | MED | yes | `python -m smartscan.cli doctor` |
| BUG-017 | LOW | reported | doctor orphans (not deleted) |
| BUG-018 | LOW | expected | mlflow_ui non-blocking |
| BUG-019 | HIGH | yes | `test_dashboard_import.py` |
| BUG-020 | MED | yes | history protocol fields |
| BUG-021 | LOW | yes | PHASE_VALIDATING |
| BUG-022 | MED | yes | plot stub + `getattr` |
| BUG-023 | HIGH | no | 90% combined package gate still fails |
| BUG-024 | LOW | partial | Playwright 1366×768 `ok=true` |
| BUG-025 | LOW | honest UI | demo --offline, no retrain |
| BUG-026 | MED | constraint | landing.py untouched |
| BUG-027 | LOW | yes | manifest sha256 fallback |

---

## Quality gates (this pass)

| Gate | Result |
|---|---|
| `uv lock --check` | PASS |
| `ruff check src tests scripts` | PASS |
| `mypy src` | PASS |
| `pytest tests --cov=smartscan --cov-fail-under=85` | PASS (**360 passed**, 1 skipped, **86.72%**) |
| Combined packages `--cov-fail-under=90` | FAIL (**87%**; `ml/improve_cycle.py` 0% — not executed) |
| `python -c "import smartscan.dashboard.app"` | PASS |
| `python -m smartscan.cli doctor` | PASS (`ok=true`) |
| `python -m smartscan.cli demo --offline` | PASS (`retrained=false`) |
| Playwright 1366×768 `scripts/stability_audit_browser.py` | PASS (`failures=[]`) |
| Requirements coverage `n_gaps==0` | PASS (pytest) |

---

## Protocol facts (parsers only; files not rewritten)

| Protocol | Bundle | Seeds | Episode | Sequential AIR | PPO AIR | periodic-intercept | Oracle (evaluator-only) | Gate |
|---|---|---|---|---|---|---|---|---|
| `v2_frozen_gate` | SmartScanScheduler v2 `scheduler_full` | 1000–1029 | 0.4 s | 9.25 | 5.00 | Not recorded | 23.25 | failed (official) |
| `v3_research` | SmartScanScheduler v3 | 8000–8007 | 0.2 s | 7.97 | 3.91 | Not recorded | 15.94 | failed |
| `v4_research` | SmartScanScheduler v4 | 9000–9007 | 0.2 s | 10.00 | 7.97 | Not recorded | 17.97 | failed |

Live dashboard PPO executes **v4 candidate**. Official chips remain **v2_frozen_gate / Not Passed**. Champion **unset**.

Bundle fingerprints (checksums.json `content_fingerprint`):

- v2 `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746`
- v3 `e89adc332b7d0532d08fa4d4d694c1dd42cd253a95f6329f2d983d8fc5b4a82f`
- v4 `a674290744dd6a18f290a2cc248ccd7c9455d77bd5cc0bf4f05a2b33196a9fe7`

---

## Seven-strategy matrix (executed)

| Strategy | Factory | Run | Metrics | Persist | Replay |
|---|---|---|---|---|---|
| sequential | PASS | PASS | PASS | PASS | PASS |
| random | PASS | PASS | PASS | PASS | PASS |
| fixed-priority | PASS | PASS | PASS | PASS | PASS |
| reactive | PASS | PASS | PASS | PASS | PASS |
| contextual-thompson | PASS | PASS | PASS | PASS | PASS |
| periodic-intercept | PASS | PASS | PASS | PASS | PASS |
| ppo | PASS | PASS | PASS | PASS | PASS |

Source: `test_seven_strategy_persist_reload_replay_matrix` and `test_all_public_strategies_dashboard_run_replay_metrics`.

---

## Final acceptance matrix

| Component | Result | How verified |
|---|---|---|
| Strategy registry | PASS | 7 ids, `TOTAL_PUBLIC_STRATEGIES=7` |
| 7 strategy factories | PASS | `make_policy` parametrize |
| periodic-intercept | PASS | factory/run/metrics/persist/replay + UI |
| v2 evidence | PASS | sequential 9.25, ppo 5.00 |
| v3 evidence | PASS | sequential 7.97, ppo 3.91 |
| v4 evidence | PASS | sequential 10.00, ppo 7.97 |
| protocol separation | PASS | selector + `CROSS_PROTOCOL_MESSAGE` |
| model-version resolution | PASS | load v2/v3/v4 fingerprints |
| SQLite linkage | PASS | protocol columns + `check_run_bundle_linkage` |
| MLflow linkage | PASS | doctor `db_mlflow_linkage`; UI optional offline |
| Configure & Run | PASS | AppTest + Playwright |
| Scan Replay | PASS | AppTest + Playwright |
| Smart Decision | PASS | AppTest + Playwright |
| Metrics Compare | PASS | selector + Playwright Not recorded |
| Run History | PASS | AppTest + protocol fields |
| Model & Data Lineage | PASS | AppTest + Playwright |
| offline demo | PASS | `demo --offline` retrained=false |
| dashboard browser test | PASS | Chromium 1366×768, `ok=true` |
| hamburger/navigation | PASS | open/close/refresh, burger on all six views |
| artifact integrity | PASS | checksum OK; orphans listed not deleted |
| ruff | PASS | src, tests, scripts |
| mypy | PASS | `mypy src` |
| pytest | PASS | 360 passed, cov 86.72% ≥ 85 |

The historical combined **90%** package gate was executed and **failed** (pre-existing `improve_cycle.py`). It is not in the table above as a silent pass.

---

## Doctor++ (excerpt)

```
Strategies: 7/7 OK
Active PPO: v4 candidate
Official gate: v2_frozen_gate FAILED
Periodic-intercept: implementation OK
v2 evidence: Not recorded
v3 evidence: Not recorded
v4 evidence: Not recorded
champion_set=false
resolved_source=candidate
resolved_model=SmartScanScheduler
resolved_version=v4
```

---

## Explicit statements

No historical benchmark result was modified during the stability audit.

No AIR result from one protocol was treated as directly comparable to an AIR result from a different protocol.

periodic-intercept historical values remain Not Recorded where the strategy was absent from that protocol.
