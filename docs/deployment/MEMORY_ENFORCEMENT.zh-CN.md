# Memory 如何强制执行

这份说明来自受控研究实现的源码和协议只读核对。该运行实现与真实 memory 未包含在本次发布中；[公开合成检查](../../examples/deployment_checks/README.md)也不是其替代实现。

Memory 接入原 prepare、当前输入检查和 runner 生命周期。约束覆盖配置所指定的新任务，旧 attempt 保持历史语义。

## 启动前：读取最新、已收尾的状态

`current()` 校验 schema、实验身份、Source、原 terminal、真实退出、费用结算、pending、清理和私有封口 metadata。它核对有限的指定 metadata，不递归读取私有内容。

遗留 `active_iteration`、memory bookkeeping failure 或更晚 attempt 已有读取/更新/terminal 证据时，下一次启动被拒绝。这防止把 CURRENT 换成早期副本后继续派发。

`predecessor()` 要求 CURRENT 与前一步的不可变 update 完全一致。Prepare 为新任务保存 `inputs/<id>/research-memory.json`，同时绑定 predecessor snapshot、closure 和 private-seal metadata。Source-bound origin、任务及完整 feedback 必须一致。

Runner 在 owner、凭据、Docker 或模型工作之前再次检查当前状态。Prepared 快照过期不能凭旧回执启动。

## 开始：读取回执与 active 标记

原 owner clock 建立后、Docker/首个角色工作前，`begin()` 写不可变 `research-memory-read.json`，记录输入快照、完整 feedback 绑定和内容哈希；安装 `active_iteration` 后，再写 `research-memory-begin-complete.json`。

读取成功和 active 安装完成是两个检查点。硬崩溃留下 active 标记时，需要依据原证据核对收尾，不能伪造完成或重开旧 owner。

## 模型输入：实际内容与绑定都要匹配

Controller/Author 的完整反馈必须包含与任务快照严格相等的 `research_memory`。分层反馈可以按已授权协议替换固定负例正文，但完整 memory 保留在 Controller projection 和 Author canonical feedback 中。

已有物理请求审计把实际 HTTP intent 与保存的 generation request 对应，核验实际用户输入包含经验证的完整 feedback。记录“已发送”不构成这项证明；代码审阅也不构成一次真实请求验证。

冻结 evaluation 窗口只读取 Supervisor memory 作 bookkeeping，保持冻结候选和预测输入不变。

## 结束：自动记录成功、拒绝和失败

`finish()` 只接受当前 runtime 的原 result/failure terminal。成功需要匹配的读取回执与完整 begin；状态和文件名必须一致，过时或并发替换会被拒绝。

随后写不可变 `research-memory-update.json`，替换 CURRENT 并回读。更新保存输入快照、Source、原 terminal 和错误类型，继承已有 `lessons`。

当前实现把详细解释留作待证据裁定，`learning_claim` 为 false。自动写回记录结果，不自动生成新教训，也不证明模型理解、利用记忆或研究能力提高。

Memory 更新仍把 owner/费用 closure 标为 pending。下一次启动须独立验证原退出、结算和封口，不能由 memory 文件代替。

## 错误与并发

Writeback 错误单独记为 bookkeeping failure，保留原 terminal 和原异常，不把成功实验改成可重试失败，也不掩盖原执行失败。任何 memory 失败都不提供付费重放权。

检查后 rename 并回读依赖原唯一 owner/唯一 Supervisor writer，不是跨主机原子 CAS。迁移必须先冻结源端，再让目标端成为唯一 writer。

## 验收边界

应在原实现上验证缺失/过期快照、前驱不符、foreign path/symlink、active 遗留、begin 安装失败、成功/拒绝/失败 writeback、closure/private metadata 不符、倒退及原异常保护。

已有原 memory 测试定义在本次核对中仅被阅读，未重新执行。公开示例的 43 项通用 fixture 测试属于另一套检查，不能替代上述生产验收。规范路径、历史证据与真实恢复包留在受控部署环境。
