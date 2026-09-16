# 数据工作总览：2026-09-09 至 2026-09-10

这两天做的工作都在 `research/market_rsi/`。这份页面是入口；详细数字和原始回执在下面的日报和 `artifacts/` 目录里。

## 一句话总结

最新检查发现：新Vantage档案虽然有39.3GB，但要求窗口内只有6个日期有记录，合计617个
有行情的分钟，达不到原方案的20个完整日期。已下载并备份，暂不能用于正式实验。
具体数字和处理方式：[Vantage覆盖检查](VANTAGE_COVERAGE_FINDINGS_2026-09-10.md)。

已完成的旧数据模型实验另见[七个模型的结果](HISTORICAL_MODEL_FINDINGS_2026-09-10.md)：
最好一个比不变预测好0.159%，但只用了三个反复检查的日期，不能算新的验证成绩。

## 昨天：先检查已有数据

详细记录：[`DAILY_LOG_2026-09-09.md`](DAILY_LOG_2026-09-09.md)、[`HISTORICAL_DATA_READINESS_2026-09-09.md`](HISTORICAL_DATA_READINESS_2026-09-09.md)

主要发现：

- 104,836 条记录的 token 和同一行的 market 对不上，不能直接改名字；
- 320 条报价出现买价高于卖价，原始行已保留，没有偷偷修正；
- 文件名日期不能直接当成 UTC 行情日期；
- K 线不完整，还有延迟补录；
- 全局 `id` 重复不一定是重复行情，不能按 `id` 全局去重；
- 有些日期只有很短的活动时间，不能把文件数量当成完整交易日；
- 5 月 14 日约 98.66% 的相邻最优报价不变，但很多行仍然有盘口更新，不能简单删掉；
- OpenMarket 只做了数据路径 canary，不能当成正式 Train/Dev/Test。

这些结果说明：先把数据时间和可用性弄清楚，再决定目标和模型。

## 今天：核对新历史来源并完成落盘

详细记录：[`HISTORICAL_SOURCE_REVIEW_2026-09-10.md`](HISTORICAL_SOURCE_REVIEW_2026-09-10.md)、[`SOURCE_ACQUISITION_REVIEW_2026-09-10.md`](SOURCE_ACQUISITION_REVIEW_2026-09-10.md)、[`DAILY_LOG_2026-09-10.md`](DAILY_LOG_2026-09-10.md)

本轮数据源只选 **Polymarket**：

- 不是 Kalshi；
- 不是 SportsRadar；
- Kalshi 的原始档案仍单独保存在 Linode，但不进入这轮实验。

GLM controller 选定的 Polymarket Canary Tape revision 是
`0f09fdb48f703d672a648c562e3f6398f45eb168`。其中已落盘的是 Vantage 第二采集点：

- 压缩文件：3,164,694,656 字节；
- 解压 SQLite：39,315,099,648 字节；
- 压缩和解压 SHA-256 都已核对；
- 原文件已保留在 Linode，并备份到私有 S3；
- 没有把原始行情、密钥或运行产物上传到 GitHub。

另一份 5.99GB 主档仍未下载，因为当前 15GB 累计额度剩余不够；没有擅自扩大额度、买存储或删除已有数据。

## 今天已做的 SQLite 检查

详细证据：[`artifacts/historical-vantage-remote-stage-20260910-01/`](artifacts/historical-vantage-remote-stage-20260910-01/)、[`artifacts/historical-vantage-transfer-audit-20260910-01/audit.json`](artifacts/historical-vantage-transfer-audit-20260910-01/audit.json)、[`DATA_BACKUP_2026-09-10.md`](DATA_BACKUP_2026-09-10.md)

数据库 schema 中确认有：

- Polymarket 事件：`pm_events`；
- 采集心跳：`heartbeats`；
- 记录的断流：`gaps`；
- 市场扫描：`markets`；
- CEX 成交：`cex_trades`。

随后做了两次有 30 秒硬上限的只读检查，没有读 payload、价格、标签或模型：

- `pm_events` 前缀样本：1,000 行、10 个订阅、6 种事件；
- `heartbeats` 前缀样本：1,000 行、24 个订阅、4 个来源；
- `gaps` 前缀样本：0 行；
- 2026-06-03 UTC 窗口的 capped sample 也已读完；
- 主 SQLite 文件大小和时间没有变化。

一个旧的无界 SQLite 统计进程跑了 11 分钟并生成 sidecar。它已被停止，sidecar 原样隔离保留；之后所有读取都强制使用 immutable 和 30 秒上限。这个问题属于读取基础设施，不是数据质量结论。

## 现在什么是真的

已经确认：

- 数据来源是 Polymarket；
- 新 Vantage 档案已经完整落盘并有私有备份；
- schema 可以读到，确实有事件和心跳；`gaps`表存在但没有记录，不能说明没有断流；
- 新档案在要求窗口内仅6个日期有数据，单独不能满足原方案；
- 旧数据存在时间和覆盖问题，不能直接拿来训练；
- 读取必须有时间上限，不能跑无界全表统计。

还没有确认：

- 每个市场的盘口状态能否按时间正确重放；
- 哪些日期可以成为正式 Train/Dev；
- 目标和模型在这份新数据上是否会提高。

## 下一步

1. 把真实覆盖缺口和剩余额度交回GLM，修订数据方案；未检查的5.99GB主档仍保留；
2. 新方案先取得逐日覆盖、字段和时钟证据，不能只看文件日期和大小；
3. 如果需要改变已选目标或特征，由controller明确提出并记录，不能悄悄修改；
4. 数据条件满足、目标与时间切分冻结后，才开始新的正式实验。

在第 1–3 步完成前，任何数字都只能叫 diagnostic，不能叫正式 RSI 结果。
