# MarketOnlyRidgeCalibration-v1 implementation — 2026-09-29

Completed at `2026-09-29T17:44:16Z`.

Status: **IMPLEMENTED AND SYNTHETICALLY VERIFIED; REAL TRAIN NOT RUN.**

## Scope and result

Implemented the Controller-frozen `MarketOnlyRidgeCalibration-v1` recipe as a
thin sibling of the reviewed full-offset runner. This task created only:

- `research/market_rsi/experiments/nfl_market_only_ridge_calibration_train_diagnostic.py`
- `research/market_rsi/tests/test_nfl_market_only_ridge_calibration_train_diagnostic.py`
- this log

No existing source or artifact was changed. No resident real Train experiment,
Dev/Final access, network request, provider call, paid fit, publication,
promotion, or deployment occurred.

The runner imports and directly reuses the exact offset runner's materializer,
600-second common gate, canonical mask gate, two-parameter-compatible objective
and optimizer, probability contract, proper scorer, KEEP rule, cluster
resampling, source constants, runtime validation, and parent bindings.

## Frozen implementation

- Prediction-time candidate inputs are only the market probability and its
  derived unstandardized logit.
- A one-column fit-only `StandardScaler` produces `z`; its mean and scale must
  equal column 0 of the unchanged 17-column fit scaler within `1e-12`.
- `eta = market_logit + b + w*z`.
- The objective is mean Bernoulli NLL plus `0.5*(b²+w²)`, with lambda 1,
  both parameters penalized, zero initialization, float64, and the exact
  reviewed L-BFGS-B convergence/finiteness/gradient gates.
- Every fold records `b`, `w`, `mu`, `scale`, equivalent affine-logit intercept
  `b-w*mu/scale`, and slope `1+w/scale`.
- Exactly four calibration fits and four unchanged ordinary-reference fits
  occur. The archived full-offset arm is never refit.
- The complete archived full-offset `-02` artifact is bound by all seven file
  hashes, its internal manifest hashes, completed boundary receipt, original
  parent-control parity, exact row identity/order/outcomes, market equality,
  and ordinary tolerance `1e-10`.
- The scorecard explicitly names market, ordinary reference, new market-only
  calibration, and archived full offset. It returns fold and aggregate proper
  scores plus relevant pairwise deltas.
- Corrected inference retains the equal-event 87-game primary estimand,
  resamples 20 complete schedule dates, reports per-unit sums/counts/means,
  and separately labels the seven observed-week sensitivity with partial
  one-game Week 14 disclosed.
- KEEP is calibration versus market and ordinary only: both aggregate proper
  losses must improve by more than `1e-12`, and calibration Brier must beat
  each reference in at least 3/4 folds. Full-offset attribution is not another
  replacement gate. All branches remain preserved.

## Exact bindings

| Binding | SHA-256 |
| --- | --- |
| Controller proposal | `cd40d3e9dababfd0da1548c4ea61e505e12fa6de2c1af0003f4f787179bf5622` |
| Offset runner | `6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f` |
| Offset tests | `409fd88d93c59b5d0bb25a1765471ad9249c0a5872cc77d31e69922a77fd0f41` |
| Archived offset manifest | `2296835ec561858383750cba8d81124daf479de1caa288908d98503a7b93acc6` |
| Archived offset predictions | `d917a1980bc0b4621ee9ab0cdc6672b47e58cbea0ae4ed335c952d40dd51288c` |
| Archived offset scorecard | `276423d4cfe97ca1198f6f95a420036bf53b7f756bdd021d691951bc4b367907` |
| Archived offset pre-score lock | `264341f66c382001c86a01ab45835b03780b06e926d79176b141d6c86d3492a1` |

All other archived file hashes are encoded in the runner and validated before
any fit. The deeper parent runner, tests, probability contract, proper scorer,
runtime, source manifest, cohort, materialized population, exclusion, folds,
staleness, and canonical check-mask bindings remain inherited and fail closed.

New files at verification:

| File | SHA-256 |
| --- | --- |
| Calibration runner | `71d329468c865246616b8cb1ee7b284a488c9ad382f2bda830bb529e383cc191` |
| Focused tests | `548d8d633fc2007414d10874b11300442ebb97719eb101bb451cd3bd8d755bb0` |

## Verification actually run

Compile:

```text
PYTHONPYCACHEPREFIX=/tmp/market-rsi-calibration-pycache PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi:/Users/estelle/Developer/market-rsi '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B -m py_compile research/market_rsi/experiments/nfl_market_only_ridge_calibration_train_diagnostic.py research/market_rsi/tests/test_nfl_market_only_ridge_calibration_train_diagnostic.py
```

Result: passed.

Focused plus both parent-adjacent suites:

```text
PYTHONPYCACHEPREFIX=/tmp/market-rsi-calibration-pycache PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi:/Users/estelle/Developer/market-rsi LOKY_MAX_CPU_COUNT=1 '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B -m unittest research.market_rsi.tests.test_nfl_market_only_ridge_calibration_train_diagnostic research.market_rsi.tests.test_nfl_market_offset_ridge_train_diagnostic research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic
```

Result: **34/34 passed** in 1.372 seconds.

Direct coverage includes one-column finite-difference gradient, zero-residual
market recovery to floating precision, mean-loss and both-parameter penalty,
fit-only scale identity, invariance to arbitrary changes in the other 16 check
columns, staleness 600/601 behavior, canonical-mask mutation rejection,
archived all-file/hash/identity/outcome/control parity, unequal-date event
weighting and per-unit arithmetic, exact KEEP behavior, deterministic
end-to-end output, no network, exact four calibration solver calls, eight
total local fits, and zero archived-offset refits.

Diff hygiene:

```text
git diff --check -- research/market_rsi/experiments/nfl_market_only_ridge_calibration_train_diagnostic.py research/market_rsi/tests/test_nfl_market_only_ridge_calibration_train_diagnostic.py
```

Result: passed with no output.

## Production command prepared, not executed

```text
PYTHONPYCACHEPREFIX=/tmp/market-rsi-calibration-pycache PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi LOKY_MAX_CPU_COUNT=1 '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B -m experiments.nfl_market_only_ridge_calibration_train_diagnostic --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-only-ridge-calibration-20260929-01'
```

The fresh ID remains unused by this task. Independent pre-score review should
verify the three new-file hashes before any real execution.
