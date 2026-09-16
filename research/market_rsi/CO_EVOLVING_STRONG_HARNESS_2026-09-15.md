# Co-evolving Strong Harness

日期：2026-09-15
状态：开发设计；未发布，未启动付费实验

## 为什么加这一层

现有 Controller 能在已有数据、feature 和 trainer 中做选择，但它发现“数据太少”以后，没有
搜索供应商、取得样本、比较授权和报价、实现下载器或申请购买的动作。因此问题进入日志，却没
有进入下一轮行动。模型方法也有同样限制：可以登记缺失能力，但不能把最重要的缺口变成一个
经过验证的新 Harness 版本。

新增外层 Strong Harness，固定使用 Codex `gpt-5.6-sol`、`high` reasoning。它读取完整实验轨迹
和机器回执，主动找出当前最早的因果瓶颈，提出多个 Harness 修改，实施并测试候选，然后只选择
一个修改进入下一版。研究 Controller 仍负责在冻结 Harness 内做实验；两者不能混成一个角色。

## 架构

```text
不可变内核
  Train/Dev/Final、预算、权限、hash、ledger、retry、独立grader
        │
Strong Harness（Codex gpt-5.6-sol）
  读轨迹 → 找瓶颈 → 提候选 → 写代码 → replay/canary → 选一个新Harness
        │
冻结的 Research Harness H_t
  数据工具、feature工具、算法库、实验接口、Archive
        │
Research Controller
  提问题、选动作、跑候选、解释结果
        │
Runner / independent evaluator
  执行、计费、打分、保存证据
```

Research Controller在每个固定Harness版本下先进入open-ended discovery。此时可改变研究问题、
target、representation、算法和研究图，但只能使用opened Train、Archive、公开文献与synthetic
canary，不设performance reward，也不允许正式提升结论。它选择一个candidate后，runner冻结
baseline、primary reward、evaluator和one-shot fresh evaluation，才进入confirmation。完整合同见
`data_scientist_harness/research_cycle_contract.py`。

`raw data → indicator → prediction → objective → PnL`只是prediction研究的可选adapter，不是Strong
Harness的全局本体。

必须同时保存两条 lineage：

```text
Harness: H0 → H1 → H2
Model:   M0 → M1 → M2
```

每个模型结果必须绑定准确的 Harness 版本。跨 Harness 的改善不能只归因于模型。

## 哪些可以进化

- data acquisition、data quality；
- feature 与 target 设计工具；
- trainer 和 evaluation diagnostics；
- Controller context、工具接口和 Archive 格式。

以下内容不能由 Strong Harness 自改：Train/Dev/Final 分区、sealed Final、预算硬上限、费用账本、
不得按分数重试、artifact hash、外部购买授权、供应商条款/身份真实性和独立 grader。

## 每次怎样滚动

1. 在 Harness `H_t` 下完成一批实验，保存全部成功、失败、调用、费用和结果。
2. 把观察写成机器可读问题：证据在哪里、严重程度、卡住了哪个动作。
3. Codex 可以提出很多候选，但每个候选只能改变一个 evolvable component。
4. 候选不能看下一批 Dev/Final，也不能在验证阶段购买数据或发送外部消息。
5. 每个候选必须通过旧失败 replay、新正反 canary、相关单测和无关回归。
6. 合格候选先解决更严重的真实瓶颈；同级选择更小的 patch、更低的下一轮成本。
7. 只选一个候选，冻结为 `H_t+1`；下一批新的 Route-Dev 才检查它是否有帮助。
8. 旧 Harness、失败候选和未选分支都保留在 Archive，不能覆盖。

这些步骤必须与真实实验交替执行。每个Harness版本都要先commit、annotated tag、push并生成release
receipt，才能启动绑定该版本的实验batch。实验batch可以包含多个内层round；batch完整结束后，
Strong Harness才能读取其机器证据并生成下一版候选。没有完整实验不能升级Harness，没有新release
不能启动下一批实验。实现合同见`data_scientist_harness/co_evolution_loop.py`。

选择过程不使用下一批预测分数。否则 Harness 会对当前 Dev 过拟合。

## 第一项改进：Data Acquisition

当前机器可读瓶颈是：只有163个独立NFL比赛，Train信号较弱，而 Harness 没有寻找、验样、
询价和购买数据的动作。第一项 Harness 候选因此不是再加一个 trainer，而是增加以下流程：

```text
define_data_need
search_data_sources
request_sample_and_quote
inspect_sample
compare_effective_units_per_dollar
request_human_purchase_approval
download_and_hash
admit_train_candidate
```

购买前必须同时有：至少3个独立样本单位、完整schema、时间戳语义检查、缺失/重复统计、研究保存
许可、正式报价、预算内判断和预计独立单位数量。准备就绪只允许“请求购买批准”，不等于已经
授权、购买或准入。

可以组合不同供应商允许的trial、公开archive、官方API、学术研究样本、付费小切片和自己合法
采集的数据。真实团队成员可以在本人同意后，用自己的团队邮箱领取供应商允许的trial；使用前
必须记录账号归属授权、供应商条款是否允许团队成员分别试用，以及是否遵守组织级trial上限。
不能创建假身份、未经本人同意代开账号，或在条款禁止时轮换邮箱规避限制。每一行数据仍须保留
来源、许可、时间语义和hash，也不能把只允许在线试用的数据默认为可长期保存或合并。Strong
Harness可以起草供应商邮件和准备询价字段；实际发送邮件、注册账号或付款仍需外部动作授权。

当前实际候选包括：

- Predexon 的Polymarket历史trade/price与按slice报价的tick数据；
- PMXT的免费Parquet archive，先检查覆盖；
- Kalshi官方trades/candles或取得书面研究许可的数据；
- Predexon Kalshi orderbook从2026-01-07开始，不能假装补齐2025常规赛L2。

下一步先取免费目录、样本和报价，不立即购买。

## 研究依据与限制

检索日期：2026-09-15。

| 查询/来源 | 阅读内容 | 采用 | 限制 |
|---|---|---|---|
| `Darwin Godel Machine self improving coding agents archive empirical validation`; [DGM](https://arxiv.org/abs/2505.22954) | 自改代码、保留分支archive、用benchmark实证验证和sandbox/human oversight | Harness候选作为版本树保存并实测 | coding benchmark结果不能证明market research有效 |
| `Automated Design of Agentic Systems meta agent search`; [ADAS](https://arxiv.org/abs/2408.08435) | meta-agent基于不断增长的archive编写新agent | 外层Codex提出多种tool/control-flow修改 | 不能直接采用其任务分数作为我们的选择标准 |
| `SWE-agent agent computer interface`; [SWE-agent](https://doi.org/10.48550/arXiv.2405.15793) | agent-computer interface设计会显著改变agent表现 | 将Harness版本作为实验变量保存 | 软件任务接口不等于时序数据研究接口 |
| Predexon历史数据与[价格页](https://predexon.com/) | slice可先询价，历史trade/price和tick archive | 用于data-acquisition候选 | 厂商覆盖声明必须用样本验证 |
| [Predexon Kalshi orderbook](https://predexon.mintlify.app/api-reference/kalshi/orderbooks) | 明示coverage从2026-01-07开始 | 防止误买不覆盖2025的数据 | 不能推出其他产品也没有更早数据 |

## 已实现的开发合同

- `data_scientist_harness/strong_harness_contract.py`：不可变内核、可进化组件、观察、候选、验证
  和单候选选择规则；
- `data_scientist_harness/data_acquisition_contract.py`：数据需求、样本、license、quote和购买前准入；
- `data_scientist_harness/test_strong_harness_contract.py`：内核不可改、失败候选淘汰、选择不看分数、
  无研究保存许可时不得请求购买。

这些只是开发代码，不是已发布 Harness，也不是 self-evolution 成绩。正式使用前还需要完整回归、
真实零付费 canary、commit/tag/release receipt和新的实验身份。
