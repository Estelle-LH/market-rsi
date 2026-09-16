# NFL 30秒表示方法消融：研究记录与事前设计

## 观察到的问题

`nfl-open-train-target-same-support-20260916-01`在同一批16,632个play上显示，固定Random
Forest预测`elapsed_30s_delta`相对zero-change改善6.04%，三个rolling fold均为正。但现有输入主要是
原始比赛状态。aggregate-only GLM Controller因此提出：保持30秒target、163场Train、相同rolling
fold和Random Forest不变，只测试更明确的比赛状态表示。

要改的组件是feature representation，不是target、trainer、split或reward。Route-Dev和Final不打开。

## 检索记录

访问日期：2026-09-16。

查询：

- `site:arxiv.org/abs/1802.00998 nflWAR win probability random forest NFL plays`
- `site:degruyter.com/document/doi NFL random forests estimate win probability before each play`
- `site:nflverse.nflverse.com win probability model methodology expected points nflfastR`
- 在全文中继续检查win-probability variables、score/time、calibration和state-change定义。

### 已找到并阅读

1. Ronald Yurko, Samuel Ventura, Maksim Horowitz, *nflWAR: A Reproducible Method for
   Offensive Player Evaluation in Football*, arXiv:1802.00998v2.
   URL: https://arxiv.org/abs/1802.00998
   阅读部分：3.2的win-probability变量和GAM；3.2.2 calibration；3.3的state-value change。
   论文发现：win probability显式使用expected score differential、remaining game time和
   expected-score/time ratio；模型评价包括按quarter校准；play value定义为结束状态减开始状态。
2. Konstantinos Pelechrinis, *iWinRNFL: A Simple, Interpretable & Well-Calibrated
   In-Game Win Probability Model for NFL*, arXiv:1704.00197v3.
   URL: https://arxiv.org/abs/1704.00197
   阅读部分：摘要、Introduction和model/evaluation主张。
   论文发现：简单的十变量logistic模型用七季play-by-play可以得到校准良好的比赛内胜率；作者
   报告在相同变量下更复杂非线性模型没有显著改善。这支持保留简单、可解释的表示作为对照。
3. nflfastR EP/WP模型说明。
   URL: https://opensourcefootball.com/posts/2020-09-28-nflfastr-ep-wp-and-cp-models/
   Controller会话`nfl-target-controller-20260916-01`读取的部分记录了
   `diff_time_ratio = point_differential * exp(4 * elapsed_fraction)`及相关比赛状态变量。
   这是项目作者的实现说明；本轮将其公式作为固定候选，而不是当作市场预测已验证结论。

### 没有读到或不能声称的内容

- Lock and Nettleton (2014)的De Gruyter全文没有成功读取；只能确认元数据，不能说读过其方法。
- 上述论文预测NFL胜负概率，不是预测Polymarket未来30秒价格变化。它们只支持“值得测试这种
  表示”，不支持“这种表示会降低我们的MSE”。
- 历史Sportradar `wall_clock`不是当时本地receive time。同一event的`end_situation`在历史事件
  时钟下可核对，但不能据此宣称实盘延迟可行。

## 比较的方案

简单基线是完全复现现有parent：相同16,632行、相同3×21场check blocks、Random Forest 200棵树、
`max_depth=8`、`min_samples_leaf=50`、`max_features=0.7`、seed 23。

只改变表示：

- score-time：`score_diff * exp(k * elapsed_fraction)`；主候选固定`k=4`，`k=2`只做敏感性。
- possession-field：把field position换成home方向，再和possession sign相乘。
- same-event state delta：用2021--2024公开PBP拟合历史state→home-win probability，再计算同一
  play开始与结束状态的差；不读取下一条play。

主候选一次加入三类feature，但同时跑leave-one-family-out和add-one-family消融。这样可以看出组合
是否有效，以及效果来自哪一类。`k=4`是唯一主候选；不会从多个结果里事后挑最好的一条。

未采用的替代方案：

- HistGradientBoosting留到下一次trainer-only实验；本轮不能同时换feature和trainer。
- GAM需要新增能力和独立canary；本轮不安装。
- 60秒或其他horizon继续是开放选项，但不能和本轮30秒feature A/B混在一起。

## 事前支持规则

主候选`full_k4`只有同时满足以下三项，才记为opened-Train支持：

1. 三个fold中最弱的zero-change相对MSE改善严格高于parent的0.0587082927399335；
2. equal-game calibration slope在[0.9, 1.1]；
3. 63个rolling-check games中至少75%优于zero-change。

另外报告candidate相对parent的逐场和日期块差异，但不把这些事后改成新的通过条件。

## 状态

- found/read：完成。
- implemented：`experiments/nfl_representation_ablation.py`及专项测试已完成。精确源码commit为
  `1e1a6108bf5c60f66ff4e91b75a08a24654d0a6c`，tag为
  `nfl-representation-ablation-v0.1.0`；两者只推送到用户的origin。
- validated on our data：`nfl-open-train-representation-ablation-20260916-01`已完成。没有打开
  Route-Dev或Final，provider cost为`$0`。

## 实际结果

Parent被完整复现：16,632行，三个rolling block共7,368个check rows。Parent的equal-game MSE为
`0.0012582749`，相对zero-change改善`6.04%`，最弱fold改善`5.87%`，校准斜率`0.9192`。

事前唯一主候选`full_k4`的MSE降到`0.0008599460`：

- 相对zero-change改善`35.79%`；
- 相对parent MSE改善`31.66%`；
- 三个fold中最弱的改善为`34.11%`；
- 63场中`92.06%`优于zero-change，`98.41%`优于parent；
- 候选减parent的日期块区间为`[-0.00042235, -0.00021904]`；
- 校准斜率为`1.1310`。

所以主候选按事前规则记为**不支持**，唯一失败项是校准斜率略高于上限`1.1`。不能在看到结果后
放宽门槛，也不能把强MSE改善写成正式通过。

## 消融告诉我们的事

几乎全部改善来自`state_wp_delta`：它单独使用时MSE为`0.0008585668`，相对parent改善
`31.77%`，63场中`98.41%`优于parent；其校准斜率也偏高，为`1.1252`。

另外两类表示很弱：

- 只加possession×field-position，相对parent改善`0.24%`；
- 只加score×time，相对parent改善`0.08%`，日期块区间跨0；
- 去掉`state_wp_delta`后，相对parent只改善`0.02%`，日期块区间跨0；
- `k=2`与`k=4`结果很接近，没有证据说明time exponent是主要因素。

因此当前最准确的结论不是“三类feature成功”，而是：同一event的历史state变化在opened Train上
提供了很强、跨fold的预测信号；组合方案仍有轻微校准问题，而且历史event clock不证明实时可用。

## 凭证

- pre-score lock SHA256：`6418d59b57c052bed1420e443b931adc1454fe12d4ab21dde77481cc50e1a7ec`
- result SHA256：`0ae7c8136ddbb83466ff74a1bbe4f660fb0a48ae93029264f0af961f007caaa6`
- diagnostics SHA256：`38a913ae219f4936be90f703fd9b464aa76089f111afdb7ecbd11f8413a09392`
- manifest SHA256：`d00305225af1651db533fcd9a615f38f54f2cdd72d03a29b4e96571ec4fd3041`
