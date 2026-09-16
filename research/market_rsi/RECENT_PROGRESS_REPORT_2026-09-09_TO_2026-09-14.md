# 最近六天实际进展（2026-09-09 至 2026-09-14）

## 先说结论

这六天每天都有实际工作，但不是每天都完成了模型实验。

- 9月9日至12日主要在处理数据来源、文件恢复、数据质量和 Data Scientist Harness。
- 9月13日第一次把真实历史数据转换、拟合、检查和多轮 researcher 比较完整接起来。
- 9月14日把 researcher 的记忆方式做成更大的八轮实验。八轮训练和 Dev 已完成。Final先因运行器的四百万条限制停过一次；修复后的recovery完成4个session后发现第5个source不符合冻结的UTC日规则，因此旧实验永久停止，部分分数不用作结论。

所以，这几天不是没有做事，也不是每天都在“训练”。真正的研究结果集中在最后两天；前四天是在解决如果不先修好、后面的分数就不能相信的问题。

## 每天具体做了什么

### 9月9日：先把目标、数据来源和实验顺序定清楚

实际完成：

- 固定了当前5分钟预测目标：预测未来270–330秒中间价的平均值。
- 固定了不变价格 baseline、按时间切 Train/Dev/Final，以及 Dev 看过以后不能再当未见数据。
- 加了 controller 的运行版本记录，能够追踪 Codex、GLM、instructions、代码和工具有没有中途变化。
- 检查了 OpenMarket、Polymarket API 和 Kalshi 的数据可用性与许可边界。当前可复现历史数据优先使用 OpenMarket。
- 跑通 OpenMarket 小样本和两天大分区的数据读取、清洗、排序和 hash 检查。一个分区有约662万条盘口更新。
- 检查“不变报价”：5月14日相邻最优买卖价有98.66%不变，但绝大多数记录仍有其他盘口更新，因此没有简单删除这些行。

当天得到的结论：

- 原来只有8天、17,319行的正式 materialized 数据，只够测试流程，不够判断模型是否真的学会。
- 数据必须按实际到达时间回放；按来源时间排序可能把晚到消息放到过去，造成未来信息泄漏。
- 当天没有完成新的正式模型 Round。

详细记录：[DAILY_LOG_2026-09-09.md](DAILY_LOG_2026-09-09.md)

### 9月10日：把历史数据拿稳，并把 Data Scientist Harness 做成可运行版本

实际完成：

- 恢复并核对897个本机文件，内容 hash 对上。
- 在 Linode 下载了3.16GB压缩历史数据，解压成39.32GB SQLite；完整 hash 通过。
- 把压缩数据备份到私有 S3，大小、SHA256、加密和非公开设置均核对通过。
- 代码推到自己的私有 GitHub，没有上传原始数据、密钥和运行 artifacts。
- 对 Vantage 数据做有界只读检查。它看起来很大，但46天范围里只有6天有记录，合计617个活跃分钟，没有一天达到原计划的完整 session 要求。
- 搭出 Data Scientist Harness：先查数据，再查时序和 feature，最后才允许 trainer 运行；加入文献搜索、公开页面读取、统计检查、四种 CPU trainer、Archive 和完整日志。
- 发布多个明确版本并跑回归测试和 canary。最终当天版本把每次实验前的假设、支持/反对条件、参数和实验后的结果、解释分开保存。

当天得到的结论：

- “文件很大”不等于“有效历史很多”。这份 Vantage 数据覆盖不足，不能进入正式训练。
- Harness 能运行，但真实 GLM 方案会话仍出现工具参数、回复恢复和授权接口问题；当天真实设计会话没有完成市场拟合。
- 当天没有新的模型成绩。

详细记录：[DAILY_LOG_2026-09-10.md](DAILY_LOG_2026-09-10.md)

### 9月11日：把历史报价异常查清，不把坏数据当机会

实际完成：

- 完整检查8个日期、38,464,296条 Polymarket 报价记录。
- 发现698,095条“买价高于卖价”，占1.81%；另外两个日期是空表。
- 回到原始消息逐步重放，发现一类交叉报价来自采集程序在同一条消息尚未处理完时就写出了中间状态，不是可以成交的套利价格。
- 修复报价重建逻辑并在已读数据上重放验证；原始文件和生产采集没有改。
- 让 controller 多次根据新证据修订方案。它最后仍选择先补数据证据，不训练；所有 GLM 会话合计仍是0次市场拟合。
- 改进超时记录：以后长审计每完成一天就落盘，不能等到最后才一次性写结果。

当天得到的结论：

- 交叉报价不能简单删掉，也不能当成套利；要区分原始消息报价、完整处理后的订单簿和写出过程中的中间状态。
- 3,800多万行不是3,800多万个独立训练样本。
- 来源时钟、历史身份映射和缺失时段仍未完全证明，因此不应急着训练。

详细记录：[DAILY_LOG_2026-09-11.md](DAILY_LOG_2026-09-11.md)

### 9月12日：把时间规则和本机文件问题变成硬检查

实际完成：

- 把“预测时点、消息时间、缺消息、无效报价、未来答案什么时候才可见”写成可以执行的检查，不再只留在文字方案里。
- 157项回归测试通过；两条真实 Codex 免费工具链通过。
- 找到旧环境卡顿的原因之一：618个相关文件中有231个是 iCloud 占位文件。
- 建立独立运行环境并取回指定文件；最终618个文件全部本地可读，旧 manifest、方案和预算授权 hash 一致。
- 发布 `dsh-v1.4.0` 到自己的私有 origin，并核对 release receipt。

当天得到的结论：

- 这一天主要修基础设施和实验纪律，没有读取新行情、没有 Tinker 调用、没有真实训练、没有新 Dev/Final。
- 修复后具备继续真实 controller 工作的条件，但还不能把工程测试写成模型进步。

详细记录：[DAILY_LOG_2026-09-12.md](DAILY_LOG_2026-09-12.md)

### 9月13日：第一次把真实数据、真实拟合和 researcher 记忆实验接起来

实际完成：

- 修复 controller 长编号引用和 JSON 文本参数问题，发布 DSH v1.4.1 和 v1.5.0。
- 对一个真实小时文件做完整读取：151,802条原始记录拆出298,068条报价；90.27%的相邻中间价不变，并发现 REST 与 WebSocket 消息混在一起会造成时间回退表象。
- 把另一个真实小时的848,542条记录转换成1,051,922个可用 feature-label 样本；92.25%的答案不变。
- 跑了一个简单的真实拟合：在8月21日一个小时训练单特征线性模型，然后锁定参数，在四个较晚小时检查。
- 四小时等权 MSE 从 `0.0001141124` 降到 `0.0000900582`，平均低21.1%；但8月25日变差7.6%，且90.2%的总改善来自9月9日一个小时。因此它只是初步诊断，不是稳定提升。
- 跑完三轮 archive-memory 对 fresh/no-memory 的小实验。最终三个 holdout 小时：baseline MSE `5.96488e-05`，fresh `5.95517e-05`，archive `5.75617e-05`。Archive 比 baseline 好3.50%，实际 GLM 费用约 `$1.97`。

当天得到的结论：

- 真实数据链路和真实拟合终于跑通。
- 小实验显示 Archive 可能帮助 researcher 记住前一轮有效想法，但 Final 只有3个小时，远远不够证明稳定 OOS，更没有证明赚钱。
- 大量相关行和少数市场集中贡献，会让平均 MSE 看起来比实际证据更强。

详细记录：[DAILY_LOG_2026-09-13.md](DAILY_LOG_2026-09-13.md)、[PRELIMINARY_RESULT_2026-09-13.md](PRELIMINARY_RESULT_2026-09-13.md)

### 9月14日：扩大记忆实验，并修复 Final 的运行器限制

实际完成：

- 复盘9月13日小实验。Fresh 在第二轮其实找到过与 Archive 最终几乎相同的好 feature，但第三轮忘掉了；Archive 把它保留到最后。这支持“Archive 帮助保留中间有效实验”这个较窄的解释。
- 完成第一份8轮 archive-vs-fresh replication 的全部 controller 和 Dev。它的 Final 只完成19/20，因为最后一个固定源文件本身被截断。Archive 在 Dev 较好，但在19个可用 Final 上按 session 等权反而比 fresh 差约6.7%；该实验不能给正式主结论。实际 controller 费用约 `$7.34`。
- 根据这个结果设计并运行三条记忆路线：`fresh`、完整 `archive`、结构化 `compact`。8轮、24个 controller session 全部完成，实际 controller 费用约 `$10.53`。
- Dev 等权 MSE：baseline `0.000641681`，fresh `0.000632853`，archive `0.000621402`，compact `0.000624137`。Archive 和 compact 在8个 Dev session 中各赢 baseline 5次，但 Dev 不能代替 Final。
- 第一次 Final 在出任何分数前停止。查明主要原因是运行器最多保留4,000,000条选中观察，不是已经证明的机器内存不足。
- 只修改 materializer 的资源上限，不改 controller、数据、目标、feature、trainer、Round 8 模型或20个 Final session。发布 commit `8b7eb1c` 和 tag `pm-memory-policy-final-recovery-v0.1.0`。
- 合成 canary 和一个已打开的大真实文件 canary 都通过；真实 canary 有3,867,212条观察，cache hash 与旧结果一致。新的 Final 第一个 session 已越过旧的四百万限制并完成；随后在第5个source发现旧preflight没有检查正式采样时间语义。

当前状态：

- Final-only recovery已永久停止：完成4/20后，第5个source在正式采样的第1条记录发现UTC日越界。
- 第5个source没有产生target、拟合、provider调用或分数；前4个部分分数不用于选择模型或正式结论。
- 9月15日开始的v2先对所有候选做完整语义检查，再冻结新的Train/Dev/Final清单。

详细记录：[MEMORY_POLICY_EXPERIMENT_2026-09-14.md](MEMORY_POLICY_EXPERIMENT_2026-09-14.md)、[MEMORY_POLICY_FINAL_RECOVERY_2026-09-14.md](MEMORY_POLICY_FINAL_RECOVERY_2026-09-14.md)

## 到现在真正学到了什么

1. 数据量不能看文件大小或行数，要看时间覆盖、市场覆盖、价格变化和独立 session 数。
2. 原始采集中的交叉报价、时钟回退和空日期，很多是数据管道问题；不先查清，模型可能学到错误。
3. 简单模型在少数已打开历史小时上能降低 MSE，但收益集中，不能写成稳定泛化。
4. Archive 可能帮助 researcher 保留有效的中间实验；但完整 raw archive 更贵，也没有在19个 Final session 的旧 replication 中胜出。
5. Compact memory 是更合理的新候选：它保留实验、结果、失败、成本和来源 hash，不重复塞入全部网页和工具记录。
6. 现在还没有盈利结果，也没有满足正式 promotion 条件。当前比较只在“预测误差”和“researcher 如何使用历史经验”这一层。

## 哪些还没做完

- 旧三路线实验因冻结source不合格而永久无效；还没有基于至少20个完整新Final session得出正式结论。
- v2已完成44个候选source的score-free检查，冻结3个Train、8个Dev、20个Final，并通过真实materialization和0-provider controller canary。
- 正式v2随后从精确发布的 `pm-memory-policy-v0.2.0` 启动。Round 1和Round 2完成；
  Round 3三个controller session完成后，fresh的完整refit在6,105,040行超过原2 GiB上限。
  这是candidate fit与完整refit资源门槛不一致的harness问题。v2没有打开Final，但已经看过
  两个rolling Dev，因此整轮作废，不原地续跑，也不把checkpoint/archive带进下一轮。
- v3只修资源执行层：candidate fit `6 GiB/480秒`，完整refit `8 GiB/600秒`，不抽样、
  不改plan、三路线一致。原失败请求已原样通过正canary；新Dev排除v2打开过的两个session，
  31个source的score-free语义回执和0-provider controller canary均已通过。正式结果尚未产生。
- 还没有把预测固定后单独做包含点差、手续费、滑点和成交概率的 PnL 实验。
- 历史模型费用账本有本地逐笔记录，但尚不能说已经与所有供应商发票完成最终对账。

## 最简短回答：每天都干了吗？

每天都有可核对的代码、测试、数据检查、controller 记录或实验结果。可是工作类型不同：

- 9月9–12日：主要是把数据和实验工具修到可以相信。
- 9月13日：开始产生真实拟合和小规模研究结果。
- 9月14日：完成8轮主要比较，正在跑锁定的20-session Final。

因此可以说“每天都有推进”，不能说“每天都完成了一轮有效训练实验”。

## 9月15日状态更新

9月14日启动的 Final-only recovery 后来完成4/20个 session，并在第5个
`2026-09-10T00` 停止。文件本身通过完整结构检查，但第一条被正式规则选中的
WebSocket 报价使用了声明 UTC 日之外的 source timestamp。运行器按原规则拒绝，
没有静默过滤、替换或重试。该 session 产生0次拟合、0次 provider 调用和0个分数。
前4个部分结果不用于正式结论。下一步先把正式采样语义加入付费前 source gate，
再用全新未见数据清单启动新实验。

v3随后从已发布的固定代码、全新Dev和Final重新开始。Round 1已在新Dev
`2026-09-11T04`完成：共同baseline、fresh、archive、compact的等权MSE分别为
`0.0000707589`、`0.0000689759`、`0.0000655224`、`0.0000480783`。本轮compact最低，
Round 2在`2026-09-11T05`的对应结果为`0.0000654868`、`0.0000679117`、
`0.0000447586`、`0.0000417038`。目前两个Dev session都是compact最低；fresh在Round 2
比共同baseline差，这是合法结果，不重跑。Round 3随后在compact controller停止：它完成
25个付费turn和25次工具调用后用满`65,536`个session输出token，最后没有调用提交工具。
provider和拟合工具正常，Round 3没有打开Dev，Final也从未打开。因为v3已经公开两个Dev结果，
不能加token后原地继续；v3保留为无Final结论的失败实验，下一版必须使用新ID和全新未见证据。

v4先修controller结尾，不重跑v3：普通研究不能再花掉最后的提交容量，进入terminal phase后
只允许模型自己提交candidate或baseline。283个本地测试和1次真实GLM零行情、零score canary
均通过；真实canary费用`$0.00223803`。这只是harness机械验收，新的正式实验尚未启动。

v4第一次扫描新候选数据时传错了contract文件，远端在第一份source、任何target/fit/provider/
score之前拒绝执行。数据没有坏，也没有理由跳过它。交换层补齐stderr和科学source hash后，
同一source用正确冻结contract和新ID通过零分数canary；完整candidate admission已用另一个新ID
重跑。这个例子固定了重跑边界：评分和付费前、原因明确且已修好的执行错误可以重跑；有效低分、
模型失败、合法timeout，或已经打开结果后想改条件，都不能为了分数重跑。

完整重跑随后通过：39/39个候选均满足冻结的数据语义，按预定分层顺序选出3个Train、8个Dev
和20个Final；没有计算target、没有拟合、没有provider调用。v4的新数据入口已经具备可审计清单，
但正式付费实验仍要等精确代码/spec提交、私有origin发布和剩余预算复核。

随后v4 spec和31份入选回执完成绑定：累计Train观察为6,589,738，Final覆盖4个UTC日期。
291个测试、610.5万行refit canary、精确Linode派生缓存清理canary、完整Codex工具循环canary，
以及真实GLM零行情/零score terminal canary均通过。账本中第一组三路线的保守上限为
`$25.32114432`，低于learning可用`$52.644617648`；正式启动前只剩精确commit、私有tag发布
和发布后hash复核。

发布前最后一次完整canary还发现了一个本地问题：训练工具结束后，下一条解释工具偶发抢不到
broker锁。失败发生在synthetic数据、0 Tinker、0正式score环境，现场保留。修复后相邻工具会
短暂等待，持续争用仍停止；不会重采controller或重跑trial。新增正反测试后全套293项通过，
新ID的完整canary也通过。
