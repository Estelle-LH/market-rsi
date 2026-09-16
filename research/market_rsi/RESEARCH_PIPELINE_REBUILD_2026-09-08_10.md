# Research pipeline 重搭记录｜2026-09-08 晚上 – 2026-09-10

新增：[正式实验前的数据科学流程](DATA_SCIENCE_PIPELINE_2026-09-10.md)。逐项说明历史数据
问题怎么处理、controller需要做什么、runner怎么验收，以及目前哪些还没完成。

最新结果：旧数据已试过七个模型，最好一个在反复看过的三个日期上好0.159%，还不能说
能推广到新日期。新下载的39.3GB档案则查出覆盖问题：要求窗口内只有6天有记录，合计617
个有消息的分钟，不能单独满足原方案。详情：[模型结果](HISTORICAL_MODEL_FINDINGS_2026-09-10.md)、
[新数据覆盖结果](VANTAGE_COVERAGE_FINDINGS_2026-09-10.md)。

## 这份记录看什么

这份只记录周二（9 月 8 日）晚上决定重搭 Harness 以后，到 9 月 10 日的工作。
它不把前面的 data-only 实验、旧模型分数或旧数据整理混进来。

## 为什么要重搭

之前的 data scientist Harness 太窄：controller 主要是在一段文字里给答案，不能连续查
论文、检查数据、写代码、实际运行、看报错、再改方案。这样即使回答听起来合理，也无法
确认它真的做过研究。

前一轮还暴露出四个具体问题：

- 预测目标太平，短期价格大多不变，persistence 基线已经很强；
- Train-CV 只看一个安静日期，controller 学到的是这个日期的特点；
- controller 选中过预测完全相同的候选，只改了无关 metadata；
- predictor 的分数和 controller 是否真的按计划工作，没有分开验收。

所以这次不是先换一个模型，而是先把“controller 怎样做研究”这条链搭完整。

## 重搭后的 Harness

### 谁负责什么

- **GLM-5.3 controller**：查公开论文，检查允许的 Train，提出研究问题，选择目标，决定
  feature、模型、loss 和下一步实验，并说明为什么。
- **Codex + runner**：提供工具和执行环境，固定数据边界、评分、预算、超时、隔离和日志。
  它不替 controller 挑一个看起来更好的结果。
- **Harbor / E2B**：隔离运行候选代码。没有真实执行和评分回执的文字答案，不算实验结果。

### 给 controller 的空间

- 单轮最多约 192K input、64K output；
- 可以查公开文献、看算法目录、读允许的 Train、写代码、在隔离环境跑 Train-CV、查看
  报错和结果；
- 只保留 Archive 作为记忆：计划、代码、文献、结果、失败和成本都留着，下一轮可以读取；
- 每次 session 记录工具调用、文献、算法、代码和运行结果；启动和结束时还记录
  `harness-runtime.json`，防止 Codex 或配置在中途悄悄变化。

### 研究流程现在怎么走

固定顺序是：

**数据发现 → 原始数据审计 → 目标研究 → 冻结 Train/Dev/Test → Train-CV → 一次性 Dev → 最后 Test**

目标和数据切分冻结前，不开始正式模型比较。Dev 只能在一轮结束后打开一次，Future Test
一直封存。候选还要做 prediction digest 去重；“模型分数有效”和“controller 真的执行了
自己的决定”分别检查。

## 9 月 8 日晚上的第一步：先研究 objective

Objective discovery 已经从正式模型训练中独立出来。controller 只能看到 Train 的聚合统计，
不能看到 Dev 或 Future Test 的答案。

- 真实Train目标选择：GLM-5.3，8个回合、18次工具调用、3次文献搜索；
- 实测controller成本：`$0.176343156`。另一次合成数据canary才是19次工具、`$0.179685864`；
- 选定并冻结：`future-midpoint-window-mean-270-330s-v1`，即预测未来 270–330 秒
  midpoint 的平均值；
- 目标合同 hash：`a2da65cbb5ed76234232ad328caddae470b55c9fc3b3f0a3233fba18e4f634d4`；
- 这一步没有打开 Dev，也没有打开 Future Test。

选择这个目标的原因不是“Train 分数最高”，而是旧 60 秒目标太平。Train-only 审计显示，
1 分钟、5 分钟、15 分钟窗口的变化率约为 2.05%、6.24%、14.60%；5 分钟目标有更多可测的
变化，同时仍能用简单的 persistence 基线比较。

## 9 月 9 日：把 Harness 验证成真的研究环境

完成了controller harness的定向测试和离线回归。随后历史数据研究继续进行了真实GLM
调用和模型诊断，不能把整天写成“没有付费模型结果”。Future Test没有因此被打开。

9月9–10日的历史数据实验另行选择了“未来1–30分钟平均报价减去当前报价”，不是上节的
5分钟目标。七个候选在同一批105,772条有标签记录上比较；t7保持21项特征，改用更保守的
树参数，MSE从不变预测的0.004345225降至0.004338338。全部检查日期都是已打开的Train，
不是新Dev/Test。[七个候选具体改了什么](HISTORICAL_MODEL_FINDINGS_2026-09-10.md)。

同时把数据发现也做成 controller 的独立阶段：controller 可以比较数据源、日期、市场、
盘口/成交流、下载上限和拒绝条件；runner 只检查规则，不替它预先选好答案。这样以后数据
不够或目标不合适时，controller 有机会自己发现，而不是被一个很小的固定题库卡住。

当天的关键结论是：数据要先过审，之后才谈模型。现有旧 materialized 数据行很多，但按行
并不独立，不能把行数直接当成有效样本量。

## 9 月 10 日：把 Polymarket 数据入口接到新流程

当前研究只用 Polymarket；Kalshi 和 SportsRadar 不混进这条实验。

- 固定了 Polymarket Vantage archive 的 revision、文件大小和 SHA-256；
- 3.16GB 压缩包已下载到 Linode，并备份到私有 S3；
- 用有界、immutable、query-only 的 SQLite 检查确认 schema、时间字段和部分缺失情况；
- 发现过一个旧的无界 SQLite 读取进程，已只停止那个确切进程并保留 sidecar；之后所有读取
  都加了 30 秒硬上限；
- 两项实时采集服务保持运行，没有重启；
- 这批数据还没有进入 Train、Dev 或 Test，数据 QA 尚未宣布通过。
- 后续精确日期检查已确认Vantage单独覆盖不足。每个有数据日期只有17–239个活跃分钟，
  不能按文件名把中间空白当成完整月份；下一步需要controller修订数据方案。

## 目前真正得到的结果

已经证明的是：

- controller 现在确实能在一个 session 里查资料、检查 Train、写代码、运行候选、读结果、
  再做决定；
- objective 可以在看 Dev 前冻结；
- Archive 能把完整研究记录传给下一轮；
- runner 能把 predictor 分数、controller 完整性、预算和数据边界分开验收。

还没有证明的是：

- 新 Harness 已经让模型在真正未见过的 Polymarket 日期上提高；
- 5 分钟目标一定优于所有其他目标；
- 预测结果能赚钱。

原因很具体：Vantage的新覆盖证据不满足原方案，其他字段与时钟检查也没有全部通过。
新的干净Dev需要另行按时间顺序冻结，不能为了赶进度复用已经打开过的日期。

## 现在该看哪些文件

- Harness 设计：[`CONTROLLER_HARNESS_V3.md`](CONTROLLER_HARNESS_V3.md)
- 时序研究规则：[`TIME_SERIES_RESEARCH_HARNESS.md`](TIME_SERIES_RESEARCH_HARNESS.md)
- Controller的数据来源方案：[`SOURCE_ACQUISITION_REVIEW_2026-09-10.md`](SOURCE_ACQUISITION_REVIEW_2026-09-10.md)
- 9 月 9 日逐步日志：[`DAILY_LOG_2026-09-09.md`](DAILY_LOG_2026-09-09.md)
- 9 月 10 日逐步日志：[`DAILY_LOG_2026-09-10.md`](DAILY_LOG_2026-09-10.md)
- 当前数据入口索引：[`DATA_WORK_INDEX_2026-09-09_10.md`](DATA_WORK_INDEX_2026-09-09_10.md)
