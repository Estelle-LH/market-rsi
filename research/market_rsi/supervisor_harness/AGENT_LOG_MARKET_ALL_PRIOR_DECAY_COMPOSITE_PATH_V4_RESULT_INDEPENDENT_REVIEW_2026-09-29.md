# MarketAllPriorDecayCompositePath-v4 real Train result — independent review

Review completed: `2026-09-29`.

## Verdict

**PASS at 0 P0 / 0 P1.** The completed Attempt-4 artifact is internally
hash-bound, and its source lineage, all-prior decay cohorts and weights,
deterministic transforms, saved objectives/gradients, candidate predictions,
eight-arm proper scores, fold results, grouped inference and exact `REVERT`
decision reproduce independently.

The candidate improves on the decision-time market and ordinary reference,
but it is worse than the MarketRecencyWeightedCompositePath-v3 incumbent in
aggregate Brier and log loss and wins Brier against v3 in only one of four
folds. The frozen rule therefore returns **REVERT** and v3 remains the current
Discovery incumbent. No branch is erased.

This is repeatedly inspected opened-Train Discovery, not independent OOS
evidence. The review invoked no runner, optimizer or model fit. It used only
read-only artifact/source checks, deterministic transform replay with the
saved coefficients, and independent arithmetic. It did not open Dev/Final,
contact a network/provider, fetch or publish data, or promote a model. The
only repository file written is this review log.

Reviewed artifact:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-all-prior-decay-composite-path-20260929-01`

## Exact artifact and identity

The artifact contains exactly seven files:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `5a024887952e3876ad8f7e4dc03fc0c343193074d97bc8025a622d08b3aeb4ed` |
| `input_receipts.json` | `cced501566428aa3011d6e301b3fdb18c5368a2318840ec3f766d87bb91094f4` |
| `manifest.json` | `74569b89cc3497d732f0fabb1a2236584999d4a7e704955db7102ef5c62d831b` |
| `pre_score_lock.json` | `c42702a47b4a181349edceeb493265097c9766d827447a8cae798dd3aec7e173` |
| `predictions.csv` | `ba9885f8d67c9c20838dabd251354d4803afb9ff90c39f990f3c0521d7c8c128` |
| `scorecard.json` | `407cf8f393a0196a3893b1d574e714a2a3b6a448084cd7b42dcd4fd63b000643` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

All six manifest-to-file bindings match. The manifest is `COMPLETE`, records
four candidate fits, zero control refits, 87 check events and `REVERT`.

The result binds the frozen runner
`c9fc5b9d01a28181382ca47d9545ca7ce06c769b6165b482b84fc26df4537139`.
The focused test rehashes to
`7183c64040bba0e02ae583b34050e87f6f4f15a42183e18eccba7a76626da2e7`
and the passing pre-score review to
`3980f2ffd1782db99d398384d671da16d05da888a62b716567b7a990c80186d7`.
Controller recipe `fab9f134...1595`, passing Attempt-3 result review
`016930f4...b0ad`, parent runner/test and the complete transitive
runtime/scorer/probability-contract chain match the frozen commitments. All
seven immutable Attempt-3 artifact hashes also match.

## Source, population and boundaries

- Source manifest/cohort rehash to
  `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
  and `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.
- All **780/780** event source-file hashes match; all **194/194** compressed
  catalog payloads decompress to their recorded raw hashes.
- Population accounting is exactly **195 source / 194 materialized / one
  exclusion**. The sole exclusion is `2025_04_GB_DAL`,
  `unresolved_outcome`.
- The check mask is **87 unique events / 20 dates / seven observed weeks**,
  hash `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
- Dev/Final, external fetch, paid provider and promotion are closed; provider
  cost is recorded as `$0`.

## Independent weight, objective and prediction replay

Every fold uses all eligible numeric game-weeks strictly before its first
check week. The saved ordered event ledgers, per-week counts, powers-of-two
weights, class totals, total/squared weights and Kish counts reproduce exactly.

| Fold | Rows | Weight sum | Squared sum | Kish rows | Weighted moment | Saved beta | Objective | Gradient |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 107 | 29.625 | 19.94140625 | 44.01097 | -0.135154 | -0.112136 | 0.5911714593 | `+6.03e-12` |
| 2 | 120 | 27.8125 | 17.9853515625 | 43.00918 | +0.070269 | +0.055870 | 0.5569578377 | `-3.12e-11` |
| 3 | 148 | 27.953125 | 18.62408447265625 | 41.95520 | +0.042343 | +0.036329 | 0.6223802701 | `-1.03e-14` |
| 4 | 177 | 28.48828125 | 18.914005279541016 | 42.90906 | +0.154840 | +0.123092 | 0.5208189651 | `-4.25e-12` |

The prior-only transform parameters reproduce exactly in all four folds. A
direct evaluation of `sum(a*NLL)/sum(a) + 0.5*beta^2` and its analytic
gradient at the saved coefficients reproduces all saved objective and gradient
values with maximum absolute difference **0.0**. Applying those coefficients
to the replayed check transforms reproduces all 87 candidate probabilities
with maximum absolute difference **0.0**. This verification did not optimize
or refit anything.

The first 16 identity/outcome/market/control fields in the 87 prediction rows
match the immutable Attempt-3 predictions exactly: **1,392/1,392 cells**.
Thus market, ordinary, calibration, full offset and Attempts 1-3 are genuinely
archive-bound controls, not refits.

## Independently reproduced scores and decision

| Arm | Brier | Log loss | Calibration slope |
| --- | ---: | ---: | ---: |
| Attempt 3 incumbent | **0.2038565961** | **0.5958367713** | 0.999862 |
| Attempt 2 | 0.2042380588 | 0.5963727488 | 1.001434 |
| Attempt 4 candidate | 0.2044223641 | 0.5970803064 | 1.000769 |
| Decision-time market | 0.2055333637 | 0.5984509292 | 1.015513 |
| Market-only calibration | 0.2058518570 | 0.5993850089 | 1.006707 |
| Attempt 1 | 0.2069233196 | 0.6025293021 | 0.981297 |
| Archived full offset | 0.2094506542 | 0.6082677941 | 0.938536 |
| Ordinary reference | 0.2356047245 | 0.6759482937 | 0.636661 |

Independent recomputation of every aggregate/fold score and calibration term
differs by at most `1.11e-16`; every aggregate pairwise delta differs by at
most `8.33e-17`.

Candidate-minus-reference deltas; negative is better:

| Reference | Brier delta | Log-loss delta | Brier fold wins |
| --- | ---: | ---: | ---: |
| Market | -0.001111000 | -0.001370623 | **3/4** |
| Ordinary | -0.031182360 | -0.078867987 | **4/4** |
| Attempt 3 incumbent | **+0.000565768** | **+0.001243535** | **1/4** |

Candidate-minus-v3 fold Brier deltas are
`-0.0004072, +0.0005962, +0.0013848, +0.0006763`; log-loss deltas are
`-0.0013018, +0.0016133, +0.0035562, +0.0009793`. Only Fold 1 improves.
Consequently all market/ordinary gates pass, but all three incumbent gates
fail: aggregate Brier, aggregate log loss and Brier wins in at least three
folds. The exact frozen decision is therefore **REVERT**.

## Grouped inference and interpretation

An independent seed-23, 1,000-replicate reconstruction sampled complete units,
pooled repeated units' events, and recomputed equal-event means. Every stored
candidate comparison, point estimate and percentile interval reproduces within
`2.78e-17`.

Candidate-minus-v3 intervals all cross zero:

- complete schedule dates: Brier `[-0.0003739, 0.0016465]`, log loss
  `[-0.0010377, 0.0037735]`;
- observed NFL weeks: Brier `[-0.0004712, 0.0017803]`, log loss
  `[-0.0011344, 0.0040694]`.

Attempt 4 beats v3 in mean Brier on only **9/20 dates** and **2/7 weeks**.
Against the market it is better on 11/20 dates and 5/7 weeks, but its
date/week intervals also cross zero. These are descriptive adaptive-Train
diagnostics, not promotion evidence.

## Final conclusion

**PASS, 0 P0 / 0 P1.** The artifact and `REVERT` decision are correct.
Extending coefficient-fit support to all prior weeks with a one-week half-life
did not improve the incumbent prediction: Attempt 4 is slightly worse than v3
on both aggregate proper scores and in three of four folds. Under the
`indicator-prediction-evals` separation, this is a trainer-support result, not
a raw-signal or objective result. Preserve the branch and its diagnostics,
retain MarketRecencyWeightedCompositePath-v3 as incumbent, and make no OOS,
profitability, promotion, generalization or self-evolution claim.
