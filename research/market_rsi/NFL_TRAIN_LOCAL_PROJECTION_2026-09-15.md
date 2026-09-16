# NFL Train-only horizon response

日期：2026-09-15
状态：Train-only 描述性研究；没有打开 Route-Dev 或 Final

## 问题

一次 NFL play 已经发生后，主客队得分变化与主队 Polymarket moneyline 价格在 30、60、300 秒
后的变化有什么关系？三个 horizon 使用完全相同的 play，避免把样本变化误当成时间反应。

这里采用 local projection 的核心做法：每个 horizon 单独做一次回归。Jordà (2005) 的原始方法
允许用直接回归估计各 horizon 的反应，不必先固定一个完整动态系统。但本项目里的得分不是
随机冲击，比赛状态也会内生变化；因此这里只报告调整后的描述性关系，不作因果解释。

## 固定设计

- 数据：163 场 `market_train`；
- 共同样本：30/60/300 秒都存在真实新成交标签的 20,836 个 play；
- exposure：本 play 的主队得分变化、客队得分变化，保持原始“每 1 分”单位；
- controls：play 前价格、剩余时间、原比分差、持球队、down、first-down 距离、端区距离、
  no-play 标志；controls 在全 Train 共同样本上标准化；
- 权重：每场比赛总权重相同；
- 区间：WLS CR1 covariance，按 163 场比赛聚类，使用 162 自由度的 t 参考分布；
- 三个 horizon 的 design matrix 完全相同，condition number `3.44`；
- 没有 Controller、没有付费调用、没有调参或模型晋级。

## 结果

单位是主队合约价格变化；`0.01` 等于 1 个概率百分点。

| Horizon | 主队每得1分 | 95%区间 | 客队每得1分 | 95%区间 |
|---|---:|---:|---:|---:|
| 30秒 | +0.00629 | [+0.00501, +0.00757] | -0.00662 | [-0.00763, -0.00560] |
| 60秒 | +0.00772 | [+0.00635, +0.00908] | -0.00802 | [-0.00922, -0.00681] |
| 300秒 | +0.00793 | [+0.00629, +0.00957] | -0.00803 | [-0.00955, -0.00651] |

按线性单位直观换算，一个 6 分主队得分事件对应的调整后价格变化约为：30秒 +3.77 个百分点，
60秒 +4.63 个百分点，300秒 +4.76 个百分点。这个乘法只帮助读数，不代表所有 touchdown
在不同状态下都有相同影响。

## 学到了什么

1. 市场反应并非在 30 秒内完全结束：主客队得分系数从 30 秒到 60 秒明显扩大。
2. 60 秒到 300 秒的点估计几乎不再增加，说明这批历史成交里的主要得分反应大致在一分钟内
   达到平台。
3. 主客队方向对称且跨 horizon 稳定，支持 play、outcome 方向和价格方向的映射没有明显反转。
4. 这解释了上一项方法筛选为何能学习到小幅信号：主客队得分变化是最稳定的 feature，剩余
   时间、原价格和场地位置帮助模型区分同样得分在不同比赛状态下的影响。

## 仍然不能说什么

- 不能说得分“因果导致”了表中的全部变化；得分事件不是随机分配的。
- 不能说我们能在别人之前看到 play；历史 provider wall clock 不等于本地 receive time。
- 不能说这些是可成交 bid/ask、fill 或 PnL；输入是公开历史 trade prints。
- 不能用这些 Train 区间代替 Route-Dev 或 Final。
- 不能因为区间好看就把 local projection 作为正式赢家；它改变的是 evaluation，不是预测模型。

## 文献记录

检索日期：2026-09-15。

| 查询与来源 | 实际采用 | 本项目限制 |
|---|---|---|
| `Jorda 2005 Estimation and Inference of Impulse Responses by Local Projections`; [AEA 原文记录](https://doi.org/10.1257/0002828053828518) | 每个 horizon 直接估计一个回归，不从单一动态系统外推 | NFL play 不是宏观随机冲击；只转移 horizon-by-horizon 设计 |
| `state dependent local projections endogenous state`; [Journal of Econometrics 2024](https://doi.org/10.1016/j.jeconom.2024.105702) | 明确限制内生 state 下的解释 | 本项目不把 score/state 系数称为条件因果效应 |

## 可审计路径

- artifact：`artifacts/nfl-train-local-projection-20260915-01/`
- result SHA256：`7bd5899077f12b1fbd8f511ef73690bca9ccfbbf350a7a3ce1a7a247ab1177a5`
- manifest SHA256：`dd424e18b05e8d8c4df0caac2d20eff0b2aa15332633c698f22073648bb1be5a`
- runner：`sports_event_research/run_train_local_projection.py`
- tests：`sports_event_research/test_run_train_local_projection.py`
- 验证：local projection 5/5；sports harness 39/39；全部4个JSON严格解析通过。
