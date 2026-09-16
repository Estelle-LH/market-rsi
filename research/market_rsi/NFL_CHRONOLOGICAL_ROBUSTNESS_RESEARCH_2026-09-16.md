# NFL 30秒Trainer的chronological robustness：修正后的事前设计

## 为什么没有直接执行Controller方案

Feedback Controller会话`nfl-feedback-controller-20260916-01`真实完成，11个turn、13次tool call，
实际Tinker费用`$0.367585614`，没有打开Dev/Final。它建议继续检查HGB相对RF的日期稳健性，但原始
方案有两个硬错误：

1. 它定义`delta = parent MSE - candidate MSE`，随后却把`delta < 0`写成candidate更好，并要求
   bootstrap上界小于0。方向相反，照做会奖励更差的candidate。
2. 它建议leave-one-date-out refit。对时间序列，这会让较晚日期进入较早日期的fit；而如果只把
   既有预测按日期重分组，也不会增加新的独立证据。

执行方没有悄悄改字后冒充Controller方案，也没有运行。错误被作为Harness反馈：dsh-v1.6.4只
接受`candidate_minus_baseline`损失差，负数才代表candidate更好；Controller指令也明确要求
past-to-future expanding/rolling origin，禁止未来泄漏的leave-one-out。

## 修正后的问题

保持target、feature、两个trainer、超参数、seed、预处理和每场等权全部不变，只改变opened-Train
内部的chronological evaluation coverage：初始fit从100场改为最早63场，之后做5个连续rolling
block，每块20场。这样check从63场增加到100场，计划日期从21个增加到29个；每一fold仍只用过去
比赛训练。

这是看过前两轮结果后的自适应Train robustness，不是独立确认。较小的初始fit也改变了模型训练
样本量，所以不能把新分数和旧分数当成完全相同的估计量；本轮只比较每个新fold内完全相同数据上
的RF和HGB。

## 唯一比较

- Parent：`full_k4` Random Forest，200 trees、depth 8、min leaf 50、max features 0.7。
- Candidate：相同`full_k4`输入的HistGradientBoosting，max iter 150、learning rate 0.05、
  31 leaves、min leaf 50、L2 1.0、no early stopping。
- Target：`elapsed_30s_delta`。
- 表示：原始state + score×time(k=4) + possession×field position + same-event state_wp_delta。
- 行：仍是原16,632个15/20/30/45/60秒共同可用play。
- 变化层：evaluation coverage only。

不调参数、不删feature、不改horizon、不做post-hoc calibration、不打开Route-Dev/Final。

## 机器固定的方向和支持规则

每个UTC check date先对当日各场比赛的MSE等权，然后定义：

`delta_date = HGB loss - RF loss`

所以负数才是HGB更好。日期ID只保存在runner-private diagnostics；公开结果只含aggregate。

支持必须同时满足：

1. 至少60%的check dates有`delta_date < 0`；
2. 对date means做10,000次paired bootstrap，95%区间上界严格小于0；
3. 至少8个check dates，否则inconclusive；
4. 最大单日绝对delta占全部绝对delta不超过50%，否则inconclusive。

另报告`mean_delta + sqrt(variance / date_count)`作为方向一致的second-moment upper cross-check，但
不把它临时加入主通过规则。

## 状态

- found/read：完成；这是对真实Controller错误和既有time-series/paired-evidence合同的代数修正，
  没有引入新的文献主张。
- implemented：完成。精确源码commit为`0d0c413618e0e5f87357e83798cdd664df45a2ef`，tag为
  `nfl-chronological-robustness-v0.1.0`；只推送到用户origin。
- validated on our data：`nfl-open-train-chronological-robustness-20260916-01`已完成，费用`$0`，
  Route-Dev/Final没有打开。

## 实际结果

扩大后的check包括100场、10,935行、29个UTC dates。HGB与RF在每个fold使用相同训练和检查数据。

- RF equal-game MSE：`0.0008653909`；相对zero-change改善`32.10%`；校准斜率`1.0771`。
- HGB equal-game MSE：`0.0007949689`；相对zero-change改善`37.63%`；校准斜率`0.9845`。
- HGB相对RF MSE改善约`8.14%`。
- 五个fold中HGB相对RF分别改善`6.90%`、`6.51%`、`7.49%`、`8.35%`、`12.44%`。

四项事前规则全部通过：

1. 20/29个dates的canonical `HGB loss - RF loss`小于0，比例`68.97%`；
2. paired-date bootstrap区间为`[-0.00009842, -0.00000545]`，上界严格小于0；
3. date count为29，大于最低8；
4. top-1绝对delta占比`31.08%`，低于50%。

方向一致的second-moment upper cross-check为`-0.00002030`，也小于0。结论按锁定规则记为
`opened_train_chronological_robustness_supported`。

## 结论边界

这次可以说：在更广的past-to-future opened-Train覆盖上，固定HGB相对固定RF的改善不只来自原来
63场或少数一个日期，且aggregate校准更好。

不能说：获得了新的独立确认。这个evaluation设计是看过前两轮后决定的，使用的是同一个163场
Train池；最后一个fold的HGB校准斜率仍为`1.1109`，提示晚期block仍可能有轻微漂移。最强feature
`state_wp_delta`只验证了历史provider event clock，仍没有live receive-time可用性、fills、fees或
PnL证据。已消费的Route-Dev也不能为了这个candidate重开。

## 凭证

- pre-score lock SHA256：`480213aa75580e8c0d6846bbd0c34a5e3de88d145393d2ecf13922ccd4c9cc39`
- result SHA256：`c2938ec08c26b51fd1e8356ac87875b0b700722909f3ba1173bc9e9609cf9734`
- diagnostics SHA256：`f88cffde8e1fdf0ac71ef5761ccb9e8cb06e9abb7fb5be2c04977aec19fd8228`
- manifest SHA256：`a1ebb3a87735136a8778468f991fc7479d300a2c5c3db5500977d64126c3ade6`
