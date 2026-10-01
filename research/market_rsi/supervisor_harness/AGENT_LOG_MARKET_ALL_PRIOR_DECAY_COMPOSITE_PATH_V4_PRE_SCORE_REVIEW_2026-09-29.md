# MarketAllPriorDecayCompositePath-v4 pre-score independent review

Date: 2026-09-29  
Verdict: **PASS**  
P0: none  
P1: none

This is a methodology and frozen-source review only. I did not run the real
opened-Train entry, create a real candidate artifact, read Dev/Final, contact a
provider or network source, or authorize promotion. PASS means only that the
Supervisor may consider the separately controlled fresh-ID Train Discovery
run.

## Frozen review inputs

- Controller recipe:
  `research/market_rsi/supervisor_harness/AGENT_LOG_DISCOVERY_ATTEMPT4_CONTROLLER_2026-09-29.md`
  = `fab9f134f2e1523265a429fbd8ff2fc9a6ca98f37216a60d7371683e43d01595`.
- Runner:
  `research/market_rsi/experiments/nfl_market_all_prior_decay_composite_path_train_diagnostic.py`
  = `c9fc5b9d01a28181382ca47d9545ca7ce06c769b6165b482b84fc26df4537139`.
- Focused test:
  `research/market_rsi/tests/test_nfl_market_all_prior_decay_composite_path_train_diagnostic.py`
  = `7183c64040bba0e02ae583b34050e87f6f4f15a42183e18eccba7a76626da2e7`.
- Implementation log:
  `research/market_rsi/supervisor_harness/AGENT_LOG_MARKET_ALL_PRIOR_DECAY_COMPOSITE_PATH_V4_IMPLEMENTATION_2026-09-29.md`
  = `d56e87d3ba213c17d22dd73ff6ca3b8a2a894d058ae06a902ec2323c85f33b0b`.
- Passing Attempt-3 result review =
  `016930f4d027be2ecee79b61beb76a914eb3198cc853c632cc79d764fcceb0ad`.
- Frozen Attempt-3 runner/test =
  `05af717084499618c99fefd034972681d4acef12b226b5fc8b8a4513c26fdbd1` /
  `9d2491170a1862a4239118ad8ff03d95e5c4ed5e682e131a5023ae4ac4b1363d`.

The observed hashes matched these values after the implementer declared the
snapshot frozen.

## Independent methodology and code findings

### Support, decay, and causality

The sole scientific delta from Attempt 3 is trainer support. For each fold the
candidate uses every eligible fit row whose numeric ISO game-week is strictly
earlier than the first check week. Event weights are exactly
`2**(numeric_week_index - latest_eligible_numeric_week_index)`: the newest
eligible week has weight 1, then 1/2, 1/4, and so on. There is no normalization
by week size, class, date, or feature value. Same-week and later-week rows are
rejected, and label availability is required to precede the earliest check
cutoff.

I independently reconciled the frozen production arithmetic:

| Fold | Eligible rows | Weight sum | Squared-weight sum | Kish rows |
| --- | ---: | ---: | ---: | ---: |
| 1 | 107 | 29.625 | 19.94140625 | 44.0109696 |
| 2 | 120 | 27.8125 | 17.9853515625 | 43.0091763 |
| 3 | 148 | 27.953125 | 18.62408447265625 | 41.9552005 |
| 4 | 177 | 28.48828125 | 18.914005279541016 | 42.9090590 |

Per-week counts, binary outcome counts, class-weight totals, total weights and
squared weights are production-frozen and fail closed. The emitted ordered
event ledger binds identity, week, outcome and weight.

The representation remains the exact Attempt-3 construction: all transform
parameters are fit only on the three latest eligible weeks strictly before the
check boundary. Those frozen parameters are applied to older eligible rows and
check rows. Outcomes from check rows do not enter transform fitting; the test
also flips check outcomes and proves bitwise-identical check transforms. Using
the latest prior transform on older trainer rows is temporally unusual but is
still check-causal and is the exact predeclared recipe.

### Objective and optimizer

The candidate remains one unconstrained coefficient on top of the market
logit. The implemented objective and gradient are exactly:

`J(beta) = sum_i a_i * [logaddexp(0, eta_i) - y_i*eta_i] / sum_i a_i + 0.5*beta^2`

`dJ/dbeta = sum_i a_i*z_i*(sigmoid(eta_i)-y_i) / sum_i a_i + beta`.

The implementation validates finite, aligned binary inputs and positive
weights, uses the frozen L-BFGS-B settings, and rejects unsuccessful or
insufficiently converged fits. The focused tests independently cover the
analytic gradient by finite differences, invariance to a common weight scale,
deterministic fitting, and `gradient_at_zero = -weighted_moment`. A zero
coefficient preserves the market probabilities bit for bit.

### Folds, controls, scorer, and KEEP

- The chronological four-fold plan, 87-event complete check mask, source
  attrition/staleness gates, and decision cutoff are inherited unchanged.
- Exactly four candidate fits are permitted. Market, ordinary,
  market-only calibration, full offset, and Attempts 1-3 are loaded from the
  immutable hash-bound Attempt-3 artifact. Identity, ordering, outcome and
  market-probability parity are checked; control refits are trapped and remain
  zero.
- All eight arms are scored through the same proper-scoring path on the same
  complete-mask hash. Brier and log loss remain equal-event estimands.
  Schedule-day resampling and observed-game-week cluster sensitivity preserve
  the pooled equal-event estimand.
- KEEP retains all prior market/ordinary gates and additionally requires the
  candidate to beat archived Attempt 3 by more than `1e-12` in aggregate
  Brier and aggregate log loss and in Brier in at least three of four folds.
  Otherwise the incumbent remains Attempt 3. Other branches are retained.

### Provenance and boundaries

The pre-score lock explicitly states that Attempt 4 was selected after reading
Attempt-3 label-dependent aggregate, fold, date, week, coefficient and
information diagnostics. Results therefore remain adaptive, repeatedly
inspected opened-Train Discovery, not independent OOS evidence. The runner
records `route_dev_opened=false`, `sealed_final_opened=false`, zero provider
cost, no external fetch and `promotion_authorized=false`. Static inspection
found no network, provider or fetch client path in the new runner.

Failure receipts distinguish failures before fitting from optimizer/fitting
and scoring failures without claiming a completed result. Production source,
parent source, Controller recipe, passing Attempt-3 review, archived artifact,
candidate specification, cohort and check mask are hash-bound.

## Verification evidence

Pinned runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`.

Independent focused replay from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' \
  -m unittest -v \
  research.market_rsi.tests.test_nfl_market_all_prior_decay_composite_path_train_diagnostic
```

Result: **6/6 passed** in 3.981 seconds. These are synthetic-fixture tests;
their end-to-end test blocks socket creation and traps every archived-control
refit. Two earlier invocations used an incomplete module search path and
failed during test-module import before any test or runner execution; the
corrected command above is the evidentiary replay.

The implementation owner additionally reported the full settlement/offset/
calibration/Attempts 1-4 parent chain at **75/75 passed**, focused **6/6
passed**, plus clean `py_compile`, `tabnanny`, and added-file whitespace
checks. I treat 6/6 as independently reproduced and 75/75 as corroborating
implementation evidence.

## Decision

**PASS, P0 none, P1 none.** The frozen source implements the Controller's exact
Attempt-4 recipe and preserves the causal, scoring, archive-control and
adaptive-Discovery boundaries. No result exists yet and this review does not
authorize promotion, Dev/Final access, a retry, or any claim of profitability
or out-of-sample generalization.
