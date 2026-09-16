# 让controller先交具体方案，再逐项验收

## 发现的问题

上次完成后没有后台实验，也没有新的训练结果。查代码确认：DSH v1.2.4的source-only
工作区没有结构化来源/目标方案入口；`request_capability`只存文字申请，最终只能defer，
而正式训练又需要source_plan等定义。旧source-review工具在另一条流程，未接入这个工作台。
因此“再多重放几天数据”不能自动补出缺少的实验定义。这是接口缺口，不是GLM已被证明不会研究。

本次先修改方案准备层，不改报价统计、数据文件、trainer或原来的准入规则。新增
`propose_source_study`：controller自己选数据使用办法、目标/单位/预测时长、早训练晚检查
日期、父对照和支持/反对标准。绑定当前QA、当前findings和实际阅读记录。一个工作区
只接受第一份有效方案；它只写方案，不读取数据、不拟合、不购买、不修改QA或打开新Test。
runner提供明确的已开放日期范围，区别于仍为空的“已准入训练日期”。新版本和工作区独立冻结。

方案检查显示两类不同的未完成项：缺少定义的组件，已有定义但缺测量/来源证明的项目。
不能把全部31项都解释成缺行数；也不能把方案写完解释成数据合格。支持的候选算法可以
先提出，不会自动加载任意代码。未实现的内容仍需单独开发、测试和新版本。

## 方法依据与替代方案

复用已有W3C PROV来源绑定方法及DSH当前QA哈希规则；不把旧报告改成新证据。
2026-09-11查询`site.tensorflow.org tfx data validation schema review validate schema environments`，
打开[TFDV入门](https://www.tensorflow.org/tfx/data_validation/get_started/)的
“Inferring a schema”“Checking the data for errors”“Schema Environments”部分。
文档区分统计、预期schema和实际验证，并建议审查推断schema，避免把某份数据的偶然特性
直接当规范。这支持把“声明预期”与“验证数据”分开；不是说TFDV能证明金融预测有效。
也打开了[TFX数据验证说明](https://www.tensorflow.org/tfx/guide/tfdv)，核对schema需审查、
版本管理和验证的流程。本次不安装TensorFlow，也不把通用schema当作事件时钟/历史身份的证明。

替代方案：继续只读文献/申请整天审计，会留下定义缺口；执行助手代写目标与切分，改变
controller的研究职责；放宽QA强行训练，会混入未验证输入。这里采用有边界的方案入口，
保留原训练门槛。此改变是人指导的harness工程，不是agent自进化成果。

## 已完成的工程验证

146项harness回归通过，其中8项新增方案测试；另有2项准备凭证测试通过。覆盖源/QA/findings
变更拒绝、保护日期拒绝、先训练后检查顺序、重复方案拒绝、已提交会话拒绝、已登记方案
修改拒绝，以及新方案不清除QA、不启动trainer。

实际Codex免费标准canary04通过：18次脚本化工具调用、4次合成CPU拟合。新增source-study
canary01通过：6次工具调用，登记合成方案后defer；没有训练cache、没有拟合、QA仍未通过。
两项canary都没有Tinker调用。它们验证工具接线，不证明GLM会选好方案。

下一步发布dsh-v1.3.0并在原$200账本里只启动一次真实GLM方案会话。统计新增实际费用；
不重采样求好答案。旧工作区和数据审计不重跑、不改写。

## 采集时钟的只读追查

2026-09-11只读查看Linode `/opt/d10/bin` 和已知同步脚本的来源路径行。当前
`daily-sync.sh` SHA256为`cea7832816feee000b4a6060f0e6a6f613b8be1bf0242b585016f40cf7df1e2a`；
`etl.py`为`584c7682d9d6ed331bc192da31e75890b7fc4158f4082137f2e2c028b6b1bf8b`。
同步脚本说明原始WS文件从另一台机器经只读rsync传入。因此这台分析机的文件时间不能
代替原始接收时间。未访问另一台机器、未读取密钥、未改变服务或行情。

本地prediction markets项目的`market_making/live_capture.py`确实在`ws.recv()`后记
wall/monotonic时间，但它保存的是`raw-market-event.v1`、`recv_wall_ts_ms`和`payload`，
不是当前D10原件的`t`/`m`格式。这是另一条采集实现，不能拿来证明当前原件的时钟。
在本次检索的Python/JS/TS文件中未找到匹配采集器；不等于证明它不存在。

剩余证据是原采集器的确切版本、部署记录及`t`字段的生成位置，而不是再扫一小时报价。
当前只能保留clock未核实。该检查没有放宽来源准入，也没有新增原始数据读取。

## 真实GLM结果与复核

`source-study-controller-20260911-01`已完成：243.669秒、9个计费turn、11个工具调用，
其中两次方案字段校验失败；模型自行修正后，第一份有效方案登记成功并正常defer退出。
计量费用$0.620910684，不确定额0，0次市场拟合。版本dsh-v1.3.0、commit`d60255b`，
release`f1554ae10541ef5abe4aa0a68c6dce89413baf9d74f116b29c1f4488f3a5739f`。

它选的是一分钟后的mid变化，用过去一分钟mid变化做特征，和固定预测零变化比较。
拟合日期Aug21–24，检查日期Aug25及Sep7–9；这些都是已开放诊断日期，不是新Test。
原方案文件hash`cb2d17a135d513ac379e577348f2ec9a839f146a4612a6d8b5b0445a2805ab2e`，
完整原文留在artifacts，不改写成已批准的协议。

独立复核发现：报价层尚不明确，分钟端点/并列顺序/报价新鲜度等规则没有落到可执行定义；
固定零baseline与拟合候选的比较不能直接声称只改特征；无法训练不等于特征被证明没用；
更多行和当前Gamma hash不能自动证明历史时钟/身份。公开阅读实为两个URL的四段共24000
字符；prices页6000–12000段没读，不是它所写的三个页面或连续0–18000。搜索0次。
前期research note的日期和baseline定义与最终方案有变化，以最终登记方案为准，旧草稿保留。

复核研究：2026-09-11检索`site.scikit-learn.org Ridge alpha 0 fit_intercept false objective function`、
`site.scikit-learn.org DummyRegressor constant strategy constant prediction`、
`site.scikit-learn.org common pitfalls data leakage test data preprocessing`。
阅读官方[Ridge目标与参数](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)、
[常数预测参数](https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyRegressor.html)、
[泄漏与预处理](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)相关部分：
alpha=0是最小二乘，不是强制零预测；固定值baseline与拟合模型需分别声明；转换和选择不能
借用之后的评分数据。这是模型定义与实验规则依据，不证明本数据有收益，也不替controller
规定信号、时长或trainer。没有安装或升级scikit-learn。

独立复核写成绑定原方案的反馈，只有声明和解释，不会清除QA或启动计算。两个新增反馈测试
通过，另两个原准备测试仍通过。接下来同一已发布DSH只做一次有反馈的方案修订，保留父方案；
这是收到具体批评后的下一次研究决定，不是盲重采样挑最好结果。没有市场分数可以筛选。

本轮后账本：计量$31.546487222；包含历史不确定额的有效成本$35.405392832；另有旧预留
$2.30；可用$162.294607168。其中learning可用$91.245120506，final$50与repair$20未动。
发票仍未完全核对，预留和已消费分开。

## 同一版本下收到反馈后的实际修订

`source-study-revision-controller-20260911-01`已完成：176.875秒、8个计费turn、10个工具
调用，计量$0.571928202，不确定额0，0市场拟合。一个带URL片段的阅读请求被拒绝，
去掉片段后成功；最终方案第一次提交即登记成功，正常defer退出。DSH源码、模型、来源
QA与预算不变，只增加已绑定的父方案和独立反馈。方案文件hash为
`c6b0e98cfdc5979bfb7cae2902336c9dfbdf56e545ae411abb060df7c1f09659`。

| 复核意见 | 实际修订 | 仍需检查 |
|---|---|---|
| 直接报价与本地深度不能混为一谈 | 明确改选直接best_bid/best_ask计算mid | 文中又声称series没变；应明确此次定义改变，不能说只改特征 |
| 常数baseline不是拟合模型 | 明确只声称候选与固定零baseline比较，不是特征消融 | `changed_layer=features`仍不能代替准确的比较定义 |
| 失败不等于没有信号 | 分开已评分但不支持、未能评分的不确定结果 | 还没有任何真实分数 |
| 分钟端点没定义 | 选择向过去寻找最近观测的backward as-of，补同时间排序和缺失计数 | 没新消息的端点仍被称作真实零变化；连续覆盖/新鲜度未被证明 |
| Gamma身份要求多余 | 对其不使用外部metadata的方案取消Gamma和sum-to-one要求 | token连续性和时钟仍待证据 |

新会话实际读完了pandas merge_asof送达的9828字符，读了scikit-learn交叉验证前12000
字符；两个URL、四段正文，共21828字符、4次成功fetch，总HTTP正文451010bytes。
无新搜索。全文送达不等于理解正确。其对父阅读账目的修正仍有
算术遗漏：父realtime未读34312字符，prices未读17111字符，而不是约28k/11k。

执行方另外阅读[pandas merge_asof](https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html)
的backward/forward、tolerance、exact-match与示例部分（2026-09-11）：它定义查找哪一条
已观察记录，不证明两条记录之间价格一直有效。这里将其用于指出方案局限，没有用它造
标签或选择tolerance。另查当前`checked_learning.py`，已有
`clip_to_probability_delta_bounds`实际裁到`[-mid, 1-mid]`，不是`[0,1]`。controller可选择
不裁剪，但它反对该现有变换的解释不准确；保留原文，不偷偷替它改。

## 发现并修复另一个交接问题

已存在的逐日原始文件清单没有进入上述两个新工作区的当前findings。清单不是新数据：
122个文件、11,889,232,674压缩bytes；Aug21/22/23/24/25、Sep7/8/9的文件数依次为
24/4/0/0/22/24/24/24。Aug23、24在该目录没有文件，不等于证明交易所停市或所有档案缺失。
controller只见“允许规划的日期”，不见这份逐日清单，不能把它选到缺文件日期全归咎于模型。

新增`source_inventory_context.py`：校验固定清单hash、来源、日期范围、文件名、逐日数量和
字节总额，再把汇总自动带入以后新建的方案及修订工作区。它不改日期选择、不删除原始行、
不把24个小时文件当完整一天。三个新单元测试及一个本地固定清单检查通过；另外四个准备/
反馈测试仍通过。复用本日来源绑定与统计/定义分离的方法，无新金融方法或新行情扫描。
已完成会话的输入不原地改；此修复尚未通过新付费会话验证。没有为此再启动第三次模型调用。

本次接续两次真实GLM会话合计$1.192838886。最新原$200账本：计量$32.118415424，
含旧不确定额的有效成本$35.977321034，旧预留$2.30，可用$161.722678966；learning
可用$90.673192304，final$50/repair$20仍保留，发票未完全核对。

结论：补上方案入口后，GLM能交方案并据具体批评作部分修订；还不能可靠地写出可执行
协议，也没有训练/性能提高证据。下一次需先带入已修好的逐日清单，再让它解决端点新鲜度、
缺文件日期和时钟依据，不应直接把当前文本编译成训练数据。当前两个runner都已退出。
# Inventory-informed continuation — September 11

The next input corrects two runner issues, not model performance: the missing
per-day file inventory, and duplicate finding IDs when feeding back more than
one completed revision. The fresh-workspace preparer now gives superseded
current-role findings historical IDs bound to their parent manifest. Their
contents remain visible; parent files are never edited. Duplicate/colliding IDs
fail closed. Two new tests pass, alongside40 source-related tests.

`audit_tools/source_study_revision_feedback.py` independently pins revision1,
its first registered proposal and terminal audit. The receipt is
`artifacts/source-study-inventory-review-20260911-01/review.json`, internal hash
`4f6b01736bdaa9352a6f63677a15d54c158f95a04c3861c580f1dedfe1b0d309`.
It separates the runner's inventory omission from the controller's outstanding
assumptions: no-message windows are not verified zero moves; backward-asof is
record selection, not continuous quote validity; same-ms start decisions need
an exact causal watermark; observed timestamp order cannot attest capture time.
It also corrects attribution (the source changed) and clipping semantics
(`clip(delta,-mid,1-mid)`, not`clip(delta,0,1)`). No tolerance, signal, horizon,
trainer or chosen date is supplied by the reviewer.

Research reuse, September11: no new query/search is claimed. The earlier read
pandas`merge_asof` backward/exact/tolerance sections and scikit-learn leakage
sections apply unchanged to these record-selection and causality questions;
see the full URL/query/read records below. Neither source certifies this
archive's continuity or receipt clock. The added code handles evidence identity,
not a new statistical method. A next controller call must select its own
bounded evidence operation or identify genuinely unavailable external evidence;
do not execute another unspecified whole-day scan or certify a textual plan.

The external adapter is versioned separately as
`pm-source-revision-context-v0.1.0`. DSHv1.3.0, its published source and real-tool
canaries remain unchanged. This section is preparation, not a completed third
session; actual dispatch and costs are recorded separately after completion.
# Completed inventory-informed revision and object-scope check

Published object-scope adapter commit`0c8e53bf32a874f5aa26c056ddcc346435cfcbf6`,
annotated tag`pm-source-object-scope-v0.1.0`, verified on privateorigin.
Post-publication metadata dry run02 completed with unchanged counts and expected
refusal of incomplete bindings. Artifact
`artifacts/source-study-object-scope-audit-20260911-02/audit.json`, internalSHA
`31ef6db3985514d7adcd70a90207e5f4489b0b4a0f49dc07bc831ccd0d67ca6c`.
This is the final-source check; the earlier development report01 is preserved.
No controller was called again and no raw-data scan or fit was started.

One real GLM session completed in217.451s:9paid replies,9tool calls, exit0,
valid terminal handoff, both exact processes reaped, unchanged DSHv1.3.0.
Actual token-metered cost was`$0.671701086`; uncertainty0, fits0. One omitted
finding acknowledgement was corrected. Two attempts at the pandas time-series
guide failed the extracted-text size bound; changing offset did not solve a
whole-document bound. A later merge_asof read succeeded:1URL,6,000 of9,828
characters,55,833HTTP body bytes. No search or full-page read happened this
session. The later proposal invents combined source/read counts; preserve that
failure and use event receipts as authoritative. The earlier successful research
record itself reported this session's reads accurately.

Workspace`artifacts/source-study-inventory-controller-20260911-01`, manifest
`2cb7e29e5aacc9d77c94f57aa75e8713a69aa0f673a19094bd78bd24ff275e02`.
First valid proposal fileSHA
`7ff30153bfdf984706e7efbb0a4c9e5088e63949ec41abe43f15aa66108d7587`;
internal proposalSHA`6659d04013ca59db7e6c2dd7d4efb720f2d87b4821fb8855cad81fa93da0064c`.
Session audit`artifacts/source-study-inventory-controller-audit-20260911-01/audit.json`,
internalSHA`e7d90637654a192edf3ba5a1110be4aa93a6791747bb733bf490e3990af211cc`.

Independent outcome review, not a controller-authored conclusion:

| Check | Actual result |
|---|---|
| Inventory feedback | Removed Aug23/24 from fit; those dates have no observed files |
| Requested work |8dates before /6after, but122files and11,889,232,674compressed bytes in BOTH |
| Content commitments | Cited raw manifest contains only Aug21T00:1file/331,091,663bytes;121files/11,558,141,011bytes not bound |
| Narrowed prediction claim | Constant-zero vs fitted lag model remains baseline-only, not a feature-effect or RSI result |
| Causal definition | Earliest strictly-greater timestamp watermark is now named, but proposal also calls it a minute-step rule; decision delay vs t-based horizon is not consistently defined |
| Missing/invalid quotes | Source text denies continuous-state validity, but objective still calls retained no-refresh values genuine labels; an 'uncrossed one-sided row' handling phrase is contradictory |
| External evidence | Quiet-vs-outage still requires original capture/heartbeat evidence; no bigger date scan can supply that fact |
| Market training | None; no MSE, baseline score, promotion or PnL produced |

The date-count reduction alone does not reduce observed-file work. The proposal
says not to repeat the completed first hour while requesting objects on all six
dates, without an exact object exclusion list. Do not turn this prose into a
wholesale replay request or silently choose exclusions for the controller.

`audit_tools/source_study_object_scope.py` now performs a metadata-only dry run
and a tested fail-closed full-binding check. It does not hash remote files, read
raw prices, admit source quality or start any worker. Complete bindings would
still not be QA approval. It also supplies explicit current manifest scope in
future revision inputs. This corrects another runner omission: earlier prompts
did not reconcile filename inventory with the one-object content manifest.
Do not attribute absent input context solely to controller weakness.

Research reused: earlier TFDV schema-vs-statistics and pandas/scikit causal
lookup references below. No new statistical method/search was introduced by
this file-set reconciliation. Existing metadata is sufficient for this check;
no source acquisition or empirical fit is needed. Six new scope tests (one on
the actual completed local artifact) plus earlier source tests give46; the two
revision-history tests give48. Separate unchanged-DSH regression:146PASS.
The first local development scope report01 is retained; a fresh report02 is
required after the final adapter publication. Never rewrite a prior receipt.

Budget after the session: metered`$32.790116510`, effective with old uncertainty
`$36.649022120`, reserved`$2.30` (not spend), available`$161.050977880`.
Learning available`$90.001491218`; final50/repair20protected; invoices not
reconciled. All three source-study sessions together cost`$1.864539972` and
produced0fits. No fourth paid revision or full-data scan has been launched.

Next: resolve an exact, resource-bounded evidence operation and internally
consistent causal/invalid-state rules before source admission. Do not repeatedly
buy another vague defer, infer receipt provenance, or count planning as training.
