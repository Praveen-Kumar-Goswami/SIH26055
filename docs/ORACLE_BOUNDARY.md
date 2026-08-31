# Oracle boundary

Ground truth occupancy, true emitter identities/parameters, future observations, and evaluator-only `threat_weight` / `hidden_metadata` are **not** policy-visible.

They may appear only in:

1. The physical simulator (`smartscan.rf.environment`)
2. The post-run evaluator (`smartscan.metrics.engine`)
3. An optional dashboard **evaluation overlay** that is labeled “not available to policy”

## Live policy

`FeatureBuilder`, `RewardCalculator`, `HitHazardPredictor`, and all deployable policies (`sequential`, `random`, `fixed-priority`, `reactive`, `contextual-thompson`, `periodic-intercept`, PPO) must not read GroundTruth occupancy or hidden labels.

The same seed and config must produce identical actions and rewards with the evaluation overlay off and on. Overlay occupancy is a visualization, not an input.

## Oracle ceiling

`oracle-ceiling` is an evaluator-only schedule that peeks at occupancy. It is labeled **unattainable**. It is never stored as a deployable model, never registered as `candidate`/`champion`, and never selected by `best-available`.

Comparative tables may show it as a ceiling. They must not treat it as a baseline the submitted scheduler is required to beat for champion status.

## Prefix

Oracle-bearing fields use `ORACLE_INFO_PREFIX` in Gymnasium info dicts so wrappers can assert they are unused by the policy.
