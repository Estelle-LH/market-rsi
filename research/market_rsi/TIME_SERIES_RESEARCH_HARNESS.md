# 时序研究 harness

## 先把问题定清楚

Controller 不能一上来就试模型。它先要回答：我们到底让模型预测什么？

昨天用的是“预测 60 秒后的一个市场中间价”。这个目标约 95%–97% 的样本没有变化，所以
直接猜“价格不变”已经很强。MSE 看起来很小，主要是目标尺度小和数据很平，不代表模型已经
很准。昨天三轮因此只算 pipeline 和 harness pilot，不能当作 RSI 性能实验。

正式研究分成两个阶段：

1. **目标研究**：只用公开论文和已经开放的 Train，比较几种合理的预测目标。
2. **模型自改进**：冻结一个目标之后，controller 才可以反复改特征、模型、loss、训练方法
   和超参数。当前 Dev 只能在每轮最后打开一次。

目标一旦冻结，不能因为 Dev 分数不好再改。若要换目标、预测时长、平滑窗口、基线或主指标，
必须开一个新 experiment，并使用新的、没看过的 Dev。

## 目标研究看什么

Harness 会给 controller 一个非穷尽的起点，但不是让它从固定菜单里机械选一个。它先自动
盘点数据源、raw 与 materialized cadence、目标的平坦程度、简单基线有多强、不同日期和比赛
是否一致、标签何时可用；看到具体问题后再查文献。它既可以比较下面这些起点，也可以提出
新的 target、所需数据流或 Train-only 诊断：

| 目标 | 做法 | 优点 | 主要风险 |
|---|---|---|---|
| 单点价格 | 取约 60 秒后的第一条报价 | 最直观，可作旧版对照 | 容易受单条报价噪声影响，也可能太平 |
| 未来窗口均价 | 对 45–75 秒内的报价做普通平均 | 假设少，能降低单点噪声 | 会把短暂但真实的跳变平均掉 |
| Forward EWMA | 对 45–75 秒内越晚的报价给越大权重 | 更接近窗口后半段的状态 | 改变实际预测时长；半衰期又多了一个可调参数 |
| 未来窗口中位数 | 取 45–75 秒内的中位数 | 不容易被孤立异常报价带偏 | 可能删掉真实但短的价格跳变 |
| 未来成交 VWAP | 对 45–75 秒内确认成交按数量加权 | 更接近真实成交价格 | 没成交就没标签；会受主动买卖方向、点差和少数大单影响 |
| 状态空间 / Kalman | 假设有一个看不见的“真实状态”并滤波 | 能显式处理观测噪声 | 假设更强，参数也要训练；不作为第一版默认方案 |

“Reverse EMA”在这里不作为模型输入，而是一个**未来标签的加权办法**：离窗口末端越近的
未来报价权重越高。它不是免费的降噪，因为它会把有效 horizon 往后推。报告时必须同时给出
实际加权后的有效 horizon。

每个候选目标至少检查：

- 每天、每场比赛有多少可用样本；
- 目标不变的比例、变化大小和尾部；
- 窗口前半段和后半段的标签是否稳定；
- “直接预测当前价格不变”能做到多少误差；
- 不同日期和比赛上的结果是否一致；
- raw error，以及相对固定基线的无量纲 skill score。

Trade price 不是无条件比 mid 好。若问题是“真正在哪里成交”，成交价和 VWAP 更直接；若问题
是“市场中心价格如何变化”，单笔成交会在 bid 和 ask 两边跳，也只在有人主动成交时出现。
所以我们会把未来成交 VWAP 作为正式候选，但必须同时报告无成交比例、成交量集中度、last
trade 的陈旧程度和 bid-ask bounce。不能把没有成交的窗口用旧成交价填满。

2026-09-08 的只读检查确认：当前 Linode 日归档有 `book_observations`、`book_changes`、
`event_observations`、`event_changes`、`discovery_changes` 和 `errors`，没有独立历史 trade 文件。
Polymarket 官方现在有 last-trade 和 trades 接口，但新接入的数据源必须先验证历史完整性、稳定
trade ID、成交时间与本地可用时间，不能把后来查询到的数据冒充当时已知的输入。

这一步不能自动挑“Train 分数最高”的目标。Controller 要写清楚研究问题、label 公式、数据
来源与可用时间、horizon、窗口、最低 coverage、基线、指标、失败条件，以及 materializer 和
测试。Runner 只检查没有泄漏、格式可执行、数据覆盖和预算，不替它选择科学内容；使用第一份
有效 controller decision，不能生成多份后由人挑最好。通过后再把选择写入不可改的 objective
contract。

## 数据怎样准备

模型可以每约 60 秒做一次预测，但标签必须从这 60 秒之后的**密集原始报价**计算。当前原始
Polymarket feed 对同一市场的典型间隔约 2 秒；旧 materializer 输出的决策行间隔约 61 秒。
因此旧文件可以做单点目标，却不能可靠计算 45–75 秒窗口的均值、EWMA 或中位数。

新的数据层要分开保存：

- `decision rows`：模型在当时真正能看到的输入；
- `dense label observations`：只用于未来标签，不能进入输入；
- `confirmed trades`：独立的成交流，至少要有价格、数量、方向、market、成交时间和稳定 ID；
- `label availability time`：至少到完整未来窗口结束之后，标签才算可用；
- 完整比赛分组和时间顺序：同一场不能跨 Train / Dev，也不能随机拆行。

数据密度不足、窗口覆盖不足或 availability 对不上时，runner 直接拒绝任务，不让 controller
用缺数据的目标继续跑。

## 一轮模型研究怎样走

目标和数据切分冻结后，controller 可以：查公开论文、看 Train、写分析代码、改特征、换模型、
换 loss 或训练方式，并在按时间切开的 Train-CV 上最多运行预定次数。它只能看到 Train-CV
反馈，不能看到当前 Dev 的答案。

Controller 提交本轮唯一 candidate 并退出后，runner 才打开 Dev 一次。Dev 得分写入下一轮
Archive；这个 Dev 随后变成下一轮 Train，不能再次作为 Dev。下一轮必须使用更晚的新 Dev。

每轮保存文献搜索、目标 hash、数据 hash、代码、特征、参数、Train-CV、Dev、失败、运行时间
和成本。Archive 本身就是下一轮的研究记忆，不再另设 Learn mode。

## 分数怎样看

短期预测主结果同时报告：

- 原始 equal-game MSE；
- `skill = 1 - candidate_MSE / persistence_MSE`；
- 每天和每场比赛的误差、覆盖率、预测变化幅度和失败数。

`skill > 0` 才表示比“价格不变”好。它只说明预测误差是否下降，不能直接写成能赚钱。盈利要
等预测环节稳定后，另外做含点差、手续费、滑点和成交概率的 execution experiment。

## 当前状态

- 目标目录、目标冻结规则和时序 research harness 已经写入代码。
- Harness 已经强制“先冻结 objective，再分配 Dev”。
- 合成数据上的完整 objective-discovery canary 已通过：8 个 turn、19 次工具调用，包含数据
  检查、文献搜索、3 个 proposal、3 个 audit、稳定性比较和一次有效冻结。
- 原始 feed 足够密；旧 materialized 文件太稀，所以第一次窗口目标 audit 被正确拒绝。新的
  materializer 已从 840 万条真实盘口生成 40,497 个决策点和密集未来标签。
- 自动数据体检已经能标出目标太平、persistence 太强、materialized cadence 太稀，以及缺少
  可验证 trade stream；这些 findings 交给 controller 决定下一步，不在代码里替它选答案。
- Train-only grid 现在同时提供 1、5、15 分钟的 point、均值、Forward EWMA 和中位数。真实
  数据里窗口均价标签的变化率分别是 2.05%、6.24% 和 14.60%，说明旧 60 秒目标确实过平。
- 真实 Train controller 已在 aggregate-only egress guard 下完成：8 个 turn、18 次工具调用、
  3 次文献搜索，实际成本 `$0.176343156`。它没有看到原始行、时间戳或市场身份，最终选择并
  冻结了约 5 分钟后的 60 秒 midpoint 均价窗口。成交 VWAP 因缺少可验证 trade stream 被拒绝。
- 选目标时没有创建或读取 Dev。目标冻结后，runner 才按日期生成三轮 Train/Dev，并把 91,369
  条历史目标行与同一个 formal contract hash 绑定。
- 正式 Round 1 已完成。6,000 条 Train 产生 3 个真实 Train-CV 候选执行；最终在 3,921 条、
  14 场比赛、一个新日期的 sealed Dev 上把 RMSE 从 15.58 bps 降到 15.40 bps，相对 MSE
  改善 2.36%。Future Test 没有打开。
- 这个分数只能归给底层 predictor。Controller 最后选择了一个预测完全相同、只增加无关
  metadata 的重复候选，未通过 controller-integrity gate。Round 2 在 harness 加入 prediction
  digest、no-op 去重和异常内容拦截前暂停。
- 完整离线测试 803 / 803 通过；付费进程退出，E2B inventory 为零。

## 研究依据

- DeepLOB 用过去和未来的 mid-price 窗口均值来降低高频标签噪声，并用阈值定义价格方向：
  [Zhang, Zohren & Roberts (2018)](https://arxiv.org/abs/1808.03668)
- Order-flow imbalance 研究强调用更平稳的 order-flow 输入预测多个未来 horizon：
  [Kolm, Turiel & Westray (2021)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141)
- 高频订单簿预测需要严格按时间做样本外检验：
  [Sirignano & Cont (2018)](https://arxiv.org/abs/1803.06917)
- 时间序列的交叉验证必须处理序列相关和非平稳：
  [Bergmeir, Hyndman & Koo (2018)](https://robjhyndman.com/publications/cv-time-series/)
- 预测概率应使用 proper scoring rule；基线归一化指标用于比较不同尺度：
  [Gneiting & Raftery (2007)](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf)，
  [Hyndman & Koehler (2006)](https://doi.org/10.1016/j.ijforecast.2006.03.001)
- Pre-averaging 和 robust M-estimation 能处理市场微观结构噪声，但会引入新的窗口与稳健性假设：
  [Shin & Kim (2017)](https://doi.org/10.1016/j.jeconom.2016.05.005)
- 高频成交价会受 bid-ask bounce 影响；该实证比较中，1 秒交易价格比 mid-quote 含有更多
  microstructure noise：
  [Liu et al. (2019)](https://academic.oup.com/ajae/article/101/2/563/5060863)
- Polymarket 官方公开了 last-trade 和市场 trade history 的字段与访问方式：
  [last trade price](https://docs.polymarket.com/api-reference/market-data/get-last-trade-price)，
  [public market trades](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets)
