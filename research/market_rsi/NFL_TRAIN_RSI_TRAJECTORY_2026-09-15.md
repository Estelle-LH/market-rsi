# NFL Train-only RSI MSE trajectory — 2026-09-15

## 一句话结果

RSI 的小闭环已经跑通。它在同一套 2025 Train 滚动检查上完成 7 轮，最好 MSE 从
zero-change 的 `0.0020001183` 降到 `0.0019082992`，下降 `4.59%`。第 6、7 轮变差，系统没有
继续继承，而是保留了第 5 轮。

这只能证明闭环能工作，并提供下一步假设。因为 controller 反复看的是已经打开的 Train
检查结果，这不是独立的泛化成绩，也没有打开 Route-Dev 或 Final。

## 固定了什么

- 数据：163 场 2025 NFL Polymarket Train；没有增加、删除或更换比赛。
- target：一次 play 后 60 秒的 home-price change。
- feature、时间顺序、三段 rolling check、每场等权 MSE、seed 23：全部不变。
- 变化范围：前三轮只换 trainer；后四轮只改 Random Forest 的一个参数。
- 成本：本地 CPU，付费 provider 调用 `0`。
- 隔离：Route-Dev 未打开，Final 未打开。

## 每轮做了什么

| 轮 | 改动 | MSE | 相对 zero-change | 结果 |
|---:|---|---:|---:|---|
| 0 | zero-change：永远预测 0 | 0.0020001183 | — | 起点 |
| 1 | Ridge | 0.0019265162 | 好 3.68% | 保留 |
| 2 | Elastic Net | 0.0019259411 | 好 3.71% | 保留；只比 Ridge 好一点点 |
| 3 | Random Forest，depth 8 / leaf 50 | 0.0019188312 | 好 4.06% | 保留 |
| 4 | 只把 depth 8 改成 12 | 0.0019187962 | 好 4.07% | 保留；改善几乎为 0 |
| 5 | 只把 leaf 50 改成 25 | **0.0019082992** | **好 4.59%** | **最终保留** |
| 6 | 只把每次 split 可看的 feature 从 70% 改成 100% | 0.0019201073 | 好 4.00% | 变差，淘汰 |
| 7 | 只把树从 200 棵改成 400 棵 | 0.0019093076 | 好 4.54% | 比 champion 略差，淘汰 |

第 5 轮相对第 4 轮又降低约 `0.55%` MSE。第 4 轮的改善只有约 `0.0018%`，不能当作有意义
的进展。第 6 轮相对 champion 变差约 `0.62%`；第 7 轮变差约 `0.053%`。

## 它实际学到了什么

这里的“学习”是实验策略更新，不是模型权重跨轮继承：

1. 线性模型能抓到一点信号，但非线性 Random Forest 更好。
2. 单纯增加树深几乎没用。
3. 减小 leaf，让模型保留更少见的 play state，有小幅帮助。
4. 每次 split 看全部 feature 反而更差；70% feature subsampling 暂时应该保留。
5. 增加树的数量没有产生新信号，所以不值得继续花计算量。

controller 在每轮后读取 MSE，选择当时最好的 Random Forest 作为下一轮父节点。候选变差时，
它记录失败并继续保留旧 champion。它不是 GLM/LLM controller，而是一个预先锁定分支规则的
本地 canary；目的是先证明轨迹、记账和淘汰机制正确。

## Champion 的辅助结果

- 63 场 rolling check 的 68.25% 比赛优于 zero-change。
- 21 个 UTC 日期中 61.90% 优于 zero-change。
- equal-game Pearson IC：`0.2324`；rank IC：`0.1451`。
- calibration slope：`0.8214`，说明预测幅度仍偏大，后面可以单独研究校准。
- 日期块 bootstrap 的 candidate-minus-zero MSE 区间：
  `[-0.00008472, -0.00000583]`。
- 三个连续检查段 MSE：`0.00215366`、`0.00196164`、`0.00160960`。

这些仍然是 Train 内部结果。它们帮助判断下一步，但不能代替一次 untouched Route-Dev 测试。

## 这次证明了什么、没有证明什么

已经证明：

- 同一输入、同一 target、同一评分下，闭环能逐轮提出、执行、记分、保留或淘汰候选。
- 每轮 intent 在训练前写入；result 和 reflection 在结果出来后写入。
- 第 5 轮给出了一个明确、可复查的 Train-only champion。
- 第 6、7 轮的负结果被保留，没有被隐藏或改写。

没有证明：

- 没有证明第 5 轮对新比赛更好。
- 没有证明 LLM controller 已经学会做研究；本次 controller 是固定规则。
- 没有证明能赚钱，也没有计算交易成本或 PnL。
- 最好分数曲线按规则保留最低值，本来就会单调；真正重要的是下一次独立测试。

## 下一步

先不要继续在同一批 Train check 上无限调参。合理的下一步是把第 5 轮 champion 和冻结的
Random Forest base 作为一对预先声明的候选，只打开一次 untouched Route-Dev，检查 `leaf 50 → 25`
是否还能降低 MSE。如果没有转移，这一轮只算 Train overfitting；如果转移，再考虑把同样的可审计
接口交给真正的 LLM controller。

## 可复查文件

- 完整 artifact：`artifacts/nfl-train-rsi-trajectory-20260915-01/`
- 总轨迹：`trajectory.json`
- 每轮训练前假设：`round-01-intent.json` 至 `round-07-intent.json`
- 每轮机器结果：`round-01-result.json` 至 `round-07-result.json`
- 每轮结论：`round-01-reflection.json` 至 `round-07-reflection.json`
- 全部逐行预测：`predictions.csv`
- 最终 manifest：`manifest.json`

关键 SHA256：

- `pre_score_lock.json`: `e64340db947e6c8e1e426f60deb70603ab2a06c6c9a6a4c4f40c3d598d12421b`
- `trajectory.json`: `bb558d1dbb9f78fc33eafcde5f6991c8e2ac0f03a0d2c4270b816b7296e4bb5f`
- `predictions.csv`: `eedb60402dd03c0d96c7517f00a6ba4a8a817ff4581d5e05acb2f33f020e01fa`
- 最后一条 reflection / hash-chain head:
  `d2f23868704b0d3ea84ba13d9df25b1a1c0613f9f1391d8ad874ef725cd94e6e`
