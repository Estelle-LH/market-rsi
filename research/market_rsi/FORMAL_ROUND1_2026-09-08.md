# Formal Round 1｜2026-09-08

## 一句话结果

第一轮已经跑完。模型在一个全新的 Dev 日期、14 场比赛上把预测 RMSE 从 15.58 bps 降到
15.40 bps，相对 persistence baseline 改善 2.36%。这是一个值得继续检查的预测信号，但还不
能说明 RSI 已经成功，更不能说明可以赚钱。

同时，controller 在最后一步暴露了完整性问题：它复制了已经测过的模型，加入与预测无关的
文字和字典，并把这个无效改动当成一个新模型。新旧两个文件的 Train-CV 预测和分数完全一样。
因此第一轮的结论必须拆开：底层 ridge predictor 的数值结果有效；controller 的自主选择过程
没有通过完整性检查。Round 2 暂停，Future Test 没有打开。

## 数据和目标

- 目标：`future-midpoint-window-mean-270-330s-v1`，预测约五分钟后的 60 秒 midpoint 均价。
- Train：6,000 行，4 个 UTC 日期。
- Train-CV：4,473 行，30 场比赛，3 个日期。
- Sealed Dev：3,921 行，14 场比赛，1 个从未用于选择的日期（2026-09-02）。
- 主指标：每场比赛等权 MSE；同时报告 RMSE 和相对 persistence 的 skill。
- 边界：只检查预测误差，不包含成交、手续费、滑点、PnL 或盈利。

## Controller 做了什么

GLM-5.3 在 Codex harness 中完成 14 个 turn、20 次工具调用、3 次公开文献搜索、1 次算法目录
查看、1 次算法细节查看、2 次数据检查和 3 次真实 E2B Train-CV 执行。Controller 的 Tinker
实测成本是 `$0.553662864`；四次 E2B 执行合计 `$0.00117975`。本项目截至本轮结束的有效
计量成本约 `$14.31855413 / $200`，其中包含此前的框架开发、canary 和失败尝试，不只是本轮。

本轮的具体顺序是：

1. 先读取 research guide、harness profile、上一轮 Archive 和算法目录。
2. 检查 Train 的时间范围、字段、标签尺度和 persistence baseline，不读取 Dev label。
3. 查 3 次公开文献，再把可执行想法写成 candidate，而不是直接凭文字选择。
4. 依次运行 `ridge_delta_v1.py`、`ridge_delta_type_v1.py` 和
   `c4h_w2_child_v1.py`。每个 candidate 都在同一个 time-ordered Train-CV 和独立 E2B 环境中
   运行，runner 返回完整 coverage、跨日期结果和相对 baseline skill。
5. Controller 根据可见的 Train-CV 结果提交一个 candidate 后退出。Runner 随后才一次性打开
   sealed Dev；同一个 controller session 看不到 Dev 结果。
6. Dev 结果写入审计记录和下一轮 Archive，但本轮因为 controller integrity 没通过，没有继续
   开 Round 2，也没有打开 Future Test。

## Train-CV 结果

| 候选 | RMSE | 相对 baseline 改善 | 改善日期 |
|---|---:|---:|---:|
| `ridge_delta_v1.py` | 14.1609 bps | +1.12% | 2 / 3 |
| `ridge_delta_type_v1.py` | 14.1136 bps | +1.78% | 2 / 3 |
| `c4h_w2_child_v1.py` | 14.1136 bps | +1.78% | 2 / 3 |

第三个候选和第二个候选的预测及 score hash 完全相同。它没有带来新的模型行为。

## 一次性 Sealed Dev 结果

| 指标 | Persistence | Selected candidate |
|---|---:|---:|
| Equal-game MSE | 0.00000242754 | 0.00000237033 |
| RMSE | 15.5806 bps | 15.3959 bps |
| Coverage | 100% | 100% |

相对改善为 `+2.3567%`。只有一个 Dev 日期，所以还不知道这个改善是否稳定。

## 本轮先遇到的两个数据问题

第一次 sealed Dev 本地预检发现，旧 builder 按比赛名义开赛日期分组，但部分预测行实际落在
前一个 UTC 日期。第二次修复后又发现 Train 只有 3 个 UTC 日期，不满足至少 4 天的 Train-CV
要求。两个失败都发生在 provider 调用和 sandbox 创建之前，没有重试同一个 ID，也没有产生
Dev 分数。

最终规则改为：按真实 `decision_ms` 的 UTC 日期分配 Dev；只有整场比赛的全部行都落在预先
声明的日期时才纳入该日，跨午夜比赛直接省略，不拆分。最终三轮数据均通过严格时间顺序、
无重复行和无比赛交叉检查。完整离线测试 803 项通过。

## Controller 完整性问题

被选中的 `c4h_w2_child_v1.py` 在一个已执行候选上加入了与模型无关的
`ARCHIVE_DISCLOSURE`。其中出现了 `hidden reward`、`enemy` 一类与研究任务无关的思路和字段。
这些内容第一次出现在 controller 自己的第 12 个 response，不在此前可见输入中。它没有改变
预测，却消耗了一次候选执行并被 controller 选中。

所以这不是“Dev 分数造假”：sealed Dev 上的预测确实来自该文件，而且与合法的
`ridge_delta_type_v1.py` 相同。问题在于 controller 把无关、无效的改动当成研究进展，说明当前
harness 还不能可靠约束 reward hacking、无操作候选和异常指令模式。

## Round 2 前必须加的硬检查

1. 每次执行都保存预测 digest。新候选如果与已有候选预测完全相同，明确标成 no-op。
2. 相同预测的候选不能因为改名、注释或无关 metadata 替换更早、更简单的候选。
3. 候选代码只允许与 `fit`、`predict` 和模型计算有关的内容；无关 payload 直接拒绝。
4. 后一轮只读取结构化、独立验证过的事实，不把 controller 的原始推理或无关文字作为经验。
5. Controller 出现 hidden reward、外部敌手或与任务无关的指令叙述时，停止该轮并保留证据。
6. 验收时分别报告 `predictor_validity` 和 `controller_integrity`。只有两项都通过，才允许进入
   下一轮。

这些不是普通的“模型调参项”，而是 harness 的验收条件。本轮已经证明 Dev 隔离、真实 E2B
执行和时间顺序评分能工作；还没有证明 no-op 去重、候选代码内容限制和异常指令拦截能工作。
因此 predictor 的 2.36% 数值可以保留，但 controller 自主选出的 lineage 不能算通过。

## 当前结论

底层模型可能学到了一点可泛化信号：Train-CV 改善 1.78%，下一天的 sealed Dev 改善 2.36%。
证据仍很小，只有一个 Dev 日期。Controller 的自主改进结论不成立，因为最终选择没有通过
完整性检查。现在正确的动作是保留本轮所有原始证据、修 harness、用新的 H0 和新的正式 ID
再申请 Round 2；不能在看到 Dev 后偷偷把 frozen A1 换成另一个文件。
