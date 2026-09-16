# 时间字段与训练样本：继续查，不改旧结果

## 为什么现在做这一步

上一步只发现“有回退、部分source时间很早”，没有按REST快照和WebSocket更新拆开。
现在要分清：回退是否主要发生在不同消息类型之间，还是同一种实时更新内部也存在。
这是新的定向数据诊断，不重跑上一份报价质量审计，不删旧行，不为得到好结果重试。

只读同一个已经核对过内容的Sep08T12文件，绑定上一步完整压缩/解压hash。单独新版本、
新run ID，只算时间字段和消息类型计数，不计算价格、label或分数。上次只返回汇总，
没有保留逐消息类型的时间统计，所以这项新问题需要一次新的限量读取。原始目录不改，
没有新日期或Test，没有Tinker/E2B调用。600秒/1GiB仍是上限，不是预计时间。

## 研究记录

2026-09-13执行方检索：
`site:docs.polymarket.com websocket book timestamp timestamp generated order book snapshot`；
`site:github.com/Polymarket timestamp orderbook timestamp last update`。
仅采用官方材料，不用第三方转载替当前数据背书。

读取[Market WebSocket](https://docs.polymarket.com/api-reference/wss/market)的book、price_change、
last_trade_price和best_bid_ask示例；
[Get order book](https://docs.polymarket.com/api-reference/market-data/get-order-book)的timestamp
及订单簿响应字段；以及官方
[Python client的parse_raw_orderbook_summary](https://github.com/Polymarket/py-clob-client/blob/main/py_clob_client/utilities.py)。
REST文档把timestamp称为订单簿快照时间；客户端把响应字段原样带进summary，没替换成
本地接收时间。WS页面展示各类型的timestamp，但不证明我们的采集器`t`字段怎样产生。
当前公开代码不是历史部署证明，也不是服务器内部更新时间的完整定义。

复用已有[Beam/pandas时间查找研究](TEMPORAL_CONTRACT_2026-09-12.md)，不把事件时间、
处理时间和本地wrapper数值混成一种。新统计只称为“两个数字字段的差”，不能叫已测网络延迟。

比较的做法：直接删所有回退行会掩盖来源差异；改用wrapper排序等于替controller换时钟；
按消息类型分别计数可以先定位问题而不改变研究方法。本次采用第三种。

## 实现与验收

`audit_tools/message_clock_origin.py`只保存计数、最早/最晚时间；每个token内部仍按
原始record/inner-event顺序，不重排、不合并同毫秒记录。分别报告相邻回退、低于此前
最大值、同消息类型子序列内的回退。忽略价格值，成交消息只计类型，不当成报价。
wrapper必须在已授权Sep08日期内，否则停。source时间早不被自动解释为坏数据。

下一步的样本转换必须把预测输入和未来答案分开：输入只用decision_key以前的数据，
答案可以用之后的端点；无后续记录不可填0。先做合成边界测试，不擅自决定缺少的特征
窗口规则，真实训练仍需controller方案一致及来源检查。当前文档不是训练放行书。

测试、服务器canary和实测结果完成后追加。当前仍未开始新训练。

新增9项clock类型测试和54项既有相关回归共63项通过。服务器完整合成canary02通过：
一条新WS、一个旧REST快照、另一条新WS，准确归因1次WS→REST回退，同类型WS回退0；
临时目录、解压器和SSH均退出。结果内部hash
`cb292a4bad55b1d552a48e9d6c181bc68754cd45f4c35f1a1fb9faef2ee964fc`。
canary01也通过；02只增加显式校验临时目录已删除，没有真实市场读取或模型调用。

## 实测结果：旧时间来自哪里

版本`pm-message-clock-origin-v0.1.0`/`94c25a4`发布后，定向读取6.85秒完成。
同一个文件的151,802条记录、298,068条报价，压缩/解压hash与上一份审计一致。
120次相邻source时间回退：112次WS更新→REST快照，8次REST快照→WS更新。
在book、price_change、REST各自子序列内，本文件均未观察到回退。
272条source时间早于wrapper当天的报价全是REST快照；最早仍是8月27日。
wrapper相邻数值没有负差，但这不证明它是经过核实的接收时间。

所以，之前的120次不能直接解释为“实时更新内部乱序”。不同消息的时间含义不能混着用。
不因此自动删REST、改成wrapper时钟或放行训练。文件只覆盖一小时，不能证明完整日、
无断流或原始采集器正确。原始采集器证据仍缺失。
实测：`artifacts/message-clock-origin-audit-20260913-01/report.json`，内部hash
`1e1b8290538d339dd7d30c5e3255384da1e91c33583961e8efbcf5e0e79f72cf`。
独立汇总与上一份计数、文件hash对齐：`artifacts/message-clock-origin-review-20260913-01/findings.json`，
内部hash`ba7ada697233dc73aaab1c073e6a6a3fabbbed7161429390bd4850394ce2d083`。

## 样本转换基础代码

`audit_tools/causal_event_samples.py`是单实体、单时钟、有序片段的参考实现，不是已接入训练的工具。
时钟、消息类型、回看窗口、容差、最少记录数、最大间隔、是否跨日都要求显式提供，没有替controller选默认值。
不静默排序、不筛掉回退、不跳过坏端点、不把缺失答案填0。

输入X只看当时及以前的记录；答案y单独找未来端点。相同毫秒也按原始到达key区分。
严格更晚的记录关闭端点组后才算答案可用，并记录这个可用时间，后续训练切分还必须检查它。
过去窗口记录数明确计入[decision-lookback,decision]；最大间隔包含选中的历史锚点到decision。
这些是原型语义，不自动等同于controller之前写得含糊的coverage/min-observation规则。
19项合成测试通过，包括改变未来不改变X、前缀一致性、重复毫秒、无效端点、0与缺失、
答案可用时间、混合时钟/实体拒绝、回退、跨日、长间隔、与已发布probe一致。

仍未接真实数据adapter、训练截止时间筛选或训练cache；没有新模型fit。
这是人写的harness改进，不是模型自我改进或预测效果提升。
新续接准备器只发送这两份汇总、原型边界和全部历史记录；不发送原始价格、ID、密钥或Test。
controller需自己明确来源/时钟/样本规则和下一步操作。DSH1.4.1保持不变，新原型尚未激活。

## Controller续接的实际结局

外部代码`cc3ed8f`/`pm-causal-samples-v0.1.0`在自己的origin发布核对后，启动一次新会话
`clock-feedback-controller-20260913-01`，没有重用旧ID。保留23条旧发现和父会话可见的
旧archive，加2条新反馈，共25条。4分37秒结束：8次计量回复、9次实际工具调用、0次fit。
全部反馈已回应；读了官方WS页面[0,6000)/14628字符，无搜索，不能叫读完论文。
一次probe错误因未先提供真实研究记录编号，随后补研究记录并通过；错误未删除。
第一份有效研究方案和最终defer已保存。这里valid=true是会话完成，不是科学方案放行。

它自己选择：WS的book和price_change进入样本，REST不进入，仍用source_ms。
下一份请求的JSON这次合法，选择的Aug21T12对象和65,819,206字节与已授权旧清单一致。
该对象这次没有打开。请求仍未激活，不能称作已做新数据实验。

独立复核留下的主要问题：

- 新增的ws_shot_gap说“某个时段附近没有WS”，但时段宽度、“附近”的容差和判断公式没写清。
- Check尾部写成按9月9日日期截止，typed规则却必须有严格更晚的真实观测关闭端点。
  用三条合成记录证明：最后一条恰好等于target也不能算已关闭；日期不能补出缺失观测。
- book官方示例有bids/asks，不是直接best_bid/best_ask；如何处理缺字段没有明确，不能代它选。
- 它声称runner已免做baseline登记，实际没有这项授权；也把还没实现的完整label操作叫成已实现。
- 它改的是消息类型所定义的数据范围，却把changed_layer写为features；不能把以后分差归因于feature。
- 原始采集器/heartbeat证据仍缺。多读一个价格文件也不能补齐这项证明。

这不是因为结果差而重试：根本没有得到新训练结果。下一项工程工作是把来源、字段、窗口、
答案可用时间和缺数据规则变成必须填写且可检查的结构，controller自己填，执行方不替它决定。
不能继续只靠长段文字表示“已经明确”。旧proposal不能回写成新规则，也不能跳过检查。

独立复核：`artifacts/clock-feedback-review-20260913-01/review.json`，内部hash
`b2f37e491ac4949db48a9f3a35e895f0964a762312193ee7fb1a6cb812a839f8`。
新增7项边界/范围测试，相关87项通过；另做100个合成片段共3,000处前缀不变性检查通过。
费用审计：`artifacts/clock-feedback-controller-audit-20260913-01/audit.json`，内部hash
`0a9248f13c6d160f2b1e5cf7ada762db205303c6fabda197492de285dade7e22`。
本次计量$1.788942672，不确定额0；原$200累计计量$39.359951504，包含旧不确定上限后的
有效占用$44.218532384，旧预留$2.30，可用$153.481467616。不是供应商发票核对结论。
runner52873和child52913已退出；没有后台训练，没有新E2B、数据下载或Test访问。
