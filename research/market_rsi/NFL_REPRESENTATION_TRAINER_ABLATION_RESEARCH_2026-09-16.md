# NFL 30秒表示固定后的Trainer A/B：研究记录与事前设计

## 观察到的问题

`nfl-open-train-representation-ablation-20260916-01`的主候选把equal-game MSE从
`0.0012582749`降到`0.0008599460`，但校准斜率为`1.1310`，超过事前上限`1.1`。消融显示改善
几乎全部来自`state_wp_delta`，不是score×time或possession×field-position。

要改变的组件只有prediction trainer。30秒target、16,632行、三个rolling blocks、完整`full_k4`
feature、预处理、每场等权、seed和评分不变。Route-Dev和Final保持关闭。

## 已有研究与项目证据

访问/复核日期：2026-09-16。

1. scikit-learn 1.6.1 `HistGradientBoostingRegressor`官方API：
   https://scikit-learn.org/1.6/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
   已复核部分：squared-error loss、learning rate、leaf count、minimum leaf size、L2、early stopping。
   用法：复用项目已经测试并冻结的参数，不根据本轮结果搜索超参数。
2. `NFL_TRAIN_METHOD_SCREEN_2026-09-15.md`的同项目证据：在相同163场、60秒raw-state任务上，
   固定HistGradientBoosting只改善zero-change `2.04%`，弱于Random Forest的`4.06%`，而且日期块
   区间跨0。这是反例，不支持预设HGB一定更好。
3. 既有memory-policy实验显示HistGradientBoosting有时能修正线性模型的非线性和校准，有时也会
   在新时间段失效。它只能支持“值得做一次严格same-data A/B”，不能支持当前NFL任务会成功。

没有新安装library。当前16,632行完整，所以HistGradientBoosting的native-NaN能力不是本实验理由；
本轮不把没有发生的缺失值优势写成贡献。

## 比较方案

Parent是上一轮精确的`full_k4` Random Forest：200 trees、depth 8、min leaf 50、max features 0.7。

Candidate只把trainer换成固定HistGradientBoosting：

- `max_iter=150`
- `learning_rate=0.05`
- `max_leaf_nodes=31`
- `min_samples_leaf=50`
- `l2_regularization=1.0`
- `early_stopping=False`
- seed 23

未采用的替代方案：

- 不直接做post-hoc calibration；那会改变calibration stage，留作HGB失败后的独立实验。
- 不删掉两个弱feature；那会同时改变feature set。
- 不搜索树深、学习率或迭代次数；本轮只允许一个固定candidate。
- 不改成60秒或其他horizon；horizon仍可自由探索，但必须另起target实验。

## 事前支持规则

Candidate只有同时满足以下四项，才记为opened-Train支持：

1. 三个rolling fold中，candidate MSE都严格低于精确Random Forest parent；
2. 63场汇总的candidate减parent日期块95%区间上界严格小于0；
3. equal-game calibration slope在`[0.9, 1.1]`；
4. 至少75%的比赛优于zero-change。

任何一项失败都记为trainer不支持。不会从多个HGB参数中事后选winner。

## 状态

- found/read：完成，复用上面列出的官方说明和项目内反例。
- implemented：完成。精确源码commit为`777d2b5648d9588c36fcf1883553471c40301d56`，tag为
  `nfl-representation-trainer-ablation-v0.1.0`；只推送到用户origin。运行前通过257项Harness、
  59项sports和16项experiment测试。
- validated on our data：`nfl-open-train-representation-trainer-ablation-20260916-01`已完成。
  Route-Dev/Final没有打开，provider cost为`$0`。

## 实际结果

固定HistGradientBoosting把equal-game MSE从Random Forest的`0.0008599460`降到
`0.0007870446`，相对parent改善`8.48%`。它相对zero-change改善`41.23%`。

四项事前规则：

1. **通过：** 三个fold都优于parent；各fold MSE为`0.0009349020`、`0.0008368396`、
   `0.0005893921`，相对对应parent分别改善`5.63%`、`8.69%`、`12.39%`。
2. **不通过：** candidate减parent的日期块区间为
   `[-0.00011820, +0.00000702]`，上界略高于0。
3. **通过：** 校准斜率从parent的`1.1310`修到`1.0316`。
4. **通过：** `92.06%`比赛优于zero-change；`77.78%`比赛优于Random Forest parent。

所以固定HGB按事前规则记为**不支持**，唯一失败项是日期块区间仍跨0。不能因为上界只高出一点
就事后改变规则。

## 进一步诊断

HGB在21个check日期中的19个日期平均优于parent，但单个最佳日期贡献了所有日期绝对变化量的
约`37.3%`。两个日期变差。三个fold都改善，说明效果并非只存在于一个连续时间段；但是日期数量
只有21，且不同日期包含的比赛数差异很大，所以当前证据仍不足以排除日期集中。

这改变了下一步：不应立刻调HGB参数追分。应该先把这两轮的aggregate evidence交回Controller，
由它在不看Dev/Final的前提下选择一个下一changed stage，例如加强时间稳健性证据、改变target/
horizon、提出新trainer/算法，或增加数据覆盖。下一轮仍须在看分前写清唯一主候选和reward。

## 凭证

- pre-score lock SHA256：`7385e9f13358472632fbe2dd6a778ebca493035ff5e4d8ef23c0fbe24f765c35`
- result SHA256：`3089826002ee21b89efa76f3526c605b6a6a97f7339ebe1e2443fe88ce26f7ac`
- diagnostics SHA256：`033ac837bad8a43f083a60463cbaabc4e41d6a1dbafe7610e1f9a0dba10da20c`
- manifest SHA256：`fb0933fc9d0410833f350d4da696c88d32371fb2049ee45b1b7a176d5fe21ef0`
