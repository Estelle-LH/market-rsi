# 搭Harness时，先查方法，再写代码

2026-09-10。用户要求：每次做数据质量、Feature engineering、Trainer engineering等
组件时，先看文献怎么处理，再结合我们的数据决定。这里记录本次有针对性的查阅，不是
完整综述，也不表示下面的方法已经实现或在我们的数据上有效。

## 怎么记录每次研究

每项记录：问题 → 搜索词和来源 → 读到的方法与限制 → 可选办法 → 我们准备怎么测 →
代码与实际结果。已有研究可复用，但要重新检查条件是否适用；新问题、新方法或新数据
需要补查。不限于固定几篇论文，也不按数量凑任务。

“搜索到”“阅读相关章节”“已经实现”“在我们的数据上验证”分开记。搜本地摘要不算
联网搜索，读摘要不算通读论文，论文中的好结果不算我们的实验结果。

## 本次查了什么

检索日期：2026-09-10，使用联网搜索与打开原文页面。实际搜索词：

- `site.otexts.com fpp3 stationarity differencing time series cross validation`
- `catch22 CAnonical Time-series CHaracteristics 22 Fulcher Lubba feature extraction paper 2019`
- `site.nber.org how often sample continuous time process presence market microstructure noise`

随后打开作者教材、出版社论文全文页、作者公开PDF，阅读下列相关章节。网页工具访问
记录保留在当前任务；本文件是自写阅读笔记，不冒充网页/PDF原始快照，也未计算论文文件hash。

### 1. 序列不稳定时，差分不是自动答案

来源：[Hyndman与Athanasopoulos，FPP3 §9.1](https://otexts.com/fpp3/stationarity.html)。
阅读范围：平稳性、差分、随机游走和单位根检验部分。

文献结论：差分可减少趋势，但过度差分会引入本来不存在的动态关系；检验有条件，也可能
给出不同答案。这个讨论主要服务于相应时序建模方法，不是要求所有模型都先做差分。

对我们的启发：先看分布和时间依赖，再由controller比较原值与变换。不能因为某个特征
长期不动就直接删除，也不能为了让它“动起来”强制差分。这里的“不自动删除”是我们的
研究规则，不是这章直接证明了静止特征在预测市场有用。

待验证：原值/变化量在同一Train划分、目标、trainer下的对照；保留变化前后的缺失和边界
记录。尚未运行，不修改当前t7。

### 2. 系统研究序列特征，而不是凭感觉堆列

来源：[Lubba等，catch22，2019](https://link.springer.com/article/10.1007/s10618-019-00647-x)，
DOI `10.1007/s10618-019-00647-x`。阅读范围：摘要、引言、特征选择方法及结果相关段落。

论文从大量候选中筛选紧凑、较少重复的时序特征，包含分布、时间依赖和变化等信息。
验证任务主要是时序分类，不是我们的价格预测。因此可以借鉴它系统整理特征的方式，
不能直接把22个特征当成已经验证的交易信号。

待验证：先做基本逐字段统计，再按需要试更复杂的描述。预测输入必须只用历史窗口；
不能用整场结束后的序列特征预测该场中间时刻。还需检查常数、缺失和不规则时间间隔下
的定义。没有安装或运行catch22；是否采用仍由研究结果决定。

### 3. 高频数据有噪声，不代表应该直接扔掉

来源：[Aït-Sahalia、Mykland与Zhang，2005，作者公开PDF](https://www.princeton.edu/~yacine/sampling.pdf)。
阅读范围：摘要、引言、基本模型及不规则采样部分；未通读全部推导。

论文研究带微观结构噪声的过程参数估计：忽略噪声与显式建模噪声，采样频率的结论不同。
它不是证明任何预测模型都应使用最高频率，也不是证明我们的静止报价应该被删掉。

对我们的启发：原始数据保留，区分记录噪声与真实变化。采样间隔和噪声处理作为明确的
候选方案，在Train内比较；不靠“更平滑”宣称预测更好。二元概率价格、短市场寿命和
断流与论文模型不同，这些条件必须先核对。

待验证：先完成覆盖与时间审计，再比较声明好的表示或采样方案，不改变评分人群。
尚未执行；当前Vantage覆盖不足不能靠滤波补成完整日期。

### 4. Trainer比较要用过去预测后面的数据

来源：[FPP3 §5.10，Time series cross-validation](https://otexts.com/fpp3/tscv.html)。
阅读范围：滚动预测起点、训练范围、多步预测与训练误差的区别。

文献方法：各次预测只使用更早观测，并按预测跨度评估。我们的应用还需要处理标签可用
时间、重叠标签和整市场隔离；这些是结合任务增加的条件，不假称这章替我们验证了它们。

待验证：新trainer与基线使用相同目标和评分行；正常化只拟合更早的数据。特征有信息
但trainer没学到，和特征本身无信息要分开记录。该规则沿用时序评估skill的分层诊断；
不是新增一次正式验证。

## 当前工具能力核对

`historical_ingest_controller.py`与`historical_grid_learning_controller.py`的文献搜索
读取冻结摘要库；`literature_catalog.py`保存的是runner自写简介。刚完成的source-review
工具则检索已冻结的来源说明。不能把这些当成GLM每轮都会上网找新论文。

当前开发助手能联网查阅，本次已做。下一版controller仍需单独接好：提出搜索问题、
获得新的公开结果、读取相关方法、记录出处和采用理由。复用旧材料与新搜索要明确区分，
新工具要经过真实canary；本次没有宣称已接通GLM实时搜索，也没有启动新的付费模型。

本次已把开发要求写入本目录`AGENTS.md`，让后续修改必须先检查研究依据。它约束开发
助手，不会自动改变隔离运行的controller，也不改变原有实验冻结记录。

## Data Scientist Harness首版实现与补充查阅

2026-09-10。这一版复用上面的时序诊断与过去拟合/以后检查原则，不声称又通读一批论文。
具体代码在`data_scientist_harness/`，保留旧目标和源实现。新问题是：怎样让controller实际
查新资料、避免只凭标题记为阅读，以及怎样接入现有Codex而不丢失终止确认。

补充检索：`Crossref REST API access authentication query bibliographic`、
`scikit-learn 1.6 common pitfalls data leakage`、`Codex MCP stdio configuration`。
读取以下官方页面的对应章节：

- [Crossref访问与认证](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)：公共元数据接口与访问限制。选择无需密钥的元数据搜索；不是全文服务，不向它发送用户邮箱或私有数据。
- [scikit-learn1.6常见问题](https://scikit-learn.org/1.6/common_pitfalls.html)：预处理一致性、数据泄漏与Train-only拟合段落。复用已安装1.6.1的四种trainer，不升级运行环境。原例子的随机切分不照搬到金融时序。
- [Codex配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)：MCP command/args、tool timeout与工具配置段落。新增MCP route，沿用原代理；worker60秒加回收时间，MCP工具外层90秒。具体行为由真实CLI canary检查，不仅凭文档判断。

备选办法：继续只搜本地摘要（不足以找到新资料）、接另一个收费检索服务（这一步不必要）、
自己重写Codex执行层（不采用）。先用公开元数据与HTML文本；PDF、登录站点和完整文献
覆盖仍未实现。取到页面、向controller交付片段和理解论文是三件不同的事。

实际验证：canary01的FPP3页面被HTTP403拒绝，未绕过限制；改用另一份可公开读取的
官方scikit-learn文档。canary03和05均实际读取其前6000个提取字符并记录URL、原始响应
hash与片段范围；Crossref返回元数据单独记账。回复是固定测试脚本，不算GLM读懂了论文。

四种trainer均经过新入口实际拟合；回归测试检查未来标签不改变拟合/预测、check数据不
影响归一化、整市场隔离、缺失处理与预算区别。真实Vantage QA失败在新入口阻止了训练。
这些是工程验收，不是验证了文献方法在预测市场有效；没有新市场评分或收益结果。

## 公共统计模块在本项目的独立接入

复用上述基本描述统计、过去拟合/以后检查和单层对照原则；本次没有提出新估计方法，
因此没有新增联网文献搜索。问题是如何复用同一统计实现而不依赖另一项目的可变源码或
Python环境。固定共享提交及三个文件hash，保留总体标准差、线性分位数、float32计算和
空/全缺失结果。拒绝无穷和算术溢出是明示的输入边界收紧，不能称所有非法输入也与旧代码相同。

比较过直接使用另一项目目录、全局安装同名包、消费者内固定源码三种接法；采用最后一种，
避免路径冲突和自动升级。新工作区同时冻结代码和依赖，不修改旧工作区。发现旧入口只因
导入时机而要求Harbor，改为真正使用沙盒时、读取凭据之前加载；未替换沙盒方法或预算规则。
这属于运行依赖修复，不是另一个金融方法实验。

验证：83项回归通过；两个独立子进程中，旧/新完整统计、四种trainer报告（仅排除耗时）、
行序/mask/预测精确一致。输入是合成夹具。完整工具canary和真实失败QA拦截另行通过，
不证明收益、因果时钟适配或新OOS能力。记录见[独立接入验收](SHARED_CORE_ADOPTION_2026-09-10.md)。

## 强制检查与每次实验的前后记录

2026-09-10。问题：仅有统计工具不保证训练前实际做过检查；只记最后的决定也难以看清
controller究竟验证了什么。本次修改计算入口和证据记录，不改目标或trainer公式。

复用本记录的过去拟合/以后检查、静止与缺数据分开、单层对照原则。补充核对的官方来源：

- 检索/页面定位：`NIST autocorrelation plot assumptions equally spaced`；
  阅读[NIST自相关说明](https://www.itl.nist.gov/div898/handbook/eda/section3/autocopl.htm)中
  定义与用途部分。采用分组时序描述，不把非等距tick的事件lag当作固定秒数，不从这套
  描述统计直接推出显著性或有效样本量。允许缺口与是否跨缺口配对分别定义。
- 复查：`scikit-learn 1.6 common pitfalls data leakage`；阅读
  [§10.1预处理一致性及§10.2数据泄漏](https://scikit-learn.org/1.6/common_pitfalls.html)。
  scaler仍只在更早的拟合行训练，评分使用同一个变换。把质量检查放在实际callback之前，
  测试NaN不能在变换后被静默隐藏。文档里的随机切分例子不直接用于这里的时序任务。

备选：只输出警告、在每个trainer旁边复制一套检查、调用共享强制检查。选择第三种，
但冻结共享提交与五个源码hash，由本项目自己验证适配器。共享`max_pair_gap_ns`将合法
安静缺口与短时配对分开；它不是数据充分性的证明，也不自动识别所有采集故障。

适用限制：当前是毫秒grid适配，没有恢复纳秒事件顺序；UTC日期不是交易session。
原始记录到grid的单位/时钟、kernel未来修改与预处理对照必须有真实输入绑定的证据；
测试夹具不能签发真实数据许可。recorded-event与更复杂历史依赖尚未接入。

代码：`sanity.py`、`checked_learning.py`、`trajectory.py`及其测试。当前合成检查覆盖
无穷、错序、缺口、静止例外、变换后NaN、未来修改、过期证据、原实现数值一致性、
先写假设后启动、失败保留和结果改动拒绝。真实数据上的有效性仍未验证。
新旧独立进程parity的20组数组完全一致，四份报告只排除耗时；不是新金融收益结果。

预先记问题/假设、事后单独记解释是本项目的实验记录规则，并非上述两份文献已经证明
能让LLM研究变好。要验证研究能力仍需固定harness的受控实验与独立评价。

## 首次真实调用暴露的工具字段缺失

2026-09-10晚。`tonight-data-scientist-design-20260910-02`连续发生acknowledgement
格式错误；实际MCP schema只说responses是array，没有公布内部id/handling/next_evidence。
固定回复的免费canary知道这三个字段，因此没有发现真实模型会被挡住。这是接口缺陷，
不是金融方法失败或GLM不会研究的证据。8个已计量turn共$0.437331474；中断第9个turn
暂留$0.90706311不确定上界。终止精确runner及其子进程，未启动训练或访问新Dev/Test。

针对新故障补查：`site.modelcontextprotocol.io tools inputSchema JSON Schema items array`。
读取[MCP官方Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
的Tool/inputSchema、tools/list、tool error处理部分，以及
[JSON Schema array](https://json-schema.org/understanding-json-schema/reference/array)的items规则。
这些是接口规范，不是声称某种提示会提高研究得分的论文。

选择公布嵌套items/required字段并在同一入口校验；没有放松科学门槛，也没有由执行方
代写acknowledgement。单纯改错误文字仍让模型首次猜字段，因此不够；反复付费重试不采用。
同类read_records、feature dispositions与枚举值一起补全。source-only状态明确不提供原始数据。
代码：broker.py。测试通过真实tools/list响应取schema构造合法调用，并检查原来的string
item得到可读且留档的ValueError；旧source/QA/预算门槛继续保留。测试与新release状态见当天log。

## 让无效工具调用收到错误反馈，而不是整轮立即退出

2026-09-10夜（UTC09-11）。真实03已成功inspect/acknowledge，第三份模型回复却把
`record_research-obj-1/2`当成工具名。解析器拒绝是正确的，但旧调用直接终止，不能收到
格式反馈。3次计量共$0.211773042；无文献读取、来源决定、拟合或新Dev/Test。

本次重读[MCP官方Tools错误处理§Error Handling](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)：
区分协议错误和工具执行错误；客户端可以把协议错误反馈给模型，但不保证恢复。
访问日期UTC2026-09-11，页面定位词`Self-Correction`、`Error Handling`，阅读451–485行。
采用有界反馈而非执行未知名称或猜测模型本意；此做法是否改善真实GLM完成率仍待验证。

v1.2.2仅在Data Scientist入口启用：解析失败先保存原回复/实际token费用，再生成明确标注
runner-authored的控制回执。它不是模型选择的研究动作，不会执行未知工具。最多2次反馈，
第3次解析失败终止；每次后续回复仍计入原turn/token/tool/美元上限。普通无提交文本仍终止，
旧入口默认行为不变。没有自动provider retry，也不把旧失败改成成功。

验证：回归重现原错误、第三次停止、坏hash和重复控制回执拒绝；免费真实Codex恢复canary
注入一份坏回复后，完成19次回复/4次合成CPU拟合。该canary不是GLM自主恢复或金融结果。

### 同一规范用于source-only收尾（v1.2.3）

复用前一节已阅读的MCP错误反馈规则，无新金融方法或新文献搜索。真实04在现有参数
说明下多次给defer填写work-order ID；报错只说没有selected trial，未明确要求空字符串。
也把search元数据ID放进read_records。新版本公布空字符串条件和可用的正确类型ID，
不自动改参数、补提交或将search当成reading。标准检查与专门无数据source-only检查
均通过；后者先拒绝错误ID，再用脚本下一条回复成功defer，不能当真实GLM已学会。

数据审计沿用已研究的原件保留、因果时钟、静止与缺口分开、不用未来变化筛选原则。
新读到旧split元数据后，增加保守的旧评估日期保护，不改变旧实验。字段范围检查只检查
矛盾，不声称价格在[0,1]就证明单位是概率。见CAPTURE_AUDIT_SCOPE_2026-09-10.md。
