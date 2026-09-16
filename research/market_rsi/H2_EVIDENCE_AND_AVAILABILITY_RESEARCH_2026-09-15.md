# H2：Feature 可用时间与成对证据输出

## 观察到的问题

`dsh-v1.6.0` 的一次性 Route-Dev 结果保存了总体 baseline 和 candidate 指标，但没有保存
candidate 相对 baseline 的逐比赛 loss difference。结果显示总体 MSE 改善 11.88%，但我们无法
在不重新打开 Dev 的情况下检查这 11.88% 是否主要来自少数比赛。

同一轮更早还发现过一次实际 future leakage：旧的状态变化 feature 读取了下一条可评分 play。
23,546 行受影响，中位向后 44 秒，28.61% 超过 60 秒。这个问题说明 availability 不能只写在
单个实验脚本里，需要成为 Harness 的通用合同。

本次只改变 Harness 证据层，不改已结束的 v1.6.0 实验，不重开其 Route-Dev，不打开 Final。

## Horizon 不是全局固定为 60 秒

`60 秒`只属于刚完成的 state-WP-delta 实验。Open discovery 可以在 opened Train/Archive 上
研究 30 秒、60 秒、300 秒、event-time target、多目标或新的 objective；Harness 不替 controller
选择 horizon。只有当一个 candidate 要进入新的 untouched confirmation 时，该轮的 horizon、
label 规则、baseline、reward 和 evaluator 才一起冻结。看过新 Dev 后不能改 horizon；新想法
进入下一 cycle 和新的 untouched cohort。

因此，通用 feature availability contract 只要求 feature 在 decision 时已经可用、label 在
decision 之后；它不写死 60 秒。本次真实 Train canary 中的 60 秒只是对既有实验的准确重放。

## 2026-09-15 查询记录

### 查询 1

`Hidden Technical Debt in Machine Learning Systems data dependencies feedback loops pdf`

- 找到并阅读：Sculley et al., *Hidden Technical Debt in Machine Learning Systems*, NIPS 2015，
  proceedings 页面摘要和论文入口。
- URL：https://proceedings.neurips.cc/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html
- 阅读部分：摘要；重点是隐藏数据依赖、反馈环和配置问题。
- 对本项目的用法：feature 必须显式声明来源和时钟，不能依赖脚本作者默认“应该已经可用”。
- 限制：论文讨论通用 ML 系统债务，不证明我们的 NFL feature 有预测价值。

### 查询 2

`White 2000 Reality Check for Data Snooping Econometrica DOI`

- 找到并阅读：White, *A Reality Check for Data Snooping*, Econometrica 68(5), 2000，publisher
  摘要、问题定义和方法目的。
- DOI：https://doi.org/10.1111/1468-0262.00152
- 阅读部分：摘要；重点是同一份时间序列反复用于模型选择时，最好结果可能由偶然产生，并提出
  相对 benchmark 的 specification-search 检验。
- 对本项目的用法：Discovery 必须保留所有试过的候选，正式 confirmation 只能预先选一个，
  不能看完 Dev 后在多个 feature 中挑最好者。
- 限制：本次不实现完整 White Reality Check；目前的 candidate 数量和日期块数量都较小。

### 查询 3

`A Test for Superior Predictive Ability Hansen 2005 DOI`

- 找到并阅读：Hansen, *A Test for Superior Predictive Ability*, JBES 23(4), 2005，作者工作论文
  页面摘要。
- DOI：https://doi.org/10.1198/073500105000000063
- 阅读部分：摘要；SPA 使用 studentized statistic 和 sample-dependent null，减少差或无关候选
  对比较的影响。
- 对本项目的用法：候选库可以开放，但 promotion 记录必须保存所有候选及其相对固定 baseline
  的证据，不能只留下 champion。
- 限制：本次不声称做了 SPA 显著性检验；先把完整 paired loss 保存下来，给以后检验留下输入。

### 查询 4

`Comparing Predictive Accuracy Diebold Mariano 1995 DOI`

- 找到并阅读：Diebold and Mariano, *Comparing Predictive Accuracy*, JBES 13(3), 1995，publisher
  摘要。
- DOI：https://doi.org/10.1080/07350015.1995.10524599
- 阅读部分：摘要；比较两个 forecast 的 loss difference，允许非高斯、非零均值和相关误差。
- 对本项目的用法：正式比较应保存同一比赛、同一行上的 paired baseline/candidate loss，而不是
  只保存两组独立汇总。
- 限制：当前实现不直接输出 DM p-value；NFL play 在同一比赛内强相关，需要先按比赛聚合。

### 查询 5

`MacKinnon Nielsen Webb cluster-robust inference guide empirical practice pdf`

- 找到并阅读：MacKinnon, Nielsen and Webb, *Cluster-Robust Inference: A Guide to Empirical
  Practice*, Journal of Econometrics 232, 2023，工作论文摘要、cluster 假设、pairs cluster
  bootstrap 和报告建议部分。
- DOI：https://doi.org/10.1016/j.jeconom.2022.04.001
- 开放作者版本：https://pure.au.dk/portal/files/284768944/rp22_08.pdf
- 阅读部分：摘要；cluster 内允许相关、cluster 间假设独立；pairs cluster bootstrap 以整个
  cluster 为单位重采样；有限 cluster 时需要谨慎。
- 对本项目的用法：比赛是主要 paired unit；日期是更粗的时间 block。报告比赛数、日期数、
  top-1/top-5 绝对贡献份额和 leave-one-game-out 范围，避免把 7,437 个 play 当独立样本。
- 限制：同一天比赛可能受共同市场 regime 影响，因此只按比赛 bootstrap 也不够；当前选择按
  日期块重采样，并明确只有 16 个日期时区间仍可能不稳定。

### 查询 6

`offline feature retrieval point-in-time join source delay data leakage`

- 找到并阅读：Microsoft Azure ML 官方 point-in-time join 文档。
- URL：https://learn.microsoft.com/en-us/azure/machine-learning/offline-retrieval-point-in-time-join-concepts
- 阅读部分：event time、source delay 和 point-in-time lookup 说明。
- 对本项目的用法：区分 `feature_event_time`、`feature_available_time` 和 `decision_time`；历史
  event clock 不等于 live arrival clock。
- 限制：这是工程实现文档，不是金融市场实证论文，也不能补出我们没有采集的 live arrival time。

## 比较过的实现选择

1. **只在报告里提醒。** 最简单，但已经被真实 future-leakage 事故证明不够。
2. **只保存 aggregate MSE。** 不暴露 Dev identity，但无法检查 paired 稳定性和集中度。
3. **公开逐比赛 Dev 结果给 controller。** 证据最全，但会把已看 Dev 变成逐题调参数据。
4. **选择：runner-private 逐比赛记录 + controller-visible aggregate。** 运行方保存完整 paired
   evidence；controller 只看到无比赛 ID 的汇总、日期块区间和集中度。既能审计，也不把具体
   Dev 比赛变成下一轮提示词。

## 落到 Harness 的规则

- 每个 derived feature 在实验前冻结 event、available、decision、label-start、label-end 五个
  时钟字段，逐行必须满足
  `event <= available <= decision < label_start <= label_end`。
- 任一行失败时整条 candidate fail closed；不能安静删掉失败行。
- confirmation 必须提前冻结 evidence 类型。预测 A/B 使用 `paired_grouped_loss_v1`；非预测型
  终端 canary 可以使用 `scalar_terminal_v1`，因此 Harness 不被锁死为 MSE 预测。
- Open discovery 的机器记录明确包含 `horizons_may_change_on_opened_data=true`。新的 confirmation
  必须单独提交 `target_spec_sha256`；horizon、event-time 规则或多目标定义都属于这个 target
  specification，而不是 Harness 的全局常数。
- paired evidence 的详细 unit 记录只放 runner-private；公开汇总不带比赛 ID。
- 公开汇总固定包含 equal-unit baseline/candidate loss、mean/median delta、胜出比例、日期块
  bootstrap 区间、top-1/top-5 绝对贡献份额和 leave-one-unit-out 范围。
- 这些规则只对新版本和新的 untouched cohort 生效；不会回头重算 v1.6.0 Route-Dev。

## 验证计划

- 单元测试：正常时钟、未来 feature、label overlap、重复 row、弱化合同；paired identity 隔离、
  重复 unit、非有限 loss、单日期 block、公开范围弱化。
- 真实 opened-Train canary：重放 163 场、23,709 行 same-event PBP 绑定，只做 availability，
  不打预测分、不读 Route-Dev/Final。
- 全回归：Data Scientist Harness 和 sports-event research 两套测试都必须通过。
- 发布前：升级版本、真实 Codex exact-source canary、commit、annotated tag、只推自己的 origin、
  生成 release receipt。没有这些，不启动下一次正式 experiment。

## 实际验证结果

- Data Scientist Harness 全回归：248/248 通过。
- Sports-event research 全回归：54/54 通过。
- 第一个发布 canary ID `data-scientist-codex-canary-20260915-09` 在受限沙箱中因 loopback
  bind 被操作系统拒绝；它没有工具循环、没有付费调用，也没有复用。
- 新 ID `data-scientist-codex-canary-20260915-10` 在允许 loopback 的同源码环境通过：18 次工具
  调用、4 次合成 CPU 拟合、1 次公开搜索、1 次公开阅读、0 Tinker、`$0`、没有新 Dev/Test。
- 真实 opened-Train availability canary `nfl-state-feature-availability-20260915-02` 通过：163 场、
  23,709 行、0 违规。这里的 60 秒只是在重放既有 target，不是 Harness 选择；回执明确记录
  `horizon_selected_by_harness=false`。历史 SportsRadar event clock 不包含 live arrival time，
  所以该结果证明历史时钟内部一致，不证明实盘时 feature 已到达。
- 已发布 commit `5aa860275f19bcc1148a591bb9fbaa152ef08a7b`、annotated tag `dsh-v1.6.1`；
  release SHA256 为 `aa2c509c3c45261c008f1c5810851a2da959bd9781e7cc956ac3f8168439f8e4`。
  只推送到 `https://github.com/Estelle-LH/RSIBench-Data.git`。
