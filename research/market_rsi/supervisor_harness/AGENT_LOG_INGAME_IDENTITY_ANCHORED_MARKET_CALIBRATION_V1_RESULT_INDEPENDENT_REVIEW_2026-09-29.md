# InGameIdentityAnchoredMarketCalibration-v1 — independent result review

Date: 2026-09-29  
Verdict: **PASS artifact; frozen decision REFUTED / scheduler REVERT.**  
P0: none. P1: none.

## Integrity and lineage

The sole completed artifact at
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-identity-anchored-market-calibration-20260929-01`
contains the exact completed files and hashes:

| File | SHA-256 |
| --- | --- |
| `manifest.json` | `b5374d0e7dc4856b7d4ece209a514c92bbe118a0d157ccc43d8fa168be8e9671` |
| `predictions.csv` | `1697206b769fb31d6e6230792934250bfa9ce5de1c93014b7ee817e9e4868d33` |
| `scorecard.json` | `34194de75a11498f480f84af5eaeb30f91365d667089c620f8a19e7e1f2ec98e` |
| `pre_score_lock.json` | `ba5ad998d9b54b448fd9941e3c61354632f24f23bb77fa3cb979a1e9019f4800` |
| `input_receipts.json` | `51f2fe488f8b80fddd551d46af3842550e3e2fe9f2f4bcd5f5aa3cf4faf932e6` |
| `exclusions.json` | `43ba359d89102ab733db8f0dc29e6b5a382e7cb7ce0b9e9cfa5438bed03db8ec` |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |

Manifest cross-links match. The lock binds Controller
`a6259940...`, runner `dc4e3724...`, component spec `128321cc...`, exact
question/hypothesis/rule, and selected `attempt-02`. Source reconciliation is
exactly `195 -> 193 + 2` named exclusions -> `87` OOF checks. The 87 unique
keys, identities, outcomes and raw/ordinary/parent probabilities match the
frozen v0 predictions row-for-row; check-key SHA-256 is `2e35779f...`.

## Independent arithmetic replay

I parsed the CSVs directly without importing or calling the candidate runner.
Fold counts are `26/16/28/17`, spanning 20 schedule dates and seven observed
weeks. Independently recomputed aggregate values are:

| Arm | Brier | Log loss | Calibration intercept / slope |
| --- | ---: | ---: | ---: |
| raw market incumbent | `0.14195252900323282` | `0.4296707847132428` | `-0.011806646530491793 / 1.0370387494646494` |
| ordinary market-only | `0.14548231253271718` | `0.43992197245621956` | `-0.023504802267641844 / 1.0568122659695651` |
| v0 market-plus-state parent | `0.16068099016465245` | `0.4711973192666776` | `0.04813167873790908 / 0.9186856458868063` |
| identity-anchored candidate | `0.14365046442423748` | `0.43356522090452837` | `-0.0019466103423365633 / 1.0186701651549077` |

All aggregate and per-fold scores/calibration matched with maximum absolute
error `0`. The candidate beats ordinary market-only by
`-0.0018318481084796797` Brier and `-0.006356751551691142` log loss, but is
worse than raw market by `+0.0016979354210046663` Brier and
`+0.0038944361912855545` log loss. It wins Brier against ordinary in folds
`[true,false,true,true]`, but against raw market in
`[false,false,false,false]`.

Independent 10,000-draw complete-group replay at seed `20260929` matched every
stored interval exactly. Candidate-minus-raw Brier intervals are
`[-0.00017203974114176317, 0.0034008043253159715]` by date and
`[0.0005989656805259836, 0.0029317150048526384]` by week. Corresponding log-loss
intervals are `[-0.0009076230978426025, 0.008302351982049304]` and
`[0.0008065347913669283, 0.007405045901899594]`.

For each row I independently reconstructed
`sigmoid(logit(p_raw)+alpha+delta*z_market)` from its fold's persisted fit-only
mean/scale and Newton parameters; maximum probability discrepancy is `0`.
All four optimizers converged in three iterations, penalty is exactly `16`,
retry count is zero, and gradient infinity norms are `<=4.14e-14`, well below
the frozen `1e-8` threshold. Fit counts are `106/132/148/176`; no fit label is
unavailable.

## Decision and scheduler recommendation

The candidate does not beat raw market on either aggregate proper score, wins
raw Brier in `0/4` folds, and both required grouped Brier upper bounds are
positive. Exact replay therefore returns
`IDENTITY_ANCHORED_MARKET_CALIBRATION_REFUTED_REVERT`.

- performance: **REVERT**;
- incumbent: keep raw market unchanged;
- scientific outcome: **`refute`** for this exact fixed-penalty identity-anchored
  calibration question;
- research-credit recommendation: **2**;
- route action: **`stop`**.

Credit 2 records a valid, independently reproduced negative answer that stops
this exact route; it is not a score bonus. The result shows that anchoring
improves substantially over the ordinary fitted market-only control, but not
over the unfitted raw-market incumbent. It does not reject every possible
market calibration method and does not authorize tuning penalty 16 on these
inspected rows.

Manifest, lock and scorecard agree on four fits, no retry, historical
opened-Train only, Dev/Final closed, zero network/provider/cost, no promotion
and no incumbent mutation. This review changed no artifact, scheduler,
incumbent, research-credit journal, budget or Git state.
