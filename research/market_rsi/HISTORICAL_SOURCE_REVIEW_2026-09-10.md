# 历史数据：目前缺什么，哪里可能补上

11:20 UTC更新：完整免费检查已通过，随后GLM完成一次真实来源审查，费用$1.11。
最终要求补查资料，还没有有效的新来源提案。工具格式说明不全也是本轮发现的问题。
[本轮结果、问题和后续动作](SOURCE_REVIEW_FOLLOWUP_2026-09-10.md)。下文保留早期记录。

9 月 10 日。这里只核对公开说明和文件目录，没有启动下载、训练或测试，也没有替 GLM 选数据源。

10:55 UTC：新的数据审查工具接口已写好，23项测试和真实工具子进程检查通过。它能读
原研究记录、比较来源、按已核对的文件大小提出方案；不能直接下载或测试。还需接入
完整Codex调用并做免费检查。本轮没有模型费用，也没有选定新来源。

## 现在的问题

当前模型需要新的、没看过的数据来验证。原来的 OpenMarket 已停止采集，并固定在归档版本；网页显示的提交与我们使用的 `74502466d1a7cef56395bfd8d0b465fbebc849cf` 相同。因此不能继续指望这个来源更新。它的快照备份日期延伸到 7 月，不代表行情事件也记录到了 7 月。[数据说明](https://huggingface.co/datasets/gregyoung14/openmarket-btc-polymarket/blob/main/README.md)、[提交记录](https://huggingface.co/datasets/gregyoung14/openmarket-btc-polymarket/commit/74502466d1a7cef56395bfd8d0b465fbebc849cf)。

已有文件清单没有 GLM 请求的 5 月 16 日至 6 月 30 日分区。这个结论只针对目录；没有新读原始行情来证明事件覆盖。此前填写的 100GB 只是请求上限，不是所需下载量。

## 找到的候选来源

| 来源 | 公开说明里的范围 | 还缺什么检查 |
|---|---|---|
| 当前 OpenMarket | 已归档；本地固定清单的 Polymarket 分区到 5 月 15 日 | 没有可直接执行的后续日期请求 |
| oraclemangle Canary Tape | 主文件标注 5 月 13 日至 7 月 5 日；第二采集点文件标注 6 月 3 日至 7 月 1 日 | 是否有足够完整日期、时钟与字段能否接上当前模型 |
| Joseph3222 Orderbook | 标注 2 月 22 日至 8 月 10 日；6 月 12–17 日缺失，8 月 10 日不完整 | 分钟文件约 1.2GB/日；有日内缺口和旧盘口延续，不能直接当干净数据 |

候选范围和缺口来自发布者说明，尚未通过原始文件验证。[Canary Tape](https://huggingface.co/datasets/oraclemangle/polymarket-canary-tape/blob/main/README.md)、[Orderbook](https://huggingface.co/datasets/Joseph3222/polymarket-orderbook)。

### Canary Tape 还不能直接接到旧模型

已核对公开表结构：有盘口消息、CEX 成交、市场信息和采集状态，但没有单独的 1 秒 K 线表。Polymarket 使用本地接收时间；CEX 另有交易所时间。即使可以用成交重新计算 K 线，也不能未经验证就说它和原特征完全相同。[表结构](https://huggingface.co/datasets/oraclemangle/polymarket-canary-tape/blob/main/schema.sql)。

市场信息是多次扫描的记录。以后连接时只能用当时已经可见的版本，不能把较晚更新的市场信息接到早期事件上；没有记录故障也不代表没有断流。[字段说明](https://huggingface.co/datasets/oraclemangle/polymarket-canary-tape/blob/main/DATA_DICTIONARY.md)。

这属于需要 GLM 明确提出的新数据方案，不能偷偷替换当前 t7 的验证条件。

## 文件大小已经核到具体字节

匿名查询了固定版本的根目录，收到 **1,812 字节元数据**，没有下载压缩行情文件：

- 主文件：5,986,672,592 字节，约 5.99GB。
- 第二采集点文件：3,164,694,656 字节，约 3.16GB。说明里的 2.95 数字不能直接当作十进制 GB 使用。
- 三天早期文件：149,594,653 字节；不能靠三天文件满足至少 20 个独立日期的要求。

目录里的文件 hash 与发布者的校验清单一致；这只验证了广告元数据的一致性，还没有校验原始文件。[固定版本目录接口](https://huggingface.co/api/datasets/oraclemangle/polymarket-canary-tape/tree/0f09fdb48f703d672a648c562e3f6398f45eb168?recursive=false&expand=false)、[发布者校验清单](https://huggingface.co/datasets/oraclemangle/polymarket-canary-tape/blob/main/SHA256SUMS)。

原始历史数据下载额度仍然没有余量。不能因为另一个文件不到 5GB 就再下载一次：额度是累计的，不是每份文件各算一次。这里也还没有决定必须下载哪一份。

## 接下来做什么

1. 把这份来源核对、字段差异和旧请求不可执行的原因，接入一个新的 GLM 数据审查阶段；旧阶段的输入和结果保留不改。
2. GLM 先说明需要哪些文件、字段怎样对应、哪些问题仍无法确定，以及最小获取量。没有依据就不填 100GB。
3. 等方案和下载额度具备后，先做小范围原始数据检查，再决定正式的时间划分。完整目录日期不能冒充完整交易日。

当前原模型、目标、已看过的数据不变。累计模型计量仍为 $23.484018410；本次来源研究没有新模型费用。

记录边界：打开 Joseph 的数据说明页时，网页自动展示了 2 月 22 日的少量示例行。没有导出、训练、打分或交给 GLM；该来源该日期不能再被本次研究称为完全未接触。没有打开候选后续日期的数据。

本地证据：`artifacts/historical-public-source-metadata-20260910-01/`；审查目录：`artifacts/historical-source-review-20260910-01/catalog.json`。这份目录不是 GLM 决策，也不是下载许可。
