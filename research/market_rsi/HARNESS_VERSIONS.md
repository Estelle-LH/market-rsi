# Harness版本和实验结果分开记

开发中：`data-scientist-harness-v1.6.0-dev`增加体育逐事件数据contract和有来源记录的方法
library。它把历史PBP状态建模、描述性市场反应、因果lead/lag和可执行P&L分开；要求按整场
比赛做时间切分，并明确历史回填时间不是本机实时到达时间、trade/depth不是我们的成交。
Runner侧已完成253场映射和完整163场Train-only trade/play面板：480,748笔成交、25,957个
play，60秒标签覆盖91.34%；Route-Dev/Final未打开。这不等于Harness已发布或模型已提高。
当前尚未发布tag、没有新训练或付费调用，不能用于正式实验归因。

同一开发版新增外层Strong Harness合同：Codex `gpt-5.6-sol`可以根据实验轨迹改进可进化外层，
但不能修改split、sealed Final、预算、ledger、hash、retry或独立grader。候选用历史replay和
新canary选择，每批只合入一个改变，不看下一批预测分数。首个Data Acquisition候选要求样本、
schema/timestamp检查、license、quote和独立单位覆盖齐全后，才允许请求人工购买批准。专项4/4、
sports合同9/9通过；尚未做真实provider canary、commit/tag或正式实验。

上一发布版：`dsh-v1.5.0`让controller填写可执行样本参数，并把完整历史改为可记录的分页读取。
188项测试、标准18调用/来源9调用的真实Codex免费检查通过。0新增Tinker调用、0行情拟合。
已发布commit`d455e3711b4d8914d4d8de5b2a7d8e9060c394a5`，release
`7c208b5c8d93c5c72b54b4f8896fe54044273f0fa93d6f590b97d53f735100f4`。
发布后的一次真实GLM续接已结束，15回复/17工具/0拟合，计量$1.891985364。
旧版本和旧方案不改；不是模型能力提升。
研究依据、参数范围与限制见[样本接口](SAMPLE_CONTRACT_2026-09-13.md)。

以下为之前的版本记录。

最新变更：`dsh-v1.4.1`按本次工具schema保留字符串参数，修复JSON文本被自动转成对象。
目标、训练算法、数据准入和预算规则未改。31项桥接测试+157项harness测试、专项与标准
免费真实Codex检查通过；旧`dsh-v1.4.0`及其失败会话保持不变。
详见[9月13日修复记录](JSON_TEXT_INTERFACE_FIX_2026-09-13.md)。

**我们改harness，是人为改进工具，不算系统自进化。**
固定harness后，controller自己提方案、做实验、看反馈并调整下一轮，才是我们研究的
自进化过程。是否真的提高，还要用独立评估证明。

## 开实验之前

先测试代码 → commit → 给该commit加版本tag并push到自己的GitHub → 核对远端 → 开新实验。

每次都记录版本号、完整commit、运行文件hash、Python/Codex版本，以及数据、标签、
目标、历史经验、特征、trainer和评分定义。数据和原始运行记录不因此上传GitHub。
同一组正式比较固定harness；改了harness，就单独记成新实验条件，不能直接算模型进步。

代码检查已放在 `data_scientist_harness/release.py`，不是只写在文档里：

- 不接受只有版本号、没有发布证据的工作区。
- 运行源码必须已提交，并与版本tag指向的commit逐字节一致。
- 核对远端tag及其commit；未push、指向不同提交、网络无法确认都不启动。
- 准备工作区和付费启动前核对；CPU训练、worker和独立验证交接也要求绑定发布记录。
- 工作区不原地升级。更换源码或版本会被拦住；旧工作区、结果和失败记录保留。
- 开发canary可以测试未发布代码，但明确记为`published=false`，不能算正式实验结果。

只检查实际冻结运行源码的范围，不要求把其他目录的未完成笔记或数据一并提交。
没有给所有旧脚本追加这道门；旧冻结实验仍按其原规则运行，新研究使用这个新入口。

## 版本表

| 版本 | Git定位 | 内容 |
|---|---|---|
| 旧开发版`data-scientist-harness-v1` | `e0f3ec83495b2d35917a6001bafa133b30533432` | 独立CPU环境和固定公共统计模块；没有正式发布tag，不倒填成已发布实验 |
| `data-scientist-harness-v1.1.0` | `dsh-v1.1.0` | 增加发布检查、实验归因字段，以及人为harness修改/agent自进化的区分；不改特征或trainer公式 |
| `data-scientist-harness-v1.1.1` | `dsh-v1.1.1` | 修正真实仓库中一次读取204个源码路径的Git超时；分批核对全部文件，检查标准不变 |
| `data-scientist-harness-v1.2.0` | `dsh-v1.2.0` | 接入固定共享质量检查和显式grid适配；原始/特征/归一化/评分四处检查；运行前假设、运行后判断及完整archive；不改原trainer公式 |

`dsh-v1.1.0`已推送，但生成发布回执时连续两次Git archive超时，没有放行实验。
保留原tag与失败记录，不覆盖；新版本`dsh-v1.1.1`另做测试与canary后发布。

版本tag的commit是准确定位，不靠表里复制一段“最新代码”。不移动已发布tag；下一次运行
源码有改动就升新版本。文档文字修改不改变运行源码时，可继续引用原发布版本。
新增软件规则是人工工作，版本表不是自进化成绩表。

## 如何使用

本项目独立CPU环境：`research/market_rsi/.runtime/data-scientist-py312-20260910/bin/python3`。
完成测试和真实工具canary后，手动提交并push版本tag；发布工具本身不会偷偷commit或push。
然后生成发布回执（示例路径必须对应实际通过的canary）：

```sh
PYTHONPATH=research/market_rsi research/market_rsi/.runtime/data-scientist-py312-20260910/bin/python3 -m data_scientist_harness.release --canary research/market_rsi/artifacts/data-scientist-codex-canary-FRESH-ID/canary.json --output research/market_rsi/artifacts/releases/dsh-v1.2.0/release.json
```

正式准备入口`prepare.py`现在必须给`--release <回执路径>`。每份工作区、工具记录、
训练claim、训练结果、controller assessment和round archive都能追到该版本；训练结果的
`attribution`保存各组件hash。`compare_attribution`列出哪些组件变了，不自动宣称因果或提升。
正式训练仍须通过数据、预算等原有检查；有版本并不代表数据足够或已经获准付费运行。

Git机制核对日期：2026-09-10；阅读官方说明的tag类型、远端引用输出和archive属性部分：
[annotated tags](https://git-scm.com/docs/git-tag)、
[remote tag/commit](https://git-scm.com/docs/git-ls-remote)、
[archive attributes](https://git-scm.com/docs/git-archive)。
档案中若有export-ignore/export-subst导致源码缺失或不同，本实现拒绝发布，不静默忽略。
这些是版本机制依据，不是金融研究结果。统计和评估原则复用已有分层评估记录。
# dsh-v1.2.1 — 工具字段说明修复（2026-09-10）

旧v1.2.0首次真实GLM设计调用没有完成：工具未声明responses数组内部字段，9次工具中
8次报错。旧调用完整保留，不重写。v1.2.1补齐嵌套参数、枚举、可读校验错误和source-only
能力说明；新增实际tools/list回归。目标、数据准入、四个trainer和预算规则不变。
这是人为接口修复，不是自进化改善；新实验必须使用新tag、canary和工作区ID。
172项回归通过（含5项schema和3项准备凭证测试）；新免费真实Codex canary13通过：
18次工具、4次合成CPU拟合、1次实时检索和1次公开阅读、零付费模型调用。
发布凭证将保存在`artifacts/releases/dsh-v1.2.1/release.json`；没有该凭证不得启动付费实验。
# dsh-v1.2.2 — 无效调用的有限错误反馈（2026-09-10夜）

v1.2.1的真实03通过字段校验，随后因不存在的工具名终止。原回复与$0.211773042
计量费用保留；没有研究决定或拟合。新版本在此入口允许最多两次明确runner错误反馈，
不执行错误动作、不替模型写答案，不重试provider。第三次错误或其他预算/状态错误仍停止。
旧入口默认行为不变。这是人为harness修复，不能算模型研究能力提高。
新免费标准canary（UTC09-11-01）和错误恢复canary均通过；后者19次回复/4次合成拟合。
源码/模型调用/控制反馈分别记账，不能把控制反馈算成模型自主工具选择。
# dsh-v1.2.3 — 明确来源研究的收尾和引用（2026-09-10夜）

真实04查了3次文献元数据、读取DeepLOB摘要页，成功存下研究和数据审计请求，但四次
defer都填了计划/运行ID，最后输出未提交文字而终止。其16次调用计量$1.446512904，
0次拟合；不伪造提交。新版本明确defer的trial_id必须为空，错误提示给出具体格式；
阅读引用报错说明期望工具和当前可用ID。门槛没放松，旧失败不改。
209项相关测试通过；标准免费Codex canary和无数据source-only错误→defer检查均通过。
这些是人为接口修复，不是agent的模型能力或预测性能改善。

# dsh-v1.2.4 — 文献读取按实际量结算，并返回真实链接（2026-09-11）

旧版本按每个尝试2MB累计，成功返回小页面也不释放上界；页面链接未返回，真实06曾猜错
两个URL。新版本持久化每次读取的预留，成功回执校验后按实际body字节结算；失败/崩溃缺
完整回执仍保留上界。总额度仍10MB，单次上界含超限探测1字节。不修改Tinker费用账本。

HTML返回最多80个去重真实href、链接文字及截断标记；相对路径基于最终页面解析。
没有自动跟随或执行链接；每次请求仍验证HTTPS、公网DNS、重定向，已读链接不算已读正文。

138项harness回归与10项新专项测试（包含在138内）通过。实际Codex免费canary03完成18次
脚本化工具调用及4个合成CPU拟合；0次Tinker。真实链接canary01从首页提取55个链接，
跟随实际返回的实时文档链接，两次读取共2,306,481正文bytes，账本一致、无挂起预留。
这些是工程测试，不是GLM新研究或真实预测结果。原始消息诊断属于独立audit_tools，未改生产。
研究依据：[修复记录](HARNESS_REPAIR_RESEARCH_2026-09-11.md)。发布回执生成后另记，不移动旧tag。

已发布并核对：commit `26a2cedd8342c7e1037ae523d4246c1bd0276906`，tag `dsh-v1.2.4`，
release `d7154441d83dac123e5204a28b604a7c694ed80d6969d934e2a85e5d5baa6b18`。
离线SDK/tokenizer检查通过，0次provider调用。下一工作区独立冻结，不修改06。

# 独立来源适配器 pm-source-quotes-v0.1.0（2026-09-11）

commit/tag `ab202f4` / `pm-source-quotes-v0.1.0` 已推到私有origin，真实固定小时重放完成。
来源BBO和重建深度分开保存，保留原始顺序/hash，不从后来的消息回填。不是新的trainer、
目标或DSH模型版本；原dsh-v1.2.4源码未改。修复通过的汇总经校验后作为新findings输入，
不能把新adapter当作已经通过全部来源准入。详见[修复结果](QUOTE_REPAIR_2026-09-11.md)。

# 独立全市场检查与来源QA输入适配器（2026-09-11）

以下均是人指导的工程变化；DSH仍为v1.2.4，quote adapter仍为v0.1.0。

| 发布标签 | commit | 变化与实际验证 |
|---|---|---|
| pm-population-audit-v0.1.0 | e57e656 | 首个逐token统计器；50k真实pilot完成。外推超过900秒上限，所以没有启动全小时 |
| pm-population-audit-v0.1.1 | 7caa6af | 仅延长全小时上限至1800秒并加pilot外推检查；新版pilot统计完全一致，完整4,328,805条实际完成 |
| pm-source-review-v0.1.0 | 613332c | 当前D10 QA与旧Vantage QA分开；scope/manifest不符拒绝，不将未知改为pass |
| pm-population-workspace-v0.1.0 | fb6b331 | 将完整汇总及event/clock/snapshot计数交给同一DSH；不提供原始行情或新Test |

111项相关测试通过；完整小时audit及真实source-QA串用拒绝检查通过。新的controller会话
正常结束、计量$0.325900908，0拟合。不能把改输入前后的controller差异单独归因为模型
自进化；旧会话保留原指针及原决定。详细数据、研究依据、剩余缺陷见
[多市场检查及controller复核](POPULATION_QUOTE_CHECK_2026-09-11.md)。

# dsh-v1.3.0 — 来源检查之后，允许controller登记具体实验方案（2026-09-11）

新增`propose_source_study`，补上source-only工作区缺失的方案入口。controller自行定义问题、
目标、预测时长、来源用法、训练/检查日期和对照；runner绑定来源hash、当前QA和已开放日期。
登记方案不等于数据准入，不读新数据、不训练、不打开Test。第一份有效方案永久保留，
收尾archive引用同一份；更改方案或来源会拒绝。所有旧QA/拟合/预算门槛不变。

146项harness测试（含8项新增）和2项准备凭证测试通过。标准真实Codex免费canary04通过；
新增source-study真实工具链canary01完成6次脚本化调用、0拟合、0Tinker。此版本是人为工程
改动，不能算模型自进化或预测进步。研究依据与边界见
[方案入口说明](SOURCE_STUDY_BRIDGE_2026-09-11.md)。

v1.3.0已发布commit`d60255b411fa7606591983d7b42e02c130795d65`，release
`f1554ae10541ef5abe4aa0a68c6dce89413baf9d74f116b29c1f4488f3a5739f`。
同一版本下两次真实GLM会话完成、0市场拟合。独立反馈适配器
`pm-source-study-feedback-v0.1.0`在`4b68e18`发布；不更换DSH或修改父方案。
随后新增的文件清单交接仅改变今后新工作区的输入，3个单元测试及1个本地清单检查通过；
DSH运行源码没改，旧输入与已付费会话保持不变。该交接修复还没有新的付费会话验证。
# pm-source-revision-context-v0.1.0 — 历史意见不重号（2026-09-11）

独立输入适配器保留历次意见及预算，但只保留一个当前意见编号；旧意见改用带父工作区
hash的历史编号，旧文件不改。重复编号或碰撞直接报错。加入对第二次修订的独立复核，
并交付已有逐日文件清单。42项相关测试通过，真实历史方案/hash核对通过；0新数据/0拟合。
DSHv1.3.0运行源码、模型、真实工具canary没变。这是人为输入交接修复，不是模型进步。
# pm-source-object-scope-v0.1.0 — 日期清单要落实到文件（2026-09-11）

外部只读核对器把controller选的日期展开为已有目录中的文件，再和它引用的内容manifest
比较。日期少了但文件没少，会明确报告；缺内容绑定时不允许当作可执行输入。即使全部
绑定，也不自动通过来源QA。后续工作区会直接得到这个范围说明；旧输入/回复不变。
48项相关测试通过，含真实已结束会话元数据核对；146项DSH回归通过。没有改DSHv1.3.0
运行源码、模型、目标或评分，也没有新市场数据、远端读取或拟合。这是人为工程修复。

# dsh-v1.4.0 — 时间规则先运行小测试（2026-09-12）

新增controller可调用的`probe_temporal_contract`。控制器自己填规则；工具区分真实相等
与缺后续记录、拦截旧时点开始的预测区间和无效报价沿用，并把结果绑定到新方案。
这不是市场simulator、数据准入或完整特征验证；支持范围与来源证据限制明确保留。
另加付费前本机文件检查，云端占位账本不直接进入付费读取流程。

157项harness回归通过；标准真实Codex免费canary18次调用/4个合成CPU拟合通过；
来源方案免费canary7次调用/0拟合通过。0次Tinker、新行情和Dev/Test。
新CPU环境位于`/Users/estelle/.cache/market-rsi/runtimes/ds-py312-20260912-01`；
Python与五个依赖版本不变，环境位置改变，须绑定新release，不沿用旧回执。
代码发布与回执生成后另记；旧版本和旧工作区不改。这是人为工程改动。
研究与实现依据：[9月12日记录](TEMPORAL_CONTRACT_2026-09-12.md)。

已发布：commit`815f05c405e0e37de7b7156f0f44e8c86c952ba0`、tag`dsh-v1.4.0`；
release`9bae3aa72e7c1e14c6ae24d6457e6cf85615c664d082a51ef4293ed6ecb5bdbb`。
源文件、运行环境、标准canary与远端tag核对通过，未移动任何旧版本。

# 未发布 sports Train-only 诊断（2026-09-15）

新增固定163场Train、60秒价格变化和100+21+21+21场滚动切分的方法筛选。zero-change、Ridge、
Elastic Net、Random Forest和Histogram Gradient Boosting使用完全相同的行、feature、每场等权
和评分。干净运行`nfl-train-method-screen-20260915-02`完成，Route-Dev/Final均未打开；专项
7/7及sports harness 34/34测试通过。

这不是新的正式Harness release，也不是Controller self-evolution。第一次运行的常量feature相关
系数被写成非标准JSON `NaN`；旧运行永久保留为失败记录。未发布版本已改成严格拒绝非有限JSON
并显式记录常量列。正式controller运行前仍需完整回归、commit、tag、release receipt和冻结action
space。

同一未发布开发面随后增加game-clustered local projection：三个horizon共用20,836个Train play、
每场等权，并按163场比赛聚类计算区间。5/5专项与39/39 sports tests通过。方法目录状态为
`implemented_unreleased`，正式Controller仍不能调用；结果只作描述性Train诊断。

# dsh-v1.6.0 — Open discovery、体育事件表示与一次性Dev（已发布并完成一次确认）

本版把研究分成两个明确阶段。Discovery只看已打开Train、Archive和公开文献，可以自由改变
问题、target、representation与算法，但不能拿到正式reward。Confirmation只选一个candidate，
先固定baseline、primary metric、方向、evaluator和完整Route-Dev cohort，然后最多评分一次。

体育研究新增同一event的start/end state表示。第一次Train实现错误使用“下一条可评分play”，
23,546行的中位向后读取为44秒，28.61%超过60秒，因此旧的约12.2%改善不能promotion。修复后
只读当前event的`end_situation`，同样163场、同样3个rolling blocks、同样Ridge下，单独加入
`state_wp_delta`把equal-game MSE从0.0019265162降到0.0016700963，Train内相对改善13.31%，
三个block均改善。这仍只是opened-Train结果；Route-Dev和Final尚未打开。

release snapshot现在也包含`sports_event_research`非测试执行代码。一次性Dev gate要求50个
preregistered文件全部materialize、零排除、source hash合法，并在读取label前消耗唯一评分权。
默认下载入口仍只允许Train；Route-Dev必须显式声明；sealed Final始终拒绝。

已发布commit `bf06e17040a5a87eb6fd3cd7d54b0fb07508670c`、tag `dsh-v1.6.0`、release
`7daa97a887e36d6ba7e5299556d986c43ac1faf4d01200f9bfc89b27cf4b960e`。真实Codex免费canary
通过：18次工具调用、4次合成CPU拟合、1次公开搜索、1次公开阅读、0 Tinker。

本版完成一次正式的Route-Dev确认。修复后的`state_wp_delta_only`在Train相对raw-state Ridge
改善13.31%；唯一一次50场Route-Dev评分改善11.88%（MSE `0.0018824113 → 0.0016587970`），
Pearson IC `0.2067 → 0.3904`。50/50 materialize、0排除、0自动重试；评分权已用完，sealed
Final未打开，provider cost `$0`。结果支持表示转移，不证明PnL、实时lead或Final泛化。

本轮也暴露一个Harness缺口：evaluator没有在评分前声明并保存candidate相对raw-state的逐场
delta，因此不能做净增益集中度审计。不会重开Dev补算；下一版本须在新的untouched cohort前
把逐场盲化delta、日期块delta和集中度输出写进冻结evaluator。

本版的全回归、真实Codex canary、精确commit、annotated tag和私有origin核对均已完成。
发布和一次Route-Dev确认不授权打开sealed Final；Final仍保持封存。

# dsh-v1.6.1 — Horizon 自由探索、可用时间与成对证据（已发布）

这版修正三个由v1.6.0真实实验暴露的Harness问题。

第一，60秒不再可能被误解成全局规则。Open discovery可以在已打开Train/Archive上比较30秒、
60秒、300秒、event-time、多目标或新的objective。机器合同明确记录horizon可变。只有candidate
进入新的untouched confirmation时，才把完整target/horizon规格单独hash锁定；看过新Dev后不改。

第二，每个derived feature必须提前声明event time、available time、decision time、label start和
label end。所有行必须满足`event <= available <= decision < label_start <= label_end`；任何一行
失败都拒绝整个candidate，不能悄悄删行。真实opened-Train canary重放既有60秒实验的163场、
23,709行并通过；这只验证历史provider event clock，不声称知道live arrival time。

第三，新confirmation要先声明证据输出。预测A/B必须保存runner-private逐unit paired loss；
controller只看到不含比赛ID的aggregate，包括按比赛/日期块的胜出比例、bootstrap区间、top-1/
top-5贡献集中度和leave-one-out范围。非预测研究可以使用scalar terminal证据，不把Harness锁死
为MSE预测。

248/248 Harness测试、54/54 sports测试和真实Codex免费canary均通过。第一个canary仅因受限
沙箱禁止loopback而失败，0调用、0费用并保留；新ID通过18次工具调用、4次合成拟合、1次公开
搜索、1次公开阅读、0 Tinker，未打开新Dev/Final。详细研究记录：
`H2_EVIDENCE_AND_AVAILABILITY_RESEARCH_2026-09-15.md`。

已发布commit `5aa860275f19bcc1148a591bb9fbaa152ef08a7b`、annotated tag `dsh-v1.6.1`；
release SHA256为`aa2c509c3c45261c008f1c5810851a2da959bd9781e7cc956ac3f8168439f8e4`。
只推送到用户自己的origin；本地运行artifacts、原始数据和密钥未推送。

# dsh-v1.6.2 — Controller可执行的Target Discovery Adapter（已发布）

v1.6.1允许open discovery改变horizon，但实际NFL adapter仍把30/60/300秒写死在源码里。本版
加入typed target spec，让researcher在opened Train上选择elapsed-time和event-time target、
price delta或预先deadband的direction，以及per-target/common support。它不能提交任意Python，
也不能打开Route-Dev或Final。

固定materializer会核对source receipt、selection、panel、manifest、PBP和trade hash；每个play
全部保留，没有合法未来成交的target写空。fixed-time target不允许静默carry-forward；event-time
target使用严格晚于decision的第N笔trade并受wall-clock上限约束。adapter只做Train discovery，
不按表现选winner、不产生正式reward。

11/11项专项、254/254项Harness和59/59项sports测试通过。exact-source canary
`data-scientist-codex-canary-20260915-12`通过：18次工具调用、4次合成CPU拟合、1次公开搜索、
1次公开阅读、0次真实Tinker、provider cost `$0`，没有打开Dev/Final。详细依据见
`TARGET_DISCOVERY_RESEARCH_2026-09-15.md`。

已发布commit `1a48ff202891cc7fa286cb8f2df90d9022368200`、annotated tag
`dsh-v1.6.2`；release SHA256为
`41367ff518acfa0196e5f7fb5c57c501cde7cbb8f3a2d4ea8186ab9bfdb1b4c2`。远端tag、源码、运行环境
和最终canary核对通过。只推送到用户自己的origin；本地数据和运行artifacts未推送。

# dsh-v1.6.3 — Aggregate-only Controller设计复核（已发布）

target-grid和same-support已经产生Train汇总，但旧workspace只有raw Train训练入口或source-QA
入口。新模式只冻结已完成的result、manifest、pre-score lock及runner整理的findings；不接收raw
rows、Train dates、Route-Dev/Final或训练输入。Controller可以查公开资料、查看sports method
library、提出capability或新算法，然后defer；任何训练或trial selection都在启动子进程前拒绝。

准备器把12个target的coverage、zero-change比例、Ridge/Random Forest的相对MSE、最弱fold、
calibration和game breadth，以及15--60秒same-support敏感性放进当前findings。它同时说明三条
未解问题：30--45秒尚未与较强的event-state表示组合测试；5-trade event-time仍是不同问题的
候选；prediction skill不等于live executable PnL。既有Route-Dev结果不进入workspace。

本地已通过257/257 Harness、59/59 sports及8/8相关experiment/preparer测试。exact-source canary
`data-scientist-codex-canary-20260916-01`通过：18次真实Codex工具调用、4次合成CPU拟合、1次公开
搜索、1次公开阅读；aggregate adapter完成3次边界调用。0 Tinker、0新Dev/Final。

已发布commit `68d500a9be24eb277aa56d4dd442f48caf7bd565`、annotated tag `dsh-v1.6.3`；
release SHA256为`1d2d400b4720be4c9b37dd827b5237fc3d204b6b2e713e579a46f348e28c397e`。
真实aggregate-only GLM会话`nfl-target-controller-20260916-01`随后完成：7个turn、9次tool call，
实际metered cost `$0.284437332`。它没有看到raw rows或Dev/Final，也没有训练；它查阅方法库和
公开来源后，选择下一次只改变feature representation：冻结30秒target、16,632个same-support
plays、3×21场rolling blocks和200-tree Random Forest，测试score×time、possession×field-position
与same-event state delta，并做消融。如果不支持，再进入trainer-only HistGradientBoosting实验。

这个结果证明aggregate边界内的Controller能产生一份可执行的事前方案，不证明方案有效，也不
证明Harness提高了预测。对应研究与会话记录见
`AGGREGATE_CONTROLLER_WORKSPACE_RESEARCH_2026-09-16.md`和
`NFL_AGGREGATE_CONTROLLER_RESULT_2026-09-16.md`。

# dsh-v1.6.4 — Paired-loss方向与时间序列评估防错（已发布）

真实feedback Controller把`delta`定义成`parent MSE - candidate MSE`，随后却把`delta < 0`写成
candidate更好，并要求bootstrap上界小于0。这个符号方向是反的。它还提出leave-one-date-out
refit；对时间序列而言，这会让较晚日期进入较早日期的训练，而且把已有日期重新分组不等于获得
新的独立证据。因此该方案没有执行。

本版把已有paired-evidence的隐含约定变成机器规则：只接受
`candidate_minus_baseline`，负数才代表candidate loss更低。正反测试确认正delta永远不会被计为
candidate更好。Controller说明同时明确禁止把会训练到未来的leave-one-date/season/entity-out当成
forecasting evaluation，也明确说明重新分组旧预测不会产生新证据。

下一实验必须使用past-to-future expanding/rolling origins。如果要增加日期证据，就在同一163场
opened Train里减少初始fit前缀、增加后续chronological check games，同时让RF与HGB使用完全相同
的fold、feature、target和weight；这仍只是自适应Train robustness，不是新Dev。

258/258 Harness、59/59 sports、16/16 experiment测试通过。真实Codex免费canary
`data-scientist-codex-canary-20260916-02`通过18次工具调用、4次合成CPU拟合、1次公开搜索和1次
公开阅读，0 Tinker、0 Dev/Final。已发布commit
`ca247d886581e6eee55e8ea0b74a6cf5aff645f1`、annotated tag `dsh-v1.6.4`；release SHA256为
`9999e9d70f54f567d23a96e560094ff66a0429fe4705ccf1a4c0658b794faffc`，只推送到用户origin。

# dsh-v1.6.5 — 实时体育时钟分层

真实实验的主要增益依赖`state_wp_delta`，但历史provider event clock不是live receive time。
Feedback Controller因此选择先验证live timing；随后检查已有DEN–KC真样本发现，公开ESPN路径的
62条live delta中，三次得分事件从provider event wallclock到本机接收约晚37.6–58.8秒，且这
个wallclock表示事件开始而不是provider发布时间。Controller原提议的90%完整率和5秒p99也没有
成功读取的原文支持，不能直接变成promotion规则。

本版新增`probe_live_timing_contract`，强制分开event-start、provider-publish、local-receive、
decision和label clocks；并把capture integrity、strict publish-to-receive latency、market lead、
independent confirmation拆成四个gate。Event-start永远不能冒充publish timestamp；合成probe通过
不支持controller自行选择的阈值、不批准来源，也不证明市场领先。

时间窗口不再被人永久固定成60秒。Controller可以在opened Train discovery中自由提出有限的
candidate horizon grid，但grid、selection rule和primary reward都必须在看到该阶段score前冻结；
进入protected confirmation时只能带一个已选horizon，不能看分后再挑窗口。

Harness 266/266、sports 59/59、experiments 19/19、live timing专项8/8和capture audit专项4/4
通过。真实Codex canary `data-scientist-codex-canary-20260916-03`通过：18次tool call、4个CPU fit、
1次live metadata search、1次public read、0 Tinker、0 Dev/Final。发布commit
`d4ea731722cbf9a6ddd806d40ea258edf7a137da`，annotated tag `dsh-v1.6.5`，release SHA256
`8546f10d12165159bcba8c33576090df19802112e50d56af7225656a66aef0a1`；只推送到用户origin。

# dsh-v1.6.6 — Aggregate来源证据接线（已发布）

真实aggregate controller已经拿到runner验证并冻结的官方资料事实，但v1.6.5只允许把controller
自己重新下载的网页登记为research。官方网页返回404/403且body额度用完后，它无法把已有证据
接到contract工具，只能defer。这个失败是Harness证据接口问题，不是source canary假设被否定。

本版新增`read_aggregate_source_evidence`。它只在aggregate-only workspace读取当前冻结finding中
带`runner_verified_primary_source_fact`类型的单条事实，并把source/finding/finding-set hash写入
append-only ledger。输出明确标记不是fresh network read、不是full text、没有在我们的数据上验证。
普通workspace、任意finding文字、search metadata和失败record不能走这条入口；该入口也不能清QA、
准入数据、训练或打开Dev/Final。

研究依据复用9月16日已经读过的Sportradar PBP、Sportradar Push Events、Polymarket market WS和
nflverse更新说明，不把重复下载包装成新研究。比较与边界见
`AGGREGATE_SOURCE_EVIDENCE_INTERFACE_2026-09-16.md`。

专项14/14、Harness 268/268、sports 59/59、NFL experiments 19/19和sports adapters 7/7通过。
真实Codex canary `data-scientist-codex-canary-20260916-04`通过18次工具调用、4个CPU fit、1次公开
搜索、1次公开阅读、0 Tinker、0 Dev/Final。发布commit
`75dccd1bd5fb9822198178c56e2f37961ea6c5a7`、annotated tag `dsh-v1.6.6`、release SHA256
`17706d0a5ba12a3b259d6faf69ab1bbce1896d823a805d5356dff5fcce433fc0`，只推送到用户origin。

# dsh-v1.6.7 — Controller可见的Algorithm Schema

v1.6.6真实controller成功研究live source并归档capability，但连续10次尝试新算法archive全部被拒绝。
内部validator要求28个精确字段，served tool schema却只告诉controller“proposal是object”；因此
model无法知道准确字段。这是Harness interface defect，不是算法假设被实验否定。

本版让`propose_algorithm_design`直接公布完整nested schema，并让served schema与validator共享同一
字段集合。增加boolean shape检查；仍要求read research record、两个closest methods、两个source
findings/limits、math、pseudocode、same-data parent和simple baseline、至少两个ablation且包含
`remove_new_mechanism`、failure modes、synthetic tests、CPU/memory上限和`requests_sealed_data=false`。
没有放松准入、激活任意代码或开放Dev/Final。

同时新增Sportradar Push canary recorder，但真实trial preflight返回403，无stream entitlement；
所以只验证安全记录代码，不声称采到数据。详细轨迹、费用和边界见
`NFL_LIVE_SOURCE_CANARY_AND_HARNESS_V167_2026-09-16.md`。

当前Harness 269/269、sports 62/62、NFL experiments 19/19通过。真实Codex canary
`data-scientist-codex-canary-20260916-05`通过：18次tool call、4个CPU fit、1次公开搜索、
1次公开阅读、0 Tinker、0 Dev/Final。发布commit
`7dc906fb33a70c240d547dc06a9f9512a5fa8ae1`、annotated tag `dsh-v1.6.7`、release SHA256
`14c834a01da0cc5cc7787475098c4eb7b62ba3565e13964b73e119e976923be4`，只推送到用户origin。
这仍是人为Harness修复，不是self-evolution score。

# dsh-v1.6.8 — Source Blocker Feedback

v1.6.7已经能安全记录Push stream，但当前Sportradar trial entitlement preflight只返回403。
本版新增fresh aggregate feedback adapter，把这个exact receipt、既有Train-only实验、post-hoc live
audit以及带transfer limit的合法替代source研究交给下一条controller。Controller可以选择Replay
capture canary、另一个source、market-response、有限target/horizon或新算法；Harness不预设
5/30/60秒，也不把403写成模型失败。

本版不改scorer、trainer、target、数据分区或旧artifact，不创建账号、不购买、不采feed、不打开
Route-Dev/Final。实现前复用既有Sportradar研究，并新读SportsDataIO testing/access/timing与OpticOdds
streaming/historical odds官方页面；详细来源和限制见
`NFL_SOURCE_BLOCKER_NEXT_STAGE_2026-09-16.md`。

Harness 269/269、sports 62/62、NFL experiments 19/19以及本次相关adapter 12/12通过。完整audit
目录另有两个需要未安装`pyarrow`的旧测试，以及一个故意拒绝用当前Harness打开旧workspace的测试；
它们与本次adapter无关，未被伪装成通过。真实Codex canary
`data-scientist-codex-canary-20260916-06`通过；发布commit
`51cb8de5d75ef0c4c639aecaa2338cce00b48c40`、tag `dsh-v1.6.8`、release SHA256
`e4d4321442cbcbcb8424b27c974424ea0b2ed062458e112ef9decfcbe13ea1c3`，只推到用户origin。

# dsh-v1.6.9 — Evidence-bound Capability Work Orders

v1.6.8真实Controller正确选择live timing/source gate，但旧`request_capability`只检查自由文本非空。
因此它成功保存了ledger中不存在的`1433ms`和多组虚构字段；最终defer文字也没有绑定工作单。这不是
科学发现，而是Harness evidence-contract defect。

v1.6.9要求每条capability observation提供exact record ID、`/result` JSON Pointer和observed JSON
value。Broker只接受observational tool result并逐值核对；Controller自己写入arguments的文字不是
证据。路径或值不匹配就拒绝。未知内容必须列入
`unsupported_assumptions`。Capability仍只归档，不自动执行；defer必须写出最新工作单的精确名称。

新合同/接口17/17、Harness 274/274、sports 62/62、NFL experiments 19/19通过。当前CPU runtime的
通用旧suite仍缺`pyarrow`和`harbor`，产生35个import error和1个依赖相关旧失败；未安装依赖来改变
冻结环境，也未把它们写成通过。真实Codex canary
`data-scientist-codex-canary-20260916-07`通过18次tool call、4个CPU fit、1次公开搜索、1次公开
阅读、0 Tinker、0 Dev/Final。发布commit
`1002c0239a80a108f7b60c237629e7469118712c`、tag `dsh-v1.6.9`、release SHA256
`d5e5bd804d53551cbeeb87140d229b247492f07b69864e058ddb6db9ffad0622`，只推到用户origin。
随后fresh paid controller `nfl-source-blocker-controller-20260916-02`有效结束：15 turns、19 tools、
0 fit、0 Dev/Final、增量Tinker `$0.934487604`。它前四次不合格的capability请求被拒绝，第五次才用
三个exact ledger observations提交`sportsdataio_replay_capture_canary`，说明合同在真实run中生效。

# dsh-v1.6.10 — Terms-gated SportsDataIO Replay Capture

状态：已发布；真实Replay session仍没有账号内endpoint和明确的polling/raw storage许可，因此provider
canary与新的实证模型实验仍未启动。

观察到的问题：v1.6.9 Controller已经产出evidence-bound Replay work order，但公开资料没有给出账号内
的准确session endpoint、认证方式或自动保存许可。直接猜endpoint或把Replay误当historical revision
archive会破坏source provenance。

变化：新增一个只能消费operator-created endpoint的recorder。它要求本地私密endpoint与显式
authorization receipt，绑定SportsDataIO host和endpoint hash，拒绝URL credential，key只从env读取；
poll interval、次数、timeout和bytes都有hard cap，不跟redirect，不自动重试。原始response、本地时钟、
重复/no-change及时间/修订样字段分开保存。clock字段不自动获得publish语义，因此不计算latency、
market lead、model score，也不打开Dev/Final。

归因：这是human-directed harness/data-acquisition engineering，不是Controller模型自我改进，也不是
新的预测结果。公开资料、transfer limits、实现与测试见
`SPORTSDATAIO_REPLAY_CAPTURE_CANARY_2026-09-16.md`。

Sports-event 72/72、Harness 274/274、NFL experiments 19/19通过。开发canary -08以后又加入JSON转义
session URL回显保护，因此没有用旧hash发布。最终exact-source Codex canary
`data-scientist-codex-canary-20260916-09`通过18次tool call、4个CPU fit、1次公开搜索、1次公开阅读、
0 Tinker、0 Dev/Final；result SHA256
`c9db71209142130ca2edfea994a59f60b12e71fe739df84f38847f02c9280040`。发布commit
`03f6cade7e32198b659dd48aaf338af8a8c8f4fb`、annotated tag `dsh-v1.6.10`、release SHA256
`4b880cc0c22ce22d738160a52e9cd172b1fb8d1c26efd28d8257ba5424aa30f9`，只推到用户origin。
没有真实Replay provider call。

# dsh-v1.6.11 — 2024 NFL Train-source discovery (human-directed)

状态：已发布；2024来源检查是opened-Train数据工程，不是模型自进化或新分数。

观察：2025市场训练仅163场；2024 Polymarket没有现成gameId、slug有两种队伍顺序及旧缩写，
旧映射会错丢比赛。新工具把通用NFL series的2024目录、独立赛程映射、固定12场成交screen和
nflverse逐play时间覆盖审计分开。285个目录事件中284个成为严格映射候选；12/12场有成交，
但60秒标签在这组样本只覆盖1,400/2,027个有时间的play。它不证明整季训练可用或性能提高。

研究及每一步证据见`NFL_2024_DATA_EXPANSION_SCREEN_2026-09-16.md`。Harness 274/274、
sports-event 91/91、NFL experiments 19/19通过；exact-source免费Codex canary
`data-scientist-codex-canary-20260916-10`通过，18个工具调用、4个CPU fit、0 Tinker、
0 Dev/Final；result SHA256
`1b8c7572d5b3872aef5a51885cca894c122326aa7f81e696451b23a378916a3e`。
精确commit`c8c4763860caac66a0312f0a7338c630475b8435`、annotated tag
`dsh-v1.6.11`已推到用户origin并核对；release SHA256
`f18a190758aefc37f278d9e03a74bc5d51649c558a98516c7d813354ac8cbed6`。
当前仍无新模型实验或性能分数，2024候选也未被正式纳入Train。

# dsh-v1.6.12 — 固定的 60 秒强基线第一轮选拔（human-directed）

2026-09-16：新增 `sports_event_research/run_deterministic_60s_baseline.py`，在已开放的
2025 Train 163 场上保持 60 秒标签、完整比赛、same-event `state_wp_delta` 表示、
滚动 3×21 场切分和逐场等权不变，只比较既有固定参数的 Ridge、Random Forest 与
Histogram Gradient Boosting。先复现旧 state-delta Ridge Train MSE 再选最低 Train MSE；
这只是确定性 trainer screen，不是自迭代结果，也不是独立测试或最终强基线。
设计及局限见 [强预测基线](STRONG_FORECAST_BASELINES_2026-09-16.md)。

发布前验证：新 baseline/评分边界合成单测 13/13、sports-event 95/95、Harness 274/274。
首次免费 canary 因执行沙盒禁止本地 loopback bind 失败，0 Tinker、0 模型分数；保留
`data-scientist-codex-canary-20260916-11`，没有复用 ID。新 ID
`data-scientist-codex-canary-20260916-12` 在允许本地 loopback 的环境通过：18 次工具调用、
4 次合成 CPU fit、0 Tinker、0 Dev/Final；result SHA256
`4e8ace19fa5ab075b35e41fa8c115b2eab6dbb65ccd83c7fe91ead4a6b46b218`。
精确 commit `abc7f6f45b6dc5b96d30d761bf0c6c146803ec6e`、annotated tag `dsh-v1.6.12`
只发布到用户 origin，远端核验通过；release SHA256
`317609f38ff4471ff67030befc417a6ae3e24014f9ddf45aeea40ffcb587bc28`。
随后 Train-only 运行的结果见[强基线记录](STRONG_FORECAST_BASELINES_2026-09-16.md)：
HGB `0.0013540355` vs 旧 Ridge `0.0016700963`，低 18.9%，但不是独立测试或自迭代效果。

# dsh-v1.6.13 — 把固定 60 秒基线交给下一条 Controller（human-directed）

2026-09-16：观察是旧 sports aggregate adapter 只描述另一个 30 秒实验，无法把刚完成的
60 秒 HGB/Ridge 同行比较、2024 的 60 秒标签覆盖缺口和时间可用性限制交给新 Controller。
本版只改 `controller_context`：新增 `audit_tools/prepare_nfl_60s_baseline_feedback_controller.py`。
它逐哈希核对已开放 Train 的 lock/result/manifest 和 2024 来源 screen，但只复制不含 raw 行和
game ID 的 result/manifest 到 aggregate-only workspace。它不能 fit、购买、打开 Dev/Final，
也不会替 Controller 选 HGB 参数或后续算法。方法研究沿用
[强预测基线](STRONG_FORECAST_BASELINES_2026-09-16.md)已经阅读的原始资料；本次是同一
已研究操作的来源交接，不声称新的文献或新的算法已经验证。

新交接专项 3/3，相关专项合计 10/10，Harness 274/274；免费 exact-source canary
`data-scientist-codex-canary-20260916-13` 通过 18 次工具调用、4 次合成 CPU fit、
0 Tinker，result SHA256
`c29224d0cf72f57f488680dbc3c234243bb38c71eaa072ffe73eead8c3268813`。
正式 commit `39a03fa5da875bd8d19cc68fd89ff7487912b4ea`、annotated tag `dsh-v1.6.13`
已只推到用户 origin 并核验；release SHA256
`3278e3c5a91768af3a1d0b564420b04025d9fc78ba3c59168cab9c533cf47406`。
其后仅 dispatch 一条 paid aggregate controller：`nfl-60s-baseline-controller-20260916-01`，
11 turns、14 tools、实际新增 Tinker `$0.439231248`，进程回收，0 fit/Dev/Final、无未结账目。
它归档未激活的算法 capability 并 defer；并没有进行模型迭代或产生新分数。完整审查见
[下一轮预测实验](NEXT_PREDICTION_CYCLE_2026-09-16.md)。

# dsh-v1.6.14 — 2024 年 60 秒标签缺失原因审计（human-directed）

观察：12 场 2024 NFL 来源样本中，仅 1,400/2,027 个有时间的 play 能形成现行
60 秒成交价标签。现有审计只给逐场覆盖，不知道其余 627 条是 play 前无成交、最近
成交太旧，还是 play 后 60 秒内没有新成交。复用已经研究和发布的 2024 trade/PBP
时间对齐操作；本版不提出新训练算法，也不把历史 play event clock 当作 live receive time。

唯一变更是新增只读 `sports_event_research/diagnose_2024_60s_missingness.py`：绑定
已冻结的 NFLverse、成交 screen 和先前逐场覆盖回执，对每条有效 play 给出互斥缺失原因，
再与既有 1,400/2,027 及每场数字交叉核对。不会补 0、挑选只活跃的场次、准入新
Train、运行模型或开 Dev/Final。新版本需专项测试、完整 Harness 测试、免费 exact-source
canary、commit/tag 只发布到用户 origin 并取得 release receipt，之后才能对真实 2024
来源运行。发布前 sports-event 98/98、Harness 274/274；免费 exact-source canary
`data-scientist-codex-canary-20260916-14` 通过 18 tool call、4 个合成 CPU fit、
0 Tinker，result SHA256
`1a9c4c886210ff9f6131db0e39bab62472a9334b8aa4c83ffd55d319cd22d16b`。
发布 commit `1e1b1e39827b0ec3ffb31150415be63542b14f68`、tag `dsh-v1.6.14`
只到用户 origin；release digest
`f126417255bbf953d5582b84f5101117d5e6e85919af6c4d352f76d4a4b1d343`。
发布后一次真实来源诊断发现：2,027 个有时间 play 中，1,400 个 covered，
549 个 play 后 60 秒无新成交，78 个 pre-play 最新成交太旧，0 个无 prior trade。
结果 SHA256 `e5008058aa50612c31a5d8ce8b98260f628b94071096af92d6c04c901ca00a1b`。
这不是模型改进或独立 benchmark 分数。

# dsh-v1.6.15 — 冻结 2024 全赛季候选并分批检查来源（human-directed）

观察：事前时间分层抽出的 12 场覆盖差异极大，无法据此判断 284 场候选的整体
60 秒标签可用性。唯一变更为 `raw_data/acquisition`：复用已研究并测试过的
Polymarket Data API 成交查询、2024 唯一赛程映射和 60 秒标签生成口径，不更改
模型、特征、目标或评分。新 `sports_event_research/fetch_polymarket_2024_full_cohort.py`
先锁定全部 284 个唯一映射 moneyline（不按交易量或模型效果挑选），再按事前
赛程顺序每 24 场一批获取。每批绑定发布回执、名单 hash、预取锁和逐场收据；
失败保留 partial，绝不自动重试或静默略掉缺数据的比赛。本机剩余空间低于
5 GiB 时禁止新批次。此阶段只是来源检查，原始数据保留在 Git 忽略的 artifact，
不准入 Train、不跑预测、不打开 Dev/Final、Tinker 成本 0。

来源与方法沿用 [2024 数据扩展 screen](NFL_2024_DATA_EXPANSION_SCREEN_2026-09-16.md)
已记录的 2026-09-16 官方 API 文档阅读；本版没有新算法或新文献验证。候选的
outcome 与时间可用性尚须按整季重新核对；原 12 场不能代替这一步。
发布前测试：sports-event 101/101、Harness 274/274；免费 exact-source
`data-scientist-codex-canary-20260916-15` 通过 18 tool call、4 个合成 CPU fit、
0 Tinker，result SHA256
`a5b851f8fcc52c2c7ab355355eceed0b8c22740e85709a95a22809bb9e3c0eda`。
它验证源码与运行通路，不是整季数据成功或预测分数。

# dsh-v1.6.16 — 数据批次启动导入修复（human-directed）

观察：`dsh-v1.6.15` 的唯一整季名单已锁定，前 10 批中的 batch 00–09
（240/284 场）成功。batch 10 的第一次进程在创建目录前持续停在 macOS 动态库
加载，没有下载请求；只停止该确切进程，不重用该次运行 ID。`sample` 的栈指向
Python 导入重型 NumPy/scikit-learn 依赖；原因是数据获取脚本仅为 SHA/JSON
助手却导入了训练脚本。此结论是进程栈和未创建输出的启动层诊断，不是成绩筛选。

唯一修改是把小型 SHA/JSON 帮助函数放回数据获取脚本，避免导入模型栈；同时
允许 **SHA256 精确等于**旧唯一 v1.6.15 cohort plan 的后续批次在 v1.6.16
执行。名单、顺序、映射、模型目标及前 240 场原始回执均不变。新批次的锁另记
v1.6.16 release；绝不重写旧 plan/tag/批次。新增独立子进程导入测试要求
此脚本不得加载 `numpy` 或 `sklearn`，另测原 plan 的跨版本精确续接。
另查出 macOS 将 266 份 release 范围内的部分旧源码标成 iCloud `dataless`，
Harness 的 resident guard 因而正确拒绝。逐份读取以仅下载本地副本后，266 份
全驻留；与 v1.6.15 release 相比仅本版主动修改的 `__init__.py` 与上述批次脚本
两份 hash 不同。随后 sports-event 103/103、Harness 274/274 通过；免费 exact-source
canary `data-scientist-codex-canary-20260916-16` 通过 18 tools、4 合成 CPU fit、
0 Tinker，result SHA256
`63d8192ee87f76ec6c979da225031b2853189b778adf76a41ae3ad2bd71ab615`。
本地化不是源码逻辑变更，也不是模型性能改善。

# dsh-v1.6.17 — 全 2024 候选的逐 play 标签覆盖审计（human-directed）

观察：v1.6.15/16 已按预冻结名单完成全部 284 场、12 个批次和 407,225 笔
公开历史成交，0 场因清淡而剔除；但这只证明取得数据，不能证明逐 play 的
60 秒目标有足够标签。唯一改变是数据质量测量，不改变 60 秒/300 秒历史标签
定义、预测器、feature、reward 或已封存 split。新只读
`sports_event_research/audit_2024_full_cohort_support.py` 逐哈希核对 cohort plan、
全部批次和 NFLverse PBP；按固定“play 前最新成交不超过 300 秒、play 后必须
有新成交”口径分别报 60/300 秒覆盖、缺失原因、逐场分布。所有映射比赛均在
分母内，缺失不补 0。原始行情留在 Git 忽略的 artifacts；这里不准入 Train、
不 fit、不打开 Dev/Final、不产生 Tinker 费用。方法沿用已研究的 2024
PBP/成交时间对齐，不声称新的文献或算法收益。
发布前 sports-event 105/105、Harness 274/274；免费 exact-source canary
`data-scientist-codex-canary-20260916-17` 通过 18 tools、4 合成 CPU fit、
0 Tinker，result SHA256
`24dbb94168fa5051563be730bc7bd4160f80ddf96b04d7c02b52280a67f0d679`。

发布 commit `8182dcb0cd1dca1518544b3c9751a8aab925d9c5`、tag
`dsh-v1.6.17` 只到用户 origin；release digest
`35a12276c29a27d06e705764fecfbcde5b2ceb274a434bd614114422db2e1701`。
完整 284 场、407,225 条成交和 47,875 条有时间/类型 play 的只读审计完成；
60 秒 32,384/47,875（67.64%），300 秒 43,506/47,875（90.87%）。
这是目标可构造性，不是预测分数；0 fit、0 Tinker、0 Dev/Final、未准入 Train。

# dsh-v1.6.18 — 整季汇总进入 controller 的冻结输入（human-directed）

观察：只读整季审计完成，但上次 controller 只看到 12 场 sample；若不把
284 场的完整结果作为**当前**输入，旧 Archive 会继续误导它把 69.1% 当成整季。
本版仅改变 `controller_context`，不改变数据、标签、trainer、reward 或旧结果。
`audit_tools/prepare_nfl_full_cohort_feedback_controller.py` 精确校验整季的
lock/result/manifest、2025 Train baseline 和旧完整 Archive；只传汇总，不传逐场
ID、原始成交、play、Dev/Final。Controller 可以研究和提出下一步，但 workspace
不允许拟合/准入新 Train/打开 Dev/Final/购买数据。300 秒是可选新目标，不能把
它与旧 60 秒 MSE 直接比，也不能从当前汇总声称性能提高。

发现旧 `audit_tools` 准备脚本没有进入发布时的 executable source 集合；本版把
旧/新两个确切脚本加入发布哈希范围，不把整个 audit_tools 目录的历史脚本一并
扩权。历史来源/时点口径复用 [2024 数据扩展 screen](NFL_2024_DATA_EXPANSION_SCREEN_2026-09-16.md)
及 v1.6.17；这里没有引入新的方法论文。受保护集不得用于选 60/300 秒目标。
新版发布、canary、付费 decision 及其结果以实际回执另记，未执行前不能声称完成。
发布前专项 6/6、Harness 274/274、sports-event 105/105 通过；免费
exact-source canary `data-scientist-codex-canary-20260916-18` 通过 18 tools、
4 合成 CPU fit、0 Tinker，result SHA256
`eecd24029ab9348826b976f093258ecb20f3584f275cac177a83b82226886ea5`。
