# MarketOrthogonalPricePath-v1 implementation log

Status: implementation and synthetic verification complete; real opened-Train
runner deliberately not invoked by this implementation task.

## Bound inputs read

- `research/market_rsi/AGENTS.md`, including the 2026-09-29 opened-Train
  Discovery override.
- Controller recipe
  `AGENT_LOG_POST_CALIBRATION_NEXT_CONTROLLER_2026-09-29.md`, verified SHA-256
  `8b5fbdef19279098759169d5a83ced8077abfe5c56b787667bd9dbb0a5632719`.
- Frozen settlement, full-offset and market-only calibration runners, tests and
  completed scorecards.
- `indicator-prediction-evals` instructions, evaluation gates, and
  `sign-and-collinearity.md`.

No Dev/Final data, network, provider, release, promotion or real Train runner
was opened or used.

## Files owned

- `research/market_rsi/experiments/nfl_market_orthogonal_price_path_train_diagnostic.py`
  - SHA-256 `af4508f0c808fbc236daae6607343c47238db26e2148289a08670fe71102f380`
- `research/market_rsi/tests/test_nfl_market_orthogonal_price_path_train_diagnostic.py`
  - SHA-256 `71e576f4a74aba6a334d09f76dc3d2023122b126a0b11ded8b2ddec6e2aad40a`
- This log only.

No frozen parent runner, test or artifact was modified.

## Implemented recipe

- Exact-name feature selection for the three VWAP and three signed
  last-minus-first columns.
- Fixed `g = p - mean(VWAP_15,60,240)` and
  `d = mean(move_15,60,240)` summaries.
- Fit-only market-logit scaling and `numpy.linalg.lstsq(..., rcond=1e-12)`
  residualization against `[1,z_market]`, rank exactly two.
- Per-family fit mean/population-standard-deviation scaling; a standard
  deviation at most `1e-8` makes the family inactive and zero on fit and check
  without dropping an event.
- Candidate `[z_market,z_g,z_d]` with the reviewed lambda-one offset solver.
- Fit-row information diagnostics occur before the candidate fit.  Check-row
  diagnostics occur only after predictions and have no gating/tuning path.
- Structured transform shape, nonfinite and rank failures are classified as
  `INVALID_DATA_QUALITY` and persist a failure receipt.
- Recomputed ordinary and market-only calibration controls are required to
  match the frozen calibration artifact within `1e-10`; full-offset
  predictions remain archive-only.
- Five-arm scorecard, paired proper scores, complete-day and observed-week
  resampling, fold coefficients/corrections, raw/residual variance and
  Pearson/Spearman/signed-moment diagnostics.

## Fit-budget semantics

The runner performs exactly twelve fits on a valid four-fold execution:

- four width-one `fit_offset_ridge` calibration controls;
- four width-three `fit_offset_ridge` candidate fits;
- four 17-column ordinary `LogisticRegression` fits;
- zero archived full-offset refits.

The focused end-to-end test counts each width/class explicitly.  An earlier
review concern about a duplicated `_fit_and_predict` pass is not present in
this source; the call-counter regression would detect it as 8+8 offset calls
instead of the required 4+4.

## Verification

Exact runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`
with `PYTHONPATH=research/market_rsi`.

- Focused suite: 17/17 passed.
- Focused plus settlement, full-offset and calibration adjacent suites: 51/51
  passed in 4.797 seconds.
- `py_compile`: passed for runner and test.
- `git diff --check` for owned source/test: passed.

Coverage includes exact formulas, no fit/check leakage, label-free transforms,
fit residual orthogonality, rank and nonfinite fail-closed behavior, inactive
families, market/calibration nesting, finite-difference gradient and penalty,
determinism, unused-column invariance, common masks, label time, 600/601-second
staleness, archive parity, unequal-day resampling, exact KEEP, diagnostic
non-gating, exact fit counts, no network, and structured failure recovery.

## Production entry prepared, not executed

Fresh proposed artifact ID:
`first-real-train-diagnostic-market-orthogonal-price-path-20260929-01`.

```sh
cd /Users/estelle/Developer/market-rsi
PYTHONPATH=research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' \
  research/market_rsi/experiments/nfl_market_orthogonal_price_path_train_diagnostic.py \
  --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' \
  --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-orthogonal-price-path-20260929-01'
```

The Supervisor should independently review the two owned code files and their
hashes before executing this command.  Any repaired implementation must use a
fresh production artifact ID.
