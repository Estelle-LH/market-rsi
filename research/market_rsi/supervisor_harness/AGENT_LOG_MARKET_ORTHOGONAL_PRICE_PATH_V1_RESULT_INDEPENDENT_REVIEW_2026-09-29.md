# MarketOrthogonalPricePath-v1 real Train result — independent review

Review completed: `2026-09-29T18:28:41Z`.

## Verdict

**PASS at 0 P0 / 0 P1.** The completed artifact is internally bound and its
lineage, predictions, five-arm proper scores, fold results, grouped intervals,
diagnostics and `REVERT` decision reproduce independently.

The candidate is better than the ordinary LogisticRegression reference and
the archived 17-feature full-offset branch, but it is worse than both the
unchanged market and the market-only calibration control on aggregate Brier
and log loss. It wins Brier against market and calibration on only one of four
folds. `REVERT` is therefore the exact frozen decision: decision-time market
remains the current best, while the orthogonal price-path branch and its
evidence remain available for Discovery.

This is repeatedly inspected opened-Train Discovery, not untouched OOS,
promotion, profitability or self-evolution evidence. This review performed no
model fit or optimizer call and did not read protected Dev/Final, acquire new
data, use a network/provider, publish or promote. It only read the existing
local source/artifacts and independently reconstructed the locked arithmetic.
The only repository file written by this review is this log.

Reviewed artifact:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-orthogonal-price-path-20260929-01`

## Exact artifact and execution identity

The artifact contains exactly seven files:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `e6ccbe815a5872261d3c07958506a602ed96ca0355913b079a1594c44a91fa3a` |
| `input_receipts.json` | `51fa298e2f6c7b672aedba1ed3d14aa5542e0f00232498f957a84298578c584d` |
| `manifest.json` | `e3ec0981f705ec511fa830680ddbe5f2e490e6a6be6eaa58550204de20725da4` |
| `pre_score_lock.json` | `365416786811f393ffa0e39f808404b8987f67c69b0c7bdce0b498363a51d9f4` |
| `predictions.csv` | `9d2d15a4a61d91aabc0862809906aebf8be7382dfaa380064676284ecd02dcc6` |
| `scorecard.json` | `263acc091232f0d3c27a3e4cd8bd0ef7aa392e00f06a0fc89dc6323c2692e4a4` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

Every manifest-to-file binding matches. The result binds the exact reviewed
runner `af4508f0c808fbc236daae6607343c47238db26e2148289a08670fe71102f380`,
tests `71e576f4a74aba6a334d09f76dc3d2023122b126a0b11ded8b2ddec6e2aad40a`
and pre-score review
`f79208cf09807f2f477acb98df40b6c251fb9834a0b6d3c4677080329aef713e`.
The recorded runtime is the bound persistent CPython 3.12.3 environment with
NumPy 1.26.4, SciPy 1.14.0 and scikit-learn 1.6.1. Parent runner, test, proper
scorer, probability-contract, Controller proposal and archived calibration
hashes all match their frozen commitments.

## Source lineage, population and boundaries

- The source manifest and cohort independently rehash to
  `429a0ef...0074f` and `ba07b553...7885`.
- All four recorded source hashes matched for all 195 cohort members:
  **780/780**. All **195/195** compressed catalog payloads decompressed to the
  recorded raw hash and byte count.
- All **194/194** materialized receipts match their corresponding source
  receipts. An independent reconstruction from catalog event/market identity
  and kickoff minus 15 minutes reproduces the materialized key digest
  `59128473ae6c50b4acd2436ac18478d4fcd7dbd96ee887eb5ce2ae77ddfc72bd`.
- Population accounting is exactly **195 source events / 42 dates = 194
  binary events + one exclusion**. The sole exclusion is source ordinal 53,
  `2025_04_GB_DAL`, date `2025-09-28`, reason `unresolved_outcome` for
  non-binary settlement values.
- The inclusive 600-second gate checked all 194 binary events. Observed age is
  0–313 seconds, with zero violations and no staleness attrition.
- Predictions contain exactly **87 unique events / 20 complete schedule dates
  / seven observed NFL weeks**. The independently reconstructed canonical mask
  is `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
  Fold check counts are 26/16/28/17 and recorded fit/check counts remain
  107/26, 133/16, 149/28 and 177/17 with no unavailable fit label.
- Week counts are 13/14/14/15/14/16/1 for Weeks 08–14. Week 14 is correctly
  disclosed as a one-event partial right edge, not a complete week.
- All predictions are finite and inside the frozen `[1e-6,1-1e-6]` contract.
  Home orientation, kickoff-minus-15-minute cutoff and event identities are
  unchanged.
- The manifest and lock record Route-Dev false, sealed Final false, external
  fetch false, paid provider false, provider cost `$0` and promotion false.

The exact source control flow and reviewed call-count regression establish four
candidate, four calibration-control and four ordinary-reference fits. The
manifest reports the same **12 total fits**. Frozen ordinary and calibration
predictions match the archived calibration artifact with maximum absolute
difference **0.0**, and the full-offset arm is byte-bound archive data with
zero refits.

## Independently reproduced scorecard

All losses and OLS outcome-on-probability calibration values were recomputed
directly from the 87-row prediction file.

| Arm | Equal-event Brier | Equal-event log loss | Calibration slope |
| --- | ---: | ---: | ---: |
| Decision-time market | 0.2055333637 | 0.5984509292 | 1.0155134727 |
| Market-only calibration | 0.2058518570 | 0.5993850089 | 1.0067066778 |
| MarketOrthogonalPricePath-v1 | 0.2069233196 | 0.6025293021 | 0.9812974660 |
| Archived 17-feature full offset | 0.2094506542 | 0.6082677941 | 0.9385363221 |
| Ordinary LogisticRegression reference | 0.2356047245 | 0.6759482937 | 0.6366611551 |

Loss deltas use `candidate minus reference`; negative is better:

| Comparison | Brier delta | Log-loss delta | Brier fold wins |
| --- | ---: | ---: | ---: |
| Candidate minus market | +0.0013899559 | +0.0040783729 | 1/4 |
| Candidate minus market-only calibration | +0.0010714625 | +0.0031442933 | 1/4 |
| Candidate minus archived full offset | -0.0025273346 | -0.0057384920 | 3/4 |
| Candidate minus ordinary reference | -0.0286814050 | -0.0734189916 | 4/4 |

Every fold score and stored delta reproduces. Candidate Brier versus market is
worse in Folds 1–3 by `+0.0027720`, `+0.0014263`, `+0.0010733`, then better in
Fold 4 by `-0.0002365`. Candidate log loss remains worse than market in all
four folds, including `+0.0005891` in Fold 4.

## Corrected grouped inference

An independent seed-23, 1000-replicate implementation sampled whole observed
units with replacement, pooled all repeated games, and recomputed the
equal-event mean within every draw. It reproduced all 20 stored
comparison/loss/unit reports, including every per-unit count, sum and mean.

Key complete-schedule-date 95% descriptive percentile intervals are:

| Comparison | Brier interval | Log-loss interval |
| --- | --- | --- |
| Candidate minus market | `[-0.0011676, 0.0047585]` | `[-0.0016194, 0.0120504]` |
| Candidate minus calibration | `[-0.0017523, 0.0044049]` | `[-0.0033118, 0.0110562]` |
| Candidate minus full offset | `[-0.0062500, 0.0024521]` | `[-0.0164342, 0.0074764]` |
| Candidate minus ordinary | `[-0.0522531, -0.0036141]` | `[-0.1398599, -0.0056640]` |

The seven-observed-week sensitivity also reproduces. Candidate-minus-market
intervals are `[-0.0013929, 0.0044780]` Brier and
`[-0.0016440, 0.0109346]` log loss. These adaptive Train intervals are
descriptive; seven observed clusters include a partial week and do not provide
formal selection-adjusted or untouched-OOS inference.

## Transform, optimizer and diagnostic reconstruction

Without fitting another model, the review independently rematerialized the 194
rows and reconstructed each fold's exact named-column formulas, fit-only market
scaler, `lstsq(rcond=1e-12)` residualizer, family scaling, fixed design,
four-parameter objective, analytic gradient and candidate probabilities.

- All four transforms have rank two; neither family is inactive. Fit residual
  standard deviations range from 0.00611–0.00699 for `g` and
  0.01031–0.01066 for `d`.
- Fit residual correlations with market logit are at most `2.2e-16` in
  absolute value. Saved betas, singular values, fit moments and every fit/check
  diagnostic reproduce within numerical precision.
- Candidate probabilities, penalized objectives and final gradient infinity
  norms reproduce with maximum absolute difference **0.0**. All optimizers
  report success and gradient infinity norms below `1e-8`, tighter than the
  required `1e-6`.
- The two residual families remain strongly collinear: correlation is
  0.791–0.826 on fit rows and 0.822–0.912 on check rows.
- Fit Pearson association with `y-p_market` moves from negative toward positive
  across expanding folds: `g` is -0.115/-0.057/-0.032/+0.027 and `d` is
  -0.109/-0.055/-0.020/+0.027. Check associations are positive in every fold.
  Correspondingly, fitted `w_g/w_d` are negative in Folds 1–3
  (`-0.0379/-0.0352`, `-0.0189/-0.0180`, `-0.0112/-0.00585`) and positive in
  Fold 4 (`+0.00897/+0.00859`).

The evidence is consistent with sign/regime instability plus substantial
redundancy between the two compressed families. Compression reduced the damage
of the 17-feature full-offset model, but this fixed prior-only trainer still did
not extract incremental proper-score value beyond market or market-only
calibration. This does **not** establish that signed price history contains no
information or that the branch should be deleted.

## Decision and claim boundary

The frozen KEEP rule requires aggregate Brier and log loss improvements over
both market and ordinary plus at least 3/4 Brier fold wins against each. The
candidate clears every ordinary-reference condition but clears neither
aggregate market loss and wins market Brier only 1/4 folds. The exact result is
therefore **REVERT**.

`REVERT` changes only the current-best prediction recipe. Decision-time market
remains incumbent; the orthogonal price-path, calibration, full-offset and HGB
branches remain research evidence. Unsupported claims remain promotion,
formal OOS gain, profitability, generalization beyond the 2025 NFL seed domain,
nonlinear conditional independence, transferable research skill and RSI
self-evolution.

The `indicator-prediction-evals` gates informed this review: equal-event
same-row proper scoring, prior-only transforms, sign and collinearity diagnosis,
event-weight-preserving grouped resampling, branch retention, and the strict
separation of adaptive Train Discovery from independent future evaluation.
