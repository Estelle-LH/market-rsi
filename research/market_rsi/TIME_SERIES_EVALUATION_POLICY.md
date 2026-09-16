# 时间序列预测：Train / Dev / Test 规则

## 先说结论

这是时间序列预测，不能把所有行打乱后随机分成 Train 和 Dev。我们要模拟真实使用：模型在
时间点 `t` 只能看到 `t` 之前已经出现的信息，然后预测 `t+60 秒` 的市场中间价。

Controller 可以研究和选择模型、特征、训练方法和超参数。数据的时间边界由 harness 固定，
不能让 controller 在看到分数后换一个更有利的 Dev。

## 一轮里怎样切

- 正式 Train 至少要覆盖 4 个 UTC 日期。
- 较早的日期用于 fit；最后 3 个日期作为一次固定的 Train-CV future block。
- 这三个日期不是三个独立训练轮次。Candidate 只用更早的数据 fit 一次，再连续预测后面的
  三天。这叫 single-origin blocked holdout。
- 不随机 shuffle。
- 同一场比赛只能在一边。若比赛跨过 fit/CV 边界，整场从这次 CV 中删掉。
- fit 中最后一个标签必须在第一条 CV feature 之前已经产生。跨过边界的标签要 purge。
- 边界在 candidate 运行前固定，不能根据 target、persistence error 或 candidate score 来选。

这样做比普通随机切分严格。随机切分会让未来市场状态进入过去的训练样本，得到的分数通常
过于乐观。Rolling forecasting origin / walk-forward evaluation 的核心也是每次只用过去预测
未来。参考：[Forecasting: Principles and Practice](https://otexts.com/fpp3/tscv.html)、
[scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)。

## 多轮怎样走

多轮实验形成真正的 walk-forward：

1. Round 1 用开放的历史 Train 做研究，只能反复看 Train-CV。
2. Controller 提交 candidate 并退出后，runner 才打开紧接着的 Dev，一次评分。
3. 这个 Dev 的结果进入下一轮 Archive；Dev 数据同时变成下一轮 Train。
4. Round 2 使用更长的历史，再预测下一个从未打开的 Dev。

因此，Dev 看完后确实会变成 Train，但它永远不能再次充当 Dev。下一轮必须向时间更晚处移动。
这属于 prequential / rolling-origin evaluation，不是固定测试集反复调参。

## Dev 怎样选

- Dev 是 Train 后面紧接着、从未打开的完整时间块。
- 正式的 prospective Dev 至少覆盖 3 个 UTC 日期和 8 场完整比赛。
- 按整场比赛分组，不能和 Train 共用 game ID。
- Dev 的起止时间只按预先冻结的时间、数据完整性和公开可用性决定。
- 不能看 target、baseline error 或 candidate score 后再决定放哪些行。
- 数据 materializer 必须在揭示 Dev target 前写出带 hash 的 selection receipt。
- 每轮只能打开一次。两个比较路线若共用一轮 Dev，必须在同一次 opening 对相同行评分。

Harness 会在运行前检查时间顺序、game 隔离、标签 purge 和 policy hash。新的
`prospective_time_series_materializer.py` 会按预先冻结的日期选择完整比赛，生成带 hash 的
selection receipt，并记录选集时使用的字段；target 和 candidate score 不在这些字段里。旧的
历史数据构建脚本仍不能作为这项证明。

## Final Test 怎样用

- Final Test 只在所有候选、checkpoint 和分析规则都冻结后打开一次。
- 当前 20 场比赛的 Transfer 只能算 pilot。
- 若要做正式推广结论，Final Test 至少覆盖 20 个完全没看过的 UTC 日期，并报告逐日结果和
  统计区间，不能只把大量分钟行当成大量独立样本。

反复尝试很多模型后只报告最好的回测，会造成 backtest overfitting，所以每次真实尝试都要
进入 Archive，不能删掉失败方案。参考：[The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)。

## Controller 能决定什么

Controller 可以决定：

- 使用哪些已开放的历史长度；
- 研究哪些滞后、变化率、流动性和跨市场特征；
- 使用 persistence、线性模型、树模型、状态模型或别的预测方法；
- 训练目标、正则化和超参数；
- 如何分析逐日和逐场的 Train-CV 结果。

Controller 不能决定：

- 把未来数据放进过去；
- 在看完 target 或分数后换 split；
- 拆开同一场比赛；
- 重复打开当前 Dev；
- 用已经看过的 Dev 冒充新 Dev；
- 在最终提交冻结前查看 Final Test。

## 当前代码边界

规则定义在 `time_series_split_policy.py`，prospective 选集写在
`prospective_time_series_materializer.py`，并作为完整 policy 和 hash 写进
`controller_harness_contract.py`。每个 candidate job 还会保存 `split-audit.json`，记录实际
fit/CV 日期、行数、比赛数、被 purge 的比赛数和时间 gap。Job 被改动后，runner 会重新计算并
拒绝执行。

现在实现的是“轮内一次固定 future block + 轮间不断向前移动”。如果以后要在一轮内部做多个
rolling origins，必须作为单独的实验改动：每个 origin 重新 fit、分别计分，再按预先规定的方式
汇总，不能悄悄改进现有结果。
