# MarketRecencyWeightedCompositeDispersion-v5 real Train result — independent review

Date: 2026-09-29  
Verdict: **PASS**  
P0: none  
P1: none

The completed Attempt-5 artifact, score arithmetic and exact `REVERT` decision
reproduce independently. The candidate beats the Attempt-3 incumbent in
aggregate Brier and log loss and in Brier in three of four folds, but it beats
the decision-time market in only two of four folds. The frozen rule retains
all prior market/ordinary gates, so this failed market fold-breadth gate makes
`REVERT` mandatory. MarketRecencyWeightedCompositePath-v3 remains the current
Discovery incumbent; all branches remain recorded.

This review invoked no runner, optimizer or fit. It used read-only artifact and
source verification plus independent arithmetic over the saved predictions.
It did not access Dev/Final, contact a network/provider, fetch or publish data,
or authorize promotion. The only written file is this review log.

## Exact artifact and execution identity

Artifact:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recency-weighted-composite-dispersion-20260929-01`

It contains exactly seven files:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `18cc4a37b1bf9f07bfccc057bb64d20c11b020ce749c1f2ec0c3dfcebf5c9eaa` |
| `input_receipts.json` | `a5aef0f809db5b016d61e6b839693cf8ee1ba85d4f613ea11d1dcc79a7c0ec98` |
| `manifest.json` | `04e539decc05e6bcf64a60d8f051bb9765364f04bdf43fa35b66a4696d007437` |
| `pre_score_lock.json` | `9e01fb263f74a2d993dd9760906f800d1379f64196b2c2e966bc42741e0f208f` |
| `predictions.csv` | `047640a5e722ea78955ae3e28ad9f85acbd3a35e4ca19d16d867c1d4ac3b787a` |
| `scorecard.json` | `34afad5d828d6688cd23bea487f603868826487700d7b618a189240d0e7e7d66` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

All manifest-to-file bindings match. The manifest is `COMPLETE`, with 195
source events, 194 materialized, one exclusion, 87 check events, four candidate
fits, zero control refits and `REVERT`.

The artifact binds frozen runner
`7e384cb18a2b11595c0e6ab77446be59f538033c7fed842a3af572571e18a658`,
test `b6202edb2f68996424287352e0d090643f9c900e38d1f6b870b5323aec6f4547`,
Controller recipe
`29bd05297afca88a6949aa1e75241cf88da458be7018862317deb74618758436`,
passing pre-score review
`7289da2b9441feeb6ef41e6b7615dbc5094bbf513e04bee0a00fa56beb4b8acd`,
and passing Attempt-4 result review
`c5b706e474af4ef1fac34eab1c19567f03c300f0c77f03bafcd129d09913f882`.
The transitive runtime/source/scorer lineage and every hash-bound Attempt-4
parent artifact file also match.

## Source, population, controls and boundaries

- Source manifest/cohort hashes match
  `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
  and `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.
- All **780/780** source-file hashes and **194/194** decompressed catalog raw
  hashes match their receipts.
- Population accounting is 195 = 194 materialized + the sole
  `2025_04_GB_DAL` `unresolved_outcome` exclusion.
- The complete mask is the same 87 events / 20 dates / seven observed NFL
  weeks, hash
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
- The first 17 identity/outcome/market/control fields of every prediction row
  match immutable Attempt-4 predictions exactly: **1,479/1,479 cells**.
  Thus all eight controls are archive-bound and control refits remain zero.
- Every arm probability is finite on the same complete mask. Dev/Final,
  external fetch, provider payment and promotion remain closed; recorded
  provider cost is `$0`.

## Independently reproduced scores

| Arm | Brier | Log loss | Calibration slope |
| --- | ---: | ---: | ---: |
| Attempt-5 dispersion candidate | **0.2022600315** | **0.5918191393** | 1.013430 |
| Attempt-3 incumbent | 0.2038565961 | 0.5958367713 | 0.999862 |
| Attempt 2 | 0.2042380588 | 0.5963727488 | 1.001434 |
| Attempt 4 | 0.2044223641 | 0.5970803064 | 1.000769 |
| Decision-time market | 0.2055333637 | 0.5984509292 | 1.015513 |
| Market-only calibration | 0.2058518570 | 0.5993850089 | 1.006707 |
| Attempt 1 | 0.2069233196 | 0.6025293021 | 0.981297 |
| Archived full offset | 0.2094506542 | 0.6082677941 | 0.938536 |
| Ordinary reference | 0.2356047245 | 0.6759482937 | 0.636661 |

Every aggregate/fold score and calibration term reproduces within
`1.11e-16`; every pairwise delta reproduces within `1.11e-16`.

Candidate-minus-reference deltas; negative is better:

| Reference | Brier delta | Log-loss delta | Brier fold wins |
| --- | ---: | ---: | ---: |
| Market | -0.0032733323 | -0.0066317900 | **2/4** |
| Ordinary | -0.0333446931 | -0.0841291545 | **4/4** |
| Attempt-3 incumbent | -0.0015965647 | -0.0040176321 | **3/4** |

The independently reproduced fold-win vectors are:

- market: `[false, false, true, true]`;
- ordinary: `[true, true, true, true]`;
- Attempt 3: `[true, false, true, true]`.

Thus the candidate passes aggregate market/ordinary gates, all ordinary fold
gates, both aggregate incumbent gates and the three-of-four incumbent gate.
It fails the pre-existing requirement to beat the market in at least three of
four folds. The scorecard's exact decision **REVERT** is therefore correct,
despite the candidate's better aggregate score.

## Grouped inference and claim boundary

An independent seed-23, 1,000-replicate reconstruction of every candidate
comparison, using complete schedule-day and observed-game-week groups and a
pooled equal-event mean per draw, reproduces all stored points and percentile
intervals within `1.39e-17`.

Candidate-minus-v3 intervals cross zero:

- schedule dates: Brier `[-0.0043744, 0.0010286]`, log loss
  `[-0.0111493, 0.0025487]`;
- observed weeks: Brier `[-0.0040179, 0.0009281]`, log loss
  `[-0.0100964, 0.0023726]`.

The candidate has better mean Brier than v3 on 11/20 dates and 5/7 weeks;
against the market it is better on 13/20 dates and 6/7 weeks. These are useful
adaptive Train diagnostics, but the intervals cross zero and the frozen fold
gate fails. They cannot override the registered decision rule.

Attempt 5 was adaptively chosen after prior opened-Train results. Applying the
`indicator-prediction-evals` separation, this is evidence about a prediction
feature/trainer variant, not untouched OOS validation, profitability or a
monetization result. No promotion, generalization, RSI self-evolution or
formal OOS claim is supported.

## Final decision

**PASS, P0 none, P1 none. Exact result: REVERT.** Preserve the Attempt-5
branch and its diagnostics; retain MarketRecencyWeightedCompositePath-v3 as
the current Discovery incumbent.
