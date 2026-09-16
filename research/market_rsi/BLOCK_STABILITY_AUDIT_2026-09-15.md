# 已打开 Final 的反馈块稳定性审计

日期：2026-09-15。运行：`block-stability-audit-v4-opened-20260915-01`。

## 问题和边界

问题：v4 每轮只看一个新小时，这个反馈单位是否太不稳定，因而掩盖了 Archive 与 Fresh
之间的真实差异？

本次改变的不是模型、目标或数据，而是 **post-hoc 诊断的聚合单位**。只读取已经打开的
v4 Final 分数和对应 header；没有重新训练、没有 provider 调用、没有打开新的 Dev/Final，
也不把结果当作新的 promotion evidence。

## 研究依据复用

本次没有提出新的估计方法，因此没有新增联网搜索。复用并重新核对：

- `TIME_SERIES_EVALUATION_POLICY.md` 已记录的 rolling-origin、按时间块评估和“已打开数据只能
  做诊断”的规则；
- `LITERATURE_TO_HARNESS_2026-09-10.md` 对 FPP3 time-series cross-validation 的阅读记录；
- `indicator-prediction-evals` 的按日期阻断、paired rows、至少20个OOS session和不把相关行
  当独立证据的门槛。

这些来源支持按时间块而不是按行做判断，但没有证明4小时或5小时一定是本项目的最佳单位。
因此本次只做数据上的稳定性诊断，不直接冻结下一版为4小时。

## 比较过的办法

1. 单小时：保留原来的20个 Final session。
2. 连续4小时：每个日期固定取最早4个连续小时；规则在读取分数前由脚本写死，第5小时不用，
   不按结果选择窗口。
3. 同日期5小时：使用v4每个Final日期已有的全部5个连续小时。
4. 24小时整日：当前数据不支持。每个日期只有5个已选小时，不能把它们冒充完整一天。

## 结果

| 聚合单位 | 块数 | Archive赢Fresh | Archive相对Fresh平均 | 块间标准差 |
|---|---:|---:|---:|---:|
| 1小时 | 20 | 12/20 | +0.38% | 1.06% |
| 固定连续4小时 | 4 | 2/4 | +0.21% | 0.43% |
| 同日期5小时 | 4 | 2/4 | +0.23% | 0.42% |

同日期5小时明细：

| 日期 | Fresh vs Baseline | Archive vs Baseline | Archive vs Fresh | Compact vs Baseline |
|---|---:|---:|---:|---:|
| 2026-09-11 | +4.24% | +4.11% | -0.13% | -3.47% |
| 2026-09-12 | +9.23% | +9.87% | +0.71% | -13.39% |
| 2026-09-13 | +8.15% | +8.56% | +0.45% | -6.84% |
| 2026-09-14 | +4.48% | +4.37% | -0.12% | -11.83% |

## 解释

- Fresh和Archive在4/4个日期块都超过固定Baseline，说明“研究后训练的模型优于固定单特征
  模型”比单小时更稳定。
- Archive只在2/4个日期块超过Fresh；平均优势约0.23%，小于日期块之间约0.42%的波动。
  因此现有结果不支持稳定的memory提升。
- Compact在4/4个日期块都低于Baseline；失败不是单个小时造成的。
- Final四天的零标签率分别约59.4%、40.8%、18.4%和89.9%，说明不同日期的市场状态差异
  很大；同一天更多相关行不能替代更多日期。
- 4小时和5小时的Archive/Fresh波动低于单小时，但当前只有4个日期块，仍不足以估计稳定
  的效应或选择“最佳”block长度。

## 下一步门槛

下一版不能继续用一个小时作为唯一反馈。设计阶段应先从未用于新Final的开放数据中冻结：

1. 每个反馈block覆盖多个连续小时，并优先跨多个日期；
2. Fresh和Archive使用相同block、行、候选次数和预算；
3. Archive每轮必须记录引用的旧证据及其对新决定的影响；
4. 预先固定32–40轮，无performance early stop；
5. 新Final至少20个未见session，按日期做paired block比较并只打开一次。

具体采用4小时、完整日期还是跨日期block，必须在新数据可用性审计后冻结；本次5小时日期块
不是24小时全日证据。

## 文件与hash

- `block_stability_audit.py`: `c17e28bb2a6922f85aa9176ec8fd3866c0c1295c7dddd935423ae3d15e01bf01`
- `test_block_stability_audit.py`: `5f7ae0f43cb90482b65a29f774c77c078651a07e627b49e0a5182ec8bea2c79c`
- `audit.json`: `f7378b7c1c98cc3c3026e964f4446fcee35139877b90d825cb72ce80ca3ea5c2`
- `report.md`: `324931617cd8d71adccd2ab285b1aeac5ec540b551d67c87416545448be75f0b`
- `complete.json`: `6395ba9a1163ebd9f4d86f7653fa4406cadcf0f8fbf0c829257ed9e9ba1c8921`

单元测试：1/1通过。
