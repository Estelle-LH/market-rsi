# NFL live timing：为什么不能直接拿历史 event clock 做实时实验

## 先说结论

30秒历史预测实验里，真正带来大部分改善的是`state_wp_delta`。但是历史数据只告诉我们一场
play大约什么时候开始，并没有证明这个状态在当时什么时候被数据商发布、什么时候被我们的
机器收到。这里如果不补上，历史MSE变好也可能无法变成实时研究结果。

Feedback Controller因此选择先查live timing。这个方向是对的，但它提出的“完整率至少90%、
p99不超过5秒”没有成功读到文献或产品说明，不能直接成为科学门槛。执行方没有照抄这个数字，
而是先检查已有真实日志、官方数据源能力和缺失字段，再把时钟规则写进Harness。

## 已有真实日志告诉了我们什么

检查对象是Prediction Markets项目已经看过的DEN–KC单场日志。输入文件SHA256：
`4d1035690ca6f1e7a1804ba66450a7fe56012e30b2def43af6c93f1f6110e458`。新审计run是
`nfl-live-timing-posthoc-denkc-20260916-02`，report SHA256：
`139af69888a37b613cd7550732dbe4788ec0e900490fe1e1de131551ea5fb162`。

- 179条记录，0条JSON错误，0条完整重复，接收时间没有倒退。
- 62条`live_delta`，对应62个不同play；全部有本机接收时间。
- 62/62有provider event-start clock；0/62有provider publish timestamp。
- 0/62同时有start/end state；0/62有win-probability字段；0/62有明确的
  correction/overturn schema。
- 所有play的event-start到本机receive描述性差值：p50 47,988ms，p90 87,154.9ms，
  p99 110,194.32ms。
- 三个得分play的同一描述性差值：37,557–58,754ms，中位数40,774ms。
- HTTP request round-trip本身很快：p50 121.893ms、p99 160.497ms。因此几十秒差值主要不是
  单次网络请求耗时；但没有publish timestamp，仍不能把差值分解成provider延迟和polling延迟。

这只能说明原始采集机械上可读，不能证明完整capture integrity、strict feed latency、market lead、
预测改善或PnL。因为这是已经看过的单场case，它也不是新的独立确认。

## 时钟必须分开

以后每条PBP和市场消息至少分开记录：

1. event-start：球场事件大约什么时候开始；
2. provider-publish：数据商什么时候创建/更新并发出记录；
3. local-receive：我们的机器什么时候收到；
4. decision：模型什么时候真正可以做决定；
5. label：事前定义的未来窗口什么时候结束。

`event-start → local-receive`只能做描述，不能冒充`provider-publish → local-receive`。PBP与市场
两边都要记录同一个本机时钟，才有资格问PBP是否领先市场。

## 60秒不是永久规则

时间窗口应该是Controller可以研究的变量，不该由人永久写死成60秒。新规则是：

- opened-Train discovery可以事前列出有限候选窗口，例如5/15/30/60秒；
- 窗口列表、选择规则和primary reward必须在看到该阶段分数前冻结；
- 看完opened Train后可以选择一个窗口进入下一份新实验；
- protected confirmation只带一个冻结窗口，不能看分后再挑最漂亮的秒数；
- 任何看分后提出的新窗口，只能进入下一轮，不能回头改写旧结论。

这给Controller探索自由，同时保留可证伪性。

## 公开来源研究

访问日期：2026-09-16。以下是`found/read`，不是我们数据上的验证。

### 查询与已读内容

- 查询：`site:developer.sportradar.com football NFL play by play API TTL 3 seconds`。
  阅读[Sportradar Game Play-by-Play](https://developer.sportradar.com/football/reference/nfl-play-by-play)
  的Update Frequency段：in-progress TTL为3秒，数据标为Realtime，建议live game每3秒请求。
- 查询：`site:developer.sportradar.com football NFL push events plays as they happen created_at updated_at wall_clock`。
  阅读[Sportradar Push Events](https://developer.sportradar.com/football/v6/reference/nfl-push-events)
  的产品说明、subscription示例和data points。Push Events称提供每个live event的实时信息；
  event/play包含`created_at`、`updated_at`与`wall_clock`，其中`wall_clock`明确是play/event entry
  开始时间。review结构也记录overturned/upheld/reversed。
- 直接阅读[Sportradar Push integration guide](https://developer.sportradar.com/football/docs/nfl-ig-push)。
  用途是理解push与REST catch-up的职责；能否访问、实际SLA和价格仍需单独验证。
- 查询：`site:docs.polymarket.com websocket market timestamp documentation`，阅读
  [Polymarket Market Channel](https://docs.polymarket.com/api-reference/wss/market)的市场消息定义。
  市场消息有provider timestamp，但我们仍必须另存本机receive time，不能只信远端时钟。
- 查询：`site:github.com/nflverse/nflverse-data play-by-play updated 1-2 hours after game`，阅读
  [nflverse-data README](https://github.com/nflverse/nflverse-data/blob/main/README.Rmd)的Play by Play
  更新说明：raw JSON通常在比赛后1–2小时出现。因此它适合历史训练/回填，不适合live lead实验。

### 可选路径

1. **ESPN polling**：免费，现有collector已运行；适合慢速归因和collector开发。现有实测缺publish
   clock与state/WP字段，不能直接支持当前最强feature的实时化。
2. **Sportradar REST**：官方说明允许in-progress每3秒拉取；比ESPN现状更有希望，仍需用本地
   receive time做prospective canary，并确认trial/production字段与授权。
3. **Sportradar Push**：最接近真正的live event stream，且有created/updated/review字段；可能需要
   Realtime产品授权。不能把文档能力当成我们账户已经具备。
4. **nflverse**：适合多年历史训练和重建WP，不适合live决策时钟。

当前选择不是立刻购买或宣称Sportradar可用。先把prospective source canary和字段验收写清，再决定
是否申请trial/报价。简单基线仍是现有ESPN collector；新源必须在同一场、同一机器上和它并行，
比较字段完整性与本机receive timing。

## 已实现的Harness变化

`dsh-v1.6.5`加入`probe_live_timing_contract`，把四个gate分开：

- capture integrity；
- strict provider-publish-to-local-receive latency；
- PBP相对市场的lead；
- untouched cohort上的independent confirmation。

Probe只检查实验合同，不读feed、不批准数据源、不证明阈值、不跑预测。审计工具
`audit_live_pbp_capture.py`只输出聚合统计和hash，不输出比赛或play标识符。

发布验收已完成：Harness 266/266、sports 59/59、experiments 19/19、live timing专项8/8、capture
audit专项4/4通过。真实Codex canary `data-scientist-codex-canary-20260916-03`通过；0 Tinker、0
Dev/Final。精确commit为`d4ea731722cbf9a6ddd806d40ea258edf7a137da`，annotated tag为
`dsh-v1.6.5`，release SHA256为
`8546f10d12165159bcba8c33576090df19802112e50d56af7225656a66aef0a1`。

## Linode运行状态与风险

只读检查显示现有ESPN PBP service仍在运行、重启数0，部署脚本SHA256与本地sports-betting项目
一致；PBP文件本身只有约228KB，不是磁盘占用来源。整台Linode根盘约157GB、已用147GB、只剩
约2.7GB。`/opt/d10`约85GB，其中raw约63GB。PBP uploader timer没有启用，也没有专用上传凭证，
所以当前新PBP只在Linode本地，尚无可验证的异地备份回执。

这不影响已经完成的单场审计，但会威胁下一次prospective capture。不能为了省空间随意删除旧数据；
下一步应先做精确inventory和可校验备份/retention方案，再开启更多大体积采集。

## 下一份真正实验的事前验收

未来prospective live study至少要满足：

- PBP和市场各有provider timestamp与local receive timestamp；
- provider字段语义明确区分event start、created、updated；
- correction/overturn能更新，而不是把初始判罚当真值；
- 能在decision time前构造Controller选中的feature；缺失不能填成0；
- horizon grid、选择规则、reward在该阶段score前冻结；
- 同一场并行采集简单基线源和候选源；
- 至少20场的独立确认只是Harness默认下限，不是文献已经证明的样本充分性；正式数量要结合
  实际事件数、日期分布和不确定区间重新做power/sensitivity设计；
- predictive score、market response和executable PnL仍是三件事，逐层验收。

## 当前能说与不能说

能说：历史opened-Train上HGB相对RF更稳，最强信息来自`state_wp_delta`；现有ESPN实时日志机械上
采到了62条live play，但缺少实时化该feature和测strict latency需要的字段。

不能说：这个feature已经可实时交易；5秒或60秒已经是正确窗口；单场DEN–KC支持market lead；
Sportradar一定足够快；或历史MSE改善已经能赚钱。
