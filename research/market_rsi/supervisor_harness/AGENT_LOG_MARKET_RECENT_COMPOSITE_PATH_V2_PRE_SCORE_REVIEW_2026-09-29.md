# MarketRecentCompositePath-v2 — independent pre-score review

Review completed: `2026-09-29`.

## Verdict

**PASS at 0 P0 / 0 P1** for one real opened-Train Attempt-2 execution using
the fresh artifact ID
`first-real-train-diagnostic-market-recent-composite-path-20260929-01`.

This verdict is limited to the exact frozen implementation below.  The review
did not run the real Train experiment, fit on resident Train data, read
protected Dev/Final, access a network/provider, spend money, publish, promote,
or change any model, scorer, data or boundary.  Only synthetic tests and
read-only source/artifact checks were performed.

## Exact frozen snapshot

| Item | SHA-256 |
| --- | --- |
| Attempt-2 Controller recipe | `2d6f26fa8f83402fea1612297966792d27eba64796c73342170105507a44e061` |
| runner | `d005d9fe5df0c33c1eeb5aa8ba2d5e7ebbb5103c9b0e7935bb5ac3de8946c70f` |
| focused tests | `4aac0a60e9e2b4bbffd9999bc1259d9c27df2b8c4b9be259d8dd22ceb3f6ca77` |
| implementation log | `77ad040c3c9e8b430d3adb092f016ec7ba9f459b7ea3cb3614bed53df1e95bd1` |
| Attempt-1 runner parent | `af4508f0c808fbc236daae6607343c47238db26e2148289a08670fe71102f380` |
| Attempt-1 tests parent | `71e576f4a74aba6a334d09f76dc3d2023122b126a0b11ded8b2ddec6e2aad40a` |
| passing Attempt-1 result review | `ea42908cbd95c93782a889a4e13f32e4b85009d03a95a1bd044a079117199f83` |
| candidate-spec digest | `bf8c466e745679e4e1a6861f930659fa4633c41c3445a539634048782ef6ed82` |

The execution-identity validator independently reproduced the persistent
CPython 3.12.3 runtime and the complete parent chain, including NumPy 1.26.4,
SciPy 1.14.0, scikit-learn 1.6.1, proper scorer
`64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b`
and probability contract
`7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74`.
The runner validates this chain, the Controller recipe and the passing
Attempt-1 result review before any optimizer invocation.

## Methodology and implementation findings

### Population, timing and recent-cohort causality

- Production inherits and rechecks the exact 195-event / 42-date source, 194
  binary materializations, sole `2025_04_GB_DAL / unresolved_outcome`
  exclusion, materialized-key digest, inclusive 600-second staleness gate,
  kickoff-minus-15-minute cutoff, token/home orientation, 22-date initial fit,
  four five-date expanding checks, and exact 87-event check mask
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
- Game weeks are parsed numerically from the exact `YYYY_WW_AWAY_HOME`
  convention.  Each fold selects the three largest fit-week labels strictly
  below the earliest check-week label.  Same-week outcome-known rows are
  explicitly ineligible, not silently treated as older eligible history.
- Production requires the frozen recent cohorts exactly: 44, 43, 41 and 43
  rows; weeks `05/06/07`, `06/07/08`, `08/09/10`, and `10/11/12`; class counts
  `22/22`, `26/17`, `20/21`, and `25/18`; and per-week counts
  `14/15/15`, `15/15/13`, `13/14/14`, and `14/15/14`.  It also requires at
  least 30 rows, both outcome classes and every selected outcome to be
  strictly available before the first check cutoff.  Failure is structured
  `INVALID_DATA_QUALITY`; there is no expanding-history fallback.

### Transform, objective and fit budget

- The candidate reuses Attempt 1's exact named causal formulas
  `g = p_market - mean(VWAP_15m,VWAP_60m,VWAP_240m)` and
  `d = mean(last_minus_first_15m,last_minus_first_60m,last_minus_first_240m)`.
  The market scaler, rank-two `[1,z_market]` least-squares residualizer with
  `rcond=1e-12`, residual-family scalers and composite scaler are fitted only
  on the selected recent rows.  Older eligible and check rows only receive
  the frozen transform.  No labels enter row selection or preprocessing.
- Inclusive family/composite inactivity at population standard deviation
  `<=1e-8` sets the corresponding values to zero without dropping events.
  The fixed representation is exactly
  `c_raw=(z_g+z_d)/2`, re-standardized on selected fit rows to `z_c`.
- The trainer is exactly one unconstrained float64 parameter:
  `eta=m+w_c*z_c`, with mean Bernoulli NLL plus `0.5*w_c^2`, lambda one,
  zero initialization, analytic gradient and frozen L-BFGS-B settings.  It
  requires success, finite outputs and final gradient infinity norm at most
  `1e-6`.  There is no intercept, market-slope refit, sign constraint, sweep,
  clipping, fallback, retry or post-score change.
- When `w_c` is exactly zero, prediction returns a copy of the original market
  probability array, preserving the incumbent bit-for-bit; a regression uses
  `numpy.array_equal`.  Nonzero predictions remain subject to the unchanged
  `[1e-6,1-1e-6]` rejection contract, with an explicit no-clipping test.
- The candidate calls exactly four optimizers, one per outer fold.  Market,
  ordinary LogisticRegression, market-only calibration, full offset and
  Attempt 1 are immutable archive controls.  The Attempt-1 artifact is bound
  by all seven file hashes; identities, order, outcomes and market values are
  checked exactly.  Tests trap every control-refit route and observe four
  candidate fit calls, four optimizer calls and zero control refits.

### Scoring, inference and decision semantics

- The scorecard has six named arms and uses the same 87 rows for every arm.
  All pairwise proper-scorer mask hashes must agree.  Equal-event Brier is the
  primary metric; log loss, calibration, four fold reports, full denominator
  accounting and candidate-minus-each-control paired deltas are retained.
- Complete schedule-date resampling and observed NFL-week sensitivity resample
  whole units, pool every repeated event in the draw and recompute the
  equal-event loss delta.  The partial right-edge observed week is retained
  and explicitly described as secondary/descriptive; it does not change the
  primary denominator or become a confidence gate.
- The exact KEEP rule compares only against market and ordinary: both
  aggregate Brier and log loss must improve by more than `1e-12`, and Brier
  must win at least three of four folds against each.  Calibration and
  Attempt-1 comparisons are separate branch diagnostics.  REVERT leaves raw
  market as current best while preserving every research branch; neither
  outcome is promotion or formal OOS evidence.
- Selected-recent, older-eligible and check diagnostics report row/date/week
  breadth, raw/residual family and composite behavior, market correlations,
  residual-family collinearity, signed moments, coefficient, optimizer state
  and correction range.  Tests establish that changing diagnostic output
  cannot affect the candidate.  These quantities do not gate, select, flip or
  tune the run.

### Failure and access boundaries

Admitted-run code/runtime/artifact/source drift is inside the structured
failure-receipt boundary.  `fit_started` becomes true immediately before the
first optimizer call, and `scoring_started` immediately before scoring.
Synthetic regressions separately confirm truthful receipts for pre-fit
selection/rank failure, optimizer failure and execution-identity drift.
Static source inspection found no network, provider, subprocess or protected
Dev/Final access path.  The result documents retain zero provider cost,
Dev/Final closed, external fetch false and promotion false.

## Independent verification replay

Using the bound persistent runtime with `PYTHONPATH=.:research/market_rsi`:

- focused Attempt-2 suite: **12/12 passed**;
- settlement + offset + calibration + Attempt 1 + Attempt 2 suites:
  **63/63 passed**;
- `py_compile` with bytecode redirected to `/tmp`: passed;
- `git diff --check`: passed;
- exact candidate-spec and full transitive execution identity: reproduced.

The only runtime warning in the combined replay was joblib falling back from
physical-core discovery to logical-core count; it did not change tests,
optimizer settings or results.

## Provenance and claim boundary

The Controller did **not** choose this recipe from Attempt-1 aggregate scores
alone.  It openly used previously inspected Attempt-1 fold/date/week/family
label-dependent diagnostics plus a new read-only, label-dependent inventory of
recent-fit and check signed moments.  Under the user's open Train Discovery
authorization this is a legitimate adaptive research choice and introduces no
within-fold future-row or check-label input into prediction.  It is also an
additional adaptive look at the same Train checks, so the result must not be
described as independently selected, untouched validation or formal OOS.

The `indicator-prediction-evals` review principles informed this gate:
prior-only preprocessing, same-row proper scoring, grouped event-weighted
inference, explicit sign/collinearity diagnosis, and separation of current
best from retained branches.  Literature-supported principles are kept
separate from project-chosen parameters such as NFL, the 15-minute cutoff,
600-second gate, three-week window, equal family weights, lambda one, folds,
seed and KEEP rule.  Whether recent history adapts better, one composite
reduces harmful redundancy, or this recipe improves proper scores remains an
untested project hypothesis until the one authorized run completes.

This Attempt cannot support promotion, formal OOS improvement, profitability,
generalization beyond 2025 NFL, cross-domain transfer, RSI self-evolution or
freedom from historical-event memorization.
