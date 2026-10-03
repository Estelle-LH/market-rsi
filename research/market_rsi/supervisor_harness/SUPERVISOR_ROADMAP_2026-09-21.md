# Market RSI — Supervisor 总路线图与当前任务

更新：2026-10-03 18:18 ET（最近时钟观察）。负责人：本会话的总 Supervisor。当前入口以本节和 `RESEARCH_STATE.md` 为准；下方 September29 与更早记录保留为历史，不同任务的成绩不混用。历史细节留在 `HUMAN_PROGRESS.md`，状态只能按真实 task 和证据更新。

## 2026-10-03 当前：真实赛中 Train 自主预测实验

沿用 `InGameWinProbabilityTrainDiagnostic-v0`：195场完整分母，193有效+2明确排除；同87比赛/20日期/7周，四个既定 chronological checks，equal-event Brier 与固定评分规则不变。赛前 settlement 与60/300秒 MSE 均是独立历史任务。

本次19:10:37–00:10:37UTC五小时最大窗口已实际完成并独立核验10候选/40fits，提前达到保留的10次尝试上限，并非五小时已过。四轮反馈依赖的后代不是预排模型：A1/A2证据→A3损失；B1/B2证据→B3输出链接；C1/C2证据→C3联合count/freshness；C3负结果/尺度证据→C4有效先验。每个真实预测产物、源码checkpoint、父分支、市场比较、时间块/分组interval、失败和反馈都有记录。

Raw市场 incumbent Brier/log0.1419525290/0.4296707847 未变。最低观测候选Brier为C2 0.1419480777，仅改善0.0000044513，2/4块、区间跨0，INCONCLUSIVE/REVERT；不是确认市场优势。C4有效先验候选0.1426785345/0.4291441157，log改善但Brier输raw/C3，2/4块、全部raw/parentproperloss区间跨0，REFUTED/REVERT。十个候选均未更新最佳；旧成绩和KEEP规则没有追溯修改。

当前执行：十候选段独立closurec8bcc3fc与Controller记忆fd3e2e3a均完成并永久保留。最新五小时不停止指令被Supervisor前瞻解释为允许另开有界pilot，不扩旧cap或编造用户对异步问题的回答。C5 contract2da17c7c冻结一个真实C4后代：同信息/同scales，Brier训练与past-fit局部diagonal data/prior曲率单位，预声明有限同目标optimizer continuation。Worker实现/测试和Reviewer数学/源码检查并行；尚未训练，不把proposal/code称为成绩。旧十候选记录不追溯改写。

已完成十候选段40fits，870predictionversions来自同87比赛；worker-wall42.696988秒不等于整个研究耗时，采样peak142528KiB/child。旧三个3/12和最终1/4批次封闭、不扩cap、不重试。前瞻continuation最多3新attempt/12fits；pilot05单独1/4/90min且clip原00:10:37UTC，每次900秒/单线程/采样RSS1GiB。后续两个slot必须先有新真实反馈和独立contract，不能预排假迭代。C2唯一followup由C3消耗，保持排除。Provider0/$0，Codex成本未知。

已证实的是可信本地Train执行与反馈驱动的自主预测器优化。H有人工集成/绑定修复；此次科学候选没有R研究流程自修改。尚未运行同模型同预算固定流程对照；不得宣称自迭代机制优越、untouched OOS、实时接收时间、PnL或正式promotion。Exact Controller serving version未知，历史NFL为seed而非永久范围。Dev/Final、网络新增数据/文献获取、付费、push/release与promotion仍关闭。

最近证据入口：`HUMAN_PROGRESS.md`十候选结果表、`COEVO_TRAJECTORY_2026-10-03.jsonl`十三条变化轨迹、`COEVO_RESULT_REVIEW_C4_2026-10-03.json`。Root179in-game/123candidate-boundary/34scoring各suitePASS，计数有重叠；旧full920diagnostic仍45errors/1failure/1skip。只报告实际证据，不把框架/测试完成当预测或自迭代成功。

## 2026-09-29 `SettlementProbabilityTrainDiagnostic-v0`（历史赛前任务）

主线已经切换为 **赛前 settlement probability**。旧的 60/300 秒价格变化 + MSE benchmark 只保留为独立 legacy experiment，不能与当前 Brier/log-loss 结果混用。NFL 是按结果无关的数据就绪标准选出的当前 seed domain，不是 Market RSI 的永久范围。

第一张真实 Train scorecard 已完成并独立复核。`first-real-train-diagnostic-nfl-settlement-20260929-02` 保留 195 场/42 个赛程日完整分母，194 场为二元目标，唯一排除是 `2025_04_GB_DAL` 的 0.5/0.5 平局；四个 expanding check 共 87 场、20 个已反复查看的 Train 赛程日。结果：market Brier/log loss `0.205533/0.598451`，ordinary LogisticRegression `0.235605/0.675948`，HGB `0.269768/0.779223`。HGB 只赢 ordinary 的第 2 fold，diagnostic 决定为 **REVERT**。LogisticRegression 只是 ordinary reference，不是 `Strong-Baseline-1`。

第二张真实 Train scorecard `first-real-train-diagnostic-market-offset-ridge-20260929-02` 也已完成并独立复核。`MarketOffsetRidgeLogistic-v1` 的 Brier/log loss 为 `0.209451/0.608268`：明显优于 ordinary Logistic，但差于 market，且四个 fold 的 Brier 全部输给 market，因此 **REVERT**；market 继续是当前最佳，offset/HGB 代码、结果和经验仍作为研究分支保留。inclusive 600 秒 gate 对 194 个二元事件通过，实际最大 313 秒。完整赛程日重采样并重算等比赛指标后，offset-minus-market 的描述区间仍在零以上；这些是反复查看的 Train 证据，不是正式 OOS。

offset 完成后，Astra/high Controller 选择的下一项 `MarketOnlyRidgeCalibration-v1` 已实现、通过独立 pre-score review、真实执行并通过独立结果复核。它的 Brier/log loss 为 `0.205852/0.599385`，比 raw market 差 `+0.000318/+0.000934`，只赢 market 2/4 folds，因此 **REVERT**；它仍明显优于 ordinary。archived full offset 比 calibration 又差 `+0.003599/+0.008883`。这完成了本轮要求的“市场校准收益 vs 额外特征收益”拆分：这一个固定 past-only calibrator 没有总体收益，而把其他 16 个标准化 residual 坐标全加入同一 ridge recipe 造成了更大损害。

连续自主 Discovery 第一批在两小时硬上限内完成了 5 次真实候选执行，并逐项通过独立结果复核。证据链依次推动了“压缩路径 → 最近三周 → 固定 recency 权重 → 全历史衰减消融 → 在 recency incumbent 上增加正交 dispersion”。`MarketRecencyWeightedCompositePath-v3` 是当前 Discovery incumbent，Brier/log loss `0.203857/0.595837`，相对 market 为 `-0.001677/-0.002614`，赢 3/4 market folds。第五轮 dispersion 候选 aggregate 更好（`0.202260/0.591819`），但只赢 market 2/4 folds，因此按冻结规则 REVERT；它作为最有希望的失败分支保留。完整批次证据见 `DISCOVERY_BATCH_2026-09-29.md`。

当前 P0 是解释并降低 dispersion 分支的折间/符号不稳定，而不是扩建治理层或修改评分口径。下一批优先测试因果 shrinkage 或 sign-stability 处理，保持 v3 incumbent、相同 masks/scorer 和所有 protected boundary。等连续闭环稳定后，再单独做相同 Astra、相同权限和等资源预算下的 fixed-process vs memory/process-improving 多次独立运行。

停止新增 harness、governance、receipt、canary、PMB adapter 或正式多域 benchmark。继续禁止 protected Dev/Final、外部抓取、付费 provider、发布和 promotion。等 calibration attribution 和连续 Discovery 闭环稳定后，再单独设计同一 Astra、同一数据权限和资源预算的 fixed-process vs memory/process-improving 多次独立运行；那才评价 self-evolution，不能把基础模型升级或某一候选成败归因于 RSI。

## 2026-09-29 主线纠偏（已被上面的 Train Discovery 解锁进一步取代）

已撤回“以 PredictionMarketBench 为主底座”的假设。PMB 仅保留为公开、非可信、可过拟合的 compatibility/smoke lane；不作 hidden Final、promotion gate 或 prediction 改善证据。旧 PMB 决策/评审保持不可变历史，后续 source intake、episode 下载、adapter、hidden evaluator、Controller Swap 和更多 PMB 治理停止。

当前主线压缩为三个并行但文件互斥的缺口：`settlement probability contract + proper scorer`、`candidate/evaluator 进程与文件系统隔离`、`KEEP/REVERT 聚合记忆链`。整合验收只跑两轮本地 synthetic loop：第一轮 KEEP、第二轮 REVERT、重启后状态不丢、Final 永不打开。它只证明闭环可运行，不证明预测提升。

本地 v0.1.26 release candidate 和 annotated tag 完整保留，但发布/canary/fetch 链现在策略性暂停；它不能关闭上述三个科学 blocker，也不再是下一里程碑。下一次需要用户看到的成果应是最小 prediction loop 的可运行证据，而不是新增治理层。

## 历史 operational snapshot（2026-09-28；已被上面的 2026-09-29 主线纠偏取代）

v0.1.25 已发布、远端独立验证，并通过 fresh zero-provider production-CLI canary。付费 D0 `market-rsi-v0125-gate1-controller-d0-20260928-01` 随后只运行一次并通过独立终审：4,020 input / 511 output / 0 cached tokens，计量 `$0.02574585`，无重试、无 incident；预算为 `metered_terminal`，global state 已关闭且 idle，74/74 watchdog 健康，最终无残留进程或容器。该永久 ID 已消费，绝不重跑。

Controller 返回了一个有效但不可执行的 `source_scope_decision`：选择注册的 Polymarket 官方 market-scoped trades response class，用于 private research，未来角色 `unassigned_candidate`，descriptive/no-forecast，提议一次最多 300 秒的一方文档审查。所有网络、provider contact、抓取、保存、花费、Train/Dev/Final、训练、评估、发布权限位均为 false。因此这是 operational D0 PASS，不是数据或预测实验结果。

| 当前工作 | 负责人 | 状态 | 下一检查 |
| --- | --- | --- | --- |
| v0.1.25 D0 一次执行 | Supervisor | DONE · PASS | 永久归档；不重跑 ID |
| D0 独立终审 | independent terminal reviewer | DONE · PASS | 原始回答、单 sample、费用、预算/state/cleanup 均已核验 |
| 受保护决策状态 | Supervisor | DONE · rebound | decision SHA `a727445b…f417`，state head `3b4eff7c…86ca`，`active_cycle=null` |
| D0 -> exact-request bridge | Supervisor + 独立离线审计 | DONE · PASS | plan `34b45266…b9b812c`；341-file local RC `c8053164…a51faee2`；未发布 |
| 实际文档/公开数据 fetch | 外部授权 gate | BLOCKED | 必须有 exact request、权利/上限/停止条件和单独授权 |
| Train/Dev/Final、训练与评估 | 数据/实验 gate | BLOCKED | 仍无 admitted real Train catalog；不得跳级 |

机器闭环计划 `SUPERVISOR_GATE1_V0125_D0_TO_REQUEST_BRIDGE_2026-09-28-v1.json` 已完成：两份前置审计、离线集成、12/12 focused、516/516 full（2 skips）、并行 fetch-boundary 交叉复核和 fresh 非作者终审全部 PASS。**这是 2026-09-28 当时的 next-action 记录；发布/canary 路径已被 2026-09-29 prediction-first reset 暂停，不再是当前最短路径。**

## 历史快照（2026-09-22）

当前不是预测实验在跑。**Gate 1 格式边界的代码修复已发布并验收**：严格解析器加五字段短选择接口，受控 324 文件源码哈希 `872f05ae…0986da`，fork 上的 annotated tag `market-rsi-protocol-v0.1.21` 指向 `f06214b3bb521096078d897fe60ec9ba589c00c6`。独立整合审查、132 项 Gate 1 测试和 20 项解析/类型测试通过；发布后的生产 CLI 无目录合成 canary `market-rsi-gate1-v021-postrelease-canary-20260922-01` 通过，provider 调用/真实费用/公开抓取均为零。两次旧 Controller 回答仍是失败终态，计量合计 `$0.03457161`，不能重试或重写。新接口**尚未取得真实 Controller 决定**，更没有市场数据抓取、真实 Train 入场、训练或 Dev/Final 读取。权威 `$200` 账本总计量 `$85.122553742`，setup 可用 `$0.071505532`，另有历史预留 `$2.30`；预留不等于实花。

| 当前工作 | 负责人 | 要交付的东西 | 状态 |
| --- | --- | --- | --- |
| 复核两次失败与工具调用边界 | 独立 format-boundary researcher | 核对原始标签、解析器、真实 SDK 能力 | DONE · -02 是标签损坏；本地取样路由无已证实的语法约束 |
| 收紧工具解析器 | 总 Supervisor + 独立复核 | 整段解析，不忽略未闭合尾部；旧 -02 仍失败 | DONE · 已独立复核并随 v0.1.21 发布 |
| 缩短 Controller 提交接口 | 独立工程 task，Supervisor 整合 | 八个短选择 ID，模型只提交五个字段；可信代码派生执行细节，新来源仍可提案 | DONE · 独立整合复核及发布后零费用 canary 通过；尚未实测新 GLM 回答 |
| 单次 Controller 启动验收 | `gate1_integrated_release_review` | 固定新 ID、packet/版本/hash、runner、预算、进程和终态回执 | DONE / HOLD · 机械条件通过；缺本次付费请求的新授权，不能启动 |
| 真实 Train 入场关键路径 | `gate1_firstwave_audit` | 串起 Controller 方案、权利、精确请求、完整重下、覆盖检查与 catalog 入场 | DONE / REPLAN · 找到 formal receipt、v2 cursor、权利、285 场分母与方向等缺口 |
| 封存 Final 元数据补证 | `final_nonexposure_audit` | 设计现有候选的补证/拒绝标准和未来窗口 fallback | DONE · 访问历史不完整时只能判 not provable；候选仍未入场 |
| 正式 Train admission receipt 闸门 | `gate1_firstwave_audit` | 实现 code-owned receipt/validator，并绑定训练/评估入口 | DONE / scoped PASS · 独立复审通过；整合仍 REPLAN：未进 controlled manifest、无正式训练/评估 caller、post-claim TOCTOU 未关闭 |
| Polymarket v2 cursor 采集契约 | `gate1_integrated_release_review` | 实现版本正确的 cursor manifest/receipt validator 和硬上限 | DONE / offline PASS · 独立对抗复审通过；仍无 live executor、网络、权利、catalog 或 admission 权限 |
| 2024 完整 285 场候选账本 | `final_nonexposure_audit` + `DONE · P0 285-game ledger rereview` | 固定完整分母、284 映射与一个明确缺失行；绑定来源哈希，不补造 | DONE / scoped PASS · -03 经独立反例重放通过；285=284+1，285/285 行承诺与来源绑定可重算；仍非正式 admission |
| 2024 主客队/代币方向校验 | `gate1_integrated_release_review` + `gate1_firstwave_audit` | 用显式别名和来源绑定生成候选 orientation receipt；歧义 fail closed | DONE / scoped offline PASS · 17/17 focused、73/73 adjacent、11/11 ledger-adjacent、18/18 independent adversarial；集成仍 REPLAN：未进 controlled release、无 non-test consumer/path provenance |
| P0 候选入场整合 | `final_nonexposure_audit` → `capability_contract` | 把 ledger、orientation、Train receipt 组成一个 controlled、candidate-only、non-test consumer，关闭 path/symlink/TOCTOU | REPLAN evidence preserved / PAUSED by 2026-09-29 reset · 不授权 rights/admission |
| 恢复合法数据调查 | GLM Controller → broker/researcher | 新版本已有，已构建全新无费用输入 packet 并重新计数 3310 输入 + 2750 最大输出，单次 hard upper `$0.0494991`；等新决定后单独审核 | WAITING · 现无运行任务；单次新请求授权尚未收到。授权后仍需新 ID、进程/账本/全局状态复核；不连续重抽旧 ID |
| 2026 Final 候选未暴露证据 | 独立 auditor；Supervisor 复核 | 只读查访问记录、市场机制和权利回执；不看结果、不换日期 | DONE · 现有证据无法独立证明完整访问历史、标签未暴露、权利或同机制市场覆盖；候选保持未入场，见 `AGENT_LOG_FINAL_NONEXPOSURE_2026-09-22.md`。后续补证独立进行，不阻塞 Train-only 来源调查 |
| 正式预测自循环与独立比较 | Controller + researcher + evaluator | 合格多季数据、固定目标/分割/强 baseline，再逐轮比较 | BLOCKED · 还没有合格实验；2026 赛程预留 Final 的首日 9/20 已过，访问历史/同机制市场/权利仍未证明，不能视为已入场 |

第一波三路零费用验收已完成；当时工程编排计划是 `SUPERVISOR_PARALLEL_ENGINEERING_2026-09-22-v1.json`。当前计划已换为 `SUPERVISOR_PREDICTION_FIRST_RESET_2026-09-29-v1.json`。下面的旧表保留为历史，不表示这些旧任务现在仍在运行。

## 历史设计背景（2026-09-22）

目标是让 GLM Controller 指挥研究者，用真实 NFL 预测市场数据反复提出并检验预测方法，最后在同一批合格样本、同一目标和未见过的日期上，与强普通模型比较。**目前还没有跑出一个合格的真实自循环预测实验。** 2024 有整季交易与标签支持证据；2023 仍有 48/285 场身份缺口且固定常规赛样本有零成交；2025 只有一场直接交易检查；旧 Final 仅 11 个日期，低于预设的 20 日期底线。

Controller 的科研选择应尽量开放：可提出新数据来源、匹配/质量方法、目标、特征、算法和工具。Supervisor 不替它改写已提交的科学决定；只审核执行权限、数据时间边界、费用、来源权利及独立评估。**当前 Gate 1 只实现了很窄的一段**，不能把它误称为 Controller 已经“几乎什么都能做”。原始回答和单独标记的 Supervisor 可行性修改见 `GATE1_ORIGINAL_CONTROLLER_PROPOSAL_FEASIBILITY_2026-09-22.md`。

### 放宽 Controller 的研究空间：Supervisor 的当前安排

放宽的是**提案空间**，不是直接执行权限。Controller 可以先提出问题、来源、文献搜索、数据核对、目标、特征、算法或候选 harness 修改，不必从固定的五个问题和四个来源里挑。它也可以根据上一轮事实性失败反馈改变路线。研究者只能执行经 broker 编译、授权并记录的具体动作；新来源或新工具先进入审查队列，不能因模型提到就自动获得网络、密钥或写权限。未来信息、封存 Dev/Final、来源权利、总预算、唯一运行 ID 和独立评估仍是硬边界。

| 顺序 | 负责人 | 具体交付 | 通过标准 / 当前状态 |
| --- | --- | --- | --- |
| 1. 把真实限制和失败原因说清 | Supervisor | 给下一次 Controller 输入原始决定的哈希、失效点、实际可用操作及每个操作的请求/样本/时间/费用上限；不替它选新方案 | 本地 packet/adapter 已加入事实反馈和精确 capability；离线 token 预检 2,482 输入 + 3,072 输出上限，费用硬上限 $0.04938732，低于单次 $0.05；尚未发布或调用模型 |
| 2. 核对执行路径 | Supervisor + 独立审查 | 聚焦测试、源码/账本审查、全路径零费用 canary；验证文档调查可执行、新提案只归档、无真实目录时交易操作不出现在菜单 | 124 项 Gate 1 相关单元测试通过，`git diff --check` 通过；新 ID `market-rsi-gate1-offered-operation-fix-canary-20260922-01` 的无目录、零 provider 生产参数路径 canary 通过；修复后的独立窄范围复审 PASS。发布审查仍未完成 |
| 3. 让 Controller 自己重提方案 | GLM Controller | 在新的已发布版本和新永久 ID 下只取第一份有效回答；可改走文档调查或提出新来源/工具，不用旧回答冒充新决定 | 需要另行授权付费请求；Supervisor 不重采样挑分数、不补写模型的科学决定 |
| 4. 把提案变成可执行研究任务 | Supervisor/broker + Researcher | 对 Controller 选的路线核查来源权利和时间边界，编译精确请求及成本上限，Researcher 执行并保留原始证据；不支持的动作先扩充 broker 并复测 | 每个动作在执行前有来源、权限、费用、停止条件和可复核回执；未满足就明确返回原因，不长期静默卡住 |
| 5. 用事实反馈形成下一轮 | 独立 evaluator + Supervisor | 检查数据覆盖、质量、错误和实际费用；向 Controller 返回聚合、带来源哈希的反馈；候选 harness 改动单独版本化 | 下一轮能区分“数据/执行改善”与“预测模型改善”；只有合格未见日期的对照才能宣称预测进步 |

Supervisor 每次最多推进当前依赖链上的一个付费动作；能并行的仅是互不写同一状态的零费用查证、代码和审查。若一步约一小时仍无判别性结果，就记录具体卡点、改变最小下一检查，而不是静默等待或重复付费。是否换更强 Controller，先看放宽后的**有效提案率、可执行率、失败后改道能力和独立证据增量**；目前一次被过窄菜单卡住的回答不足以证明 GLM 弱。

当时的最短路径是先修正式运行路径。独立发布审查给出 REPLAN：Wave 2 编译器等模块原先没进受控源码清单；正式 Controller 只输出 task/proposal，没有进入 exact-request compiler；交易查询只认合成目录；源码仍 dirty。前两项已在本地因果修复：五个 Wave 2 文件进入受控清单，固定交易任务接到 exact-request compiler，外层从原始决定重新编译并逐字节核对请求清单。攻击性检查又发现真实目录前置检查会挡住 Controller 提出新来源；现已将两条权限分开：文档调查/待审提案不要求真实目录，固定交易计划没有它仍会失败。当前无目录 packet 的工具菜单也不再提供交易操作，避免引导 Controller 走无法执行的分支。80 项相关测试和新的无目录、零 provider 生产路径 canary 通过；但登记表仍只有合成目录，真实交易不能执行。完整测试在当前环境受缺 scipy、端口权限及旧 E2B 条件影响。真实 Train catalog、独立审查和发布仍未完成，新付费 GLM 未获授权。离线合成测试通过不等于真实自循环预测已跑通。

## 历史顺序（已被 2026-09-29 prediction-first reset 取代）

1. **P0 因果修复（现在）。** Wave 2 模块已纳入本地受控清单，bounded-plan 接线与无目录调查/提案路径有相关测试和合成 canary，但仍待独立审查。真实目录入场前，Controller 只能提交文档调查或待审新来源提案；交易分支不进入当前工具菜单，越界提交仍由外层拒绝。待审源码哈希、已跑检查、攻击问题和边界见 `SUPERVISOR_GATE1_BINDING_REVIEW_PACKET_2026-09-22.md`。先完成合并源码攻击性测试、受控清单和脏文件审查。
2. **版本与零费用验收。** 独立复查生产路径、受控清单、dirty 文件范围、预算、唯一 ID 与进程；审查通过后才请求新版本发布授权。在发布的确切版本上跑零费用 canary，核对两种 Controller 终态、exact request manifest 和越权拒绝。未通过就定位因果层，不启动付费请求。
3. **只取 Controller 的第一份有效决定。** 另获一次付费请求授权后，用全新永久 ID、一次 GLM 样本、单次 $0.05 硬上限且不重试。Controller 可以选有界旧来源计划，或提出新来源/匹配/质量/目标假设；Supervisor 不代它挑科学路线。提案只能待审，不能直接抓取。
4. **真实来源调查与数据入场。** Controller 决定通过后，再单独检查来源/执行权限，预先固定请求、样本、字节/时间上限和停止条件；查真实 fills、PBP 时钟、权利与完整逐场分母，保留零成交、身份失败和未知暴露。至少三个可比完成赛季作为 pilot，五年为更强目标；至少 20 个确实未打开的 Final 日期。取不到就明确报告无法正式验收。
5. **预测自循环实验。** 数据入场后，用 opened Train 冻结目标、样本规则和强 baseline。Controller 在预算内迭代 feature、算法、训练与候选 harness；每轮记录决策、代码、工具、成本、失败、独立 Dev 反馈和版本变化。所有方法在同样样本、目标、日期与预算下比较；Final 只在最终候选选定后打开一次。

若真实来源无法满足三赛季或未触碰测试期，结果应是明确的“不具备正式验收条件”和带证据的范围选择，而不是改分母或把旧 Dev/Final 当新测试。

## 历史分工（00:16 ET；不表示现在仍在运行）

当前并行计划为 `SUPERVISOR_GATE1_NEXT_PARALLEL_2026-09-22-v1.json`。两项只读工作已在现有空闲 task 完成并主动发回 Supervisor；整合的独立复审正在进行。源代码快照哈希为 `2544e25605a9c9d731784b492dc5c040f0b43aa47fc911b3f8a373db1312eb4e`。本地适配器边界 PASS，但发布 REPLAN、真实数据 BLOCKED；这些是不同结论。

| Task | 当前工作 | 状态 / 下一检查 |
| --- | --- | --- |
| `ACTIVE · integrated review` | 新独立 reviewer 复核 17 个 dirty 受控文件、发布范围与数据边界 | 已派发，只读；等待单一快照 PASS/REPLAN，不授权发布 |
| `DONE · release scope` | 现有空闲 task 查精确发布范围并主动发回结论 | 发布 REPLAN：17 个受控文件未提交，其中 1 个共享 bottleneck gate；不能把当前哈希当作 Gate-1-only 发布 |
| `DONE · real catalog route` | 另一现有空闲 task 查真实 Train 目录入场路径并主动发回结论 | 只登记合成目录；真实目录 BLOCKED。建议授权后从原始来源完整重下并验哈希，不拼补碎片 |
| `DONE · offered-operation rereview` | 独立复核上一个因果修复 | 新受控源码哈希 `2544e256…312eb4e`；124/124 相关测试及零费用 canary 通过，仅本地窄范围 PASS |
| `Supervisor · Market RSI` | 唯一整合/Git/预算负责人 | 核对两个报告和确切 staged 文件；review 通过前不 commit/tag/push，也不启动新付费调用 |

旧的 S1–S3 结果归档如下；它们不是本波的新 verdict。

| Task | 负责人 / Codex task | 交付与验收 | 状态 |
| --- | --- | --- | --- |
| S1：发布前边界审查 | `DONE · Gate 1 release audit` | 四个 P0 发布缺口；109/109 专测、479/479 非 socket 广域测试，结论仍为 REPLAN | 已完成；发布不通过 |
| S2：真实数据入场证据 | `DONE · P0 data evidence audit` | 核对 2023–2025 分母、回执哈希和未知项，不替 Controller 选来源 | 已完成；数据未入场 |
| S3：任务可见性核对 | `DONE · Supervisor visibility audit` | 查出 20/39 截断；Supervisor 修了展示上限并验证 39 条可见 | 已完成；人工日志并非原始工具流 |
| S4：整合与决策 | `Supervisor · Market RSI`（本 task） | 证据写回日志、机器计划、blocker 看板和本路线图；下一工作是 P0 生产接线修复 | 本次审查完成；尚不能发布或跑付费实验 |

这三个外部 task 在自己的现有 worktree 只读主 checkout；它们无权写主 checkout，故由总 Supervisor 把带来源的结论追加到专属日志并核对原始文件。三个任务已完成并改名为 DONE。没有同时运行的付费研究任务。下一批分工要围绕 P0 因果修复，不再重复三项审查；修复后的独立 reviewer 应与代码作者分离。

## Supervisor 每次检查四件事

1. 哪个任务真在运行？它的最新可见证据和下一次检查时间是什么？闲置/结束就归档，不占据 dashboard 顶部。
2. 哪个 blocker 正挡住下一项有意义的结果？给出负责者、原始证据、最小修复、测试和失败回退；超过约一小时无决策价值就重排，而不是无限修连接。
3. 预算、唯一 ID、发布版本、数据角色和进程/沙箱有没有越界？任何一个不通过，就只停受影响动作并保留记录。
4. 这一轮是否产生了真实新信息？代码通过、合成 canary 通过、来源文档存在，都不能单独称为预测进步。

状态来源：`RESEARCH_STATE.md`（受保护科研决定）、`BOTTLENECK_STATE_2026-09-18.json`（机器 blocker 看板）、`AGENT_LOG_INDEX_2026-09-17.json`（dashboard task 索引）、`HUMAN_PROGRESS.md`（历史）。本文件不绕过任何现有 gate，也不授权发布、购买、GLM 调用、抓取或 Dev/Final 访问。
