# MarketRecentCompositePath-v2 implementation log

Status: exact frozen Attempt-2 recipe implemented and synthetic verification
complete.  The real opened-Train runner was deliberately **not** invoked, so
this implementation work does not consume a continuous-Discovery candidate
attempt.

## Bound inputs and boundaries

- Controller recipe
  `AGENT_LOG_DISCOVERY_ATTEMPT2_CONTROLLER_2026-09-29.md`, SHA-256
  `2d6f26fa8f83402fea1612297966792d27eba64796c73342170105507a44e061`.
- Passing Attempt-1 independent result review
  `AGENT_LOG_MARKET_ORTHOGONAL_PRICE_PATH_V1_RESULT_INDEPENDENT_REVIEW_2026-09-29.md`,
  SHA-256
  `ea42908cbd95c93782a889a4e13f32e4b85009d03a95a1bd044a079117199f83`.
- Immutable seven-file Attempt-1 artifact binding and its frozen market,
  ordinary, calibration, full-offset, and Attempt-1 predictions.
- Existing settlement, offset, calibration and Attempt-1 runners/tests, plus
  the `indicator-prediction-evals` causality, sign and collinearity guidance.

The implementation opened no protected Dev/Final data, network/provider
client, paid service, publication, release or promotion path.

## Files owned

- `research/market_rsi/experiments/nfl_market_recent_composite_path_train_diagnostic.py`
  - SHA-256
    `d005d9fe5df0c33c1eeb5aa8ba2d5e7ebbb5103c9b0e7935bb5ac3de8946c70f`
- `research/market_rsi/tests/test_nfl_market_recent_composite_path_train_diagnostic.py`
  - SHA-256
    `4aac0a60e9e2b4bbffd9999bc1259d9c27df2b8c4b9be259d8dd22ceb3f6ca77`
- This implementation log only.

No frozen Controller log, parent runner/test, or completed artifact was
modified.

## Implemented recipe

- Strict numeric game-week parsing; per fold the candidate selects exactly the
  three largest fit weeks strictly before the earliest check week.  Same-week
  outcome-known rows remain explicitly ineligible.  Frozen production gates
  require the exact `44/43/41/43` row cohorts, exact weeks/class counts and
  per-week counts, at least 30 rows, both classes, and causal label timing.
- Reuses Attempt-1's exact named `g` and `d` causal feature formulas, then fits
  market scaling, rank-two `[1,z_market]` residualization, family scaling and
  the equal-weight standardized composite on selected recent rows only.
  Older eligible rows and check rows only receive the frozen transform.
- Fits one unconstrained parameter per fold:
  `eta = market_logit + w_composite*z_composite`, using mean Bernoulli NLL,
  lambda-one penalty, analytic gradient and the frozen L-BFGS-B convergence
  gates.  A zero coefficient returns the original market-probability array
  bit-for-bit.
- Performs exactly four candidate optimizer calls.  All five controls are
  archive-only and all control refit counts are zero.
- Emits six-arm identical-mask proper scores, fold results, complete-day and
  observed-week equal-event resampling, frozen KEEP/REVERT semantics, and the
  full population/breadth accounting.
- Reports selected/older/check row/date/week labels and counts, named raw and
  residual composite variance fractions, market-logit correlations,
  selected-fit orthogonality, family/composite correlations and signed
  moments.  These diagnostics cannot gate, tune or change predictions.
- Binds the exact Controller decision and the passing Attempt-1 review before
  any fit.  Admitted-run validation failures persist a structured fresh-ID
  receipt.  `fit_started` changes only immediately before the first optimizer
  invocation; `scoring_started` changes only immediately before scoring.
- Candidate probabilities retain the frozen `[1e-6,1-1e-6]` rejection rule;
  there is no clipping, fallback or retry-in-place.
- Provenance explicitly says the recipe was adaptively selected after reading
  label-dependent Attempt-1 fold/date/week/family evidence and a new read-only
  recent signed-moment inventory.  This is reused Train Discovery, not
  aggregate-only or untouched validation.

## Verification

Exact runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`
with `PYTHONPATH=.:research/market_rsi`.

- Focused v2 suite: **12/12 passed** in 2.359 seconds.
- Settlement + offset + calibration + Attempt-1 + v2 combined regression:
  **63/63 passed** in 7.319 seconds.
- `py_compile`: passed for runner and focused test with a persistent-code-free
  `/tmp` bytecode cache.
- Independent moving-snapshot replay found no remaining P0/P1, and its static
  scan found no network/provider/Dev/Final client path.  Final hashes above
  still require the normal frozen-source independent review before execution.

Focused coverage includes exact formula and transform isolation, no future or
label leakage, strict week causality, expected cohort gates, rank/class/count
fail-closed paths, residual orthogonality, inactive behavior, analytic
gradient/penalty, deterministic fit, bitwise market nesting, extreme
probability rejection without clipping, immutable archive parity, exact four
optimizer calls, explicit traps for every control refit path, common masks,
grouped resampling, KEEP semantics, diagnostic non-gating, no network, and
truthful pre-fit/post-fit structured failure receipts.

The synthetic end-to-end fixture uses a deterministic four-phase causal price
path so every three-row test-only recent cohort is nondegenerate and its check
predictions remain within the production probability contract.  This changes
only synthetic source construction; production rejection behavior is
unchanged and separately tested.

## Production entry prepared, not executed

Fresh proposed artifact ID:
`first-real-train-diagnostic-market-recent-composite-path-20260929-01`.

```sh
cd /Users/estelle/Developer/market-rsi
PYTHONPATH=.:research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' \
  research/market_rsi/experiments/nfl_market_recent_composite_path_train_diagnostic.py \
  --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' \
  --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recent-composite-path-20260929-01'
```

The Supervisor should freeze and independently review the exact runner/test
hashes before executing this command.  Any source repair after that review
requires a new artifact ID; the runner itself never retries an occupied ID.
