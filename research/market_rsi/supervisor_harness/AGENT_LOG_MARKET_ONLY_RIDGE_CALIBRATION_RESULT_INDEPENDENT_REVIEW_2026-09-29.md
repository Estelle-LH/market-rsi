# MarketOnlyRidgeCalibration-v1 real Train result — independent review

Review completed: `2026-09-29T17:58:27Z`.

## Verdict

**PASS at 0 P0 / 0 P1.** The completed artifact is internally bound and its
predictions, proper scores, fold results, grouped intervals and `REVERT`
decision reproduce independently. The past-fitted market-only calibration is
slightly worse than the unchanged decision-time market on both aggregate
proper losses. It substantially beats the ordinary LogisticRegression
reference, while the archived full-offset model is worse than this restricted
calibration control.

This is repeatedly inspected, opened-Train Discovery evidence. It is not
untouched OOS evidence, a promotion result, a profitability result, or evidence
of transfer beyond the 2025 NFL seed domain. The review did not fit another
real model, run another real experiment, read protected Dev/Final, use a
network or provider, or change experiment code. The only file written by this
review is this log.

Reviewed result:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-only-ridge-calibration-20260929-01`

## Artifact, source and parent-chain integrity

The result directory contains exactly seven files. Independently recomputed
SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| `exclusions.json` | `c6e8d143c0aa20610e1ea391200d692bff94ee0fd39e3e9107993fae7538f131` |
| `input_receipts.json` | `db6506a0544a82b2a51d82bc65fb77f1a435f511da34f568041aea7d64f2f297` |
| `manifest.json` | `a6e2e63b97fabab640c83f264e2c3afdbee1390f90dd2f1c39ffeb31131f37bb` |
| `pre_score_lock.json` | `190a846bf29edb1418ba7a2677d8cc87aa1b488cfe3284943d75a21481537ac7` |
| `predictions.csv` | `b9d28742157dd79cead5d2f22071daaa40526ad78b55b6a9c007f43c9e5f2358` |
| `scorecard.json` | `513856565af0cd9d4142b875d9fb38b3141bb59da58f330d4a6fa1c9144e7f2b` |
| `staleness_inventory.json` | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

Every manifest-to-artifact binding matched. The pre-score lock binds the exact
input receipts, exclusion ledger and staleness inventory. Current reviewed
source hashes also match every recorded execution commitment:

| Binding | SHA-256 |
| --- | --- |
| Calibration runner | `71d329468c865246616b8cb1ee7b284a488c9ad382f2bda830bb529e383cc191` |
| Calibration tests | `548d8d633fc2007414d10874b11300442ebb97719eb101bb451cd3bd8d755bb0` |
| Offset runner | `6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f` |
| Offset tests | `409fd88d93c59b5d0bb25a1765471ad9249c0a5872cc77d31e69922a77fd0f41` |
| Base settlement runner | `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b` |
| Base tests | `6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927` |
| Proper scorer | `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b` |
| Probability contract | `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74` |
| Controller proposal | `cd40d3e9dababfd0da1548c4ea61e505e12fa6de2c1af0003f4f787179bf5622` |

All seven archived full-offset files matched the calibration receipt and that
archive's internal completed-manifest bindings. Its market and ordinary rows
in turn matched the original settlement parent on all 87 identities and
values. The archived prediction SHA is
`d917a1980bc0b4621ee9ab0cdc6672b47e58cbea0ae4ed335c952d40dd51288c`;
the original parent prediction SHA remains
`f91647a2a5b84836bd717ce2d0c6fd404bc1f4a759342a8b8d40fc6e576f37c1`.

The source manifest and cohort reproduce
`429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
and `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.
For all 195 cohort events, all four recorded source hashes matched: **780/780**.
All **195/195** compressed catalog objects decompressed to the recorded raw
hash and byte count. All **195/195** trade manifests matched game, condition,
tokens, Train boundary and trade-window hash. Re-materialization without any
fit reproduced the **194/194** materialized-event receipts and exact key digest
`59128473ae6c50b4acd2436ac18478d4fcd7dbd96ee887eb5ce2ae77ddfc72bd`.

## Population, staleness, chronology and runtime behavior

- Frozen denominator: **195 events / 42 schedule dates**.
- Materialized: **194/195**. The sole exclusion remains source ordinal 53,
  `2025_04_GB_DAL`, schedule date `2025-09-28`, with reason
  `unresolved_outcome` for non-binary `[0.5, 0.5]` settlement values.
- The inclusive 600-second staleness gate covered all 194 binary events.
  Independently reconstructed ages range from **0 to 313 seconds**, with zero
  violations and no event removed by the gate.
- The four chronological folds reconstruct as **107/26, 133/16, 149/28,
  177/17** fit/check events. Every fit outcome was available before its first
  check cutoff; unavailable counts are `0/0/0/0`.
- The common check population is **87 events / 20 complete schedule dates / 7
  observed NFL week clusters**. The canonical mask independently reproduces
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
- Static control-flow review finds one calibrator solver call and one ordinary
  `.fit(...)` call inside the four-fold loop. The archive is loaded as CSV and
  never fitted. The completed receipt therefore agrees with exactly **4
  calibrator + 4 ordinary fits and 0 archived full-offset refits**.

The runtime receipt remains persistent local CPython 3.12.3 with NumPy 1.26.4,
SciPy 1.14.0 and scikit-learn 1.6.1.

## Market-only input, scaling and fitted parameters

The calibrator's prediction-time calculation was independently reconstructed
as `sigmoid(market_logit + b + w*z_market_logit)` from each earlier-fold fit
population. It uses no non-market feature value at prediction time. For every
fold, the independently computed one-column `ddof=0` mean and scale equal both
the persisted values and column zero of the 17-column fit-only scaler; maximum
absolute difference is **0.0**. Every one of the 87 persisted calibration
probabilities matches the reconstructed formula with maximum absolute
difference **0.0**.

| Fold | `b` | `w` | `mu` | `scale` | affine-logit intercept | affine-logit slope |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.0200807645 | 0.0054140352 | 0.2167502500 | 0.8097921620 | 0.0186316353 | 1.0066857095 |
| 2 | -0.0018583359 | 0.0029704665 | 0.2458911957 | 0.8480558285 | -0.0027196136 | 1.0035026780 |
| 3 | -0.0009207376 | 0.0040830729 | 0.2458382776 | 0.8510827572 | -0.0021001477 | 1.0047975040 |
| 4 | 0.0057903166 | 0.0133840913 | 0.2245357305 | 0.8747558957 | 0.0023548362 | 1.0153003728 |

The independently recomputed penalized mean-NLL objectives equal all four
stored objectives. The final gradient infinity norms are
`2.196e-10`, `2.634e-11`, `1.250e-10` and `2.227e-12`, all below `1e-6`;
all optimizers report success/status 0. The small affine slopes show that this
fixed lambda-1 recipe made only a slight adjustment to the market. That is an
observation about this chosen recipe, not proof that every market calibrator
would behave similarly.

Market, ordinary and archived full-offset values in the new 87-row CSV match
their exact parent rows with maximum absolute difference **0.0**. Thus all four
arms use one outcome/key mask and the full-offset attribution is based on
archived predictions, not a hidden refit.

## Independently reproduced scorecard

All Brier losses, bounded log losses and OLS outcome-on-probability calibration
diagnostics were recomputed directly from `predictions.csv`.

| Forecast | Equal-event Brier | Equal-event log loss | Calibration slope | Calibration intercept |
| --- | ---: | ---: | ---: | ---: |
| Decision-time market | 0.20553336372767944 | 0.5984509292283796 | 1.0155134726661597 | -0.029218480860792484 |
| Ordinary LogisticRegression | 0.23560472453952527 | 0.6759482937171853 | 0.6366611551135252 | 0.17273454690115536 |
| MarketOnlyRidgeCalibration-v1 | 0.20585185704759978 | 0.5993850088689292 | 1.0067066778386775 | -0.025614803510338846 |
| Archived MarketOffsetRidgeLogistic-v1 | 0.20945065421878312 | 0.6082677941274733 | 0.9385363221033207 | 0.014390690942336914 |

Loss deltas use `left minus right`; negative is better:

| Comparison | Brier delta | Log-loss delta |
| --- | ---: | ---: |
| Calibration minus market | +0.0003184933199203891 | +0.0009340796405495402 |
| Full offset minus calibration | +0.003598797171183312 | +0.008882785258544202 |
| Calibration minus ordinary | -0.029752867491925506 | -0.07656328484825611 |
| Full offset minus market | +0.003917290491103701 | +0.009816864899093742 |
| Full offset minus ordinary | -0.02615407032074219 | -0.06768049958971191 |
| Ordinary minus market | +0.03007136081184589 | +0.07749736448880565 |

Calibration-minus-market Brier fold wins are **2/4**:
`false, true, true, false`. Calibration-minus-ordinary Brier fold wins are
**4/4**. Every fold score and every persisted pairwise arithmetic field was
reproduced.

The experiment therefore separates the two effects cleanly for this finite
recipe: the market-only fitted calibration did not improve aggregate market
proper scores, while adding the other 16 residual columns made both losses
further worse than the restricted calibration control. This does not prove
that those feature families have no usable incremental information; it says
this residual representation/trainer did not extract a benefit on these reused
Train checks.

## Complete-day and observed-week inference

The grouped procedure was reimplemented from the 87 persisted rows without
calling the runner's interval helper. Each draw samples observed units with
replacement, pools all games from sampled units including repetitions, and
then recomputes the equal-game loss delta. Seed 23 and 1000 draws reproduce
every stored interval exactly. All **270** per-unit event count, sum and mean
records across five pairwise comparisons, two losses, 20 schedule days and
seven observed weeks also reproduce exactly.

Key intervals are:

| Comparison | Unit | Brier 95% percentile interval | Log-loss 95% percentile interval |
| --- | --- | --- | --- |
| Calibration minus market | 20 complete schedule dates | `[-0.00018439987936904657, 0.0009299675751371983]` | `[-0.00047563651478004773, 0.002710911989019646]` |
| Calibration minus market | 7 observed week clusters | `[-0.00010574667455404756, 0.0008406134750823236]` | `[-0.0003143203809534615, 0.002511899859228294]` |
| Full offset minus calibration | 20 complete schedule dates | `[0.0006295251031694627, 0.006695366956236674]` | `[0.0013349056489460342, 0.016622790241230152]` |
| Full offset minus calibration | 7 observed week clusters | `[0.0008492925316776264, 0.006187456908107343]` | `[0.0016706672742309522, 0.015133345724972463]` |

Schedule-day event counts are exactly the stored 20-unit distribution. Week
counts are `13/14/14/15/14/16/1` for Weeks 08–14. Week 14 is a one-event
partial right-edge cluster and is correctly disclosed as a sensitivity rather
than a complete-week claim. These intervals remain descriptive under repeated
Train inspection; 20 dates and seven observed weeks do not establish formal
independent significance.

## Decision, branches and claim boundary

The frozen rule requires the calibration candidate to beat both market and
ordinary on aggregate Brier and log loss by more than `1e-12`, and to win at
least three of four Brier folds against each. It beats ordinary on both losses
and 4/4 folds, but loses both aggregate losses to market and wins only 2/4
market folds. The exact result is therefore **REVERT**.

REVERT changes only the current-best prediction: the decision-time market
remains the current best for Discovery. The calibration, full-offset and HGB
branches stay preserved with their code, artifacts and lessons. Ordinary
LogisticRegression remains an ordinary reference, never `Strong-Baseline-1`.

The lock correctly separates literature-supported principles (strictly prior
fitting, fit-only preprocessing, dependence-aware grouping), project choices
(NFL seed cohort, 15-minute cutoff, 600 seconds, 22 + 4x5 dates, affine-logit
lambda 1, optimizer settings, seed and KEEP rule), and unvalidated hypotheses
(market-only calibration or additional residual columns can improve future
proper scores). This review does not promote project parameters to literature
consensus.

The artifact, source receipts and static imports consistently show Route-Dev
false, sealed Final false, external fetch false, paid provider false, provider
cost `$0` and promotion false. The no-network synthetic test remains present.
Unsupported after this PASS: promotion, formal OOS gain, profitability,
executable-price performance, generalization beyond the 2025 NFL seed domain,
causal attribution to individual added features, or evaluation of the RSI
self-evolution hypothesis.

## Verification run

The persistent-runtime canonical command covering the calibration runner and
both parent-adjacent suites passed **34/34 tests** in 1.376 seconds. Coverage
includes finite-difference gradient, zero-residual market recovery, objective
and penalty semantics, fit-only one-column scaler parity, invariance to the 16
unused check columns, 600/601-second behavior, exact mask and archive parity,
unequal-day event-weighted resampling, deterministic execution, no-network
execution, exactly four calibrator calls, eight total local fits, zero archive
refits and the exact KEEP/REVERT rule.

The review applied the local `indicator-prediction-evals` evaluation gates for
same-row proper scoring, strictly earlier fitting, dependence-aware inference,
branch preservation and the mandatory distinction between reused Train
Discovery and untouched OOS.
