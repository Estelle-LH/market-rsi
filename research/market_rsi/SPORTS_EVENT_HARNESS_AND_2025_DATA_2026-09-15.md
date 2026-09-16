# 体育逐事件 Harness 与 2025 NFL 数据盘点

日期：2026-09-15

## 这次解决什么

当前 Market RSI Harness 主要处理固定时间格上的行情。NFL 研究真正需要的是把每个 play、
比赛状态、市场报价、成交和订单生命周期按同一场比赛、同一方向和可用时间拼起来。如果不先
补这层，更多模型或更多轮只会在很短、很平的价格序列上反复拟合。

本次改Harness、盘点来源，并只对公开Polymarket Train数据做有边界的catalog、trade和play对齐。
先做12场canary，再扩到完整163场Train。不启动训练，不打开Dev/Final，不调用付费模型，也不
下载Kalshi行情。

## 从 Prediction Markets / NFL Kalshi 项目复用的规则

实际阅读了以下本机材料：

- `prediction-market-research/docs/NFL_KALSHI_ROADMAP.md`，SHA256
  `4f9719caf4756b1d067959c2a4de141c93848a45f3658256e5bdda5de7d24611`；
- `prediction-market-research/docs/NFL_PBP_DATA_STATUS_2026-09-15.md`，SHA256
  `a9ff82563ae00940f1827c28631e38284a54e4f5724c5b0389c53679128aa9aa`；
- `prediction-market-research/docs/DATA_CONTRACT.md`；
- `prediction-market-research/docs/VENUE_RACE_MODEL.md`；
- `prediction-market-research/docs/ONSITE_SIGNAL_PILOT.md`；
- `prediction-market-research/docs/NFL_Market_Making_Research_Strategy_Spec.md`的数据、
  timestamp、event study和chronological evaluation部分；
- `prediction-market-research/docs/NFL_CFB_INFORMATION_ALPHA_HANDOFF_2026-09-15.md`
  中的可用时间、映射和实验规则部分。

落实进 Harness 的规则：

1. 原始数据、特征、预测、可执行目标、P&L分层，不能跨层替代证据。
2. 统一映射必须包含game、home/away、market/outcome方向和结算规则；保留vendor原ID。
3. PBP至少保留event/play ID、game clock、score、possession/down-distance、事件类型和
   correction/overturn状态。
4. 分开保存event/source time、provider publish time、local receive time、exchange time、
   order send/ack、fill和cancel ack。文件落盘时间不能冒充事件或到达时间。
5. 历史PBP可以训练state model，但历史回填没有当时的local receive time，不能证明实时领先。
6. 市场price/candle/trade可以做描述性反应；没有历史L2时不能重建queue/cancel。
7. 显示深度不是fill；没有账户ack/fill/cancel和费用，不能报告可执行P&L。
8. Train/Dev/Final按整场game和时间切分；同一场的plays不能随机分到多个集合。
9. 至少20场未打开Final才允许进入正式promotion判断；重复play不是独立样本。
10. 数据授权、原始manifest、hash、缺口、重复、纠错和timestamp aliasing都是先决检查。

代码实现为`data_scientist_harness/sports_event_contract.py`及controller工具
`probe_sports_event_contract`。它分别报告`state_prediction`、`market_response`、
`lead_lag`、`executable_pnl`四层是否满足软件规则。它不读取或自动认证真实来源，也不放行训练。

## 2025 NFL play-by-play：已经找到并已在本机

### nflverse

- 文件：`data/raw/nflverse/nfl_pbp/play_by_play_2025.csv.gz`；
- 285场，48,771行，372列；比赛日期2025-09-04至2026-02-08；
- 文件SHA256：`2f135887790a013fd004e609e37096bb4816d5cc80b9f19122e1bad478961978`；
- manifest SHA256：`8c16b2ada2117a794aa6c6176c16170b25d3a507596afad626149a687d663c6c`；
- 用途：历史state/fair-value建模；
- 限制：没有我们当时的receive timestamp，不能做feed latency或venue race。

### Sportradar

- 本机目录：`data/raw/sportradar/nfl/2025/`；
- PRE 49场、REG 272场、PST 13场，共334场、52,884个plays；
- 完整性检查：0 missing、0 duplicate game ID、0 parse/hash/partial issue、0 zero-play game；
- manifest SHA256：`2a00fc6b507b77e2c52073b913b8ad1bbc6c49a7188f0612cc7b950dd98edcbf`；
- validation SHA256：`582a157e9b0490f6f5626216cf61ccf0722f02815699d5a8ffbc47de8210e748`；
- play含`id`、`sequence`、`clock`、`wall_clock`、`created_at`、`updated_at`、比分、
  possession/down/location、penalty/no-play和review文字；
- 用途：更丰富的历史state model和事件taxonomy；
- 限制：这是后来回填的历史响应，`wall_clock/created_at`不能替代我们当时的local receive time。

因此，“去年play-by-play在哪里”已经解决。新的瓶颈是去年市场数据和逐场映射。

## 2025 prediction-market 数据：找到什么，仍缺什么

Prediction Markets项目已经通过Polymarket Gamma Events API识别：

- `nfl-2025`共253个唯一game events；
- 240场常规赛、13场季后赛；
- 汇总成交额约`$1.082B`；
- 现有汇总SHA256：`1f7babe68d9ced8ee8a07a9cf097d72601273ce37611d797dca37103e34e2da8`。

这证明2025 Polymarket NFL市场目录存在，但当前仓库只保留聚合结果，没有保存253场的完整
event/market/token原始清单，也没有逐场price history、trades或历史L2 manifest。因此现在能说
“市场存在且规模可观”，还不能说“已经有可训练的PBP×market panel”。

Kalshi官方历史API提供markets、trades和1/60/1440分钟candlesticks，但不是完整历史L2。
当前本机NFL Kalshi项目只有少量2026 L2/实时case，不是2025完整赛季。现有Predexon adapter
曾成功取得Kalshi历史L2样本。进一步核对本机Predexon历史screen后，免费目录中的NFL只覆盖
2025赛季季后赛（公历2026年1–2月）：目录有80个NFL prop候选，对6个代表市场做过免费
L2/trades验证，但多数样本很薄。这不能替代2025常规赛历史。更广的历史覆盖和研究使用权仍需
vendor确认。

## 实际取得的Polymarket数据

公开`nfl-2025` catalog已保存3页原始响应，共285个events、253个带game ID的比赛和10,964个
markets。253场全部映射到canonical game：Train 163、Route-Dev 50、sealed Final 40。
Final这里只映射目录，没有打开价格、成交或结果。

单场price-history canary每个outcome只有10个点、5个不同价格，不够逐play学习。相同比赛的
public trade tape有2,546笔记录，因此后续使用trade tape而不是稀疏price-history。

随后按时间均匀选择12场Train，不看价格、成交量、比分或结果。共取得60,189笔窗口内成交，
对齐1,947个play：30秒覆盖95.69%，60秒覆盖99.49%，300秒覆盖100%。标签必须来自play后
真实发生的新成交，不能沿用play前价格制造零变化。所有12场都未触及
20,000行截断，最差单场60秒覆盖97.14%。这只证明数据链可用，不是模型成绩。

同一套规则随后扩到全部163场Train，共480,748笔窗口内成交、25,957个play。30/60/300秒
标签覆盖分别为80.27%/91.34%/99.10%，60秒平均绝对变化为2.71个概率百分点；0自动重试，
0截断。小canary的覆盖明显高于整季，因此它只用于工程验收，不能代表正式样本难度。

第一次全量对齐在156场后遇到`Rams`/`LAR`的provider命名差异而停止。旧输出已标成不可用于
正式面板，没有续跑。修复只加入显式NFL球队名等价表，并用正反测试证明主客队和outcome方向；
之后使用新ID从第1场重跑，163/163完成。Route-Dev和Final仍未打开。

详细实验设计见[下一版self-evolution设计](SPORTS_SELF_EVOLUTION_DESIGN_2026-09-15.md)。

## 外部来源研究记录

访问日期均为2026-09-15。

| 查询/来源 | 实际阅读 | 结论 | 转移限制 |
|---|---|---|---|
| `nflverse 2025 play by play parquet`；[nflverse PBP release](https://github.com/nflverse/nflverse-data/releases/tag/pbp) | release说明和PBP资产说明 | 官方release提供play-by-play，项目本机manifest进一步验证2025文件 | 社区整理数据；没有本地实时receive time |
| `Sportradar NFL API play-by-play official`；[Game Play-by-Play](https://developer.sportradar.com/football/reference/nfl-play-by-play) | endpoint、live timeline、possession/location与统计说明 | 适合PBP状态和事件结构；本机已有2025完整回填 | 历史回填不测当时feed latency；生产授权另算 |
| [Polymarket market-data overview](https://docs.polymarket.com/market-data/overview) | event→market→outcome token ID工作流和价格/盘口入口 | 必须保存event、market、token和outcome方向后才能抓价格或盘口 | 当前历史price/trade不等于历史完整L2；reuse条款仍需单独确认 |
| [Polymarket batch price history](https://docs.polymarket.com/api-reference/markets/get-batch-prices-history) | token/time range/interval/fidelity参数 | 可以做一个有边界的2025逐场price-history canary | 分钟价格不能恢复queue、cancel或可执行depth |
| [Kalshi historical data](https://docs.kalshi.com/getting_started/historical_data)与[candlesticks](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks) | historical/live cutoff、markets/trades/candles、1/60/1440分钟字段 | 技术上能回填2025 market metadata、trades和bid/ask/trade candles | 不是历史full-depth replay |
| [Kalshi Developer Agreement v1.1](https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf) | 第3节API使用与存储限制 | API仅限会员自己的Kalshi交易；研究存储需要事先书面授权 | 因此本次没有直接批量下载Kalshi 2025数据 |

## 后续数据与实验顺序

1. **已完成：**冻结2025 NFL `game_master`并记录Sportradar/nflverse映射。
2. **已完成：**恢复253场原始event/market/token清单并完成Train-only canary。
3. **已完成：**扩到163场Train，生成逐play描述性market-response面板。
4. **已完成：**在Train内部做zero-change和四种现有trainer的同数据滚动对照。Random Forest
   相对zero-change的每场等权MSE低4.06%，Ridge/Elastic Net低约3.7%；没有打开Dev/Final。
   详细证据见`NFL_TRAIN_METHOD_SCREEN_2026-09-15.md`。
5. **已完成开发版：**在20,836个共同Train play上做按比赛聚类的30/60/300秒horizon response。
   主客队得分反应从30秒扩大到60秒，之后大致持平；只作描述性解释。详见
   `NFL_TRAIN_LOCAL_PROJECTION_2026-09-15.md`。
6. 正式Controller实验才逐块打开Route-Dev；设计结束后只打开一次Final。
7. Kalshi只走两条合法路径：取得Kalshi书面研究授权，或使用有明确研究许可且覆盖2025 NFL的
   vendor数据。未解决授权前不从官方API批量落盘。
8. 如果目标升级为queue/cancel/fill研究，分钟价格不够，必须另外取得历史L2和账户执行证据。

## 当前判断

比赛状态侧已经有2021–2025共1,424场、247,284个play行。市场侧163场Train已经形成480,748
笔成交与25,957个play的完整面板。Train内部的第一轮方法检查显示简单模型有约2.0%–4.1%
MSE改善，但这还不是独立Dev或正式成绩。Kalshi仍需书面授权或vendor coverage。Harness已把
证据层和方法library写进代码，后续controller不能把历史PBP、市场聚合量、trade print或显示
深度直接当成可执行收益证据。
