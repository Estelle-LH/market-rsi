# MarketRecencyWeightedCompositePath-v3 real Train result — independent review

Review completed: `2026-09-29`.

## Verdict

**PASS at 0 P0 / 0 P1.**  The completed Attempt-3 artifact is internally
bound, and its source lineage, population, fixed recency weights, objectives,
candidate predictions, seven-arm proper scores, fold deltas, grouped inference
and `KEEP` decision reproduce independently.

The candidate beats the decision-time market on aggregate Brier and log loss
and on Brier in three of four folds.  It also beats the ordinary reference in
all four folds.  The frozen current-best rule therefore returns **KEEP**:
`MarketRecencyWeightedCompositePath-v3` becomes the Discovery incumbent.  This
does not promote the model, erase any research branch, or establish formal OOS
improvement.

This is repeatedly inspected opened-Train Discovery.  The review invoked no
runner, optimizer or model fit.  It used read-only source/artifact checks,
deterministic transform replay and independent arithmetic.  It did not open
Dev/Final, use a network/provider, fetch data, publish or promote.  The only
repository file written is this review log.

Reviewed artifact:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recency-weighted-composite-path-20260929-01`

## Exact artifact and execution identity

The artifact contains exactly seven files:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `cde9f1b57d1a6c8337200b6312cbac1ef2dae0434a9d30786baa52cfebb98df4` |
| `input_receipts.json` | `cc030734a5af5a264cda6b820cf4f08cafb0d2b8c30c70c13a210c513f57ca6e` |
| `manifest.json` | `03a0b3d932c3faff55ecde90bbcbcb99a24609a919e9562155112fc683c8b2af` |
| `pre_score_lock.json` | `2fd4e708eb1f0160bcc34edd6ddde8155e66bc3494cc2e2de7a9e978cbe1cfbd` |
| `predictions.csv` | `cbf2fba9fdd08f42ee9897cc01fdbf06052b9f10097eedd5dac21de84c53e9b1` |
| `scorecard.json` | `556af6167bed0bee9a2e7d47a1ba742af801f005fbcc16cb4d5af812ccae61cf` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

All six manifest-to-file bindings match.  The result records frozen runner
`05af717084499618c99fefd034972681d4acef12b226b5fc8b8a4513c26fdbd1`;
the test source independently rehashes to
`9d2491170a1862a4239118ad8ff03d95e5c4ed5e682e131a5023ae4ac4b1363d`
and the passing pre-score review to
`4842c407e4572aaa231386be7e2ca37ed1f16be16e25b7710d73863df4be32ed`.
Controller recipe `1def1562...83cc`, Attempt-2 runner/test, its passing result
review `6800cd96...9c6d`, all seven archived Attempt-2 files, and the complete
transitive runtime/scorer/probability-contract chain match their commitments.

## Source lineage, population and boundaries

- Source manifest and cohort rehash to
  `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
  and `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.
- All four source-file hashes match for all 195 events: **780/780**.  All
  **194/194** materialized receipts match, and all **194/194** stored catalog
  payloads independently decompress to their recorded raw hashes.
- Accounting is exactly **195 source events / 42 dates = 194 materialized +
  one exclusion**.  The sole exclusion is source ordinal 53,
  `2025_04_GB_DAL`, reason `unresolved_outcome`.
- The inclusive 600-second gate checks all 194 rows.  Observed age is 0–313
  seconds with no violation or staleness attrition.
- The check mask is exactly **87 unique events / 20 complete schedule dates /
  seven observed NFL weeks**, hash
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
  Fit/check counts are 107/26, 133/16, 149/28 and 177/17; no fit label is
  unavailable.
- All seven arms use the same finite `[1e-6,1-1e-6]` probability mask.  Home
  orientation, kickoff-minus-15-minute cutoff and identities are unchanged.
  Dev/Final, external fetch, provider payment, publication and promotion are
  closed; recorded provider cost is `$0`.

## Weights, objective, predictions and fit accounting

The strict prior-week cohorts reproduce exactly as 44/43/41/43 rows over
Weeks 05/06/07, 06/07/08, 08/09/10 and 10/11/12.  Their per-week counts are
14/15/15, 15/15/13, 13/14/14 and 14/15/14; class counts remain
22/22, 26/17, 20/21 and 25/18.

Every event receives weight `0.25/0.50/1.00` according to its ordered
oldest/middle/newest selected week, independent of row order.  Event ledgers,
week/class totals, squared sums and Kish counts reproduce exactly:

| Fold | Rows | Weight sum | Squared sum | Kish rows |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 44 | 26.00 | 19.6250 | 34.4459 |
| 2 | 43 | 24.25 | 17.6875 | 33.2473 |
| 3 | 41 | 24.25 | 18.3125 | 32.1126 |
| 4 | 43 | 25.00 | 18.6250 | 33.5570 |

An independent deterministic transform replay and direct evaluation of
`sum(a*NLL)/sum(a) + 0.5*w^2` reproduces every saved objective and analytic
gradient.  Candidate probabilities reproduce with maximum absolute difference
**0.0**.

| Fold | Weighted moment `z*(y-pm)` | Fitted `w_c` | Objective | Gradient norm |
| ---: | ---: | ---: | ---: | ---: |
| 1 | -0.148876 | -0.122974 | 0.5921298735 | 1.25e-11 |
| 2 | +0.091406 | +0.072540 | 0.5307193004 | 1.37e-10 |
| 3 | +0.068793 | +0.059442 | 0.6248310130 | 2.16e-13 |
| 4 | +0.176862 | +0.140941 | 0.5009793186 | 3.61e-11 |

The stored gradient-at-zero values equal the negative moments, preserving the
correct sign convention.  Four successful optimizer reports plus frozen source
control flow and call-count tests establish **four candidate fits / zero
control refits**.  All **1,305** archived identity, outcome and control cells
(87 rows × 15 Attempt-2 columns) match the immutable Attempt-2 predictions
byte-for-byte.

## Independently reproduced scorecard

| Arm | Brier | Log loss | Calibration slope |
| --- | ---: | ---: | ---: |
| MarketRecencyWeightedCompositePath-v3 | **0.2038565961** | **0.5958367713** | 0.999862 |
| MarketRecentCompositePath-v2 | 0.2042380588 | 0.5963727488 | 1.001434 |
| Decision-time market | 0.2055333637 | 0.5984509292 | 1.015513 |
| Market-only calibration | 0.2058518570 | 0.5993850089 | 1.006707 |
| Attempt 1 | 0.2069233196 | 0.6025293021 | 0.981297 |
| Archived full offset | 0.2094506542 | 0.6082677941 | 0.938536 |
| Ordinary reference | 0.2356047245 | 0.6759482937 | 0.636661 |

Candidate-minus-reference deltas; negative is better:

| Reference | Brier delta | Log-loss delta | Brier fold wins |
| --- | ---: | ---: | ---: |
| Market | -0.0016767676 | -0.0026141579 | **3/4** |
| Market-only calibration | -0.0019952609 | -0.0035482375 | 3/4 |
| Attempt 1 | -0.0030667234 | -0.0066925308 | 3/4 |
| Attempt 2 | -0.0003814626 | -0.0005359774 | 2/4 |
| Full offset | -0.0055940581 | -0.0124310228 | 3/4 |
| Ordinary | -0.0317481284 | -0.0801115224 | **4/4** |

Direct recomputation of every aggregate/fold metric and calibration value
differs by at most `4.5e-16`; every pairwise delta differs by at most
`2.8e-17`.  Candidate-minus-market Brier/log-loss deltas by fold are
`+0.004490/+0.012919`, `-0.002698/-0.007294`,
`-0.003723/-0.009478` and `-0.006776/-0.010661`.

## Grouped inference and exact decision

An independent seed-23, 1000-replicate reconstruction sampled complete units,
pooled every repeated unit's events and recomputed the equal-event mean.  All
stored candidate comparisons, per-unit sums/means, points and percentile
intervals reproduce within `2.8e-17`.

Candidate-minus-market intervals still cross zero:

- complete schedule dates: Brier `[-0.0070544, 0.0052447]`, log loss
  `[-0.0151708, 0.0142352]`;
- observed NFL weeks: Brier `[-0.0067024, 0.0050672]`, log loss
  `[-0.0138775, 0.0128548]`.

The candidate has better mean Brier on 11/20 dates and 5/7 observed weeks.
Week 14 contains one right-edge event and is correctly labelled a partial-week
sensitivity, not a complete week.  These adaptive Train intervals and breadth
counts are descriptive, not promotion gates.

All four aggregate loss conditions against market and ordinary pass.  Market
Brier fold wins are `[false,true,true,true]`; ordinary wins are all true.  The
frozen three-of-four rule therefore yields exact decision **KEEP**.  The fact
that the weighted candidate beats Attempt 2 in only two folds is retained as a
branch-stability diagnostic and does not alter the preregistered incumbent gate.

## Interpretation and claim boundary

Fixed recency weighting modestly improves the already-positive Attempt-2
branch and, unlike Attempt 2, clears the frozen market fold-breadth rule.
Calibration slope is essentially one.  However, the aggregate improvement over
Attempt 2 is small, Fold 1 worsens, and complete-day/week intervals versus the
market cross zero.  The proper conclusion is a useful current Discovery
incumbent with material temporal uncertainty—not robust OOS superiority.

The decay rule was selected after label-dependent Attempt-2 fold/week/date
diagnostics.  That is authorized adaptive Discovery but not untouched or
independently selected validation.  Applying the `indicator-prediction-evals`
principles, the review preserves causal prior-only transforms, identical-row
proper scoring, event-weight-preserving grouped resampling, branch retention,
and the separation of current-best replacement from promotion.

Attempt 3 does not support formal OOS improvement, profitability,
generalization beyond 2025 NFL, cross-domain transfer, RSI self-evolution or
freedom from historical-event memorization.
