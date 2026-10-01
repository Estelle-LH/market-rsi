# MarketRecencyWeightedCompositeDispersion-v5 implementation

Status: exact frozen Attempt-5 recipe implemented and verified synthetically.
The real opened-Train runner was not invoked.

## Bindings and files

- Controller recipe:
  `29bd05297afca88a6949aa1e75241cf88da458be7018862317deb74618758436`.
- Attempt-4 PASS/REVERT result review:
  `c5b706e474af4ef1fac34eab1c19567f03c300f0c77f03bafcd129d09913f882`.
- Attempt-4 runner/test:
  `c9fc5b9d01a28181382ca47d9545ca7ce06c769b6165b482b84fc26df4537139` /
  `7183c64040bba0e02ae583b34050e87f6f4f15a42183e18eccba7a76626da2e7`.
- New runner
  `research/market_rsi/experiments/nfl_market_recency_weighted_composite_dispersion_train_diagnostic.py`:
  `7e384cb18a2b11595c0e6ab77446be59f538033c7fed842a3af572571e18a658`.
- New test
  `research/market_rsi/tests/test_nfl_market_recency_weighted_composite_dispersion_train_diagnostic.py`:
  `b6202edb2f68996424287352e0d090643f9c900e38d1f6b870b5323aec6f4547`.

No prior experiment source, test, Controller log or completed artifact was
modified.

## Exact delta

The runner preserves Attempt 3's exact three-week cohorts, unweighted path
transform and `0.25/0.50/1.00` candidate event weights.  It adds the fixed
mean of the exact 15/60/240-minute weighted probability-standard-deviation
columns.  On selected fit rows only, that family is residualized against
`[1,z_market,z_composite]`, rank three is required, and the residual is
standardized with the inclusive `1e-8` inactive rule.  No label enters the
transform.

The candidate fits exactly two unconstrained residual coefficients using
weighted mean Bernoulli NLL plus lambda-one squared L2.  Its analytic gradient,
zero initialization, convergence gate and endpoint rejection are frozen.  Two
zero coefficients return market probabilities bit-for-bit.  Exactly four new
fits occur.  Nine arms are scored on one common mask; all eight controls through
Attempt 4 are archive-only with zero refits.  KEEP still requires the market
and ordinary gates plus aggregate Brier/log and 3/4-fold Brier improvement over
the Attempt-3 incumbent.  REVERT keeps Attempt 3; Attempt 4 remains a branch.

Diagnostics include exact feature-name/formula resolution, transform rank and
singular values, raw/residual variance, raw and residual Pearson/Spearman
correlations against both market logit and the path composite, selected-fit
orthogonality, weighted/unweighted signed moments overall/by week, coefficients
and score deltas.  They do not tune or gate the candidate.

This reuses previously researched prior-only transformation, family
residualization and proper-score principles.  The equal dispersion average,
three-week window, residualizer, optimizer and thresholds are project choices.
Any result is adaptive opened-Train Discovery, not untouched OOS evidence.

## Verification

Pinned runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`
with `PYTHONPATH=.:research/market_rsi`.

- focused suite: **5/5 passed** in 4.483 seconds;
- settlement, offset, calibration and Attempts 1–5: **80/80 passed** in
  17.869 seconds;
- `py_compile`, `tabnanny` and added-file whitespace checks: passed;
- static scan: no network/provider/fetch or Dev/Final route.

Tests cover exact formula/name resolution, fit/check and label isolation,
rank-three failure, inactive zeroing across selected/older/check, nonfinite
pre-fit rejection, analytic finite-difference gradient, weight normalization,
deterministic fit, bitwise market nesting, logit/epsilon validation, exact four
fits, nine arms, archive parity, zero control refits, no network, truthful phase
receipts, and the exact Attempt-3 incumbent KEEP/REVERT rule.

## Fresh production command prepared, not executed

Fresh proposed artifact ID:
`first-real-train-diagnostic-market-recency-weighted-composite-dispersion-20260929-01`.

```sh
cd /Users/estelle/Developer/market-rsi
PYTHONPATH=.:research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' \
  research/market_rsi/experiments/nfl_market_recency_weighted_composite_dispersion_train_diagnostic.py \
  --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' \
  --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recency-weighted-composite-dispersion-20260929-01'
```

Freeze and independently review this exact snapshot before any real run.  No
retry may reuse an occupied artifact ID.
