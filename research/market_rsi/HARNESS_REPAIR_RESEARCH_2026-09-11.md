# 9月11日：报价重放与文献工具修复依据

这是执行方工程研究，不是GLM读过的内容或模型能力提高。先记依据、备选与验收，再实现。

## 报价来源

问题：逐日CSV检查发现交叉报价；合成测试显示当前ETL会漏WS book/报价失效，并在一条
消息内部发出中间报价。尚未证明历史中各原因所占比例。

沿用[已有来源核查](CAPTURE_SOURCE_REVIEW_2026-09-11.md)，本次再打开
[Polymarket实时消息说明](https://docs.polymarket.com/market-data/realtime-data)，
定位`event_type`，读取API market stream的book、price_change、last_trade_price与
tick_size_change示例（833–924行）。当前格式不证明旧档相同，先核对真实旧档字段。

固定最早允许诊断日8/21的第一个小时文件，前5000条、最多64MiB解码、90秒墙钟。
只在Linode读取，返回聚合/来源hash，不回传原始行或标识符，不生成标签、不打开保护日期。
不根据价格变化挑样本；原件不改。这个小样本只验证解析与机制，不能代表全日错误比例。
下一步备选：直接删交叉行不解决丢失状态；先做独立原始消息重放再与当前ETL比较。
验收包括来源不变、顺序保留、显式无效状态、未来修改不改变过去输出；目前为待做。

## 文献工具

问题：GLM06成功读取的正文远少于10MB，但旧工具按每次2MB计数且不释放上界；也没返回
HTML链接，让模型猜路径。改变的是研究工具，不是金融目标/特征/模型。

2026-09-11直接打开Python3.12官方文档：

- [HTTPResponse](https://docs.python.org/3.12/library/http.client.html#httpresponse-objects)：
  阅读read(amt)、status、headers和分块读取示例。按实际已读body字节计量，不把Content-Length
  当作实际接收量。该计量不包含TLS/HTTP头/底层缓冲，不能冒称网络账单字节。
- [URL拼接与安全](https://docs.python.org/3.12/library/urllib.parse.html#urllib.parse.urljoin)：
  阅读urljoin警告与URL parsing security。相对链接应基于最终页面地址解析；解析不是安全验证，
  每次请求仍检查HTTPS、公网DNS和重定向，不能自动访问网页里的链接。
- [HTMLParser](https://docs.python.org/3.12/library/html.parser.html)：
  阅读feed/close和handle_starttag/attrs；提取实际href，不执行script，不把外部文字当指令。

采用先持久化预留、完整成功回执后结算实际body字节；失败/超时缺证据仍留上界。进程被杀
也不能让预留消失。保持10MB总上限，单次上界包含超限探测的1字节。不采用直接调大限额，
也不把失败当作免费。返回有界链接列表及来源页hash，链接不等于已读正文。
计划验证：多次小页面、失败上界、崩溃后预留、超限拒绝、解析失败但已读body计量、
安全链接/相对链接/去重/截断标记，以及真实公开页面的小规模免费canary。

## 本次实测

- `capture-raw-prefix-20260911-01`：固定前5000条、3,187,382解码bytes，时间跨度约1.605秒。
  有4998条price_change和2条book；wrapper没有src字段。5000条均有t，消息均有timestamp；
  t不早于message timestamp，但这不能证明它就是接收完成时间。
- `capture-shadow-prefix-20260911-01`：同一hash前缀交给当前ETL，0条quote；处理WS book后
  明确得到2个双边snapshot状态。9996个delta entry仍未初始化（422个token出现过），
  不向前补造订单簿。per-entry与atomic两个新变体在这段输入上没有出现交叉差异，
  **不能说已经解释了全量1.81%的交叉行，也没有与已发布CSV逐行比对**。
- Source SHA `27621845de8cc31ca2055235b2a4b69e11a0c6116f3d316f3eda84e647bb4255`；
  prefix SHA `03d5f2ec3c8d9f24bb76797071ce2b2a1af432620c5385ab4c2aef657507f56e`；
  shadow report digest `bca0234dce71b76b517c881d996ed396b8bf546a2a925dcf31f2dad776f79700`。
  两个reader均退出0，zstd在固定前缀结束时收到SIGPIPE(-13)并回收，这是主动截断，不是全档解码成功。
- 7项原始消息/重放合成测试通过，含未来修改/追加不改变过去状态、缺锚点、单边失效、单位
  异常和身份冲突；138项harness回归通过。真实数据有效性/时钟和历史版本仍未证明。
- 真实public-links canary提取55链接并跟随实际链接，两次正文429170+1877311=2306481bytes，
  账本完全一致，0个未结算请求；免费Codex canary完成18个脚本化调用。没有新增Tinker消费。

代码：`data_scientist_harness/public_budget.py`、`literature.py`、`broker.py`，以及
`audit_tools/capture_raw_prefix.py`、`capture_shadow_replay.py`。这些修复没有选择目标或算法。
完整长文每翻页仍重新抓取，尚无正文缓存；失败缺回执仍占上界。这些限制没有隐藏。
只找到目前运行的Polymarket US采集器，它不是本次历史国际CLOB来源，未混用其时钟证据。

## 对新controller方案的独立复核

source-repair-followup完成7个模型turn、8个成功工具操作，实际读取实时文档0–12000字符
与完整价格说明4679字符（没有全文通读实时文档），费用$0.669495132。它选择defer并请求
全天raw replay；这个决定没有被重抽，也没有被执行方改写。

方案仍有未经证明的判断：缺文件=断流、mtime/保存时钟=接收时钟证明、当前Gamma缓存=
历史身份验证。它提出的“任意Yes+No报价相加恒等1”也不能直接成为删行规则。
复查[官方价格说明](https://docs.polymarket.com/concepts/prices-orderbook)99–190行：
示例讲的是互补价格的订单匹配/铸造，以及bid/ask与展示价的区别；据此不能推导出
不同步的任意bid/ask/mid都必须相加恰好为1。这是执行方推断，不是文献给出的已测结果。

所以不直接启用该完整能力或这些判定；先做其机械部分的固定规模pilot：同一原始小时
前50000条、64MiB解码、512MiB内存、120秒。检查两种重放的初始化/双边/单边/交叉计数与
耗时，评估能否扩大到全天。沿用上面已查阅的消息格式与前7项单元测试，不另选算法或目标。
这个pilot不具备全天增量落盘、历史身份认证或报价正确性的完整证据；未运行前不称通过。

pilot已完成：前50000条31,967,293解码bytes、约62.987秒行情，4.163秒运行。
旧ETL0quotes；两个shadow变体相同，12,204个双边、72个单边、87,544个未初始化状态。
99,730delta entry，90WSbook快照，910个token出现过。扩大的前缀仍没测到两种shadow的
交叉差异，所以不得归因全量异常。中间状态风险只在合成例子复现，快照遗漏则在实际前缀复现。
receipt digest `d513471479881b0cae7ffa7e6cb975644b0a656efe5502b6b74336da07a5d7bd`。
没有开启全天任务或后台训练。公开正文读取账本核对为4187932bytes、无挂起请求。
