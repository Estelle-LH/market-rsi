# 2024 NFL：多一年数据到底能不能用

日期：2026-09-16。状态：**Train-only 数据来源检查**，不是新一轮模型训练，也不是分数提升。

## 为什么做

上一轮只有2025赛季163场可用于市场反应训练。继续在同一批比赛上调模型，无法回答“数据太少”
是不是瓶颈。这里先验证更早一季的比赛目录、主客队映射、成交和逐play时间是否真的能接上。
没有打开2025 Route-Dev/Final，也没有用比赛结果、成交量或模型分数挑样本。

## 每一步发生了什么

1. 官方Gamma API里没有`nfl-2024`这个series slug；较早比赛放在通用`nfl` series中。
   新目录工具按2024-09-01至2025-02-15的赛季窗口、series ID、closed标志，读取3页原始响应，
   保存请求、字节数和SHA256。得到285个比赛形状的event，全部缺`gameId`。目录SHA256：
   `19f51b40871f851be113332c0aca16dc45b9a0afcc1b46a1035d5a173824a067`。
2. 第一版严格映射把slug两队顺序都当作“客-主”，只匹配216场。查看失败记录后发现这不是
   真实缺赛：早期一些slug是“主-客”。第二版允许两种方向，但只有独立nflverse比赛日程能唯一
   确认时才接受，得到270场。剩余失败揭出`LAS→LV`、`WSH→WAS`的旧缩写；显式别名和正反测试
   后最终得到**284/285场候选**，222场slug为客-主、62场为主-客。唯一剩余事件缺合格的双边
   moneyline；没有硬凑、没有用赛果猜方向。最终映射SHA256：
   `a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b`。
3. 在看成交前先按开始时间选择最早一场作机械性canary。它有1,037笔查询窗口内成交、367个不同
   成交价；这只证明一个市场的接口可用。
4. 再把最早一场排除，对其余候选按开始时间排序，从12个等长位置区间各取中点一场。
   12/12场均有历史成交，合计18,699笔，每场220–3,880笔，中位数1,376笔；无自动重试、
   无20,000行截断。预选清单SHA256：
   `0e83ce7f1ad0907ce062c911458f9193749e584bf55a87881ecdfc0604416956`；
   12场运行manifest SHA256：
   `44be88eeafd316cd2792810a754b54ff7b5eeee158d5acad638608f2c409c89b`。
5. 本机已有2024 nflverse PBP原件，SHA256
   `23370d5d10f8104d80d46a1fc5e61f4f6f5a3263fe96fe2dd629913cfcb08c06`。
   12场共2,087行PBP，其中2,027行带play type；这2,027行全部有可解析的`time_of_day`。
   每场第一条play在赛前目录时间后19–227秒，最后一条在约2.9–3.5小时后，未见明显整小时
   时区错位。按旧实验同样的“play前5分钟内须有成交，play后必须有**新**成交”口径，
   30/60/300秒分别有1,099/1,400/1,885条可形成标签，约54.2%/69.1%/93.0%。
   60秒单场覆盖从27.1%到97.0%，差异很大。审计per-game SHA256：
   `ac3c8a477b14f949c8d7516a9f51d67065090f2402ea9364f50481b549714a20`。
6. 发布后额外做了只读方向核对：284个候选市场的两个`outcomes`名称均能唯一对应日程中的两队，
   顺序为222场客-主、62场主-客；12场screen的18,699笔安全成交中，`asset`到`outcome`的对应
   与目录中token数组逐笔一致，0条不符。这增强了来源映射证据，但尚未把全赛季成交/标签纳入训练。

## 这说明什么，不说明什么

**能说：**2024不是“没市场数据”。已经找到284场可严格映射的市场候选，一组事前按时间抽取的
12场都能拿到历史成交；PBP绝对时间与成交在机械上可以对齐。扩大Train数据有实际可行性。

**不能说：**284场已经进训练、整个赛季都有足够的60秒标签、模型会变好、行情能实时领先、
或可以赚钱。12场是来源screen，不是独立性能测试。2024 60秒覆盖69.1%，低于2025整季
Train的91.34%；两者的比赛选择和PBP供应商时钟并不完全相同，不能把差额直接归因于
“2024市场更薄”，也不能直接拼成一个同质样本。`time_of_day`是历史play时间，不是当年的
provider-publish或本机receive时间。钱花费：本次Tinker **$0**；没有购买数据、没有打开Dev/Final。

## Harness学到了什么，下一步怎么做

- **数据协议不能假设跨年不变。** 2024的`gameId`缺失、slug队伍顺序混用、球队缩写变化。
  新代码把方向绑到独立赛程，模棱两可就拒绝；三个中间版本和失败列表保留，没有改写旧记录。
- **只看比赛数会高估可用训练量。** 12场都有成交，但60秒标签覆盖差别巨大。下一轮先让
  controller看到聚合的逐周/逐场覆盖与费用估计，再在opened Train上事前选一个研究问题、
  horizon和纳入规则；不能看到Dev分数后改窗口或只保留好看的比赛。
- **下一个真正的实验应一次只改一层。** 先固定旧feature、trainer和评估，只改加入多少2024
  Train比赛，做按整场/日期分组的学习曲线；然后才独立测新算法。2024与2025的play时间语义
  还需桥接审计，未经确认不能把跨年MSE变化归因于“更多数据”。
- **现在先不全量抓284场。** 先冻结2024 cohort admission与磁盘/备份计划，验证outcome方向及
  时间字段，再决定是60秒低覆盖训练、较长horizon，还是分层/加权。这里不代controller选目标。

## 来源与可复核物

2026-09-16查询并阅读：

- `site:docs.polymarket.com gamma events keyset series_id start_date_min`：
  [Polymarket keyset events](https://docs.polymarket.com/api-reference/events/list-events-keyset-pagination)
  的cursor、series/date过滤和分页参数。页面描述接口能力；**285是本次实测**，不是文档承诺。
- `site:docs.polymarket.com data api get trades market start end takerOnly limit offset`：
  [Polymarket Data API trades](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets)
  的market、limit/offset与trade字段。API返回的raw响应仅在被Git忽略的本机artifact中；安全CSV
  不含wallet字段。公开可读不等于已核实所有后续再分发/商业使用许可。
- `site:nflfastr.com time_of_day play by play`：
  [nflfastR字段说明](https://nflfastr.com/articles/field_descriptions.html)及
  [nflverse数据更新说明](https://github.com/nflverse/nflverse-data/blob/main/README.Rmd)。
  前者将`time_of_day`描述为play开始的时间，后者说明raw JSON通常比赛后1–2小时才出现。
  因此它适合历史对齐，不是实时接收证据。

实现、单测和结果分别在：

- `sports_event_research/fetch_polymarket_2024_nfl_catalog.py`
- `sports_event_research/map_polymarket_2024_nfl_catalog.py`
- `sports_event_research/fetch_polymarket_2024_trade_canary.py`
- `sports_event_research/fetch_polymarket_2024_trade_screen.py`
- `sports_event_research/audit_2024_pbp_trade_support.py`
- `artifacts/pm_2024_nfl_catalog_20260916_01/`
- `artifacts/pm_2024_nfl_mapping_20260916_01`、`_02`、`_03/`（保留修复轨迹）
- `artifacts/pm_2024_nfl_trade_canary_20260916_01/`
- `artifacts/pm_2024_nfl_trade_screen_20260916_01/`
- `artifacts/pm_2024_nfl_timing_support_20260916_01`、`_02/`

新增专项测试19/19、sports-event整体91/91、Harness 274/274、NFL experiments 19/19通过。
免费exact-source Codex canary通过；代码发布为`dsh-v1.6.11`，commit
`c8c4763860caac66a0312f0a7338c630475b8435`，release SHA256
`f18a190758aefc37f278d9e03a74bc5d51649c558a98516c7d813354ac8cbed6`。
发布只证明代码/来源检查可复现；尚未开始新的模型实验，不能把source screen写成正式RSI提升。

## 同次采集安全检查

Linode `173.255.231.4`的ESPN采集进程仍运行，2026-09-16 14:32 UTC的本日live文件还在更新；
NFL hourly finalizer运行，反复日志中的旧manifest是幂等返回，不是重复压缩。根盘157GB、
只剩约1.84GB（99%）；`/opt/d10/raw/pbp`仅约228KB，主要占用在别的原始数据。PBP的S3上传
timer处于disabled，专用凭据文件不存在，故不能声称已有异地备份。已将当前6个归档文件复制到
本机被Git忽略的`artifacts/market_rsi_live_pbp_backup_20260916/pbp/`，逐文件SHA256与Linode一致；
原件和服务未改动。这是临时第二份，不是S3回执；不扩大Linode采集量、不删除旧数据。
