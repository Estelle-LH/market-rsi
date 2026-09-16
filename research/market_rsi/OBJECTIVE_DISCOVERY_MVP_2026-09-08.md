# Objective discovery MVP｜2026-09-08

## 今天做通了什么

Objective discovery 已经成为 controller 的独立第一阶段。它先检查已经开放的 Train，查公开
文献，提出多个目标，逐个运行 Train-only audit，比较稳定性，最后只冻结第一份有效选择。
这个阶段没有 Dev 文件，也没有 Future Test，更没有正式训练模型。

合成数据 canary `objective-discovery-controller-canary-20260908-02` 已经完整通过：GLM-5.3
用了 8 个 turn 和 19 次工具调用，检查了数据、查看了 3 个目标、查了 2 次文献、写了 3 个
proposal、运行了 3 次 audit，并提交了一个目标。完整 hash-chain 日志通过检查。该 canary 的
Tinker 实际计量成本是 `$0.179685864`。

第一次 canary 暴露了两个接口问题：proposal 的文献 ID 顺序要求没有写进工具 schema；最终
decision 使用嵌套 JSON 时，GLM 容易把字段拆错。现在 proposal 会自动规范化唯一文献 ID，
最终 decision 改成平铺 schema；中断后的 provider dispatch 也会保守结算，不再留下无主预留。

## 真实 Train 数据

从 Linode 的四个封存日期 `2026-08-29` 到 `2026-09-01` 只读复制了盘口和事件归档。归档的
SHA-256 与每日 manifest 一致。Materializer 读取了 8,401,097 条盘口快照、93 个 event，得到
40,497 个决策点，覆盖 48 场比赛和 209 个市场。每个决策点约相隔 60 秒，但标签来自约每
2 秒一条的未来密集盘口；标签和输入分开，完整未来窗口关闭后标签才可用。

为了不把 controller 限死在旧的 60 秒目标，runner 预先物化了 1、5、15 分钟三个 horizon，
每个 horizon 都有 point、window mean、forward EWMA 和 median 四种可执行定义。Controller
可以比较这些定义，也可以提出别的目标；新目标如果没有 materializer 和 audit，只能记录为
失败建议，不能被选中。

## Train-only 发现

| 目标 | 可用行 | 标签发生变化 | persistence RMSE |
|---|---:|---:|---:|
| 1 分钟窗口均价 | 40,371 | 2.05% | 5.80 bps |
| 5 分钟窗口均价 | 39,650 | 6.24% | 13.66 bps |
| 15 分钟窗口均价 | 38,922 | 14.60% | 26.68 bps |

结论很简单：昨天的 60 秒目标太平。约 98% 的样本没有变化，所以“直接猜价格不变”已经很
强，MSE 很小也不代表模型很强。把 horizon 拉长后，可学习变化明显增多，但 15 分钟仍有约
85% 样本不变。下一步不能只看 raw MSE，必须同时看相对 persistence 的 skill、每天和每场
比赛的稳定性、coverage 和变化率。

当前历史归档没有可验证的 trade stream，所以未来成交 VWAP 还不能作为正式目标。它可以
保留为后续数据工程方向，但不能用后查到的成交数据冒充当时可用数据。

## 数据外发边界

真实 Train controller 已经在 aggregate-only egress guard 下完成。GLM-5.3 只收到上述汇总
统计、公开文献目录、objective 目录以及它自己写的 proposal；没有收到原始盘口行、时间戳、
比赛或市场身份、本地路径。它用了 8 个 turn、18 次工具调用和 3 次文献搜索，提出并检查了
1 分钟窗口均价、5 分钟窗口均价和成交 VWAP 三个方案。成交 VWAP 因缺少可验证成交流被 audit
拒绝。第一份有效决策冻结了 `future-midpoint-window-mean-270-330s-v1`，即约 5 分钟后的
60 秒 midpoint 均价窗口。实际计量成本是 `$0.176343156`。四条 append-only 日志和全部 egress
记录均通过检查；选择时没有创建或读取 Dev，也没有打开 Future Test。

选定目标随后被原样提升为 formal-learning contract。Controller 没有重新采样，目标定义和
Train 证据没有变化。修正 UTC 日期分配后，正式学习数据冻结为三轮：第一轮 6,000 条 Train、
3,921 条 sealed Dev；第二轮累计 12,421 条 Train、2,398 条新 Dev；第三轮累计 17,319 条
Train、3,232 条新 Dev。每轮 Dev 都只包含完整落在预先声明 UTC 日期内的整场比赛。

## 当前结论边界

已经证明的是：objective-discovery 的 controller/tool/audit/freeze 闭环能在真实 Train 上运行；
真实密集标签能生成；旧 60 秒目标确实过平；GLM 独立选择并冻结了 5 分钟窗口均价。正式
Round 1 也已经完成：底层 ridge predictor 在 3,921 行、14 场比赛、一个新 Dev 日期上，相对
persistence 的 equal-game MSE 改善 2.36%，RMSE 从 15.58 bps 降到 15.40 bps。

这还不是 RSI 结论。只有一个 Dev 日期，而且 controller 最终选择了一个预测完全相同、只加入
无关 metadata 的重复候选。数值结果属于底层 predictor；controller 自主选择没有通过完整性
检查。Round 2 因此暂停，Future Test 仍未打开。完整报告见
`FORMAL_ROUND1_2026-09-08.md`。

完整离线测试为 803 / 803，通过；`git diff --check` 通过；正式进程退出，E2B inventory 为零。
