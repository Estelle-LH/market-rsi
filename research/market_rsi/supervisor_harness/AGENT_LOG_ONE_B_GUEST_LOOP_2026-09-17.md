# P0：B 沙箱持续接收与回显

- 2026-09-17：任务登记。只做离线 guest 实现与测试，不启动付费沙箱、GLM 或封存评估。状态：进行中。
- 2026-09-17 20:17:30 UTC：已核对 `AGENTS.md`、`RESEARCH_STATE.md`、方向架构及 `directional_handoff.py` 的精确订单/ACK/事件路径和 schema。新增 `directional_guest_worker.py`（独立标准库 CLI，一进程处理 20 个序号、严格任务哈希/会话绑定、独占原子发布、持久化后 stdout JSONL 里程碑、超时和篡改/重复拒绝）及 `test_directional_guest_worker.py`。此处复用已定义的合成文本 SHA-256 协议，不引入科学方法、数据或新文献主张；未进行网络/付费操作。下一步：运行离线测试，修复发现的问题，并记录最终结果。
- 2026-09-17 20:18:48 UTC：首次 11 项离线测试发现 fresh-output 检查误将迭代器当真值，已修复；随后增加会话绑定和 ACK 后订单篡改回归测试。最终执行 `python3 -m unittest supervisor_harness.test_directional_guest_worker supervisor_harness.test_directional_handoff supervisor_harness.test_researcher_guest_worker -v`，31/31 通过（新 guest 13/13）。核验了 20 个顺序订单、40 条已 flush 的 ACK/event 里程碑、准确的 host schema/hash、CLI `-I`、超时、重复任务、JSON 重复键、非法/符号链接文件、先前订单/输出篡改、ACK 后篡改和事件发布失败时不虚报事件。改动仅限新增 guest、其测试及本日志。剩余：真实单 E2B 的放置、通信延迟、隔离、计费和清理均未测试；宿主必须独立核验产物、执行源门槛并记录真实费用。结果仅为零付费本地协议测试，不是研究改进或实时沙箱通过。
- 2026-09-17 20:19:21 UTC：为“持久化后里程碑”补充目录 `fsync`（先同步文件，再原子独占链接、移除临时名、同步目录，最后输出 stdout）。同一 31 项离线测试再次通过。无外部进程、沙箱、模型或付费调用。
