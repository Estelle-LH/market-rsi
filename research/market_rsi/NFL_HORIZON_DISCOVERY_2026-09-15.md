# NFL Horizon Train-only Discovery

## 为什么跑这一步

上一轮预测把目标固定成“play后60秒的home价格变化”。这个选择来自当时实验设计，不是
Harness应该长期写死的规则。`dsh-v1.6.1`已经允许在opened Train/Archive上自由改变target和
horizon；这一步先比较当前panel已经有的30、60和300秒标签，检查60秒是不是明显更合理。

这不是正式选horizon。Route-Dev和Final没有打开，Train看过以后不能把赢家直接写成正式结论。

## 运行前固定了什么

- Harness release：`dsh-v1.6.1`，release SHA256
  `aa2c509c3c45261c008f1c5810851a2da959bd9781e7cc956ac3f8168439f8e4`。
- 实验代码：commit `085d71217180bbdabdc0ad13a53281e070e1b1f3`，tag
  `nfl-horizon-discovery-v0.1.0`；代码在运行前已推到用户自己的origin。
- 数据：同一163场opened market Train；三个horizon共同有标签的play才进入比较。
- 滚动设计：前100场fit，之后3个block各21场check；总check为63场、8,784行。
- Feature：同一组play状态、比分、剩余时间、pre-play市场价格与play结果字段。
- Trainer：固定Ridge和固定Random Forest；没有根据本次结果改超参数。
- Baseline：永远预测价格不变。主要看每场等权MSE相对baseline改善，而不是比较不同horizon的
  原始MSE大小。
- Route-Dev/Final：均未打开。Provider费用：`$0`。

## 结果

| Horizon | Check目标平均绝对变化 | Ridge相对改善 | RF相对改善 | Ridge赢的比赛 | RF赢的比赛 |
|---|---:|---:|---:|---:|---:|
| 30秒 | 2.11个百分点 | 5.06% | 5.88% | 76.19% | 76.19% |
| 60秒 | 2.84个百分点 | 3.89% | 4.00% | 73.02% | 66.67% |
| 300秒 | 5.73个百分点 | 1.48% | -1.19% | 65.08% | 50.79% |

分block结果：

- 30秒Ridge：`4.18%、4.60%、6.90%`；30秒RF：`4.49%、5.94%、7.72%`。
- 60秒Ridge：`3.20%、3.66%、5.11%`；60秒RF：`3.09%、5.02%、3.99%`。
- 300秒Ridge：`1.47%、1.10%、1.90%`；300秒RF：`-0.38%、-1.83%、-1.49%`。

30秒在3/3个时间block、2/2个trainer中都改善，也都比同一block和trainer的60秒相对改善更大。
30秒的日期块bootstrap loss-delta区间不跨0。Random Forest的最大单场只占绝对delta贡献5.49%，
前5场占22.58%；Ridge分别为4.12%和18.44%。所以当前30秒结果不是由一两场比赛撑起来。

60秒也不是失败：两个trainer都改善，日期块区间也不跨0。结论是60秒有信号，但没有证据说明
它应该被Harness固定成唯一target。

300秒明显更难：Ridge的日期块区间上界略高于0，Random Forest平均比zero-change差，且前5场
绝对贡献集中度达到42.48%。更长时间内出现了更多当前feature没有描述的新事件和市场变化。

## 这一步学到了什么

1. 以前固定60秒过早。当前Train证据更支持继续研究30秒附近，而不是继续默认60秒。
2. 不同horizon的原始MSE不能直接比较。300秒价格变化更大，所以MSE天然更大；必须看相对同一
   horizon zero-change baseline的skill、block稳定性和贡献集中度。
3. 当前结果支持“短期play后反应”比“五分钟后价格”更贴合现有feature，但不证明30秒是最终
   target，也不证明可交易。
4. 实验工具仍有真实限制：当前panel只预先生成了30、60、300秒。合同虽然允许自由探索，NFL
   adapter还不能让controller提交任意horizon或event-time target。这是下一项Harness改进。

## 下一步

下一版NFL target adapter应接受controller提交的target spec，而不是源码常量。至少支持：

- 一组有界fixed-time horizons；
- event-time或next-trade target；
- delta、方向和经过明确scale的target变换；
- 每个target的coverage、活动度、zero比例、availability和共同样本审计；
- Train-only比较及完整候选留档，不自动打开Dev。

新的researcher可以据文献和本轮轨迹决定是否探索10/15/30/45/60/90秒、event-time或别的target；
Harness不替它提前选。等researcher在opened Train上提出一个confirmation candidate以后，再在看新
Dev之前冻结完整`target_spec_sha256`、baseline、reward与evaluator。

## 证据路径

- 运行目录：`artifacts/nfl-open-train-horizon-screen-20260915-01/`
- 运行前锁：`pre_score_lock.json`
- 完整逐fold、逐比赛结果：`result.json`
- 输入hash：`input_receipts.json`
- 完成回执：`manifest.json`

