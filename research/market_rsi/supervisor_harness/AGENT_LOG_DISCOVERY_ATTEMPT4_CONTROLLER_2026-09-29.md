# Discovery Attempt 4 Controller decision — MarketAllPriorDecayCompositePath-v4

Time: 2026-09-29, after real opened-Train Discovery Attempt 3.

Status: **one candidate frozen before implementation or scores**.  This task
only read resident Train artifacts/history and performed arithmetic on recorded
diagnostics.  It did not implement, fit, score, invoke a runner, open
Dev/Final, use network/provider services, spend money, publish or promote.

## Evidence and current best

Attempt-3 artifact:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recency-weighted-composite-path-20260929-01`.

| File | SHA-256 |
| --- | --- |
| exclusions | `cde9f1b57d1a6c8337200b6312cbac1ef2dae0434a9d30786baa52cfebb98df4` |
| input receipts | `cc030734a5af5a264cda6b820cf4f08cafb0d2b8c30c70c13a210c513f57ca6e` |
| manifest | `03a0b3d932c3faff55ecde90bbcbcb99a24609a919e9562155112fc683c8b2af` |
| pre-score lock | `2fd4e708eb1f0160bcc34edd6ddde8155e66bc3494cc2e2de7a9e978cbe1cfbd` |
| predictions | `cbf2fba9fdd08f42ee9897cc01fdbf06052b9f10097eedd5dac21de84c53e9b1` |
| scorecard | `556af6167bed0bee9a2e7d47a1ba742af801f005fbcc16cb4d5af812ccae61cf` |
| staleness | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

Attempt 3 is the new current-best Train-Discovery recipe.  It returned KEEP:

- candidate Brier/log loss `0.2038565961 / 0.5958367713`;
- market `0.2055333637 / 0.5984509292`;
- candidate-minus-market `-0.0016767676 / -0.0026141579`;
- candidate-minus-Attempt-2 `-0.0003814626 / -0.0005359774`;
- Brier wins versus market in folds 2–4 and loses fold 1.

Calibration slope is `0.99986`.  This rejects the narrow concern that the gain
is only probability-scale inflation.  It remains repeatedly inspected Train,
not formal OOS evidence.

The remaining problem is estimator variance and one regime miss.  Fold
coefficients are `-0.12297, +0.07254, +0.05944, +0.14094`; Fold 1's negative
coefficient harms market by `+0.00448965` Brier and `+0.01291949` log loss.
Attempt 3 uses only `32.1–34.4` Kish-effective fit rows.  Complete-day and
observed-week intervals versus market and Attempt 2 cross zero.  Its incremental
gain versus Attempt 2 wins only 10/20 dates, although five of seven observed
weeks improve.  Therefore KEEP is useful Discovery progress, not sufficient
certainty to stop research.

The sign evidence still does not justify a hard positive constraint.  Fold 1
has a genuinely negative prior weighted moment and a positive check moment.
Flipping or truncating that coefficient using already-seen checks would be
post-hoc leakage.  Changing the half-life would also become a decay sweep.

## Exactly one candidate: `MarketAllPriorDecayCompositePath-v4`

### Question and changed component

Question: can the same fixed one-week half-life reduce coefficient variance and
Fold-1 harm when its support includes every strictly prior eligible week,
without erasing the Fold-2–4 adaptive directions?

Only the **trainer's weighted support** changes.  The half-life, three-week
transform, composite, one-parameter model, penalty, scorer and decision-time
boundary remain exact.  This is a direct bias–variance test, not a window or
half-life menu.

### Frozen data, transform and controls

Keep the exact source/cohort hashes, 195-event denominator, 194 binary rows,
sole GB-DAL tie exclusion, orientation, kickoff-minus-15-minute cutoff,
inclusive 600-second staleness gate, no imputation, 22 + 4x5 folds, and exact
87-event check mask
`eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
Scoring remains equal-event Brier/log loss and calibration with complete-date
and observed-week resampling at seed 23 / 1000 draws.

Fit the transform exactly as Attempts 2–3 on the three largest week labels
strictly before the first check week.  Preserve exact recent cohorts, class
counts and per-week counts.  Use the same exact-name `g`/`d` formulas,
unweighted market scaler, rank-two `[1,z_market]` residualizer with
`rcond=1e-12`, family scalers, equal composite and composite scaler.  Apply
that frozen transform to older eligible and check rows.  The `<=1e-8`
inactive rule and no-row-drop rule remain unchanged.

Bind all seven Attempt-3 artifact hashes above and a passing independent
Attempt-3 result review before fitting.  Archive market, ordinary, calibration,
full offset, Attempts 1, 2 and 3 without refitting.  The scorecard has those
seven controls plus the new candidate.

### All-prior fixed-decay trainer

For each fold, candidate fit rows are **all** fit rows whose numeric game-week
label is strictly below the earliest check-week label.  Exclude same/later
week rows even if their outcome is known.  Let `W` be the numerically latest
eligible week.  Assign each event in eligible week `w`:

```text
a_i = 2 ** (numeric_week(w) - numeric_week(W))
```

Thus the newest eligible week has weight `1`, the preceding week `0.5`, then
`0.25`, with the same fixed half-weight per calendar week continuing backward.
Do not normalize by week size, class, date, feature or score.  The objective
normalizes by total event weight:

```text
eta_i = market_logit_i + beta * z_composite_i
J(beta) = sum_i a_i*NLL(y_i, eta_i)/sum_i a_i + 0.5*beta^2
gradient = sum_i a_i*z_i*(sigmoid(eta_i)-y_i)/sum_i a_i + beta
```

Use float64, lambda `1`, zero initialization, unconstrained beta, analytic
gradient and L-BFGS-B (`maxiter=1000`, `gtol=1e-8`, `ftol=1e-12`).  Require
success, finite values and final gradient infinity norm `<=1e-6`.  No
intercept, market slope, sign constraint, clipping, sweep, fallback, early
stopping, post-score edit or retry is allowed.  Beta zero must return market
probabilities bit-for-bit; nonzero predictions retain the
`[1e-6,1-1e-6]` rejection policy.

Frozen production cohort arithmetic is:

| Fold | eligible weeks | rows | y=1 / y=0 | weight sum | squared sum | Kish rows |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 01–07 | 107 | 61 / 46 | 29.625 | 19.94140625 | 44.01097 |
| 2 | 01–08 | 120 | 69 / 51 | 27.8125 | 17.9853515625 | 43.00918 |
| 3 | 01–10 | 148 | 81 / 67 | 27.953125 | 18.62408447265625 | 41.95520 |
| 4 | 01–12 | 177 | 98 / 79 | 28.48828125 | 18.914005279541016 | 42.90906 |

Exact per-week row counts remain
`16,16,16,15,14,15,15,13,14,14,15,14` as applicable by fold.
Weight totals by class `(y=0,y=1)` are respectively
`(12.640625,16.984375)`, `(11.3203125,16.4921875)`,
`(13.830078125,14.123046875)`, and
`(11.95751953125,16.53076171875)`.

Read-only arithmetic using Attempt-3 stored transformed weekly moments gives
pre-fit all-prior weighted moments
`-0.1351542, +0.0702689, +0.0423434, +0.1548400`.  They preserve the
negative/positive/positive/positive coefficient descent directions while
reducing magnitude versus Attempt 3 in every fold.  This motivates the
variance test; these values cannot gate or tune execution.

Fit exactly four new one-parameter candidates.  Every control fit count is
zero and provider cost remains `$0`.

### Diagnostics and invalidation

Report, without gating or tuning:

- fixed-order identity/week/outcome/weight ledger for every eligible fit row;
- per-week/per-class rows and weights, total/squared weights and Kish rows;
- unweighted and weighted `mean(z*(y-p_market))` overall and per week;
- `gradient_at_zero = -weighted_moment`, coefficient descent direction,
  fitted beta, optimizer state and probability correction range;
- unchanged selected-three-week/older/check transform and association
  diagnostics; fold/date/week score deltas versus market and every archive.

Fail with a structured fresh-ID receipt for any source/artifact/review/code/
runtime drift; denominator/exclusion/mask/fold/eligible-week/row/class/weight
arithmetic mismatch; same-week inclusion; outcome-time leakage; transform
rank/nonfinite/inactive-rule failure; objective/gradient mismatch; optimizer
or probability rejection; control refit; network/provider/Dev/Final access;
hidden sweep; or row reduction.  Phase flags must truthfully distinguish
pre-fit, optimizer and scoring failures.  No repair in place.

### Scorecard and current-best rule

Use one common 87-event mask for all eight arms and the unchanged proper scorer
and grouped inference.  KEEP as the new current best only if all prior market/
ordinary rules still pass **and** the candidate beats archived Attempt 3 on
both aggregate Brier and aggregate log loss by more than `1e-12`, with Brier
wins against Attempt 3 in at least three of four folds.  Otherwise retain
Attempt 3 as incumbent and preserve Attempt 4 as a research branch.  Confidence
intervals remain descriptive, not gates.

## Evidence classification and memory

**Established evaluation principles:** prior-only transforms and labels,
identical paired masks/proper scores, grouped dependence-aware inference,
explicit raw-signal versus trainer diagnosis, and variance reduction without
changing downstream scoring.

**Project choices:** NFL, cutoff/staleness, folds, three-week transform,
one-week half-life, untruncated support, lambda one, optimizer tolerances,
seed/resamples and KEEP thresholds.  None is literature consensus.

**Unvalidated hypothesis:** tiny older-week weights reduce estimator variance
more than they add regime bias, preserving three positive directions while
reducing Fold-1 harm.  Selection used repeatedly inspected, label-dependent
Train fold/week/date evidence and is adaptive Discovery, never untouched OOS.

If Attempt 4 does not beat incumbent Attempt 3, keep Attempt 3 and move to a
different information family.  Do not sweep truncation length, half-life,
penalty or sign constraints on these same checks.  No result here can support
promotion, formal OOS gain, profitability, transfer, RSI self-evolution or
freedom from historical-event memorization.
