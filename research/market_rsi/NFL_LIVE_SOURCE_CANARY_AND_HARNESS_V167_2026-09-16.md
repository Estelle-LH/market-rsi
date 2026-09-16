# NFL live source canary与Harness v1.6.7

日期：2026-09-16

## 这轮做了什么

`nfl-live-timing-controller-20260916-02`在已发布`dsh-v1.6.6`下运行。它只看到冻结的aggregate
findings和公开资料入口，没有raw rows、split IDs、训练入口、Route-Dev或Final。会话24 turns、
29次工具调用，322.69秒，进程正常回收，model authorship通过，无未结算调用。Tinker实付计量
`$1.627523118`；运行后learning余额`$39.841161974`。

本轮没有fit或score。Controller最后defer，因为当前最好的HGB表示依赖`state_wp_delta`，但该字段
在决策时能否实时获得还没有证明。

## Controller实际完成的研究

成功动作：

- 读取Sportradar Push Events和REST Play-by-Play官方页面的6个bounded ranges；第7个读取因body
  cap被拒绝。
- 建立3条research records，分别用于feature、data quality和trainer-compatible composition。
- 运行live timing contract。它正确返回四个gate都没有通过：correction/overturn处理未验证，
  independent confirmation至少需要20场prospective games。
- 归档capability proposal `prospective_push_feed_canary_recorder`，状态是proposed/not activated。
- 提交一份具体下一步：先验证live source，再训练derived-state representation；不打开Dev/Final。

Controller建议的小canary是至少3场、300条live play，记录`created_at`、`updated_at`、
`wall_clock`和local receive，保存immutable raw messages并并行记录market messages。它把95%字段覆盖、
0 receive-clock倒置和5秒p99写成采集验收；5秒只从官方3秒REST TTL做粗略工程推导，不是SLA，
也不是market-lead阈值。即使小canary通过，也只说明capture mechanics，不是独立科学确认。

目标时间窗口没有被永久固定为60秒。Controller为“如果source通过后的同parent诊断”保留了既有
30秒target，理由是不在同一次比较里同时换source、representation和horizon。以后新的opened-Train
discovery仍可事前提出其他有限horizon grid；看分后不能改。

## 两个Harness观察

### v1.6.6证据bridge边界

v1.6.6提供runner-bound aggregate source evidence。但本次paid controller没有调用该工具，因为
官方页面这次可以直接读取。Bridge已经过unit tests和真实Codex scripted canary验证，但不能写成
“paid controller已使用”。本次真正使用的是6个`read_public_source` records。

### 新算法没有成功归档

Controller连续10次调用`propose_algorithm_design`，全部被拒绝。它确实提出了一个思路：用比分、
down、yards-to-first-down、yardline、possession、quarter、clock及review/correction字段重建
decision-time state，并用rolling-origin fit一个win-probability proxy；HGB trainer保持不变。

但这个想法不能算正式archive。根因是工具对controller只公布`proposal: object`，内部却要求28个
精确字段。错误包括string而非object、字段名不匹配、research record layer不匹配和缺少完整schema。
因此v1.6.7把全部字段、类型、enum、boolean、数组和exact required set直接放进served tool schema；
validator和served schema使用同一字段集合。它不放宽算法准入，不激活代码，也不奖励novelty。

## Source capability实现与真实preflight

新recorder `capture_sportradar_push_canary.py`实现：

- entitlement preflight不跟随signed stream redirect；
- key和signed URL永不落盘；
- 原始provider bytes与local receive receipts分文件保存；
- 每条消息记录raw hash、wall-clock receive和monotonic clock；
- 解析created/updated/wall-clock、entry mode、review/correction字段覆盖；
- message/time硬上限，无自动retry；
- manifest明确不证明SLA、market lead、模型score或PnL。

真实单次preflight run：`nfl-sportradar-push-entitlement-preflight-20260916-01`。结果`HTTP 403`，
无redirect，`stream_entitlement_observed=false`；receipt SHA256
`c3d05a0799430b93ce376917e6d3694e31b6551b1e19412019278202726bc927`。没有打开stream、没有消息、
没有key/redirect泄露。现有trial不能执行Push canary；这与之前记录的“普通trial不含Push”一致。

## 当前结论和下一步

已经证明：代码能安全记录prospective Push数据；当前trial没有Push entitlement；algorithm工具之前
的失败主要是served schema缺失。

没有证明：Push feed的真实延迟、字段覆盖、market lead、derived-state模型效果或PnL。

下一步不能假装继续采集。可选路线是申请短期Push/Pulse access；或用当前可用的REST/ESPN做
较慢的prospective source study，但那回答的是低频状态可得性，不是严格push latency。无论选哪条，
先冻结source、clock semantics、primary reward和horizon，再采数据；独立确认仍需要至少20场。

## 验证

- Harness 269/269。
- sports 62/62，包括新recorder 3/3。
- NFL experiments 19/19。
- v1.6.7真实Codex canary `data-scientist-codex-canary-20260916-05`已通过：18次tool call、
  4个CPU fit、1次公开搜索、1次公开阅读、0 Tinker、0 Dev/Final。commit
  `7dc906fb33a70c240d547dc06a9f9512a5fa8ae1`、tag `dsh-v1.6.7`和release SHA256
  `14c834a01da0cc5cc7787475098c4eb7b62ba3565e13964b73e119e976923be4`已核对并发布到用户origin。
  这是已发布的人为Harness修复，仍不是self-evolution score；也没有因此重跑旧controller。
