# InGameStaticStateNestedShrinkageDiagnostic-v2 — cross-independent pre-score review

Date: 2026-09-29  
Reviewer role: cross-independent pre-score reviewer; no implementation edits, no scoring run, no scheduler-state mutation  
Verdict: **PASS**

## Frozen review inputs

- runner: `experiments/nfl_ingame_static_state_nested_shrinkage_train_diagnostic.py`
  - SHA-256: `a3026d5a12fa0028087f470e44b71f4e6eb9de1432e351e415e72a039b83f65b`
- tests: `experiments/test_nfl_ingame_static_state_nested_shrinkage_train_diagnostic.py`
  - SHA-256: `4f6797fe09646c09143b657ae320decc38f32524a066a006a68f0f5fd52ee05e`
- implementation log: `supervisor_harness/AGENT_LOG_INGAME_STATIC_STATE_NESTED_SHRINKAGE_V2_IMPLEMENTATION_2026-09-29.md`
  - SHA-256: `895c60eb3bd6af113dbdb77e31de3b0781e1a40685180c857206c1d1f29389f0`
- frozen Controller decision: `supervisor_harness/AGENT_LOG_INGAME_DISCOVERY_V3_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md`
  - SHA-256: `a2c1c060b3ddf63ee3c0e1b6f7baebdba08b550c91be0a7d5585ead9b5dac18f`

All four observed bytes match the hashes supplied for this review.

## Contract review

PASS, with no findings:

- The candidate reconstructs and fail-closed validates the exact v0 materialized population, exclusions, checkpoint-state hash, chronological folds, and 87-row check mask. It then requires the frozen v1 prediction artifact to have its exact file set and hashes, exact prediction schema, exact 87-row key digest, and unchanged raw probabilities, outcomes, fold identities, dates, weeks, and checkpoints.
- The research parent and the comparison target remain distinct: the candidate develops the archived v0 static-state branch, while raw market is the task-local incumbent and frozen v1 linear-offset predictions are a read-only attribution control. The control is never refit.
- For every outer fold, the last six outer-fit dates are partitioned in order into exactly three consecutive two-date inner checks. Each inner fit uses all and only outer-fit dates strictly before the first date in its check block. Label availability must also be strictly earlier than the first check cutoff; unavailable labels, incomplete populations, empty/one-class fits, or causal-row validation failures stop the run.
- Every inner split evaluates exactly `lambda in {0.25, 1, 4, 16, 64}` on one common check mask. Selection minimizes pooled equal-event inner Brier across the three checks; an exact loss tie chooses the largest lambda. There is one full outer refit after selection. The enforced total is `5 * 3 * 4 + 4 = 64` candidate fits, with zero control fits and zero automatic retries.
- The four continuous static-state columns are standardized separately from the applicable inner or outer fit rows only. The possession/down binary columns remain raw. The predictor is `market_logit + intercept + standardized_state * beta`, fixing the market coefficient at one. The ridge term applies only to non-intercept coefficients, so the intercept is unpenalized.
- All three arms are evaluated on the identical 87 rows. Aggregate and fold arithmetic uses equal-event Brier/log loss. Paired evidence resamples complete schedule-date groups and complete observed-game-week groups with 10,000 replicates and seed `20260929`; it recomputes the equal-event mean inside each grouped resample.
- The decision routes match the frozen Controller rule. `SUPPORTED` requires aggregate Brier and log loss below both raw market and the frozen v1 control, plus Brier wins against each comparator in at least three of four folds. `REFUTED` applies when any aggregate comparison fails or raw-market Brier wins are at most one of four. All other valid outcomes are `INCONCLUSIVE`.
- The pre-score lock is written before fitting. Identity, hash, mask, chronology, label-availability, finite-number, optimizer, fit-count, and inner-selection failures are terminal. Output-root guards remain fail-closed. The artifact declares repeatedly inspected opened-Train historical diagnosis only and explicitly excludes realtime, untouched-OOS, promotion, deployment, PnL, and cross-task claims.
- Static inspection found no network client or subprocess import in the runner. Its declared boundaries remain Train-only with `external_fetch=false`, `paid_provider=false`, provider cost `$0`, Dev closed, Final sealed, and promotion unauthorized.

## Executed verification

From `research/market_rsi` with the pinned local Python 3.12 runtime:

1. `python -m unittest -v` over the attempt-02 test module plus the frozen v1 and v0 regression modules: **33/33 PASS** in 14.396 seconds.
2. The named actual opened-Train no-score preflight passed. It reconstructed the frozen materialization/masks and checked nested chronology without calling the candidate fitter.
3. `python -m py_compile` on the frozen runner and frozen test module: **PASS**.
4. `git diff --check` on the frozen runner, tests, and implementation log: **PASS**.
5. Post-test SHA-256 verification of all four frozen inputs: **PASS**, unchanged.

No real experiment, model scoring, artifact batch, provider call, external fetch, Dev/Final access, publication, promotion, or scheduler-state change was performed by this review.

## Disposition

The frozen attempt-02 implementation is internally consistent with the Controller contract and is safe for the Supervisor to launch as the separately authorized one-shot historical Train diagnostic. This PASS is pre-score implementation clearance only; it is not evidence that shrinkage helps, is not a KEEP/promotion decision, and does not authorize a run by itself.
