# NFL Train-only 方法筛选

日期：2026-09-15
状态：人指导的 Train 内部诊断；不是正式 Controller 轮次，不是 Route-Dev 或 Final 成绩

## 这次问什么

在完全相同的 2025 NFL Train 数据上，只更换训练方法，检查简单模型能否比“预测价格不变”
更准确地预测一个 play 后 60 秒的主队合约价格变化。

这次固定了数据、target、feature、滚动切分、每场等权、seed 和评分。没有看 Route-Dev，
没有看 sealed Final，也没有根据结果调参数。

## 数据和切分

- 数据：163 场 `market_train` 比赛；
- 有 60 秒真实新成交标签的 play：23,709 行；
- 初始拟合：最早 100 场；
- 检查：之后 63 场，按时间分成 3 段，每段 21 场；
- 每段结束后，下一段拟合可以使用之前已经经过检查的比赛；
- 三段检查共 9,615 行、63 场、21 个 UTC 日期；
- 同一场比赛不会同时出现在一段的 fit 和 check 中；
- 主要指标：每场等权 MSE，避免 play 多或成交多的比赛支配结果。

输入 feature 是 play 前价格、比赛时间、period、比分差、持球队、down、距离、场地位置、
play 类型，以及这次 play 是否改变主客队比分等事件结果。这里预测的是历史 play 发生后市场
怎样反应，不是可执行的实时交易预测；历史 provider wall clock 不是本地 receive time。

## 干净结果

固定 zero-change 的每场等权 MSE 是 `0.0020001183`。

| 方法 | 每场等权 MSE | 相对 zero-change | 赢过基线的比赛 | 赢过基线的日期 | 日期块 95% 区间：候选减基线 |
|---|---:|---:|---:|---:|---:|
| Ridge | 0.0019265162 | +3.68% | 71.43% | 66.67% | [-0.00007162, -0.00001800] |
| Elastic Net | 0.0019259411 | +3.71% | 73.02% | 66.67% | [-0.00007255, -0.00001987] |
| Random Forest | **0.0019188312** | **+4.06%** | 66.67% | 66.67% | **[-0.00009261, -0.00001495]** |
| Histogram Gradient Boosting | 0.0019593162 | +2.04% | 52.38% | 38.10% | [-0.00004884, +0.00014092] |

Random Forest 在三个连续检查段相对 zero-change 分别提高 3.13%、4.79% 和 4.43%。Ridge 和
Elastic Net 也在三段都提高。Histogram Gradient Boosting 的平均分更好，但日期块区间跨过 0，
其中第二段还比基线差 0.50%，所以目前不能说它稳定更好。

## 模型实际学到了什么

原始单 feature 与 target 关系最明显的是：

- 主队本次 play 得分变化：Pearson IC `+0.1400`；
- 客队本次 play 得分变化：Pearson IC `-0.1443`；
- 当前持球队是否为主队：Pearson IC `+0.0440`；
- play 前价格与其余单个状态变量的线性关系都很弱。

Random Forest 三段最重要的 feature 一直包括主客队得分变化、剩余比赛时间、play 前价格、
到达端区的距离和原比分差。这个排序跨三段基本一致。线性模型也一直给主队得分变化正系数、
客队得分变化负系数。

这说明模型不是完全没学到东西：它学到了不同 play 和比赛状态对应不同的短期市场反应。
但提升只有约 4%，而且还没经过独立 Dev，因此不能把它写成已找到强 alpha。

## 发现的数据问题

`official` 在初始 100 场的 14,094 个拟合行中是常量，不能提供信息。研究脚本现在会显式
登记常量列，并且严格拒绝 `NaN`/`Infinity` JSON。其余数值 feature 标准化后的条件数约
`7.85`，没有显示严重的整体病态共线性；但 `period` 与剩余时间高度相关，比分差与 play 前
价格也高度相关，后续解释系数时仍须谨慎。

## 第一次运行为什么作废

第一次输出目录 `nfl-train-method-screen-20260915-01` 的模型分数本身完整，但原始信号诊断把
常量列相关系数写成了非标准 JSON `NaN`。这属于记录层失败，不能作为干净凭证。旧目录保留，
并写入 `post_run_audit.json` 标记为 `superseded_instrumentation_failure`。

修复只做了三件事：常量列相关系数写成 `null`、JSON 写入遇到非有限数直接失败、加正反测试。
没有修改数据、feature、target、切分、模型或参数。随后用新 ID `...-02` 从头重跑；两次的
`aggregate` 完全一致。

## 可以说和不能说

可以说：在 Train 内部的三个连续时间段上，简单模型相对 zero-change 有小幅、可重复的预测
改善；Random Forest 的平均改善最高，Ridge/Elastic Net 的赢比赛比例更高。

不能说：Random Forest 已正式胜出、模型能赚钱、结果能泛化到新赛季、事件 feed 在真实交易
中可提前获得，或 Controller 已经自我改进。这次没有 Controller，也没有打开 Dev/Final。

## 下一步

1. 保留这次筛选作为 Train-only 诊断，不用它直接晋级正式赢家。
2. 下一次只增加一种能力：优先补一个 game-clustered local projection，用固定 30/60/300 秒
   horizon 检查反应曲线；不同时更换 target、feature 和 trainer。
3. 删除常量列的规则要在下一版 pre-score lock 中预先固定，而不是根据 Dev 分数处理。
4. 完成专项测试和完整回归后，冻结并发布新的 Harness 版本，再让 Controller 开始多轮研究。
5. 正式阶段逐块打开 Route-Dev；设计完全冻结后才运行一次 40 场 Final。

## 可审计路径

- 干净 artifact：`artifacts/nfl-train-method-screen-20260915-02/`
- 结果 SHA256：`3eadb5ba708588f044fcd02995bcaa7fdd673e36e6c39810957251f7ec4899ec`
- manifest SHA256：`fc63676b817589cd5d21e0ee959a9cb8da7db3c35fcccf9c57831531debec0c9`
- runner：`sports_event_research/run_train_method_screen.py`
- 专项测试：`sports_event_research/test_run_train_method_screen.py`
- 验证：专项 7/7、sports harness 全部 34/34。
