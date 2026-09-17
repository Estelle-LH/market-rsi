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

### Supervisor 判断：三季先做，五季再加强

- **决定：** 第一版有对照的预测实验，最低要三季已结束、同一种交易机制的数据；五季是更强的主 benchmark 目标。三季实验只能叫“三季实验”，不能宣称五季结论。这个数字是我们根据切分和当前来源状况作的设计判断，不是论文给出的万能门槛。
- **为什么：** 本地 NFL 赛程显示每季约 284–285 场、61–65 个比赛日期、22 个比赛周。三季勉强能按时间留出训练、调试、最终测试各一季；五季能看更多年份变化。但同一场里的很多 play 会相互关联，不能当成几万个独立样本。2021–2022 的早期 AMM 与后来 CLOB 机制不同，不能为了凑五年硬合并；先查近三季是否真正可比更快。
- **开跑条件：** 2023–2025 只是候选，现有材料尚未证明三季成交和预测标签都够用。要逐季按全部赛程报覆盖，核对数据来源和使用权，预先锁目标，证明至少有 20 个真正没看过的最终测试日期，并在只看训练/开发数据时估算配对结果的精度。2025 已看过的例子和汇总必须做泄漏审计；若没有独立测试，不能硬称有最终分数。
- **结果：** 这是实验门槛与搜索方向的改进，不是模型进步；今天没有新的预测成绩、数据采购或 Tinker 费用。下一步优先核查 2023–2025 同机制数据及 2025 测试集是否仍独立，而不是继续漫无目的寻找更早的 AMM 年份。

### 23:56 ET：三季候选还没过关，先纠正测试设计

- **目标与动作：** 按三季候选做一次有边界的检查：把 2023 的比赛目录连到 NFL 赛程；固定抽三场看成交和分钟价格；核对 2025 已有测试分组的日期数。来源、取样和原始数据 hash 详见 `DAILY_LOG_2026-09-16.md` 与 `P0_FIVE_SEASON_DATA.md`。
- **发现：** 2023 目录能对应 237/285 场，但缺 48 场；固定三场开球后的真实成交为 0、6、137 条。分钟价格虽每场约 1,020 个点，实际只变化 41、34、133 次，不能把分钟点当成独立成交。更关键的是现有 2025 封存的 40 场只落在 11 个日期，不够预先要求的 20 个没看过的日期。
- **判断：** 数据量表面增加了，**可比较的训练标签和合格的最终测试仍未证明**。这次是发现设计问题，不是模型进步，也没有开跑。先做不看封存价格/结果的曝光日期清单、厘清价格代表什么；找不到独立测试区间，就不启动付费实验，也不把 11 日期写成正式 benchmark。
- **费用/把握：** 0 新 Tinker、0 采购、0 Dev/Final 开封；八个离线测试通过。对目录连接和三个固定样本的计数把握较高；对全季逐场标签、价格语义、许可和最后能否检出实际提升仍未知。

### 2026-09-17 00:07 ET：supervisor 接管抽样和清洗判断

- **问题：** 不能把“这些数据该怎么抽、怎么清洗”一直交给用户，也不能为了得到好看的训练集，只留成交活跃的比赛。
- **做法：** 我把全部 285 场比赛定为分母；先在四段赛季里各固定抽三场来诊断来源，选法只看赛程 ID，不看价格或赛果。清洗时只隔离可证明错误的记录；缺交易就记缺失，不填成价格没动，真正的零变化不删。规则和停止条件已经进 supervisor 文件与测试。
- **发现：** 2023 第 13–18 周有 92 场，当前档案目录只对应 45 场。缺口明显集中在后半季，不能删掉剩下 47 场假装数据干净。12 场样本只是冻结了选择，还没查成交；不是新模型结果。
- **决定：** 先做 2025 测试日期和曝光的只读核查，以及历史价格含义核对；若没有独立测试时间块，或价格不是所需的成交，supervisor 停在 P0 并自己提出新目标/时间段版本。只有改变研究范围、使用权或花钱时再请用户裁决。0 新付费、0 封存打开。

### 2026-09-17 00:19 ET：按递归规则做完下一项实查

- **这轮做了什么：** 只看赛程日期，核对旧 2025 Train/Dev/Final；然后用早已固定的 12 场 2023 比赛查公开成交数，并对一场整窗零成交的比赛查官方分钟价格。开始时本地缺 Parquet 读取包，第一笔查询前就失败；隔离安装后用新结果目录完成，失败目录没有复用。
- **发现：** 2025 的 195/50/40 场分组覆盖 42/11/11 天，没有日期交叉，但 Final 仍不够 20 天。2023 固定抽到的 9 场常规赛中，5 场开赛后五小时零成交；3 场季后赛有 59–79 笔。那场整窗零成交比赛的官方分钟价格仍有 1,020 个点，但只在赛前变动一次。不能把这些点冒充成交，也不能把无成交比赛删掉。
- **判断与下一步：** P0 仍关闭；这是一条来源/实验设计上的负面发现，不是模型失败或进步。下一轮由 supervisor 查历史访问回执能否证明真正未碰过的测试日期，并制定前瞻封存方案；已有 2023 成交目标暂不烧模型预算。详细哈希、限制和错误见 `DAILY_LOG_2026-09-17.md`。0 新 Tinker、0 采购、0 封存打开。

### 2026-09-17：纠正分工，并验收第一道架构闸门

- **纠正：** 上一条写的“supervisor 自己决定下一轮科学调查”不再是现行分工。那些旧数据审计仍保留为外层诊断；controller 应决定下一步查什么、做什么，supervisor 只看守权限和证据。正在生效的定时任务也已改成这套分工。
- **做了什么：** 写清每轮的事实输入、controller 原始决定、researcher 执行、独立验收和反馈顺序；加了只允许零费用、合成数据的代码闸门。九项拒绝篡改/越界的测试通过，`research-cycle-fixture-20260917-03` 跑完一个真实本地子进程，并留下完整 hash 记录。先前 `-01` 的事实绑定有错，`-02` 缺少交接时重核，都保留而不冒充最终验收。
- **结果与限制：** 这是 provenance/流程检查通过，不是模型自己决定，也不是 E2B/Harbor 隔离，更不是预测成绩。0 Tinker、0 购买、0 Dev/Final 开封。真正的 controller→隔离 researcher→反馈→第二次 controller 选择还没跑通。
- **下一步：** 接真实 controller 决定与回执，再跑零费用隔离 researcher canary；正式评分继续等 P0、预算和未见测试闸门。具体文件及结果见 `CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md` 和当天 log。

### 2026-09-17：把 canary 变成每次运行前的硬门槛

- **原因：** 一次通过不能保证后来换了代码或环境还能安全运行；只把规则写在文档里，下一轮容易忘。
- **改变：** 新的合成 runner 除了显式 bootstrap 外，每轮都必须给出前一个通过的 canary，并在创建新目录前重核完整源码、Python 环境、原始决定、执行和验收记录。真实 controller-led/付费入口仍拒绝使用合成证明；只有未来做完各自的模型和隔离 canary 才能接通。
- **验收：** 13 项 gate 测试通过；`-06` bootstrap 和使用它做准入的 `-07` 都完成。旧 `-05` 在启动前被拒绝，新目录没有创建。0 模型费用、0 封存数据使用；这不是预测分数。
- **下一步：** 保持此规则不退让，接真实 controller 和 E2B/Harbor 的回执；有任一源码/运行环境改动，就换新 ID 重新跑对应 canary。

### 2026-09-17：先定清两层 Harness 和 E2B 隔离

- **分工：** 最外层 GPT-5.6-Sol + Codex 是 supervisor，负责观察、边界、版本和验收；内层 GLM controller 用独立的 Research Harness 决定科学步骤。controller 是否弱还没有证据，不能用数据或执行失败直接下结论。
- **隔离要求：** controller 的工具会话和 researcher 的执行必须使用两个不同 E2B sandbox/microVM；可信 broker 传有 hash 的许可输入输出，独立评分器和保护数据留在外面。现有代码只有本地 GLM 接入与单 sandbox coder probe，尚未达到这个目标。E2B sandbox 隔离不等于已证明不同物理机器。
- **状态：** 架构合同、AGENTS 和生效的定时任务已纠正；未运行双 sandbox canary，未开新模型实验，0 新 Tinker、0 数据购买、0 Dev/Final 开封。下一步先做接口和正/反隔离测试，再判断是否应把 controller 换成 GPT-5.6-Sol。
