# NFL opened-Train target grid：第一轮结果

## 这轮在问什么

前面的实验一直把60秒当作默认target。新Harness不再先认定60秒，而是在同一163场opened
Train中同时构造clock-time和event-time target，再用同一套整场rolling split比较。每个target
只和自己的zero-change baseline比；raw MSE不能跨target直接比较。

这仍是Train discovery。Route-Dev和sealed Final都没有打开，也没有任何provider费用。

## 数据和运行

- 163场、25,957个原始play。
- target：10/15/20/30/45/60/90/120秒，以及未来第1/2/5/10笔成交。
- 119个play既没有任何target，也缺至少一个feature；它们仍在coverage分母中，但不进入设计矩阵。
- 实际设计矩阵共有25,838个play；rolling check是最后63场，分成连续3块，每块21场。
- 固定方法：Ridge和Random Forest。没有根据本轮结果改参数。
- 预先支持规则：三折skill全正、aggregate skill为正、超过一半比赛改善、日期块差值区间完全低于
  零、全量coverage至少50%。
- 成功run：`nfl-open-train-target-grid-screen-20260916-02`；result SHA256
  `238429415eab87e44882bc2b6e2de82064885889fcf5e50416334afb7b1f0003`。
- 第一次`…-01`在拟合前因runner错误停止，0费用并保留；没有覆盖或续跑旧ID。

## High-level结果

24个target×method组合中，16个满足全部事前条件。按“最弱一折skill→整体skill→coverage”的
冻结规则，每个target只留一个方法，前三名是：

| target | 方法 | 相对zero-change改善 | 最弱一折 | coverage | 改善比赛占比 | calibration slope |
|---|---:|---:|---:|---:|---:|---:|
| 30秒 | Random Forest | 6.01% | 4.78% | 80.27% | 76.19% | 0.978 |
| 20秒 | Random Forest | 5.36% | 4.68% | 71.61% | 73.02% | 0.939 |
| 45秒 | Random Forest | 5.73% | 4.48% | 87.44% | 77.78% | 0.967 |

排名按最弱一折优先，所以20秒的整体skill低于45秒但排在它前面。这个shortlist只用于下一步
opened-Train研究，不是正式promotion。

## 其他重要结果

- 15秒RF整体改善5.08%，三折全正，表现也稳定；它只是没进入最多3个的shortlist。
- 60秒RF整体改善4.06%，三折为3.13%/4.79%/4.43%。60秒不是失败，只是没有达到当前Train
  的峰值。
- 10秒Ridge整体改善2.68%，日期块区间也低于零，但coverage只有52.07%；它更依赖成交活跃度。
- 90秒Ridge改善2.85%并满足规则；120秒RF第二折为-0.17%，而120秒Ridge的日期块区间上端
  略高于零，因此较长horizon证据更弱。
- event-time有真实信号：未来第5笔成交的RF改善4.51%，三折2.21%/6.10%/5.88%，满足全部规则。
  第1笔成交也满足规则但skill只有2.51%；第2和第10笔的日期块区间跨零。
- RF在15–60秒通常强于Ridge，说明当前信号不完全是线性的；但差距不大，不能据此声称某个
  复杂模型已胜出。

## 我们学到了什么

第一，60秒不应继续被写成默认真理。当前opened-Train显示一个较宽的15–60秒有效区间，中心
大约在30–45秒。

第二，event-time值得保留。按成交笔数定义target不是噪声实验，第5笔成交有稳定skill；它可能
比固定秒数更好地适应活跃与不活跃市场。

第三，当前证据还不能说明30秒在独立数据上最好。不同target的eligible rows不同；即使每个target
都和自己的baseline比较，30秒仍可能因为样本组成更容易而占优。

## Same-support结果

后续敏感性实验只保留15/20/30/45/60秒，并要求五个target在同一个play上都有label。共16,632
个full-population play；rolling check的63场有7,368行。结果满足事前假设：30秒和45秒在Ridge、
RF两种方法下都排前二。

| target | RF改善 | RF最弱折 | Ridge改善 | Ridge最弱折 |
|---|---:|---:|---:|---:|
| 15秒 | 5.08% | 4.39% | 4.10% | 3.42% |
| 20秒 | 5.57% | 4.70% | 4.82% | 4.54% |
| 30秒 | 6.04% | 5.87% | 5.46% | 5.17% |
| 45秒 | 6.09% | 5.28% | 5.32% | 5.09% |
| 60秒 | 3.98% | 2.95% | 4.25% | 4.06% |

因此30–45秒的优势不只是eligible population差异；在同一批play上仍然存在。成功run为
`nfl-open-train-target-same-support-20260916-01`，result SHA256
`573a4bcfd86599556c43dad6abf43ffcba6ce226a4cc41297ed4e74483145b92`。费用`$0`，Dev/Final未开。

这不是独立复现：target neighborhood来自前一个opened-Train screen，两个实验使用同一份Train。
它只排除了一个具体confound，不能当作新的held-out证据。

## 下一步

让Controller只看opened-Train aggregate：target结果、coverage、稳定性、剩余能力目录和
费用，提出下一轮feature/algorithm方案。Controller不能看到Route-Dev label。等target、feature、
trainer和reward全部锁定后，再决定是否消耗一个新的untouched Route-Dev确认。

## 仍未证明

- 没有证明Route-Dev或Final泛化。
- 没有证明实时可用；历史provider timestamp不是live arrival receipt。
- 没有证明可成交、可盈利或扣成本后有效。
- 没有证明30或45秒是唯一最优horizon，也没有解决多次opened-Train探索带来的选择偏差。
