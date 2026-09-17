# Data Scientist Harness

这是给内层 controller 用的数据科学工具和检查规则，不是另一个 LLM。
下面的 Codex/GLM 图只描述旧的 controller 接入方式，**不是整个项目的
最高层架构**。新的分层设计见
[`CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md`](../supervisor_harness/CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md)：
最外层是 GPT-5.6-Sol + Codex Supervisor Harness；内层 controller 自有
Research Harness；controller 工具会话与 researcher 执行必须分属两个
不同的 E2B sandbox。旧接入目前没有证明这种双 sandbox 隔离。

```text
Codex：执行、调用工具、维护会话
  Controller（GLM）：决定下一步研究什么
    Data Scientist Harness：查资料、检查数据和特征、运行trainer、保存证据
```

外层的self-iterating data science反复使用这一层：发现数据问题就回去研究数据；发现
特征没信息就改表示；特征有信息但训练没学到，就研究trainer。不是清理一次数据就结束。

我们改harness是人为工程改动，不算agent自进化。同一组实验固定harness，记录agent
如何根据反馈调整方案；是否提高另用独立评估判断。发布与归因规则见
[Harness版本记录](../HARNESS_VERSIONS.md)。

## 已实现什么

| 部分 | 代码 | 实际能力 |
|---|---|---|
| Codex接入 | `run_controller.py`、`broker.py` | 沿用Codex/GLM Responses代理，通过MCP调用已登记工具；提交后退出 |
| 文献 | `literature.py` | 联网查Crossref元数据；读取公开HTML/text；记录URL、字节hash、实际读到的文字范围 |
| 时序和特征 | `profiles.py` | 分布、缺失、变化率、连续静止、时间缺口、日期差异、特征与固定目标的关系 |
| 训练 | `worker.py` | 复用Ridge、ElasticNet、RandomForest、HistGradientBoosting；独立限时CPU进程 |
| 计算前检查 | `sanity.py`、`checked_learning.py` | 原始grid、生成特征、归一化后数据、评分输入分别检查；实际计算放在检查后的callback中 |
| 研究轨迹 | `trajectory.py` | 运行前保存假设与判断标准，运行后绑定完整结果与解释；失败也必须记录 |
| 记录和权限 | `store.py`、`broker.py` | 数据/代码/运行版本绑定、每次工具调用记录、候选结果核对、当前发现与历史archive分开 |
| 验证前检查 | `handoff.py` | 检查完整数据科学报告，再核对原有独立验证要求；自身不运行Dev/Test |
| 来源方案与时间规则 | `source_study.py`、`temporal_contract.py` | controller自己填写规则，先运行合成时间边界检查，再登记第一份有效方案；不自动准入真实数据 |
| 体育逐事件数据 | `sports_event_contract.py` | 区分历史PBP状态建模、描述性市场反应、实时lead/lag和可执行P&L四层证据；按game切分，禁止把历史回填时间当成实时到达时间 |
| 体育方法library | `sports_method_library.py` | 分状态预测、市场反应和校准列出当前可执行方法、待补能力、研究来源与适用限制；library不替controller选赢家 |
| 一次性Dev闸门 | `sealed_dev_gate.py` | 先固定cohort、reward和evaluator，再完整物化Dev；评分权在读取任何Dev label前消耗，崩溃也不重看 |
| 本机文件检查 | `io_preflight.py` | 付费前拒绝云端占位的账本文件；不下载文件，不代替完整账本核对 |

新方法通过`request_capability`提出，记录研究理由和要补的测试；不是永久只能用四种。
但新代码不能未经检查直接成为可执行工具。这一版不提供任意shell、市场数据购买或下载工具。

## 一轮怎样运行

先读当前发现和数据检查。查相关资料并说明适用条件；统计原始序列；提出特征并检查；
解释保留这些特征的理由；选择trainer和参数；保存预测与结果；选一个候选或说明为什么
暂时不训练。所有实际调用、错误、参数和来源都保留，不只保留最后的结论。

数据未通过，训练入口不能启动子进程。文献读失败不能登记为读过；变更特征需要新检查；
同一训练方案不会因分数不好自动重跑。第一次候选确定比较时期和评分汇总方式，随后只改
特征或trainer中的一层，方便判断原因。新目标、新数据要开新的研究定义，不能改旧记录。

这里的后段check仍是已经开放的Train诊断，不是新的Dev。归一化和模型只拟合更早、标签
当时已可用且不跨市场隔离边界的行。静止行不因为未来没变化就被删掉。没有数据不填成0；
明确使用persistence预测回退不等于把缺失的源数据填成0。

完整32项检查不是全部自动修复器：不同来源仍需对应的检查代码与真实证据。Train内CPU
试验先要求来源、覆盖、字段与因果重放四阶段通过；正式验证前仍须完整八阶段通过。
Controller不能自己签发通过报告，也拿不到新Dev/Test工具。

体育或其他逐事件研究还要先运行`probe_sports_event_contract`。历史play-by-play有比赛时钟、
比分和事件类型时，可以用于训练state model；但没有当时的本机接收时间，就不能用来证明
谁先调价。只有市场价格历史、candles或屏幕深度，也不能证明订单能成交。可执行收益还需要
同一账户的order send、ack、fill、cancel ack和当日费用。Train/Dev/Final必须按整场比赛
切开，不能把同一场的不同plays随机分到不同集合。

Controller用`inspect_sports_method_library`按研究层查看方法。当前市场反应层能执行zero-change
对照和Ridge、Elastic Net、Random Forest、Histogram Gradient Boosting；GAM、XGBoost、
game-clustered local projection和held-out calibration仍是`capability_required`。同一候选
必须固定数据、target、horizon和game split，只改变一个因果层；方法多不等于一次混用。

正式Route-Dev不是controller可反复查询的调参工具。`sealed_dev_gate.py`在下载Dev价格前先固定
全部50场资格清单、唯一candidate、baseline、primary metric、方向和evaluator源码hash；物化时
50场必须全部成功且不能按label或score删题。runner在读取第一个Dev label之前永久消耗唯一一次
evaluation allowance，失败也不补一次。sealed Final仍由另一个入口保留，Dev闸门不能打开。

从数据科学角度怎样设计实验、读每轮记录，见[实验设计与轨迹](../EXPERIMENT_DESIGN_AND_TRACE_2026-09-10.md)。
它是设计草案，不是已经完成的真实数据验收或正式实验。

## 如何查看、运行

从仓库根目录运行单元与回归测试：

```sh
PYTHONPATH=research/market_rsi:research/market_rsi/validation_tools:research/market_rsi/source_review_tools:research/market_rsi/tests python3 -m unittest data_scientist_harness.test_harness data_scientist_harness.test_dispatcher data_science_tools.test_pipeline test_source_review_v2 test_source_dispatcher_v2 test_historical_grid_learning -v
```

免费端到端canary（每次必须换全新ID；需要允许本地loopback和公开网页访问）：

```sh
PYTHONPATH=research/market_rsi python3 research/market_rsi/data_scientist_harness/canary.py --output research/market_rsi/artifacts/data-scientist-canary-FRESH-ID
```

这是实际Codex、实际HTTP请求与实际CPU拟合；LLM回复和12行市场数据是合成测试夹具。
**不是金融simulator，不是GLM自主研究，也不是策略收益。** Fixture账只是测试计数，
不写入原来的真实费用账。

`prepare.py --help`提供准备新工作区的入口，需要runner核对的当前发现、质量报告及hash，
以及`--release`指定的发布回执。运行源码必须已commit、加版本tag并push到自己的GitHub。
可选输入仅为已开放Train的七文件缓存，加上`sanity-contract.json`和其中引用的三份
runner证据。它们分别检查源数据单位/时钟、未来修改不会影响过去特征、预处理实现一致性，
同时绑定数据与实现hash。每个特征的单位、检查阈值、例外与理由必须明确，不能补隐藏默认值。
合成证据只用于canary，真实来源要另做检查。可按明确文件hash带入过去的round archive。
`run_controller.py --help`是付费GLM入口：要求同源码/同运行版本的成功canary、原授权账本、
可用预算与无未结束调用；启动前再次核对远端版本，与旧dispatcher共用排他锁。额度预留不是消费，实际调用沿用
原追加式费用账。v1.3.0已完成真实GLM方案会话但尚未训练；v1.4.0目前只有免费工具链验证，
不能把脚本化canary算成GLM研究。详情见[9月12日记录](../TEMPORAL_CONTRACT_2026-09-12.md)。

工作区里的主要记录：

- `activity.jsonl`：按顺序排列的调用，链接每条完整记录；hash链检测改动，不宣称能抵抗有磁盘写权限的系统管理员。
- `records/`：搜索、阅读、研究理由、统计、错误和训练回执。
- `trials/<id>/`：运行前`intent.json`、计划、进程、stdout/stderr、预测、结果或失败、回收记录，以及运行后`reflection.json`。
- `trials/<id>/sanity/`：四个检查位置，每处三份报告；成功结果必须核对全部12份报告。
- `research-trace.md`：按次序读本轮问题、实际调用、前后分数和判断。完整数字与引用在`research-trace.json`。
- `round-archive.json`：这一轮的决定、各次计划/结果/解释及检查和研究证据。历史不冒充当前QA。
- `session/assessment.json`：Codex退出、实际调用数、终止确认与计量结果。

## 本项目单独维护和运行

公共代码固定为共享仓库的 `df963b02f8e1fae7db4f4d99d34507e1f339b416` 版本，五个依赖文件保存在本项目的
`../ds_harness_core/`，逐字节核对；运行时不读取另一个项目的共享源码目录。
这是明确选择的共享预发布提交，不声称上游已合并或发布；本项目另行测试、发布。
新工作区保存这五个文件，版本/hash进入记录。除统计外，现接入数据与时序的强制检查。
适配器明确使用毫秒grid，不伪造原始tick的更细时间顺序；合法长缺口与短时相关配对分开处理。
未改评分行、特征公式、目标、四种trainer和选择规则，但合法输入边界收紧。
另一项目升级不影响这里；我们自己的升级单独检查，旧实验不变。

独立CPU环境在 `research/market_rsi/.runtime/data-scientist-py312-20260910/`。
五个数值计算包固定在 `requirements-cpu.txt`；该环境不上传GitHub，也不修改
原有Python环境。以下命令使用仓库根目录，环境建好后无需读取另一项目：

```sh
DS_PY=research/market_rsi/.runtime/data-scientist-py312-20260910/bin/python3
PYTHONPATH=research/market_rsi "$DS_PY" -m unittest data_scientist_harness.test_core_adoption -v
PYTHONPATH=research/market_rsi "$DS_PY" research/market_rsi/data_scientist_harness/adoption_canary.py --baseline-canary research/market_rsi/artifacts/data-scientist-codex-canary-20260910-05 --output research/market_rsi/artifacts/shared-core-parity-FRESH-ID
```

第二条会分别用旧冻结代码和新代码做四次小型CPU拟合，精确比较完整统计、训练报告、
行顺序、mask和预测；训练报告只排除耗时。全部数据与文献回复都是合成夹具，
没有市场数据、联网检索或模型消费。它不替代真正Codex工具canary，也不是金融结果。
该独立环境目前只覆盖CPU/固定回复canary；真实GLM付费依赖和准入仍需单独核对，
不能凭这次通过就启动付费实验。

## 当前边界

- 公开阅读支持HTML/text，尚不支持PDF或登录后页面；403明确失败，不绕过访问限制。
- 每个页面最多2MB，子进程30秒；每轮公开响应体预留10MB。它是有边界的检索工具，不是全网完整文献库。
- 基本统计不是完整平稳性检验、有效样本量估计或盈利证据；条件相关、区间与完整特征家族研究仍需补接。
- 当前适配器只支持既有grid输入，不支持recorded-event特征。历史窗口依赖与当前行缺失的组合可能被保守拒绝，尚无已验证的例外；不是所有成交、深度或新来源都已接入。
- 新的体育事件contract目前只检查controller填写的软件规则，不读取或认证真实PBP/市场文件；真正接入recorded-event训练前仍需runner逐文件核对manifest、授权、映射、时钟和split。
- 保存的是候选定义与预测，不是可直接部署的模型权重。正式验证与部署要另走原有runner。
- 原冻结实验不改。当前Vantage片段覆盖不足，不能因为这套工具通过canary就启动正式训练。
- canary04曾出现一次调用入口`Errno35`，后续05未重现；已补入口错误位置记录，具体系统调用原因仍未查明，不能写成已彻底修复。

开发依据与适用限制见[文献记录](../LITERATURE_TO_HARNESS_2026-09-10.md)，
实际验收及失败见[当天记录](../DAILY_LOG_2026-09-10.md)。
