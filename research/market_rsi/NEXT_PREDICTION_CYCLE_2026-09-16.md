# 下一轮预测实验：先固定强对手，再让研究代理迭代

2026-09-16。此页是执行计划和本次实际交接结果，不是新的模型提升报告。

## 现在真实到哪一步

- 离线 60 秒任务的 2025 opened-Train 前滚检查上，固定 HGB 的逐场等权 MSE 为
  `0.0013540355`；旧 state-delta Ridge 为 `0.0016700963`。18.9% 是普通确定性方法的
  **Train-only** 差，不属于自迭代，不能推断到未见比赛。
- 昨天讨论的交替状态机、Archive、新算法提案、Dev 前冻结 reward 和一次性 Dev gate 已有
  代码与测试。它们尚未组成一个已经持续训练的正式 `E1 → H2 → E2` 实验。2024 只有
  12 场来源 screen；60 秒标签历史覆盖 1,400/2,027（69.1%），未准入多赛季 Train。
- 本次人为发布的 `dsh-v1.6.13` 仅把 HGB/Ridge 汇总、数据缺口和时间语义交给一个
  aggregate-only GLM controller。发布 commit `39a03fa5da875bd8d19cc68fd89ff7487912b4ea`，
  release SHA256 `3278e3c5a91768af3a1d0b564420b04025d9fc78ba3c59168cab9c533cf47406`。
  Controller run `nfl-60s-baseline-controller-20260916-01` 有效结束：11 turns、14 tools、
  0 fit、0 Dev/Final、无未结算调用。本次 provider-metered 增量 `$0.439231248`；
  `$8.44038144` 是启动前的最大预留，不是花费。

## Controller 做了什么、没有做什么

它读了基线汇总和公开 CatBoost 摘要，归档一个
`hist_gradient_boosting_permutation_subsample_option` capability，然后 defer。它明确说这是
未激活的建议，不能把 18.9% Train 差算作新算法收益；这条边界是对的。

但提案**尚不可执行**：它只读摘要，没有读 ordered boosting 的方法和实现部分；建议的
“每轮随机一半建树、另一半赋叶值”是项目自拟近似，不是已验证等同于 CatBoost Ordered 模式。
提案正文还把当前 NFL 任务误写成 basketball。这两点必须作为 controller/harness 的失败轨迹
保留，不能悄悄修正文案后宣布算法已获支持。原始轨迹在
`artifacts/nfl-60s-baseline-controller-20260916-01/records/0012.json`。
重新阅读 [CatBoost 原论文 §4–5](https://papers.neurips.cc/paper/7898-catboost-unbiased-boosting-with-categorical-features.pdf)
可见 ordered boosting 涉及按排列前缀构造估计与更复杂的实践实现；因此不能凭摘要把该半分法
当成论文算法。官方 [CatBoostRegressor 文档](https://catboost.ai/docs/en/concepts/python-reference_catboostregressor)
提供已实现、可复现的回归器。这里是对提案可执行性的判断，不是本数据上的性能结论。

## 接下来按这个顺序执行

1. **数据/时点检查，先不训练。** 在已经开放的 2024 样本里，把 60 秒标签缺失拆成
   “play 前无近 300 秒成交”“play 后 60 秒无成交”“时间/资产映射问题”；按整场、比赛日
   报覆盖和来源 hash。另把 play event、provider publish、本机 receive、可作决策时间
   分开；未知就标未知。不能以缺失标签为 0，也不能把历史 end-state 当成已证明的 live 输入。
   这一步只改变 `data_quality/availability`，不拿 MSE 选算法。已有 12 场的逐场回执显示
   60 秒覆盖从 27.1% 到 97.0%，同时成交数从 220 到 3,880；这提示交易稀疏度可能是
   缺标签的重要来源，尚未拆出确切原因。不能为了达到 90% 门槛只留下活跃比赛，
   否则任务/样本被悄悄改变；若 60 秒 trade-price 标签本来就不适合多赛季，应在
   opened Train 上明确比较更长 horizon 或合法 quote 数据，另建版本并重建全部基线。
2. **固定对手。** 在同一 60 秒目标、同一行、同一信息截止点和事先规定的 CPU/搜索预算下，
   将 HGB 与真正的 CatBoost/LightGBM 等成熟实现比较。只用 opened Train 前滚选一个
   `Strong-Baseline-1`，记录模型文件、全部预测、参数、运行成本和 hash；不在已消费的
   Route-Dev 上反复挑冠军。若新数据被准入，所有对手都要在同一扩展 Train 上重训。
3. **研究代理内层迭代。** 使用同一个已发布 Harness、同一个已开放 Train 和固定试验预算。
   GLM 可以逐轮提出不同的特征、表示、trainer 或有完整来源的新算法；每个候选先写
   parent、唯一 changed stage、预测方向、支持/否定条件和消融，再执行一个有限 CPU fit。
   每轮保存查询/正文阅读、输入、代码与参数 hash、逐行预测、逐场/逐日 paired MSE、
   校准、失败及实际费用。保留全部尝试，不只保留冠军。并行运行同预算的普通固定搜索，
   以免把“多试了模型”误说成“自迭代有效”。
4. **外层 Harness 迭代。** 至少完成一个可审计内层 batch，或出现明确阻断，Codex 才从完整
   轨迹提出多个 Harness 改进候选。一次只发布一个有 replay、正反 canary、版本 tag 和
   release receipt 的改动；然后开始下一 batch。上述抽象阅读不足和任务域写错，是这一轮
   必须进入候选池的观察，但不自动指定最终 patch。
5. **一次性新时间检验。** 只有 baseline、候选、reward、cohort 和打分器都锁定后，才使用
   至少 20 个此前未见的比赛日作主要确认。旧 50 场 Route-Dev 已消费；现有 40 场
   sealed Final 只有 11 日期，最多作单独标明的 pilot。主张看 candidate 对强基线的
   同场等权 MSE 差及日期块区间，而不是仅赢 Ridge 或 Train。

第 1 项对已选 12 场的只读诊断已完成；下一项是完整候选 cohort 的来源/覆盖审计，
第 3 项的自动训练仍未启动。提案中的
“半分 HGB”保持 Archive 状态，不写入 frozen trainer。总 Tinker 上限仍是旧 `$200`，
本轮开始后的账本有效成本 `$88.690028480`、预留 `$2.30`、可用 `$109.009971520`；
learning bucket 可用额需每次 dispatch 前重读，不能以总可用额替代。

## 第 1 项实际结果与随之收紧的下一步

只读数据诊断以 `dsh-v1.6.14` 发布源码运行，精确 commit
`1e1b1e39827b0ec3ffb31150415be63542b14f68`、release digest
`f126417255bbf953d5582b84f5101117d5e6e85919af6c4d352f76d4a4b1d343`。
结果在 `artifacts/nfl-2024-60s-missingness-20260916-01/result.json`，其文件 SHA256
`e5008058aa50612c31a5d8ce8b98260f628b94071096af92d6c04c901ca00a1b`。
12 场已选样本中，2,027 个有时间 play：1,400 个有 60 秒标签，549 个在
play 后 60 秒内无新成交，78 个 play 前最近成交超过 300 秒，0 个从未有 play 前成交。
互斥类别逐场及总体均与原覆盖回执一致。0 模型 fit、0 provider 费用，未打开 Dev/Final。

这把当前 627 条缺标签的主要**直接原因**定位为 60 秒内没有新成交（549/627，
87.6%），而不是单纯缺 pre-play 成交。它不证明 2024 全赛季的覆盖率，也不排除
尚未检查的 outcome 映射或真实信息到达延迟。不能通过只留成交密集的比赛把该样本
“修好”。同一 12 场的 300 秒历史覆盖为 1,885/2,027（93.0%），但换成五分钟
就是一个新目标，不能与现有 60 秒 MSE 直接比较。

因此下一项应先对**事前确定的全赛季候选 cohort**做相同的来源/覆盖审计；若 60 秒
继续明显缺标签，可在只看 Train 来源和标签分布的前提下，预先登记 300 秒或合法
quote-based 目标作为新 benchmark 版本，重跑包括零变化、HGB、CatBoost/LightGBM
在内的所有强基线。之后才允许固定 Harness 的研究代理做有限的 Train 内层迭代。
目前没有新模型 self-iteration 分数，不能说已达到比强基线高 10% 或 20%。
