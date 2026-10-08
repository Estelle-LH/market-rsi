# `InGameWinProbabilityTrainDiagnostic-v0` result — independent review

Date: 2026-09-29  
Verdict: **PASS**  
P0: none  
P1: none  
Result: **`PBP_INCREMENT_NOT_SUPPORTED`**

The completed artifact is internally hash-bound and its arithmetic, grouped
uncertainty and frozen decision reproduce independently. Adding the fixed
pre-play PBP state to the same logistic trainer made both aggregate proper
scores worse than the market-only logistic control and won Brier in only one
of four folds. The registered three-part increment rule therefore fails on all
three conditions. This negative result must be retained as-is; it does not
support the proposed PBP data increment.

This review did not invoke the runner, refit a model or read a new score. It
used the already completed artifact, frozen source and read-only arithmetic.
It did not access Dev/Final, contact a network/provider, spend money, publish,
promote or change research state. The only written file is this review log.

## Exact artifact and frozen identity

Artifact:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-win-probability-train-diagnostic-20260929-01`

The directory contains exactly seven regular result files:

| File | SHA-256 |
| --- | --- |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |
| `exclusions.json` | `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1` |
| `input_receipts.json` | `0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18` |
| `manifest.json` | `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7` |
| `pre_score_lock.json` | `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2` |
| `predictions.csv` | `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56` |
| `scorecard.json` | `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87` |

Every manifest-to-file hash and the input-receipt-to-checkpoint hash matches.
The manifest is complete and records exactly eight model fits: the two
logistic arms in each of four folds.

Frozen implementation identity also matches the passing pre-score review:

- runner:
  `e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7`;
- R checkpoint extractor:
  `37a26997406de0e54bd9d91de10e7417a8b340c68b675892c4f16e9a51675163`;
- focused tests:
  `6198546e99467ec22d45db42ec609199c7a7b8c21cf07c609b216f8b8d3fb29d`;
- pre-score review:
  `7f21e991d7bf45a0bb59bb4424eb8cdfa7eeeb5839ba5147837a605713426abd`;
- settlement dependency:
  `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b`;
- probability contract:
  `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74`;
- proper scorer:
  `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b`.

The opened-Train source manifest and cohort independently hash to
`429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
and `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`,
matching `input_receipts.json`.

## Population, exclusions, masks and chronology

- The deterministic extractor produced one Q3 checkpoint anchor for each of
  the **195** source games. Market/outcome materialization then produced
  **193**, with exactly two recorded exclusions:
  `2025_04_GB_DAL` / `unresolved_outcome`, and
  `2025_05_TEN_ARI` / `market_trade_too_stale` at
  `1088.1570000648499` seconds. Thus `195 = 193 + 2` exactly.
- The OOF result has **87** rows on 20 schedule dates and seven observed game
  weeks. All 87 game IDs and all 87 `(event_id, market_id, cutoff_ms)` keys are
  unique. The recomputed common-mask hash is
  `2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
  Every row contains the same outcome and checkpoint for raw market,
  market-only logistic and market-plus-state logistic, so there is exactly one
  checkpoint per game and no arm-specific attrition.
- Fold 1 uses **106** prior fit events. The expanding fit counts are
  **106/132/148/176**, and the four disjoint check counts are
  **26/16/28/17**, totaling 87.
- All four recorded fit-label-unavailable lists are empty and all four bind to
  the canonical empty-list SHA-256
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
  Each fold records the same rows, labels, trainer and budget across the two
  fitted arms.

## Independently reproduced scores

All values below were recomputed directly from the 87 saved predictions, not
read from the scorecard aggregates.

| Arm | Brier | Log loss | Calibration slope | Calibration intercept |
| --- | ---: | ---: | ---: | ---: |
| Raw decision-time market | 0.141952529003 | 0.429670784713 | 1.037038749465 | -0.011806646530 |
| Market-only logistic | 0.145482312533 | 0.439921972456 | 1.056812265970 | -0.023504802268 |
| Market plus PBP state logistic | 0.160680990165 | 0.471197319267 | 0.918685645887 | 0.048131678738 |

State-minus-market-only deltas, where negative loss would be better, are
**+0.015198677632 Brier** and **+0.031275346810 log loss**. The four fold Brier
deltas are `+0.019582073407`, `-0.008537564340`, `+0.014332653104`, and
`+0.032261046349`: only fold 2 is a win, or **1/4**.

Market-only logistic also trails the raw decision-time market by
**+0.003529783529 Brier** and **+0.010251187743 log loss**. This secondary
comparison is model/calibration evidence, not PBP-increment evidence.

## Independently reproduced grouped intervals

I reconstructed the frozen 10,000-replicate, seed-20260929 bootstrap by
resampling complete schedule-date or observed-game-week groups and computing
the pooled equal-event mean in each draw. Stored points and percentile bounds
reproduce to floating-point precision.

State-minus-market-only intervals:

| Loss | Schedule-date 95% | Observed-week 95% |
| --- | --- | --- |
| Brier | `[-0.000902521898, 0.031426222859]` | `[-0.000904043751, 0.030835726851]` |
| Log loss | `[-0.008446365127, 0.071090392361]` | `[-0.006242722475, 0.068977752085]` |

Market-only-minus-raw-market intervals are strictly positive (worse):

| Loss | Schedule-date 95% | Observed-week 95% |
| --- | --- | --- |
| Brier | `[0.001390923792, 0.006196657370]` | `[0.002174672370, 0.005871938923]` |
| Log loss | `[0.005302707733, 0.017106468578]` | `[0.006487807031, 0.016543704873]` |

The state intervals crossing zero do not rescue the candidate: the frozen
decision is a deterministic proper-score/fold rule, not a significance-test
override.

## Decision and boundaries

The pre-score lock requires all three of the following: state-model aggregate
Brier below market-only, state-model aggregate log loss below market-only, and
state-model Brier wins in at least three of four folds. Independently
recomputed conditions are **false / false / false**, with fold wins
`[false, true, false, false]`. The only valid decision is therefore
**`PBP_INCREMENT_NOT_SUPPORTED`**. A negative result cannot be converted into
support by changing the rule after scores are known.

This is repeatedly inspected opened-Train Discovery evidence. It does not
establish real-time edge, untouched OOS validity, PnL, or a cross-task score
comparison, and it does not authorize adopting the PBP feature set. It may be
used as an immutable negative branch when selecting a distinct next
opened-Train Discovery hypothesis, provided that future work keeps the same
Dev/Final and promotion boundaries and obtains its own pre-score review.

The artifact and lock consistently record no external fetch, no paid provider,
provider cost `$0`, Route-Dev unopened, sealed Final unopened and no promotion
authorization. **PASS, P0 none, P1 none.**
