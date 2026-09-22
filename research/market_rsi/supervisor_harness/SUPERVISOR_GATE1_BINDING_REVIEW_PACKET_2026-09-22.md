# Gate 1 接线：待独立复核的本地候选版

状态：**待审，不可发布，不可调用付费 Controller。** 本文件是 Supervisor 的交接材料，不是独立审查结论，也不是预测结果。对应计划为 `SUPERVISOR_GATE1_BINDING_2026-09-22-v1.json`。

## 为什么改

S1 审查发现正式 Controller 的交易任务可以只有 `task.json`，没有精确请求清单，却通过外层复核。初次修复又让真实 Train 目录成为所有 live 回答的前置条件，连找数据所需的文档调查与新来源提案都无法启动。这两个问题现在被分开处理。

## 候选行为

| Controller 回答 | 无真实目录时 | 有代码登记且审查过的真实目录时 |
| --- | --- | --- |
| 文档调查 | 可完成“计划待审”，不抓数据 | 同左 |
| 新来源提案 | 只归档待审，不获得执行权 | 同左 |
| 固定交易查询 | 当前工具菜单不提供；强行提交也被外层拒绝 | 由原始决定和目录字节编译精确清单，再逐字节复核；仍不自动联网 |

目录路径、文件 SHA-256 和代码内承诺必须成组提供；不完整或合成目录不能冒充真实目录。当前登记表**只有合成目录**，所以第三列尚无真实可运行实例。

## 已执行的零费用验证

- 相关单元测试：110/110 通过；`git diff --check` 通过。
- 无目录生产参数路径 canary：`/private/tmp/market-rsi-gate1-no-catalog-canary-20260922-0340-01/canary-result.json`，`passed=true`，provider 调用 0，网络/抓取 0，实际费用 0。里面 `$0.00005103` 是**合成账本**，不是账单。
- 模拟 live 模式的单测验证文档调查和提案不依赖目录，固定交易任务缺目录会失败并保留计量终态。这不等于真实 GLM 模型验收。
- 更广的 Supervisor discovery 为 475 项、1 失败/6 错误：缺 `scipy`、受限环境端口权限和旧 E2B 测试条件。不得称全套通过。

## 待审源码快照 SHA-256

以下是本地候选字节；改一行就必须重新计算，并重跑相关验证。

| 文件（均在 `research/market_rsi/supervisor_harness/`） | SHA-256 |
| --- | --- |
| `build_p0_gate1_controller_packet.py` | `ee7e48e1e2ffe41906d050c40362c9ff89278c214ad667d27ef6d9ca012abafa` |
| `p0_gate1_controller_adapter.py` | `03b74692d246074f96641f87691b7aafe4100a3659f17078c05abaece998d38e` |
| `p0_gate1_controller_outer.py` | `2b007743e9e956aee5b8b365bfda765919e61c7e1a97d8b2f03b24cf5cc712b0` |
| `p0_gate1_controller_live_entry.py` | `c949fe4c1961c8dc4c5b48efe6a04ff2e7947e391328c904987a3e2affb40349` |
| `p0_gate1_controller_supervisor_parent.py` | `e25f9d083e201f40e5bc67c04b5da072b9fb111e2a667e3f94b84803d05d0abe` |
| `p0_gate1_plan_compiler.py` | `32dd48b10dc7eb7dcde03f9dfa1805729cddc156d54b0423014251cf96969c1e` |
| `p0_gate1_trade_query.py` | `60117c1ea76bfec6bca818d31ae05699f01ebe412ffd1babd1363e8da085784e` |
| `protocol_source_release.py` | `56aac9368df38da869a5e34fad46b6b59b9881220fcd09fc197498575047b4df` |

## 独立复核必须回答

1. 在当前 packet 中，模型提交工具是否真的看不到交易操作？若仍构造交易回答，外层是否终态失败而不产生请求或数据权限？
2. 文档调查与提案在**无目录**时是否通过同一正式 parent/child 参数边界，且不把提案变成任务？
3. 传半套目录参数、篡改目录字节、未知承诺、合成目录伪装真实，是否都在密钥或子进程前拒绝？
4. 编译结果被删、改值、改类型、加网络许可或改 URL，外层是否重新计算并拒绝？
5. 受控源码清单是否覆盖所有实际导入的生产模块？当前脏工作树哪些是本次范围，哪些属于其他工作？
6. 预算、永久 ID、global state 和零费用 canary 回执是否保持各自终态；没有真实数据或封存集被读？

即使这六项通过，真实目录入场、版本提交/发布、发布版零费用 canary、一次新的付费请求授权仍是**分别关闭的后续关口**。
