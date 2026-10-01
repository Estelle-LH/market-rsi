# MarketAllPriorDecayCompositePath-v4 implementation log

Status: the exact frozen Attempt-4 recipe is implemented and verified on
synthetic fixtures.  The real opened-Train runner was not invoked, so no real
candidate attempt was consumed.

## Exact bindings and files

- Controller recipe:
  `fab9f134f2e1523265a429fbd8ff2fc9a6ca98f37216a60d7371683e43d01595`.
- Passing Attempt-3 result review:
  `016930f4d027be2ecee79b61beb76a914eb3198cc853c632cc79d764fcceb0ad`.
- Attempt-3 runner/test:
  `05af717084499618c99fefd034972681d4acef12b226b5fc8b8a4513c26fdbd1` /
  `9d2491170a1862a4239118ad8ff03d95e5c4ed5e682e131a5023ae4ac4b1363d`.
- New runner
  `research/market_rsi/experiments/nfl_market_all_prior_decay_composite_path_train_diagnostic.py`:
  `c9fc5b9d01a28181382ca47d9545ca7ce06c769b6165b482b84fc26df4537139`.
- New focused test
  `research/market_rsi/tests/test_nfl_market_all_prior_decay_composite_path_train_diagnostic.py`:
  `7183c64040bba0e02ae583b34050e87f6f4f15a42183e18eccba7a76626da2e7`.

No prior runner, test, Controller log or completed artifact was modified.

## Implemented delta

The exact Attempt-3 three-week, fit-only representation and common 87-event
scoring boundary are reused.  The sole scientific change is candidate trainer
support: every fit row from a numeric game-week strictly earlier than the first
check week is included, with event weight
`2**(week_index-latest_eligible_week_index)`.  There is no normalization by
week size or class.  The unchanged one-parameter market-offset objective is
weighted mean Bernoulli NLL plus `0.5*w_composite^2` with the same analytic
gradient, lambda, optimizer and rejection policy.

Production gates freeze all-prior fold sizes `107/120/148/177`, outcome and
per-week counts, total and squared weights, and class weight totals.  The
runner records an ordered identity/week/outcome/weight ledger, per-week and
per-class totals, Kish effective rows, unweighted and weighted signed moments,
and `gradient_at_zero = -weighted_moment`.  These diagnostics do not select,
tune or gate the recipe.

Exactly four new one-parameter fits occur.  Market, ordinary, calibration,
full offset and Attempts 1–3 are loaded from the hash-bound Attempt-3 artifact
with zero control refits.  The scorecard has eight arms on one common mask.
KEEP additionally requires aggregate Brier and log-loss improvement over the
Attempt-3 incumbent and Brier wins in at least three folds.  All results remain
adaptive, repeatedly inspected opened-Train Discovery.

This is a direct reuse of the previously researched prior-only weighting and
proper-score principles; no new method or uncertain implementation assumption
was introduced that required a new external literature search.  The
one-week half-life, all-prior support and exact KEEP thresholds remain project
choices, not literature consensus.

## Verification

Runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`
with `PYTHONPATH=.:research/market_rsi`.

- focused Attempt-4 suite: **6/6 passed** in 3.817 seconds;
- settlement + offset + calibration + Attempts 1–4: **75/75 passed** in
  13.952 seconds;
- runner/test `py_compile` with bytecode redirected to `/tmp`: passed;
- `tabnanny` and added-file whitespace checks: passed;
- static scan found no network/provider/fetch or Dev/Final client path.

Coverage includes numeric week ordering and strict same-week exclusion,
row-order-independent exact exponential weights, all-prior support, class and
week totals, squared weights and Kish arithmetic, finite-difference gradient,
weight-scale invariance, deterministic fitting, transform array parity,
check-label non-use, bitwise zero-coefficient market nesting, exact four
optimizer calls, traps for every archived control refit, exact Attempt-3
archive parity, no network and truthful pre-fit/optimizer failure receipts.

## Production entry prepared, not executed

Fresh proposed artifact ID:
`first-real-train-diagnostic-market-all-prior-decay-composite-path-20260929-01`.

```sh
cd /Users/estelle/Developer/market-rsi
PYTHONPATH=.:research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' \
  research/market_rsi/experiments/nfl_market_all_prior_decay_composite_path_train_diagnostic.py \
  --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' \
  --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-all-prior-decay-composite-path-20260929-01'
```

Freeze and independently review the exact hashes before execution.  Any repair
requires a fresh artifact ID; the runner never retries an occupied ID.
