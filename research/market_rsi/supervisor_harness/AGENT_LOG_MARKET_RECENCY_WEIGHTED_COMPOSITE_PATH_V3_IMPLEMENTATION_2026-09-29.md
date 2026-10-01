# MarketRecencyWeightedCompositePath-v3 implementation log

Status: frozen Attempt-3 recipe implemented and verified synthetically.  The
real opened-Train runner was not invoked, so no candidate execution attempt was
consumed.

## Exact bindings and files

- Controller recipe SHA-256:
  `1def15625da467de6b6130dc7f7bf3adb08ae7da00ee43de9900c1d5a73283cc`.
- Passing Attempt-2 result review SHA-256:
  `6800cd9647508963a2eb1efa525f5489c04fd9e3c920fa2a495fba0f417d9c6d`.
- Runner
  `research/market_rsi/experiments/nfl_market_recency_weighted_composite_path_train_diagnostic.py`:
  `05af717084499618c99fefd034972681d4acef12b226b5fc8b8a4513c26fdbd1`.
- Focused test
  `research/market_rsi/tests/test_nfl_market_recency_weighted_composite_path_train_diagnostic.py`:
  `9d2491170a1862a4239118ad8ff03d95e5c4ed5e682e131a5023ae4ac4b1363d`.
- This log only.  No parent runner/test, Controller log or completed artifact
  was modified.

The runner binds all seven Attempt-2 artifact hashes.  It reuses the exact
three-week selection and unweighted transform, then assigns every event in the
oldest/middle/newest selected week weight `0.25/0.50/1.00`.  The objective is
weighted mean Bernoulli NLL normalized by total event weight plus
`0.5*w_composite^2`; its analytic gradient is frozen and tested.  The real
weight sums are `26.0/24.25/24.25/25.0`.

The report distinguishes weighted moment, actual gradient at zero and
coefficient descent direction.  It enforces
`gradient_at_zero = -weighted_mean[z*(y-p_market)]`; the Controller narrative's
reversed gradient-sign sentence was not implemented.  Fixed-order diagnostics
include the per-event identity/week/outcome/weight ledger, class/week totals,
squared-weight total, Kish effective rows, and unweighted/weighted overall and
per-week signed moments.  Diagnostics remain non-gating.

Exactly four new one-parameter fits occur.  Market, ordinary, calibration,
full offset, Attempt 1 and Attempt 2 are immutable controls with zero refits.
The scorecard has seven arms, one common 87-event mask, unchanged proper
scores/resampling/KEEP rule, and structured truthful phase receipts.  No
network/provider/Dev/Final/release/promotion path was added.

## Verification

Runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`
with `PYTHONPATH=.:research/market_rsi`.

- focused Attempt-3 suite: **6/6 passed** in 3.083 seconds;
- settlement + offset + calibration + Attempt 1 + Attempt 2 + Attempt 3:
  **69/69 passed** in 9.854 seconds;
- `py_compile` with bytecode redirected to `/tmp`: passed.

Coverage includes scrambled row order and unequal week counts, exact totals,
class totals, squared weights and Kish arithmetic, finite-difference gradient,
global weight-scale invariance, gradient-zero negation, parent-transform array
parity, check-label non-use, deterministic fit, bitwise zero-coefficient market
nesting, exact four optimizer calls, traps for every control refit, archive
parity, no network and truthful pre-fit/optimizer failure receipts.

## Production entry prepared, not executed

Fresh proposed artifact ID:
`first-real-train-diagnostic-market-recency-weighted-composite-path-20260929-01`.

```sh
cd /Users/estelle/Developer/market-rsi
PYTHONPATH=.:research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' \
  research/market_rsi/experiments/nfl_market_recency_weighted_composite_path_train_diagnostic.py \
  --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' \
  --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recency-weighted-composite-path-20260929-01'
```

Freeze and independently review the exact hashes before execution.  Any repair
requires a fresh artifact ID; the runner never retries an occupied ID.
