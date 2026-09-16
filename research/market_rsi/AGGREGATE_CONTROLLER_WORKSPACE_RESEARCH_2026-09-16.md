# Aggregate-only Controller Workspace

## 观察到的问题

target-grid与same-support实验已经完成，但现有Data Scientist Harness只有两种主要入口：带完整
opened-Train cache的训练workspace，或围绕source QA的规划workspace。把当前体育实验的aggregate
结果硬塞进任一旧入口，会让Controller看到不属于本轮的data QA，或获得不必要的raw输入。

要改变的组件是Controller workspace admission：新增一个aggregate-only研究模式。它只冻结已完成
的机器结果、manifest、hash和当前findings；允许查公开文献、查看方法库、提出算法/feature设计并
defer；禁止raw profiling、训练、Dev/Final访问和正式promotion。

## 2026-09-16查询与阅读记录

### 查询

`Dwork reusable holdout adaptive data analysis Science 2015 primary paper DOI`

`adaptive data analysis holdout reuse Thresholdout primary paper PDF`

### 阅读1

- Dwork et al., *The reusable holdout: Preserving validity in adaptive data analysis*, Science 349(6248),
  2015。DOI：https://doi.org/10.1126/science.aaa9375
- 阅读部分：摘要与问题定义。
- 发现：分析过程本身会根据之前结果自适应改变；把同一holdout反复反馈给分析者会破坏传统的
  固定过程假设。论文提出受控holdout反馈，而不是让分析者无限读取明细。
- 本项目用法：Controller可以反复看到opened-Train aggregate和自己的旧Archive，但当前Dev label
  仍不进入workspace；aggregate模式不把Train探索包装成独立确认。
- 限制：论文的理论机制基于隐私/稳定性方法；本版不实现Thresholdout，也不声称只给aggregate
  就自动获得统计有效性。

### 阅读2

- Dwork et al., *Generalization in Adaptive Data Analysis and Holdout Reuse*, NeurIPS 2015。
  Primary proceedings PDF：
  https://proceedings.neurips.cc/paper_files/paper/2015/file/bad5f33780c42f2588878a9d07405083-Paper.pdf
- 阅读部分：abstract、Reusable Holdout、Thresholdout算法和限制说明。
- 发现：Thresholdout把Train与holdout差异超过阈值的次数作为有限预算；其保证依赖明确的样本
  与查询假设，不等于“任何aggregate都安全”。
- 本项目用法：本版采取更保守的边界——aggregate-only Controller完全没有Dev query接口，最终
  confirmation仍由外层runner一次性执行。当前workspace只决定下一项opened-Train研究。
- 限制：NFL比赛和plays不是论文假设中的IID统计查询；因此不套用论文的样本复杂度或噪声参数。

## 方案比较

1. **复用旧训练workspace。** 可以少写代码，但会冻结不匹配的Train schema，并给Controller多余
   raw入口；拒绝。
2. **把结果写成prompt文本，绕过Harness。** 快，但没有hash、append-only tool log、预算与提交
   约束；拒绝。
3. **选择：aggregate-only workspace。** Runner冻结结果/manifest和current findings。Controller
   仍使用Codex harness + GLM、公开研究工具和唯一提交；raw/train/Dev工具在数据层拒绝。
4. **实现Thresholdout/差分隐私反馈。** 理论更强，但与当前非IID体育数据和一次性Dev协议不直接
   匹配，且会引入新的统计机制；本轮不做，保留为未来研究。

## 实现与验收

- `Store.create`已新增`aggregate_research`，必须有至少一个hash匹配的aggregate receipt，必须没有
  data root、Train dates或planning context。
- aggregate文件复制进workspace并进入冻结source manifest；Controller只通过`findings.json`看到
  runner整理的有限summary，原始行情不进入workspace。
- `Store.quality()`明确返回`aggregate_only`、`training_allowed=false`、`raw_data_admitted=false`；
  `quality_before_training()`无条件拒绝。
- Broker仍要求逐条acknowledge findings；允许文献、method library、algorithm proposal、capability
  request和defer。选择trial或训练必须失败。
- synthetic adapter canary已加入inspect→acknowledge→defer及append-only archive核对；标准
  exact-source真实Codex canary仍需在发布commit后运行18次工具调用。
- `prepare_sports_aggregate_controller.py`只接受两份已经冻结的Train-only实验。它逐项核对result、
  manifest和pre-score lock的schema/hash/cross-reference，拒绝任何标为打开Route-Dev/Final或非零
  provider cost的输入。它生成六条当前findings，不把raw rows或既有Route-Dev结果交给Controller。
- aggregate模式的Controller提示明确禁止raw profiling、训练、trial selection和source-study
  registration；仍允许公开资料阅读、sports method library、capability request和新算法提案。
- 通过fresh commit、annotated tag、origin push和release receipt后，才能创建付费sports
  aggregate Controller session。该session只能使用原`$200`账本的learning余额。

## 当前验证状态

- **found/read：** 两篇primary source已按上文记录阅读；没有把论文结论外推成NFL数据保证。
- **implemented：** aggregate-only admission、冻结receipt、训练/选择拒绝、Controller模式提示、
  sports汇总准备器及测试已经写入`dsh-v1.6.3`候选源码。
- **validated locally：** 3项aggregate workspace测试、2项sports准备器测试通过；完整Harness
  257/257、sports 59/59、相关experiment/preparer 8/8通过。
- **validated release mechanics：** exact-source canary
  `data-scientist-codex-canary-20260916-01`通过18次真实Codex工具调用、4次合成CPU拟合及新增3次
  aggregate边界调用；0 Tinker、0新Dev/Final。commit
  `68d500a9be24eb277aa56d4dd442f48caf7bd565`、tag `dsh-v1.6.3`和release
  `1d2d400b4720be4c9b37dd827b5237fc3d204b6b2e713e579a46f348e28c397e`已核对发布。
- **validated controller boundary：** 真实aggregate-only会话
  `nfl-target-controller-20260916-01`完成。GLM用了7个turn、9次tool call，先检查Harness和方法库，
  再搜索公开资料、成功阅读两份来源、记录研究、逐条回应6个findings，最后defer。它没有raw rows、
  没有训练、没有Dev/Final，也没有改Harness；model authorship、进程回收和7笔Tinker accounting均
  通过。实际新增metered cost为`$0.284437332`，不是`$8.44038144`的启动上界。
- **controller proposal：** 保持30秒target、16,632个same-support plays、3×21场rolling blocks和
  Random Forest不变，只测试score×time、possession×field-position和same-event state delta三类
  表示，并做消融。若不支持，再单独测试HistGradientBoosting。Controller没有提出新trainer；这是
  一次保守的feature-stage决定。
- **not yet validated on our data：** Controller只给出了事前实验设计，并未证明表示方法有效。
  对应opened-Train A/B必须用冻结源码和fresh run ID执行；Dev/Final仍不能打开。

## Controller方案的opened-Train回传

`nfl-open-train-representation-ablation-20260916-01`已经执行。精确parent被复现。主候选相对parent
降低MSE `31.66%`，63场中`98.41%`更好，但校准斜率`1.1310`超过事前上限`1.1`，所以按锁定规则
记为不支持。消融显示几乎全部改善来自`state_wp_delta`；另外两个表示只贡献约`0.08%`和`0.24%`。

这份回传改变了下一实验的问题：不是再猜更多feature，而是在完全相同的`full_k4`输入上只更换
trainer，检查固定HistGradientBoosting能否同时改善Random Forest并修正校准。Dev/Final仍不打开。

固定HGB随后把MSE再降低`8.48%`，三个fold都优于RF，并把校准斜率修到`1.0316`；但是候选减
parent的日期块区间`[-0.00011820, +0.00000702]`略跨0，所以仍按事前规则记为不支持。

第二个aggregate-only feedback adapter现在把target-grid、same-support、representation和trainer
四份已完成Train实验的result/manifest/lock作为12个精确hash receipt冻结。Controller只看到六条
新的aggregate finding：实验链、feature归因、trainer结果、剩余不确定性、评估边界和下一决定。
它看不到raw rows、比赛ID、逐场诊断、Route-Dev或Final，也不能训练。

本次没有为了“看起来在进化”而修改核心Harness：v1.6.3现有aggregate边界已经能安全承接反馈。
变化的是已提交、带hash的feedback adapter和实验上下文。只有Controller下一决定暴露出真实能力
缺口时，才发布新的Harness版本；这样可以区分“研究策略更新”和“Harness代码更新”。
