# Controller harness v3

> 2026-09-08 更新：下面的早期 canary 使用的是旧 60 秒单点目标，只能证明流程能运行。
> 下一次正式实验先执行 [`TIME_SERIES_RESEARCH_HARNESS.md`](TIME_SERIES_RESEARCH_HARNESS.md)：
> 用公开文献和开放 Train 研究目标，冻结 objective contract 后才允许创建 Dev schedule。
> Controller 在之后可以改模型、特征和训练方法，但不能在看过 Dev 后改目标。

Objective discovery 也是 controller 的工作，不由人预先替它从固定菜单中选答案。Harness 会先
自动给它 source inventory、raw/materialized cadence、target flatness、trivial baseline、跨日期/
比赛差异和 availability 检查，再允许它查论文、提出新的 target 或需要补的数据流。Runner 只
验证因果性、隔离、可执行性和预算，使用第一份有效决定，不按人偏好重抽。完整边界在
[`objective_discovery_harness.py`](objective_discovery_harness.py)。

## 这次改什么

前两版把 controller 当成了一个一次性填表模型：GLM 看一段压缩后的文字，最多输出
4096 tokens，然后交一份短 JSON。它不能自己查论文、打开允许的数据、写分析代码、运行
实验、读报错，再修改方案。Codex 也只是收到最终方案后写一次代码。

这会让 controller 很难真正做研究。Round 1 的 20 个 proposal 没有正式论文引用；v2
canary 还出现过一次有内容的回答因为 `hypothesis` 超过 600 个字符而直接作废。这些都
说明 harness 太窄，不能直接解释成 GLM 没有研究能力。

v3 改成：**GLM 仍然负责研究判断，Codex 负责给它提供一个可以连续工作的研究环境。**
Codex 不是第二个替它拍板的 controller，也不是只写一次代码的 coder。

新实验只保留一种跨任务记忆方式：**Archive**。Controller 可以读取自己以前的完整研究
记录，然后直接决定下一步。旧实验里的 Learn 组不再保留；我们不再另开一条路线，要求模型
把历史压成一份会反复改写的 learned guide。这样不会把“是否保存经验”和“是否会写 guide”
混成两个研究变量。旧 Reset / Archive / Learn 的代码、运行记录和结果仍原样保存，只作为历史
证据，不再驱动新的付费实验。

这里仍有一份固定的 `research-guide.json`。它只是 harness 的使用说明，告诉 controller 要
检查数据、查文献、写清假设、记录失败；controller 不能改写它，因此它不是旧的 Learn mode。

## 一次任务怎样走

1. Runner 给 GLM 一个新的、永久绑定的 research session。它只看到允许使用的 Train、
   Dev、自己 Archive 中的历史、预算和固定评分规则。
2. GLM 可以让 Codex harness 检查数据、搜索公开论文、写代码、在隔离环境里运行
   Train-CV 实验、查看错误和结果，再继续修改。当前轮 Dev 不在这里反复打分。
3. 这些操作都发生在同一个 session 里。不是生成十个答案后挑最好，也不会因为分数不好
   重新抽一次。
4. 研究过程和 notebook 全部保存。最后另交一份小的 decision envelope，告诉 runner
   要运行哪个 candidate、依据是什么、什么结果会推翻当前判断。
5. Runner 独立验证文件和费用，在 E2B 执行，使用固定 scorer。Future Test 继续封存，
   controller 和 Codex 都看不到。

## 给 controller 多大空间

- 每一轮模型调用的输入上限：196,608 tokens。
- 每一轮模型调用的输出上限：65,536 tokens。
- 每个 arm-task session 的累计输入上限：1,572,864 tokens；累计输出上限：65,536
  tokens。
- 最多 24 个模型回合、32 个工具调用、3 个 Train-CV candidate execution。
- 最长 30 分钟。
- 64K 是上限，不是要求它写满。最终交给 runner 的决定最多 16 KiB；长推理、日志、论文
  笔记放在单独的、带 hash 的 research notebook 里。

Controller 每次最多读取约 192K input，并最多输出 64K，不再受原来的 4096 output 限制。
多步 harness 仍有整次 session 的总量上限。按照当前 GLM 的 token 费率，一个 session
用满 1,572,864 个累计 input 和 65,536 个累计 output，最坏模型费用约 `$8.44038144`；
实际费用按所有回合真实 token 相加。

## Controller 可以决定什么

在 objective discovery 阶段，它可以查论文、检查已开放 Train，并提出预测目标。在 runner
冻结 objective contract 以后，它可以自己决定特征、模型、loss / 训练变换、超参数、诊断
方式和下一步，但不能再改预测问题。它不再被 240/600/1800 字符的小框限制研究过程。

它不能改的包括：已经冻结的预测目标和基线、Train/Dev/Future Test 的边界、评分器、可评分
行、预算上限、日志和隔离规则。

## 这是时间序列预测，数据边界怎样定

Controller 可以决定怎样使用已经开放的历史数据，但不能自己挑一个分数更好看的时间切分。
正式 Train-CV 至少需要 4 个 UTC 日期：较早日期 fit，最后 3 天作为一次固定的 future block。
不随机拆行；同一场比赛不能跨 split；fit 的标签若跨过 CV 起点，就把整场比赛从这次比较中
删掉。边界必须在看到 target 和 candidate score 前固定。

每轮 candidate 冻结后，runner 才打开紧接着的完整 Dev，一次评分。评分后的 Dev 进入下一轮
Train，下一轮再使用更晚、从未打开的 Dev。Final promotion 至少需要 20 个未见过的 UTC 日期；
当前 20 场比赛的 Transfer 仍只是 pilot。完整规则见
[`TIME_SERIES_EVALUATION_POLICY.md`](TIME_SERIES_EVALUATION_POLICY.md)。这些规则和 hash 已写入
harness contract，每个 candidate job 也必须保存并通过 `split-audit.json`。

## Codex harness 提供什么

只提供以下受控动作：

- 查看允许的 Train/Dev 数据；
- 读取固定的研究流程说明；
- 搜索公开论文，并保存 query、URL、时间和内容 hash；
- 查看非穷尽的算法目录及每种方法的假设、风险和成本；
- 写 candidate 代码；
- 请求 runner 在隔离 E2B 中运行 Train-CV candidate；
- 查看本路线已经保存的研究记录；
- 提交最后决定。

它不能直接读取 Mac、密钥、Future Test 或别的 arm，也不能自己绕过 runner 发起付费任务。
不能只靠 prompt 保证这些边界；正式运行前要做一个 tool-enabled isolation canary，实际
尝试读取 harmless marker、别的 arm 和封存目录，确认全部失败。

同一轮里，controller 能反复看的分数只来自已经开放的 Train。它提交最终 candidate 并退出后，
runner 才打开当前 Dev，一次执行、一次评分。这个 Dev 分数不会回到刚结束的 session，只会进入
下一轮 Archive；评分后的 Dev 同时变成下一轮 Train。这样 Dev 不会因为被反复查看而变成训练集。

## Logging

每个 session 有三份只能追加的 hash-chain 日志：

- `controller-tool-journal.jsonl`：所有工具调用，以及参数和返回值的 hash；
- `literature-activity.jsonl`：每次检索词、返回的论文 ID、标题、URL、年份和内容 hash；
- `algorithm-activity.jsonl`：看过的算法、candidate 的假设与引用、代码 hash、父版本、执行
  结果、失败和最终选择。

三份日志会交叉检查。正式研究中，controller 自己决定要不要查文献、看算法库，以及采用
什么方法；只要调用了，对应记录就必须和工具总账一一对上。被选中的 candidate 必须能在
日志中追到同一份代码的写入和成功执行。缺一段、改旧记录或 hash 对不上，整轮无效。失败
动作也保留，不能删掉以后假装第一次就成功。验收 canary 会特意走完全部工具，只是检查
harness，不代表正式研究必须按这个顺序工作。

每个 session 还会在启动前写 `harness-runtime.json`。它绑定 Codex CLI 的版本和二进制 hash、
controller model、model catalog、instructions、完整启动命令、关闭的产品功能与隔离开关。退出后
runner 再计算一次；任何运行中变化都会让本次 assessment 无效。这样 Codex 产品更新、项目
harness 修改和 controller 自己从 Archive 学到东西不会被混成同一种变化。

## 当前验收结果（2026-09-08）

Train-CV 与一次性 Dev 的真实执行检查也已经通过：

- `controller-harness-traincv-canary-20260908-01` 中，GLM-5.3 在同一个 Codex harness
  session 里只能反复运行由已开放 Train 切出的 temporal Train-CV。它做了 8 个模型回合、
  14 次工具调用和 2 次真实 E2B candidate execution，最终选择
  `mid_persistence_v2.py`。当前 Dev 的路径和标签没有交给 controller execution service。
- Controller 正常提交决定并退出后，`sealed_dev_runner.py` 才把该 candidate 在旧诊断 Dev
  上执行一次。300/300 行完成，没有失败；结果不会返回已经结束的 controller session。
- append-only data lifecycle 显示 `round-01` 已完成，`old-dev-00` 已从 Dev 转成 Train，
  active Dev claim 已清空。这个 block 不能再作为 Dev 使用。Future Test 没有打开。
- 运行后本地相关进程和 E2B sandbox 都是 0。全项目测试为 `719/719` 通过。
- 这次旧诊断 Dev 上 candidate 与 mid baseline 都是 `3.75e-7` MSE，相对改善为 `0`。
  它只证明“一轮里调 Train-CV，退出后 Dev 只看一次”的机制能真实工作，不是性能结论。
- 本次 controller 的 Tinker token 计价为 `$0.118992726`。整个新实验账本目前累计
  Tinker token 计价 `$1.697538222`；E2B 只记录预算占用，尚无 provider invoice，不能写成
  实际花费。

固定 H0 的两段 Archive 传递检查已经通过。它回答的是“上一轮的完整执行记录能不能真的被
下一轮读取和继承”，还没有回答“研究能力是否提高”。

- `A0`：`controller-harness-formal-canary-20260908-04`，从空 Archive 开始。GLM-5.3 用了
  11 个模型回合、17 次工具调用，写了 2 个 candidate，在 E2B 真实执行 2 次，最终选择
  `candidate_v2.py`。Controller 实测费用 `$0.168413580`。
- `A1`：`controller-archive-carryover-canary-20260908-01`，读取 A0 Archive 后处理另一个旧诊断
  任务。第一次写 candidate 时 Archive parent 格式不合规，harness 拒绝落盘；controller 随后
  自己修正，真实执行并选择 `mid_persistence_refine_v1.py`。共 7 个模型回合、8 次工具调用、
  1 次 E2B 执行。Controller 实测费用 `$0.322804116`。
- 机器检查确认 A1 的最终 candidate 直接继承 A0 选中的源码，`ancestry_depth=1`。两个
  snapshot 形成一条有效 hash chain；A0 和 A1 的 harness profile hash 与 29 个运行源码 hash
  完全相同。两轮均未打开 Future Test；结束后相关进程和 E2B sandbox 都为 0。
- A1 本地准备时发现 helper 的局部变量重名 bug。它发生在任何模型调用和目录创建之前，费用
  为 0。为了不改变 A0/A1 之间的 H0，A1 使用同一批已冻结底层准备函数生成；两段结束后才修
  helper 并补回归测试。当前全项目测试为 `717/717` 通过。

这两段使用的都是以前已经看过的诊断数据，所以 candidate 分数不能当成新的研究结果。它只
证明 Archive 不是一段写在文档里的设想：controller 能读到上轮记录，引用准确的父源码，改出
新版本，真实执行，并留下可核验的继承链。

## 较早的单 session 验收（2026-09-07）

Controller 已通过带完整 logging 的真实闭环 canary：

- 正式 ID：`controller-harness-formal-canary-20260907-07`。
- GLM-5.3 在一个 session 内走过全部 9 个受控动作：读固定说明、看 Train/Dev、读自己的
  Archive、查公开论文、列算法、看算法详情、写 candidate、请求 runner 执行、提交决定。
- 共 9 个模型回合、14 次工具调用，写了 4 个不可覆盖的 candidate 版本，真实执行 2 个。
  最终选择 `queue_imbalance_linear_v1.py`，它能追到同一份 source hash 的写入、执行和选择。
- 两次 candidate execution 都在独立 E2B sandbox 中拟合 6,000 条 Train，预测 300 条
  不带标签的 Dev。Dev 标签没有进入 sandbox；runner 在 sandbox 关闭后才评分。
- 三份 append-only hash-chain 日志全部通过；文献、算法和工具总账数量互相一致。
- Future Test 没有打开。精确进程已经退出，两份 cleanup receipt 都确认 kill；运行后的 E2B
  查询为 0 个活动 sandbox。
- 固定 Python runtime 和 24 个运行源码的 hash 都已记录。全项目测试为 `697/697` 通过。

这个旧任务上的被选 candidate 比简单 mid baseline 的相对 MSE 好约 `2.50%`，但 Dev 只有
1 场比赛。这不是研究结论、不是盈利证据，也没有测试多轮 Archive 是否真的让 controller
变强；它只证明当前 harness 能让 controller 自己研究、真实执行并留下完整记录。

这次 `-07` 的 Tinker 实测 token 费用是 `$0.142423758`。两次 E2B 各只有 `$0.10` 的
预算占用记录，没有 provider invoice，所以不能写成实际花费。当前整个新实验账本累计
Tinker 实测费用是 `$0.714810258`；E2B 的 `$1.30` 仍全部列为未对账的 reservation，
不与花费混在一起。

`-06` 已永久标为无效：它保存了决定，但提交后多请求了一个模型回合，在 12-turn cap 处
退出。修复后，成功提交直接由本地确定性 handshake 结束，不再增加付费回合；同一 candidate
也不能重复执行。`-03`、`-04`、`-06` 都保留原样，旧 ID 没有复用，也没有为了分数重抽。

旧 Round 1 和 v2 canary 继续保留原样，作为“短输出、弱 harness”的 baseline，不能把
新代码写回旧 artifact，也不能用同一个 run ID 续跑。

## 下一步边界

Controller harness 和 Archive 传递本身已经可以使用。下一步若开始正式研究，必须重新冻结正式任务、源码
和预算，并使用新的永久 session ID。正式研究只有一条持续的 Archive lineage；不能把这个
old-task canary 的 candidate、分数或 Dev 反馈继承进去。
