# NFL 状态变化表示：第一次完整 Train → 一次性 Route-Dev 循环

## 一句话结果

这一轮得到了一条值得继续验证的信号。我们先在 163 场已打开的 Train 比赛上发现：把一次
play 对比赛胜率的影响加入预测，可能比只看原始比赛状态更好。修掉一次明确的未来信息泄漏后，
我们只选择一个候选，并在完全没看过的 50 场 Route-Dev 比赛上只评分一次。结果是 equal-game
MSE 从 `0.0018824113` 降到 `0.0016587970`，相对改善 `11.88%`。

这个结果支持“同一事件带来的胜率变化有预测价值”。它还不能证明能赚钱、能实时领先市场，
也不能当作 sealed Final 成绩。

## 这一轮问的是什么

每次 NFL play 发生后，我们想预测 Polymarket 主队合约价格在未来 60 秒内的变化。

比较的两个模型完全相同，都是固定 `Ridge(alpha=1)`，使用同一批 Train、同一批 Route-Dev、
同一个 60 秒目标、同一个类别编码和标准化方式，也都是每场比赛等权。

- 固定 baseline：只看已有的原始比赛状态和市场状态。
- 唯一 candidate：在 baseline 上只增加 `state_wp_delta`。
- `state_wp_delta`：用历史 NFL play-by-play 拟合一个比赛状态胜率模型，然后计算当前这一次
  play 的结束状态胜率减开始状态胜率。它只读同一条 event 的开始和结束状态。
- 主要 reward：`candidate equal-game MSE - baseline equal-game MSE`，越小越好。

这里还有一个 zero-change 参照：永远预测未来 60 秒价格变化为 0。它只帮助理解绝对 MSE，
不是本轮 candidate 的正式对手。

## Harness 和实验怎样一起迭代

### Iteration 1：先找表示，不急着打开 Dev

在已经打开的 163 场 Train 上，我们把历史 NFL 状态模型接到市场预测上。最初实现的结果看起来
很好，MSE 大约改善 12.2%。Harness 没有直接接受这个分数，而是先检查每个 feature 在做决定时
是否真的已经存在。

### Iteration 2：发现未来信息，原结果作废

检查发现旧实现不是读取“当前 play 的结束状态”，而是读取“下一条也有 target 的 play”。
23,709 条可评分 Train 行中，有 23,546 条使用了后面的行：

- 向后看的时间中位数是 44 秒；
- 90 分位数是 183 秒；
- 28.61% 的行向后超过 60 秒；
- 56.25% 的后续行虽然还在 60 秒 label trade 之前，但仍然晚于决策时点。

所以旧的约 12.2% 改善不再用于 promotion。没有打开 Route-Dev，也没有拿这个结果挑分数。

### Harness v1.6.0 的变化

我们把表示改成只读同一个 PBP event 的 `start_situation` 和 `end_situation`。Harness 还增加了：

- open discovery 和 frozen confirmation 两个阶段；
- reward、candidate、baseline、evaluator 和完整 Dev cohort 必须在看 Dev 前冻结；
- 一次性 Dev gate：读取第一个 Dev label 前就消耗唯一评分权；即使崩溃也不能按分数重试；
- 50 个预注册 Route-Dev 文件必须全部成功，不能看到结果后删题或换题；
- sealed Final 继续拒绝访问。

发布版本为 `data-scientist-harness-v1.6.0`，commit
`bf06e17040a5a87eb6fd3cd7d54b0fb07508670c`，tag `dsh-v1.6.0`。真实 Codex canary 使用 18 次
工具调用、4 次合成 CPU 拟合、1 次公开搜索和 1 次公开阅读，结果通过；没有 Tinker 费用。

### Iteration 3：只在 Train 上重新比较

修复后，我们在固定的 163 场 Train 上使用 3 个按时间滚动的 check block。正式选择的
`state_wp_delta_only` 在三个 block 都优于 raw-state Ridge：

| Train 指标 | raw-state Ridge | 加 `state_wp_delta` |
|---|---:|---:|
| equal-game MSE | 0.0019265162 | 0.0016700963 |
| 相对 raw-state 改善 | — | 13.31% |
| Pearson IC | 0.2103 | 0.4070 |
| Rank IC | 0.1064 | 0.3309 |
| 相对 zero-change 改善的比赛比例 | 71.43% | 88.89% |

另外两个想法没有被带进 Dev：单独加入 `state_wp_pre` 或 `state_market_gap` 都比 raw-state Ridge
稍差。把三个 state feature 全加进去的 Train MSE 更低一点，但这是看过 Train 后的组合；为了
避免多选一，我们仍然只 promotion 事先解释最清楚的 `state_wp_delta_only`。

历史状态模型本身也做了独立时间检查：2021–2023 的 851 场用于拟合，2024 的 285 场用于检查；
equal-game Brier 为 `0.15716`，常数预测为 `0.24776`，相对下降 `36.57%`。这只说明状态模型不是
完全没有信息，不代表市场预测已经成立。

## 看 Dev 前冻结了什么

正式 confirmation contract 在任何 Route-Dev label 或分数被打开前固定：

- 完整 50 场 Route-Dev；零排除、零替换；
- 唯一 candidate：`same-event-state-wp-delta-v1`；
- baseline：`raw-state-ridge-alpha1-v1`；
- 主要指标：candidate MSE 减 baseline MSE；
- 固定 Train、target、60 秒 horizon、Ridge、编码、标准化和 equal-game weighting；
- 最多一次评分；
- 成本上限 `$0`；
- 不允许打开 sealed Final。

50 场比赛全部 materialize 成功，自动重试 0，排除 0。Materialization 只生成文件和 hash，
没有先汇总 label 或打分。50 个文件在评分后再次做了只读 hash 核对，全部一致。

## 一次性 Route-Dev 结果

Route-Dev 有 50 场、7,437 个可评分 play、16 个 UTC 日期。唯一评分在
`2026-09-16 03:06 UTC` 完成。

| Route-Dev 指标 | zero-change | raw-state Ridge | 加 `state_wp_delta` |
|---|---:|---:|---:|
| equal-game MSE | 0.0019558903 | 0.0018824113 | 0.0016587970 |
| 相对 zero-change 改善 | 0% | 3.76% | 15.19% |
| 相对 raw-state Ridge 改善 | — | — | **11.88%** |
| Pearson IC | — | 0.2067 | 0.3904 |
| Rank IC | — | 0.0951 | 0.3321 |
| calibration slope | — | 1.0005 | 0.9433 |
| 相对 zero-change 改善的比赛比例 | — | 76% | 84% |
| 相对 zero-change 改善的日期比例 | — | 87.5% | 100% |

最重要的数字是最后一列相对 raw-state Ridge 的 `11.88%`。`15.19%` 是 candidate 相对
zero-change 的总改善，里面包含 raw-state 模型本来已经有的 3.76%，不能把它写成新表示的净贡献。

Train 上的净改善是 `13.31%`，一次性 Route-Dev 上是 `11.88%`。方向和量级接近，没有出现
Train 很好、Dev 消失的情况。候选 calibration slope 为 `0.9433`，接近 1，但略低于 1，说明
预测幅度可能稍大。这个信息只能用于下一轮设计，不能回头调本轮模型。

## 完整性审计

- 一次性 Dev journal 只有四个顺序事件：freeze、materialize、claim、terminal。
- claim 在读 Dev label 前写入；剩余评分次数为 0。
- 50/50 panel hash 全部匹配冻结 manifest。
- evaluator SHA256：`1e5c4e843352fac1e42e73a9618adb6ac01395f72a5b086f2cab932cf5d98430`。
- confirmation SHA256：`f6b06a7d254990b7c5c58f245b8150809a57b724ece96c45accc73de675fd774`。
- materialized data commitment：`8d1a8eaf7904a60793522b696ddf908d2ed14352a4ec1fbf4dd3558325ace2f5`。
- result 文件 SHA256：`8308d186e56de6343c48db4f9a7b8cf040870b4162d01469aaa3b2aa571f3bae`。
- Route-Dev evaluation uses：1；allowance remaining：0。
- sealed Final opened：false。
- 本轮 provider cost：`$0`；没有 Tinker、E2B 或 Harbor 训练任务。

## 这轮支持什么，不支持什么

支持：

- “当前 play 改变了多少比赛胜率”比只看静态状态更能解释未来 60 秒的市场价格变化。
- 这个改善从 opened Train 转移到了按时间更晚、完全未看的 50 场 Route-Dev。
- 信息可用性检查是必要的；如果不先检查，第一次看起来不错的结果其实会带未来信息。
- Harness 可以把实验暴露的问题变成下一版的硬规则，并用新版本跑下一轮实验。

不支持：

- 不证明 sealed Final 上也会提高；Final 还没打开。
- 不证明能成交或赚钱；目前没有盘口深度、滑点、延迟和交易成本模拟。
- 不证明是因果 lead；这是历史数据上的预测关系。
- 不证明 Codex 或底层模型权重已经“学会”了研究。这一轮主要是人为指导的 Harness 改进，
  加上可复核的 discovery/confirmation 执行闭环。
- 不证明哪个单独比赛贡献最大。本次 evaluator 只保存了聚合结果，没有保存 candidate 相对
  raw-state 的逐场差值；为了保护一次性 Dev 纪律，我们不会事后重新打开 Dev 补算。

## 从这轮学到的 Harness 改进

下一版不应该因为分数不错就直接扩大模型。它应先补上这几个研究能力：

1. **预先保存贡献分布。** 下一次 evaluator 在看 Dev 前就要写明并保存逐场盲化 delta、日期块
   delta 和集中度；这样能判断是不是少数比赛撑起整体结果，而不需要事后重开 Dev。
2. **把信息可用性变成通用 gate。** 每个新 feature 必须声明 event time、available time 和
   label time；任何行读到决策时点之后的数据，整条 candidate 不能 promotion。
3. **把校准当成下一轮单独问题。** slope `0.9433` 提示幅度可能略大，但不能在当前 Dev 上调参。
   如果要研究校准，必须在新的 Train/Archive 上提出候选，并使用新的 untouched cohort。
4. **继续开放 discovery。** 当前候选是 representation improvement，不应把以后研究空间锁死为
   Ridge 或 state-WP。下一轮仍允许查文献、提出新 target、representation、trainer 或评价方法，
   但每个正式 A/B 只 promotion 一个清楚的变化。
5. **Final 继续封存。** 先把这条候选和下一版 evaluator 写成固定规则，再决定何时只开一次 Final。
   不能因为 Route-Dev 好就反复看 Final。

## 关键文件

- Train availability audit：`artifacts/nfl-state-surprise-availability-audit-20260915-01/result.json`
- 修复后的 Train discovery：`artifacts/nfl-state-surprise-discovery-20260915-03/result.json`
- discovery/confirmation 轨迹：`artifacts/nfl-state-surprise-route-dev-confirmation-20260915-01/`
- 冻结的 Route-Dev cohort：`artifacts/nfl-state-surprise-route-dev-selection-20260915-01/`
- materialization receipt：`artifacts/nfl-state-surprise-route-dev-materialized-20260915-01/manifest.json`
- 一次性 gate journal：`artifacts/nfl-state-surprise-route-dev-gate-20260915-01/runner-private/journal.jsonl`
- 正式 Route-Dev result：`artifacts/nfl-state-surprise-route-dev-evaluation-20260915-01/result.json`
- Harness release：`artifacts/releases/dsh-v1.6.0/release.json`
