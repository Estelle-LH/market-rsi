# Controller memory study v2

## 要回答的问题

同一个 GLM controller、同一套 Codex harness、同一批按时间推进的数据和同一套训练工具，
只改变 controller 能看到的自身历史，结果会不会不同？

三条路线是：

- `fresh`：每轮不看自己的旧记录。
- `archive`：每轮看自己过去的完整记录。
- `compact`：每轮只看从自己旧记录中按固定程序整理出的短摘要。

本实验只回答 controller memory 对预测误差的影响。它不证明能赚钱，也不把旧实验的部分
Final 分数当作证据。

## 为什么要重新做

v1 已经完成8轮 controller，但 Final 第一次运行碰到资源上限；recovery 做完4/20个 Final
session 后，又发现第5个原始文件的 source timestamp 越过声明UTC日。旧 preflight 只证明
文件能完整解压，没有运行正式的数据选择逻辑。因此 v1 recovery 永久停止，4个部分分数
不用于模型选择或正式比较。

v2 的科学问题不变。改变的是实验基础设施：所有 Train、rolling Dev 和 Final 数据必须在
第一次付费 controller 调用前，完整走一遍正式 `CacheProfile.consume`。正式 materialize
还要再次复现完全相同的文件hash、记录数、选中观察数、实体数和时钟统计，之后才允许写
训练缓存。

## 数据怎样选

先写好按时间排序的候选池，并按 Train、8个 rolling Dev、4个 Final 日期层分组。每层选择
最早通过完整语义检查的固定数量。这个阶段不计算target、MSE、IC，不运行模型，也不看任何
分数。失败文件保留hash和原因，只能在manifest冻结前按这条固定规则跳过。

最终固定3个初始Train session、8个rolling Dev session和20个Final session。Train早于Dev，
Dev早于Final；以前打开过分数或用于测试的session不能回来当新实验数据。

## 正式运行顺序

1. 候选池完成score-free语义检查，并按固定规则生成manifest。
2. 把manifest写进v2 spec；将31个已选文件已有的完整语义回执绑定到spec，不重复读取原始
   文件。正式materialize仍逐文件重新读取，并复现原回执后才写训练缓存。
3. 冻结代码、spec、数据清单、目标、模型、预算和重跑规则，提交并发布带注释的Git tag。
4. 运行0-provider canary，验证 Codex 工具、真实拟合和最终提交握手。
5. 每轮三条路线先全部提交方案，再一起打开该轮Dev；Dev随后进入下一轮Train。
6. 第8轮提交后冻结模型；20个Final session只打开一次；报告按session等权MSE。

## 哪些东西固定

- GLM controller型号、Codex harness、seed 23、每轮最多3个候选、共8轮。
- 60秒因果quote-midpoint目标、行资格规则、特征/normalizer/trainer library。
- 三条路线看到完全相同的当轮Train与Dev结果；只有自身历史的表示不同。
- primary metric 是20个Final session的等权MSE；PnL不在本实验中测量。
- 原 `$200` 全局上限继续生效；只把GLM controller实际metered usage算作本实验付费部分。
  预留不是消费。每轮三条路线是不可拆的预算单位。

## 失败后什么时候重跑

- 先永久保存旧失败，再查明单一原因，只修改出错层，并通过单元测试与真实正反canary。
- 只有结果产生前的机械故障，且数据、模型、目标、manifest和评分都没变，才可用新ID重跑。
- 只有精确checkpoint可幂等继续、没有结果和未确认外部副作用时，才能继续同一个run。
- source只可在manifest冻结前按预先规则跳过；冻结后出错，整轮作废，不能临时换session。
- 分数低、没有提升、合法timeout、格式失败或模型行为差都是实验结果，不能为了分数重跑。
- 根因没找到、修复没测过、下一完整单元放不进剩余预算时，停止并记录。

## 通过标准

- 31/31已选source通过spec绑定的完整语义preflight。
- 正式materialize逐文件复现preflight，且没有原始行情发给controller。
- 8/8轮每轮三条路线都完成，所有费用有terminal receipt。
- Final有20/20个session、四个arm使用相同行数，且只打开一次。
- 报告完整分数、配对差值、胜率、费用、失败和限制；不把趋势写成盈利结论。
