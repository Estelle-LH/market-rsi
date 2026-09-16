# 单文件检查：先得到真实的数据结果

本次controller正常退出，8次回复计量$1.336091760，没有未返回调用。第一份方案已登记，
但没有训练。原$200账本计量累计$37.571008832；含未确定费用上限后为$42.429589712，
另有$2.30预留，可用$155.270410288。计量不是供应商账单，预留不是消费。

## 这一步做什么

Controller选了已打开诊断日期中的一个文件：Linode `173.255.231.4` 上
`/opt/d10/raw/data/polymarket/polymarket-20260908T12.jsonl.zst`，清单大小13,166,507字节。
只对这个文件做一次读取，边算压缩文件hash边解压，统计消息、报价和时间戳。
不打开其他文件、不补下载、不训练；只返回汇总，不导出原始价格或token ID。

这是执行方的**部分只读复核**，不是把controller的整份请求判为可执行：记录0009的
内嵌JSON在outputs列表结尾格式错误，还把未来label写成只能使用decision之前的数据。
原文保留，不自动修复。因此本次不计算feature、label或可训练行，也不声称完成了它
要求的全部时间窗口检查。明确写出的单文件地址和资源上限独立核对后使用。

最多读取13,166,507压缩字节、2GiB解压字节，墙钟600秒，父进程和解压器地址空间上限
合计1GiB。数据类型、大小、读取中变化、解压/解析或资源限制出错则保留部分结果并停，
不自动重跑。临时进程退出必须有记录。一次成功只绑定此刻这一个副本，不证明原始
采集链、全日覆盖、静默期间没断线，或其他121个文件内容完整。

## 方法和文献记录

问题：过去一直在讨论时间窗口，但新文件连内容hash和source时钟统计都还没有。
本次只补原始数据层，不更换目标、特征或训练方法。

复用已研究的`quote_source/reconstruct.py`与`audit_tools/population_quote_profile.py`，
不改直接BBO和重建depth的区别，不删除零变化报价。原研究见
[报价来源记录](LITERATURE_TO_HARNESS_2026-09-10.md)。新增统计只数source_ms的相邻间隔、
回退和连续同时间戳段；原population统计用capture_ms，两者分别标注。连续段不是
已验证的决策组，也不把原始记录数当成独立训练样本数。

2026-09-13执行方补查（不是controller的阅读记录）：
查询`site.docs.polymarket.com market channel book timestamp milliseconds best_bid_ask price_change`。
只使用Polymarket官方页面，读取
[Market WebSocket](https://docs.polymarket.com/api-reference/wss/market)的book、price_change、
last_trade_price、best_bid_ask示例及heartbeat部分，以及
[Get order book](https://docs.polymarket.com/api-reference/market-data/get-order-book)的响应字段。
前者区分成交与报价消息；后者把timestamp描述为快照时间。当前示例本身不能证明我们
归档记录的单位、排序或本地接收时间，heartbeat协议也不能证明历史采集不中断。
所以只测数值形状/间隔/回退，不给时钟语义或断线分类通过。没有采用新的金融模型。

替代做法是先解析完整执行请求或扫描全部日期。前者的语义仍需controller澄清；后者
成本更高且不解决单文件未知。本次只读部分可以独立完成，不替它决定未来label。

## 验证和结果

代码：`audit_tools/single_object_stream.py`、`source_clock_profile.py`和独立runner。
已有transport本机6测试及Linode合成canary通过，实际市场文件尚未因此被读取。
新增clock计数/范围核对与旧adapter回归合计54项测试通过。服务器完整流程canary也通过：
只读3条临时合成报价，hash、零变化计数、解压子进程和临时目录清理均核对成功。
凭证`artifacts/single-object-complete-canary-20260913-01/canary.json`，内部指纹
`2e2f3b601352dac26b4f6b7d68ebaeac264dc4b6e33d1dd35af18efa433a7670`。
这些是工程测试；真实文件结果尚待执行，不是预测实验成功。

Controller原始记录：`artifacts/temporal-executable-controller-20260913-01/`。
费用与完整性复核：`artifacts/temporal-executable-controller-audit-20260913-01/audit.json`。

## 实际结果：已完成，不是计划

代码先在`df4f2b1`发布为`pm-single-object-audit-v0.1.0`，再运行真实文件检查。
37.23秒完成，父进程峰值约39.3MiB；读一次，文件读取前后未变。解压器、读取线程、SSH
均正常退出，远端PID1448514已不存在，锁已释放。没有新Tinker/E2B调用。

| 检查 | 实测结果 |
|---|---|
| 压缩文件 / 解压内容 | 13,166,507 / 100,621,569字节 |
| 原始记录 / 拆出的报价记录 | 151,802 / 298,068 |
| token / market | 1,230 / 615，不是独立训练样本数 |
| 相邻有效中间价对 | 295,778，其中266,989不变（90.27%）、28,789变化（9.73%） |
| 存在中间价变化的token | 427；另有720个token有有效相邻报价但未见中间价变化 |
| source_ms相邻回退 / 低于此前最大值的报价 | 120对 / 131条，两个统计口径不同 |
| 相邻source_ms相同 | 41,556 / 296,838对，14.00% |
| 直接BBO / 重建depth不一致 | 893 / 267,192条可比较报价，0.334% |
| 直接BBO买价高于卖价 | 本文件未观察到；不代表整个数据源通过 |

这个文件名是9月8日12点，但来源时间戳最早为8月27日00:36:53.385 UTC。
450个token至少有一个来源时间早于文件小时；204个token的所有来源时间都早于该小时。
这可能涉及旧状态快照、延迟消息或字段含义，目前不能确定。没有另开8月27日文件；
也不能直接用这些数推断断线、污染或清除规则。

我们学到的是：记录很多不等于可训练样本多；时间戳看起来像毫秒，也不等于就是
预测时可获得信息的时间。中间价不变的报价先保留，不能按未来是否变动来选样本。
这次90.27%是相邻报价统计，不是“一分钟目标90.27%为零”。

真实报告：`artifacts/single-object-source-audit-20260913-01/report.json`，内部hash
`48184528d0239cd0b7df5e3b0e56a1d1eb6f644baaa200117bdde0f528084e97`。
压缩内容hash：`353c3cb29bd277e84a4f614d84ac81f030df36090c430c33fb90891f8436b7f0`。
供后续controller读取的独立发现：
`artifacts/single-object-source-review-20260913-01/findings.json`，内部hash
`aadf77c63017acd1cfd137516588b81214bc50e29a3528b3e641c35aec994e36`。
新增5项汇总复核测试通过，总计59项相关测试通过；汇总没有再次读取原始数据。

仍未完成：时间戳含义核实、controller执行请求中的未来label矛盾、事件到训练样本的
转换及相关数据检查。因此还没有新训练或MSE。当前文件内容核对完成，不等于整份
capability已执行；旧QA、旧manifest、旧结果均不改写。不能继续付费重复同一份defer。

23:39UTC收尾复核：E2B当前sandbox清单为0；账本仍保留23条历史dispatched记录，合计
$2.30预留。这是未结清的历史记账，不是23个正在运行的sandbox，也不是已消费$2.30。
没有凭当前清单释放预留或改写旧费用；清理复核存于真实run的`cleanup-check.json`。
