# Stage 5 report — observable prediction and smart scheduler

`implementation_complete`: **true**

`performance_gate_passed`: **false**

Full-budget PPO (`configs/train_full.yaml`, 200k timesteps) is registered as **SmartScanScheduler v2 alias candidate** only. Champion/production were not set. No superiority claim is made.

Smoke PPO (256 steps) remains historical; it is not the evaluated policy. The frozen held-out manifest was not regenerated. Thresholds in `configs/benchmark_final.yaml` were not changed.

## Files created or changed, grouped by purpose

### Frozen-contract extensions (compatible; Stages 1–4 interfaces preserved)
- `src/smartscan/types.py` — `ORACLE_INFO_PREFIX`, optional `DecisionRow` reward/forecast fields
- `src/smartscan/receiver/schedules.py` — last-command outcome fields on `ScheduleView`
- `src/smartscan/receiver/logs.py` — episode-level horizon forecast fields on `DecisionLog`
- `src/smartscan/receiver/scanner.py` — `ReceiverEngine` for command-by-command policies
- `src/smartscan/config.py` — `RewardWeights`, `ScenarioSeedSpec`, `TrainConfig` (`ppo_ent_coef`, `ppo_net_arch`, `eval_cadence`, `early_stopping_patience`), `BenchmarkConfig`
- `src/smartscan/metrics/statistics.py` — `newcombe_diff_upper()`
- `src/smartscan/storage/pipeline.py` — persist tries Stage 2 `make_schedule`, then Stage 5 `make_policy`
- `src/smartscan/cli.py` — `collect`, `train-predictor`, `train-contextual-bandit`, `train-scheduler`, `evaluate`, `models promote`

### Observable ML core
- `src/smartscan/ml/observable.py`, `features.py`, `periodicity.py`, `novelty.py`, `reward.py`, `actions.py`, `calibrate.py`, `predictor.py` (`BuilderBackedHazardPredictor`), `forecast.py`, `dataset.py`

### Environment, policies, lineage (this cycle)
- `src/smartscan/ml/env.py` — cycles frozen train/val `(scenario, seed)` catalogs; optional frozen observation stats; `record_forecast=False` during PPO
- `src/smartscan/ml/train.py` — train-split observation normalizer, validation AIR checkpoint selection over the full 200k budget, neural predictor wrapping
- `src/smartscan/ml/diagnose.py` — train/validation-only baseline diagnostics (never reads the held-out manifest)
- `src/smartscan/ml/evaluate.py`, `runner.py`, `policies.py`, `bundle.py`, `cli.py`

### Configs (held-out frozen before training; not tuned on)
- `configs/train_smoke.yaml` — 256 PPO steps; not used for performance claims
- `configs/train_full.yaml` — 200000 timesteps, `eval_cadence: 10000`, `early_stopping_patience: 5`, `ppo_ent_coef: 0.01`, `ppo_net_arch: [256, 256]`; train seeds sparse/dense/agile 0–5 / 0–3 / 0–5; val seeds 200–201 (dense 200 only); `test_scenarios: []`
- `configs/benchmark_final.yaml` + `configs/held_out_manifest.json` — 30 paired seeds 1000–1029 across sparse, dense, agile_threat, unseen_random, tsrd_synthetic

### Tests
- `tests/unit/test_ml_observable.py`, `test_ml_estimators.py`, `test_ml_env_policies.py`, `test_ml_gate.py`, `test_ml_train_bundle.py`, `test_ml_extra.py`
- `tests/integration/test_ml_cli.py`

### Docs and packaging
- `README.md`, `docs/BUILD_CONTRACT.md`, `pyproject.toml`
- `docs/stage_reports/STAGE_5_REPORT.md` — this report

## Frozen split verification (unchanged)

Held-out `configs/held_out_manifest.json` fingerprint (recomputed, file not rewritten):

`4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4`

30 pairs, seeds 1000–1029. Train/val catalogs in `configs/train_full.yaml` do not overlap those seeds. `test_scenarios` is empty; held-out is a separate frozen manifest.

Benchmark thresholds (unchanged): `vs_sequential_air_rel=0.05`, `vs_random_air_rel=0.05`, `vs_sequential_delay_rel=0.10`, `vs_best_noninferior_rel=0.02`, `pfa_newcombe_abs=0.001`, `pfa_newcombe_rel=0.20`.

## Why smoke PPO underperformed (train/validation only)

Diagnostics on `configs/train_full.yaml` catalogs (`artifacts/models/diagnose_train_val.json`). Held-out pairs were not read.

Train split (16 pairs) mean AIR:

| Strategy | Mean AIR | Hit rate | Dwell |
| --- | --- | --- | --- |
| sequential | 10.00 | 0.105 | all 8 |
| fixed-priority | 9.75 | 0.282 | all 8, bands 8/4/10 only |
| random | 8.75 | 0.104 | mixed 1–16 |
| reactive | 7.13 | 0.298 | all 8 |
| contextual-thompson | 6.75 | 0.087 | mixed 1–16 |

Validation split (5 pairs) mean AIR: fixed-priority **10.4**, sequential **9.6**, contextual-thompson **9.2**, reactive **8.8**, random **5.6**.

Reward-component scales: mean `cost_tune` ≈ 1e-4 and `cost_time` ≈ 4e-4 per decision; reward is essentially hit + 0.5×priority. Weights in `train_full.yaml` were left unchanged.

Smoke-training defects addressed without touching held-out data or thresholds:

1. PPO `learn()` previously reset only `train_scenarios[0]` (sparse). Env now cycles the frozen train catalog.
2. Observation normalizer previously reset every episode and kept last-episode stats. It is now fitted on **train-split** collect rows (`count=3741`) and frozen during PPO/eval.
3. SB3 `ent_coef` default 0 collapsed Discrete(80). Full config uses `ppo_ent_coef: 0.01`.
4. 256 steps was far below the documented 200k budget. Full budget was run.
5. Horizon MC (128 rollouts) is disabled inside PPO `step()` (`record_forecast=False`).
6. Neural `HitHazardPredictor` is wrapped with `BuilderBackedHazardPredictor` so env/PPO reward `p_hit` can use the calibrated net. Calibrators were fit on validation rows only.

## Full-training configuration

From `configs/train_full.yaml` (executed, not only documented):

- `timesteps: 200000`, `device: cpu`, `n_envs: 1`, `seed: 0`
- `duration_s: 0.5`, `dt_s: 0.001`, `noise_power_w: 1.0e-13`
- `ppo_n_steps: 2048`, `ppo_batch_size: 64`, `ppo_n_epochs: 10`, `ppo_learning_rate: 0.0003`, `ppo_gamma: 0.99`
- `ppo_ent_coef: 0.01`, `ppo_net_arch: [256, 256]`
- `eval_cadence: 10000`, `early_stopping_patience: 5` (patience recorded; **learn() was not truncated** — checkpoint rule `best_validation_air_full_budget`)
- Predictor: `n_epochs_predictor: 8`, `predictor_hidden: 64`, `predictor_lr: 0.003`; isotonic hit/activity calibrators fit on validation rows only
- Exploration collect strategies: sequential, random, fixed-priority, reactive

## Training / validation evidence (not held-out)

Exploration dataset `artifacts/models/datasets/full`: `n_rows=4952` train=3741 val=1211 test=0. Families: agile_threat 1887, sparse 1885, dense 1180.

Predictor train loss (validation used only for isotonic calibration): epoch 0 **1.420** → epoch 7 **0.726**.

PPO validation AIR (Stage 3 `average_intercept_rate` on the five frozen val pairs, every 10k steps):

| Timestep | Val AIR | Best so far |
| --- | --- | --- |
| 10000 | 6.0 | 6.0 |
| 20000 | 3.6 | 6.0 |
| 30000 | 7.2 | 7.2 |
| **40000** | **8.8** | **8.8** (selected) |
| 50000–200000 | 4.0–8.4 | 8.8 |

`timesteps_requested=200000`, `timesteps_completed=200704` (SB3 n_steps rounding). Selected checkpoint: **best_validation** at 40k, val AIR **8.8**. That is below validation sequential (9.6) and fixed-priority (10.4). Checkpoint choice used validation only.

Bundle: `artifacts/models/scheduler_full` (`freeze_obs_stats=true`, `normalizer_count=3741`).

## Commands executed and actual exit status

| Command | Exit status |
| --- | --- |
| `ruff check src tests` | 0 |
| `mypy src` | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov=smartscan.metrics --cov=smartscan.storage --cov=smartscan.ml --cov-fail-under=90` | 0 |
| `python -m smartscan.cli collect --config configs/train_full.yaml --output artifacts/models/datasets/full` | 0 |
| `python -m smartscan.cli train-predictor --config configs/train_full.yaml --track --output artifacts/models/predictor_full` | 0 |
| `python -m smartscan.cli train-contextual-bandit --config configs/train_full.yaml --track --output artifacts/models/cts_full` | 0 |
| `python -m smartscan.cli train-scheduler --config configs/train_full.yaml --track --output artifacts/models/scheduler_full` | 0 |
| `python -m smartscan.cli evaluate --config configs/benchmark_final.yaml --train-config configs/train_full.yaml --model artifacts/models/scheduler_full --seeds 30 --track` | 0 (gate recorded false) |
| `python -m smartscan.cli models promote --name SmartScanScheduler --version 2 --require-gate` | 2 (refused champion) |

No unrun check is claimed as passed. Held-out evaluation was run **once** after the bundle was frozen.

## Tests, coverage, acceptance-gate evidence

Final suite (workspace `.venv`, Python 3.11.9):

- **245 passed**, 0 failed
- Combined line coverage **rf + data + receiver + metrics + storage + ml: 93.76%** (threshold 90%)
- Critical modules: `observable.py` 97%, `reward.py` 96%, `predictor.py` 96%, `features.py` 96%

Engineering / firewall evidence (tests, not the held-out AIR gate):

- Gymnasium `check_env` passes; action decode, observation bounds, truncation, seeded replay
- Oracle firewall and future-causality tests pass; unvisited bands keep missingness masks
- Survival-loss golden cases; periodicity/agility/novelty use observed hits only
- Horizon forecast deterministic and clipped to `[0, 1]`; recency time-to-hit beats a constant-horizon naive on a periodic synthetic stream
- Five non-oracle baselines plus PPO produce compatible logs; bundle round-trip reproduces a fixed action
- Frozen held-out fingerprint and train/val seed lists are asserted in unit tests

## Held-out performance gate (full-budget weights — failed)

Manifest fingerprint: `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4`  
Gate artifact: `artifacts/models/held_out_gate.json` (`n_rows=210` = 30 pairs × 7 strategies including unattainable oracle ceiling)  
Smoke gate preserved at `artifacts/models/held_out_gate_smoke.json` (not used for this decision).

Held-out means (`duration_s=0.4`):

| Strategy | Mean AIR | Event interception ratio | Successful-event median delay (s) |
| --- | --- | --- | --- |
| PPO (full, best-val ckpt) | 5.00 | 0.369 | 0.0127 (n=25) |
| sequential | 9.25 | 0.443 | 0.0390 (n=27) |
| random | 7.00 | 0.368 | 0.0382 (n=26) |
| fixed-priority (best non-oracle) | 14.00 | 0.421 | 0.0127 (n=19) |
| reactive | 7.08 | 0.391 | 0.0426 |
| contextual-thompson | 7.75 | 0.368 | 0.0544 |
| oracle-ceiling (unattainable) | 23.25 | 0.674 | 0.0109 |

Relative AIR: vs sequential **−0.4595** (need ≥ 0.05); vs random **−0.2857** (need ≥ 0.05). Delay reduction vs sequential **0.675** (this single criterion would pass ≥ 0.10; it does not rescue the gate).

Paired 95% bootstrap CIs (PPO − baseline, seed 0):

| Contrast | Metric | mean Δ | 95% CI |
| --- | --- | --- | --- |
| vs sequential | AIR | −4.25 | [−6.08, −2.50] |
| vs random | AIR | −2.00 | [−3.75, −0.33] |
| vs sequential | event interception ratio | −0.073 | [−0.163, 0.021] |
| vs sequential | median delay | −0.028 | [−0.040, −0.015] |
| vs fixed-priority | AIR | −9.00 | [−19.34, −0.91] |
| vs fixed-priority | event interception ratio | −0.051 | [−0.147, 0.044] |
| vs fixed-priority | median delay | −0.0004 | [−0.0055, 0.0056] |

No primary paired delta vs best non-oracle has a 95% CI excluding zero in the improvement direction.

Pfa Newcombe (PPO 1/1406 vs fixed-priority 0/952): upper **0.00318** > limit **0.001**.

Per-family mean AIR (PPO vs sequential; family pass requires ≥ 5% relative):

| Family | PPO | sequential | Pass |
| --- | --- | --- | --- |
| sparse | 4.38 | 3.44 | true |
| dense | 6.88 | 15.00 | false |
| agile_threat | 7.19 | 14.38 | false |
| unseen_random | 0.63 | 3.75 | false |
| tsrd_synthetic | 0.00 | 0.00 | false |

Improvement does not hold in two families including `agile_threat`.

Forecast (not a pass/fail gate criterion): PPO ratio MAE **0.433** vs naive MAE **0.501** (n=30); mean intercept-time error **0.039** s; coverage mean **0.633**.

Gate reasons (verbatim):

- AIR vs sequential −0.4595 < required 0.05
- AIR vs random −0.2857 < required 0.05
- average_intercept_rate inferior to fixed-priority by −0.6429
- event_interception_ratio inferior to fixed-priority by −0.1221
- no primary paired delta vs best non-oracle has 95% CI excluding zero
- Pfa Newcombe upper 0.00318164 > limit 0.001
- improvement must hold in at least two families including agile_threat

`models promote --require-gate` correctly refused champion (CLI exit 2). Version 2 remains **candidate**.

## Reproducibility

| Item | Value |
| --- | --- |
| Python | 3.11.9 (`.venv`) |
| Train seed | `0` in `configs/train_full.yaml` |
| Held-out pairs | seeds 1000–1029; `duration_s=0.4`; `bootstrap_seed=0` |
| Dataset content fingerprint | `e1bb33ab8a12d9582d48e51b0917ecf130a83b36bac9665911ed15439c4dadc2` |
| Dataset artifact SHA-256 | `1351e501dbd23d692f39b157aa5f0ec7d383270813f9a788e59e0456e6f029d9` |
| Scheduler bundle content fingerprint | `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746` |
| PPO weights SHA-256 | `df3b6e05a719241efd41cdd36312bb9ffcebf82fddf1e12e7cfac96372e9b677` |
| Held-out manifest fingerprint | `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4` |
| Predictor MLflow run | `72c362c706b3435ca9d747b32570953b` |
| Contextual-bandit MLflow run | `3e91ab2ac361484a83832d08a24e15c3` |
| Scheduler MLflow run | `1d4383bb1e69473298286b6cc6e040fd` |
| Held-out eval MLflow run | `9de270ab7c454c4db355c8cf38c3e6c1` |
| Domain run (scheduler persist) | `da00b1e4-1a29-435d-b43a-6486c30e037b` |
| Registered model | `SmartScanScheduler` version **2**, alias **candidate**, unvalidated |
| Git SHA | none (workspace is not a git repository) |

Stage 5 train/benchmark `noise_power_w: 1e-13` is a **receiver-config** choice so builtin emitter powers (~1e-12 W) can produce detections. Stage 1 GroundTruth is unchanged.

## Known limitations (not blockers for `implementation_complete`)

- **Performance gate failed** on the frozen full-budget candidate. Engineering work is complete; champion is absent; no superiority claim.
- Validation AIR peaked at 8.8 (below val sequential 9.6). The 40k checkpoint was selected from validation only, then evaluated once on held-out.
- PPO still trails sequential and random on held-out AIR. Sparse is the only family with a sequential-relative AIR pass.
- TSRD held-out rows use the legal synthetic PDW fixture, not the gated 70 GB corpus.

## Stop condition

Stage 5 is closed. Stage 6 (dashboard) was not started.
