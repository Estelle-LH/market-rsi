# NFL prediction-market self-evolution：下一版怎么跑

日期：2026-09-15
状态：数据与方法的开发版；还不是正式成绩

## 先说结论

是的，下一版需要更多数据，也需要更多方法。但“更多”不能理解为把全部数据、特征和模型
一次混在一起。那样即使分数变好，也不知道为什么。

下一版采用两层学习：

1. 用2021–2024年的NFL play-by-play学习比赛状态，例如当前比分、剩余时间、down和场地位置
   对胜率有什么影响。
2. 用2025年的play和Polymarket成交学习市场反应，例如一个play发生后30、60、300秒，
   主队合约价格怎样变化。

系统现在再增加一层 Strong Harness。Codex `gpt-5.6-sol`读取完整实验轨迹，主动发现数据、工具、
feature、trainer或评估上的瓶颈，提出并实现Harness候选；候选必须通过历史回放、正反canary和
回归测试，每批只选择一个修改给下一批实验使用。Research Controller仍在冻结Harness内选择数据、
特征、模型或校准方法。Runner负责守住Train/Dev/Final、时间、费用和评分。

## 现在真实有多少数据

| 数据 | 数量 | 用途 |
|---|---:|---|
| 2021–2025 nflverse | 1,424场，247,284个play行 | 比赛状态研究 |
| 2021–2024 state history | 1,139场，198,513个play行 | 训练较稳定的state model |
| 2025完整比赛 | 285场，48,771个play行 | 按时间分Train/Dev/Final |
| 2025 Polymarket可映射比赛 | 253场 | moneyline、spread、total等市场目录 |
| 其中market Train | 163场，480,748笔成交，25,957个play | 已生成完整训练面板 |
| Route-Dev | 50场 | 每个block只打开一次；看过后进入历史 |
| sealed Final | 40场 | 设计结束后只跑一次 |

253场市场已经100%映射到nflverse和Sportradar比赛。映射使用明确的provider简称规则，
不是模糊猜测；两场周六比赛的日期差异也只在队伍完全一致、相邻一天且唯一时才接受。
Final目前只建立了比赛目录，没有打开价格、成交或结果。

## 12场canary和完整Train告诉了什么

先按赛季时间均匀选12场Train，不看成交量、价格、比分或结果。结果是：

- 60,189笔公开历史成交；
- 1,947个有Sportradar wall clock的play；
- 30秒后有新成交价格的play占95.69%；
- 60秒后占99.49%，最差单场也有97.14%；
- 300秒后占100%；
- 60秒的平均绝对价格变化约0.0314，也就是3.14个概率百分点。

标签要求play之后真实出现一笔新成交；不能把play前的旧价格沿用到未来，再伪造成零变化。
这说明旧的稀疏price-history接口不适合逐play学习，但public trade tape可以继续扩。12场只
用于证明数据链可用，不拿来报告模型优劣。

随后已把同一套规则扩到全部163场Train：

- 480,748笔窗口内成交，393,134个不同成交时间戳；
- 25,957个play；
- 30秒标签覆盖80.27%，60秒覆盖91.34%，300秒覆盖99.10%；
- 60秒平均绝对价格变化为0.02715，即2.71个概率百分点；
- 163场都完成，0自动重试，0达到20,000行截断；
- Route-Dev和Final都没有打开。

全量覆盖低于12场canary，说明12场均匀样本偏向交易更活跃的比赛，不能用小canary估计整季
难度。缺少play后新成交的行保留为缺失标签，不补成零。现在数据量足够开始Train内部的方法
检查，但还没有正式模型成绩。

## 第一版固定研究问题

给定一个play前的比赛状态、play发生后可观察到的事件结果，以及play前最后一笔市场成交，
预测60秒后的主队moneyline价格变化。当前历史数据只能支持描述性market-response研究，不能
证明真实交易时可以比市场更早收到这个play。

- 主要target：`home price(t+60s) - home price(pre-play)`；
- 辅助target：30秒和300秒；
- 主要单位：概率百分点，同时保留原始0–1价格；
- 固定对照：预测价格不变，也就是变化为0；
- 不把trade print称为bid/ask、历史L2、我们的fill或可交易PnL。

60秒在看Dev之前选定，因为canary已有99.49%覆盖，完整Train仍有91.34%，同时比300秒更接近
play后的直接反应。30秒和300秒只作稳健性检查，不能根据哪个分数更漂亮临时换主要target。

## 方法不只是一串模型名字

### A. 比赛状态层

目标是得到当时的比赛胜率或状态变化。先做可解释、能校准的低复杂度模型，再做更强的
非线性模型。

- generalized additive model；
- tree/boosting win-probability model；
- held-out calibration；
- 固定的简单状态基线。

### B. 市场反应层

同一批play、同一target、同一split上比较：

- zero-change persistence；
- Ridge；
- Elastic Net；
- Random Forest；
- Histogram Gradient Boosting；
- game-clustered local projection，用来分别看30/60/300秒反应。

前五种里，zero-change和四种CPU trainer已经能执行。local projection已完成Train-only开发和
测试，但仍未发布，正式Controller不能调用。GAM、XGBoost和专门的calibration目前只是library
里的候选；补依赖、测试和新Harness版本前不能偷偷执行。

### C. 校准与组合层

状态模型和市场反应模型先分别通过检查，再考虑校准或组合。不能同一轮同时改特征、trainer、
target和校准，否则无法归因。组合模型需要保留组件ablation。

## Strong Harness怎样与实验一起进化

实验和Harness分别保留lineage：`H0 → H1 → H2`与`M0 → M1 → M2`。Round N暴露的问题只能
产生下一版Harness候选，不能改规则重跑同一批分数。Codex可以修改data acquisition、data
quality、feature/target工具、trainer/evaluation、context、工具接口和Archive格式；不能修改
split、sealed Final、预算、ledger、hash、不得按分数重试和独立grader。

每次先把问题写成证据化observation，再提出多个候选。候选不能看下一批Dev/Final，也不能在
验证时购买数据。通过旧失败replay、新canary和回归的候选中，先解决更严重的瓶颈；同级优先
更小的patch和更低的下一轮成本。每批只合入一个主要改变，保证能够归因。

当前第一个blocking observation是：只有163个独立比赛，而旧Harness不能搜索、验样、询价或
购买更多有许可的数据。第一项候选因此是Data Acquisition，不是继续换trainer。详细设计和
开发合同见`CO_EVOLVING_STRONG_HARNESS_2026-09-15.md`。

## Research Controller内部的Self-evolving发生在哪里

在每个冻结Harness版本内部，Research Controller的自进化过程是：

1. Controller读取全部Train资料、方法library、费用和之前每轮archive。
2. 它提出一个明确假设，并选择本轮要改的数据分配、特征、trainer或校准中的一层。
3. Runner在真实Train上执行同起点的候选，并用当前Route-Dev block统一评分。
4. Controller拿到aggregate结果、错误、费用和稳定性检查，写下“支持/不支持/还不知道”。
5. 这个完整记录进入Archive。下一轮可以保留父模型、换一个方法，或退回简单基线。
6. 一个Dev block一旦反馈给Controller，就不再是假装未见的数据；它进入历史，后面的时间块
   成为新Route-Dev。
7. 所有设计结束后，冻结一个方案，只运行一次40场Final。

所以它每轮学到的不是一句模糊“经验”，而是：什么数据上、改了哪一层、哪种方法、用了多少
费用、在哪些比赛支持或不支持假设、失败属于科学结果还是基础设施问题。

## 每轮最低记录

- 父checkpoint和候选checkpoint；
- 本轮唯一改变的层；
- 数据、代码、selection、plan和结果hash；
- 每个方法的完整参数、训练行数、比赛数、失败和耗时；
- 相对zero-change的paired MSE差；
- Pearson IC、rank IC、calibration slope；
- 赢过基线的比赛比例；
- 按game block计算的不确定区间；
- Controller调用、工具调用和实际费用；
- 下一轮为什么继续、换路或停止。

## 如何防止“数据更多”变成过拟合

- game是独立单位，同一场的play不能随机拆到Train和Dev；
- 按时间前后切，不让未来数据训练过去；
- 每场等权或明确保存权重，不能让成交多的一场决定全部结果；
- 12场pilot只做工程验收，不拿来挑正式赢家；
- Route-Dev分块逐次打开，看过的block以后算历史，不重复当新证据；
- 40场Final直到最后都不给Controller；
- 不能因为分数差重跑、换题、删静止样本或改target。

## 接下来执行顺序

1. **已完成：**把公开trade tape扩到全部163场Train，保存逐请求回执、hash、缺口和截断状态。
2. **已完成：**生成完整play×trade panel，包含possession、down/distance、field position、score、
   game clock、pre-play market price和event type；没有可靠来源的timeout没有擅自回填。
3. **已完成：**在Train内部完成zero-change和四种现有trainer的同数据滚动对照；这仍是工程
   与建模检查。Random Forest的每场等权MSE相对zero-change低4.06%，Ridge和Elastic Net约低
   3.7%；没有打开Route-Dev或Final。详见`NFL_TRAIN_METHOD_SCREEN_2026-09-15.md`。
4. **已完成开发版：**补game-clustered local projection，在同一20,836个Train play上分别估计
   30/60/300秒反应。得分反应从30秒继续增加到60秒，60到300秒基本持平；这是描述性结果，
   不是因果或正式成绩。详见`NFL_TRAIN_LOCAL_PROJECTION_2026-09-15.md`。
5. GAM/XGBoost和calibration之后逐个进入，不一次改四层。
6. **开发中：**Strong Harness和Data Acquisition合同已实现并通过专项测试。下一步先取得免费
   数据目录、3–5场样本、license和报价，不立即购买。
7. 固定并发布新的Harness版本、commit和tag，之后才开始Controller正式多轮实验。
8. 先滚动使用50场Route-Dev；设计冻结后才打开40场Final。

当前没有正式Dev/Final模型成绩，也没有PnL结论。Train内部已经看到简单模型比zero-change低
约2.0%–4.1%的MSE，其中Random Forest平均最好，但这只能证明研究链能发现小幅Train滚动信号。
数据规模已经从很短的小时片段升级到多个赛季和163场完整Train，2025成交可以与25,957个
play高覆盖对齐，方法library和评估边界已有可执行入口。
