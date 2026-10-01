# First real Train result — independent review (2026-09-29)

## Verdict

**PASS.** The completed artifact is internally bound, reproducible from
`predictions.csv`, and correctly resolves to **REVERT**. This is opened-Train
diagnostic evidence only. It is not independent OOS evidence and does not
authorize promotion, publication, deployment, external fetching, paid-provider
use, or access to Route-Dev/Final.

Reviewed artifact:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-nfl-settlement-20260929-02`

Review completed at `2026-09-29T16:56:42Z`. No retraining or source/code change
was performed.

## Source and artifact integrity

- Exact artifact file set: `exclusions.json`, `input_receipts.json`,
  `manifest.json`, `pre_score_lock.json`, `predictions.csv`, and
  `scorecard.json`; no extra file was present.
- Independently recomputed SHA-256 values:
  - `exclusions.json`: `cf61302708a6535b892232d3cf499575e3a8909a4aad1e8de1a0b7959a0164bd`
  - `input_receipts.json`: `427c0a93b0a972200d25493bed2dc11f5a43aed9514f769f57d5a5c6e46b8ace`
  - `manifest.json`: `a36bce7debb71333caa7b35afebeaf9e7adcdd0e07c1679fbf70369dffa6bcb4`
  - `pre_score_lock.json`: `1f54eb27bc22a728c67d161a512ccab0a5fa38f20c28aa6ee11f5b57f7489019`
  - `predictions.csv`: `f91647a2a5b84836bd717ce2d0c6fd404bc1f4a759342a8b8d40fc6e576f37c1`
  - `scorecard.json`: `98f78e0bc68f7743881d285560b5fbc1a9a6b74b5178601ff6fc4201128fb710`
- Every manifest-to-artifact hash binding matched. The pre-score lock's
  bindings to `input_receipts.json` and `exclusions.json` also matched.
- Frozen source bindings matched:
  - source manifest: `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`
  - cohort: `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`
  - runner source: `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b`
- Recomputed all four recorded source-file hashes for every one of the 195
  cohort events: **780/780 matched**. Independently decompressed and verified
  all **195/195** raw-catalog stored/raw hash pairs and every trade manifest's
  binding to its trade CSV.
- The 194 materialized-event receipts exactly matched the source population
  after exclusion. Their catalog meta, stored raw, decompressed raw, trade
  manifest, trade window, and condition bindings matched.
- Current reviewed source hashes:
  - runner: `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b`
  - tests: `6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927`
  - proper scorer: `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b`
  - probability contract: `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74`

## Denominator, chronology, masks, and execution boundaries

- Frozen denominator: **195 events on 42 schedule dates**.
- Materialized: **194/195** (`99.4871794872%`). The sole exclusion is
  `2025_04_GB_DAL`, whose source resolution is exactly `[0.5, 0.5]`; the
  ledger correctly records `unresolved_outcome`. No other attrition occurred.
- Four chronological folds use 22/27/32/37 earlier schedule dates for fit and
  four disjoint five-schedule-date checks. Their OOF event counts are
  **26, 16, 28, 17**, totaling **87 events on 20 schedule check dates**.
- Independently reconstructed every label-availability clock from the selected
  market and event records. Each fold has **zero** fit labels unavailable at
  the first check cutoff.
- The 87 `(event_id, market_id, cutoff_ms)` keys are unique. Market, ordinary,
  and candidate probabilities are present and valid on every row. The
  independently recomputed common-mask hash is
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`,
  matching all three scorecard mask commitments.
- The reviewed runner has four folds and exactly two `.fit(...)` calls inside
  each fold (ordinary and candidate), consistent with the manifest's **8 model
  fits** and the four-fold prediction population.
- Boundary fields are consistently fail-closed: Route-Dev false, sealed Final
  false, external fetch false, paid provider false, provider cost `$0`, and
  promotion authorization false. Static import review found no network/provider
  client. The test suite also blocks sockets in its deterministic end-to-end
  case.

## Independently reproduced metrics

All values below were recomputed directly from the 87 CSV rows, without using
the scorecard's aggregates.

| Forecast | Brier | Log loss | Calibration slope | Calibration intercept |
|---|---:|---:|---:|---:|
| Market | 0.20553336372767944 | 0.5984509292283796 | 1.0155134726661597 | -0.029218480860792484 |
| Ordinary logistic | 0.23560472453952527 | 0.6759482937171853 | 0.6366611551135252 | 0.17273454690115536 |
| Candidate HGB | 0.2697684947156754 | 0.7792234633163909 | 0.35149469337539296 | 0.3355118664178188 |

Candidate minus ordinary (negative loss would be better):

- aggregate Brier: **+0.03416377017615010**
- aggregate log loss: **+0.10327516959920557**
- fold Brier deltas: **+0.05100193432942027, -0.06187770320397515,
  +0.03630495125072125, +0.09527660758844345**
- fold log-loss deltas: **+0.13795855388894473, -0.13563620607343374,
  +0.10078355794352889, +0.27919158992790916**
- candidate Brier fold wins: **[false, true, false, false]** (1/4)

The event-level paired records, UTC-date paired records, means, medians,
better/tied fractions, and seeded interval conventions all recomputed exactly.
Key interval checks:

- event Brier delta 95% bootstrap interval:
  `[-0.005865225194311411, 0.07664298926260418]`
- event log-loss delta 95% bootstrap interval:
  `[-0.0022825365085908885, 0.20822355045750207]`
- UTC-date Brier delta 95% one-day circular-block interval:
  `[-0.06485175548222519, 0.0931477186318942]`
- UTC-date log-loss delta 95% one-day circular-block interval:
  `[-0.12382655586319573, 0.2524705474453966]`

The fixed KEEP rule requires lower aggregate Brier, lower aggregate log loss,
and at least three of four Brier fold wins. All three conditions fail, so the
only valid result is **REVERT**.

## 20 schedule check dates versus 26 UTC cutoff dates

Classification: **acceptable, explicitly labeled secondary evidence; not a P1
repair requirement**.

The chronological split is correctly keyed to the frozen NFL schedule
`game_date`: 20 disjoint check dates, with whole schedule dates kept together.
The existing proper scorer independently groups its secondary paired interval
by `cutoff_ms` UTC calendar date, and its records explicitly use the field
`utc_date`. Late games cause one schedule date to span two UTC dates, producing
26 UTC cutoff-date units. This does not alter the equal-event primary metrics,
the four schedule-date folds, or the KEEP/REVERT decision, none of which uses
that interval. The pre-score lock also expressly distinguishes schedule-date
folding from cutoff UTC date. The 26-unit interval is therefore valid secondary
UTC-date evidence, not a claim that the experiment had 26 schedule sessions.

## Failed `-01` attempt and tests

- `first-real-train-diagnostic-nfl-settlement-20260929-01` contains exactly one
  file: `failure.json`.
- It contains no prediction, fit, scorecard, receipt, or completed-manifest
  artifact. Its failure is the pre-fit 42-date fold-shape check, and all boundary
  flags remain safe with `$0` provider cost.
- Canonical project runtime command:
  `LOKY_MAX_CPU_COUNT=1 PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B -m unittest research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic`
  passed **9/9** tests in 0.213 seconds.
- The system Python lacks `pytest`; that unavailable test frontend did not
  affect the successful canonical `unittest` run.

## Independent conclusion

The artifact and source receipts pass integrity and arithmetic review. The
first real Train diagnostic completed, and its scientific result is negative:
the nonlinear candidate is worse than the ordinary logistic model and the
decision-time market on aggregate proper scores. Preserve this as a diagnostic
**REVERT** result and do not promote it.
