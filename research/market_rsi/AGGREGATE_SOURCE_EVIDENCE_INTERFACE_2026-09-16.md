# Aggregate-only Controller的来源证据接口

日期：2026-09-16

## 为什么改

真实会话`nfl-live-timing-controller-20260916-01`已经收到runner整理并冻结的四条官方资料事实，
但`dsh-v1.6.5`的`record_research`只接受controller自己用`read_public_source`重新打开网页后生成的
record。会话中的官方页面读取先遇到404/403，随后公共网页body预留额度用完。Controller因此
不能把已经存在的来源事实登记成research record，不能继续调用后面的contract工具，最后只能
defer。这个结果不是“source canary方案被数据否定”，而是证据接口没有接通。

本次只改aggregate-only workspace的来源证据入口，不改目标、特征、trainer、数据、split、reward、
预算或Dev/Final权限。旧会话、旧workspace和它的defer结果不改。

## 已有研究怎样复用

这里没有重新声称做了一次新文献搜索，而是复用2026-09-16已经完成并记录的primary-source阅读：

- 查询问题：NFL live play-by-play能否区分event clock、provider publish和local receive？
- Sportradar NFL Play-by-Play，读取`Update Frequency`：live in-progress TTL为3秒，建议每3秒请求。
  <https://developer.sportradar.com/football/reference/nfl-play-by-play>
- Sportradar Push Events，读取产品说明、subscription example和data points：文档描述为real-time，
  字段包括`created_at`、`updated_at`、`wall_clock`及review/reversal信息。
  <https://developer.sportradar.com/football/v6/reference/nfl-push-events>
- Polymarket Market WebSocket，读取market channel messages：消息带provider timestamp，但本机
  receive仍需另记。<https://docs.polymarket.com/api-reference/wss/market>
- nflverse README，读取Play by Play update schedule：raw JSON通常赛后1--2小时出现，只适合
  history/backfill。<https://github.com/nflverse/nflverse-data/blob/main/README.Rmd>

这些资料只支持“来源可能提供什么字段/更新方式”。它们不证明我们的账号有权限，不是实测SLA，
不证明字段完整、市场领先、可成交或P&L，也不能代替prospective canary。

## 比较过的办法

1. **继续让controller重新下载页面**：基线做法。真实会话已经因403/404和body额度失败，而且重复
   下载同一证据没有增加科学信息。
2. **允许任意finding文字直接算文献**：不采用。这样无法区分runner事实、模型总结和未验证主张。
3. **只开放结构化、runner绑定的来源事实**：采用。来源必须在当前冻结`findings.json`中，必须有
   `runner_verified_primary_source_fact`类型、URL、读取部分、事实和transfer limitation；每次读取
   都进入append-only ledger并绑定source、finding和整份findings的hash。

## 实现和边界

`dsh-v1.6.6`新增`read_aggregate_source_evidence(finding_id, source_index)`：

- 只在`aggregate_research`模式可用；普通workspace拒绝。
- 只读取当前冻结finding里的一个结构化来源事实；不能读取任意本地文件。
- 明确返回`fresh_network_read=false`、`full_text_read=false`和
  `empirically_validated_on_our_data=false`。
- `record_research`只接受成功的`read_public_source`或
  `read_aggregate_source_evidence` record；search metadata、inspect record和失败record仍拒绝。
- 该接口不能清QA、准入source、profile raw data、fit、训练、打开Dev/Final或证明阈值。

live-timing adapter同时给四条来源增加明确的`evidence_type`。因此新workspace可以使用这条接口；
旧`v1.6.5` workspace不会被原地升级。

## 验证

已完成：

- 专项14/14：aggregate mode成功、普通mode拒绝、非runner类型拒绝、来源边界和adapter类型检查。
- Harness 268/268。
- sports 59/59。
- NFL experiment 19/19。
- aggregate sports adapter 7/7。

随后已经完成：真实Codex canary、`dsh-v1.6.6` tag/release和一条fresh paid controller会话。
该会话能直接读取6段Sportradar官方页面，所以没有调用aggregate bridge；因此bridge已经过unit test
和真实Codex scripted canary，但还没有paid-controller路径验证。代码与canary只说明接口按合同工作，
不说明下一方案有效。
