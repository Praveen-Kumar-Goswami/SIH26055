# Final bug register — SIH26055 completion pass

Captured after the pre-fix snapshot (`docs/final/FINAL_PRE_FIX_SNAPSHOT.md`). Historical v2/v3/v4 AIR, gate booleans, and frozen hashes were not edited.

Severity: CRITICAL / HIGH / MEDIUM / LOW.

---

## This pass (completion / GitHub handoff)

### F-01

| Field | Value |
|---|---|
| Severity | HIGH |
| Component | Repository hygiene |
| File | `.gitignore` |
| Symptom | `artifacts/models/*`, `artifacts/demo/*` (except manifest), and `artifacts/benchmark_final/*` were ignored. A clone could not load live PPO v4, frozen v2 gate JSON, or demo recordings. |
| Reproduction | `git check-ignore artifacts/models/scheduler_v4/ppo_policy.pt` would ignore the file. |
| Root cause | Stage-7 gitignore treated all checkpoints as too large. Bundles are ~0.5–1.2 MB. |
| Fix | Un-ignore `scheduler_full`, `scheduler_v3`, `scheduler_v4`, `held_out_gate.json`, demo files, and benchmark JSON/CSV. Keep DBs, MLflow/store, smoke/training datasets ignored. |
| Regression test | Post-commit `git ls-files` includes `artifacts/models/scheduler_v4/ppo_policy.pt` and excludes `data/smartscan.db`. |
| Final status | **FIXED** |

### F-02

| Field | Value |
|---|---|
| Severity | HIGH |
| Component | Offline demo / dashboard Load demo |
| File | `src/smartscan/release/demo.py`, `src/smartscan/dashboard/services.py` |
| Symptom | `artifacts/demo/manifest.json` listed `truth.npz` but the npz logs were absent. `demo --offline` skipped rebuild when the manifest existed. `load_demo_bundle` would raise on missing truth. |
| Reproduction | Delete `truth.npz`, keep `manifest.json`, run Load demo or `demo --offline`. |
| Root cause | Completeness was defined as “manifest exists”, not “matched recordings exist”. |
| Fix | `demo_bundle_is_complete()` requires manifest + `truth.npz` + each listed `{strategy}.npz`. Incomplete trees rebuild. Loaded demo results carry `protocol_id=live_session`. |
| Regression test | `test_load_demo_bundle_rebuilds_when_truth_missing` |
| Final status | **FIXED** |

### F-03

| Field | Value |
|---|---|
| Severity | MEDIUM |
| Component | Config example |
| File | `.env.example` |
| Symptom | Commented `SMARTSCAN_MODEL_DIR` still pointed at `scheduler_full` (v2), which is official gate evidence, not live weights. |
| Reproduction | Read `.env.example`. |
| Root cause | Dashboard live path moved to v4; example comment was not updated. |
| Fix | Comment now points at `scheduler_v4` and states v2 remains gate evidence. |
| Regression test | File review (no runtime test). |
| Final status | **FIXED** |

### F-04

| Field | Value |
|---|---|
| Severity | HIGH |
| Component | Submission docs |
| File | `README.md`, `docs/BUILD_CONTRACT.md`, `THIRD_PARTY_NOTICES.md` |
| Symptom | README still said checkpoints were gitignored and did not state seven public strategies, live v4 vs official v2 gate, or protocol non-comparability. |
| Reproduction | Read README “Known limitations”. |
| Root cause | Docs lagged the stability-audit identity split. |
| Fix | README and BUILD_CONTRACT current-state section updated. Root `THIRD_PARTY_NOTICES.md` added. |
| Regression test | Manual review against scientific truth (`performance_gate_passed=false`, Champion unset). |
| Final status | **FIXED** |

### F-06

| Field | Value |
|---|---|
| Severity | HIGH |
| Component | Configure & Run / demo caption |
| File | `src/smartscan/dashboard/pages.py` |
| Symptom | After regenerating demo logs with live v4, the UI still said “Recorded demo PPO is a historical v2 replay.” |
| Reproduction | Load agile_threat demo; read caption under Load demo. |
| Root cause | Caption described the previous gitignored incomplete bundle, not the rebuilt live_session demo. |
| Fix | Caption now states demo PPO is live_session v4 candidate, not the official v2 gate. |
| Regression test | Browser QA reads body after Load demo (no “historical v2 replay”). |
| Final status | **FIXED** |

### F-05

| Field | Value |
|---|---|
| Severity | LOW |
| Component | Historical research JSON |
| File | `artifacts/ml_improve/fresh_test_gate.json`, `fresh_test_v4_gate.json` |
| Symptom | `bundle_dir` stores an absolute Windows path from the original research machine. |
| Reproduction | Open those JSON files. |
| Root cause | Research export recorded local paths. |
| Fix | **Not applied.** Rewriting those files would alter historical evidence bytes. AIR and `performance_gate_passed` are left unchanged. Documented as a limitation. |
| Regression test | n/a |
| Final status | **WONTFIX (preserve evidence)** |

---

## Prior stability pass (already in tree; not reopened)

These were confirmed fixed before this completion pass. See `docs/audit/FULL_PROJECT_BUG_AUDIT.md`.

| ID | Severity | Summary | Status |
|---|---|---|---|
| A-01..A-n | HIGH | Protocol mixing, live vs gate identity, periodic-intercept registry, Metrics Compare 0 vs Not recorded, header strategy leakage, session phase contradictions | **FIXED** (prior pass) |

No CRITICAL defects were open at the start of this pass (app imported, tests 360 passed).

---

## Remaining after this pass

| Severity | Remaining | Notes |
|---|---|---|
| CRITICAL | 0 | |
| HIGH | 0 | after F-01, F-02, F-04, F-06 |
| MEDIUM | 0 open | F-03 fixed |
| LOW | 1 documented | F-05 absolute paths in historical JSON |

`CRITICAL_BUGS_REMAINING = 0`  
`HIGH_BUGS_REMAINING = 0`
