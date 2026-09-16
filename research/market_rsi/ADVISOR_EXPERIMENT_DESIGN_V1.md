# LLM researcher 自我改进实验（第一版）

## 我们要回答的问题

同一个 LLM researcher 做完几次真实、可执行的市场预测实验后，能不能根据结果改进自己的研究方法，并在后面没见过的数据上做得更好？

第一版使用 Polymarket US 数据。Exchange 只是数据来源，不是研究变量。以后可以把同一套实验换到 Kalshi。

## 三组对照

三组使用同一个 GLM-5.3 researcher、同一个 Codex coder、同一批任务、同样的 token、时间和 sandbox 预算。

| 组 | 下一轮能看到什么 | 它回答的问题 |
| --- | --- | --- |
| Reset | 只看最初说明，不看以前的实验 | 没有学习时会怎样？ |
| Archive | 看自己以前的完整实验和结果 | 只保留经验有没有用？ |
| Learn | 看同样的实验和结果，还要写一份可以继续修改的 research guide | 总结经验以后，下一次会不会做得更好？ |

这个设计把两件事分开：Archive 对比 Reset 测“记住经验”；Learn 对比 Archive 测“从经验中总结规则”。

## 一轮怎样运行

1. Runner 给三组同一个 Train/Route-Dev 任务。
2. Researcher 每次只能提出一个明确改动，例如换特征、换目标变换或换模型；不能一次全改。
3. Codex 只把这项改动写成代码，不负责重新决定研究方向。
4. 代码只在 E2B 中运行。它只能看到本轮允许的 Train 和 Route-Dev。
5. 独立 scorer 使用完全相同的有效样本计算结果。
6. Archive 保存完整结果。Learn 还要根据结果修改自己的 research guide。
7. 下一轮换到时间更晚、没有重复比赛的新任务。

模型不会修改自己的权重。第一版的 self-improvement 是：研究经验和研究规则在多轮之间变得更好。这样先验证“LLM 会不会成为更好的 researcher”，不把 post-training 和研究能力混在一起。

## Controller 和各自职责

| 组件 | 使用什么 | 负责什么 | 不允许做什么 |
| --- | --- | --- | --- |
| Trusted runner | 固定代码，不是 LLM | 分任务、锁预算、保存记录、控制 deadline、决定何时打开数据 | 不替 researcher 选假设，不看结果后改规则 |
| Researcher | GLM-5.3，经 Tinker 调用 | 看允许的历史结果，提出下一项实验；Learn 组更新 research guide | 不能看 Test、grader、其他组记录或本地文件 |
| Coder | Codex，ChatGPT subscription | 把已经选定的实验写成受限 Python 代码 | 不能改变研究问题、访问网络或执行代码 |
| Executor | Harbor + E2B | 在隔离环境运行候选代码 | 不暴露密钥、隐藏标签或 scorer |
| Scorer | 固定代码 | 在同一批样本上打分并生成不可修改的结果 | 结果产生后不能改变公式 |

## 数据和预测任务

按完整比赛划分，不能把同一场比赛的不同盘口或不同时间放进两个集合。时间顺序固定为：

- Train：较早的完整比赛，researcher 可以训练和分析。
- Route-Dev：稍晚的比赛，每轮给出反馈。
- Audit-Dev：更晚的比赛，只在固定轮次检查是否只是在适应 Route-Dev。
- Test：最后至少 20 场完整比赛；整个研究结束后只打开一次。

第一版任务是预测一个盘口 60 秒后的 midpoint。现在固定使用预测时已经收到的七项：bid、ask、midpoint、spread、买一量、卖一量和两边挂单量差。第一轮不再临时加别的特征。

标签取预测时间 60 秒后第一条合格盘口，最大允许延迟提前固定。没有合格未来盘口就记为 missing，不填成零，也不在看完结果后删除。

## 怎么判断 researcher 变好了

主要指标是相对 persistence baseline 的 MSE 改善。Persistence baseline 就是假设 60 秒后的价格等于当前价格。

每场比赛先单独算分，再比较三组在同一批比赛上的差值：

`improvement = MSE_baseline - MSE_candidate`

正数表示候选比简单 baseline 好。我们同时记录：

- 相同样本上的 MSE 改善；
- 每场比赛是赢还是输；
- calibration；
- missing prediction 和运行失败率；
- 模型调用、sandbox、token、时间和美元成本。

最终主结果是 Test 上 Learn、Archive、Reset 的成对差值。交易 PnL 是第二指标，统一扣除 spread、手续费和固定延迟。预测分数提高但成本后 PnL 没提高时，不能说它更赚钱。

## 防止作弊和过拟合

- Test 的文件名、内容、标签和单题结果都不给 researcher 或 coder。
- Candidate 只能输出预测，不能接触 scorer 或修改 grader。
- 三组使用同一批有效样本；不能因为某个方法失败就少算难题。
- 每个 proposal 只允许改变一个因果阶段，方便知道提升从哪里来。
- 每次请求、代码、数据、结果和成本都写入 append-only 记录并保存 SHA-256。
- 一次任务只允许一个回答；格式错误、超时和零提升都算真实结果，不为了分数重抽。
- Route-Dev 可以每轮使用；Audit-Dev 只在预定轮次使用；Test 只使用一次。

## 第一轮规模

- 6 个 learning tasks；
- 3 个 transfer tasks；
- 每个 task 最多 2 个 proposal，再做一次固定选择；
- 三组总共最多 54 个候选执行；
- 先设 $50 pilot cap，只有数据、baseline 和执行链全部通过后才放开；
- 完整实验仍保留 $100–200 总预算上限。

如果 Test 少于 20 场完整、互不重叠的比赛，只报告 pilot 方向，不报告“LLM researcher 已经提高”的结论。

## 预先写下的判断

- 如果 Archive 优于 Reset：保留完整研究经验有用。
- 如果 Learn 进一步优于 Archive：LLM 总结 research guide 带来了额外改进，这是主要 self-improvement 结果。
- 如果三组接近：当前任务数量、反馈或模型能力不够，不能说 self-improvement 成功。
- 如果 Route-Dev 提高但 Audit-Dev/Test 不提高：发生了过拟合。
- 如果预测分数提高但失败率、成本或 PnL 变差：只能说局部指标提高，不能说整体 researcher 更好。

## 今晚可以向导师确认的三个问题

1. 是否同意把主要研究问题定为：LLM 能否从经过执行验证的实验结果中，逐轮成为更好的 researcher？
2. Reset / Archive / Learn 这三组是否足以把“记住经验”和“总结经验”分开？
3. 是否同意把预测准确度作为主要可控指标，把扣除成本后的 PnL 作为更严格的第二指标？
