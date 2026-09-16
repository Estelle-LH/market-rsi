# Co-evolving Harness：数据加强与新算法设计

日期：2026-09-15
状态：开发版；合同和测试已实现，尚未发布为正式 Harness，尚未打开 Route-Dev/Final

## 我们现在要解决什么

刚完成的内层 RSI 在同一套 Train 上把 MSE 从 `0.0020001183` 降到 `0.0019082992`，下降
`4.59%`。但是只有 163 场、一个赛季；继续在同一批数据上调 Random Forest，越来越容易只是
记住 Train。

所以外层 Harness 的第一项工作不应是再选一个现成模型，而是把“数据不够”变成可以执行、
可以验收的动作。数据扩大后，再给 controller 一个正式的新算法设计通道。

## 两条 lineage

```text
Harness: H0（现在） → H1（多赛季数据能力） → H2（新算法设计能力）
Model:   M0           → M1（H1 下训练）       → M2（H2 下训练）
```

不能把两个 Harness 改动同时放进一个正式实验。否则即使 MSE 下降，也不知道是更多数据还是新算法
造成的。

更重要的是，Harness 和实验必须严格交替，不是两条各走各的路线：

```text
commit/tag/push H_t
        ↓
用 H_t 跑 E_t 的多个内层 round
        ↓
冻结 E_t 全部轨迹、失败、费用和 hash
        ↓
Strong Harness 只根据 E_t 提出 2–256 个候选
        ↓
replay/canary 后只选择一个 Harness 改动
        ↓
commit/tag/push H_t+1
        ↓
用 H_t+1 跑 E_t+1
```

没有完整 E_t，不能生成 H_t+1；没有新 commit/tag/release，不能启动 E_t+1。允许一次提出一百种
方法，但不需要实现或运行一百个完整实验：先做约束检查、去重和便宜的 replay/canary，只有通过
验证的少数候选进入选择，最后仍只发布一个 Harness 变化。

## 每个实验先 Discovery，再 Confirmation

不能把 confirmation 的规则强加给最开始的研究发现。每个 `E_t` 分成两段：

```text
Open-ended Discovery
  可以改问题、target、representation、算法和研究图
  只看opened Train、Archive、公开文献和synthetic canary
  没有performance reward，也不能声称正式提高
        ↓
Freeze
  选一个candidate；冻结baseline、primary metric、reward方向、evaluator、数据和预算
        ↓
Confirmation
  untouched Route-Dev/future holdout只使用一次
  结果出来以后不能改reward；新的想法进入下一cycle
```

Discovery仍然有预算、迭代数、权限和完整日志，但没有必须降低MSE之类的单一reward。它看过的所有
数据自动变成非fresh。只有确认阶段需要预先锁定reward和否定条件。

当前的`raw data → indicator → prediction → objective → PnL`只保留为prediction实验的一个
adapter，不再是整个RSI的固定结构。通用research type包括数据发现、描述、预测、因果问题、
representation learning、decision policy、market mechanism、simulation、algorithm design、
evaluation method和research tooling。

## 外层每一轮怎样工作

1. 读完整轨迹，包括成功、失败、费用、hash 和已看过的数据。
2. 找最早的因果瓶颈：raw data、signal、prediction、objective、PnL 中哪一层先坏。
3. 查 Archive，再做新的公开文献检索和正文阅读。搜索结果标题不算读过。
4. 提出一组不同类型的候选：数据、工具/诊断、feature/target、trainer，以及至少一个此前没做过
   的机制候选。
5. 每个候选只改变一个 Harness component，并预先写支持/否定条件。
6. 先跑旧失败 replay、正反 canary、单测和无关回归；不看下一批 Dev/Final 分数。
7. 只冻结一个候选成为下一版 Harness。失败候选和没选中的候选全部留在 Archive。
8. 新 Harness 下再运行内层 RSI。模型结果必须绑定准确的 Harness version。

“以前没做过”负责扩大探索范围，不直接获得分数奖励。真正采用仍要靠同数据对照、消融和新的
untouched evaluation。

## 当前 7 轮怎样归类

刚完成的 `nfl-train-rsi-trajectory-20260915-01` 是 bootstrap 开发观察，不是正式的 `E0`。原因是
它的 runner 在运行前没有先形成新的 commit、annotated tag、push 和 release receipt。不能在结果
出来以后反过来补版本并声称它属于正式 co-evolution。

它可以合法地帮助我们设计第一版 H1，但正式 lineage 要从以下顺序开始：

```text
发布 H1 → 跑 E1 → 观察 E1 → 选择 H2 → 发布 H2 → 跑 E2
```

这也意味着 H2 不能仅仅因为我们现在觉得“新算法很好”而发布；它必须由 E1 的实际轨迹触发。

## H0 → H1：实际加强数据

### 当前机器证据

- 只有 163 个独立比赛，来自一个赛季。
- 三段 Train rolling check 共 63 场、9,615 个有 60 秒标签的 play。
- 最好的 Train-only 模型只比 zero-change 低 4.59% MSE。
- 继续增加树或让每次 split 看全部 feature 都没有改善。

这不能证明模型一定需要更多数据，但足以说明“继续小范围调参”不是优先级最高的下一步。

### 第一阶段目标

- 建一个至少 600 场、至少 3 个赛季的 versioned Train candidate。
- 600 不是“已经足够”的结论，只是第一个能画出 `163 → 300 → 600` 学习曲线的阶段目标。
- 当前已看过或计划打开的 2021–2025 数据只能进入 Train/diagnostic。
- 保留未来 2026 数据作为新的时间外 holdout；不能把已经看过的 2025 重新叫 Dev。
- 总数据预算上限先保持 `$200`；计划本身不授权下载、发邮件、购买或准入。

### 数据来源不是预先锁死的

Harness 同时比较：

- Polymarket 免费 archive，加经过验证的官方/API/on-chain 重建；
- 有书面保存许可和报价的 vendor historical slice；
- Kalshi 官方公开历史接口或书面研究访问；
- 合法的自有 live capture 只用于未来数据，不假装补齐过去。

现在已经有一份公开 Polymarket market metadata 样本，但 metadata 不是 play-by-play trade trajectory，
不能直接进入训练。真正需要的是每场比赛可验证的 trade/price 时间序列和对应 play timestamp。

### 每个数据 batch 必须过的门

- 原始对象、版本、许可和 SHA256 都存在；允许研究保存。
- 独立单位按 game 计算，不用大量相关 play 冒充样本量。
- immutable row key 唯一；UTC timestamp；game 内顺序可重建。
- required field 缺失率 `0`，duplicate rate `0`；不做静默 imputation。
- 60 秒 target 和 play/trade alignment 覆盖率都至少 `90%`。
- scoring、late-game、non-scoring 等 regime 达到预先规定的最低覆盖。
- 不接触 future holdout、Route-Dev 或 sealed Final。
- 通过也只表示可以生成一个 Train candidate，不表示预测已经改善。

### 数据增加后怎样判断是否真的有用

固定同一个 target、feature、trainer 和 rolling 规则，只改变训练 game 数：

```text
163 games → 300 games → 600 games
```

每个点报告 MSE、IC、calibration、positive-game fraction 和 game/date block interval。若学习曲线仍明显
向下，继续找数据有依据；若很快变平，瓶颈更可能在 feature、target 或 algorithm，不应盲目购买。

## H1 → H2：允许 controller 设计新算法

现在 controller 主要从 Ridge、Elastic Net、Random Forest、Histogram Gradient Boosting 中选。
`request_capability` 也只能记录一个浅层请求。这会把 controller 变成菜单选择器。

H2 增加 `propose_algorithm_design`。每个新算法 proposal 必须包含：

- 它回应哪条真实实验轨迹；
- 实际读过的 trainer research record；
- 至少两个最近的方法、从文献读到的内容和迁移限制；
- 为什么现有 library 不够；
- 新机制的数学定义和伪代码；
- 输入、target、loss、regularization 和严格的时间拟合规则；
- zero-change、Ridge 和当前 champion 的同数据对照；
- 至少两个消融，包括 `remove_new_mechanism`；
- 失败模式、正反 synthetic tests、CPU/内存上限和依赖；
- 明确声明不读取 sealed data。

Proposal 只进入 Archive，不会自动激活代码。接下来必须经过 source review、sandbox reference
implementation、正反 canary、同数据 Train 比较和消融，才有资格成为新的 Harness version。

### 怎样真正鼓励创新

- 每个外层 cycle 的候选生成阶段必须考虑一个项目里没试过的机制；不能只列已安装的算法。
- 没有固定“读几篇论文”的数字；但是算法里的每一个关键说法都必须绑定实际正文阅读记录，并说明
  文献结论为什么可能不能迁移到 prediction market。
- 可以提出新的组合、loss、gating、hierarchical structure、online update 或 uncertainty treatment，
  不要求必须来自现成库。
- 也允许结论是“现在最早的瓶颈仍是数据，所以新算法先归档、不执行”。这不是拒绝创新，而是保持
  因果顺序。

### 一个示例方向，不是预先指定的答案

刚才的误差看起来可能集中在少数重要 play，普通 play 大多接近零。controller 可以研究一种
event-gated residual model：

```text
p(move | x) = sigmoid(g(x))
size(x)      = m(x)
prediction   = p(move | x) * size(x)
```

它先判断是否会发生有意义的市场变化，再预测条件幅度。这个方向必须先查 mixture-of-experts、
hurdle model 和事件条件响应的文献；还要用 `gate only`、`magnitude only` 和
`remove_new_mechanism` 做消融。这里不声称它在学术上全新，也不声称它一定比 Random Forest 好。

## 什么保持永远不能自改

- Train/Dev/Final 和 sealed Final；
- 预算硬上限、费用账本和不得按分数重试；
- provider 条款、身份真实性、外部购买/发送授权；
- artifact hash、完整失败记录和 independent grader；
- 已看过的数据不能重新包装成 fresh evaluation。

## 已实现

- `data_strengthening_contract.py`：具体 600-game/3-season 工作单、学习曲线、batch admission gate。
- `algorithm_invention_contract.py`：文献绑定的新算法数学/消融/失败合同。
- `broker.py`：加入 `propose_algorithm_design`，同时在 controller 指令里明确不能只选现成算法。
- `strong_harness_contract.py`：数据和算法两个瓶颈都绑定到刚完成的 RSI trajectory。
- `co_evolution_loop.py`：强制 `published Harness → experiment → observation → candidate portfolio →
  one selection → new published Harness → next experiment` 的交替状态机。
- `research_cycle_contract.py`：允许无performance reward的open-ended discovery；只有从候选中选定
  一个confirmation后才冻结reward、baseline、evaluator和one-shot fresh-data规则。
- `algorithm_invention_contract.py`：不再只允许prediction；可提出representation、training algorithm、
  decision policy、market mechanism、simulation和evaluation method。
- `test_coevolving_data_algorithm_contracts.py`：干净数据通过；重复、holdout 污染和 sealed-data
  算法请求 fail closed；算法 proposal 只归档、不激活。
- `test_co_evolution_loop.py`：未发布 Harness、无实验升级、无证据观察、重复 commit/tag 和未包含
  新探索候选的 portfolio 全部 fail closed；100 个候选 portfolio 可以保存，但只能选一个。
- `test_research_cycle_contract.py`：discovery可以改问题且无performance reward；禁止看Dev；看过的
  discovery数据不能再用于confirmation；confirmation reward必须先冻结且只用一次。

## 下一步执行顺序

1. 跑完整回归和零付费 synthetic canary。
2. 将 H1 最小能力作为单独版本提交、打 annotated tag、推到用户自己的 origin并生成release receipt。
3. 在 H1 下启动 E1：controller决定本轮动作，至少完成一个有多轮轨迹的实验batch。
4. E1 结束后，Strong Harness 从实际轨迹生成候选；若数据仍是最早瓶颈，再选数据加强，不预先
   保证一定选择它。
5. 选中的唯一改动形成H2并发布；E2只能在H2发布后开始。
