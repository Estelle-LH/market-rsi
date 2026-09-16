# SportsDataIO Replay采集Canary

日期：2026-09-16
状态：代码已实现并通过离线测试；尚未连接真实Replay账号或session；不是新的预测结果

## 为什么做这一层

`dsh-v1.6.9`的fresh Controller在没有看到Dev/Final、没有拟合模型的前提下，提交了第一份通过
evidence binding的capability work order：先验证SportsDataIO Replay的采集、更新与时钟字段，再决定
是否能进入特征和算法实验。这个顺序合理，因为目前缺的是source/timing evidence，不是另一个未经
验证的trainer。

Controller提出的`>=30 games`、`>=5 weeks`、`>=4000 plays`和`3s polling`仍是待验证的实验设计，
不是已经观测到的数据性质，也不是Harness提前写死的科学结论。当前版本只实现一条有上限的session
recorder；在账号内的准确endpoint和使用条款确认前，不启动真实采集。

## 公开资料研究记录

访问日期：2026-09-16。

查询：

- `site:sportsdata.io/developers/replay SportsDataIO Replay documentation historical play by play`
- `site:cdn.sportsdata.io/openapi NFL openapi SportsDataIO play by play`
- `site:sportsdata.io/terms-of-service automated means access controls SportsDataIO`
- `site:sportsdata.io/help historical data integration guide replay data storage SportsDataIO`

实际阅读：

1. [Getting Started](https://sportsdata.io/developers)，`Replay`、`Free Trial`、`Vault / Historical
   Data`。Replay是past games的真实历史数据，按live feed schedule提供，response format与production
   相同，并且是session-based；Free Trial是scrambled；Vault才是研究/回测用的历史产品。
2. [Replay](https://sportsdata.io/developers/replay)，登录前的公开部分。公开页说Replay免费、无限，
   package页会列recorded endpoints和intervals；但必须登录才能看到具体package和启动session。
3. [Historical Data Integration Guide](https://sportsdata.io/help/historical-data-integration-guide)，
   `What to know`和`A note on Replay`。Replay是测试live integration的工具，不是historical-data product
   或revision archive；历史event feed只保留最终revision，不保留完整point-in-time correction trail。
4. [Integration Tools](https://sportsdata.io/developers/integration-tools)，`API Replay`。Provider说明它
   保存自身API responses，再让用户重复回放。这支持mechanical integration test，不证明真实当前比赛
   的publish latency。
5. [NFL Data Dictionary](https://sportsdata.io/developers/data-dictionary/nfl)，`Play`和available
   endpoints。公开字典列出Play By Play live/final、delta以及`Sequence`等字段，但公开资料没有证明
   哪个时间字段等于provider publish wall clock。
6. [Terms of Service](https://sportsdata.io/terms-of-service)，`Prohibited Conduct`。未获授权的自动化
   抓取和绕过access controls被禁止。因此公开网页“free/unlimited”不能替代账号内条款或书面许可。

发现与限制：公开资料支持“Replay适合验证parser/polling/update mechanics”；不支持“Replay等于历史
revision archive”、“任意自动化保存都已获许可”、“某字段就是provider publish time”或“Replay能测
真实market lead”。准确Replay endpoint、session认证方式和本地原始研究存储权仍需账号内确认。

## 实现

新增`capture_sportsdataio_replay_canary.py`。它只消费operator已经创建的endpoint，不会注册账号、点击
接受条款、启动Replay、发现endpoint或购买数据。

执行前必须同时满足：

- endpoint与authorization receipt都是本机`0600`文件；
- HTTPS host必须是receipt明确批准的SportsDataIO subdomain；
- URL不能含API key、token、signature或fragment；key只从`SPORTSDATAIO_API_KEY`读取；
- receipt明确确认该endpoint允许自动Replay polling和本地raw research storage；
- polling最短3秒、总poll数/timeout/response bytes均有hard cap；不自动重试，不跟redirect。

每次poll保存provider原始bytes、local request/receive wall clock、monotonic round trip、HTTP status、
hash、重复/连续不变标记。时间样字段和修订样字段只按JSON pointer和值原样归档。只要provider body
回显key或完整session URL，程序在落盘前停止。输出不写key、完整URL或authorization内容。

## 当前验证

离线单元测试覆盖：权限失败关闭、私密文件权限、host allowlist、URL key拒绝、raw bytes/hash、
本地时钟、重复/no-change统计、非2xx后停止且不重试、3秒与poll hard cap、key回显不落盘、字段只观察
不赋语义。Sports-event suite为72/72通过。

开发canary -08通过后，又发现JSON转义形式的session URL回显需要在落盘前解析检查；修改源码后没有
复用旧结果。最终exact-source Codex canary `data-scientist-codex-canary-20260916-09`通过：18次tool call、4个CPU fit、
1次公开搜索、1次公开阅读、0 Tinker、0 Dev/Final。它使用synthetic market rows，只证明Harness和
工具链可运行，不证明真实Replay access、数据价值或预测改善。

已发布到用户origin：commit `03f6cade7e32198b659dd48aaf338af8a8c8f4fb`、annotated tag
`dsh-v1.6.10`、release SHA256 `4b880cc0c22ce22d738160a52e9cd172b1fb8d1c26efd28d8257ba5424aa30f9`。

尚未验证：真实Replay endpoint、实际认证header、response size、NFL package覆盖、30场/5周/4000 plays
是否可得、update/correction字段语义、provider publish clock、与Polymarket的共同支持、预测提升或P&L。

## 下一道闸门

只有在operator提供账号内的准确session endpoint，并确认该session允许自动polling和本地raw research
storage以后，才能生成authorization receipt并跑一次小型真实canary。真实canary仍只验证采集机械性；
如果没有独立reviewed clock mapping，不计算publish-to-receive latency。没有这一步就不进入模型拟合，
也不打开Route-Dev或Final。
