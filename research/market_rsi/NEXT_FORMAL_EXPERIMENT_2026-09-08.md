# 下一次正式实验草案｜2026-09-08

现在还不能启动正式 round。昨天的目标是 60 秒后的一个价格点，约 95%–97% 的样本没有变化；
目标没有在 model iteration 之前经过 Train-only 研究和冻结。因此昨天的结果是 harness pilot，
不是正式 RSI 性能证据。

## 开始前先完成

1. 从密集原始行情生成未来 45–75 秒的标签候选。
2. 只用已开放 Train 比较：60 秒单点、未来窗口均值、Forward EWMA、未来窗口中位数。
   如果先补齐并验证历史成交流，再把未来成交 VWAP 加入目标比较；当前归档没有 trade stream，
   所以不能假装已经可以比较。
3. 报告 coverage、目标不变比例、变化尺度、前后窗口稳定性、每天/每场基线误差和 EWMA
   的有效 horizon。
4. Controller 根据公开文献和这些 Train 诊断选择一个目标；runner 冻结目标、horizon、窗口、
   基线、raw metric 和 relative skill metric，并写入 hash contract。
5. 目标冻结后，才分配更晚、未打开的 Dev。

## 正式 round 要回答的问题

在同一个已冻结的预测问题上，GLM controller 使用 Codex research harness，能否通过查文献、
检查数据、修改特征、模型和训练方法，在连续的未见 Dev 上比固定 persistence baseline 更好？

## 一轮怎样走

- Train-CV 至少有 4 个 UTC 日期，按时间用早期数据 fit，连续预测后 3 天；不随机拆行，完整
  比赛不能跨边界。
- Controller 可以反复看 Train-CV，最多使用预定的 candidate execution 次数。
- Controller 冻结唯一 candidate 并退出后，runner 打开当前 Dev 一次。
- Dev 得分只进入下一轮 Archive；该 Dev 随后进入下一轮 Train，不能再作为 Dev。
- 下一轮使用更晚的新 Dev。Future Test 在所有最终提交冻结前不打开。

## 每轮报告

- raw equal-game MSE；
- 相对 frozen baseline 的 skill；
- 每天和每场比赛的结果、覆盖率、预测变化幅度、失败和 timeout；
- 文献搜索、代码、特征、模型、loss / training transform、参数和选择理由；
- 实际模型 tokens、sandbox 次数、时间和费用。

一个 Dev 变好只算方向性证据。连续多个新 Dev 都变好，而且不是一两场比赛造成，才算重复
进步迹象。盈利能力是后续独立 execution experiment，不由 MSE 直接推出。
