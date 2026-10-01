# MarketOffsetRidgeLogistic-v1 implementation — 2026-09-29

## Result

Completed at `2026-09-29T17:19:18Z`.

Status: **IMPLEMENTED, REPAIRED AFTER A PRE-SCORE FAILURE, AND SYNTHETICALLY
VERIFIED; NO SCIENTIFIC REAL-TRAIN RESULT YET.**

Implemented the Controller-frozen `MarketOffsetRidgeLogistic-v1` experiment in
one new runner and one focused test module. The initial implementation task did
not run resident real Train. A later Supervisor-launched attempt failed before
scoring as recorded below. No Dev/Final, network, provider, paid fit,
publication, promotion, or deployment path was used.

Owned files:

- `research/market_rsi/experiments/nfl_market_offset_ridge_train_diagnostic.py`
- `research/market_rsi/tests/test_nfl_market_offset_ridge_train_diagnostic.py`
- this implementation log

The reviewed parent runner and its tests were not edited. The new runner
imports and directly reuses the parent event materializer, chronological fold
builder, prediction-record builder, simple metrics, proper-scorer adapter, and
paired-score view. It adds only the frozen offset learner, the common input
gate, parent-control parity, corrected grouped inference, and new artifact
bindings needed for this experiment.

## Failed real attempt `-01` and narrow repair

After the initial implementation, the Supervisor launched the separately
authorized real attempt:

`first-real-train-diagnostic-market-offset-ridge-20260929-01`

It failed before scoring with `check mask differs from frozen parent`. The
receipt says `fit_started=true`, `scoring_started=false`, all protected,
network, and paid flags false, and provider cost `$0`. The directory contains
no `predictions.csv`, `scorecard.json`, or completed `manifest.json`, so this
is a **pre-score implementation failure, not a scientific result and not a
KEEP/REVERT observation**.

Exact failed-attempt artifact hashes:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `2d6d6327a59f77ac20b945fe7eece2c982e16da671aabf8fc96f48a4573f72a9` |
| `failure.json` | `ed25651c9a96d80804bd7efddbf0d93e2c6de7821c23d3a486a54c936517a786` |
| `input_receipts.json` | `7de568e2c993ac5e63036f2d0ff506d025a336cd2cf0353d8aeda51ffb44e5bd` |
| `pre_score_lock.json` | `3ea16fc006ce6307f5af596d6a904717d452ac901ad0dead0299fed5a64c795c` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

Root cause: the gate directly hashed check rows in fold order, producing
`a2996dade7978016824d6923eebe4dcdbe253a0c01a9fde0feb4a7f3463391f2`.
The frozen proper scorer first validates trusted rows through
`validate_probability_rows` and sorts keys by
`(cutoff_ms, event_id, market_id)`, producing the expected
`eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.

The repair does not weaken or remove the gate. It now passes trusted row
dictionaries through the same frozen probability-contract canonicalization
used by the scorer, then digests those canonical keys before scoring. A new
regression deliberately presents valid rows in noncanonical order, proves the
canonical commitment passes, and proves a changed event key still fails.
No model, feature, data, fold, objective, score, or decision rule changed, and
this repair task did not rerun real Train.

## Implemented frozen behavior

- All 17 fold-standardized inputs remain present, including `market_logit`.
- The unstandardized market logit is a fixed coefficient-1 offset.
- The residual intercept and all 17 residual coefficients use mean Bernoulli
  NLL plus `0.5 * ||theta||^2`, with all-zero initialization.
- `scipy.optimize.minimize(method="L-BFGS-B")` uses the analytic gradient,
  `maxiter=1000`, `gtol=1e-8`, `ftol=1e-12`, and float64. Optimizer failure,
  nonfinite results, or final gradient infinity norm above `1e-6` aborts.
- The inclusive 600-second latest-trade gate is checked before any fit or
  score. Any required binary row over the limit produces
  `INVALID_DATA_QUALITY`; it is not filtered or replaced.
- Real execution requires the exact 195/42 population, exact 194 binary rows,
  and the sole exclusion at ordinal 53: `2025_04_GB_DAL`, `2025-09-28`,
  `unresolved_outcome`.
- Real execution requires exact parent market/ordinary row identity and order,
  exact market probabilities, and ordinary probability agreement within
  `1e-10` against the frozen `-02` prediction CSV.
- KEEP requires candidate Brier and log loss to beat both market and ordinary
  by more than `1e-12`, plus at least 3/4 candidate Brier fold wins against
  each reference. KEEP/REVERT changes only the Discovery current best; the
  candidate and prior HGB branches remain retained and ordinary remains only
  an ordinary reference.
- The unchanged proper scorer remains present. New inference resamples whole
  source schedule dates and recomputes the pooled equal-event delta in every
  draw. NFL week evidence is explicitly an observed-week-cluster sensitivity:
  the fixed real check population spans weeks 08–14 with counts
  `13/14/14/15/14/16/1`, and Week 14 is disclosed as a partial right-edge
  cluster retained in the 87-event denominator. Per-date and per-week event
  counts are emitted.
- The pre-score lock separates literature-supported evaluation principles,
  project-chosen parameters, and the unvalidated residual-information
  hypothesis. It also records the incumbent/branch semantics.

## Exact source and runtime bindings

The runner validates these identities before any fit:

| Binding | SHA-256 |
| --- | --- |
| Controller proposal | `7345349cb0560a23e447b1e89b83e1c3de49adec6b1ada967a5a909ff1ab1314` |
| Parent runner | `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b` |
| Parent tests | `6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927` |
| Proper scorer | `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b` |
| Probability contract | `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74` |

Runtime validation requires the persistent local MarketRSI CPython 3.12.3
executable plus NumPy 1.26.4, SciPy 1.14.0, and scikit-learn 1.6.1. The full
runtime identity and source hashes are written to both input receipts and the
pre-score lock.

New implementation hashes at completion:

| File | SHA-256 |
| --- | --- |
| Offset runner | `6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f` |
| Focused tests | `409fd88d93c59b5d0bb25a1765471ad9249c0a5872cc77d31e69922a77fd0f41` |

## Verification actually run

Compile check:

```text
PYTHONPYCACHEPREFIX=/tmp/market-rsi-offset-pycache PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi:/Users/estelle/Developer/market-rsi '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B -m py_compile research/market_rsi/experiments/nfl_market_offset_ridge_train_diagnostic.py research/market_rsi/tests/test_nfl_market_offset_ridge_train_diagnostic.py
```

Result: passed.

Focused plus parent-adjacent unit tests:

```text
PYTHONPYCACHEPREFIX=/tmp/market-rsi-offset-pycache PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi:/Users/estelle/Developer/market-rsi LOKY_MAX_CPU_COUNT=1 '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B -m unittest research.market_rsi.tests.test_nfl_market_offset_ridge_train_diagnostic research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic
```

Result after the mask-gate repair: **24/24 passed** in 0.597 seconds.

Coverage includes analytic-gradient finite differences, exact zero-residual
market recovery, mean-loss and all-parameter penalty semantics, 600-pass /
601-fail staleness, exact exclusion identity, fit-only scaling, deterministic
candidate output, common masks, frozen-control parity and rejection, optimizer
success/gradient gates, unequal-size cluster arithmetic, exact week parsing,
right-edge partial-week disclosure, exact KEEP rules, truthful scoring-phase
failure receipts, scorer-canonical mask order plus key-mutation rejection,
no-network synthetic end-to-end execution, and the nine
unchanged parent tests.

Diff hygiene:

```text
git diff --check -- research/market_rsi/experiments/nfl_market_offset_ridge_train_diagnostic.py research/market_rsi/tests/test_nfl_market_offset_ridge_train_diagnostic.py
```

Result: passed with no output.

## Remaining boundary

This repair task did not rerun the real Train experiment. The implementation
is ready for an independent pre-score review. A later real run must use a fresh
persistent artifact ID, pass every source/runtime/staleness/control check, and
remain opened-Train Discovery only.
