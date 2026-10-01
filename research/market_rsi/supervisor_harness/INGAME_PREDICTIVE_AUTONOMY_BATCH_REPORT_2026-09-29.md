# Market RSI 赛中自主预测迭代报告 — 2026-09-29

## 一句话结论

闭环跑通了，预测没有过门槛。Controller 根据已核验反馈改变后续候选，两个候选实际完成训练、逐样本预测和独立评分；最终没有替换 raw-market incumbent。本批证明的是**自主优化预测器的闭环可运行**，不是研究流程自修改，也不是自迭代机制优于固定流程。

## 1. 批次范围与实际消耗

- 执行窗口：`2026-09-29 18:19:47–19:06:08 EDT`，约 46 分钟，早于 20:00 截止且低于 90 分钟。
- 尝试：3 次；真实 scored prediction runs：2 次；pre-fit invalid：1 次。
- 训练：8 个 chronological outer fits；0 retry；0 control refit。
- 输出：每个有效候选 87 条逐比赛预测，共 174 条 candidate prediction rows。
- 评估：同一 87 场、20 个赛程日、7 个比赛周，fold sizes `26/16/28/17`，同一标签、时点、mask、scorer 和 seed。
- 权限：resident opened Train only；0 provider、0 network、`$0`；未读 Dev/Final；无发布、promotion 或部署。
- 并发：第一代两个独立候选的实现/预审并行；候选完成后立即复核并反馈。第二代候选在收到第一代真实反馈后才选择，不把预先并行搜索冒充连续迭代。

批次使用两个持久状态目录。主 v2 批次 `market-rsi-ingame-predictive-autonomy-20260929-03` 保存第一代两条分支，最终 state SHA 为 `e4065dc0842ed332435ded1718a032242bcb06b60f44ae5bef272ec48c0311e0`。它在 bookkeeping 上仍是 `2/3`、无 active attempt、`stopped_reason=null`，并未被错误描述为正式关闭。原因是 v2 在只剩一个 attempt 时按设计不给单成员 global-pool slot；Supervisor 没有改 harness，而是使用已有 v1 单槽恢复批次 `market-rsi-ingame-predictive-autonomy-recovery-20260929-04` 原样绑定 Controller 的第二代选择。恢复批次在 `1/1` 后正式关闭，最终 state SHA 为 `02f9f2f6aad5748954af60a23b5feeed28592785b3f660be8b9d1a68e9b5d44a`。因此是三次尝试组成的整体研究工作已经完成，不是两个 scheduler batch 都显示 closed。

这是一次实际人工编排介入，但没有替 Controller 选择算法、改评分或放宽边界。没有用户逐轮指导。

## 2. 简洁结果表

数值均为 repeatedly inspected opened-Train Discovery；loss 越低越好。

| Arm / attempt | 实际运行 | Equal-event Brier | Log loss | Candidate − raw Brier | Candidate Brier wins vs raw | 决定 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| raw market incumbent | frozen comparator | `0.1419525290` | `0.4296707847` | `0` | — | incumbent |
| ordinary market-only Logistic | frozen comparator | `0.1454823125` | `0.4399219725` | `+0.0035297835` | — | ordinary reference |
| v0 market + static-state parent | frozen comparator | `0.1606809902` | `0.4711973193` | `+0.0187284612` | — | archived negative parent |
| A1 `PreAnchorMomentumOffset-v4` | **0 fits**；mandatory coverage failed | — | — | — | — | invalid / cooldown / REVERT |
| A2 `IdentityAnchoredCalibration-v1` | 4 fits；87 predictions | `0.1436504644` | `0.4335652209` | `+0.0016979354` | `0/4` | refuted / stop / REVERT |
| A3 `PriorPlaySuccessUncertaintyOffset-v4` | 4 fits；87 predictions | `0.1419536874` | `0.4296330177` | `+0.0000011584` | `1/4` | refuted / stop / REVERT |

A3 几乎与 raw market 持平：Brier 略差 `1.16e-6`，log loss 略好 `3.78e-5`。但冻结规则要求同时胜过所有 comparator、至少 `3/4` raw-Brier fold wins，且日期和周的 paired Brier interval 上界都低于零；它没有满足这些条件。

### 四个时间块的 Brier

| Arm | Fold 1 (26) | Fold 2 (16) | Fold 3 (28) | Fold 4 (17) |
| --- | ---: | ---: | ---: | ---: |
| raw market | `0.1244784311` | `0.1729635462` | `0.1493726804` | `0.1272693543` |
| ordinary | `0.1306171088` | `0.1758954959` | `0.1518059167` | `0.1291778095` |
| A2 identity calibration | `0.1272499372` | `0.1761018058` | `0.1502581613` | `0.1273079194` |
| A3 prior-play stratified | `0.1244817851` | `0.1729278012` | `0.1493902333` | `0.1272748847` |

A3 candidate-minus-raw Brier 的 10,000-draw complete-group intervals：

- 20 个 schedule dates：`[-0.0000186924, +0.0000224469]`；
- 7 个 observed game weeks：`[-0.0000177210, +0.0000222824]`。

两个区间都跨零。它在四折 Brier 中只赢 raw market 的第二折；对 ordinary 则四折全赢。这个结果支持“该候选优于普通基线”，不支持“该候选优于市场”。

## 3. 可核查的反馈依赖轨迹

| 阶段 | 谁提出 | 进入时的证据 | 具体修改 | 执行与结果 | 如何改变下一步 |
| --- | --- | --- | --- | --- | --- |
| Generation 1 / A1 | scientific Controller | 既有 120 秒 momentum audit aggregate 正向、3/4 folds 正向但 grouped intervals 跨零 | 固定 raw-market logit 为 offset，只拟合 intercept + standardized momentum；冻结 300 秒 staleness | pre-score 检查发现 3 个必需 fit games 的 reference age 为 `334/419/612s`；0 fits、0 predictions | exact route invalid/cooldown；不得删行、插补、改 lag 或放宽 staleness |
| Generation 1 / A2 | scientific Controller，与 A1 独立并行 | ordinary market-only Logistic 差于 raw market，需要区分校准损失与新信息损失 | 用 penalty 16 把 market-only calibrator 锚定在 identity map | 4 fits/87 predictions；胜 ordinary，但 Brier/log loss 均输 raw，0/4 raw-Brier wins | exact calibration route refuted/stop；不再花预算微调 penalty |
| Generation 2 / A3 | scientific Controller，在 A1/A2 复核后异步选择 | A1 覆盖不足；A2 被反证；prior-play success 对 193 materialized games 全覆盖，旧 uncertainty audit 提供预注册 regime | raw logit coefficient固定为 1；无 intercept；分别拟合 low/high uncertainty 的 prior-play offset，penalty 16 | 4 fits/87 predictions；Brier 与 raw 几乎相同但略差，1/4 raw-Brier wins，日期/周区间跨零 | exact stratified route refuted/stop；保留“PBP 整类信息仍未被否定”，但禁止在同 87 行上调 threshold/ridge/interaction |
| Post-budget memory | scientific Controller | A3 独立复核后的完整分数和区间 | 不再执行；更新 research memory 与 active questions | 推荐未来另批次先检查全量 causal fill-age coverage，再测试单参数 market-freshness interaction | 这是下批建议，不是本批第四次 attempt，也没有新授权 |

Generation 1 的 A1 与 A2 是**并行搜索**。只有 A1/A2 的完成/失败证据导致 A3 的选择，才构成这次真正的反馈驱动迭代。

## 4. 独立复核和冻结裁判

- A2 独立结果复核 SHA：`e234818638de242efeda2bef08e8d35727e18793af3b4d642b0e7fb4922be4ae`。
- A3 独立复核从 `predictions.csv` 重算 87 行、四个 arm、四折和 date/week bootstrap；review SHA：`69e5578a55670fb5327979a9e5dc30cedbbcfe2660d763f234489738d9d4f078`。
- A3 manifest / predictions / scorecard SHA：
  - `a0143a045282ec5315e01d7294befe201e3bc5263abe5cd67a6756da63ae7b64`
  - `0da49156a9a1543d326f94aa62b8f8077b6a02ab860fcb82aa1a4e7033ba894a`
  - `5d246a61ea2e98f3489f4a1ebecf34e3b526e43632d0ba47e7dc42d6b386fdd7`
- 精确 87-row key digest 始终为 `2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`。
- 相关 candidate/scheduler 定向测试在冻结的单线程环境下 `53/53 PASS`。

评分目标、时间切分、样本 mask 和 KEEP/REVERT 没有在看分后修改。A1 的失败记录没有被覆盖；A2/A3 的 REVERT 不删除代码、预测、scorecard 或经验。

## 5. 当前 active pool 与下一步

最终 Controller memory 将 incumbent 与研究父分支分开：

1. 性能 incumbent 仍是 raw market，只作为比较对象。
2. 活跃研究问题一：`Market-freshness interaction`。检查最新 causal prior fill 的年龄是否改变 market logit 的可信度；这是 Controller 推荐的下一次独立预算实验。
3. 活跃研究问题二：`Coarse causal state residual`。只允许一个预注册、低维、单调的 possession/down-distance/field-position residual basis，作为方法不同的 backup。

不机械添加第三个问题。A1 exact route 是 invalid/cooldown；A2 和 A3 exact routes 是 refuted/stop。所有分支仍在 archive，但“保留历史”不等于继续给已否定的 exact route 预算。

## 6. 三个必须分开的结论

### 1) 自主迭代闭环是否跑通？

**是。** 证据不是日志长度，而是：Controller 读取已核验结果，改变候选选择；新候选被实现、完成真实训练和逐样本预测；独立 scorer 重算；结果再进入 Controller memory。没有逐轮用户选算法。

更准确的名称是**自主优化预测器**。本批没有由系统修改研究工具、工作流或实验选择机制；人工给 Supervisor 的新指令不能算系统自我进化。

### 2) 历史 Train 上是否出现预测改善？

**没有按冻结规则出现。** A2 明显输给 raw market；A3 Brier 比 raw market 差 `1.16e-6`，只赢 1/4 folds，区间跨零，因此 incumbent 不变。A3 的微小 log-loss 改善和对 ordinary 的稳定优势是有效信息，但不足以称为市场外预测改善。

### 3) 自迭代机制是否优于同预算固定流程？

**未测试。** 没有 matched fixed-process versus self-iterating-process control，也没有独立重复。一条成功运行的轨迹不能支持机制优越性。

## 7. 仍未支持的 claim

- 不支持 untouched OOS、Dev/Final、正式 benchmark、promotion、部署、PnL 或论文结论。
- 不支持实时优势；当前证据是历史 event-clock，可用时间尚不能等同 provider publish/local receive time。
- 不支持“所有 PBP 信息无效”；只反证了 exact A3 candidate。
- 不支持“momentum 无效”；A1 是冻结覆盖失败，不是科学性能反证。
- 不支持 Market RSI 自迭代机制优于相同 Astra、相同预算的固定研究流程。
- 不应继续在同一 87 个已看结果上调 A3 threshold、penalty 或 feature family 来追逐改善。
- 本批记录了提出者为独立 scientific Controller task，但 exact runtime model/version 没有写入 experiment manifest；在未来 matched mechanism comparison 前必须补上这个绑定，当前不得据此做基础模型同一性的 claim。

## 8. 关键证据路径

- Generation-1 Controller：`AGENT_LOG_INGAME_PREDICTIVE_AUTONOMY_GENERATION1_CONTROLLER_2026-09-29.md`
- Generation-2 Controller：`AGENT_LOG_INGAME_PREDICTIVE_AUTONOMY_GENERATION2_SINGLE_CANDIDATE_CONTROLLER_2026-09-29.md`
- Final Controller memory：`AGENT_LOG_INGAME_PREDICTIVE_AUTONOMY_FINAL_CONTROLLER_MEMORY_2026-09-29.md`
- A2 result review：`AGENT_LOG_INGAME_IDENTITY_ANCHORED_MARKET_CALIBRATION_V1_RESULT_INDEPENDENT_REVIEW_2026-09-29.md`
- A3 result review：`research/market_rsi/agents/AGENT_LOG_INGAME_PRIOR_PLAY_SUCCESS_UNCERTAINTY_STRATIFIED_OFFSET_V4_RESULT_INDEPENDENT_REVIEW_2026-09-29.md`

所有结论仅属于 opened-Train Discovery。工程完成、研究信用和闭环可运行都没有被写成预测改善或机制成功。
