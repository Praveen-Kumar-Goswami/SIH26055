# SmartScan ML model improvement report

Offline synthetic simulation only. No live RF, SDR transmission, jamming, geolocation, or operational threat targeting.

This document is the closeout of one research improvement cycle. It does **not** replace Stage 5/7 held-out evidence.

```
MODEL_IMPROVEMENT_COMPLETE=true
NEW_PERFORMANCE_GATE_PASSED=false
V4_ACCURACY_PASS_COMPLETE=true
```

## Model identities (do not conflate)

| Role | Name | Path | Content fingerprint | Status |
| --- | --- | --- | --- | --- |
| **OLD HISTORICAL MODEL** | SmartScanScheduler **v2** | `artifacts/models/scheduler_full` | `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746` | Frozen candidate from Stage 5/7. **Not overwritten.** Dashboard still loads this bundle. |
| **RESEARCH CANDIDATE** | SmartScanScheduler **v3** | `artifacts/models/scheduler_v3` | `e89adc332b7d0532d08fa4d4d694c1dd42cd253a95f6329f2d983d8fc5b4a82f` | Prior research candidate. **Not overwritten.** Fresh test (8000–8007) remains historical. |
| **NEW ACCURACY CANDIDATE** | SmartScanScheduler **v4** | `artifacts/models/scheduler_v4` | `a674290744dd6a18f290a2cc248ccd7c9455d77bd5cc0bf4f05a2b33196a9fe7` | First-hit reward + teacher BC + longer PPO. Alias: candidate / unvalidated. **Not champion.** |

v3 is **not** claimed superior to v2 or to non-oracle baselines. A fresh predeclared synthetic test (seeds 8000–8007) shows v3 **worse** than sequential and random on Average Intercept Rate (AIR).

Historical Stage 5/7 held-out results (seeds **1000–1029**) remain locked. They were **not** used for hyperparameter selection, repeated candidate scoring, or this report’s model choice.

---

## 1. Diagnosis of old PPO (SmartScanScheduler v2)

v2 is a technically complete research candidate that **failed** the frozen performance gate. That failure is historical evidence, not a retuning target.

**Locked historical held-out (Stage 7, not re-run here):**

| Strategy | Mean AIR |
| --- | ---: |
| oracle-ceiling (unattainable) | 23.25 |
| fixed-priority | 14.00 |
| sequential | 9.25 |
| contextual-thompson | 7.75 |
| reactive | 7.08 |
| random | 7.00 |
| PPO v2 | **5.00** |

Held-out manifest content fingerprint: `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4`. File SHA-256: `bb3439ddbf23dff9c73b6611049b97ab0f068fd73d52f148fad5f85f44081c83`. `configs/benchmark_final.yaml` SHA-256: `2f8768768279e71444039df273704af278757509cdcf5470ca4e51bfc3fcef8b`.

### Why PPO can lose to simpler baselines (evidence from a *new* TRAIN/VAL protocol)

Diagnostics (`artifacts/ml_improve/diagnostics.json`) scored all non-oracle strategies on the **improvement** TRAIN/VAL splits only. v2 PPO was evaluated with its original 309-d observation (no v3 extras). Seeds 1000–1029 were unused.

**TRAIN global mean AIR (20 scenario+seed pairs):**

| Strategy | AIR | Unique bands | Band entropy | Dwell=1 count | Episode return |
| --- | ---: | ---: | ---: | ---: | ---: |
| fixed-priority | **11.00** | 3.0 | 1.10 | 0 (all dwell 8) | (costs dominate hits on some families) |
| reactive | 9.50 | 13.0 | ~2.7 | mixed | — |
| sequential | 9.25 | **16.0** | 2.77 (max) | 0 | **−1.41** |
| random | 7.75 | 15.7 | 2.70 | mixed | — |
| PPO v2 | **6.00** | **5.95** | **1.02** | **1155** | **+73.76** |
| contextual-thompson | 5.50 | 12.2 | 2.72 | mixed | **−2.21** |

**VAL global mean AIR (7 pairs; small-n, high variance):** CTS 12.14, random 13.57, fixed-priority 8.57, PPO v2 / reactive / sequential **7.14**.

Per-family TRAIN AIR for v2 PPO vs strongest simple baseline:

| Family | PPO v2 | Sequential | Fixed-priority | CTS |
| --- | ---: | ---: | ---: | ---: |
| agile_threat | 7.5 | 12.5 | **25.0** | 9.2 |
| dense | 8.75 | 11.25 | **0.0** | 5.0 |
| random | 2.5 | 5.0 | 5.0 | 3.75 |
| sparse | 5.0 | 7.5 | **8.3** | 3.3 |

Fixed-priority’s TRAIN win is **family-specific**: public bands `[8, 4, 10]` match agile_threat occupancy and miss dense (AIR 0). Global averages hide that.

### Root-cause ranking (not “PPO is the wrong algorithm”)

Evidence supports **several interacting failures**. PPO as an optimizer is not independently guilty.

1. **Reward / metric mismatch (strong).** Under the diagnostic reward, v2 PPO’s TRAIN `reward_hit_total=952` vs sequential `38`, while AIR is *worse* (6.0 vs 9.25). The policy farms **observable hits** with 1-step dwells on a few bands (band 8: 1122 visits; hit rate 0.62). AIR and event-interception ratio credit **distinct events**, not repeated hits on the same occupancy. Repeat cost (`40.9` total) does not offset hit+priority (`952 + 623`).

2. **Historical time-cost scaling (strong).** v2 `time_cost_mode=dt_scaled` multiplies tune/time costs by `dt_s=0.001`, so `c_tune * dt ≈ 10⁻⁴` vs `w_hit=1`. Tune and dwell penalties were scientifically present and numerically negligible. The policy learned “short dwell, stay on a hot band.”

3. **Policy collapse / under-exploration of the band simplex (strong).** TRAIN band-visit entropy **1.02** vs sequential **~2.77**. Unique bands **5.95** vs 16. Repeat-band streak **4.40** vs sequential 1.0. Hits following exploration: **0**. This is exploitation of a small subset, not uniform scanning.

4. **Joint Discrete(80) action space (moderate).** Band×dwell as one categorical makes “dwell=1 on band 8” a single high-value atom. Factorizing later (MultiDiscrete) is a research mitigation, not a proof that Discrete was the only problem.

5. **Predictor–policy mismatch (moderate).** Logged `p_hit` Brier on v2 PPO TRAIN trajectories **0.224** / ECE **0.194** vs sequential **0.087 / 0.088**. The collapsed policy visits a non-representative band mix; calibration on those visits is poor.

6. **Scenario imbalance of the *metric*, not only the sampler (moderate).** Fixed-priority dominates agile_threat and fails dense. A policy that copies public-priority bands looks good on mixed averages and dies on dense.

7. **Value-function / horizon (moderate, confirmed on v3 too).** Short 0.2 s episodes, sparse distinct-event credit, and a dense per-step hit bonus make the critic hard to fit. v3 explained variance is often **negative**.

8. **Insufficient observations** was **not** the leading v2 failure. The 309-d `FeatureBuilder` already includes per-band recency, EWMA hit rate, SNR, visit counts, periodicity/agility/novelty channels, and missingness. Collapse happened *with* those features.

9. **Overfitting to training seeds 0–5** is possible for v2’s 200k-step run; this cycle did not re-train v2 and does not re-interpret the locked 1000–1029 scores.

**Not supported as primary causes:** missing oracle features (forbidden and unnecessary for sequential/fixed-priority wins); Pfa (v2 diagnose Pfa ≈ 0 on this split); “entropy too high” (v2 entropy was *too low*).

---

## 2. Experiments performed

Development used a **new disjoint protocol** (`configs/train_improve.yaml`). `TrainConfig` **rejects** seeds 1000–1029.

| Split | Families | Seeds | Use |
| --- | --- | --- | --- |
| TRAIN | sparse, dense, agile_threat, random | 10–15 (dense/random 10–13) | Fit predictor + PPO |
| VALIDATION | same | 300–301 (random: 300 only) | HPO, checkpoint, seed selection |
| DEV-TEST | same | 400 | Protocol completeness only; **not** used for selection |
| Frozen held-out | Stage 5/7 | **1000–1029** | **Untouched** |
| Fresh final test | same four families | **8000–8007** | One evaluation after freeze |

v2 historical train seeds 0–5 and val 200–201 were also avoided.

| Experiment | Split | Artifact | Outcome |
| --- | --- | --- | --- |
| Diagnostic baselines (6 strategies × train/val, per family) | TRAIN/VAL | `diagnostics.json` | v2 PPO collapses; reward≠AIR |
| Predictor mlp vs residual_ln | VAL Brier/ECE | `predictor_study.json` | **mlp** selected |
| HPO: Discrete vs MultiDiscrete vs Discrete+curriculum (1536 steps) | VAL composite | `hpo.json` | **multidiscrete_ent002** |
| Multi-seed PPO (seeds 41, 42, 43; 4096 steps) | VAL composite | `v3_selection.json` | seed **43** |
| Fresh test (once) | seeds 8000–8007 | `fresh_test_gate.json` | gate **false** |

**Not run as full validation grids** (CPU-bounded cycle; stated as limitations, not hidden):

- Five-way predictor-channel PPO ablations (`none` / `q_hit` / `q_hit+p_active` / temporal / full neural forecasts)
- GRU / LSTM / 1-d conv / attention *policy* encoders
- Two-stage hierarchical band-then-dwell PPO
- Recurrent PPO (RecurrentPPO / sb3-contrib not in the lock)
- Optuna (deterministic 3-trial HPO used instead)

Lightweight substitutes that *were* run: MultiDiscrete vs Discrete; curriculum vs mixed-from-start; recency `q_hit`/`p_active`/uncertainty channels + last-4 actions in the observation; residual MLP predictor vs v2 Sequential MLP.

MLflow experiment: `smartscan-ml-improve`.

---

## 3. Feature ablations

Oracle firewall unchanged: no occupancy truth, emitter IDs, future activity, hidden threat labels, or post-run event matches in the policy observation.

**v2 observation:** `FeatureBuilder.vector` **309-d** (per-band stats, EWMA, SNR, visits, periodicity/agility/novelty, global tune/horizon).

**v3 observation:** 309-d base + recency predictor channels (16×3 + 1) + last-4 `(band, dwell, hit)` history → **366-d**. Neural per-band MLP forecasts (`include_neural_predictor_obs`) were implemented and **left off** for CPU cost; they were not selected.

| Comparison | VAL evidence | Adopted? |
| --- | --- | --- |
| v2 309-d vs v3 366-d | Confounded with reward, action layout, and step budget. Not a clean ablation. | v3 extras kept as the research candidate’s contract |
| Neural forecast channels on vs off | Off only (no val grid) | **Off** |
| Last-k action history k=4 | Used as a cheap temporal encoder; no k-sweep | **On** |
| Discrete 80 vs MultiDiscrete [16, 5] | VAL AIR 6.43 vs **7.14** (HPO) | **MultiDiscrete** |

No redundant base FeatureBuilder channels were removed: there was no isolated val proof that any 309-d slice *hurt* AIR.

---

## 4. Reward analysis

Decompose (observable only):

`R = w_hit·hit + w_priority·hit·priority − c_tune·tune_steps − c_time·time_term − c_repeat·wasted_revisit − c_false·low_conf_hit`

| Mode | Tune / time scale | v2 default | v3 research |
| --- | --- | --- | --- |
| `dt_scaled` | × `dt_s` (1e-3) | **yes** | no |
| `per_step` | per command, 1-step cheaper than 8-step | diagnosed; **rejected** (CTS return negative when costs > hits) | no |
| `excess_dwell` | time cost only on dwell **above** 8 steps; tune **per step** (not × dt) | — | **yes** |

v3 weights: `w_hit=1`, `w_priority=0.4`, `c_tune=0.03`, `c_time=0.02`, `c_repeat=0.08`, `c_false_like=0.1`.

**TRAIN component totals (same eval reward, 20 pairs):**

| Strategy | hit Σ | priority Σ | tune Σ | time Σ | repeat Σ | AIR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sequential | 38 | 2.4 | 35.2 | 29.7 | 0 | 9.25 |
| CTS | 27 | 2.5 | 32.1 | 29.1 | 10.4 | 5.50 |
| PPO v2 | **952** | **623** | 27.7 | 29.2 | 40.9 | 6.00 |

Hit still dominates for a 1-step farming policy. `excess_dwell` stops *rewarding* short dwell via a smaller time cost, but it does not make AIR the training objective. That remaining mismatch is a **limitation**, not a solved problem.

Controlled ablations on TRAIN/VAL were the mode switch (dt_scaled / per_step / excess_dwell) plus coefficient lowering after CTS returns went negative under `per_step`. Coefficients were **not** raised until PPO “won.”

---

## 5. Predictor analysis

Dataset fingerprint (collection): `6688772705664d12f4f19387ab5f969479817541a2d5a472a1b1a502343c6d1d`.  
Rows: 2861. Train positives 296 / 1803 (`pos_weight ≈ 5.09`). Val 670 rows. Isotonic calibration fit on VAL only.

| Arch | Val Brier raw | Val Brier cal | Val ECE raw | Val ECE cal | Early stop | MLflow |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **mlp** (v2-compatible Sequential, hidden 48, dropout 0.1) | 0.152 | **0.113** | 0.172 | **0.023** | epoch 4 best of 6 | `c4fa12e251274e99ac3f22f1be3bf2c1` |
| residual_ln | 0.163 | 0.116 | 0.154 | 0.026 | epoch 2 | `12e1851cba03483fa3ba31495b810d51` |

**Selected: mlp.** Residual+LayerNorm did not improve calibrated Brier on this sample. Isotonic reduces ECE ~0.17 → ~0.023. Class-balanced BCE used; focal loss not adopted (no val win required). Network stays CPU-small (`n_in=309`).

v3 still uses this calibrated hit/active head for logging and CTS; PPO observations use **recency copies** of those probabilities, not a second temporal net.

---

## 6. Hyperparameter experiments

Bounded deterministic search (no Optuna). Each trial 1536 PPO steps, VAL composite:

`score = AIR + 0.5·ratio − 0.05·delay − 20·Pfa`

Dataset fingerprint: `45d5610580cd97ddcab4b01fc3f590c4911bd25257c1265552e032f1a8109676`.

| Trial | Layout | Curriculum | Best VAL AIR | Best score | Peak timestep | MLflow |
| --- | --- | --- | ---: | ---: | ---: | --- |
| discrete_ent002 | Discrete 80 | no | 6.43 | 6.60 | 1536 | `8d9cd969dca445589a28e267d46e7f58` |
| **multidiscrete_ent002** | MultiDiscrete | no | **7.14** | **7.32** | **768** (then 5.0 @ 1536) | `e2c073ca365f4b66ba494d4a94cff14a` |
| discrete_curriculum | Discrete 80 | sparse→periodic-like→dense→agile→mixed | 7.14 | 7.31 | 768 | `6db6f8e61a89404e98765f60b708dfc0` |

Shared PPO knobs (not swept independently): `lr=3e-4` (linear decay on longer runs), `n_steps=256`, `batch=64`, `n_epochs=4`, `gamma=0.99`, `gae_lambda=0.95`, `clip=0.2`, `ent_coef=0.02`, `vf_coef=0.5`, `max_grad_norm=0.5`, net `[128,128]`.

VAL curves are **unstable** on a 7-pair val set. Best-checkpoint restore is mandatory; last-step AIR is not used.

---

## 7. Training curves (v3 selected seed 43)

4096 steps, MultiDiscrete, mlp predictor, frozen observation normalizer after warmup (`normalizer_count=123`).

VAL (composite checkpoint rule):

| Timestep | VAL AIR | Ratio | Delay | Pfa | Score |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2048 | **5.71** | 0.319 | 0.0065 | 0 | **5.87** |
| 4096 | 5.00 | 0.306 | 0.019 | 0 | 5.15 |

Restored **best_validation** at 2048 steps.

Typical TRAIN diagnostics (seed 43, late updates): entropy loss ≈ **−4.35** (near `log 16 + log 5 ≈ 4.38` — policy still close to uniform over legal atoms); KL ~ 2e-4; clip fraction ≈ 0; explained variance **oscillates through negative**; value loss O(0.3–1.0).

Interpretation: 4096 steps is far below v2’s 200k. v3 did **not** collapse like v2, and also **did not learn** a peaked intercepting policy. Deterministic argmax at eval then behaves like an arbitrary near-uniform logit tie-break — often worse than a designed random scheduler.

MLflow: `de69c8c2245c44fa91c4de48dcefc954` (seed 43). Seeds 41 / 42: `f951a5832038464aa3ab67d711cf82f0` / `a2f387a2c98d4b7481377740d7106341`.

---

## 8. Validation comparison

**v2 PPO on improvement VAL (not held-out):** AIR 7.14.

**v3 HPO winner on VAL:** AIR 7.14 (768 steps, n=7).

**v3 multi-seed VAL AIR:** mean **5.24**, median **5.71**, std **0.67** (seeds 41: 4.29; 42: 5.71; 43: 5.71).

Curriculum was **not** selected (score 7.31 vs 7.32). Mixed-from-start + balanced family interleave is the v3 sampler.

VAL n=7 is noisy (e.g. diagnostic random AIR 13.57). Selection used the **predeclared composite**, not max AIR alone, and required **3 training seeds**. That is still a weak val set; it is the honest protocol, not a claim of precise ranking.

---

## 9. Final chosen architecture (v3 candidate)

- **Policy:** Stable-Baselines3 PPO, MultiDiscrete `[band_index, dwell_index]`, MLP `[128, 128]`, CPU.
- **Observation:** 366-d composed vector; running mean/std from **train warmup only**, persisted in `normalizer.npz`, frozen before PPO (`freeze_obs_stats=true`). Missingness via masks in FeatureBuilder; no fake zeros as “known empty.” NaN/Inf rejected.
- **Predictor:** mlp hidden 48, dropout 0.1, class-balanced BCE, isotonic on VAL, `predictor_meta.json` `arch=mlp`.
- **Reward:** `excess_dwell`, coefficients above.
- **Dwell bins:** `[1, 2, 4, 8, 16]` unchanged scientifically; 1-step remains legal.
- **Not adopted:** residual predictor, neural forecast obs, GRU/LSTM/attention policy, hierarchical two-loop PPO, RecurrentPPO, curriculum final mix.

`model_version`: `3.0.0-candidate`. Receiver command contract unchanged (`band + dwell_steps`).

---

## 10. Fresh-test methodology

Manifest **generated and fingerprinted before** evaluating v3.

- File: `configs/fresh_test_manifest.json`
- Content fingerprint: `0f00476bd03177a51a4bc520dfe151a5829fcbdd39fa69b492425036e4c1a7fb`
- File SHA-256: `b073973e06ffea2d8cfc0fc8d6f82d92f3cb15c3dbc7b4c97d157e0d999399b2`
- Benchmark YAML: `configs/benchmark_v3_fresh.yaml` SHA-256 `72f6e66dca41bcdcada0fae08f69b03f671306361445ecd6cb970fea4c7f7f32`
- Duration **0.2 s**, `dt=1 ms` (research protocol; **not** the 0.4 s historical held-out YAML)
- 4 families × 8 seeds = **32 pairs**; 7 strategies including oracle → **224** rows
- Seeds **8000–8007** never in v2 train/val, never in improve train/val/dev-test, never in 1000–1029
- Model and dataset fingerprints frozen in the gate JSON **before** interpreting pass/fail
- **Evaluated exactly once** (`evaluated_once=true`)

This test is **not** comparable one-to-one with Stage 5/7 (different duration, seeds, and model). It is a new synthetic gate for v3 only.

---

## 11. Final results (fresh synthetic test — once)

MLflow (cycle summary): `0c0464e689504f7da74825bd6d3e6777`.

**Mean AIR**

| Strategy | Mean AIR |
| --- | ---: |
| oracle-ceiling | 15.94 |
| random | **8.44** |
| fixed-priority | 8.13 |
| sequential | 7.97 |
| contextual-thompson | 7.19 |
| reactive | 7.03 |
| **PPO v3** | **3.91** |

Relative AIR: vs sequential **−0.51**; vs random **−0.54**. Best non-oracle: **random**. Paired delta vs best: mean **−4.53** (95% CI entirely negative).

**Per-family mean AIR (do not quote only the global mean)**

| Family | Seq | Random | Fixed-pri | Reactive | CTS | **PPO v3** | Oracle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sparse | 5.63 | 5.00 | 6.88 | 5.00 | 5.00 | **5.00** | 6.88 |
| dense | 12.50 | 9.38 | **0.00** | 13.13 | 10.00 | **0.00** | 10.63 |
| agile_threat | 10.63 | 15.00 | **25.00** | 7.50 | 11.25 | **10.00** | 43.75 |
| random | 3.13 | 4.38 | 0.63 | 2.50 | 2.50 | **0.63** | 2.50 |

**Failures (not hidden):**

- **Dense: PPO AIR 0** on this seed block (same qualitative hole as fixed-priority’s public-band stare).
- Agile_threat: PPO ≈ sequential (10 vs 10.6), far behind fixed-priority (25) and random (15).
- Random family: PPO near floor (0.63).
- Sparse: PPO ties several baselines (~5), below fixed-priority (6.88).

**Pfa:** PPO `0/1521` detections vs random `3/705`. Newcombe upper **7.4×10⁻⁵** < 0.001. Low Pfa is **not** a scheduler win when AIR collapses.

**Delay:** `delay_reduction_vs_sequential ≈ 0.92` is **not** a success metric here. PPO intercepts far fewer events; delay is computed on a selected subset and must not be advertised as “faster intercepts.”

Seed-level rows: `artifacts/ml_improve/fresh_test_gate.json` (`n_rows=224`).

---

## 12. Failures and limitations

- v3 **underperforms** sequential, random, fixed-priority, reactive, and CTS on the fresh test.
- **4096 PPO steps / 0.2 s episodes** is not a compute-matched rematch of v2 (200k steps, longer historical eval). Under-training is the leading v3-specific issue; near-max entropy + deterministic eval ≈ a bad random policy.
- Reward still credits **hits**, not unmatched events. Farming remains a viable local optimum for any longer run unless the objective is changed carefully (still observable-only).
- VAL set is 7 pairs; HPO AIR 7.14 did **not** generalize to 32-pair fresh AIR 3.91.
- Feature / temporal / hierarchical / recurrent experiments were **bounded**, not exhaustive.
- `improve_cycle.py` is orchestration (pytest coverage **0%** on that file); behavior is covered indirectly via unit tests and saved JSON.
- No Optuna; no claim that `(lr, n_steps, …)` are optimal.
- Dashboard still serves **v2**. No UI redesign.
- Champion / production aliases were **not** promoted. Formal Stage 5/7 gate rules were **not** bypassed.

The model is not perfect. It is a documented research candidate.

---

## 13. Fingerprints

| Object | Value |
| --- | --- |
| v2 bundle content | `81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746` |
| v3 bundle content | `e89adc332b7d0532d08fa4d4d694c1dd42cd253a95f6329f2d983d8fc5b4a82f` |
| v3 `checksums.json` SHA-256 | `92681140310b54d1c70580144cb794860a6fb37207eeb4a198b73eb816eb2041` |
| Historical held-out manifest content | `4603deb9f4203082e087f3bd3b8b3a6e0ac70f9967bef19bc49bfe0c61c5aed4` |
| Historical `benchmark_final.yaml` | `2f8768768279e71444039df273704af278757509cdcf5470ca4e51bfc3fcef8b` |
| Fresh-test manifest content | `0f00476bd03177a51a4bc520dfe151a5829fcbdd39fa69b492425036e4c1a7fb` |
| Fresh-test manifest file | `b073973e06ffea2d8cfc0fc8d6f82d92f3cb15c3dbc7b4c97d157e0d999399b2` |
| `benchmark_v3_fresh.yaml` | `72f6e66dca41bcdcada0fae08f69b03f671306361445ecd6cb970fea4c7f7f32` |
| `train_improve.yaml` | `1178f0097ad587996b040d2c15f2bdaa039322c22755d6a0e29660dde4880dfa` |
| Predictor dataset | `6688772705664d12f4f19387ab5f969479817541a2d5a472a1b1a502343c6d1d` |
| HPO dataset | `45d5610580cd97ddcab4b01fc3f590c4911bd25257c1265552e032f1a8109676` |
| v3 train dataset | `00d406ed0662a994b576a82fe9c42b7364cab9497cf8d1eace3c9ce159c7b92f` |

v2 files were not rewritten. A prior broken v3 fingerprint `d799907d…` (unnormalized obs) was replaced by the retrained bundle above **before** the one-shot fresh test.

---

## 14. MLflow run IDs

Experiment `smartscan-ml-improve`.

| Run | ID |
| --- | --- |
| Predictor mlp | `c4fa12e251274e99ac3f22f1be3bf2c1` |
| Predictor residual_ln | `12e1851cba03483fa3ba31495b810d51` |
| HPO discrete | `8d9cd969dca445589a28e267d46e7f58` |
| HPO multidiscrete (selected layout) | `e2c073ca365f4b66ba494d4a94cff14a` |
| HPO curriculum | `6db6f8e61a89404e98765f60b708dfc0` |
| v3 train seed 41 | `f951a5832038464aa3ab67d711cf82f0` |
| v3 train seed 42 | `a2f387a2c98d4b7481377740d7106341` |
| v3 train seed 43 (selected) | `de69c8c2245c44fa91c4de48dcefc954` |
| Fresh test | `0c0464e689504f7da74825bd6d3e6777` |

Registry: new version path `artifacts/models/scheduler_v3` only. **Do not** treat this as champion. `SmartScanScheduler` v2 artifacts remain the historical candidate bundle for the dashboard (`configs/dashboard.yaml` → `scheduler_full`).

---

## 15. Inference performance

From `artifacts/ml_improve/inference.json` (CPU, laptop-class):

| Metric | v3 |
| --- | --- |
| Bundle load | 0.027 s |
| Mean infer | 0.063 ms / call (64 repeats) |
| Observation size | 366 |
| Device | CPU only |

Suitable for a normal laptop. Checksum verification remains via `checksums.json`. Observation normalizer is inside the bundle.

### Quality gates (this cycle)

```
ruff check src tests scripts   # pass
mypy src                       # pass (80 files)
pytest tests --cov=smartscan --cov-fail-under=85   # pass, 87.38%
```

New tests live in `tests/unit/test_ml_improve.py` (protocol hygiene, oracle leakage, action legality, reward modes, composed obs + normalizer persistence, residual save/load). Critical modules are mostly ≥85–97%; `train.py` ~80% and `improve_cycle.py` 0% are the practical gaps.

---

## 16. v4 accuracy pass (addendum)

v3 under-trained and still paid for every observable hit. v4 does **not** overwrite v2 or v3. Selection used TRAIN/VAL only. The v3 fresh test (8000–8007) was **not** reused.

### Changes

1. **First-hit-on-visit reward** (`first_hit_only`): a hit is credited only when the previous command was a miss or a different band. Farming 1-step dwells on the same occupancy no longer stacks `w_hit`.
2. **Coverage bonus** for visiting a band absent from the last 16 commands (sequential-like sweep).
3. **Per-decision cost** `c_action` plus `c_repeat_hit` on continued-stay hits.
4. **Behavioral cloning** from sequential, reactive, and periodic-intercept teachers (observable `ScheduleView` only), then PPO fine-tune.
5. **Longer PPO**: 32768 steps, 3 seeds (51/52/53), MultiDiscrete, `ent_coef=0.008`.

Config: `configs/train_v4.yaml`. Bundle: `artifacts/models/scheduler_v4`.

### Validation (not a test set)

| Seed | Best VAL AIR | MLflow |
| ---: | ---: | --- |
| **51** (selected) | **8.57** | `a814fffce9b84255ba267d285bebfd15` |
| 52 | 6.43 | `5b52da31874f40859eef943d7ac2043f` |
| 53 | 5.71 | `b6ee327bd589479fbf5127cc1b104385` |

Mean **6.90**, median **6.43**, std **1.21**. Dataset fingerprint `4183b452fbaceb2bc2422d56ebc3e27f07b6647834336d08f87a07beb8dcd834`.

v3 multi-seed VAL mean AIR was **5.24**. Seed 51 VAL **8.57** exceeds sequential’s ~7.14 on this 7-pair val set. Val n=7 remains noisy; this is not a gate.

### Fresh test (once, seeds 9000–9007)

Predeclared before training: `configs/fresh_test_v4_manifest.json`  
content fingerprint `fda8d2ac12e2235466b9ea3fd0bf3a047b5c3d5f62c150e2b3519be97b8158e1`  
`configs/benchmark_v4_fresh.yaml` SHA-256 `a0dfafbe6430366e3287344b1ffabe121437a9bcd719c13e02b86774b3cbea1d`  
Gate file: `artifacts/ml_improve/fresh_test_v4_gate.json` (`n_rows=224`, `evaluated_once=true`)  
MLflow: `08411f812c8c401eb205ef08f816d1ae`

**Mean AIR (duration 0.2 s, not comparable 1:1 to Stage 5/7 0.4 s held-out)**

| Strategy | v3 fresh (8000–8007) | v4 fresh (9000–9007) |
| --- | ---: | ---: |
| sequential | 7.97 | **10.00** |
| random | 8.44 | 9.53 |
| reactive | 7.03 | 9.06 |
| fixed-priority | 8.13 | 8.91 |
| **PPO** | **3.91** | **7.97** |
| CTS | 7.19 | 6.56 |
| oracle | 15.94 | 17.97 |

v4 PPO vs sequential on this new test: relative AIR **−0.203** (v3 was **−0.51** on a different seed block). Still below the +0.05 gate. **Not claimed superior to sequential.**

**Per-family mean AIR (v4)**

| Family | Seq | Random | Fixed-pri | Reactive | CTS | **PPO v4** | Oracle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sparse | 6.88 | 4.38 | 8.13 | 6.25 | 4.38 | **5.63** | 8.13 |
| dense | 15.63 | 13.13 | 0.00 | 13.13 | 10.00 | **5.63** | 11.25 |
| agile_threat | 11.25 | 16.88 | 25.00 | 10.00 | 8.13 | **16.25** | 43.75 |
| random | 6.25 | 3.75 | 2.50 | 6.88 | 3.75 | **4.38** | 8.75 |

`family_pass.agile_threat=true` (PPO beats sequential there). Dense remains a failure. Gate still requires two families including agile_threat.

**Pfa:** PPO `4/3619` vs sequential `1/627`. Newcombe upper **0.00210** > 0.001. v4 is less conservative than v3’s zero false alarms.

Inference: load 0.038 s, 0.114 ms/call, obs 366, CPU.

Do not retune on 9000–9007. Dashboard still points at v2. To try v4 in the dashboard, set `SMARTSCAN_MODEL_DIR=artifacts/models/scheduler_v4` and restart; frozen held-out cards stay historical.

---

## Flags (read these first)

```
OLD HISTORICAL MODEL = SmartScanScheduler v2
  path: artifacts/models/scheduler_full
  fingerprint: 81751a75c678b5bab922f54f77e73fc525a9a2c8c5d9ecbaaaa257a48eef6746
  held-out (historical): PPO AIR 5.00 vs sequential 9.25 / random 7.00 / fixed-priority 14.00
  performance_gate_passed: false  (unchanged)

RESEARCH CANDIDATE = SmartScanScheduler v3
  path: artifacts/models/scheduler_v3
  fingerprint: e89adc332b7d0532d08fa4d4d694c1dd42cd253a95f6329f2d983d8fc5b4a82f
  fresh test (once, seeds 8000–8007): PPO AIR 3.91 vs sequential 7.97
  champion_set: false

NEW ACCURACY CANDIDATE = SmartScanScheduler v4
  path: artifacts/models/scheduler_v4
  fingerprint: a674290744dd6a18f290a2cc248ccd7c9455d77bd5cc0bf4f05a2b33196a9fe7
  fresh test (once, seeds 9000–9007): PPO AIR 7.97 vs sequential 10.00 / random 9.53
  alias: candidate / unvalidated
  champion_set: false

MODEL_IMPROVEMENT_COMPLETE=true
NEW_PERFORMANCE_GATE_PASSED=false
```

Stop. Do not tune on seeds 1000–1029, 8000–8007, or 9000–9007. Do not promote champion from this cycle.

