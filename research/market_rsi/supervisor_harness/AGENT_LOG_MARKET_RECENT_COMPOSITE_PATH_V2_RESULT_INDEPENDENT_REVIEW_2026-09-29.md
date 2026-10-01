# MarketRecentCompositePath-v2 real Train result — independent review

Review completed: `2026-09-29`.

## Verdict

**PASS at 0 P0 / 0 P1.** The completed Attempt-2 artifact is internally
bound, and its source lineage, population, recent cohorts, archived controls,
candidate predictions, six-arm proper scores, fold deltas, grouped inference,
diagnostics and `REVERT` decision reproduce independently.

The candidate improves aggregate Brier and log loss versus the decision-time
market, market-only calibration, Attempt 1, full offset and ordinary reference.
It nevertheless beats market Brier in only two of four folds, below the frozen
three-fold requirement.  `REVERT` is therefore exact: decision-time market
remains current best, while the recent-composite branch and its evidence are
retained for Discovery.

This is repeatedly inspected opened-Train Discovery, not untouched OOS,
promotion, profitability or self-evolution evidence.  This review invoked no
runner, model fit or optimizer; it used read-only source/artifact checks and
independent arithmetic reconstruction.  It did not open protected Dev/Final,
use network/provider services, acquire data, publish or promote.  The only
repository file written is this review log.

Reviewed artifact:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recent-composite-path-20260929-01`

## Exact artifact and execution identity

The artifact contains exactly seven files:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `1ee1b77e6f1f71b4382c452916afe51d19d7edfa8b1a9844fd81e21f18d887e2` |
| `input_receipts.json` | `eeb0449123c55e6b0b3e7f7b314c9b5327b1404041d3dd5fb18dededdf718640` |
| `manifest.json` | `3434aef3a97fc54b61a6d0c762a1f80523d24f3a96c0071dd77944befef7683c` |
| `pre_score_lock.json` | `fc462890587cc7dc9a079acb128590a7a7ccdf5494c30be5d5136c3ee1a8ce62` |
| `predictions.csv` | `7691a6dbee6b7dc0949583a7a421e7a421ad7565caaf20ebf559121b1b76cca2` |
| `scorecard.json` | `29632c1a8879be045ffb5018067ec72c3eca70fad44f43b9b5a60060f1e992d8` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

Every manifest-to-file binding matches.  The result records the exact runner
`d005d9fe5df0c33c1eeb5aa8ba2d5e7ebbb5103c9b0e7935bb5ac3de8946c70f`.
The reviewed test source still hashes to
`4aac0a60e9e2b4bbffd9999bc1259d9c27df2b8c4b9be259d8dd22ceb3f6ca77`,
and the passing pre-score review to
`179d46f337e0ec90f012b64750f3343724dfdd3ac46e6f7cfdfb4ef863e88fb7`.
Controller recipe `2d6f26fa...e061`, Attempt-1 runner/test and its passing
result review `ea42908c...9f83`, plus the full transitive runtime, scorer and
probability-contract chain all match their frozen commitments.

## Source lineage, population and boundaries

- Source manifest and cohort independently rehash to
  `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
  and `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.
- All four source-file hashes match for all 195 events: **780/780**.  All
  **194/194** materialized receipt links match, and all **194/194** compressed
  catalog payloads independently decompress to their recorded raw hash.
- Accounting is exactly **195 source events / 42 dates = 194 binary events +
  one exclusion**.  The sole exclusion is source ordinal 53,
  `2025_04_GB_DAL`, reason `unresolved_outcome`.
- The inclusive 600-second gate checks all 194 rows.  Observed age is 0–313
  seconds, with no violation or staleness attrition.
- The common prediction mask is exactly **87 unique events / 20 complete
  schedule dates / seven observed NFL weeks**, hash
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
  Fold fit/check counts are 107/26, 133/16, 149/28 and 177/17; no fit label is
  unavailable.
- Every probability is finite and inside `[1e-6,1-1e-6]`.  Home orientation,
  kickoff-minus-15-minute cutoff and identities are unchanged.  Dev/Final,
  external fetch, paid provider, publication and promotion remain closed;
  provider cost is `$0`.

## Recent cohorts, transform and fit accounting

The strict prior-week rule reproduces exactly:

| Fold | Weeks | Rows | y=1 / y=0 | Per-week rows |
| ---: | --- | ---: | ---: | --- |
| 1 | 05/06/07 | 44 | 22 / 22 | 14/15/15 |
| 2 | 06/07/08 | 43 | 26 / 17 | 15/15/13 |
| 3 | 08/09/10 | 41 | 20 / 21 | 13/14/14 |
| 4 | 10/11/12 | 43 | 25 / 18 | 14/15/14 |

The first check weeks are 08, 09, 11 and 13.  Thirteen already-settled Week-09
rows in Fold 2 and one Week-11 row in Fold 3 remain explicitly ineligible,
confirming that same-week outcomes did not enter the recent candidate fit.

An independent reconstruction from named source columns reproduces all four
rank-two market residualizers, scalers, composite scales, residual-family
correlations, selected/check signed moments, objectives and candidate
probabilities.  Maximum candidate probability difference is **0.0**; saved
transform parameters, objectives, composite scales and signed moments also
match exactly.  All optimizer gradient infinity norms are below `5.6e-9`.

The fitted `w_c` values are `-0.10151`, `-0.00616`, `+0.07331` and `+0.09783`.
Selected-fit composite moments are `-0.12484`, `-0.00747`, `+0.08830` and
`+0.11884`; corresponding check moments are positive in every fold:
`+0.08799`, `+0.10550`, `+0.16866`, `+0.09949`.  Fold 1 therefore retains the
known fit/check sign reversal, Fold 2 is nearly neutral, and Folds 3–4 align.
Residual-family correlation remains high: 0.842–0.887 on selected fit rows and
0.855–0.900 on checks.  Compression is diagnostically sensible, but the
remaining temporal instability is material.

The artifact has four successful optimizer reports, one per fold.  Source
control flow and the reviewed call-count regressions establish exactly **four
candidate fits and zero control refits**.  All 1,218 identity/control cells
across the 87 rows and 14 archived columns match the immutable Attempt-1
prediction artifact byte-for-byte.

## Independently reproduced scorecard

| Arm | Brier | Log loss | Calibration slope |
| --- | ---: | ---: | ---: |
| MarketRecentCompositePath-v2 | **0.2042380588** | **0.5963727488** | 1.001434 |
| Decision-time market | 0.2055333637 | 0.5984509292 | 1.015513 |
| Market-only calibration | 0.2058518570 | 0.5993850089 | 1.006707 |
| Attempt 1 | 0.2069233196 | 0.6025293021 | 0.981297 |
| Archived full offset | 0.2094506542 | 0.6082677941 | 0.938536 |
| Ordinary reference | 0.2356047245 | 0.6759482937 | 0.636661 |

Candidate-minus-reference deltas; negative is better:

| Reference | Brier delta | Log-loss delta | Brier fold wins |
| --- | ---: | ---: | ---: |
| Market | -0.0012953049 | -0.0020781804 | **2/4** |
| Market-only calibration | -0.0016137983 | -0.0030122601 | 2/4 |
| Attempt 1 | -0.0026852608 | -0.0061565533 | 3/4 |
| Full offset | -0.0052125954 | -0.0118950453 | 3/4 |
| Ordinary | -0.0313666658 | -0.0795755449 | 4/4 |

Direct recomputation of every arm metric, calibration value, fold result and
pairwise delta differs from the stored scorecard by at most `2.3e-16`.
Candidate-minus-market Brier/log deltas by fold are respectively
`+0.003684/+0.010371`, `+0.000242/+0.000653`,
`-0.004517/-0.011535`, and `-0.005052/-0.008112`.

## Grouped inference and decision

An independent seed-23, 1000-replicate reconstruction sampled complete units,
pooled all repeated events and recomputed the equal-event mean.  All stored
candidate comparisons, point estimates and day/week percentile intervals
match exactly.

Candidate-minus-market intervals cross zero:

- complete schedule dates: Brier `[-0.0063543, 0.0044645]`, log loss
  `[-0.0135384, 0.0114652]`;
- observed NFL weeks: Brier `[-0.0064004, 0.0048945]`, log loss
  `[-0.0136909, 0.0123050]`.

The candidate has better mean Brier on 12/20 dates and 4/7 observed weeks, but
these adaptive Train breadth counts and intervals are descriptive.  Week 14
contains one right-edge event and is correctly retained rather than presented
as a complete week.

All aggregate loss conditions versus market and ordinary pass, as do all four
ordinary Brier folds.  The candidate beats market Brier only in Folds 3 and 4,
so the frozen `>=3/4` condition fails.  Exact decision: **REVERT**.  Market
remains current best; all branches remain retained.

## Interpretation and claim boundary

The result supports a narrow Discovery conclusion: recent-window compression
substantially improves the path branch and produces a favorable aggregate
score, including better calibration slope, but its gain is not stable across
the four frozen checks.  The first two folds still reflect fit/check temporal
mismatch; complete-day and observed-week intervals versus market cross zero.
This is useful Category-B/trainer evidence, not a reason to delete the branch
or to override the preregistered decision.

The Controller recipe was adaptively selected after label-dependent Attempt-1
fold/date/week/family diagnostics and a new recent signed-moment inventory.
That is legitimate under opened-Train Discovery, but it is not aggregate-only,
independently selected or untouched OOS.  Applying the
`indicator-prediction-evals` principles, the review preserves causal
prior-only transforms, paired same-row proper scoring, grouped event-weighted
inference, sign/collinearity diagnosis, and the distinction between current
best and retained research branches.

Attempt 2 does not support promotion, formal OOS improvement, profitability,
generalization beyond 2025 NFL, cross-domain transfer, RSI self-evolution or
freedom from historical-event memorization.
