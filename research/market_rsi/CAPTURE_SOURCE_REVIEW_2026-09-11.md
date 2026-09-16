# 现有CSV能不能直接训练：来源核查

这是执行方补查，不算GLM06读过的文献，也没有改06的决定。访问日期2026-09-11。
检索方式是从官方首页点击实际链接，不是搜索摘要或猜URL。没有调用市场交易API。

## 官方文档说什么

- [Prices & Orderbook](https://docs.polymarket.com/concepts/prices-orderbook)，读取价格和订单簿部分：
  报价0–1是每份合约的美元数，0.25即25美分，隐含概率为25%；不是0.25美分。
  网页展示价格还可能在价差大时切换到最后成交价，不能默认与我们CSV算出的mid相同。
- [Prices and Order Books](https://docs.polymarket.com/market-data/prices-order-books)，
  读取outcome token及订单簿schema、API例子（到best-market-price段）：condition/market
  与交易token是不同字段，bid/ask price与size也是不同字段。文档不证明我们的历史CSV映射正确。
- [Markets & Events](https://docs.polymarket.com/concepts/markets-events)，读取身份与事件结构：
  一个事件可能包含多个市场，一个市场又有不同outcome token。不能把这些ID混成同一个层级。
- [Real-Time Data](https://docs.polymarket.com/market-data/realtime-data)，读取market stream
  的book、price_change、last_trade_price、tick_size_change类型及例子：流中不只有price_change。
  还没据此证明历史档实际收到了哪些类型。

以上是当前官方格式说明；真实使用仍需绑定历史原件、采集时钟、转换代码和字段对照。
本次未选择预测目标、持有期、模型或交易策略。

## 生产转换代码里看到的风险

只读`/opt/d10/bin/etl.py`，SHA256：
`584c7682d9d6ed331bc192da31e75890b7fc4158f4082137f2e2c028b6b1bf8b`。
读取iso/emit_tob/write_depth/run_polymarket及其直接上下文，没有修改或运行完整ETL。

Polymarket路径只用REST快照初始化book，处理price_change和last_trade_price；
其他WebSocket类型跳过。REST快照本身不发报价行，任一侧空时也不发，只有最优价/量
变化时发。这意味着完整有效状态未必能从CSV还原；若下游一直向前填，可能把已失效的
报价继续使用。这是代码推导的风险，不是已测得的历史错误比例。

新增一个只用合成帧的检查，直接抽取已审阅源码的4个函数，在内存里跑四种情况：
只有REST快照、WS book后接delta、删除最后一个ask、REST重新锚定。它不读取真实行情，
不运行ETL main、不调HTTP、不写原始目录。记录预期行为与实际发出的行数。
结果另存`artifacts/capture-etl-semantics-canary-20260911-01/report.json`；执行前不称通过。

替代处理：直接无限向前填最简单，但会掩盖无效状态，不能先采用。更有依据的后续方案
是从固定原始消息重放，显式保存book有效/无效、快照与接收时间，再做未来修改不影响
过去特征的检查；这需要controller后续决定和真实数据验证，当前没有替它启用。

## 合成检查及第一批真实统计

01的四个合成情形均复现，回执hash：
`2f1402f8e8e11af7a535f573ce6ddb376bf3ff744ed95eeb175e82cb6a707cf9`。
这证明当前代码的行为，不证明旧档受影响比例。

逐日真实审计读完8/21、22后，分别发现72,722/6,945,820和124,195/5,537,879条
Polymarket报价行中买一高于卖一；不自动删除，也不据此声称真实市场可套利。
这是同一来源的诊断观察，不是Dev结果。8/22仅219个有记录分钟，不是完整24小时覆盖。

新增第5个合成情形：同一price_change帧先提高bid，再删除旧ask，使最终book不交叉。
代码在每条内部变更后发一行，可能输出暂时交叉的中间状态。复用已阅读的官方stream
结构和已核查函数，不另选文献或修改真实转换器。检查另用02保存；实际历史中有多少
交叉行由这个原因造成，还需固定原始帧的独立重放，不能用合成例子代替。

02实际执行结果：5种行为全部复现，第5例同一帧发出2行，第一行交叉，最后一行不交叉。
回执hash `0095a97768b1f2b6476fbd5188bbd2ba8e6cca5962b6541f987cbd6596c7c72d`。
两个probe均退出0，没有修改真实ETL或访问真实行情行。后续实际训练仍不放行。
