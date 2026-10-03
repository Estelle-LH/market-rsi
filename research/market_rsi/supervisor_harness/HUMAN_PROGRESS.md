# Market RSI — human progress

This is an append-only plain-language summary, separate from engineering logs.

- 2026-09-29 — 今晚要求的真实自主预测迭代已在约 46 分钟内完成，不是新一轮框架建设。Controller 首代并行提出两个候选：120 秒 momentum offset 在拟合前发现 3 个必需 fit game 的 reference age 超出冻结的 300 秒上限，因此 0 fit fail-closed；identity-anchored market calibration 完成 4 fits/87 predictions，但 Brier/log loss `0.143650/0.433565` 均差于 raw market，0/4 raw-Brier fold wins，REVERT。两项经核验的反馈随后实际改变了第二代选择：Controller 不再延续失效路线，改用全 193 场有覆盖的 prior-play success × market-uncertainty offset。该候选也完成 4 fits/87 predictions，Brier `0.1419536874` 只比 raw market 差 `0.0000011584`，log loss 好 `0.0000377670`，但 raw-Brier 仅赢 1/4 folds，日期与周区间均跨零，所以按预先冻结规则 REFUTED/REVERT。独立复核重算了 87 行、四折与区间；raw market incumbent 不变。总计 3 attempts、2 个真实 scored candidates、8 fits、174 candidate prediction rows、零网络/付费/Dev/Final。闭环证明了“已有证据→Controller 选修改→实际训练预测→独立评分→反馈改变后续选择”能跑通；它没有证明历史 Train 上的预测改善，也没有同预算固定流程对照，因此不能声称 self-iteration 优于固定研究流程或系统自我进化。

- 2026-09-29 — 第一批连续自主 Discovery 已经实际跑完 5 个真实 Train 候选，而不是停在计划或审计。Controller 逐轮用上一轮证据改变下一轮：宽 offset 失败后压缩路径；符号不稳后只看最近三周；aggregate 改善但 fold 不稳后加入固定 recency 权重，得到首个 **KEEP** 的 `MarketRecencyWeightedCompositePath-v3`；全历史衰减变差后回到 v3，并只增加正交化 dispersion。当前最佳 v3 的 Brier/log loss 是 `0.203857/0.595837`，相对 market 改善 `-0.001677/-0.002614`，赢 3/4 folds。第五轮 aggregate 更好（`0.202260/0.591819`），也胜 v3 三个 folds，但只胜 market 2/4 folds，因此按事先冻结的规则 **REVERT**，没有用总分覆盖稳定性门槛。5/5 次运行和结果都独立复核；零付费、零网络、未读 Dev/Final，无逐轮人工选题。所有失败分支保留，下一批优先解释 dispersion 的符号/折间不稳定，而不是改评分规则。结果仍是反复查看的 Train Discovery，不支持正式 OOS、promotion、盈利、跨域或 RSI 自迭代结论。

- 2026-09-29 — 按用户要求，offset 完成后由同一 `gpt-6-astra`/high Controller 选择并执行了下一项 `MarketOnlyRidgeCalibration-v1`，结果也通过独立复核（0 P0 / 0 P1）。在完全相同的 87 场/20 个赛程日上，past-only market calibration 的 Brier/log loss 为 `0.205852/0.599385`，比 raw market 差 `+0.000318/+0.000934`，只赢 market 2/4 folds，因此 **REVERT**；它仍明显胜过 ordinary。archived full offset 又比 calibration 差 `+0.003599/+0.008883`，完整赛程日重采样区间为 `[0.000630,0.006695] / [0.001335,0.016623]`，说明在这套相同 penalty/solver recipe 下，额外 16 个 residual 特征带来的是可测损害，而不是市场之外的增量收益；这不等于所有特征都无效。market 继续是当前最佳，calibration/offset/HGB 分支全部保留。Controller 已把经验写入下一轮 `MarketOrthogonalPricePath-v1`：将既有因果价格路径压缩为两个有方向的 feature family，并在每折用过去数据对 market logit 正交化，再做四参数 offset ridge。该第三轮 recipe 已冻结但尚未实现或运行。没有 Dev/Final、网络、付费 provider、发布或 promotion。

- 2026-09-29 — 第二张真实 Train scorecard `MarketOffsetRidgeLogistic-v1` 已完成并通过独立结果复核。第一次 `-01` 在拟合后、评分前因 mask 哈希使用折顺序而非 scorer 规范顺序 fail-closed；它没有 predictions、scorecard 或 KEEP/REVERT。最小修复经独立复核后，fresh `-02` 在相同 195→194 分母和 87 场/20 个赛程日上完成。full offset 的 Brier/log loss 为 `0.209451/0.608268`，优于 ordinary Logistic 的 `0.235605/0.675948`，但差于 raw market 的 `0.205533/0.598451`，且四个 fold 的 Brier 全部输给 market，因此 **REVERT**，当前最佳仍是 market；offset 与 HGB 分支都保留。按完整赛程日重采样并在每次抽样内重算等比赛 delta 后，offset-minus-market 的 Brier/log 95% 描述区间为 `[0.000845,0.007130] / [0.001584,0.018286]`；第 14 周只有 1 场，周结果明确只是含右边界部分周的敏感性分析。Astra/high Controller 已冻结下一项 `MarketOnlyRidgeCalibration-v1`：只用过去 market logit 拟合两参数 ridge calibration，并与 archived full offset 比较，以拆分市场校准和额外特征效果；实现正在进行。没有 Dev/Final、网络、付费 provider、发布或 promotion。

- 2026-09-29 — 主线已切为 `SettlementProbabilityTrainDiagnostic-v0`，旧 60/300 秒价格变化 + MSE 只保留为 legacy。第一张真实本地 Train scorecard 已完成并独立复核：2025 NFL moneyline 完整分母 195 场/42 日，194 场二元可评分，唯一排除是 GB–DAL 40-40 对应的 0.5/0.5；四个 expanding checks 共 87 场/20 个已查看 Train 赛程日。decision-time market 的 Brier/log loss 为 0.205533/0.598451，ordinary LogisticRegression 为 0.235605/0.675948，HGB 为 0.269768/0.779223；HGB 只赢 1/4 folds，结论 REVERT。第一次 `-01` 因把 schedule date 误作 UTC cutoff date 而在 fit 前 fail-closed，只有 failure.json；修复并独立复核后 `-02` 完成 8 次拟合，零 provider、未读 Dev/Final。更强的 `gpt-6-astra`/high Controller 已写出下一轮 memory：只测试 `MarketOffsetRidgeLogistic-v1`，并在下次 lock 加入 inclusive 600 秒 staleness gate。当前结果只支持 Train Discovery 的负结论，不支持 untouched OOS、正式 benchmark、promotion、publication、PnL 或跨域提升。

- 2026-09-29 — 按 synthetic-only 边界完成了本地候选 adapter 的四轮独立复核闭环。最终 exact v4 快照为 0 P0 / 0 P1：85/85 专项与相邻测试、516/516 全仓测试（2 个设计性 skip）通过，11/11 额外 claim/journal/checkpoint/completion/staged-source 篡改攻击均 fail-closed。候选每次只能收到一条 synthetic public row；没有 outcome、scorer、Train/Dev/Final、provider、网络或可写 host mount。这个 PASS 仍只是静态/离线 readiness；没有运行 live Docker canary，也没有真实预测分数。下一步必须使用新 ID、单次、zero-provider、synthetic-only 的 Docker 隔离 canary，并在结果进入后再次独立复核。

- 2026-09-29 — 最小 prediction-first 合成闭环已通过独立复核：严格 cutoff 概率、逐行无标签提交、相对市场概率的 Brier/log loss、一次性 Dev、KEEP/REVERT、聚合记忆和崩溃恢复已经在同一 exact-hash v4 快照跑通。第一轮 KEEP，第二轮 REVERT；54/54 专项、33/33 相邻测试通过，独立攻击复核为 0 P0 / 0 P1。复核期间发现并修复了六个真实的绑定/恢复漏洞，包括 outcome 与冻结 Dev 不一致、完整评分未持久化、以及完整评分应 REVERT 但精简指标伪造为 KEEP。这个结果只证明合成编排，不是现实数据预测提升，也没有网络、付费、受保护 Dev/Final、训练、PMB、PnL、发布或推送。下一步改为盘点已打开的本地数据是否满足新合同，并另做真实隔离 canary。

- 2026-09-29 — 主线纠偏：撤回“以 PredictionMarketBench 为主底座”的假设。源码/论文审计表明 PMB 是公开、同进程、只有四个高度相关事件的早期交易回放器；它没有 Brier/log loss/calibration、严格 Train/Dev/Final 或开放 Agent 的可信 hidden-eval 边界。现有 PMB v4 PASS 只证明本地合成合同能 fail closed，不证明科学有效性。PMB 代码冻结为非生产 smoke/compatibility prototype，后续 intake、episode、adapter、hidden evaluator、Controller Swap 和治理扩建停止。核心改为 probability-first：严格 cutoff 概率、相对 market probability 的 proper score、隔离 Dev 评分、KEEP/REVERT 和聚合记忆；prediction 冻结后才另测 PnL。v0.1.26 本地 release candidate 完整保留但策略性暂停，因为发布它不能关闭当前三个科学 blocker。本次没有 fetch、provider、付费、真实训练、Dev/Final 读取或预测分数。

- 2026-09-19 — Supervisor 不再只靠文档判断“卡住”。新增了一个本机 watchdog：它分别检查进程是否还活着、有没有真正的新结果、数据门槛是否失败、预算和日志是否完整。零费用故障测试已经证明：任务可以继续发 heartbeat，但如果 30 秒没有有效进展，系统仍会主动建立故障记录；重启后不会忘记；修好并通过 canary 前不会恢复；恢复必须使用新 ID。Dashboard 已显示这套状态。下一步是把现有 Controller、取数、Docker、训练和评估 runner 全部接入它；在接入前，它还不能自动接管真实任务。
- 2026-09-20 — 第一个真实步骤已经接入 watchdog：Gate 1 查官方数据来源的 runner。它开始时登记任务，拿到有效输入和数据快照时分别登记真实进展；成功才关闭。超时或返回错误格式时会自动生成故障记录，不能直接重跑。30 项相关检查通过。现在还差最外面的独立 monitor：即使内部 runner 自己卡死，外层也要能发现、只停准确的进程，并把故障交给 Controller 调查。
- 2026-09-20 — Supervisor 的正常成功路径也用真实本机进程和 Docker 测过了。第一次测试发现一个新的退出竞态：任务已经做完，但子进程在父进程读取状态时短暂变成 zombie，被误判成进程身份变化。我们没有复用失败 ID，而是修复父进程回收逻辑、加固定复现测试，再用新 ID 重跑。第二次测试正常完成：没有故障记录、没有调用清理、进程和容器都已退出、0 模型调用、0 费用。相关检查 89/89 通过。代码还没有发布，因此正式付费入口继续关闭。
- 2026-09-20 — 又补了一条可复现规则：失败路径和成功路径的 canary 程序本身也必须进入发布清单，不能只冻结生产代码、却让验收程序留在清单外。现在以后发布少了任何一条 parent canary 都会被拒绝。测试仍是 89/89；因为发布清单又变了，现有本地结果不能直接当成已发布版本的入场证明。
No entry may turn a diagnostic, infrastructure repair or spent budget into a
claim of prediction improvement. Link detailed evidence rather than pasting it.

Quick terms: **HGB** means histogram-based gradient boosting, a series of
decision trees that correct earlier errors. **Ridge** is a regularized linear
regression. **MSE** is mean squared error; lower is better on the *same* rows.
"Opened Train" means the data was already available for development, not an
untouched test.

## 2026-09-17：改走本地 B 沙箱

- **现在的结果：** 已停掉后续 E2B 连接测试，并把定时监督任务改到本地 B 路线；没有新付费调用，也没有新的预测分数。
- **做了什么：** 写了只给 B 单独工作目录的 Docker 启动配置；容器不联网、不接收密钥、账本或封存评估目录，并限制权限和资源。32 项本地离线测试通过；进度已显示在 dashboard 的 activity log。
- **仍卡在哪里：** 这台 Mac 有 Docker Desktop，但引擎目前没有启动成功。因此还没有真实容器、隔离证明或 20 次实际交接数据。不会用普通本机子进程冒充沙箱，也不会用旧 E2B 状态记录批准新路线。
- **下一步：** 先让 Docker 引擎可用，再在一个新容器里跑零付费合成任务；通过隔离、交接、日志和清理检查后，才考虑连接 GLM 研究循环。

### 同日结果：本地交接已跑通

- Docker 已更新并启动。一个本地 B 容器在新 ID 下连续处理 20 个合成任务：0 丢失、0 重复、0 超时。交接 p95 为 29 毫秒，回显 p95 为 7 毫秒；测试后确认这个容器已消失。
- 单独的隔离探针确认无网络、看不到 Mac 用户目录和付费密钥、不能改写容器系统目录。加强 broker 的文件读取后，34 项离线测试及一轮新的真实容器测试都通过。
- **边界：** 这是连接和隔离的合成测试，不是 GLM 自主研究，也没有模型训练或预测分数。下一步仍需把 GLM 的决定接到 B，先做零付费研究任务，并处理版本发布与受保护的全局状态记录。

### 同日后续：代码已发布，正式 Controller 轮次仍关闭

- 本地 B 的代码、测试和说明已经固定成新版本 `789d360` / `market-rsi-protocol-v0.1.4`，只推到用户自己的 fork；37 项相关测试通过，远端源码逐字节核对通过。
- 保护决策页的安全审查拒绝了单独改页：它要求与追加式全局日志同步。我们没有绕过。因此虽然本地合成交接已通，GLM 还没有开始自主研究，训练和封存评分也没有启动或花新钱。
- 需要一次受审的“决策页 + 追加式日志”同步更新；在它通过前保持正式入口关闭。

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

### 2026-09-17：把连接耗时列为 P0，确认旧失败是整体命令截止

- **证据：** 旧 `-03` 运行从 A 方向本地检查到 `TimeoutException` 相隔约 25 秒，符合固定 E2B SDK 的整条 `commands.run` 流连接上限；没有 A 的 HTTP/TLS 报告，也没启动 B→A。不能据此判定 A→B 网络通或不通。
- **修复与验证：** 新版 `v0.1.2` 在用户 fork 已发布，整条命令上限调到 60 秒，并保存本机派发、标准输出和沙箱内部逐请求进度；异常回执会失败即停。46 项相关离线测试通过。专项 agent 复核其中 35 项，没有旧证据支持再猜一个代码补丁。
- **下一步：** 先核对总账、进程、沙箱与新编号，再做一次限额 $0.20 的真实双向连接测试。其他付费研究暂停；这还不是预测实验结果。

### 2026-09-17：新测试把超时定位到 A 的第三个请求

- **真实过程：** 用全新 `-04` 编号跑了一个 E2B 合成连接测试。A、B 两个沙箱都启动，基础边界检查和 B 的本地服务通过。A 的公开网页代理请求与直连请求都完成；A 通过环境代理访问 B 的请求只留下“开始”回显，60 秒后本机 SDK 超时。B→A 没开始，因此 A↔B 隔离仍未证实。
- **清理和费用：** 本方向独立服务的 kill 回执没有确认，但父程序确认 A、B 两个完整沙箱都已销毁，账户没有残留。权威账本对本次记的是未知实际用量的 $0.20 上限，不是发票；累计有效占额 $91.303153492/$200。
- **学到的与下一步：** 单纯把外层上限从 25 秒加到 60 秒没解决问题。要给沙箱里每一次网络请求独立的硬截止，并把超时记为“不确定”，不能记成隔离成功。已把这项修复交给 P0 专项 agent，修复、测试和新版本发布前不再派发付费测试。Dashboard 已分别显示 A→B/B→A 的阶段日志。

### 2026-09-17：把单次请求硬截止和 A/B 正常交接讲清楚

- **代码和测试：** 每个沙箱内的网络请求现在由独立子进程执行，6 秒还不返回就强制结束并留下“不确定”回执；父程序也会独立拒绝把这种回执当成网络隔离成功。失败时保留有大小上限的原始报告便于排查。52 项相关离线测试通过；真实 E2B 仍需新版本、新编号验证。
- **架构澄清：** A 与 B 的正常合作不直接互访，也不每做一步都跨沙箱通信。Controller 经本机 broker 下达一份任务，Researcher 在自己的沙箱内完成多步工具循环后回交结果；一轮内复用沙箱。当前卡住的直接 A→B 是故意测试禁止通道。后续要单独量正常 broker 交接时延；如果那条生产路径也慢，再重新考虑双远端沙箱。

### 2026-09-17：改成单 B 沙箱的正常交接测试，并让当前工作可见

- **用户纠正：** A 是能看 B、给 B 下任务的 Controller；B 不能直接访问 A。旧双沙箱的对称直接互访探针不是这个生产架构的验收测试。Supervisor 自己负责架构与验收判断。
- **当前动作：** 新 P0 subagent 正在实现一个持续 B 会话的 20 次 A→本机 broker→B 任务交接和 20 次 B 观察回读离线测试；不启动 E2B 或模型。旧双沙箱命令已禁止继续派发。新测试尚未得到结果。
- **可见度：** 本机 dashboard 把当前 agent 的近期日志放在顶部，把完成的 agent 标题和旧测试折叠到页面底部。旧的哈希保护决策页还未更新为新方向，页面明确把它标成历史账本；不能把旧页当作新方案的放行决定。
- **边界与下一步：** 离线测试即使通过，也不能替代真实 E2B 延迟和清理证据。先审核持续交接代码、测试和精确费用上界，再考虑在原 $200 总账及已授权最多 $5 连接测试范围内申请新编号的真实测试。没有新预测结果、训练或付费进程。

### 2026-09-17：新交接的 20 次离线测试通过，真实路径仍未测

- **做了什么：** 用同一个模拟 B 对象依次交接 20 个不同任务；每个任务都有编号、任务哈希、B 接收确认、B 事件和 A 读回记录。计时只用本机单调时钟，并按事先定的 p95 ≤2 秒、单次 ≤5 秒检查；缺失、重复、超时和回执被改都必须失败。
- **验证：** subagent 完成实现，Supervisor 独立重跑相关 38 项测试，全部通过。代码和测试还未发布；没有付费调用。
- **还没证明：** 真实 E2B 是否能在一个持续沙箱里稳定处理 20 次交接、GLM 是否实际读到事件、真实网络延迟、隔离、费用和清理。因此 dashboard 不得把“离线通过”写成“系统已跑通”。

### 2026-09-17：单 B 代码发布；真实测试仍被全局决策闸门挡住

- **做了什么：** 接好单 B 的真实测试入口、父子进程监督、独立账户清理检查和费用保守结算。一个持续 B 的 20 次交接在模拟沙箱中完成；固定 E2B Python 环境里相关 109 项离线测试通过。源码 `e384b5d` 和不可移动的 `market-rsi-protocol-v0.1.3` 标签已推到用户自己的 fork，远端源码哈希核验通过。没有原始数据、密钥或运行 artifacts 入库。
- **费用与安全：** 只在原 $200 总账内部把 $0.20 从 repair 额度调到 setup，未派发、未新增花费；有效占额仍是 $91.303153492。再次查到没有旧 canary 进程，E2B 账户里没有活跃的 Market RSI 沙箱。
- **当前阻塞：** 权威 `RESEARCH_STATE.md` 仍记录旧双沙箱决定。试图改成单 B 决定时，受保护文件写入被自动安全审查拒绝；没有绕过，也没有改坏附属追加账本。新的零付费 canary 和真实 $0.20 测试均未启动。需获准按“改决策页→空闲状态下追加 journal revision”的受审流程完成同步，然后才能继续；这不是预测结果或系统已连通。

### 2026-09-17：本地方案决策账本已修，预测数据仍未入场

- **完成：** 用户授权后，把旧 E2B 决策页和一条追加账本记录一起更新；独立校验通过，当前没有活动中的研究轮次。此前通过的本地沙箱 20/20 交接仍只是连接证据。
- **预测为什么没启动：** 只读核对显示，旧 2025 封存集只有 11 个独立日期，低于事先定的 20 日期；三季行情、逐球数据和标签也尚未通过入场检查。没有打开封存答案、调用付费模型或新增占额。
- **下一步：** 核对旧数据实际暴露范围，补齐可比较的数据和真正未看过的测试日期；模型署名与沙箱隔离的正式入口还需单独验证。不能把连接测试当成预测结果。

### 2026-09-17：核对旧行情能否补短周期标签

- **查到：** Polymarket 官方文档把历史价格点称为带时间窗口的“观测”，与真实成交价接口分开；旧数据长期保留的价格窗口较粗。它不能自动补成逐分钟真实成交，更不能把一个价格点当成一笔成交。
- **对实验的影响：** 2023 年那场“有上千个价格点、却无场内成交”的样本不能拿来证明 60 秒预测标签齐全。下一步需按事先固定的样本，把价格点与独立成交记录逐个核对；缺失的比赛仍计入总数。本次只读了官方文档，没有下载、训练、打分或花钱。
### 2026-09-18：P0 数据入场仍卡住；先补上源码版本闸门的一处漏项

- **目的：** 确保后续真实 Controller 测试使用的代码都被同一个已发布版本锁定。
- **做了什么：** 在现有发布清单中加入新适配器、交接程序和隔离检查；加防漏测试，修正测试夹具对清单的覆盖；独立跑了 32 项相关测试。
- **学到什么：** 清单漏项是具体的发布风险，现已在本地修正。离线测试通过不代表真实 GLM 或预测实验已验收。
- **结果：** 源码仍未审完、提交或发布，受保护状态和预算前置核对也未完成；正式数据和旧 Final 仍不入场。新增付费支出 $0。下一步只做确切源码审查与发布前置核对，不开付费轮次。

### 2026-09-20：外层 Supervisor 已能发现“子任务卡住”，但还没接真实进程控制

- **解决了什么：** 被监控的程序自己卡死时，外层 Supervisor 现在也能看出来。它会核对进程、容器、数据、预算和日志证据，把原失败固定下来，只清理记录中的那个任务，然后生成一份给 Controller 的修复任务。它不会自动重跑，也不会换 ID 偷跑。
- **怎么验证：** 35 项相邻测试全部通过，覆盖正常运行、心跳超时、清理失败、身份不匹配，以及重启后不重复清理。
- **还差什么：** 目前使用的是离线故障注入。下一步要把它接到 Mac 上真实的进程和 Docker 容器，再做一个零付费的“故意卡住”测试。通过以后，才接正式 Controller、Researcher 和数据下载。没有调用模型、没有下载数据、没有训练、没有看 Final，新增费用为 0。

### 2026-09-20：真实 Mac 进程和 Docker 卡死清理测试通过

- **实际做了什么：** 启动一个故意不回消息的本机子进程和一个本地 Docker 容器，让外层 Supervisor 发现超时。它先保存失败证据，再只停止这一个进程和这一个容器，最后生成修复任务。
- **中间发现的问题：** 第一次 Docker 没启动；第二次 macOS 启动 Python 时命令会变化；第三次进程已经被杀掉，但还需要父进程回收。三个失败都保留，没有用旧编号重跑。修完后第四个新编号通过。
- **结果：** 41 项代码测试通过，第四次真实零付费测试也通过。进程和容器都确认不存在，费用为 0。现在剩下的是把这套监控接进真正的 Controller 和 Researcher，而不是继续修本地清理。

### 2026-09-20：Supervisor 已接到正式 runner 的入口

- **改了什么：** 正式 runner 现在必须先收到外层 Supervisor 对当前进程的精确认领，才能读取付费 API key。Supervisor 会持续看预算状态和真正产生的新文件；只有这些发生变化才算进展，普通心跳不能假装工作有推进。
- **怎么测：** 新父进程实际启动了一个故意卡住的本机任务和 Docker 容器。五秒没有结果后，Supervisor 固定失败记录，只清理对应任务，生成修复单，不自动重跑。进程和容器都确认消失，12 项独立核对通过，费用为 0。
- **现在到哪：** 卡死、主动报错和正常结束三条路径都有硬检查，68 项相关测试通过；最新源码下的第二个新编号零付费测试也通过。代码还没有发布，所以付费入口仍然故意关闭。下一步先完成代码差异清单，再经授权发布，并跑一次零付费成功路径。
### 2026-09-20: Supervisor 父进程发布后两条路径都验收通过

- 只把已审查的 Supervisor 控制代码推到用户自己的 fork：commit `a3a33fe`，tag `market-rsi-protocol-v0.1.10`。远端 305 个受控文件与本机完全一致。
- 故意卡住的任务：Supervisor 留下一条失败记录，只清理自己拥有的进程和容器，清理恰好执行一次。
- 正常结束的任务：没有生成失败记录，没有调用清理，进程和容器自然退出。
- 两条都没有调用模型，费用是 `$0`，也没有残留进程或容器。这证明“卡住会被发现和收尾，正常任务不会被误杀”。
- 还没有开始付费预测。下一步先审查并发布 Gate 1 的 Controller 选数据源代码，然后才允许一次有上限的决策。

### 2026-09-20：Gate 1 的单次 Controller 调用层已补齐

- 之前的代码能准备问题、检查答案和抓一个官方页面，但没有把“第一个模型回答”和永久 ID、费用、原文、最终任务完整绑住。这层现在补上了。
- Controller 只能回一次；格式错、被截断或私自加 URL/命令时直接失败，不换一个答案。原始回答会先保存。
- 真实 tokenizer 算出输入 700 tokens，最坏费用上限是 `$0.0282852`。本次没有调用 provider，没有花钱。
- 28 项专项检查和一次零费用 canary 通过。但还差最外层的发布、总账本、进程监控和失败收尾，所以付费 Controller 仍然没启动。

### 2026-09-20：Gate 1 的外层账本和监控已接好

- 现在发送前出错会取消预留，不会算成花费。如果已经发送，有 token 回执就按真实 token 结算；没有终态回执就暂时按 `$0.05` 上限占用。
- 已经发送后如果本机崩溃，全局任务会保持占用，要先修复和对账，不能直接跑下一个。
- 付费 key 仍放在最后：发布、输入、运行环境、全局状态、预算、重复进程和 Supervisor 对这个子进程的认领都通过后，程序才读 key。
- 最新全套检查是 373/373。两个新的零费用 canary 都通过：一个检查单次 Controller 回答，一个检查全局状态和账本顺序。真实 provider 调用和费用仍是 0。
- 现在还差不可修改的 commit/tag/push 和发布后验收，所以还没有发付费 Controller 请求。
- **2026-09-20 23:25 EDT — Gate 1 packet repair:** The first published v0.1.11 source-selection launch did not reach GLM. It found a real preflight bug: the packet receipt hashed pretty-printed file bytes while the runner compared canonical JSON. Supervisor cleanup worked and provider cost was `$0`, but the canary had missed the production artifact path. The repair now names and checks both hashes in the parent before spawning a child, preserves the old failure, and passes 379/379 checks in the required environments plus one fresh exact-packet zero-provider canary. Outcome: operational capability improved; no scientific or data result. Next: independent diff review and full production-CLI zero-provider acceptance before seeking release or paid-run authorization.
- **2026-09-20 23:35 EDT — 完整生产路径零费用验收通过：** 新 canary 用真实父进程、真实命令参数、真实子进程身份、真实 Supervisor claim，以及合成的全局状态和预算账本走完了一次。只把 Git 发布查询和模型后端替换成明确的离线假对象。结果是 380/380 项检查在各自需要的环境通过；`p0-gate1-production-cli-canary-20260921-03` 通过，模型调用 0、真实费用 `$0`、没有抓数据、没有放行正式数据。代码仍未提交或发布，不能重跑付费 Gate 1。下一步是独立审查差异，申请新版本发布授权，再用发布后的相同字节重跑零费用验收。
- **2026-09-20 23:40 EDT — 验收入口收紧后再次通过：** 审查发现，离线子程序替换虽然没有出现在 CLI，但程序内部仍接受任意文件路径。现已限制为唯一的 canary 文件和唯一的 synthetic tag，任意其他替换会失败。新增反例测试后共 381 项；受限环境通过 379 项，另外两项本机进程/socket 测试单独通过。新 ID `p0-gate1-production-cli-canary-20260921-04` 再次走完整路径成功，模型调用 0、真实费用 `$0`。这是最终本地候选，仍未提交或发布。

### 2026-09-21：P0 Gate 1 发布完成，但第一次真实 Controller 回答被截断

- 修正了 Supervisor 的等待时间：GLM 单次采样最多允许 60 秒，外层现在等 90 秒，不会再在模型仍合法工作时误杀。382 项检查全部在各自需要的环境通过。commit `3885ab3` 和 tag `market-rsi-protocol-v0.1.13` 已只推到用户 fork；远端 318 文件 manifest 是 `f5137381a1c8362c350de26394aa8b385b06c8e9caa670e602589f8d8ff870d8`。发布后 canary `-08` 通过，模型调用 0、费用 `$0`。
- 唯一授权的真实 ID `market-rsi-gate1-controller-20260921-02` 调用了 GLM 一次。输入 700 tokens；模型返回恰好 2,048 output tokens，`finish_reason=length`。全部输出仍是分析文字，截断前没有写出要求的 JSON plan，因此没有 `decision.json`、`task.json` 或有效 provider receipt。
- 协议正确地把它记为失败，没有自动重试，没有抓公开数据，没有读取 Dev/Final，也没有放行任何正式数据。账本因为缺少可验证的终态 token receipt，按 hard upper 保守记录 `$0.05` 为 `uncertain_terminal`；这不是已确认 invoice。Supervisor 确认进程和容器均不存在。
- 结论：连接、发布、tokenizer、账本和 Supervisor 路径已经打通；当前 P0 卡点是 Controller 输出设计，而不是 E2B 或数据下载。下一步先离线修 answer-first structured output 和 token/cost 边界，通过 adversarial canary 并发布新版本；没有新的明确授权前，不再调用 provider。

### 2026-09-21：Controller 输出协议已完成离线修复

- **为什么失败：** 上一次不是超时，而是 Controller 把 2,048 个输出 token 全部用在分析上，截断前没有提交最终计划。单纯延长等待时间不能解决。
- **怎么修：** 不再让它最后自由写 JSON。现在只给一个“提交 Gate 1 计划”的结构化入口，里面必须一次填完全部字段；这个入口只能记录计划，不能联网、执行、买数据或看 Dev/Final。自由文字、多个提交、截断、额外权限都会失败，也不会自动再抽一次。
- **预算：** 真实 tokenizer 算出新输入为 1,393 tokens；3,072 输出 token 的最坏费用是 `$0.04409478`，仍低于单次 `$0.05` 上限。
- **验收：** 34 项相关测试和 44 项 Gate 1 检查通过；两个新的零费用 canary 通过，provider 调用 0、费用 `$0`、没有抓数据。全仓 516 项中 514 项通过，另两项是旧 memory artifact 哈希漂移和受限环境不允许读取 `ps`，与本次 Gate 1 改动无关。
- **边界：** 目前只证明离线协议修好了。代码还要固定成新 commit/tag，并跑发布后的完整生产路径零费用验收；新的付费 Controller 调用仍未授权。
- **发布后结果：** commit `61cb1aa` 和 tag `market-rsi-protocol-v0.1.14` 已只推到用户 fork；远端 318 个受控文件匹配 manifest `d682d86c0f98919676d376e849dec6f1b11a0633a762eee154e18daba3f9a6a3`。发布后完整生产路径 canary `p0-gate1-production-cli-canary-20260921-09` 通过，provider 调用 0、费用 `$0`。受保护状态账本已同步到新页面哈希，当前没有活动轮次，付费入口继续关闭。

### 2026-09-21：v0.1.14 唯一真实回答失败关闭，已完成离线通用修复

- **真实发生了什么：** 用户授权的新 ID `market-rsi-gate1-controller-20260921-03` 只调用 GLM 一次。模型选了“检查 2025 全季 Polymarket 交易访问”，输出 1,393 input / 582 output tokens，正常 `stop`，计量成本 `$0.01384128`。
- **为什么没放行：** 回答用了唯一提交工具，但工具调用后带了 GLM 模板的空 `<|observation|>` 终止标记，并多写了一个未声明的空字段 `rights_check_placeholder`。协议按规定拒绝，没有偷偷删除字段或替模型补答案。
- **边界：** 没有生成 decision/task，没有公开抓取、数据入场、训练、Dev/Final 读取或自动重试。全局状态已失败关闭；精确进程/容器清理通过。
- **本地修复：** 下一版只允许一个完全空的模板终止标记；叙述、第二个调用、多余字段仍失败。提示也明确要求只填声明字段。43 项相邻 Gate 1 检查和 12 项 packet/fetch 检查通过；全仓 516 项中 515 项通过，唯一错误仍是无关的旧 memory artifact 哈希漂移。真实失败回答回放仍被多余字段挡住。三个新零 provider canary 全部通过，费用 `$0`。新提示为 1,406 input tokens，最坏费用 `$0.04415796`。
- **下一步：** 先独立审查这份两文件代码改动和失败报告。任何新付费样本都必须使用新发布版本、新永久 ID 和单独授权；当前不重跑。
- **发布完成：** commit `d099b1b` 和 annotated tag `market-rsi-protocol-v0.1.15` 已只推到用户 fork；远端 318 文件与 manifest `056e3f5f…27ff5` 匹配。发布后完整生产路径 canary `p0-gate1-production-cli-canary-20260921-11` 通过，provider 调用 0、费用 `$0`、没有抓数据或放行数据，进程和容器均无残留。新的付费 Controller 仍未授权。

### 2026-09-21：去掉“只改文档也必须切回 tag”的发布摩擦

- **问题：** 旧发布检查要求整个仓库 HEAD 正好等于协议 tag。即使受控源码完全没变，只在 tag 后补一份报告，也会被拒绝，迫使正式 runner 另建 detached worktree。
- **修复：** 现在直接比较当前 318 个受控源码字节与 annotated tag 内的同一组文件。文档-only commit 可以存在；任何受控源码变化，无论已提交还是未提交，仍然失败。
- **验证：** 33 项相邻测试通过；全仓 516 项中 515 项通过，唯一错误仍是无关的旧 memory artifact 哈希漂移。零 provider 完整路径 canary `p0-gate1-production-cli-canary-20260921-12` 通过，费用 `$0`，没有抓取或放行数据。
- **边界：** 这是本地未发布的 human-assisted operational repair。没有 tag、push 或新的付费 Controller 授权。

### 2026-09-21：全仓检查不再把“本机没带旧 artifact”误报成实验被改坏

- **发现：** 唯一的 memory recovery 红灯不是 hash 变了。这个本机 source-only 副本根本没有迁入旧运行 artifact；测试把“文件不存在”和“文件被改”报成了同一句话。
- **修复：** 只有当两个完整的旧 artifact 根目录都不存在时，这项历史集成检查才明确跳过。如果只迁了一部分、文件 hash 不同或模型冻结文件改变，仍然失败。正式恢复程序没有改。
- **另一个环境限制：** 当前受限测试环境不允许调用宿主 `ps`。四种 trainer 的宿主监控集成检查会明确跳过；正式 trainer 的实时 RSS 检查没有被放宽。
- **结果：** 固定本机 runtime 跑完 516 项：全部成功，2 项有明确原因的环境跳过。没有模型调用、数据抓取、训练、Dev/Final 读取或费用。
- **下一步：** P0 仍是正式预测数据入场。先发布当前本地修复并跑发布后零费用 canary；新的付费 Gate 1 Controller 样本必须另行授权。

### 2026-09-21：v0.1.16 单次 Gate 1 回答因重复字段失败关闭

- **运行结果：** 永久 ID `market-rsi-gate1-controller-20260921-04` 只调用 GLM 一次，正常结束。输入 1,406 tokens，输出 465 tokens，计量成本 `$0.01248291`，没有重试。
- **模型想做什么：** 它选择检查 2025 全季 Polymarket 官方交易接口能否覆盖 285 场比赛。这是一个有用且符合当前数据瓶颈的方向。
- **为什么没通过：** 同一个必填字段 `rights_check` 写了两次，而且两段文字并不完全相同。协议不能擅自挑第一段、最后一段或合并，因此整份计划按重复字段失败。
- **安全边界：** 没有生成正式 decision/task，没有下载公开数据，没有放行训练，没有读取 Dev/Final。账本按真实 token 记录，不是按 `$0.05` 上限计费；进程和容器都已确认清理。
- **下一步：** 只做离线因果修复。先判断“数据使用权规则”是否应该由 Supervisor 固定执行，而不是让 Controller 自由写；通过测试和独立 canary、发布新版本并获得新的明确授权前，不再调用 provider。

### 2026-09-21：权限规则已从 Controller 自由输出中移除

- **怎么改：** Controller 以后只选研究问题、公开来源、假设、固定样本、操作和预算。数据能不能访问、能不能买、能不能写、能不能进入正式训练，由 Supervisor 的固定版本规则决定。
- **为什么这样改：** 权限规则不是研究想法，让模型自由写没有好处，反而连续制造格式错误。重复字段仍然会失败，系统不会替模型挑答案。
- **验证：** 41 项相关检查和全仓 516 项检查通过；两个新零费用 canary 通过。没有调用模型、没有下载数据、没有开始训练。
- **新 packet：** 输入文件和内容 hash 都已经固定；真实 tokenizer 测得 1,468 input tokens，单次最坏费用 `$0.04445928`，仍低于 `$0.05`。
- **现在边界：** 这是本地未发布版本。下一步是独立审查、再申请发布；没有授权新的付费请求。

### 2026-09-21：第一版预测实验设计已经开始并通过机器检查

- **要回答的问题：** 在数据、target、样本、评估规则和总美元相同的条件下，自迭代研究代理能不能打败 Train 上选出的强普通模型。
- **已经固定：** 所有路线用相同行；按时间切 Train、Route-Dev、Audit-Dev、Final；Final 至少 20 个从未看过的日期；主要比较 candidate 和 strong baseline 的逐场等权 MSE，并看按日期分块的区间。
- **还没有乱定：** 数据还没正式入场，所以 target、具体日期、强 baseline 和正式实验预算都保持空白。它们必须在看 Dev 前固定并写 hash。
- **baseline：** 至少包含 zero change、persistence、Ridge、HGB；如果运行环境验证通过，再加 CatBoost 或 LightGBM。在 opened Train 上按固定预算选一个强 baseline。
- **RSI 路线：** GLM Controller 可以查文献、设计 feature/representation/trainer/loss 或提出新算法；一次试验只改 prediction 里的一个组件，所有失败也归档。Supervisor 不替它选科学方向，只守数据、预算和评估边界。
- **验证：** 设计 JSON 通过验证器；八个反例确认它不能提前打开执行、选择 target、缩短 Final、删掉 HGB 或给自己加预算。旧 memory replication 和 benchmark scorer 的十四项测试也继续通过。
- **版本：** 修复 commit `bfef4d0`；实验设计 commit `7bea4fc`；审查边界文字修正 `191e03e`。三个都只在本地，尚未推送。

### 2026-09-21：v0.1.17 已发布，单次 Controller 漏了机械 schema

- **发布与 canary：** 三个提交已只推到用户 fork，annotated tag 是 `market-rsi-protocol-v0.1.17`。远端 commit、tag object、318 个受控文件和 manifest `9200f93f…cd15d` 全部匹配。发布后 canary `p0-gate1-production-cli-canary-20260921-15` 通过，provider 调用 0、真实费用 `$0`、没有抓数据或放行数据。
- **真实请求：** 永久 ID `market-rsi-gate1-controller-20260921-05` 只调用 GLM 一次，没有重试。输入 1,468 tokens，输出 349 tokens，正常 `stop`，计量成本 `$0.01137483`。
- **模型做了什么：** 它仍然选了当前有用的问题：检查 2025 全季 Polymarket 官方交易接口；固定最多 3 个市场、20 个请求、2 MB、20 分钟。所有真正的研究字段都填了。
- **为什么失败：** 它只漏了固定版本标签 `schema`。系统没有偷偷补字段，所以没有生成 decision/task，也没有开始抓数据。
- **终态：** 权威账本为 `metered_terminal`；总计量费用 `$85.087982132`，可用 `$106.253436988`。进程和容器都已清理；没有 public fetch、数据入场、训练或 Dev/Final 读取。
- **下一步：** `schema` 不该由模型决定。离线改为 trusted adapter 固定注入；真实研究字段仍必须完整、唯一、严格验证。当前不再调用 provider。

### 2026-09-21：机械 schema 已完成离线修复

- **怎么改：** Controller 现在只填写 12 个真实研究字段。固定协议版本由 trusted adapter 注入；如果模型自己加 `schema`，它反而会因为额外字段失败。
- **没有放宽：** 缺少、重复或多写任何真实研究字段仍然失败。rights policy、数据边界、预算和 Dev/Final 隔离都没变。
- **验证：** 55 项 Gate 1 检查和全仓 516 项通过，2 项按原原因跳过。新的 adapter、外层账本和完整生产路径 canary 都通过；provider 调用和真实费用是 0，没有抓数据或放行数据。
- **新 packet：** file hash `5f261e00…eff85`，canonical hash `28d5265c…08c6`；1,456 input tokens，单次最坏费用 `$0.04440096`。
- **当前边界：** 修复已本地提交为 `4fa02dd`，失败和修复审查提交为 `b9095a7`；两者都未发布，没有新的付费请求授权。

### 2026-09-21：Gate 1 离线计划 canary 合并测试

- 两条独立工作线的代码已合并到当前工作目录：一条把请求上限固定为 6，并要求每个选中样本的完整行和哈希都匹配预先承诺的合成 Train 目录；另一条补了可保存结果的离线 canary。合并时发现 canary 拦截函数仍用旧接口，已改为把目录绑定参数传给真实 builder，不能由 canary 自己替 builder 拒绝假哈希。
- 合并后 35 项直接相关检查、105 项 Gate 1 核心检查、15 项 Gate 1 runner 检查通过；全套 516 项通过，2 项因本机环境条件明确跳过。
- 合成 canary 的有效路径重复编译一致；34/34 个攻击输入、26/26 个编译后篡改被拒绝。结果保存在 `/Users/estelle/Library/Application Support/MarketRSI/runs/p0-gate1-executable-plan-canary-20260921-01`；它只生成离线请求计划，网络调用 0、provider 调用 0、费用 `$0`，没有抓取数据或开放 Dev/Final。
- **边界：** 独立复核仍在进行。当前只有合成目录的承诺，真实 Train 数据目录尚未获得入场资格；本次未提交、未发布、未启动任何付费请求。
- **独立审查发现并修复：** 审查者用篡改后的请求清单直接调用收据生成函数，发现它只查 schema，会把 `max_requests=999` 写进收据。这不影响上述离线 canary 的真实路径，但不能作为未来执行器的安全边界。现在收据函数必须拿到原 builder 输入和受信目录绑定，重新生成整份请求清单后逐字段比对；改上限、请求数、联网权限或目录字节都会失败。新增两项测试后，相关 37 项和全套 516 项通过（2 项环境跳过）；新合成 canary `p0-gate1-executable-plan-canary-20260921-02` 仍为 34/34 + 26/26，网络/provider/费用均为 0。第二次独立复核待完成；生产接线和发布仍关闭。
- **第二次审查与最终离线结果：** 审查者又发现 Python 会把 `6.0` 当 `6`、把 `0` 当 `False`，因此普通对象相等不足以保证收据字节准确。现改为比较规范 JSON，并只用重新生成的受信清单制作收据。新反例覆盖上限、联网布尔值和分页 offset 的类型混淆。独立复核给这一个离线收据边界 `PASS`；相关 37 项和全套 516 项继续通过（2 项环境跳过）。最终合成结果 ID `p0-gate1-executable-plan-canary-20260921-03` 为 34/34 + 26/26，费用 `$0`；builder 源文件 SHA-256 为 `60117c1ea76bfec6bca818d31ae05699f01ebe412ffd1babd1363e8da085784e`。这**不是**生产接线、真实 Train 入场、发布或付费请求的验收。

### 2026-09-21：并行工作改为只优化真正的等待时间

- **问题：** 两条代码线虽然同时完成，但接口对不上，随后合并、全套测试和多次审查修复依次等待。没有实际计时证明多开聊天缩短了总用时。
- **改动：** Supervisor 规则现在要求先固定共同接口和各任务独占的文件，再决定开几个并行任务；一个负责人持续合并，审查只看合并后的同一版本。开发中先跑相关小测试，版本稳定后跑全套；审查发现问题时做针对性修复、复核，并在最终冻结前重跑必要的全套检查。每段开始和结束时间要记入现有活动日志，比较实际关键路径，不让用户在聊天间传话。
- **结果边界：** 这次是工作方法的人工改进，不是模型预测能力或自动自进化的结果；没有新实验、provider 调用或费用。下一次并行任务才能检验是否真的节省时间。
- **机器检查：** 现有 `bottleneck_gate.py` 对声明为并行的计划检查起点哈希格式、2–3 个 worker 的独占文件、合并依赖，以及独立只读审查；文件冲突或顺序错误会在派发前失败。新增测试后，该模块 6/6 通过；Supervisor 其余非网络测试 462/462 通过，网络审计事件 0。完整 Supervisor discovery 的另外两项仍因已退役 E2B 子进程和本机端口权限出错，未归因给本次改动；研究目录另一组 516 项通过、2 项环境跳过。旧单任务计划仍能通过派发检查。新规则能挡住错误的**声明**，实际是否加速要在下一波记录时间验证。

### 2026-09-21：聚焦检查现有真实数据能否启动预测自循环

- **结论：** 现在还不能把合成 canary 算作真实数据自循环。2024 有整季交易和 label 支持审计，但未正式入场；2023 只匹配 237/285 场，固定样本里有零成交的常规赛场次；2025 匹配 285/285 场目录，却只有一场交易 canary，尚无整季成交与标签审计。
- **测试集问题：** 旧 2025 Final 仅 11 个日期，低于预设的 20 个未看过日期；访问记录不完整，不能把未知当作未看过。2026 候选仍只有赛程承诺，未入场。
- **下一步：** 只推进真实数据的最短路径：生产源码冻结及零费用验收后，由第一份有效 Controller 决策选一个有界的公开来源调查；随后核实交易、PBP、数据权利和缺失率。没有扩大通用 harness、没有网络/模型调用、训练、Dev/Final 读取或新费用。详细证据见 `P0_DATA_READINESS_DECISION_2026-09-21.md`。

### 2026-09-21：把数据缺口纳入自循环定义

- **发现：** 当前 Gate 1 代码只给 Controller 五个固定问题、四个固定来源；只有固定文档读取和一个合成的固定交易请求计划被登记为可执行。这能安全做窄范围调查，却不能证明系统会自主发现并补齐新的数据缺口。
- **设计修正：** 实验设计和 Supervisor 规则现明确要求：独立审计发现缺口 → Controller 基于完整分母和来源证据提出来源/匹配/目标假设 → Researcher 只运行经过 broker 审查的有界任务 → 独立审计核实可用覆盖、权限与成本 → 结果进入下一轮。新来源可以提出，但不能凭模型一句话获得联网/购买/封存数据权限。
- **当前边界：** 这是人写的设计修正，不是已经运行的 Controller 自循环；开放式提案及结果反馈的生产接线仍未完成。没有数据抓取、模型调用、训练、Dev/Final 读取或费用。

### 2026-09-21：开放式数据缺口提案的第一道代码边界

- **代码：** 新增 `p0_data_gap_proposal.py`。它接收来源哈希绑定的数据缺口和 Controller 自由提出的来源/匹配/质量/目标方案，留下不可执行的待审提案；审核反馈可以绑定到下一轮输入。新来源不必在旧四项清单里，但提案不产生任务、handler、联网、购买、数据入场或 Dev/Final 权限。
- **验证：** 十项离线测试通过，覆盖新来源可提案、篡改缺口 hash、封存值暴露、超上限请求、改写提案、超提议费用及错误反馈。没有模型或网络调用，费用 `$0`。
- **尚未完成：** 这个独立模块尚未接到正式 GLM adapter/outer runner；真实审计回执的签发方仍由未来可信 caller 验证。当前 live Controller 仍受固定清单限制，不应宣称已具备自动找新来源或完成数据修复的能力。下一步需版本化接线和完整生产路径零费用验收。

### 2026-09-21：新来源提案接到 Gate 1，但只通过零费用合成验收

- **改动：** GLM Controller 的同一次回答现在可二选一：提交旧清单内的有界调查计划，或提出清单外的新来源、匹配方法、质量检查、目标假设。后者只归档为 `review_required`，不能生成研究任务，也不给联网、购买、数据入场或 Dev/Final 权限。外层 Supervisor 重新解析原始回答、重算提案并核对文件哈希；它仍只允许一次模型样本和一个永久 ID。
- **反馈边界：** 合成审计反馈已能和提案哈希一起编成下一轮输入；这还不是来自独立真实审计员的回执，也没有接入下一次 live Controller 请求。真实反馈必须先由可信调用方核验签发和来源，不能把任意 JSON 当成已验证结果。
- **验证：** 41 项直接相关检查、112 项 Gate 1 检查、11 项发布/入口检查通过。新增反例证实有人在提案后偷加 `task.json` 或改成 `network_authorized=true` 时，外层复核拒绝并保留计量终态。两个新 ID 的合成 canary 分别走通旧计划和新提案；二者 provider 调用、真实费用、抓取和数据入场均为 0。真实固定 tokenizer 给当前双工具请求算出 1,906 输入 token，3,072 输出 token 的单次最坏计量为 `$0.04658796`，低于原 `$0.05` 单次上限。
- **完整测试：** 加上两项篡改反例后，允许本机进程/端口的环境中一次运行 Supervisor 全套 480/480 通过；受限环境里原先两项本机子进程/端口测试会因权限报错。现有研究文献/来源权利规则沿用 `AGENTS.md` 和已记录的官方来源审查；本次没有提出新的科学方法，也没有进行新的文献搜索。
- **下一关：** 本地代码尚未提交/发布；真实来源、真实数据目录、独立审计回执、下一轮 live 反馈输入都未打通。未运行新的 GLM 请求，也未开始预测训练或读取 Dev/Final。发布和新的付费请求按现行协议分别授权。

### 2026-09-21 晚：总 Supervisor 收拢路线图和正在做的工作

- 新建 `SUPERVISOR_ROADMAP_2026-09-21.md` 作为单页入口：当前 P0 是真实数据入场，不是继续堆通用 harness；先审查/冻结当前源码，再由 Controller 给一次有效决定，接着只做有界真实来源调查；三赛季 pilot、未触碰 Final、强 baseline 和预测自循环在数据入场之后。
- 对应四步机器 orchestration plan 已通过 dispatch 与 S1–S3 ready-step 检查。三条只读工作已分别送到现有 Codex task：发布边界、真实数据证据、任务可见性。三个 task 已重命名为 `ACTIVE · ...`；旧 agent 索引里三个实际上已完成却仍标为运行中的条目已归档。消息送达不等于工作完成。
- 更新了 dashboard 读取的任务索引和 blocker 看板；看板验证通过（6 个未解决项）。这些改动没有改科研 protected state、调用 GLM、抓数据、打开 Dev/Final、提交或发布源码。现在等三份实际审查证据，总 Supervisor 再决定下一项最小修复或是否具备发布审查条件。
- 三份只读审查现已返回，任务均改为 DONE。S1 判定 **REPLAN**：Wave 2 模块漏入受控源码、正式 Controller 未接 exact-request compiler、无真实 Train catalog、当前受控源码未干净到可发布。S2 判定真实 Train 仍不能入场：2023 237/285 身份匹配、2024 60 秒标签覆盖 32,384/47,875、2025 仅一场成交检查且逐场暴露仍大多 unknown；旧 Final 只有 11 日期。S3 发现 dashboard 只显示前 20/39 条任务；总 Supervisor 修了展示上限并通过本机数据源和实际页面接口核对 39 条。完整证据在三个 `AGENT_LOG_SUPERVISOR_*_2026-09-21.md`；人工日志不是原始工具流。
- 决策：先做 P0 生产接线因果修复，再独立审查、发布授权、零费用验收，之后才考虑另行授权一次 GLM 决定及有界真实数据调查。本次未发布、未付费、未抓取、未打开 Dev/Final。审查任务完成不等于整个 bottleneck resolved。
- 用户要求 Supervisor **持续维护**整体路线图与状态，而非一次性汇报。已在 `RESEARCH_SUPERVISOR.md` 加入每个工作块/定时唤醒核对同一 command center 的规则：实际任务和进程、证据、阻塞、版本、数据与 held-out 边界、实花与预留、下一验收；未知不可写成零或通过。复用了原 `market-rsi` heartbeat，移除过时版本快照，恢复 ACTIVE，改为每 15 分钟在本会话检查一次；状态不变时安静，重大进展/失败/需授权时通知。这个定时检查不赋予发布、付费、抓取或打开 Dev/Final 的权限。尚未有新的预测实验结果。

### 2026-09-21 22:28 ET：定时 Supervisor 推进一个 P0 发布缺口

- **目标与依据：** 按独立 S1 审查的 REPLAN，先修受控源码清单遗漏。这是沿用已有发布边界和审查证据的操作修复，不是新科学方法；本次没有新的文献主张。
- **动作和验证：** 先在发布专测列出漏掉的五个 Wave 2 文件，确认测试失败；随后只修改受控清单，发布专测 6/6 通过，`source_hashes()` 能读取当前 324 个受控文件。没有执行发布检查或声称旧 tag 覆盖这些新字节。
- **结果边界：** 仅本地修复了清单遗漏，尚未独立审查、提交或发布。正式 Controller 仍未接 exact-request compiler，真实 Train catalog 仍未入场，整个 P0 保持阻塞；没有模型调用、数据抓取、训练或 Dev/Final 读取。权威预算日志最后仍是旧 `market-rsi-gate1-controller-20260921-05` 的计量终态；本次未新增费用。进程检查没有匹配的 Market RSI runner。
- **下一步：** 对正式 bounded-plan → exact-request compiler 做失败复现和因果修复；保持 proposal 审查队列与真实数据入场边界分开。完整集成后再独立复查发布范围。

### 2026-09-21 22:49 ET：真实运行路径的 trade-plan 漏检已先行关住

- **问题与动作：** 沿用 S1 发布审查和现有离线编译器的操作证据，没有提出新的预测方法。测试先证明：Controller 选固定交易样本时，外层运行器原会在只有 `task.json`、没有 exact request manifest 的情况下判通过。随后在外层复核加入临时拒绝规则；文档页检查和新来源待审提案不受影响。
- **验证与边界：** 新反例修复前失败、修复后通过；外层、编译器与发布相邻共 24 项测试通过。这里仍是**故意 fail closed**，不是已经把正式 Controller 接到 compiler。下一步需传入经过独立审查的真实 Train catalog，编译并核对 exact manifest 与收据，才能解除拒绝。没有调用模型、抓取数据、开 Dev/Final、发布或增加费用；权威预算仍有历史未结算 hold，不能把预留当实花。

### 2026-09-21 23:17 ET：Gate 1 本地接线推进，正式入口仍关闭

- **版本化计划：** `SUPERVISOR_GATE1_BINDING_2026-09-22-v1.json` 的 dispatch 和首步 ready 检查通过。它只覆盖零 provider、零网络的合成集成验证；独立复核、真实数据入场与发布均另设闸门。
- **改动：** 固定交易计划通过代码登记的 Train 目录逐字节编译为 `compiled-plan.json`，外层复核从原始决定重新编译并比对字节。缺目录、改目录、未知承诺、篡改计划都不能通过；文档页和新来源待审提案仍在原边界。真实 CLI 和 Supervisor parent 增加目录字节哈希及承诺入参，并在读取 Tinker 密钥或创建子进程前拒绝非真实已审目录。目前登记表只有合成目录，因此付费入口仍不可执行。
- **验证：** 107 项 Gate 1 相关测试通过；零 provider 的生产参数路径 canary ID `market-rsi-gate1-binding-canary-20260922-0305-02` 通过，provider/网络/抓取都是 0，合成账本 `$0.00005103` 不是真实开销。先前在受限环境试跑同一 canary 的新鲜 ID `...0305-01` 被 `ps` 权限挡住，已保留失败现场，没有在原 ID 上重试。Supervisor 测试 discovery 为 475 项、1 失败/6 错误：缺 scipy、端口权限及旧 E2B 运行条件，不能称全套通过。
- **边界和下一步：** 没有 GLM 调用、真实数据抓取、预测训练、Dev/Final 访问、提交或发布。当前代码和多项既有改动仍未冻结审查；下一步做合并源码攻击性测试及独立只读审查，再处理真实目录入场。权威预算最后已知计量 `$85.087982132`、有效占用 `$91.446563012`（含 `$2.30` 预留），不能把它们混作实际花费。

### 2026-09-21 23:26 ET：修复目录前置检查造成的 Controller 死结

- **发现：** 上一步把“有已审查真实目录”设成所有 live 回答的前置条件。这虽然保护交易计划，却连文档调查和新来源待审提案也挡住；Controller 因而无法帮助寻找尚缺的数据。
- **因果修复：** 真实目录变为可选的成组参数：不传目录时，调查或提案可走原本的审批流程；只传路径/哈希/承诺的一部分立即拒绝。若提交固定交易计划，没有受信目录则外层审查失败、保留计量终态，绝不生成可执行请求。若传目录，正式入口仍要求代码登记的真实 Train 承诺；合成目录不能冒充。冻结 packet 现在明确告诉 Controller 目录尚未入场，建议先调查或提案。packet 字节已变化，旧文件和旧发布版本不能直接用于新请求。
- **验证：** 80 项直接相关测试通过；新的零 provider、无目录生产参数路径 canary `market-rsi-gate1-no-catalog-canary-20260922-0330-01` 通过，provider 调用、联网、数据抓取和真实费用都是 0；其合成账本 `$0.00005103` 只是测试值。合成 live 模式测试分别覆盖文档、提案可结束以及交易计划无目录失败，**不**声称真实 provider 已跑通。
- **仍需处理：** 在真实付费前，还要独立审查这一整版源码及 packet 能力说明；当前 packet 的工具 schema 仍列有交易操作，虽然外层会拒绝。要决定是否机器屏蔽不可用操作，避免一次无效付费样本。真实目录入场、发布、授权、预测实验均未完成。

### 2026-09-21 23:28 ET：当前无目录 packet 不再向 Controller 提供交易操作

- **改动：** 当冻结 packet 明示真实 Train 目录尚未入场时，Controller 的提交工具枚举去掉 `fetch_fixed_public_sample`。这只收窄当前无法执行的操作，不替 Controller 选择文档问题、来源或新提案。若模型仍构造越界交易决定，无目录的外层审查依旧失败；以后真实目录入场需生成并审查新 packet/发布版本，不能沿用当前字节。
- **验证：** 80 项直接相关测试通过，工具 schema 测试确认该操作缺席；新 ID `market-rsi-gate1-no-catalog-canary-20260922-0340-01` 的无目录生产参数路径零 provider 验收通过，真实费用、网络调用和抓取均为 0。先前 synthetic trade 的离线编译测试仍在，但不代表当前 packet 可执行交易。
- **剩余关口：** 独立复核当前整合版源码、控制文件范围和脏工作树；真实目录入场、正式 release、单次 GLM 授权及后续数据调查仍未完成。
- **整合复查：** 读完整体 diff 时发现 Supervisor parent 会把 release tag 和源码哈希参数重复传给子进程；已删去重复项并加单次出现的测试。最新 Gate 1 相关测试 110/110 通过，`git diff --check` 通过。该修复不改变科研路线，也没有实际 provider 或网络调用。

### 2026-09-21 晚：原始 Controller 回答与 Supervisor 修改分开归档

- **原文没动：** 唯一真实 Gate 1 回答 ID `market-rsi-gate1-controller-20260921-05` 的原文 SHA-256 为 `e0ada90eec518767cee11da568496917dd1326758fe62ec0a565314e0ad4938a`。模型选了 2025 Polymarket 历史交易问题，同时要查文档和取三个市场的固定小样本。账本是 `$0.01137483` 计量终态；没有抓取数据。
- **新发现：** 旧适配器先因机械 `schema` 缺失拒绝；但即使补上，原答仍同时请求两个操作和最多 20 次查询，而当前受信能力只能执行单页文档或另一个需要真实目录的六请求固定交易计划。这是交给模型的表面上限与实际 handler 不一致，不能仅据此说模型弱。
- **Supervisor 修改：** 独立、非执行的分阶段可行性建议写在 `GATE1_ORIGINAL_CONTROLLER_PROPOSAL_FEASIBILITY_2026-09-22.md`。它保留原问题/来源，建议先核文档、满足来源与目录条件后才考虑固定交易样本，再把事实反馈模型。该建议不冒充 Controller 的新决定，也不复用旧 ID。下一轮 packet 必须把原回答的拒绝原因和准确可用能力告诉 Controller，不能只让它猜。

### 2026-09-21 晚：Supervisor 重新安排放宽 Controller 的工作

- **决定：** 放宽 Controller 的研究提案空间，不放开来源权利、未来信息、Dev/Final、密钥、预算或独立评估。原回答的拒绝原因和真实可用的 broker 能力已加入本地下一轮 packet；Supervisor 不代模型选下一条科学路线。详细负责人、依赖和验收写入 `SUPERVISOR_ROADMAP_2026-09-21.md`。
- **零费用预检：** 本地 tokenizer 得到 2,482 输入 token、3,072 输出 token 上限，单次理论费用上限 `$0.04938732`，低于既定 `$0.05`。这是上限估计，不是实际花费。改动后 123 项 Gate 1 相关单元测试通过，`git diff --check` 通过。
- **未完成：** 当前实现仍主要是文档调查和待审提案，不能声称开放式研究任务已经可执行；改动后的完整生产路径 canary、独立审查、源码发布和新的付费授权仍需分开完成。本段没有 GLM 调用、真实数据抓取或预测实验。
- **新 canary 结果：** 首个新 ID `market-rsi-gate1-relaxed-packet-canary-20260921-01` 在受限环境的 `ps` 权限检查处失败；确认无遗留同 ID 进程后，用全新 ID `...-02` 在有本机进程核对权限的环境运行，生产参数路径通过。其 provider 调用 0、真实费用 0、公开抓取 0；合成账本 `$0.00005103` 不是实际费用。失败的 `...-01` 保留，不重用。独立源码/账本审查及正式发布仍未完成。

### 2026-09-22：并行审查发现并修复一个付费死路

- **分工结果：** 真实数据审查证实当前只有合成 catalog，真实交易执行仍 BLOCKED。两个旧 Codex 审查 task 没有交付可见的最终报告，均按阻塞记录；新独立 agent 在 324 文件哈希 `48b7b78f…14afa` 上给 REPLAN。
- **具体缺口：** 当前 packet 不提供固定交易操作，但模型仍可手写这个操作并被 adapter 当成有效计划；外层最终会拦截，所以没有数据泄露或超预算，但会白费一次付费 Controller 调用。回归测试先失败，证明原代码会接受。
- **因果修复与验证：** adapter 现在检查模型所提交操作必须属于该次工具 schema 真实提供的枚举。未来已审查 catalog 的离线正例通过测试专用 packet 继续覆盖；当前正式 packet 仍隐藏交易。修复后 124 项 Gate 1 相关测试通过，`git diff --check` 通过；新 ID `market-rsi-gate1-offered-operation-fix-canary-20260922-01` 的无目录生产参数路径通过，provider 调用和真实费用均为 0。新的受控源码哈希 `2544e25605a9c9d731784b492dc5c040f0b43aa47fc911b3f8a373db1312eb4e`。
- **边界：** 这不是预测结果，也不是已发布版本。修复后的独立复审、清理发布范围、正式发布和后续 Controller/数据调查仍未完成；没有新付费调用、抓取、Dev/Final 读取或 push。

### 2026-09-22：修复后独立复审通过，两个空闲 task 并行交付

- **窄范围 PASS：** 独立 reviewer 在新受控源码哈希 `2544e25605a9c9d731784b492dc5c040f0b43aa47fc911b3f8a373db1312eb4e` 上重放原越界交易提交；adapter 在产生任务文件前拒绝。文档调查、待审提案和测试专用合成交易正例仍通过。124/124 Gate 1 测试及新零费用 canary 通过；provider 调用、真实费用和公开抓取均为 0。这不等于发布或预测实验通过。
- **并行工作：** 两个现有 Codex task 分别查发布范围和真实 Train 目录路径，完成后主动把结果发回总 Supervisor。发布审查给 REPLAN：324 个受控源码文件中有 17 个 dirty，包括共享 `bottleneck_gate.py`；不能挑部分文件就声称发布了同一源码哈希。数据审查确认只有合成目录，真实入场 BLOCKED。
- **数据下一步：** 若原始数据存在缺口，先由 Controller 选来源，核实权利、费用和访问范围，再考虑对同一原始版本完整重下、验原始对象哈希和逐场分母；不默认拼补旧碎片。尚未实际下载或入场。
- **Git 责任：** 用户把 Git checkpoint 时机和 fork 推送交给总 Supervisor。规则已写进 `RESEARCH_SUPERVISOR.md`；并行审查 task 不提交或推送。当前没有新 GLM 调用、真实抓取、训练、Dev/Final 访问、commit/tag/push 或新费用。正在做整合快照的最后独立复审。

### 2026-09-22：两个真实 Controller 答案都因工具格式被拒，开始离线修格式

- **第一次：** v0.1.18 的 GLM 选了官方交易文档，但把系统要求逐字填写的取样规则改写成了一段话。独立审查纠正了我们起初的判断：规则原文其实已在同一请求里，不能说是“没告诉模型”。第一次计量 `$0.01666737`，没有取数。
- **修复和发布：** 把取样规则从自由文本变成工具接口里的固定选项，补上第一次失败反馈；126 项测试与独立复审通过。只把六个代码/测试文件作为 v0.1.19 推到用户 fork。零费用 canary 通过。之后精确算出这份输入按旧输出上限的最坏预留是 `$0.05102514`，超过单次 `$0.05` 闸门，所以没有启动请求。
- **费用闸门：** 把最大输出从 3072 缩到 2944，最坏预留变为 `$0.04946994`；127 项测试与独立复审通过。只把两个代码/测试文件作为 v0.1.20 推到用户 fork，零费用 canary 通过。输入内容没改，真实数据/Dev/Final 均未打开。
- **第二次：** 新 ID `market-rsi-gate1-controller-20260922-02` 只采样一次。原始文本里用了正确的固定规则，但在 `max_minutes_placeholder` 附近把工具标签写坏了，解析后缺少必填的 `question_id`；本地审核拒绝，没有生成任务或抓取。之前说它只是“多写一个字段”不准确，已根据原始回答更正。计量 `$0.01790424`，进程/容器清理通过，ID 终态不可重试。两次新失败合计计量 `$0.03457161`，不是预留的 `$0.10`，也不是预测实验结果。
- **现在：** 付费重抽暂关。Supervisor 已开离线格式边界调查：查工具调用的结构化约束或安全的无权限字段处理，先写明接受/拒绝规则与测试，再考虑新的版本。真实 Train 目录、数据来源权利和正式预测实验仍是另外的阻塞项。

### 2026-09-22：把格式故障缩到真正的因果层

- 独立调查读回第二次原始回答，发现工具标签没有成对；不是普通“多一个字段”。原始回答及 `$0.01790424` 计量保持不变，不补写成成功。调查还用合成输入证明旧解析器可能忽略工具调用尾部的未闭合片段。
- Supervisor 在写明接受/拒绝规则后，本地收紧解析器：标签错、未解析尾部和重复/异常键都拒绝。原始第二次回答重放仍被拒；127 项 Gate 1 测试和 20 项解析/类型测试通过。另一人只读复核给出**本地窄范围 PASS**，没有把它当成可付费发布。
- 继续并行做一项离线简化：让 Controller 选短 ID 和研究内容，系统按已登记能力填执行参数，并清楚记下哪些是模型选的、哪些是系统填的。这样减少手写接口的负担，但尚未证明下一次模型会遵守，也没有新的数据或预测结果。专属工作记录见 `AGENT_LOG_GATE1_SHORT_CHOICE_2026-09-22.md`。

### 2026-09-22 02:00 ET：Gate 1 格式修复发布、验收，下一步直指真实 Controller 决定

- **完成：** 严格解析器和五字段短选择接口通过独立整合复核。相关 132 项 Gate 1 测试、20 项解析/类型测试和 staged diff 检查通过；只提交 13 个代码/测试文件为 `f06214b3bb521096078d897fe60ec9ba589c00c6`，annotated tag `market-rsi-protocol-v0.1.21` 已原子推送到用户的 `Estelle-LH/RSIBench-Data` fork。远端 tag、commit 与本地 324 个受控源码文件的哈希 `872f05ae48fa49deeb811bc6ca4705652168f198b5f1f9d69d3ce172ad0986da` 一致；未提交本地日志、数据、密钥、账本或 artifacts。
- **零费用验收：** 全新 ID `market-rsi-gate1-v021-postrelease-canary-20260922-01` 走生产 CLI 参数和 Supervisor→child 路径，`passed=true`；真实 provider 调用/费用、公开抓取、正式数据入场均为 0。合成账本 `$0.00005103` 只用于测试结算，不是实际花费。格式边界计划 v5 的三个步骤和整体验收经机器 resolve 检查通过。
- **下一步预检：** 全新 Gate 1 输入 packet `p0-data-admission-gate1-packet-20260922-03` 已从原有 Gate 0 与 live-transport 回执生成；没有模型调用或数据抓取。固定 tokenizer 重新计出 3310 输入 token、2750 最大输出 token，单次最坏上限 `$0.0494991`，旧 3300/$0.0494505 估算作废。权威 `$200` 账本计量 `$85.122553742`、setup 可用 `$0.071505532`，但仍有历史预留 `$2.30` 与未完成发票对账；当前进程检查未见 Gate 1/Tinker worker。获得新请求授权和完整唯一 ID/全局状态复核前不发送付费请求。
- **结论边界：** 两次历史格式失败继续是失败，不因修代码变成成功；新版仍未证明 GLM 会交出有效计划，也没有真实 Train 数据或预测得分。真正的下一判别步骤是只取一次全新 Controller 回答，先独立审查，再决定能否执行来源调查。

### 2026-09-22 03:33 ET：封存测试候选的第一天已过去，入场证据仍不齐

- **发现：** 9 月 18 日只按赛程预留的 2026 候选测试期从 9 月 20 日开始；现在是 9 月 22 日。原始预留文件 SHA-256 `70be5d64c6e35a680107fed6569e8cfb62e2be917b29f17aec584518f35372cc` 未改，仍标记完整访问历史、同机制市场覆盖和数据使用权均未验证，`formal_final_admitted=false`。本次只看了赛程元数据和这些标记，没有打开价格、标签或比赛结果。
- **结论：** 这不是一个已合格的封存 Final。第一天已经过去，不能再说“开赛前完成验证”；也不能因为缺证据就静默改选已经发生的日期。独立核对访问历史、市场机制和权利后，才判断原预留期是否还能证明真正未暴露；证明不了就保持未入场，再按事先固定、只用赛程的规则预留未来窗口。旧 2025 Final 只有 11 个日期，也不能顶替正式 >=20 日期要求。
- **其他状态未变：** v0.1.21、零费用 canary 和 `$200` 预算没有新变化；新 GLM 请求仍待单次确认，未调用 provider 或抓取数据。此问题与 Gate 1 数据调查并行跟踪，不拿封存结果指导 Controller。

### 2026-09-22 03:56 ET：独立核查封存测试候选，保留阻塞但不拖慢 Train-only 调查

- **做了什么：** 独立 auditor 只盘点预留文件、访问记录和来源/权利/机制元数据；Supervisor 重算所引六个文件及专属审计日志的 SHA-256，预留文件仍是 `70be5d64c6e35a680107fed6569e8cfb62e2be917b29f17aec584518f35372cc`。计划的第二步依赖闸门通过。详细 yes/no/unknown 表在 `AGENT_LOG_FINAL_NONEXPOSURE_2026-09-22.md`。
- **发现：** 已有 ledger 在 2026-09-20 至 11-02 的预留期没有记录，但缺少完整访问历史；零行不能证明无人看过。`labels_read=false` 只是预留文件的声明。2026 市场数据使用权和同机制覆盖也未证实。不能断言发生了污染，也不能认定完全未暴露。
- **决定：** 候选继续 `formal_final_admitted=false`；不看价格、标签、交易、比分或结果，不依据得分改选日期。封存集补证单独跟踪；Controller 的 Train-only 来源调查是独立路径，可在原有授权/预算闸门下继续。此次没有新 provider 调用、购买、训练或 Dev/Final 读取。

### 2026-09-22 05:04 ET：一小时停滞复盘

- **状态：** 无新 Controller 回答、数据回执或付费进程；预算末笔仍是旧失败请求，global-state 无 active cycle。现有 v0.1.21、零费用 canary 和输入 packet 不变。
- **判断：** 最短路径仍是单次新的 Controller 数据调查决定；没有可安全替代 Controller 科研选择的离线工作。此刻卡在这次请求的明确授权，而不是模型训练、E2B 或数据下载。最多预留 `$0.0494991`，授权后还要重新检查唯一 ID、进程、版本、账本和全局状态；未授权前不调用模型。没有新实验结果或费用。

### 2026-09-22 15:20 ET：授权等待期间启动三路零费用并行验收

- **启动：** Supervisor 同时派发三项互不重叠的只读工作：v0.1.21 单次 Controller 启动验收、真实 Train 入场关键路径、封存 Final 元数据补证方案。
- **边界：** 三项工作都只能读当前源码与证据并写各自日志；不能调用 provider、预留预算、抓取或购买数据、读取 Dev/Final 结果、修改受保护状态、提交或推送。
- **目的：** 新授权到达前先消除启动和后续执行中的可预见摩擦。三个结果返回后由总 Supervisor 逐项复核，再把 task index、blocker board、roadmap 和 dashboard 合并为一个下一步。
- **计划：** `SUPERVISOR_PARALLEL_READINESS_2026-09-22-v1.json`。当前仍没有运行中的付费 worker、新数据、训练或预测结果。

### 2026-09-22 15:42 ET：第一波验收完成，第二波 P0 工程修复已并行启动

- **启动路径：** v0.1.21 的版本、packet、runtime、预算和唯一 ID 检查都能通过；下一 ID `market-rsi-gate1-controller-20260922-03` 尚未使用。但本次付费请求没有新授权，不能启动；授权后还必须先写 decision revision 并重取 state/document hash。
- **真实 Train：** 保留的 2024 v2 capture 有 561 页、409,419 条原始记录，但仍是候选，不是正式 Train。现在的受控采集契约还是 v1 两页抽样；request catalog 不是 admission receipt；watchdog 只检查一个 64 位 hash 的格式。112/112 离线测试通过，只证明旧边界按设计运行。
- **Final：** 如果无法恢复自 9 月 18 日起覆盖所有访问者和存储面的完整防篡改日志，现有候选只能是 `not provable`，不能正式入场。没有读取结果，也没有换日期。
- **第二波：** 已并行派发 formal Train admission receipt/validator 和 Polymarket v2 cursor contract 两项本地工程修复。两项都不联网、不花钱、不抓真实数据、不改受保护状态。计划：`SUPERVISOR_PARALLEL_ENGINEERING_2026-09-22-v1.json`。

### 2026-09-22 15:50 ET：三个可见 Codex task 已改名并接入 Supervisor pull/push

- `01a0c58f…` 改名为 `ACTIVE · Train admission review`，负责独立对抗验收矩阵。
- `01a0c589…` 改名为 `ACTIVE · v2 cursor review`，负责独立检查 cursor/终止/硬上限边界。
- `01a0c597…` 改名为 `ACTIVE · 2024 rights + coverage`，负责核对权利、285 场分母、方向、时钟与来源回执缺口。
- Supervisor 已先 pull 三个 task 的旧结果，再 push 新任务；三者都已确认进入 active turn。每个 task 必须把最终结果主动发回本 Supervisor，Supervisor 验证后再归档和改名为 DONE。

### 2026-09-22 16:05 ET：两个 P0 实现完成独立复审

- **Train admission gate：** 第一轮 reviewer 找到 dataset bytes、season/question/task、正式调用点和 source commitment 缺口；实现方修复后，fresh rereview 对 scoped validator/Watchdog 给出 PASS。23/23 focused、37/37 adjacent 与零费用 canary 通过。端到端仍 REPLAN：尚未加入 controlled manifest，没有正式 training/eval caller，post-claim TOCTOU 仍需关闭。
- **v2 cursor contract：** reviewer 先找到超 1000 行、单 token、bool/float 冒充 int 等五类反例；实现方统一修复后，最终 source `6c329f54…e080f` 的独立 55/55 对抗检查与 80/80 合并检查通过。旧 v1 文件保持不变。它仍只是离线契约，不是网络、权利、catalog 或 admission 授权。
- **2024 evidence chat：** 原 task 连续两次完成但没有可见 final；Supervisor 已发第三次最小取回请求。若仍为空，将标为 BLOCKED 并转派，不会写成成功。

### 2026-09-22 16:14 ET：可见 task 完成换班，下一组两项离线证据开始

- **已拉回的 2024 结果：** replacement task 给出正式入场 REPLAN。离线证据支持完整赛程分母 285、已有映射 284，唯一明确缺失是 nflverse `2024_22_KC_PHI` / Polymarket event `17330`，原因 `moneyline_missing_or_ambiguous`。来源权利、代码拥有的主客队/代币方向以及 provider publish/local receive 时间仍不完整，所以不能正式入场。
- **任务重命名与归档：** replacement 已改名 `DONE · P0 2024 evidence replacement`。原来三次空回传的 task 保持 `BLOCKED · P0 2024 evidence · empty`，不再复用，也不把空结果写成通过。
- **新分工：** 两项零费用实现已在内部并行开始：完整 285 场候选账本，以及主客队/代币方向 verifier。两个可见 task 已分别改名 `ACTIVE · P0 285-game ledger review` 和 `ACTIVE · P0 orientation review`，收到只读独立复审任务，并确认进入工作。它们必须把中间和最终证据主动推回总 Supervisor。
- **边界：** 本段没有联网、重下、付费调用、Dev/Final 读取、数据入场、训练、commit、tag 或 push。权利与真实发布时间仍是外部 gate，不能靠本地代码消除。

### 2026-09-22 16:22 ET：285 场账本第一版独立审查给 REPLAN

- **正确部分：** 独立 reviewer 重新解析真实来源，确认 285 场赛程、284 个唯一映射和唯一缺失 `2024_22_KC_PHI` / event `17330`。canonical ledger 连续两次得到相同 SHA-256 `179d701a…a8c2`；6/6 原测试通过。
- **四个反例：** 第一版仍会接受一套完全伪造但自行重算 hash 的来源；没有解析 catalog payload，所以错误 event/slug 也能通过；输入多出 `dev_score` 会被静默丢掉；每行没有自己的来源承诺。故 task 已改名 `REPLAN · P0 285-game ledger review`，不能 freeze 或 admission。
- **修复动作：** 四个可复现反例已推回实现 owner，要求固定 canonical resolved path/hash、解析并验证 event 17330、拒绝额外与 Dev/Final 字段、增加逐行来源绑定，并为修复生成新的候选 ID；旧候选保留为 superseded，不改写成成功。
- **并行项：** outcome orientation 实现已经产出稳定快照，另一条可见 task 正做独立对抗复审。仍无联网、付费、正式数据入场、训练或 Git 发布。

### 2026-09-22 16:28 ET：账本第二版进入复审，空回传方向 task 被替换

- **账本修复：** 新的 `...-20260922-03` 候选没有覆盖旧候选。它固定 canonical resolved path/hash、解析 285 个 catalog event、严格要求 13 列输入 schema，并给 285 行加入可重算来源承诺。11/11 author tests 通过；Supervisor 把账本和方向两套测试一起运行，28/28 通过。原 reviewer 已重新进入 active turn，正在重放首轮四个反例；仍不能提前写 PASS。
- **方向实现：** source `fbe3b7e1…db4c`、test `5e6a50dc…78e9`；作者报告 17/17 focused 与 73/73 adjacent 通过，284 个 candidate receipts，event 17330 保持明确未定向。Supervisor 自己的合并测试也通过。
- **空结果处理：** 可见 orientation reviewer 的正式 review 与最小 final retrieval 连续两次结束但没有正文，已改名 `BLOCKED · P0 orientation review · empty`。没有把空结果当通过。fresh internal reviewer 已收到固定 snapshot 和对抗矩阵，正在独立复审。

### 2026-09-22 16:34 ET：285 场账本第二版独立复审通过

- **结论：** exact -03 ledger checkpoint 获 scoped PASS。独立 reviewer 重放首轮四个反例：完整替代来源树、matching-hash symlink、错误 event/slug、额外 `dev_score`/`Dev`/`Final` 字段全部被拒绝。
- **可复核结果：** 11/11 focused tests 通过；285/285 row commitments 与 source bindings 独立重算一致且唯一；两次 canonical build 与保存 artifact 逐字节相同。ledger SHA `1c12f539…5819`，receipt SHA `245d70bb…e38f`。
- **边界：** 这里只证明候选账本完整性。`admission_claim=false`；数据权利、provider publish/local receive 时间、方向校验、controlled release 与正式 Train admission 仍需各自通过。没有网络、付费、Dev/Final、commit 或 push。

### 2026-09-22 16:38 ET：方向校验替补独立复审通过离线范围

- **固定快照：** source `fbe3b7e1…db4c`、test `5e6a50dc…78e9`。替补 reviewer 跑过 17/17 focused、73/73 adjacent、11/11 ledger-adjacent 和 18/18 独立内存反例，全部通过。
- **结果：** 285 catalog events 生成 284 个 candidate-only orientation receipts；event `17330` 明确保持未定向，没有被推断修复。receipt-set digest 为 `abc24dd4…da70`。catalog/mapping/alias/token/slug/game-ID 的替换、冲突与反转都 fail closed。
- **边界：** 这是固定 bytes 的离线 PASS，不是发布或正式 admission。模块尚未进入 controlled source manifest，没有 non-test consumer；bytes-only 接口不能自己证明调用方 canonical path/symlink provenance。rights、provider provenance、Train receipt 和 protected split 仍是单独 gate。
- **任务可见性：** 原可见 task 两次空回传仍保留为 BLOCKED；替补 reviewer 的真实证据单独记录，未覆盖或美化空结果。

### 2026-09-22 16:44 ET：从四个离线 PASS 转入单一路径整合

- **新瓶颈：** Train receipt、v2 cursor、285 场 ledger 和 orientation 各自通过 scoped offline review，但还没有一个 production consumer 把它们连成同一条受控路径。新模块也没有全部进入 controlled source manifest；canonical path/symlink 和 check-to-use 保证分散在不同层。
- **编排：** 新建 `SUPERVISOR_P0_ADMISSION_INTEGRATION_2026-09-22-v1.json`。dispatch 和第一步 ready-step 机器闸门均通过。实现 owner 只可写一个 integration module、focused test、controlled manifest 和专属 log；稳定后才轮到 fresh reviewer，不能边写边自审。
- **目标边界：** 产物只能是 candidate-only integration receipt，event `17330` 继续未解决；rights、provider timing、正式 Train admission、release 和付费 Controller 均不由这一步解决。本轮没有联网、付费、fetch、Dev/Final、commit、tag 或 push。

### 2026-09-22 16:53 ET：候选入场 consumer 实现完成，转入独立复审

- **实现快照：** consumer `cf2e4562…21838`、test `46120084…0481`、controlled manifest `5f634549…deb6`；335 文件受控源码 digest `5d650ae3…ac5f`。它只打开 canonical no-symlink 文件一次、保留 bytes、核对 descriptor/path identity，再把相同 bytes 交给 ledger/orientation/receipt validators。
- **结果边界：** integration receipt `20e884ad…a345` 仍是 candidate-only：285=284+1，event `17330` 未解决；rights、provider、network/v2 execution、formal admission、Dev/Final 和 improvement 全部 false。
- **验证：** author 13/13 focused、95/95 combined；Supervisor 用同一固定快照重跑，结果同样 13/13 与 95/95。实现 evidence 已写入机器 plan，independent-review ready-step 通过。
- **现在：** fresh reviewer `capability_contract` 已收到固定三个文件哈希、controlled digest 和完整攻击矩阵。review 未回来前不写整合 PASS，不发布、不 admission、不联网、不付费。

### 2026-09-22 17:01 ET：独立复审找到两条整合绕过，立即 REPLAN

- **不是旧 task 卡住：** dashboard 里的两个 BLOCKED 可见 task 是历史空回传，不是当前执行路径；证据已由 replacement work 找回。两者现已归档，日志保留。
- **真实新 blocker 1：** 第一版 consumer 会接受重新计算 row commitment 后的 `provider_verified=true`、`network_access_authorized=true`、`formal_training_authorized=true`、`improvement_claim_allowed=true`。原代码只覆盖了 rights 与 Dev/Final 的部分别名，权限字段检查不够通用。
- **真实新 blocker 2：** 在读取过程中，把祖先目录短暂替换成指向同 inode hardlink 的 symlink、再在最后 pathname 检查前恢复，仍能通过。原因是 consumer 没有从 repo root 到文件一直持有完整 descriptor chain。
- **处理：** 独立 verdict 明确记为 REPLAN。两个反例已推回 implementation owner，要求新 source/test snapshot、通用权限升级拒绝、全祖先 descriptor chain 持有与 deterministic tests。旧 review 只适用于 `cf2e…21838`；正在变化的新 bytes 没有 verdict。修复前不发布、不 admission、不联网、不付费。

## 2026-09-28 — v0.1.25 tool-schema visibility repair is locally reviewed

- **Problem:** Paid D0 `market-rsi-v0124-gate1-controller-d0-20260928-01` returned exactly one tool call but paired `bounded_response_canary_proposal` with `max_documents_proposed=1`. The local validator correctly requires zero; the model-visible schema had not exposed that cross-field rule. The old ID remains terminal failed and non-reusable.
- **Single-layer repair:** Only the `bounded_investigation` tool-schema description now states the complete mode-dependent table. The frozen packet, semantic validator, parser/normalization, provider, budget, fetch, admission and training paths remain unchanged. Trusted code does not rewrite the model's value.
- **Verification:** The captured mismatch remains rejected; a fixture changing only `1` to `0` passes. Focused tests passed 48/48; the full suite passed 516/516 with 2 environment skips. Pinned rendering is 4,020 input tokens with a `$0.0389772` no-cache upper under the `$0.05` ceiling.
- **Independent review:** PASS with no blocking code finding. No provider call, credential read, fetch, data access, training, release, push or canary occurred. Publishing v0.1.25, running its zero-provider canary and any fresh paid ID still require separate authorization.
## 2026-09-28 — v0.1.25 integrated release candidate independently passed

- The authorized integration combines the architecture documentation and the one-layer tool-schema visibility repair on `codex/v0125-release-integration`. The trusted semantic validator is unchanged and the original invalid D0 response remains rejected.
- Fresh integrated checks passed: focused 48/48, full discovery 516/516 with 2 environment skips, `git diff --check`, JSON and secret/data-scope checks. The 339-file controlled-source digest remains `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`.
- Independent integrated review returned PASS after tightening one causal statement and generalizing user-specific paths in the public architecture document. Publication and remote verification are authorized; no zero-provider canary, provider call, fetch, data admission or training is authorized in this step.
## 2026-09-28 — v0.1.25 published and independently verified

- `main` and annotated tag `market-rsi-protocol-v0.1.25` were atomically pushed to the standalone user repository at release commit `ed4048e55096b763ba763526e768057b5180cdeb`; tag object is `67b8e4a88e22c1f00e60850f521b26282517d682`.
- Supervisor verification and a separate credential-free anonymous-clone review both passed. The remote release contains exactly 339 controlled files with digest `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4`.
- This release did not run a canary, call a provider, fetch data, read or admit Train/Dev/Final, or train. The next step is a separately authorized v0.1.25 zero-provider canary.

## 2026-09-28 — v0.1.25 zero-provider first canary passed independent review

- The one authorized run `market-rsi-v0125-gate1-first-current-source-20260928-01` completed once through the production CLI and Supervisor parent. It is permanently consumed and will not be retried.
- Receipt SHA-256 `187c819a42a90361956145017d34a87f788f83026decfdfa5adc8d3b9e47671f` binds annotated v0.1.25, release commit `ed4048e55096b763ba763526e768057b5180cdeb`, tag object `67b8e4a88e22c1f00e60850f521b26282517d682`, 339-file controlled digest `c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4` and runtime digest `1faf044ade2390b0d4cdbc18605bb8851f84fb57951849400bed92e0025c83a3`.
- Independent review and Supervisor verifier replay passed all 30 evidence hashes and terminal cleanup. Provider calls and real provider cost were zero; no public fetch, formal data admission, sealed Train/Dev/Final access, compiled task/plan or training occurred. The isolated `$0.00005103` metering is synthetic only. The authoritative paid journal remained unchanged.
- This is infrastructure evidence, not a Controller-authored research decision or prediction experiment. The next discriminating step is one separately authorized paid v0.1.25 D0 under a fresh permanent ID, followed by independent review before any separately authorized fetch.

## 2026-09-28 — paid v0.1.25 D0 authorized, held before claim on a budget-allocation mismatch

- The user authorized one paid D0 under fresh ID `market-rsi-v0125-gate1-controller-d0-20260928-01`, at most one sample, no retry, no fetch, no Train/Dev/Final and no training. Two independent read-only preflights ran in parallel; neither read the credential, claimed/reserved the ID or called a provider.
- Release/source/runtime/canary/packet bindings and the dormant production argv passed. Pinned local encoding is 4,020 input plus 1,600 maximum output tokens, exact request upper `$0.0389772`.
- The production outer nevertheless hard-codes a `$0.05` setup reservation. Authoritative setup availability is `$0.044036812`, so it is short `$0.005963188`. The ID remains unused, `active_cycle=null`, run/claim paths are absent and exact process/container checks are clear.
- The budget implementation requires explicit authority for an append-only bucket allocation transfer. Execution is therefore held before any mutable or paid boundary. After authority, transfer at least the shortfall from an eligible non-Final bucket, bind the paid authorization in durable state, rerun all preflights and invoke the exact ID once only.

## 2026-09-28 — v0.1.25 operational D0 passed and closed

- **Goal:** Execute and independently review exactly one authorized v0.1.25 Controller D0 without granting fetch, data-admission or training authority.
- **Actions:** Simulated and appended the authorized `$0.006` `repair`-to-`setup` allocation transfer; rebound the durable decision state; ran two independent launch rechecks plus a final Supervisor replay; invoked the production parent once; independently audited the terminal run, budget, state and cleanup.
- **Why:** The prior v0.1.24 response exposed a model-visible schema gap. v0.1.25 repaired only that interface, and this single live D0 was the cheapest discriminating test of whether the model could now return one valid scientific scope choice.
- **Actual learning:** The model returned a valid `scope_only_non_executable` source-scope decision. It selected the registered official Polymarket market-scoped-trade response class for private research, future role `unassigned_candidate`, descriptive/no-forecast semantics and one first-party-document-review proposal. This demonstrates valid D0 contract use, not data access or prediction gain.
- **Outcome:** **Improved operationally; no experiment result yet.** Exactly one terminal provider sample used 4,020 input, 511 output and 0 cached tokens at metered `$0.02574585`; no retry, catalog, fetch, purchase, Train/Dev/Final access, data admission, training or evaluation occurred. The permanent ID is consumed.
- **Evidence:** `SUPERVISOR_GATE1_V0125_D0_2026-09-28-v3.json` passes the full resolve gate. Execution evidence SHA-256 is `c6166ea807fbae2ccdb8d85f9a90ad240b8965073a6ef11e0fb14daf6e3e2dc3`; independent terminal-review log SHA-256 is `b8d76898f8f7e68673b66c8d039fe25367c009f4210e24c0185695596f138857`. Budget head is `e2566dff000fd3a91025734107a9438ca14bcd3860f05b2d6796b1d834e70a34`; post-review decision/state hashes are `a727445ba25b372eae71e23a21a8f8a0c749435b1b955a7393632e11a8e5f417` / `3b4eff7c056452ddc319333541e6a8e24902e0752ca650d400fb136ba3bc86ca`.
- **Approximate effort:** One bounded allocation/state preparation, two parallel read-only audits, one paid sample and one independent terminal audit; no retry.
- **Remaining blocker:** There is no reviewed executable bridge from the prospective D0 decision to one exact request manifest, and no real Train catalog or source-rights/admission evidence. Fetch remains separately unauthorized.
- **One next action:** Audit and plan the smallest offline D0-to-exact-request bridge for the selected fixed official documentation page. Any source change needs targeted/full tests and independent review; publication/canary and actual fetch each remain separate authorization gates.
- **Confidence:** High for the operational D0, cost, closure and cleanup facts; low that the selected source will solve multi-season data coverage until an authorized document/source investigation returns evidence.

### 2026-09-28：D0 到 exact-request 的离线桥接完成独立终审

- **Goal:** 只把唯一已复核 D0 选择编译成确定的非执行文档请求计划，不联网、不把 scope 决定升级为 fetch 权限。
- **Actions:** 两位独立审计先分别确认 decision/capability 缺口和 fetch/watchdog/rights 边界；Supervisor 随后加入纯离线桥接与对抗测试，并把源码和测试纳入受控发布清单。另一位 reviewer 用真实不可变 D0 制品连续编译两次并独立复测。
- **Outcome:** **PASS as unpublished offline release candidate.** 固定 request-plan hash `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`；341-file candidate digest `c80531648d07f83ff73c1c70c3a8c0d5fd5d02459bb1957c875959daa51faee2`。focused 12/12、pinned-runtime full 516/516（2 个既有 skip）和非作者终审通过。
- **Actual learning:** D0 的 opaque pair 现在只能通过 code-owned injective mapping 到完整 `polymarket_official_trades` registry/capability；caller 无法提供 URL、参数、headers、limits、retry 或权限。现有 fetch/admission schema 不能直接消费 bridge 输出。
- **Boundary:** 没有 provider/source contact、credential、network、external bytes、retention、catalog/Train/Dev/Final、data admission、training、evaluation、commit/tag/push/release/canary。所有这些权限仍为 false。
- **Next blocker:** 先另行授权发布新版本，再另行授权该版本的 fresh zero-provider canary。实际文档/public-data fetch 仍须其后的独立 fresh-ID 授权。
- **Evidence:** integration/test/review logs SHA-256 分别为 `7208847b04ebea6e8de64873e50b646dce78584329ef2c3fdadc9297611c9c3d`、`e050d1828ac70f11aab1c7667d09e6e69b536417177d949d0c517b160e4143ad`、`10dceb089ad0c4b59b0c0ced82a0962fbe3e9ed13e2f324467f1c3715f825bb1`。

### 2026-09-29：赛中 Discovery 小批次完成 4/4，raw market 仍为 incumbent

- **执行：** 在已有 opened-Train 权限内完成 scheduler-v2 两代、四次真实尝试；实际探索/利用为 2/2，约 49 分钟，零 provider、零联网、零费用。批次因 `max_attempts_reached` 正常关闭。
- **同信息结果：** raw market Brier/log loss `0.1419525290/0.4296707847`；market-only Logistic `0.1454823125/0.4399219725`；market + static state/PBP Logistic `0.1606809902/0.4711973193`。固定 PBP 表示没有显示增量，但不能否定整类信息。
- **研究闭环：** prior-play signal、market-uncertainty split 和 120 秒 pre-anchor market momentum 都得到有效但 inconclusive 的证据；nested shrinkage 在预注册收敛门槛 fail closed，不算科学反证。信用 `[1,0,1,1]` 实际影响下一代 parent 选择，所有 REVERT 只是不更新 incumbent。
- **当前路线：** 下一批保留 raw-market incumbent 和 market-momentum bounded follow-up 两条，不机械补第三条。momentum 总体方向与 3/4 folds 为正，但日期/周区间跨零；还不是概率改善结论。
- **独立终审：** 27 条 journal 精确重放 PASS，head `8b2339a8…17845e`，state `3204552e…ed7c3`；4/4 branches 均 feedback-ready，权限边界未扩大。终审日志 SHA `8fb61d058e2b9feefed2a977e9cc5fd047205c9e3ca2e925f138e82f155c6935`。
- **仍未证明：** untouched OOS、实时可用性、PnL、多域迁移，以及固定研究流程和可自迭代流程的匹配预算 A/B。详细报告见 `INGAME_DISCOVERY_SMALL_BATCH_REPORT_2026-09-29.md`。

### 2026-10-01: Preserve the working research loop; optional small-step controls

- **Goal:** Build on September 15's working research capabilities, repair the demonstrated final-slot scheduler dead end, and constrain harness/researcher evolution without adding gates to ordinary legacy research.
- **Changes:** Added an opt-in `final-singleton-v1` policy for fresh batches; added pure small-step transitions in the existing co-evolution module and durable events in the existing Discovery journal. Separate harness/researcher identities, fixed context, exact write scope, one pending change, reviewed idle-boundary acceptance/rollback and execution-pair/memory bindings are checked. Legacy defaults remain unchanged.
- **Actual verification:** 75 focused tests passed. Journals generated by the saved pre-change implementation replayed to identical complete v1/v2 states and hashes under the changed implementation. Synthetic integration completed two parent-pair attempts plus a final singleton under a reviewed pair and rolled back without erasing attempts or feedback.
- **Outcome:** Local implementation ready for independent integration review; not published, not activated in a live research batch, not autonomous self-evolution or prediction gain. Review evidence remains a trusted-supervisor responsibility; hashes/identity strings are not OS isolation or independent proof of test truth.
- **Boundaries:** No model/provider/network/data acquisition, protected-data read, empirical training, release or Git publication. Existing experiment/budget/global-state artifacts and scientific `RESEARCH_STATE.md` remain unchanged. Unrelated dirty work preserved.
- **Next action:** Review the scoped diff, then bind the actual existing worker's measured pair and memory identities to the new opt-in claim path before a separately bounded operational batch. Do not rebuild the research engine.
- **Evidence:** `SMALL_STEP_COEVOLUTION_2026-10-01.md`; `test_micro_evolution.py`; `test_continuous_discovery_small_steps.py`; audit worktree `research/harness_continuity_audit_20261001/legacy_compatibility_final.json`.

### 2026-10-01: User-requested local version-control checkpoints

- **Goal:** Preserve all pending project source, tests, plans and curated reports while separating the earlier research work from the new small-step controls.
- **Action:** Created `codex/market-rsi-coevolution-checkpoint-20261001` without moving `main`. Baseline `793c30248b085edd673fd95472db91d2d4efe973` captures the earlier 247-file change set; the new control implementation is a separate follow-on commit. The verified pre-control scheduler was staged from saved bytes without altering working files.
- **Verification:** The 75 focused tests passed again. Python/JSON syntax and credential-pattern checks passed for the pending source/report inventory. Historical Markdown whitespace warnings are preserved. This is not a new independent review of every baseline file.
- **Scope:** Local Git only, no push/tag/release/live experiment. Raw data, credentials, runtime files, budget/global-state ledgers and raw run artifacts are excluded. Task-local reports and audit evidence use a separate research-records branch in the existing task repository.
- **Next:** The live worker binding and bounded operational trial remain unperformed; checkpointing does not authorize deployment or establish autonomous improvement.

### 2026-10-01: Standing checkpoint rule for replayable history

- **User direction:** Make a Git checkpoint at every meaningful stage going forward, not just this one-time preservation pass.
- **Parent/source:** `baa6b36`, repository `/Users/estelle/Developer/market-rsi`, branch `codex/market-rsi-coevolution-checkpoint-20261001`.
- **Changed scope:** Project `AGENTS.md` and Supervisor procedure now require bounded source commits, result/failure commits, replay provenance, preservation of rejected candidates and append-only corrections. This progress entry and the human-direction log record the change.
- **Verification/outcome:** Scoped documentation diff reviewed; `git diff --check` passed. No executable behavior changed. Runtime/model/data/configuration/seed/output identities are not applicable to this policy edit; no empirical replay is claimed.
- **Evidence:** Main source/control checkpoints `793c302` and `baa6b36`; task-repository design/evidence checkpoints `81d0542` and `bd4a0ac`. The commit containing this entry is the policy checkpoint.
- **Boundary/next:** No new hook, service, release gate, paid call, experiment or deployment. Apply this rule to the next existing-worker integration change and its subsequent verification.

### 2026-10-03: Attributable small-change rule added

- **Goal:** Make every co-evolution checkpoint show what changed, where it changed, who proposed it and whether the evidence concerns prediction, Harness operation or researcher capacity.
- **Rule:** The governing instructions now require separate `K/M/C/H/R` identities, one declared `C/H/R` axis and one named effect for an attributable comparison, exact allowed/protected paths, measured-diff and runtime verification, fixed resource ceilings, matched replay, independent review, idle activation and one-step rollback. Composite Discovery changes remain allowed but are labelled `COMPOSITE_UNATTRIBUTABLE`.
- **Smallness:** Causal and authority blast radius controls acceptance. More than two production modules or about 200 changed lines triggers splitting or an explicit inseparability review; it is not a safe-harbor threshold. Any permission, protected-data, evaluator, model/runtime, network, budget or authority change outside the contract fails closed.
- **Evidence:** Each trajectory step records exact commits/files, before/after identities, triggering evidence, execution/review receipts, prediction and capacity metrics, resources, decision and evidence level `L0` through `L5`. Final reports separate predictor, Harness and researcher-capacity conclusions.
- **Verification/outcome:** Documentation-only policy change; scoped diff and whitespace checks required before the local checkpoint. No runner, evaluator, data, experiment, provider, release or deployment changed. Apply the rule first to the worker-binding checkpoint and the bounded co-evolution pilot.

### 2026-10-03: Immediate implementation dispatched

- User requested immediate implementation and persistence for five hours. Actual clock start is 19:10:37 UTC; outer end 00:10:37 UTC on October 4. A nested pilot keeps the earlier small scope: at most three prediction attempts, twelve fits, ninety minutes from first pilot action. Engineering does not consume prediction fits.
- Starting source: `26d7121`, clean current Developer checkout; historical September 29 scores and rules remain unchanged. New jobs use reviewed trusted host code, not a claimed arbitrary-code sandbox. Protected Dev/Final, external fetch, paid providers, push/release and promotion remain closed.
- Registered independent Controller, candidate researcher and reviewer before assignment. Controller froze freshness and a distinct pre-play possession-pressure branch from actual evidence; next-generation scientific choice is pending verified feedback. Exact serving model version unavailable and not invented.
- Existing feature receipts independently covered all 193 materialized games; baseline 87-row metrics and complete 195-event denominator reproduced. No real new fit yet. Worker adapter synthetic suite passed 82 checks, including nine new adapter checks; initial test fixture used incompatible v1 and was corrected to the existing v3 policy. No production scheduler/scorer modification.
- First checkpoint preserves scoped contracts/registration. A separate source checkpoint will isolate worker binding and tests, followed by source-frozen candidate runs and result checkpoints. No empirical or researcher-capacity gain is claimed from engineering.

### 2026-10-03: H worker-binding source checkpoint

- Parent `c6661a9`; change axis H, component feedback delivery. Exactly one new production module `opened_train_discovery_worker.py` (164 lines) and its synthetic test module. Existing scheduler, micro-evolution controls, data readers, candidates and scorers unchanged. Human-directed integration, not system self-evolution.
- Effect: reviewed request verifies exact source/HEAD/runtime/memory, conservatively reserves fits, atomically claims before spawn, caps two jobs, runs one-thread candidate, polls child RSS, kills group at timeout/RSS excess, hashes outputs, and records execution terminal in existing scheduler. A restart refuses a claimed ID; unresolved interrupted claims require independently reviewed closure, not automatic retry.
- Verification: 127 relevant tests passed; independent reviewer reproduced 47 focused tests. Initial broader invocation used two nonexistent test module names and failed import, then corrected to actual `tests.test_minimal_probability_contract`; no scoring source change. Final adapter SHA `512176a1cb84ad81383e7e890abf9b2058ee66e7a8a643e3549fd5ec4c0db360`; tests SHA `00f4bd421d8fe0098d24bfa2bb092231da71b5cc5b9580a85e1044e76119c60e`.
- Limits: trusted host code only, not network/arbitrary-code isolation. Sampled parent RSS is not OS-hard or aggregate-descendant memory enforcement. Child success is not independent scientific acceptance. Evidence L1 and matched synthetic terminal/restart checks; opened-Train operational L3 remains pending.
- Runtime: Python3.12.3 binary `80ee2dd97bc26259d4e30853336f72ad38aa4aa0531bb196cc444d899422689d`, numpy1.26.4/scipy1.14.0/sklearn1.6.1, thread cap1 and hashseed0. No fit/provider/data acquisition. Next: freeze candidate source and data/memory identities, run reviewed pilot.
