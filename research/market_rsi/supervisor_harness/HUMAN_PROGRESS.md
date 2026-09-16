# Market RSI — human progress

This is an append-only plain-language summary, separate from engineering logs.
No entry may turn a diagnostic, infrastructure repair or spent budget into a
claim of prediction improvement. Link detailed evidence rather than pasting it.

Quick terms: **HGB** means histogram-based gradient boosting, a series of
decision trees that correct earlier errors. **Ridge** is a regularized linear
regression. **MSE** is mean squared error; lower is better on the *same* rows.
"Opened Train" means the data was already available for development, not an
untouched test.

## 2026-09-16, work block: stop the iCloud loop

- **Current goal:** Get back to a trustworthy NFL prediction experiment.
- **What I did:** Moved active execution to a non-iCloud local copy; kept the
  original as an archive; made the original budget unable to accept writes;
  restored the scheduled work with local-only instructions.
- **Why:** The previous paid controller stopped when iCloud evicted its source
  during execution. Another identical run would waste money without testing
  the prediction question.
- **What we learned:** The local execution path is usable. We learned nothing
  new about forecast accuracy from this repair.
- **Result:** No meaningful prediction result yet.
- **Evidence:** The original 21-turn controller had no valid decision or model
  fit and cost $1.213125012 incrementally. The local canary passed with zero
  Tinker calls. The migrated $200 ledger reports $89.903153492 effective cost,
  $2.30 still reserved and $107.796846508 globally available; it is not a new
  budget. See `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
- **Time/effort:** Multiple work blocks across the day; no precise wall-time
  ledger was kept, so a finer claim would be invented.
- **Current blocker:** A frozen, useful target and strong same-row benchmark
  are still missing.
- **Next action:** On opened Train, test target variation and a zero-change
  comparator for the candidate horizons; lock the label rule before matched
  strong baselines.
- **Confidence:** Moderate that this is the right next test; low that the
  current evidence says self-iteration has improved forecasting.

## 2026-09-16, work block: trajectory review

- **Current goal:** Stop measuring activity as if it were research progress.
- **What I did:** Compared the actual run history against the central question,
  recorded a compact decision state, and set review triggers for future work.
- **Why:** The user correctly observed that infrastructure work had displaced
  the next predictive experiment.
- **What we learned:** The best quantitative comparison is still an opened-
  Train HGB/Ridge result; full-season 2024 work measured label availability,
  not a new model's accuracy. There is no active paid run at this review.
- **Result:** Replanned; no new prediction result.
- **Evidence:** HGB 0.0013540355 vs Ridge 0.0016700963 MSE on 2025 opened
  Train; 2024 coverage 67.64% at 60s and 90.87% at 300s over 47,875 timed
  plays. See `RESEARCH_STATE.md` and the daily log.
- **Time/effort:** About one review work block; no paid provider call.
- **Current blocker:** Objective and matched strong baseline not yet frozen.
- **Next action:** Use the already audited coverage counts, then measure target
  variation and a zero-change comparator on opened Train before choosing the
  objective and rerunning all baselines on matching rows.
- **Confidence:** Moderate in the diagnostic priority; unknown that a longer
  horizon will yield better out-of-sample predictability.

## 2026-09-16, work block: make the next test executable

- **Current goal:** Check whether the next target/strong-baseline test can run
  from the repaired local environment.
- **What I did:** Checked the frozen 2024 source commitments and searched the
  local MarketRSI tree for the cohort plan, batch receipts and PBP source.
- **Why:** The next test needs actual opened-Train rows, not just the aggregate
  coverage numbers that were copied for the controller.
- **What we learned:** The local tree has the seven aggregate input receipts but
  not the frozen full-cohort raw source/batches. The audit can be cited, but a
  new target-value or model comparison cannot yet run locally from those files.
- **Result:** Direct blocker identified; no new forecast result.
- **Evidence:** The frozen support lock binds 12 batch manifests and one PBP
  source hash; the local tree contains none of the matching source/batch file
  names. The 284-game audit remains a historical coverage result only.
- **Time/effort:** One bounded file-inventory check; zero paid calls.
- **Current blocker:** Stage only the already-frozen opened-Train source from
  an authorized resident archive with hash checks, without another iCloud
  hydration loop.
- **Next action:** Locate the existing backup of those exact files and verify
  its hashes before copying the minimum needed into the local tree.
- **Confidence:** High that this is a direct prerequisite; it does not yet
  imply the 300-second target is useful or the model improves.

## 2026-09-16, work block: five-year data intervention

- **Current goal:** Make sure the next experiment can test the five-year
  prediction question rather than a convenient single-year pilot.
- **What I did:** Interrupted the planned 2024-only baseline run, reviewed the
  actual data scope, and made five-season acquisition a P0 Harness gate.
- **Why:** A model score on one season cannot establish the multi-year result
  the user asked us to seek.
- **What we learned:** 2024 has one full-season support audit; a limited 2025
  opened-Train baseline exists. We have not verified comparable market trades
  for 2021–2023 or all of 2025. Official Polymarket and Kalshi APIs provide
  historical access routes, but endpoint existence does not prove five-year
  NFL coverage. No vendor quote or data purchase has happened.
- **Result:** Replanned; five-year data problem remains open, no new prediction
  result.
- **Evidence:** The 2024 audit counted 284 games and 407,225 trades; its
  training-admission flag is false. The official source links and per-season
  unknowns are in `P0_FIVE_SEASON_DATA.md`.
- **Time/effort:** One bounded source and trajectory review; zero new data or
  Tinker spend.
- **Current blocker:** Per-year market/price granularity and legitimate access
  costs have not been established.
- **Next action:** Inventory official market metadata for 2021–2025, then seek
  a concrete paid quote only for the gaps.
- **Confidence:** High that P0 data is the correct priority; unknown whether
  any single exchange can supply five comparable seasons.

## 2026-09-16, work block: first five-season metadata probe

- **Current goal:** Find out whether public history can support a five-season
  NFL market inventory before selecting a data vendor.
- **What I did:** Read the official historical API descriptions and queried a
  small public event-metadata page for each candidate season, without keys,
  trades or payment.
- **Why:** We need to distinguish “the endpoint exists” from “the same kind of
  NFL contract and sufficient trades existed every year.”
- **What we learned:** A 2021 NFL-labeled example was a point-spread market,
  not the 2024 moneyline task. The broad text query also returned unrelated
  events, and several first pages had continuation cursors. Its page counts
  cannot establish coverage.
- **Result:** A source-discovery failure mode found; five-year data remains
  unverified. No model experiment or score.
- **Evidence:** Official Gamma keyset API and the bounded public probe are
  described in `P0_FIVE_SEASON_DATA.md`; no complete per-season count exists.
- **Time/effort:** One short public metadata probe; zero vendor/Tinker spend.
- **Current blocker:** Exact contract classification and full cursor inventory
  by season/exchange.
- **Next action:** Build a strict, schedule-matched metadata inventory with
  immutable source receipts, then request a vendor quote only for true gaps.
- **Confidence:** High that this avoids a false five-year claim; still unknown
  how much comparable data exists.

## 2026-09-16, work block: paginated public NFL catalog audit

- **Current goal:** Test whether the free exchange catalogs even contain five
  seasons of the same kind of NFL game market before paying for history.
- **What I did:** Built and tested a receipt-preserving, no-trades inventory;
  paged the public Polymarket `nfl` series for 2021–2024 and its separate
  `nfl-2025` series for 2025. Checked Kalshi's historical-access documentation
  and its dated sports-market launch notice.
- **Why:** The first broad search mixed unrelated events and old formats. A
  zero in the generic 2025 series was misleading until the separate series
  was checked.
- **What we learned:** 2024 has 284 modern typed-moneyline candidates,
  matching the previous support-audit cohort. 2025 has 271 such metadata
  candidates; no trade or schedule support has been checked. The generic
  catalog has 199 legacy 2021 events, 35 legacy/grouped 2022 events and no
  2023 records in the queried window. The old events do not fit the modern
  schema; that is not proof of no historical winner markets. Kalshi publicly
  announced sports markets in January 2025, so its historical API alone is
  not evidence of five seasons of NFL trading.
- **Result:** P0 remains open. This is source coverage evidence, **not** a
  model score or formal data admission.
- **Evidence:** The two local artifact manifests and raw SHA-256 page receipts
  are listed in `P0_FIVE_SEASON_DATA.md`; two no-network tests passed. Public
  Kalshi and Betfair source links are there as well.
- **Time/effort:** One bounded metadata fetch (five seasons, no trades), two
  tests and source review; zero paid data or Tinker spend.
- **Current blocker:** Comparable 2021–2023 game-trading history and 2025
  event-aligned trade coverage are not established. No vendor quote.
- **Next action:** Check other catalog/provider paths and get a concrete
  quote for the missing years/granularity; do not substitute a new exchange
  in the benchmark without an explicit scope decision.
- **Confidence:** High in the queried series counts; low in any conclusion
  about five-year usable trade coverage.
