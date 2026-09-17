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

## 2026-09-16, work block: alternative historical exchange screen

- **Current goal:** Find a legal five-year source instead of assuming that
  paying a vendor can create older markets that did not exist.
- **What I did:** Checked the exchange's own historical-data catalog,
  granularity tiers, American-Football inclusion, public price guidance and
  access restrictions. No account was opened and nothing was purchased.
- **What we learned:** Betfair advertises archived exchange data back to 2015
  and includes American Football in Other Sports. Its free BASIC tier is
  one-minute last-traded price without volume; paid ADVANCED offers one-second
  prices/volume. Public Other Sports guidance lists £39/month or £399/12
  months for ADVANCED, but NFL game-level coverage and a quote are unverified.
  This would be a *different exchange* and require a distinct benchmark.
- **Result:** A plausible source lead, not P0 admission or approval to spend.
- **Evidence:** Official Betfair links and the scope boundary are recorded in
  `P0_FIVE_SEASON_DATA.md`.
- **Time/effort:** Public documentation review; zero spend.
- **Current blocker:** Exact NFL market coverage, account/jurisdiction access,
  permitted research use and full price are unknown.
- **Next action:** Verify a sample/market count or direct quote before any
  purchase or exchange switch.
- **Confidence:** Medium that Betfair has some usable NFL history; unknown
  whether five full seasons can match the current prediction target.

## 2026-09-16, work block: 2025 directory correction and one trade canary

- **Current goal:** Verify whether 2025's public game catalog and trade stream
  are real enough to count as a possible second season of source data.
- **What I did:** Matched the frozen public 2025 metadata to the nflverse
  schedule using only game identity fields. The first mapping gave 235/285
  because I had not normalized the schedule's `LA` alias. After fixing that
  and retaining the first artifact, it gave 271/285: the missing 14 were all
  Week 1 games. A direct public lookup proved a missing game did exist and
  was closed; the catalog date filter was excluding it. I kept that flawed
  receipt, removed only the misleading filter from the season-specific
  query, reduced page size after a 20 MB safety-limit failure, and reran with
  fresh artifact IDs. The corrected catalog has 285/285 typed moneylines,
  each uniquely mapped to one of the 285 scheduled games. Then a fixed
  earliest-game canary fetched 2,148 public timestamped trades in a 17-hour
  window (733 before game start; 1,415 in the next five hours).
- **Why:** Otherwise we would have falsely reported 14 absent markets and
  designed the benchmark around an incomplete API query.
- **What we learned:** 2025 has a complete *market identity* catalog in this
  series, plus at least one game with a usable public trade stream. Neither
  says that all 285 games have sufficient event-aligned labels or that a model
  improved. The earlier 271 count in this log is explicitly superseded.
- **Result:** P0 still open; no formal data admission, training, Dev/Final
  opening, model score or purchase.
- **Evidence:** Local ignored artifacts `p0-polymarket-2025-series-metadata-20260916-04/`,
  `p0-polymarket-2025-schedule-screen-20260916-03/`, and
  `p0-polymarket-2025-trade-canary-20260916-01/` have source hashes and
  receipts; all six no-network tests passed. Flawed `-01`/`-02`/`-03`
  attempts remain preserved for the record.
- **Time/effort:** One catalog pagination correction, one schedule mapping
  correction and one bounded public-game trade screen; zero provider spend.
- **Current blocker:** No comparable 2021–2023 market/trade history or vendor
  quote; 2025 whole-season trade/PBP coverage remains untested.
- **Next action:** Prioritize old-season source and licensing/cost verification;
  do not spend effort on a full 2025 trade download until the five-year path
  is credible or the user explicitly changes scope.
- **Confidence:** High in the 285 identity matches and one 2,148-row trade
  canary; low in any five-year training-data conclusion.

## 2026-09-16, work block: parallel source and vendor checks

- **Current goal:** Resolve the oldest missing seasons faster without
  launching another model experiment or duplicating paid work.
- **Parallel ownership:** One independent audit checked 2021–2023 official
  Polymarket/Kalshi event evidence; another checked Betfair/other exchange
  coverage, prices, access and rights. The supervisor reviewed code/tests and
  integrated only the supported findings. A separate bounded 2025 trade-
  coverage *code-only* task was assigned; it is not a new data collection.
- **What changed:** Official Polymarket event pages show some older NFL game-
  winner markets. This corrects the tempting but false interpretation that
  zero modern-schema matches meant no older markets. The pages do not prove
  season-wide timestamped trade availability. Betfair has American Football
  in its historical Other Sports package and published package prices, but
  neither five-season NFL coverage nor US delivery/commercial-use rights has
  been confirmed. Matchbook is another inquiry lead, not verified data.
- **Result:** Parallel checks settled the catalog-interpretation error and
  separated advertised package price from data rights. P0 remains open; no
  formal model run, protected-set access, vendor contact or provider spend.
- **Evidence:** `P0_FIVE_SEASON_DATA.md` links the official event/API, Betfair
  and Matchbook pages. Thirteen local no-network inventory/mapping/canary/
  coverage-code tests pass. The 2025 whole-season coverage code has **not**
  been run against the public API; its SHA receipts would not be independently
  recheckable later unless raw pages were separately preserved.
- **Critical-path effect:** The two independent reviews completed during the
  local code/document review, rather than waiting for it serially. They
  narrowed the next question to actual older fills and lawful delivery; they
  did not shorten the five-season admission gate itself.
- **Next action:** Check whether specific older condition IDs return dated
  fills within the documented history window, then obtain a season-by-season
  vendor inventory and itemized quote before any purchase or benchmark claim.
- **Confidence:** High that isolated older winner markets existed; low that
  their full 2021–2023 trade history is obtainable now.

## 2026-09-16, supervisor handoff resumed

- **Current goal:** Put the continuing P0 data-acquisition oversight back on
  the existing scheduled supervisor, not a second paid research process.
- **What changed:** The user explicitly directed the supervisor to take over.
  The existing `market-rsi` task was changed from PAUSED to ACTIVE, retaining
  its two-hour cadence and this same task. Its saved prompt now reflects the
  corrected 2025 count and the older-market counterexamples.
- **Result:** Scheduled supervision resumed. No model run, vendor purchase,
  Dev/Final opening or budget change was authorized by this status change.
- **Next action:** At its next review, continue the exact old-season trade and
  lawful five-season supplier checks; report a concise result or an honest
  no-change status, keeping P0 closed to formal model comparison until proven.

## 2026-09-16, paid-experiment ownership clarified

- **Current goal:** Keep source acquisition and eventual paid experiments under
  one supervisor, without a second process or a new budget.
- **What changed:** The user authorized the resumed supervisor to take on
  qualifying paid work too. The active scheduled task now says it may run an
  in-cap Tinker experiment after P0 data admission and all release, split,
  run-ID, process and ledger checks. Ordinary in-cap execution needs no further
  handoff. The existing $200 cap is unchanged; vendor purchase has a separate
  price/rights decision.
- **Current evidence:** P0 is still not passed: 2024 has one audited season,
  2025 has a full market-identity map but only one trade canary, and 2021–2023
  season-wide timestamped fills are unverified. A process-name check found no
  Market RSI/Tinker runner at this review. That check alone is not a paid-run
  preflight or a fresh budget reconciliation.
- **Result:** Authorization and ownership changed; no paid experiment was
  launched, no cost incurred, and no score claimed.
- **Next action:** Resolve the exact old-season trade availability or lawful
  five-season supplier path before a formal paid model comparison.

## 2026-09-16, evening supervisor review: older public trades

- **Question:** Do the public trade endpoints actually return fills for the
  older NFL winner markets whose event pages we found?
- **What I did:** Read the provider's current history-window documentation,
  then made three fixed, `limit=1` public queries for one 2021-season playoff
  market, one 2022-season Week 5 market, and one October 2023 market. Each
  condition ID came from an exact official event-slug lookup; only row counts
  and the first timestamp were inspected.
- **Result:** The 2021 and 2022 queries returned zero rows; the 2023 query
  returned one timestamped fill. This is consistent with the documented
  roughly three-year floor for market-scoped history. It does **not** mean the
  two older games had no trades, nor does one 2023 row establish season-wide
  training coverage. No model, Dev/Final score or paid provider call changed.
- **Evidence:** Exact event slugs, condition IDs and UTC query windows are in
  `P0_FIVE_SEASON_DATA.md`; the linked Polymarket trade API documentation
  states the market-scoped history limit. These were exploratory response
  summaries, not frozen raw-page artifacts or admissible training data.
- **Effort/cost:** Three one-row public history requests and three exact event
  identity lookups; $0 provider spend.
- **Decision:** Keep P0 closed. The direct free market-scoped API is not a
  demonstrated five-year source; focus next on a lawful archive/provider
  inventory, rights and exact price for 2021–2022 before model spending.
- **Confidence:** High in the three observed API responses; low in any
  claim about all older NFL markets or alternative archive availability.

## 2026-09-16 深夜：找到旧年份的免费成交档案

- **目标：** 看 2021–2022 年的 NFL 交易记录能不能找回来，而不是先花钱买一个范围不明的数据包。
- **做了什么：** 查了 Polymarket 早期市场的合约格式，找到一个公开的链上归档；只下载三个月份的小文件，用七场已知比赛的市场地址逐一核对。文件版本和校验值都记下了。
- **发现：** 2021 年两场常规赛分别有 251、406 条记录；同一赛季四场季后赛分别有 556、332、661、870 条；2022 年一场比赛有 420 条。此前普通交易接口返回 0，不代表当年的交易不存在。免费区块链节点也读不到那段旧历史。
- **结果：** 旧数据有了一条可验证的免费来源，这是数据收集进展；**还不是五年数据齐备，也不是预测分数提高**。这些只是选定七场的原始记录，部分时间在赛后，不能直接拿来训练或打分。
- **证据与费用：** 来源固定在一个公开版本；三份原始小文件和校验值存于 `artifacts/p0-polymarket-amm-archive-canary-20260917-01/`，详细边界见 `P0_FIVE_SEASON_DATA.md`。这一步没有购买数据、没有 Tinker 调用，也没有打开 Dev/Final。
- **接下来：** 先清点 2021–2023 每一场 NFL 比赛在归档里是否有足够的赛中交易，并核对早期交易机制与后期订单簿能否使用同一种预测目标；只有确实缺的部分再询价。
- **把握：** 对这七个市场确有归档记录把握高；对整季覆盖和可比性仍未知。

### 同晚追加：这七场的数据够密吗？

- 把七场比赛的开球时间与旧交易时间对上后，每场在开球前一小时到后五小时有 231–856 条交易。说明记录不只是赛后残留。
- 但每场都有几分钟到一百多分钟的空档，不能据此说每个比赛事件都有可用的 60 秒或 300 秒预测标签。下一步仍是逐场、逐事件检查；这一步没有模型结果或费用。

### 同晚追加：停止无边界找数据，但不降低数据标准

- **用户要求：** 不能无限找，也不能拿不够的数据硬做五年实验。现在把“找来源有截止点”和“五季数据要验收”分开执行。
- **这次做的定点检查：** 只读取公开链上档案的两个小型目录文件，以及一个较大目录的远程列数据。文件版本和校验值已核对。按严格的 `nfl-` 名称筛选，三个旧赛季的窗口分别得到 0、32、237 个尚未匹配赛程的候选市场。这不是逐季比赛数；早年样本确有成交，目录却查不到，因此不能用这个目录的零来判定无数据。
- **真正学到的：** 免费档案可能保留旧成交，但目前没有可直接用于五年实验的完整旧市场目录。继续随机搜索不会自动补齐它；接下来只做一次聚焦的旧比赛映射与密度核查，做不通就列缺口和针对性报价。
- **边界：** 五个赛季、逐季赛程/市场/成交/标签覆盖、可核验的来源和使用权、至少 20 个未看过的测试日期仍是准入条件。没有新模型分数、没有购买数据、没有 Tinker 消费，也没有打开 Dev/Final。
