# Market RSI — human progress

This is an append-only plain-language summary, separate from engineering logs.
No entry may turn a diagnostic, infrastructure repair or spent budget into a
claim of prediction improvement. Link detailed evidence rather than pasting it.

Quick terms: **HGB** means histogram-based gradient boosting, a series of
decision trees that correct earlier errors. **Ridge** is a regularized linear
regression. **MSE** is mean squared error; lower is better on the *same* rows.
"Opened Train" means the data was already available for development, not an
untouched test.

## 2026-09-17：双 E2B 沙箱实测发现出网闸门未生效

- **目标：** 让 controller 的工具和 researcher 分住两个 E2B 沙箱，并在正式使用前检查隔离。
- **做了什么：** 固定一个小额、只用合成字符串的检查程序；先查活跃沙箱和预算，再用全新 ID 逐次测试。修正了 macOS 虚拟环境识别、E2B 不接受的网络参数，以及失败检查项没有保存的问题。两个沙箱确实拿到了不同 ID；退出后逐一关闭，账户现在是 0 个活跃沙箱。
- **学到什么：** 实测中，沙箱没有拿到密钥或另一只沙箱的测试文件，但向公网 IPv4 地址的 TCP 建连成功。我们还没做 TLS/HTTP 往返，所以不能断言应用数据真的出网；同样也不能凭 E2B 回报“禁止互联网”就认定隔离通过。原因尚未查明；这是安全闸门的失败，不是模型或预测能力的结果。
- **决定：** 已让 live 双沙箱入口在读密钥和记预算前直接拒绝。不会重复同一种配置来赌一次通过；先找到不同的、创建时就起效的隔离方法并另作验证。正式 GLM/researcher 轮次和封存评分仍不启动，安全的公开资料/Train-only 工作继续。
- **费用与证据：** 四个已派发失败 ID 合计按 **$0.80 最大可能额** 记账，实际 E2B 发票未知；最初的预检查失败 ID 没有派发。Tinker metered 数字未变。详见 `DAILY_LOG_2026-09-17.md` 和 ignored `artifacts/dual-e2b-role-canary-20260917-02/` 至 `-05/`；最终 13 项离线测试通过。这一步没有新预测分数。

### 同日调整：让 controller 自己搜、自己读

- **为什么改：** 用户指出全面禁网不是目的；controller 必须能自主查文献。真正要阻止的是绕过 broker 的私下传递，不是有记录的公开研究。
- **核对到的现有能力：** 旧 Harness 已经有实时 Crossref 搜索、公开网页/文本阅读、原文哈希和实际阅读引用检查；22 项离线测试通过。新 E2B controller 尚未接入这条链，不能说它现在已经能自主搜索。
- **下一步：** 复用这些可信 broker 工具，把 GLM 的检索词、选文、已读范围、失败和后续决定串进同一轮记录，再验证两个沙箱的边界。没有新模型分数或新付费调用。

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

### 2026-09-17：全局状态硬闸门与文献工具连接（仍是离线验收）

- **问题：** 规则让 supervisor 读写全局状态，但实际合成 runner 没检查，下一轮可能拿旧决定开跑，或与另一轮同时占用同一状态。
- **做了什么：** 加入 supervisor 独占的追加式全局状态日志；每轮先核对当前 `RESEARCH_STATE.md`、最新日志 head、未占用状态、新 ID、源码和 canary，完成后写通过或失败。变更状态文档必须在空闲时明确登记理由。旧付费入口没有接入，所以仍关闭。另将 controller 文献调用按 host 观察到的沙箱身份限权，复用现有搜索、公开网页阅读和研究记录 broker。
- **验证：** 36 项相关单测通过；真实旧 broker 的假网络数据链走通“搜索元数据→阅读正文范围→引用实际阅读”。本地全局日志记录了 `-08/-09` 和源码修订后的 `-10/-11` 两对零费用合成运行；`-09` 在代码变更后被拒绝作为新 canary，拒绝时 `-10` 目录尚未创建。日志目前无活跃轮。`-10/-11` 均是脚本决定加本地子进程，非 GLM、自进化或市场预测结果。
- **下一步：** 把这套状态闸门与文献适配器接到真实 GLM/E2B 控制通路，再验收受控 A→B 交接、文献访问、禁止未授权直连和两边清理。先修旧 E2B 费用回执写早了的问题；在有效隔离 canary 前不重启付费路径。P0 数据和最终测试仍未通过。

### 2026-09-17：修正 E2B 费用回执的先后顺序（没有重跑付费 canary）

- **问题：** 旧双沙箱脚本在自己还没退出时就写了“进程已退出”，金额虽按上限保守计算，但这条证据在写入当时不准确。
- **改动：** 子进程只做沙箱工作和清理，保持预算预留；外层监督进程等它真实退出，再核对 A/B 各自的沙箱 ID、清理确认与账户活跃列表。证据齐全才按未知实际用量的上限结算；缺证据就保留未结预留，不能假装成功或重用 ID。旧账本不修改。
- **实测与边界：** 用独立本地 E2B 2.38.0 环境通过依赖核对；19 项 E2B 离线测试通过，其中一项真的启动并等待了本地子进程，但没有创建 E2B 沙箱。旧网络隔离问题仍在，live 入口继续拦截。0 新 Tinker/E2B 调用、0 预测结果。
- **下一步：** 给 controller/researcher 设计按角色准许的网络和 broker 交接正反测试；以新版本、新 ID 验证后，才能考虑接真实 GLM。当前优先不是再重复原来的“完全禁网” canary。

### 2026-09-17：把文献工具接到受控消息口（离线）

- **目标和动作：** 补上 controller 沙箱到可信 broker 的逐次消息连接。每次只能从已登记的 A 沙箱读取一条编号请求，先核对 supervisor 的当前轮次和输入 hash，再调用旧的查文献工具；回答只送回 A，不送给 B。失败、重复编号或状态被改都要停。
- **为什么：** 之前只是代码能直接调用 broker，真实 controller 的工具会话还没有可审计的入口。这里先把边界和失败记录做成可测试的接口，不把假对象说成真沙箱。
- **验证与学到的：** 假 A/B + 真 broker/假公共网页的数据链跑通“自己选搜索词→读一页→引用阅读记录”，B 没收到内容；状态文档偷改、重复调用和坏地址都被拒。30 项连接/状态测试和另外 19 项 E2B 账务测试通过。结果是连接能力前进一步，不是预测提升。
- **下一步与限制：** 真正的 GLM/E2B 工具会话和 A→B 交接尚未接入；先做可验证的应用层网络/直接互访隔离，再用新版本 canary。当前 live 入口仍关闭。0 新付费，0 封存集使用；对离线行为把握高，对真实 E2B 网络隔离尚无结论。

### 2026-09-17：把坏工具请求也留下证据

- **问题：** 上版连接在收到缺失或超大的请求时会停止，但只在内存里记住失败，重启后不够好追查。
- **改动和验证：** 现在每次先写尝试记录，再读请求；成功和失败分别留不可覆盖的证据。缺请求、超大请求、重复调用、状态变化都测试了，31 项相关离线测试通过。旧文献工具仍负责自己的访问额度和阅读记录。
- **判断：** 这是可靠性补丁，不是新研究结果。我们核对了 E2B 官方 SDK 的网络字段，但它只说明配置意图，不能解释之前“禁止外网却连上 TCP”的真实现象。下一步仍是应用层和 A/B 互访的正反 canary；没有新付费或封存集使用，live 入口保持关闭。

### 2026-09-17：把 A→B→A 的交接线接通到离线测试

- **目标和动作：** 让 controller 的第一份决定只能经可信本机传到另一个 researcher 沙箱，再把独立核对过的结果返回 controller。先限制为公开合成文字的哈希任务；真实科学任务尚未获准。
- **实际验证：** 两个不同的假沙箱对象完成 A 查文献→A 决定→B 收到原样任务→B 回答→本机核对→A 收到反馈，再关闭同一个全局状态轮次。改动中间任务、伪造结果、篡改原始决定或回执、打开封存数据、重复第一次决定都会被拒。新模块十项加一项整体联调，相关连接/状态共 42 项通过。
- **学到和边界：** 这证明消息顺序与证据记录在离线代码里可行，不证明 GLM 自己决定，也不证明真实 E2B 网络隔离或预测变好。下一步是实际 GLM/E2B 接线和应用层正反隔离测试；付费入口继续关闭。0 新费用、0 封存集使用。

### 2026-09-17：B 真的执行了合成任务，但还只在本地

- **目标和动作：** 上一版测试直接把正确答案写进假的 B 沙箱，没有证明 B 会执行。现在让一个真实本地子进程读取 broker 给 B 的合成任务，计算哈希并写一次结果；本机再独立核对，把反馈只送回 A。
- **验证：** 28 项相关离线测试通过，包括越界任务和覆盖旧结果的拒绝。全局状态日志已记录这次决策文档修订，目前没有活跃轮次。改动在本地提交 `09619a2`，未推送。
- **学到和边界：** 这解决了“测试直接伪造 B 的结果”这一个漏洞，不等于 GLM 选题、E2B 隔离或预测能力提升。没有新付费调用，也没有打开 Dev/Final。下一步先做真正双沙箱的应用层网络和互访正反 canary，再接模型原始响应；在验收前 live 入口继续关闭。

### 2026-09-17：准备应用层网络检查，仍未重开双沙箱

- **目标和动作：** 旧检查只测 TCP 建连，无法判断实际 HTTP 内容能否出网。新探针会对预先指定的公开 HTTPS 地址和另一沙箱服务地址各试两种连接方式，并把 HTTP 403 也算作“收到应用层回应”。还需要本机 broker 能读同一公开来源的正面检查和双向 peer marker 检查，不能仅凭几个访问失败就宣称隔离。
- **验证：** 复查 E2B 官方网络选项及本机固定 SDK；新探针的 6 项离线测试通过，连同相关交接测试共 29 项通过。未调用 E2B/Tinker，未打开行情或封存集。旧 live 入口仍会在读取凭证前拒绝。
- **判断与下一步：** 这是缩小故障含义的诊断准备，不是已解决网络隔离；对真实 E2B 仍无新观测。下一步把探针和双向 peer 服务、broker 正面控制、清理及预算回执接成一个新版本 canary，再决定是否可以连接 GLM；正式评分的 P0 闸门不变。

### 2026-09-17：给双向互访检查加了真正的正面控制

- **问题：** 如果 A 连不到 B，可能只是 B 根本没启动服务，不能据此说沙箱隔离有效。
- **动作和验证：** 加了只返回随机合成标记的服务；先在服务所在环境自己读取并核对标记，再让另一边尝试访问。两项测试通过，其中一项真的在本地启动和停止了服务进程。没有创建 E2B 沙箱或花钱。
- **边界与下一步：** 这只证明正面控制的代码能在本地工作。仍需把它接到真实 A/B 沙箱、双向网络探针和父进程清理/预算链；旧 live 入口保持关闭。

### 2026-09-17：把双向检查接成一个可调用组件（离线）

- **目标和动作：** 给已经创建的 A/B 沙箱对象规定同一条检查顺序：B 先证明自己的标记服务在运行，A 再试公开 HTTPS 和 B 的服务地址；然后反过来检查。每一步保存原始报告、来源和清理请求。若公开网页真回了 HTTP，或 A/B 拿到了对方的标记，就判失败。
- **验证与边界：** 5 项假沙箱对象测试通过，其中双向检查和失败后停止服务都有覆盖；没有实际创建 E2B 沙箱。组件一直明确写“没有证明隔离”，不能用它单独解锁付费实验。
- **下一步：** 让一个受预算和已发布源码约束的父进程实际创建并核对两个 E2B 沙箱，跑这个检查和 broker 正面控制，再等所有子进程退出、核实账户无残留后记账。真实 GLM 原始响应还未接入。

### 2026-09-17：把 B 的任务执行接到宿主机交接线（仍是离线）

- **目标和动作：** 上一版只有测试代码能启动 B 的本地 worker。现在交接线能把冻结任务和执行代码交给指定的 B 对象，核对写入内容，按 controller 预先给出的时间上限执行一次；宿主机验证结果后，才把反馈送给 A。命令失败或任务被改就记录失败，不能用同一个交接再试。
- **验证：** 33 项相关测试通过，其中 B 确实在本地子进程里算了结果；错沙箱对象、改过的任务和命令失败都被拒绝。对“本地连接正确”的把握较高；对真实沙箱隔离还没有新证据。
- **边界和下一步：** 这不是 GLM 决策或真实 E2B 执行，更没有预测分数。没有新付费、没有打开封存集。下一步要由已发布源码、全局状态和预算约束的父进程创建真实 A/B，做双向隔离与 broker 正面检查，并核对清理；旧入口继续关闭。

### 2026-09-17：先把“代码版本已发布”变成硬检查

- **目标和动作：** 真实双沙箱检查不能只凭本地提交或版本号启动。新增只读验收：本机执行源码必须和 Git 提交一致；用户自己的远端必须有指向同一提交的正式版本标签。沿用现有 Harness 的源码清单，把新连接件一并纳入；检查本身不会推送或启动沙箱。
- **结果与边界：** 36 项相关离线测试通过。当前代码尚未发布，新闸门在接触远端或付费服务前就正确拒绝了它。没有新模型结果、E2B 调用或费用；这一步解决的是版本纪律，不是网络隔离。
- **下一步：** 完成唯一的父级双沙箱入口及清理/记账，再一次性核对要发布的代码；真实 canary 仍需新 ID 和独立验收，不能借旧失败回执开跑。

### 2026-09-17：把版本、全局状态和预算接到同一个入口

- **目标和动作：** 新的双沙箱检查要先通过已发布源码、旧合成检查、全局状态空闲且未用过 ID、setup 额度足够这几道门，才能占用一个轮次和预算。新增入口把这些检查接在一起；它只预留，不会启动 E2B 或模型。
- **验证：** 40 项相关离线测试通过。未发布代码、旧状态、预算不足都会在占用前被挡住；预留失败时只关闭对应的失败轮次。同一个 ID 不能再用。结果是执行纪律更明确，不是隔离或预测结果。
- **下一步：** 仍要补真正的 A/B 子进程与父进程清理/结算。没有新的付费或封存数据操作，也没有实际运行完整控制循环。

### 2026-09-17：补上双沙箱的父子执行链，暂未启动真实沙箱

- **目标：** 解决“各项检查都有，但没有一个安全入口把它们完整跑完”的断点。
- **做了什么：** 父程序先核对已发布源码、唯一轮次和 $0.20 上限，再启动一次子程序；子程序计划检查两个不同沙箱、宿主机可读取公开来源、双向直接访问和密钥隔离。父程序必须等子程序退出，核对每个已创建沙箱的清理及账户列表，才按费用上限记账。失败或证据缺失不能假装通过。
- **实际结果：** 相关 48 项离线测试通过，包括第二个沙箱创建失败、清理未确认、回执被改、无密钥、宿主机公开来源不可读、账户仍有沙箱及本机临时互访服务。公开来源先在付费调用前检查，失败就不启动沙箱；账户未清空时也不能把预留款当作零费用取消。没有调用真实 E2B/GLM，也没有新的预测分数或费用。源码还未发布，真实安全性仍未知。
- **判断与下一步：** 这是连接能力的进展，不是研究结果。下一步先完成代码审计和本地版本固定；在用户授权的准确发布范围内发布后，才用新 ID 跑一次真实双沙箱检查。旧失败 ID 不重试。

### 2026-09-17：发布后首次真实检查，停在第一个沙箱的配置回显

- **做了什么：** 按明确授权把 20 个提交和版本标签推到用户自己的 fork。第一条新命令在占用预算前发现缺 `python-dotenv`；补齐并固定版本、重做零费用前置检查后，用另一个全新 ID 启动真实检查。
- **结果：** 第一个 E2B 沙箱创建成功，但其网络配置回显没有通过严格核对；第二个没创建，双向通信检查没开始。父程序已确认第一个沙箱清理且账户无残留。本次账本按未知用量上限计 $0.20，不是实际发票；没有 GLM 或预测结果。
- **学到的：** v0.1.0 只记了失败阶段，没记清哪个配置字段不同；沙箱杀掉后服务端查询返回 404，所以现在不能猜测是 E2B 策略失效还是回显格式不合。已在下一版候选代码里补安全的字段记录，继续严格拒绝不匹配。
- **判断与下一步：** 不重试旧 ID。setup 额度只剩 $0.049486662，低于下一次 $0.20 上限；先查真实费用证据或取得明确的账本额度调整，再发布新源码做新检查。正式研究循环仍未启动。

### 2026-09-17：核对费用证据，未解锁下一次检查

- **目标与动作：** 把记录回显差异的改动连同失败说明本地提交为 `bdbd40d`；50 项离线测试通过。只读核对权威账本和已安装的 E2B SDK，并尝试查看 E2B 账户账单页面。
- **结果：** 总账有效占额 $90.903153492，仍在原 $200 上限内；setup 类别可用 $0.049486662，另有 22 个较早已发出的 setup 请求共 $2.20 尚未结算。它们不是可以直接取消的未发出预留。账户网页停在登录页，没有取得本次沙箱的账单或具体网络回显。官方按秒计价说明也不是这次的实际费用证据。
- **判断与下一步：** 没有新的预测或隔离证明；不能将 $0.20 保守占额改写成推算费用，也不能从其他类别静默挪额度。v0.1.1 诊断版目前仅本地提交。需要可核实的供应商费用记录，或对原 $200 内的明确类别调整决定，随后发布新源码、用新 ID 做一次严格检查。

### 2026-09-17：把“配置不匹配”拆开查清

- **问题：** 11:45 的真实检查只记录 `policy_controller/ValueError`，没有记录哪个字段不同，所以第二个沙箱和真正的网络测试都没有开始。
- **修复：** 检查固定 SDK 的创建请求和可选返回字段后，本地代码把“明确相反的配置”与“回显字段缺失”分开。前者立即停；后者只做无敏感数据的双沙箱诊断，最后仍记失败，不得称隔离通过。51 项相关离线测试通过；没有新的 E2B 调用。
- **可读记录：** `LIVE_PROTOCOL_DEBUG_LOG_2026-09-17.md` 按秒列出请求、失败、清理、费用，明确哪些只是推测。下一次真实测试仍需新的已发布版本和足额的 setup 占额。

### 2026-09-17：一次新编号真实连接检查仍未通，但定位前进了

- **目标和动作：** 按用户逐项批准，在 $200 总上限不变的前提下把 $0.20 从 repair 调给 setup，发布新版本到用户 fork，跑一条全新 ID 的 E2B 合成检查。运行前确认无匹配进程、无活跃 Market RSI 沙箱，并通过同版本零费用前置检查。
- **看到的结果：** 两个不同沙箱创建成功。旧版卡住的配置回显问题已定位为两边都省略了可选的 `allow_out` 字段；其他已返回字段没有相反值。两个沙箱的基础边界检查以及 B 的本地标记服务通过。A→B 的完整网络探针碰到 25 秒 SDK 连接超时，没得到 HTTP/TLS 结论；B→A 没开始。两个沙箱和本地子进程已清理，账户显示零残留。
- **费用和判断：** 新测试按未知用量上限占 $0.20，不是发票；总有效占额 $91.103153492/$200。没有预测分数或 GLM 决策，网络隔离仍未证明。检查官方 E2B 命令超时说明后，本地把整组探针的连接上限改为 60 秒并通过 23 项相关离线测试，但这还没有发布或实测。一次授权已用完，不启动第二次；下一步等明确的新版本和额度决定。

### 2026-09-17：并行拆开三段故障，并把各自日志接到本机页面

- **做了什么：** 三个 subagent 分别检查配置回显、SDK 命令超时和 A↔B 逐请求探针。每个都有单独、带时间的工作记录；本机 dashboard 现在直接显示任务、状态、下一步和完整记录入口。新增 agent 要先登记日志，这条规则写进了项目 Harness。
- **验证和边界：** 合并后的 45 项相关离线测试在固定 E2B Python 环境通过。代码能保留分段进度，缺失 `allow_out` 回显仍不能算隔离通过；超时或只有部分回执仍是未确定。没有启动 E2B、GLM 或付费实验，没有新的预测结果。项目里的 dashboard 源码已保存，Chrome 的本机页面核对过三份日志；Codex 内置浏览器当前显示连接错误。
- **下一步：** 总体验收本地差异、版本和预算闸门；要判断 E2B 真正的 A→B/B→A 行为，仍需全新 ID、发布源码及单独授权的真实检查。旧回执不改、不重试。
