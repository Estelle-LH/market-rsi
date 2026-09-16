# NFL source blocker与下一阶段

日期：2026-09-16  
状态：Harness v1.6.8已发布并完成一条Controller run；还不是新的预测结果

## 观察到的问题

`dsh-v1.6.6` Controller把下一步定为Sportradar Push prospective canary。Recorder和安全边界已经
实现，但唯一一次真实trial entitlement preflight返回HTTP 403、没有redirect、没有stream
entitlement。API key和signed redirect都没有落盘。这个结果只说明当前trial不能跑Push，不说明
Push字段不存在，也不说明模型或算法失败。

改变的Harness component是`data_acquisition + controller_context`。简单基线是继续等待同一个Push
权限；它不会产生新信息。另一个选择是跳过source gate直接拟合derived-state模型；这会把历史字段
当成live可用，和上一轮预先写下的direction flip冲突。当前选择是把403和合法替代source证据加入
下一条fresh controller workspace，让Controller在换source、Replay canary、market-response、
target/horizon或新算法之间自己选一个阶段。

## 公开资料研究

检索日期：2026-09-16。

查询：

- `official NFL live play by play API push websocket created_at updated_at provider timestamp documentation pricing`
- `official SportsDataIO NFL play by play API real time timestamps corrections trial pricing`
- `official OpticOdds NFL play by play websocket timestamps documentation pricing`
- `official API-Sports NFL live play by play events timestamps documentation pricing`

实际阅读：

1. [SportsDataIO API Resources](https://sportsdata.io/developers/apis)，`Testing Options`、`Free Trial`、
   `Replay`和`Production Key`。Free Trial是scrambled结构数据，不能用于研究结论；Replay是真实历史
   比赛，按live feed节奏、用production格式重放。它可验证capture/parser/update mechanics，但不能
   证明当前比赛延迟、market lead或production entitlement。
2. [SportsDataIO access methods](https://sportsdata.io/developers)，`Discovery Lab`、`Leagues API`、
   `Vault / Historical Data`。Discovery Lab提供real但next-day数据，free tier含last season；深度
   real-time PBP要商业Leagues API。公开页面没有给本项目的准确报价、字段完整性、研究存储授权或
   provider publish timestamp保证。
3. [SportsDataIO timing](https://sportsdata.io/help/refresh-rates-feeds-and-timing)，`Play-By-Play`和
   `Scores`。页面描述PBP实时更新、最小3秒cache，常见速度是相对cable/OTA约20–30秒。它不是我们的
   实测publish-to-receive分布、SLA、时钟同步或领先市场证据。
4. [OpticOdds Odds API](https://developer.opticodds.com/docs/odds-api-getting-started-guide)，
   `Real-Time Streaming`、`Results Stream`和`Historical Odds`。它有SSE odds/results与带timestamp的
   历史价格变化，但不是完整NFL PBP，不能直接补齐缺失的play-state primitives。

状态区分：上述页面已找到并阅读；v1.6.8 adapter已实现；尚未用这些source跑新的provider canary、
训练、Route-Dev或Final，也没有账号注册、询价、购买或对外消息。

## v1.6.8的边界

新adapter只复制hash绑定的aggregate结果、post-hoc audit和403 receipt。它不复制raw row、game/play
identifier、credential、Route-Dev、Final或训练入口。Controller可以自由提出有限horizon/target，
包括不使用秒数的event-time目标；只有进入confirmation前才冻结reward和一个选择。5秒、30秒、
60秒、一小时窗口和任何provider threshold都不是Harness默认答案。

## 实际Controller结果

`nfl-source-blocker-controller-20260916-01`在运行层面完整结束：12 turns、14 tools、0 fit、
0 Dev/Final，本次Tinker费用`$0.504720234`。它正确保留了source/timing gate，但最后的capability
混入不存在于ledger的数字和字段，因此没有进入执行。详细逐步记录和v1.6.9修复见
`NFL_SOURCE_BLOCKER_CONTROLLER_TRACE_2026-09-16.md`。

Controller自行提出`30/60/300秒`作为opened-Train候选grid；这不是Harness预设。因为没有source
admission或数据score，grid也没有得到支持。未来仍可以自由探索event-time、其他秒数或其他target，
但必须在本阶段看分数前冻结选择规则，protected confirmation只携带一个已选答案。
