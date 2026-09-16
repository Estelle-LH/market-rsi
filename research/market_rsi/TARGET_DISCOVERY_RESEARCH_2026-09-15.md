# Target Discovery Adapter Research

## 观察到的问题

`dsh-v1.6.1`已经允许open discovery改变target和horizon，但NFL数据adapter仍在源码中固定
`30/60/300`秒。刚完成的Train-only screen显示30秒相对skill稳定高于60秒，300秒明显更弱。
如果工具不能接受researcher提交的新target spec，系统实际上仍只能在人工预设菜单里选择。

本次改变target构造与审计能力，不改变任何已完成实验，不打开Route-Dev/Final，也不根据旧Dev
结果选择新target。

## 2026-09-15查询与阅读记录

### 查询1

`direct multi-step forecasting horizon evaluation primary paper DOI direct versus recursive forecasting`

- 阅读：Chevillon and Hendry, *Non-parametric direct multi-step estimation for forecasting economic
  processes*, International Journal of Forecasting 21(2), 2005。
- DOI：https://doi.org/10.1016/j.ijforecast.2004.08.004
- 阅读部分：摘要与direct multi-step方法说明。
- 发现：不同horizon可以各自直接拟合目标；direct方法让训练目标与目标horizon一致，但效率和
  robustness取决于模型是否misspecified及过程是否nonstationary。
- 对本项目的用法：每个horizon生成独立target；不把一个短horizon模型递推成更长horizon。
- 限制：论文研究一般经济时间序列，不证明NFL prediction market的任何horizon有alpha。

### 查询2

`forecast comparison multiple horizons normalized loss baseline primary paper`

- 阅读：Quaedvlieg, *Multi-Horizon Forecast Comparison*, Journal of Business & Economic Statistics。
- DOI：https://doi.org/10.1080/07350015.2019.1620074
- 阅读部分：setup、uniform/average superior predictive ability与结论。
- 发现：逐horizon挑最好会产生隐含multiple testing；联合比较应保留horizon-specific loss，并
  预先定义uniform或weighted-average主张。
- 对本项目的用法：adapter只materialize完整candidate grid；报告每个target相对自身baseline，
  不自动选winner。若以后做multi-horizon confirmation，权重和主张必须在Dev前冻结。
- 限制：本次不实现完整multi-horizon SPA检验，当前仍是opened-Train discovery。

### 查询3

`limit order book event time forecasting paper event based sampling primary`

- 阅读：Shi and Cartlidge, *State Dependent Parallel Neural Hawkes Process for Limit Order Book Event
  Stream Prediction and Simulation*, KDD 2022。
- DOI：https://doi.org/10.1145/3534678.3539462
- 阅读部分：摘要、event/state interaction和event time/type预测定义。
- 发现：LOB是event-driven continuous system；event时间与event类型可以联合建模，不能把不规则
  事件流默认当成等间隔clock-time序列。
- 对本项目的用法：加入“第N笔严格晚于decision的trade”target，与fixed elapsed seconds并列，
  但不声称NFL二元市场等同于连续LOB。
- 限制：我们的Polymarket历史数据只有trade prints，没有完整LOB event types或实时arrival。

### 查询4

`high frequency event time versus calendar time market microstructure prediction`

- 阅读：Berardi and Serva, *Time and Foreign Exchange Markets*, 2003。
- URL：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=423921
- 阅读部分：摘要中calendar time与business time定义及conditional variance结论。
- 发现：calendar time把交易记录视为连续过程的离散采样；business/event time按报价/交易顺序推进，
  活跃与不活跃期间的时间含义不同。
- 对本项目的用法：fixed-time和event-count target必须使用不同名字和不同合同，不能混称同一个
  horizon。
- 限制：外汇市场与NFL prediction market结构不同；这里只支持“值得分开测试”，不支持优劣结论。

## 比较过的实现方案

1. **继续扩充源码常量。** 最简单，但每次新增horizon都要改代码，而且controller并不真正拥有
   target选择权；拒绝。
2. **允许任意Python target函数。** 最自由，但会让controller执行未审计代码、改变数据population
   或读取sealed数据；拒绝。
3. **选择：typed target spec。** Researcher选择有界fixed-time或event-count target、target
   transform和support policy；runner执行固定、可测试的materializer。新target family仍可提案，
   但需要下一版Harness实现，不能用prose绕过。

## 计划实现

- `target_discovery_contract.py`：验证并冻结opened-Train target spec；至少一个fixed-time或
  event-count target，列表唯一且有界；禁止Route-Dev/Final。
- `materialize_controller_targets.py`：从已hash的163场Train source receipt重建pre-price与label；
  fixed-time使用horizon内最后一笔严格晚于decision的trade，event-time使用严格晚于decision的
  第N笔trade并受最大wall-clock限制。
- 支持`price_delta`或带预先deadband的`direction`，不允许按结果大小删行。
- 输出每个target coverage、活动度、exact-zero比例、共同support和所有source hash；每个play都
  保留，不可用target写空值。
- 单元测试覆盖边界时刻、静默carry-forward、event第N笔、最大时间、direction deadband、乱序与
  非Train访问。

## 已实现和已验证

- 新增typed target spec。Controller/researcher可以在opened Train上选择1–3600秒的
  elapsed-time horizons、未来第1–64笔trade的event-time horizons、`price_delta`或带预先
  deadband的`direction`，并明确选择per-target或common support。
- materializer会重新核对source receipt、163场selection、每场panel、manifest、raw PBP和
  trade文件hash。每个play都会保留；没有合法未来成交的target写空，不补零、不carry-forward，
  也不按结果大小删行。
- fixed-time label只允许decision之后且不晚于deadline的成交；event-time label只允许严格晚于
  decision的第N笔成交，并受预先声明的wall-clock上限约束。两类target使用不同名字。
- Route-Dev和Final访问在合同层直接拒绝。adapter只生成候选target和Train统计，不给reward、
  不选winner，也不把opened-Train结果写成正式confirmation。
- 11/11项新增专项测试、254/254项Data Scientist Harness全回归、59/59项sports全回归通过。
- exact-source canary `data-scientist-codex-canary-20260915-12`通过：18次工具调用、4次合成CPU
  拟合、1次公开搜索、1次公开阅读、0次真实Tinker调用、provider cost `$0`，没有打开新Dev/
  Final。账本中的`$0.000629856`是fixture计量演练，不是供应商费用。

## 真实opened-Train materialization

`dsh-v1.6.2`发布后，冻结spec
`e83bdc66686bfdb7c91ffd68a6c38fe2493b8cff6f40d35add5704c7cd248d8e`在同一163场Train上生成
10/15/20/30/45/60/90/120秒，以及未来第1/2/5/10笔成交的price-delta target。它没有reward，
没有自动选winner，Route-Dev/Final均未打开。

- 共25,957个play；全部12个target共同可用12,808行。
- clock-time覆盖从10秒的52.07%逐步升到120秒的96.79%；30秒80.27%，60秒91.34%。
- event-time覆盖从第1笔的99.10%降到第10笔的83.66%。这说明event count和elapsed seconds形成
  不同的数据population，不能按raw MSE直接横比。
- event targets的样本均值轻微为负，elapsed targets轻微为正。当前只记为需要解释的selection/
  timing信号，不当作可交易结论。

下一步的`experiments/nfl_target_grid_screen.py`已经实现并通过3/3专项、5/5 experiments回归。
它在相同整场rolling split中为每个target分别计算zero-change baseline，并固定Ridge与Random
Forest；只按相对skill、三折稳定性、逐场胜率、日期块区间和coverage形成opened-Train shortlist。
实验尚未运行，需先commit、annotated tag和push精确源码。

第一次score run `nfl-open-train-target-grid-screen-20260916-01`在拟合前停止。163场中的
`2025_03_ATL_CAR`有3个play缺`home_price_pre`；这3行也没有任何可用target。v0.1.0 runner
错误地要求“所有保留play都有完整feature”，而正确边界是“任何有target、会进入拟合的行必须有
完整feature”。失败run保留，0拟合、0费用、Dev/Final未打开。

本次没有新增文献搜索；直接复用本记录已经研究并实现的`unavailable_do_not_filter`规则，适用性
是：原始play仍留在target materialization和coverage分母中，但没有任何target且feature不完整的
行不进入设计矩阵；如果任一target已观测而feature缺失，仍然整轮拒绝。修复增加正反测试，必须
用新commit、新tag和新run ID验证，不能续跑`…-01`。

修复版`nfl-open-train-target-grid-screen-20260916-02`完成。25,838行进入设计矩阵；119个无任何
target且feature不完整的原始play只留在coverage分母。24个target×method组合中16个通过全部
预先条件。冻结shortlist为30秒RF（6.01%，最弱折4.78%）、20秒RF（5.36%，最弱折4.68%）和
45秒RF（5.73%，最弱折4.48%）。60秒RF仍改善4.06%；event第5笔RF改善4.51%并满足规则。
完整结果和限制见`NFL_TARGET_GRID_RESULT_2026-09-16.md`。

最重要的下一项诊断是same-support sensitivity。当前每个target使用自己的eligible rows；相对
zero-change skill解决了scale差异，却没有完全解决population差异。下一轮先在15/20/30/45/60秒
共同可用的同一批play上复查，不打开Dev。

same-support runner已实现并在精确源码发布后运行。它固定15/20/30/45/60秒、Ridge/RF和原rolling split；
排名先看最弱一折skill，再看aggregate skill。事前假设是30或45秒在两种方法下都进入前二。
这个规则只检验当前opened-Train解释，不能产生正式promotion。

run `nfl-open-train-target-same-support-20260916-01`完成并满足假设。五个target共同可用16,632
个full-population play，rolling check为7,368行。30秒在RF/Ridge分别改善6.04%/5.46%，最弱折
5.87%/5.17%；45秒分别改善6.09%/5.32%，最弱折5.28%/5.09%。两种方法均把30和45秒排前二。
60秒为3.98%/4.25%。这支持“30–45秒优势不只是population差异”，但不是独立数据验证。

状态：研究、adapter、真实Train materialization和下一步实验代码均已完成；rolling score待精确
源码发布后执行。`…-11`只因发布卫生检查后删除了源码末尾一行空白而被旧字节版本取代；它也
通过且费用为零，但不能作为最终release canary。
