# MarketOrthogonalPricePath-v1 independent pre-score review

Review completed: `2026-09-29T18:21:21Z`.

## Verdict

**PASS at 0 P0 / 0 P1.** The exact frozen implementation satisfies the
Controller recipe and is admissible for one fresh opened-Train Discovery run.
This is a pre-score implementation verdict only; it is not an empirical result,
promotion decision, formal OOS claim, profitability claim, or RSI
self-evolution result.

No real Train runner was invoked. No protected Dev/Final data, network,
provider, paid service, release, publication or promotion was used. The only
repository file written by this review is this log.

## Exact reviewed snapshot

| Item | SHA-256 |
| --- | --- |
| Orthogonal runner | `af4508f0c808fbc236daae6607343c47238db26e2148289a08670fe71102f380` |
| Orthogonal tests | `71e576f4a74aba6a334d09f76dc3d2023122b126a0b11ded8b2ddec6e2aad40a` |
| Implementation log | `4115fed89707535c63664fec5dc07a45731359e189c788a7bd5227172e58e037` |
| Controller proposal | `8b5fbdef19279098759169d5a83ced8077abfe5c56b787667bd9dbb0a5632719` |
| Calibration runner / tests | `71d329468c865246616b8cb1ee7b284a488c9ad382f2bda830bb529e383cc191` / `548d8d633fc2007414d10874b11300442ebb97719eb101bb451cd3bd8d755bb0` |
| Full-offset runner / tests | `6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f` / `409fd88d93c59b5d0bb25a1765471ad9249c0a5872cc77d31e69922a77fd0f41` |
| Settlement runner / tests | `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b` / `6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927` |
| Proper scorer / probability contract | `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b` / `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74` |

The archived calibration artifact's exact seven-file set independently
rehashes to the runner commitments: exclusions `c6e8d143...f131`, inputs
`db6506a0...f297`, manifest `a6e2e63b...37bb`, lock `190a846b...ac7`,
predictions `b9d28742...2358`, scorecard `51385656...e7f2b`, and staleness
inventory `3b545bd2...a10e`.

## Contract findings

- Exact-name mapping selects only the three frozen 15/60/240-minute
  `weighted_mean_home_probability` columns and the three signed
  `last_minus_first_home_probability` columns. The implemented formulas are
  exactly `g = p - mean(VWAPs)` and `d = mean(moves)` in home-oriented
  probability units. Unused-column mutation leaves the design unchanged.
- Market scaling, least-squares residualization against `[1,z_market]`, and
  residual scaling are fit-only. The same fitted transform is applied to check
  rows. Fit- and check-label mutation tests establish that compression is
  label-free and check outcomes cannot change candidate parameters or
  predictions.
- `lstsq(..., rcond=1e-12)` requires rank two and records rank, singular
  values, both coefficients per family and fit moments. Shape, nonfinite and
  rank failures fail closed as structured `INVALID_DATA_QUALITY`. A fit
  population standard deviation at most `1e-8` makes that family explicitly
  inactive and zero on both fit and check without dropping an event.
- The candidate design is `[z_market,z_g,z_d]`. The reviewed offset solver
  gives exactly four parameters, market-logit offset coefficient one, mean
  Bernoulli NLL plus `0.5` times squared L2 of every parameter, lambda one,
  zero initialization, float64 L-BFGS-B and the frozen convergence and
  probability-rejection contracts. Finite differences, all-parameter penalty,
  all-zero market recovery and zero-family-coefficient calibration recovery
  pass.
- A valid four-fold run performs exactly four width-three candidate fits,
  four width-one calibration fits and four 17-column ordinary fits. The
  archived full-offset arm is never refit. The earlier moving-snapshot duplicate
  fit pass is absent, and the call-count regression would detect its return.
- Recomputed ordinary and calibration controls must match the frozen
  calibration artifact within `1e-10` on identical ordered keys, outcomes and
  market values. Archived full-offset predictions remain immutable. Parent
  artifact hashes and manifest bindings validate before model fitting.
- Fit diagnostics are computed before candidate fitting and check diagnostics
  only after prediction. Raw/residual variance, correlations, average-rank
  Spearman, signed moments, null reasons, fold parameters and probability
  corrections are reporting-only; mutation tests confirm they cannot tune the
  model or enter KEEP.
- The scorecard contains exactly five named arms on one common 87-row mask and
  reports equal-event Brier/log loss, calibration, folds and all required
  candidate comparisons. Whole schedule dates are resampled and the pooled
  equal-event estimand is recomputed in each draw. Observed NFL weeks remain a
  separate seven-cluster sensitivity with the partial right-edge week
  disclosed; unit counts, sums and means are retained.
- KEEP is exactly candidate improvement over both market and ordinary by more
  than `1e-12` on aggregate Brier and log loss plus at least three of four
  Brier fold wins against each. Candidate-versus-calibration and interval
  diagnostics cannot decide KEEP. REVERT preserves the incumbent market and
  every research branch.
- Production checks preserve 195 source events / 42 dates, exactly 194 binary
  rows, the sole ordinal-53 `2025_04_GB_DAL` unresolved-outcome exclusion,
  materialized key digest `59128473...72bd96`, 87 checks / 20 schedule dates /
  seven observed weeks, mask `eddf8cc9...341cb`, folds 107/26, 133/16,
  149/28 and 177/17, zero unavailable fit labels, home orientation, the fixed
  15-minute cutoff and inclusive 600-second staleness gate.
- The pre-score lock separates literature-supported principles, project-chosen
  parameters and unvalidated hypotheses. Scorecard semantics are opened-Train
  Discovery only; ordinary remains an ordinary reference and failed candidates
  remain research branches.

## Independent verification

Using the exact bound runtime
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`
with `PYTHONPATH=research/market_rsi`, the orthogonal, calibration, offset and
settlement suites passed **51/51** tests in 4.923 seconds. The focused
orthogonal subset contains 17 tests. `py_compile` passed for the exact runner
and tests, no-index whitespace checks were clean, and static import/call scans
found no network, provider, subprocess or arbitrary-code execution path.

An initial invocation under non-bound Python environments failed closed: the
system interpreter lacked scikit-learn and the alternate 3.12 environment was
rejected for executable-identity mismatch. This is expected enforcement, not
an implementation failure.

The `indicator-prediction-evals` gates informed the review: same-row proper
scoring, prior-only transformations, dependence-aware resampling, coefficient
sign freedom, explicit collinearity/rank handling, current-best versus branch
separation, and the boundary between adaptive Train Discovery and untouched
future evaluation.

## Admission boundary

This PASS admits only the proposed fresh local opened-Train attempt
`first-real-train-diagnostic-market-orthogonal-price-path-20260929-01` against
this exact source/runtime snapshot. A code, test, parent, artifact or runtime
change requires a new exact review. Protected Dev/Final, external acquisition,
paid provider use, release, publication and promotion remain unauthorized.
