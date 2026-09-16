# NFL source blocker Controller：逐步结果

日期：2026-09-16  
Run：`nfl-source-blocker-controller-20260916-01`  
结论：会话在运行层面完整结束，但没有产出可执行的新算法或数据实验。

## Controller看到了什么

这是aggregate-only workspace。Controller只看到12份汇总receipt、11条当前finding、公开的method
library和既有官方资料的有限摘要。它没有看到raw row、比赛或play ID、split ID、Dev、Final、账号、
provider key或购买权限，也不能训练。

- workspace manifest SHA256：
  `fc0edc7176c5231e9c4e3cdf2bd1739698bfc5f72d44b83865f94d79b82fd2a6`
- 12 turns，14次tool call，190.26秒；进程已回收，0未结算调用。
- 本次新增Tinker费用：`$0.504720234`。
- 累计有效费用：`$87.316309628`；账本仍未和provider invoice完成核对。
- 0 fit、0 Dev、0 Final、0新source admission。

## 每一步发生了什么

1. `inspect_harness`：确认这是aggregate-only设计审查，不能训练。
2. `acknowledge_current_findings`：逐条回应11个finding。
3. `read_aggregate_source_evidence`：读取runner已经核验的SportsDataIO Replay边界。
4–5. `inspect_sports_method_library`：分别查看可用sports研究阶段和方法状态。
6–7. `read_aggregate_source_evidence`：读取Sportradar PBP cadence和Push字段的有限官方事实。
8. 第一次`probe_sports_event_contract`失败：错误引用了method-library record，不是research record。
   这是格式错误，没有执行任何source或训练操作。
9. `record_research`：把三段已读摘要连接到live timing/source validation问题。
10. 第二次`probe_sports_event_contract`成功执行，但state prediction、market response、lead/lag和
    executable P&L四层全部有blocker。
11. 第一次`probe_live_timing_contract`执行。source receipt不是SHA256、correction state缺失；所有
    claim gate未通过。
12. 第二次`probe_live_timing_contract`修正receipt格式，但correction state仍只是partial；capture、
    strict latency、market lead、independent confirmation仍全部未通过。
13. `request_capability`成功归档，但内容不可靠，见下节。
14. `submit_research_decision`选择defer，没有训练或候选模型。

Append-only research trace SHA256：

- JSON：`40bba988aa6d083fcae0a0a150864f6a02819ec3ba042ed51fa7ee563886f19f`
- Markdown：`d6b963b00e83fea646abc01dcb580ae184160b14d79fe5a55397062489f2530e`

## 哪些内容可以保留

Controller把第一阻塞项定为`live timing/source validation`，不是继续调trainer或直接声称P&L。
这个顺序合理。它也保留了四个边界：Replay不能证明live latency；event wall clock不等于provider
publish clock；market lead还缺同一时钟上的market receive time；independent confirmation还需要
至少20场prospective games。

它自由提出了`30s / 60s / 300s`候选horizon，并写明只能在opened Train里按预先规则选一个，再带
入protected confirmation。这个grid是这次Controller提出的，不是Harness永久写死的，也没有因probe
成功而获得科学支持。

## 哪些内容被拒绝

Capability名为`prospective_live_leap_second_aware_iso8601_capture_clock_recorder`。它声称观察到
`1433ms`，还加入`monthly tensor schedule`、`Quiet Communities`、`correlation_invent`等当前记录里
不存在的值和字段。这些内容既不在已读官方摘要里，也不在probe结果里。

因此这条capability只能算“旧接口成功保存了一段文字”，不能算Controller发现、算法创新、数据结果或
可执行工程单。最终defer reason也没有明确复述这个capability，说明旧Harness只检查了字段非空，没有
检查结论是否真的绑定证据。

## Harness从这次失败学到了什么

`dsh-v1.6.9`只改controller/harness接口，不改数据、模型、target、reward或scorer：

1. 每条capability必须提供至少一个`evidence_ref`。
2. 每个ref包含精确record ID、`/result`内的JSON Pointer和模型声称看到的JSON值；Controller自己
   写入tool arguments的文字不能作为证据。
3. Broker重新读取append-only ledger并逐值核对；路径不存在、值不同或不是observational tool
   result就拒绝。
4. Controller必须单列`unsupported_assumptions`，不能把未知内容写成测量或provider字段。
5. capability仍不会自动执行；还要经过人工审查、实现、测试和新Harness发布。
6. 如果最后defer，reason必须写出最新capability的精确名称，避免结论和工作单脱节。

这不是模型性能提升，而是一次可归因的Harness修复：旧接口允许无证据文字入库；新接口使同类内容
在进入工程队列前失败关闭。

## 下一步

`dsh-v1.6.9`已经完成exact-source canary并发布。下一步可以用同一份冻结aggregate输入进行一条
fresh controller run，检查它能否提交证据绑定的source/capture工作单。不能重写本次run，也不能
因为输出不好而重采同一个ID。只有新的工作单通过证据核对，才决定实现Replay canary、替代source
adapter或另一个明确阶段。
