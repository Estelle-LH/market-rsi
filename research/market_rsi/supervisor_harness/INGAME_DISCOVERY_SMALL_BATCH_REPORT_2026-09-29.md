# Market RSI 赛中 Discovery 小批次报告 — 2026-09-29

## 结论摘要

这次升级保持在小范围：没有重构评分器、数据边界或整套 harness，而是在现有
Supervisor 上增加全局 2–3 分支池、研究谱系、独立研究信用和约 30% 探索预算，
然后真实运行了一个两代、四次尝试的小批次。

批次 `market-rsi-ingame-discovery-v3-20260929-02` 于
`2026-09-29T21:22:21.803851Z` 开始，在 4/4 尝试后于约
`2026-09-29T22:11:12Z` 结束，停止原因为 `max_attempts_reached`。实际消耗约
49 分钟、零 provider、零外部抓取、零付费。四次尝试中三次产生有效科学证据，
一次在冻结的优化器收敛门槛处 fail closed；没有读取 protected Dev/Final，
没有发布、promotion 或训练权限扩大。

当前赛中 incumbent 仍是同一 87 场配对检查上的 decision-time raw market：
Brier `0.1419525290`，log loss `0.4296707847`。本批没有生成可替换它的新概率
候选；所有 `REVERT` 都只表示“不更新 incumbent”，不表示删除研究分支或回滚
代码。赛前任务的独立 incumbent 仍是 `MarketRecencyWeightedCompositePath-v3`，
两个任务的分数不得混用。

## 1. 实际检查的代码、状态和记录

本轮不是依据旧状态文档启动。Supervisor 先检查了当前 dirty checkout、v0/v1
真实 artifacts、两次独立结果复核、scheduler-v2 的 append-only journal 和精确
批次 snapshot。

最终 scheduler 状态：

| 字段 | 最终值 |
| --- | --- |
| attempts | `4/4` |
| pool generations | `2` |
| exploration / exploitation | `2 / 2`，实际探索比例 `50%` |
| failed attempts | `1` |
| branch stages | 四条均为 `controller_feedback_ready` |
| incumbent updates | `0` |
| research credits | `[1, 0, 1, 1]` |
| journal | `27` 条，head `8b2339a8dcaad1d1fffd86d1dd2a228a8fe370a7ec31048719e8cb584c17845e` |
| state SHA-256 | `3204552e723db4d45d680d61b21d16d8dca656d0aa48fc4178de06f2bd8ed7c3` |
| stop | `max_attempts_reached` |

持久批次目录位于非云盘、非临时目录：

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/continuous-discovery-batch-20260929-02`

## 2. 最小调度升级

`continuous_discovery_batch.py` 的 v2 路径在不改变既有 v1 记录重放的前提下加入：

- 一个全局 2–3 条分支的 active pool，而不是每个父节点机械保留多个子节点；
- `research_parent_sha256` 与 `comparison_incumbent_sha256` 分离，实际研究父分支和
  性能比较对象不会再混淆；
- REVERT 候选仍可作为研究父分支；archive parent 可跨批导入，但只有 hash-bound
  研究身份，没有数据或执行权限；
- 默认 30% exploration reserve，允许 20–40% 范围内有理由调整；本批实际为
  2/4，即 50%，因为全局两员池每代至少保留一条方法不同的 exploration 路线；
- 研究信用 `0/1/2` 与预测分数完全分离，必须绑定预注册问题、规则、authority
  snapshot、结果 artifact 和独立 review；
- credit 1 只允许一次 bounded follow-up；credit 0 的无效运行进入 cooldown，
  不能充当科学反证或研究父分支；
- Controller feedback packet 带入研究信用、剩余 follow-up、方法差异和资源提示，
  所以下一轮选择实际受到信用影响，而不是只写一条日志；
- protected score、incumbent 更新规则、Dev/Final、网络、provider、发布和 promotion
  边界没有改变。

该调度器定向测试为 25/25 PASS；独立最终复核为 PASS。旧 v1 32 条记录可以精确
重放。这里证明的是状态机和边界行为，不是预测收益或自迭代收益。

## 3. 同信息赛中数据对照

v0 使用固定的 2025 NFL moneyline Train cohort：195 场原始事件，193 场完成赛中
materialization，2 场按预注册原因排除；chronological checks 共 87 场、20 个
赛程日、7 个比赛周。每个 arm 使用同一场比赛、同一决策时点、同一标签和同一
检查 mask。

| Arm | 信息 | Brier | Log loss | 相对 raw market Brier | 解释 |
| --- | --- | ---: | ---: | ---: | --- |
| decision-time raw market | 当时市场概率 | `0.1419525290` | `0.4296707847` | `0` | 赛中 incumbent |
| market-only Logistic | 相同市场概率，普通固定模型 | `0.1454823125` | `0.4399219725` | `+0.0035297835` | 模型/校准未改善 |
| market + static state Logistic | 市场 + 当时可用比赛状态/PBP | `0.1606809902` | `0.4711973193` | `+0.0187284612` | 对 market-only 为 `+0.0151986776`；该固定表示未显示数据增量 |

因此当前证据支持的表述是：在这套固定 Logistic 表示和 Train Discovery 检查上，
static game-state/PBP 没有带来可用的增量信息。它不支持“PBP 整类信息无效”，也
不支持实时可部署优势，因为现有来源只能证明历史 event time，不能完整证明
provider publish/local receive time。

## 4. 四次真实尝试

| # | Allocation | 研究问题 | 执行结果 | KEEP/REVERT | 信用与路由 |
| --- | --- | --- | --- | --- | --- |
| 1 | exploration | prior-play success differential 是否与 market residual 有增量方向 | 有效但指标混合；Pearson `0.0314`、Spearman `0.1477`，log alignment 为正、Brier-logit alignment 略负，分组区间跨零 | REVERT | `1 / inconclusive / bounded_followup` |
| 2 | exploitation | nested shrinkage 能否挽救 static-state offset | 在 lambda `4` 的冻结 gradient 门槛失败；无 prediction、scorecard 或科学结论 | REVERT | `0 / invalid / cooldown` |
| 3 | exploitation | 尝试 1 的方向冲突是否由 market uncertainty regime 解释 | 低不确定性 log alignment `+0.004831`，高不确定性 `-0.003532`，contrast `+0.008362`；但仅 2/4 fold 为正，日期/周区间均跨零 | REVERT | `1 / inconclusive / bounded_followup`；本批不再延伸 |
| 4 | exploration | 决策时点前 120 秒 market-logit momentum 是否有 residual 方向 | Pearson `0.098585`、Spearman `0.079843`、log alignment `+0.011166`、Brier-logit `+0.001282`，3/4 fold 为正；但日期/周 log interval 下界仍为负 | REVERT | `1 / inconclusive / bounded_followup` |

### Attempt 3 的完整不确定性口径

- 87 场完整 mask：低不确定性 51、高不确定性 36；没有删行或插补。
- low-minus-high log contrast 的日期区间：
  `[-0.0060316279, 0.0281757556]`。
- 周区间：`[-0.0055000806, 0.0222054989]`。
- 10,000 次 complete-group bootstrap 均有效，但两个下界都没有超过零。
- 结论严格为 `PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_INCONCLUSIVE`，不是 support。

### Attempt 4 的完整市场路径口径

- `p_now` 复用 v0 的严格 prior、home-oriented、同秒 size-weighted probability。
- `p_ref` 是 `floor(decision_time)-120s` 之前的最新成交，reference age 必须
  `(0, 300]` 秒；87/87 全覆盖，未删行或插补。
- log-alignment 日期区间：`[-0.0048385560, 0.0289289148]`。
- 周区间：`[-0.0017025916, 0.0246890415]`。
- 10,000 次 complete-group bootstrap 均有效。
- 结论严格为 `PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_INCONCLUSIVE`。它是当前最值得
  一次小额后续的非 PBP 路线，但还不是概率候选，也不是预测改善。

## 5. 研究信用确实影响了调度

这不是事后给分：

1. Attempt 1 的 credit 1 使 Attempt 3 成为它唯一的 bounded follow-up；两者的
   parent hash 相同，而比较对象始终是 raw-market incumbent。
2. Attempt 2 的 credit 0 使该运行进入 cooldown；Controller 没有把失败的 optimizer
   当成“信息无效”证据，也没有让它成为下一代 parent。
3. 已归档的 v0 state branch 有独立 credit 2/refute/branch 身份，因此可以产生一个
   方法正交的 market-path Attempt 4，而不是被 REVERT 删除。
4. Attempt 4 获 credit 1，因此下一批可给一次小额、冻结的概率化 follow-up；它的
   资格不提高 Brier、不抵消退步，也不构成 incumbent 更新。

同一发现没有重复计分。阅读、代码量和日志长度本身均未获得信用。

## 6. 当前 active pool、archive 和谱系

批次已经关闭，所以 runtime `active_attempt_ids=[]`。研究层面下一批建议只恢复两条，
不机械凑满三条：

1. **Incumbent：** `InGameWinProbabilityTrainDiagnostic-v0-raw_market`。它是性能比较
   对象，不从研究信用获得任何分数加成。
2. **潜力路线：** `InGamePreAnchorMarketMomentumResidualAudit-v3`。它来自 archived
   v0 negative state branch，而不是来自 incumbent；理由是方法上与 PBP/static-state
   不同，已有正向但不确定的原始信号证据，且一个小额概率化实验可直接回答它是否
   转化为 Brier/log-loss 改善。

`InGamePriorPlaySuccessMarketUncertaintyAudit-v3` 保留在 archive 中。它不是被删除，
但原 credit-1 父路线的单次 follow-up 已经完成；除非提出新的可区分机制，不继续
对同一阈值和同一问题追加预算。所有 runner、结果、失败原因和独立 review 都保留，
可在出现新证据时恢复。

## 7. 数据收益、模型收益和机制收益的边界

### 当前有证据的部分

- **模型收益：** 在固定同信息比较中，普通 market-only Logistic 比 raw market 差；
  当前没有发现模型变换收益。
- **PBP 数据收益：** 固定 static-state Logistic 明显变差，prior-play signal 显示一些
  异质性但不稳定。当前没有支持 PBP 增量收益。
- **市场路径数据收益：** 120 秒 pre-anchor momentum 的原始方向在 aggregate 和 3/4
  folds 为正，值得一次 bounded follow-up；分组区间跨零，所以尚未支持稳定增量。
- **研究流程功能：** REVERT 可继续当 parent、credit 影响下一代、探索预算生效、
  谱系和恢复正确保存。这是工程和流程证据。

### 尚无证据的部分

- 没有证明 Market RSI 自迭代机制优于同一个 Astra 的固定研究流程。
- 没有运行匹配预算的 A/B 机制 pilot，更没有独立重复；不能把本批任何发现归因于
  self-evolution。
- 没有 untouched OOS、Dev/Final 或未来结算事件结果。
- 没有实时可用性、交易可执行性、PnL、多域迁移或正式论文结论。
- 没有证明 PBP 整类信息无效，也没有证明 market momentum 可形成更好概率预测。

## 8. Controller 实际能力与限制

当前已实际可用：已授权本地 Train 分析、代码修改、真实小实验、固定分组 bootstrap、
失败恢复、独立 review 和 append-only 反馈。真实文献检索/原文阅读的代码路径存在，
但本批 `network_allowed=false`，也没有新的网络 canary；因此不能声称已具备或使用了
实时全文阅读。已有本地摘要目录明确不算全文阅读。

## 9. 下一小批建议

下一批仍用 2 条 research pool、相同 30% 左右 exploration 起点和原评分边界：

1. 用固定、低自由度的 market-offset probability model 把 120 秒 momentum 加到
   `p_now` 上；训练预算、mask、fold、seed 和 penalty 预先冻结。
2. 同时保留 raw market incumbent；只在相同 87 场、相同时点上比较 Brier、log loss、
   calibration、4 folds 和 date/week grouped intervals。
3. 如果概率化 follow-up 不改善或方向翻转，就把该确切 momentum 路线停止并保留
   反证；不要尝试多个 lag 后挑最好。
4. 等赛中数据增量路线稳定后，再做 matched research-mechanism pilot：A 固定流程与
   B 可修改流程使用同一 Astra 版本、初始记忆、工具、pool capacity 和资源预算；
   两组都允许多分支和多次训练。探索信用的有/无激励另做消融，不与 A/B 同时改变。
5. 独立确认仍需在接触结果前冻结候选规则，并在后续未参与选型或未来才结算的比赛上
   评估。日常 Train Discovery 不必等待正式显著性或未来数据。

## 10. 关键证据

- Scheduler v2 final rereview：
  `AGENT_LOG_CONTINUOUS_DISCOVERY_RESEARCH_SCHEDULER_V2_FINAL_REREVIEW_2026-09-29.md`
- Controller capability/credit audit：
  `AGENT_LOG_MARKET_RSI_CONTROLLER_RESEARCH_CAPABILITY_CREDIT_AUDIT_2026-09-29.md`
- Batch initialization review：
  `AGENT_LOG_INGAME_DISCOVERY_V3_BATCH_INITIALIZATION_STATE_REVIEW_2026-09-29.md`
- Generation-1 Controller：
  `AGENT_LOG_INGAME_DISCOVERY_V3_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md`
- Generation-2 Controller：
  `AGENT_LOG_INGAME_DISCOVERY_V3_GENERATION2_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md`
- Attempt 3 result review SHA-256：
  `321ffc11c8e71114071bc928e46251b7b85ca07b2f63096597503d4c1cf7d2ab`
- Attempt 4 result review SHA-256：
  `48080a2ccaa188673d7a2e29bc47bb10c1761e3bfc61aab5905b29b95e5a3079`

所有科学结论都属于反复查看的 opened-Train Discovery。工程完成、研究信用和候选资格
都没有被写成预测改善或正式自迭代成功。
