# Final pre-fix snapshot

Captured: 2026-08-31 before the SIH26055 completion pass. No code was changed before this file was written.

## Environment

| Item | Value |
|---|---|
| Python | 3.11.9 |
| OS | Windows 10 (win32 10.0.26200) |
| Project root | local working tree `SIH` |
| Git | **not initialized** (no `.git`) |
| GitHub `Praveen-Kumar-Goswami/SIH26055` | **does not exist** |
| `gh auth` | logged in as `Praveen-Kumar-Goswami` (https, `repo` scope) |

## Lockfile

| File | SHA-256 |
|---|---|
| `uv.lock` | `963c937790bd1a0496b7749bb1a1e64be2d435aec47994ba4c9432e4ca88d7b1` |

## Frozen config fingerprints (`configs/frozen_hashes.json`)

| Key | Value |
|---|---|
| held_out_manifest_content_fingerprint | `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4` |
| held_out_manifest_sha256 | `bb3439ddbf23dff9c73b6611049b97ab0f068fd73d52f148fad5f85f44081c83` |
| benchmark_final_yaml_sha256 | `2f8768768279e71444039df273704af278757509cdcf5470ca4e51bfc3fcef8b` |

## Model bundles (content_fingerprint)

| Generation | Path | Fingerprint |
|---|---|---|
| v2 (official gate evidence) | `artifacts/models/scheduler_full` | `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746` |
| v3 (research) | `artifacts/models/scheduler_v3` | `e89adc332b7d0532d08fa4d4d694c1dd42cd253a95f6329f2d983d8fc5b4a82f` |
| v4 (live PPO) | `artifacts/models/scheduler_v4` | `a674290744dd6a18f290a2cc248ccd7c9455d77bd5cc0bf4f05a2b33196a9fe7` |

Dashboard `configs/dashboard.yaml`: `model_dir=artifacts/models/scheduler_v4`, `gate_path=artifacts/models/held_out_gate.json`.

Largest bundle file: v2 `ppo_policy.pt` ≈ 1.19 MB. No 70 GB corpus in tree.

## Historical evidence (not to rewrite)

| Protocol | Evidence file | `performance_gate_passed` |
|---|---|---|
| v2_frozen_gate | `artifacts/models/held_out_gate.json` | **false** |
| v3_research | `artifacts/ml_improve/fresh_test_gate.json` | **false** |
| v4_research | `artifacts/ml_improve/fresh_test_v4_gate.json` | **false** |

Champion: unset.

## Demo artifacts (pre-fix)

`artifacts/demo/manifest.json` lists `truth.npz` SHA `c850acc9…` and strategies sequential, random, fixed-priority, reactive, contextual-thompson, ppo.

**On disk:** metrics JSON + manifest + `.gitkeep`. **`truth.npz` and strategy `*.npz` logs are missing.** `demo --offline` does not rebuild when the manifest exists. Load demo would fail on a fresh tree.

## Storage locations (local, gitignored)

| Store | Path |
|---|---|
| Domain SQLite | `data/smartscan.db` |
| MLflow tracking | `data/mlflow.db` |
| MLflow artifacts | `artifacts/mlflow/` |
| Domain artifact store | `artifacts/store/` |

## Public strategies

```
sequential, random, fixed-priority, reactive, contextual-thompson, periodic-intercept, ppo
TOTAL_PUBLIC_STRATEGIES = 7
```

Registry: `src/smartscan/ml/strategy_registry.py`.

## Tests (pre-fix last known)

| Item | Value |
|---|---|
| Test modules (`test_*.py`) | 45 |
| Last pytest | 360 passed, 1 skipped, coverage 86.72% (`--cov-fail-under=85`) |

## `.gitignore` risk

`artifacts/models/*`, `artifacts/demo/*` (except manifest), and `artifacts/benchmark_final/*` are ignored. A GitHub clone would lack PPO weights and frozen gate JSON. `.env.example` still comments `SMARTSCAN_MODEL_DIR=artifacts/models/scheduler_full` (v2), which disagrees with live v4.

## Scientific truth preserved

- No PPO retrain in this pass
- No v5
- No Champion promotion
- `performance_gate_passed=false` on official v2 gate
