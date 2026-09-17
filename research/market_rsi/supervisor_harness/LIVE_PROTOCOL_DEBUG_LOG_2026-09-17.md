# Market RSI 连接调试记录（2026-09-17）

这份记录把**已经发生的事**和**仍待验证的推测**分开。它是外层 supervisor 的基础设施调试，不是 GLM controller 的研究轮次，也没有预测成绩。

## 真实运行：为什么没通

| 时间（纽约） | 实际发生 | 证据 |
| --- | --- | --- |
| 11:45:53 | 新 ID `market-rsi-protocol-canary-20260917-02` 通过已发布源码、全局状态、零费用前置检查；为 E2B 预留 $0.20 上限。 | `artifacts/market-rsi-protocol-canary-20260917-02/admission.json`、`reserved.json` |
| 11:45:54 | 宿主机读公开测试页成功；随后记下唯一一次 E2B dispatch。 | `host-public-read.json`、`dispatch.json` |
| 11:45:55 | 创建了一个 Controller 沙箱 `i565muqh7qx7qopziiolr`。程序调用 `get_info()` 后，在 `policy_controller` 抛出 `ValueError`。 | `controller-sandbox-id.json`、`child-failure.json` |
| 11:45:55 | 子进程退出码 1，父进程已等待它结束；沙箱 kill 得到确认，账户列表为 0 个活跃 Market RSI 沙箱。 | `parent-process.json`、`child-cleanup.json`、`parent-account-check.json` |
| 11:45:55 | 轮次记为失败；$0.20 作为**未知用量上限**占账，不是 E2B 发票。没有创建 Researcher 沙箱，也没有双向应用测试、GLM 或预测实验。 | `parent-terminal.json`、权威预算账本 |

上表时间来自本地文件修改时间，精度约一秒；不能用它当作 E2B 的计费时长。

## 查到的程序问题

旧版向 E2B SDK 传了 `allow_internet_access=False` 和网络规则；固定的 SDK 会把这些参数写进创建请求。但旧版随后要求 `get_info()` **逐字段原样回显**网络规则。固定 SDK 把回显网络字段定义为可选，服务端也可能省略或规范化字段；旧版把缺失和明确相反的配置混为一个 `ValueError`，且在抛错前没有保存具体返回字段。因此这次能确定的是**我们的检查过早退出且日志不够**，不能从旧日志确定服务端究竟返回了什么，更不能断言网络隔离已通过或 E2B 有故障。沙箱销毁后再查其详情得到 404。

11:45 的第一个沙箱一创建就停，真实的 A→B/B→A、HTTP/TLS 测试**根本没执行**。此前旧 canary `dual-e2b-role-canary-20260917-05` 观察到公网 IPv4 TCP 能建连，但它没有测试 HTTP/TLS 载荷；这又是另一条尚未解决的证据，不能混成这次失败的具体原因。

## 已做的修复和验证

- 本地版先保存有界、不含密钥的配置回显和字段判定。若 E2B **明确**返回相反配置，立即停止，不创建第二个沙箱。
- 如果只是可选字段**缺失**，仅继续这次没有密钥、没有行情和封存数据的合成双沙箱网络诊断；无论应用探针观察到什么，仍将该轮记为“策略回显未确认／失败”，不会解锁真实 GLM 或声称隔离成立。
- 真实失败 ID 不修改、不重试。新增测试覆盖“明确相反配置立即停”和“缺字段时收集双向证据但最后仍失败”。截至 12:19 纽约时间，51 项相关离线测试通过；这不等于 E2B 实测通过。

## 为什么现在没有再启动

现有权威账本：总有效占额 $90.903153492／总上限 $200；setup 类别剩 $0.049486662，下一次按现行源码要先占满 $0.20。另有以前已 dispatch 的 setup 请求共 $2.20 未结算，不能当成未发出预约取消。E2B 账户网页停在登录页，尚未取得这只沙箱的实际费用凭证。新代码还未发布为用户 fork 上的新标签。**预算类别与版本双重闸门仍挡住新付费测试**；目前没有活跃的匹配进程或遗留沙箱证据。

下一步不是继续盲试：先取得明确的原 $200 内类别调整决定或可核实的实际费用，再发布精确的新版本，使用新 ID 跑一次合成诊断。随后核对原始回显、HTTP/TLS、A↔B 标记、清理与费用；任何失败都保留，不能为了好结果反复重试。

## 第二次真实测试：走到双沙箱，卡在探针超时

用户明确同意在原 $200 上限内把 $0.20 从 repair 调到 setup、发布修复版并只跑一次新测试。账本以追加事件记录了这次调整；`market-rsi-protocol-v0.1.1` 已发布到用户 fork，源码哈希 `20557935da038374c2bfda5b3517b5af3c3932ad231015dfa87c6c990fc6a0ff`；新零费用 fixture `research-cycle-fixture-20260917-14` 通过。唯一新测试 ID 是 `market-rsi-protocol-canary-20260917-03`。

- E2B 创建了不同 ID 的 Controller 和 Researcher 沙箱。两者 `get_info()` 均返回 `allow_internet_access=false`、`deny_out=["0.0.0.0/0"]`、`allow_public_traffic=false`，但都**省略** `allow_out`。这解释了上一版过严的逐字段回显检查为什么可能过早退出；仍不证明实际网络隔离。
- 两个沙箱的密钥、对方私有文件、本机用户目录边界检查通过。A→B 方向中，B 的本地标记服务正面检查通过（第二次尝试响应），说明服务本身能工作。
- A 里的四项公开/对端、代理/直连 HTTP 测试由 `commands.run(timeout=25)` 承载；SDK 返回 `TimeoutException`，没有完整 HTTP/TLS 报告，也没有进入 B→A。不能把“未观察到响应”说成“网络阻断”，也不能说已连通。
- 子进程退出码 1，父进程已等待；B 的标记服务和两个沙箱都得到精确 kill 确认，E2B 账户查询为零个活跃 Market RSI 沙箱。账本将本次整笔 $0.20 记为未知用量的**保守上限**，不是发票；总有效占额为 $91.103153492/$200，setup 余 $0.049486662。没有 GLM、行情、Dev/Final 或预测结果。

定位记录：`artifacts/market-rsi-protocol-canary-20260917-03/` 下的 `*-policy-observed.json`、`*-policy-verdict.json`、`*-boundary.json`、`a-to-b/peer-local-positive.json`、`a-to-b/failure.json`、`child-cleanup.json`、`parent-account-check.json`、`parent-terminal.json`。2026-09-17 搜索官方 E2B 文档，查询为 `python SDK commands.run timeout parameter TimeoutException sandbox command`；阅读 [E2B Commands.run 文档](https://docs.e2b.dev/sdk-reference/python-sdk/v2.5.0/sandbox_sync) 的超时与连接说明，并核对本机固定的 `e2b==2.38.0` SDK。该参数约束整个流式命令连接，不是四个 HTTP 请求各自的 25 秒；一次请求的超时不会证明访客命令已被杀。因此本地候选只把整组探针的 SDK 连接上限从 25 秒改为 60 秒，仍保留 E2B 沙箱的 180 秒寿命和父进程超时。23 项相关离线测试通过。**这只是尚未发布、尚未实测的修复假设**，不能据此判定下一次必然成功。用户只授权了一次新付费测试；不再自动启动第二次。
