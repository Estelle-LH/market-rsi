# Archive self-improvement experiment v1

## 我们现在要证明什么

同一个 GLM controller 做完实验后，把自己的完整记录放进 Archive。下一次它能读取这些记录，
自由决定查什么、改什么、跑什么。如果后面的研究结果更好，说明 Archive 中的执行经验帮助了
它。模型权重不变；这里的学习发生在跨轮研究记录中。

新实验没有单独的 Learn mode。Archive 本身就是 learning。固定 research guide 只说明工具、
预算和不能碰的 Test 边界，不告诉 controller 应该选哪种算法或按什么顺序工作。

## 数据开放原则是 harness 代码，不是 prompt 提醒

Controller 可以看到全部已经开放的学习内容：原始 Train、标签、以前评分过的 Dev、代码、
执行结果、失败、文献和算法记录。当前轮 Dev 在评分前只开放预测时可用的信息，不开放标签。

Controller 先锁定当轮全部 candidate，runner 才允许 Dev 评分一次。评分完成的同一个原子状态
转换会把这批 Dev 标成下一轮 Train；以后可以完整读取和学习，但永远不能再次充当 Dev。
下一轮必须使用新的封存 Dev。Transfer 只有在 `A0` 到 `A3` 的全部答案冻结后才能统一评分。

每轮内部改 candidate 时，只能看已经开放 Train 上的时间切分 CV。controller 提交并退出后，
runner 才把最终 candidate 在当前 Dev 上跑一次。Dev 分数到下一轮才通过 Archive 可见。

这套规则由 `prospective_data_lifecycle.py` 强制执行，并写入 hash-chain
`data-exposure-ledger.jsonl`。Controller prompt 只解释规则，没有修改数据状态的权限。

## Archive 传递检查（已通过）

2026-09-08 已完成两个固定 H0 的诊断 session：

1. `A0` 从空 Archive 开始，在诊断任务 1 上自由研究。
2. Runner 保存它的 prompt、工具调用、文献、算法版本、代码 hash、执行结果、失败、决定和费用。
3. Runner 生成只读 Archive snapshot `A1`，不替 controller 总结“下一步应该做什么”。
4. 第二个 session 在诊断任务 2 上读取 `A1`。它可以沿用、修改或放弃以前的方法。
5. 检查第二轮引用的历史记录、代码父版本和新执行结果能否完整追溯。

这一步只检查 Archive 真能传下去，不拿旧数据上的分数当正式结论。

实际结果是：A0 从空 Archive 选出 `candidate_v2.py`；A1 先读取 A0 的完整记录，再写出并执行
`mid_persistence_refine_v1.py`。机器校验确认 A1 的最终源码直接指向 A0 被选源码，两个
snapshot 的 hash chain 完整，Future Test 未打开，结束后 E2B 为 0。两段 controller 实测费用
合计 `$0.491217696`。因此第 1、2 项验收已经完成；下一步是冻结新的正式数据再跑 A0→A3。

## 正式实验

Archive 传递检查通过后，运行一条连续路线：

`A0（空） → 学习任务 1 → A1 → 学习任务 2 → A2 → 学习任务 3 → A3`

这条主实验从 A0 到 A3 始终使用同一个已经通过 canary 的 Codex H0 harness。Controller 可以
在 Archive 中记录它认为应该增加的工具或 harness 改动，但本实验不启用 H1，也不在中途改变
工具、prompt、context policy 或 runner。这样最后只测“完整执行经验能不能帮助 researcher”，
不会把 Archive 学习和 harness 修改混成一个变量。

AI 自己修改 harness 是后续单独实验：先完成主实验，再用相同 controller、任务和预算比较
冻结的 H0 与候选 H1。当前还没有证据说明哪一种 H1 会更好。

每个学习任务使用不同、按时间排列的完整比赛。Controller 能看到当轮 Train、没有标签的
Dev、自己的 Archive 和固定评分规则。它自己决定研究问题、文献、算法、特征、诊断和最多
三个 candidate。Runner 负责执行和打分，然后把完整结果放回 Archive。

为了判断是否真的提高，不让不同任务的难度混进结论，`A0`、`A1`、`A2`、`A3` 最后在同一
批封存 transfer tasks 上各做一次。所有答案先冻结，之后 evaluator 才统一打开标签和评分。
评分结果不会再放回 Archive。

## 看哪些结果

每轮马上返回给 controller：

- 与 persistence baseline 相比的同样本 MSE；
- 每场比赛分别赢还是输；
- calibration、覆盖率、失败和 timeout；
- 每个 candidate 的运行时间、token 和费用。

最终判断主要看 `A0` 到 `A3` 在同一批 transfer games 上的 equal-game MSE 是否持续改善。
同时报告覆盖率、失败率和费用。PnL 只做辅助结果；没有真实成交和足够比赛时不写“能赚钱”。

## Logging

每个 session 保存三本只能追加的账：工具总账、文献账、算法账。Archive snapshot 还要记录它
引用的每个 session、文件和最后一条 hash。Controller 不需要查文献或使用算法目录；但只要
做了，相应的 query、论文、假设、代码版本、执行、失败和选择都必须留下。

## 当前数据边界

现有旧 Round 1 有 6 个 learning task 和 3 个 transfer task，但每个 Dev task 只有一场比赛，
而且已经用于旧实验或 harness canary。它们只能用于 Archive 传递检查。

正式 transfer set 必须来自 `2026-09-07T16:08:41Z` 之后首次得到的数据，至少包含 20 场
互不重叠的完整比赛。数量不够时可以继续做工程检查，但不能报告正式 self-improvement 结果。

9 月 6 日的新封存数据有 12 场完整比赛；沿用事先已有的难度门槛后有 8 场。它足够作为一个
多比赛 learning block，但同一天不能拆成三轮：后一个任务的盘口会早于前一轮标签完全可用。
因此三轮 learning 使用分开的日期；9 月 7 日边界以后的数据不拿来调 controller，只进入统一
Transfer。当前还没有凑齐并封存 20 场 Transfer。现在先冻结 Transfer 的选择规则：边界以后
按时间选择最早满足门槛的 20 场完整比赛；等数据够了再按这条规则生成内容。这样可以先做
三轮 learning，但所有 A0–A3 答案冻结前仍然不能打开 Transfer。

## 正式数据和当前状态（2026-09-08）

三轮 learning 数据已经冻结：Round 1 是 6,000 条 Train、1,443 条 Dev；Round 2 累计
9,943 条 Train、1,500 条新 Dev；Round 3 累计 13,943 条 Train、2,400 条新 Dev。Dev 分别
覆盖 5、5、8 场比赛。每一轮的累计 Train 都由生命周期里的 component 逐条重建并校验 hash，
不能只靠文件路径替换数据。

正式 study `archive-formal-self-improvement-20260908-01` 已经完成不花钱的准备：A0、H0、
GLM-5.3、Archive、三轮数据边界、Transfer 规则、源码和预算都已冻结。Round 1 尚未调用模型。
启动时会把 6,000 条带标签 Train 和 1,443 条无标签 Dev 特征交给 Tinker 上的 GLM，并把
候选代码和允许的数据交给 E2B 执行。安全审核要求先明确同意这两个数据去向，因此当前停在
付费 dispatch 前；没有正式费用，也没有残留 sandbox。

## 验收顺序

1. ✅ Archive snapshot 能完整、只读、带 hash 地传到下一轮。
2. ✅ 两轮诊断 session 都能执行、结束和清理 sandbox。
3. ✅ 冻结正式 learning tasks、Transfer 选择规则、预算和源码。
4. 跑完 `A0 → A3`，不中途看 transfer 标签。
5. 所有 snapshot 的 transfer 答案提交后，只打开一次标签并出最终表。

## 第一次正式启动的记录（2026-09-08）

`archive-formal-self-improvement-20260908-01` 已经启动，但在提交 Round 1
选择前中止。GLM 实际完成了 10 次回答，并在 E2B 跑了两个候选：直接使用当前 mid 的
persistence 与基于 imbalance/spread 的 ridge 修正。后者在 Train-CV 反而差约 0.83%。

中止不是算法分数失败。GLM 最后选择了 persistence，但输出了短工具名
`submit_decision`；旧 adapter 只接受完整名字
`mcp__controller_tools__submit_decision`，所以选择没有进入 broker。Dev 没有打开，也没有
正式分数。该 ID 永久保留，不在原地重跑。

现在 harness 已允许两种写法，但只限白名单里的 controller 工具；其他名字仍会被拒绝。
全套 735 个测试通过。下一次从新的 source manifest 和正式 study ID 开始。

第二个新 ID `archive-formal-self-improvement-20260908-02` 证明短工具名已经可以正常进入
broker，但又发现下一层问题：controller 把文件名和 hash、execution ID 写在同一个字段里。
broker 拒绝后，旧 MCP 把本应可修改的格式问题当成整轮失败。这个 ID 也没有打开 Dev，不能
算结果。

现在格式错误会作为普通工具结果返回，让 controller 在剩余 turn 内改正。若字段开头能唯一
对应本 session 已执行的候选，harness 也可以只取文件名，并保留原字段的 hash 供审核；不能
唯一对应时仍然拒绝。云端或 runner 基础设施错误不会被这样吞掉。

第三个 ID `archive-formal-self-improvement-20260908-03` 跑出了第一个有效 Round 1：三个
候选都执行成功，最终选 `mid_persistence_v1.py`。封存 Dev 有 1,443 条、5 场比赛，覆盖率
100%，但相对 persistence 的提升是 0.0%。这是有效的零提升结果，已经写入 A1 Archive。

Round 2 读取 A1 和更多 Train 后，在执行新候选前用完旧 H0 的累计输入额度：6 个 turn 已用
213,136 tokens，下一次约 55K，会超过 262,144 上限。因此 Round 2 没有分数，不能说算法
失败。新 H0 保留每次最多 65,536 tokens，把全 session 输入提高到 786,432，同时明确每页
最多 100 条、不要重复翻同一页、跨轮继承用 `archive_parent`、最后只填候选文件名。每轮最坏
controller 成本上限从 `$2.07028224` 增加到 `$4.61832192`，仍受总预算硬限制。

第四个 ID `archive-formal-self-improvement-20260908-04` 的 controller 成功选出了
`level_tie_mid_v2.py`，但 Dev 在启动 sandbox 前被账本拒绝。原因是 Dev runner 给不同 study
都用了同一个付费 job ID `sealed-dev-execution`。账本拒绝复用是正确的；错误在 ID 生成规则。
这轮没有 Dev 分数，也不会修改 active claim 后重试。现在 Dev ID 同时包含永久 session ID，
不同 study 不会再撞号。

第五个 ID `archive-formal-self-improvement-20260908-05` 证明 Dev 唯一 ID 已修好，Round 1
再次得到 0.0% 提升。Round 2 又发现 64K 单次输入不够：Codex 每次都要带完整 Archive 和前面
工具记录，第 6 次请求会超过 65,536 tokens，所以还没执行候选就停止了。

新的限制是每次最多 196,608 input + 65,536 output，合起来不超过 GLM 的 262,144 context；
全轮累计 input 最多 1,572,864。每轮最坏 controller 上限是 `$8.44038144`。这不是无限放大，
仍有 turn、tool、candidate、wall time 和总美元五层限制。
