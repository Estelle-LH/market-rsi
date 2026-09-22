# Market RSI — Supervisor 总路线图与当前任务

更新：2026-09-22 16:14 ET。负责人：本会话的总 Supervisor。这个文件是用户看的当前入口；历史细节留在 `HUMAN_PROGRESS.md`，机器闸门见同名 orchestration JSON。任务状态只能按真实 task 和证据更新，不能把计划写成结果。

## 最新决定（后文旧设计表是历史快照）

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
| P0 候选入场整合 | `final_nonexposure_audit` → `capability_contract` | 把 ledger、orientation、Train receipt 组成一个 controlled、candidate-only、non-test consumer，关闭 path/symlink/TOCTOU | REPLAN / remediation ACTIVE · reviewer 找到 generic authority-key 升级和 ancestor symlink/hardlink race 两个反例；实现方正修第二版，不授权 rights/admission |
| 恢复合法数据调查 | GLM Controller → broker/researcher | 新版本已有，已构建全新无费用输入 packet 并重新计数 3310 输入 + 2750 最大输出，单次 hard upper `$0.0494991`；等新决定后单独审核 | WAITING · 现无运行任务；单次新请求授权尚未收到。授权后仍需新 ID、进程/账本/全局状态复核；不连续重抽旧 ID |
| 2026 Final 候选未暴露证据 | 独立 auditor；Supervisor 复核 | 只读查访问记录、市场机制和权利回执；不看结果、不换日期 | DONE · 现有证据无法独立证明完整访问历史、标签未暴露、权利或同机制市场覆盖；候选保持未入场，见 `AGENT_LOG_FINAL_NONEXPOSURE_2026-09-22.md`。后续补证独立进行，不阻塞 Train-only 来源调查 |
| 正式预测自循环与独立比较 | Controller + researcher + evaluator | 合格多季数据、固定目标/分割/强 baseline，再逐轮比较 | BLOCKED · 还没有合格实验；2026 赛程预留 Final 的首日 9/20 已过，访问历史/同机制市场/权利仍未证明，不能视为已入场 |

第一波三路零费用验收已完成，当前工程编排计划是 `SUPERVISOR_PARALLEL_ENGINEERING_2026-09-22-v1.json`；格式边界机器计划 `SUPERVISOR_GATE1_FORMAT_BOUNDARY_2026-09-22-v5.json` 已通过 resolve 检查。失败、费用、清理证据：`GATE1_V020_FIRST_RESPONSE_FAILURE_2026-09-22.md`。下面的旧表保留为历史，不表示这些旧任务现在仍在运行。

## 现在到底在哪

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

当前最短路径是先修正式运行路径。独立发布审查给出 REPLAN：Wave 2 编译器等模块原先没进受控源码清单；正式 Controller 只输出 task/proposal，没有进入 exact-request compiler；交易查询只认合成目录；源码仍 dirty。前两项已在本地因果修复：五个 Wave 2 文件进入受控清单，固定交易任务接到 exact-request compiler，外层从原始决定重新编译并逐字节核对请求清单。攻击性检查又发现真实目录前置检查会挡住 Controller 提出新来源；现已将两条权限分开：文档调查/待审提案不要求真实目录，固定交易计划没有它仍会失败。当前无目录 packet 的工具菜单也不再提供交易操作，避免引导 Controller 走无法执行的分支。80 项相关测试和新的无目录、零 provider 生产路径 canary 通过；但登记表仍只有合成目录，真实交易不能执行。完整测试在当前环境受缺 scipy、端口权限及旧 E2B 条件影响。真实 Train catalog、独立审查和发布仍未完成，新付费 GLM 未获授权。离线合成测试通过不等于真实自循环预测已跑通。

## 接下来的顺序

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
