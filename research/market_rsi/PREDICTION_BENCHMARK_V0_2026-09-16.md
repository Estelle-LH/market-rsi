# Prediction benchmark v0：先把要击败的对象定清楚

日期：2026-09-16。状态：**设计与评分器开发版**，尚未冻结数据、运行新的基线或打开封存集。

## 本项目现在只问什么

在同一批未来比赛、同一预测时点和同一价格目标上，一个新方法能否比固定的简单方法和固定的强方法预测得更准？这是**预测**研究，不是交易盈利测试，也不是让 controller 在自己的 Dev 上挑一个好看的数字。其他项目的数据、PnL、研究代理或训练成绩不能填进本项目的榜单。

第一项具体任务是 NFL 比赛事件后的 Polymarket 主队 moneyline 价格变化预测。输入是截至该 play 结束时的历史比赛状态与 play 前市场价格；输出是主队合约价格变化。当前历史 play 的 `time_of_day` 不是提供方发布时间或本机接收时间，因此这只能叫 **historical-response/offline benchmark**。未来若有真实到达时间，再建独立的 **live-availability benchmark**，不能把两者的分数并列。

## 文献怎样改变我们的设计

| 已读原始来源 | 文献/项目实际提供的做法 | 在这里怎么用；不能照搬什么 |
|---|---|---|
| [Hyndman 与 Athanasopoulos，Forecasting: Principles and Practice，§5.10](https://otexts.com/fpp3/tscv.html) | rolling forecasting origin：每次用过去拟合，预测后面的时间；训练残差不是真实预测误差。 | 整场比赛按时间前后切，多次向前滚动；同场 play 不拆到两边。文中的普通单序列示例不自动解决我们的事件时间和标签缺失。 |
| [M4 官方方法与评估仓库](https://github.com/Mcompetitions/M4-methods) | 同一训练/测试集合、公开的简单基线、明确的预测跨度和复现评分代码。 | 固定多种基线、同一批比赛和统一评分器。M4 的 sMAPE/OWA 不适合直接作为接近零的价格变化主指标。 |
| [Monash Time Series Forecasting Archive，指标讨论 §4](https://openreview.net/references/pdf?id=wDPsjZNCW) 与 [Hyndman–Koehler 的误差度量论文](https://robjhyndman.com/papers/mase.pdf) | 报告多个可解释的误差指标；近零/大量零时百分比误差可能误导；跨不同量纲时可用朴素预测缩放。 | 主指标采用相同 0–1 价格量纲下的 MSE，并同时报 RMSE 的概率百分点与相对零变化基线的 skill。MASE 可以在跨目标比较时诊断，但不把各场接近零的分母硬塞进主榜单。 |
| [Diebold–Mariano，Comparing Predictive Accuracy，摘要](https://doi.org/10.1080/07350015.1995.10524599) | 比较两种预测要看成对的损失差，并允许误差有时间相关。 | 保存逐场/逐日的成对损失，用比赛日整块重采样给区间；不把上万条 play 当上万次独立实验。本版不是照搬该检验的渐近 p 值。 |
| [Gneiting–Raftery，Strictly Proper Scoring Rules，摘要与 §1](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf) | 概率预测应由 proper score 评价，校准不能只看分类准确率。 | 若以后预测终场胜率，单开 Brier/log-score 榜；本版预测**价格变化数值**，不把 Brier 与价格 MSE 混成一个分数。 |

文献没有证明我们的市场目标一定可预测；下面的口径是结合当前数据作出的**本项目设计选择**，要由尚未打开的数据验证。M5 的 RMSSE 来源已找到，但网页正文此次无法打开；本版不以它作具体规则依据。

2026-09-16 实际检索词：`Forecasting Principles and Practice time series cross validation rolling forecasting origin benchmark MASE naive forecast`；`M4 forecasting competition benchmark methods statistical evaluation paper MASE OWA PDF`；`Monash Time Series Forecasting Archive benchmark datasets evaluation MASE paper`；`Diebold Mariano comparing predictive accuracy forecasting loss differential original paper PDF`；`Gneiting Raftery strictly proper scoring rules prediction probabilistic forecasts Brier score 2007 PDF`；`Hyndman Koehler 2006 another look at measures of forecast accuracy MASE pdf`；`M5 accuracy competition RMSSE intermittent demand zero forecast official paper`；`Diebold Mariano 1995 comparing predictive accuracy journal business economic statistics PDF`。阅读范围如上表；检索摘要、论文正文和可执行仓库须区别记录。

## 要冻结的任务合同

1. **预测目标与时点。** v0 的主目标沿用先前事前声明的 60 秒价格变化：`home_price(t+60s) - home_price(pre-play)`。价格是 0–1 的主队 YES 合约成交价，不是 bid/ask。`pre-play` 取 play 时点前 300 秒内最后一笔成交；`t+60s` 取该时刻之前 60 秒内最后一笔成交，且它必须晚于 play。没有合格新成交则标签为缺失，**不是 0**。每条 play 必须先列入全集，再记标签是否存在，不能看误差后删 play。30 秒、300 秒是预先声明的次指标，不能选最好的一项替换主目标。若要研究另一个 target，新建 benchmark 版本，不能改写 v0。
2. **数据分层。** 2021–2024 NFL PBP 可帮助训练比赛状态表示；2024 Polymarket 目前只有目录和 12 场成交/时间支持 screen，未通过全季纳入检查，不能说已经是正式训练集。2025 的 163 场 Train 已开放，可反复研究；50 场 Route-Dev 已在旧实验评分一次，今后只是诊断/历史，不再冒充未见数据；40 场 sealed Final 仍未打开。对既有 `game_master.csv` **只读核对赛程元数据**发现这 40 场仅分布在 **11 个独立比赛日**；没有读价格、标签或结果。按本项目至少 20 日期的预定门槛，它最多是 sealed pilot，不能冒充正式 benchmark 确认。更有说服力的最终比较要另冻结后续从未见的时间块。
3. **时间纪律。** 按完整比赛及 UTC 日期向前滚动；每个 origin 的拟合、标准化、特征选择和校准只用当时已知的过去；跨边界的未来标签 purge。每场 play 及两种预测必须使用相同的预冻结 row mask。对于 `state_wp_delta` 等赛后状态特征，还要另记 `event_time` 和 `available_time`；历史 benchmark 能用同一 play 的赛后状态，不能自动宣称它实时可用。
4. **固定基线。** B0 是预测变化为 0 的 persistence；B1 是既有 raw-state `Ridge(alpha=1)`；B2 是旧实验中事前只选一个候选、并在 Route-Dev 评分一次的 `same-event state_wp_delta + Ridge(alpha=1)`。B2 在那 50 场的 60 秒 MSE 是 `0.0016587970`，仅作历史参考。**发表级的正式对手不是 B2**：须先用同一 60 秒目标、相同历史可用输入和 Train rolling-origin 评估 CatBoost、LightGBM 与可合理编码的时序序列模型，选出并冻结 `Strong-Baseline-1`。完整选拔依据、适用限制见[强基线研究](STRONG_FORECAST_BASELINES_2026-09-16.md)。新确认集不能再选对手；B0/B1/B2/Strong 都同场报告。历史时间没有证实实时可用，因此这套对手只适用于离线任务。
5. **主分数。** 对每场合格 play 算平方误差，先在场内平均，再对比赛等权平均。正式比较为 `MSE(candidate) - MSE(Strong-Baseline-1)`，负数更好；同时报相对 gain `1 - MSE(candidate)/MSE(Strong-Baseline-1)`、所有基线的绝对误差、`100 × sqrt(MSE)` 概率百分点 RMSE，以及每场/每日期损失差。10% 和 20% 是我们希望检验的 **MSE 相对改善目标**，不是已达到的成绩；不能误说成 RMSE 改善同样百分比。所有模型必须对**所有预定 play**提交有限预测；只在预先规定的、有可观察标签的行计误差，缺失标签率和各场覆盖单独报告。不得只挑活跃/大波动事件作为主分数，允许事前声明的分层诊断。
6. **不确定性与验收。** 用日期为块成对重采样损失差，保留同日的所有比赛；报告 95% 区间、赢过 Strong 的比赛/日期比例、校准斜率及逐时间段表现。若日期太少，报点估计但标记 *underpowered pilot*。只有在未见确认集上损失差为负、区间上界也小于 0、覆盖及可用性门槛未失败，才说“beat benchmark”。值得投稿还需要同预算普通搜索对照、消融及最好第二个未见时间块，否则不能把改善归因于自迭代。这些是本项目的决策门槛，不是上述文献统一规定的阈值。
7. **防止反复看测试集。** 提交前保存 dataset/source manifest、完整 row IDs、标签生成规则、baseline/candidate 预测、参数、代码 hash、评分器 hash 和事前比较合同。每次打开 Dev/Final 都记永久回执。已看过的区块只能进入下一轮 Train/Archive；最终封存集仅在全部规则锁定后使用一次。失败、缺失和所有尝试都保留。

## 第一张榜单长什么样

| 方法 | Train rolling MSE | 未见确认 MSE | 相对 Strong 的 gain | RMSE（概率百分点） | 覆盖/场次/日期 | 结论 |
|---|---:|---:|---:|---:|---|---|
| B0 不变 | 待同口径重算 | 未打开 | — | — | — | 基础参照 |
| B1 raw-state Ridge | 待同口径重算 | 未打开 | — | — | — | 线性参照 |
| B2 state-delta Ridge | 待锁定预测文件 | 未打开 | — | — | — | 旧 Dev MSE `0.0016587970` 仅作历史参考 |
| Strong-Baseline-1 | 待 Train-only 选拔与冻结 | 未打开 | 0 | — | — | 正式要击败的线 |
| 自迭代候选 | 待提交 | 未打开 | 未知 | — | — | 只与同一批行上的 Strong 比 |
| 同预算普通搜索 | 待设计 | 未打开 | 未知 | — | — | 检查收益是否真来自自迭代 |

现有 60 秒 Ridge 在旧 50 场 Route-Dev 上有一次性结果，但那不是这张新榜单的“未见确认”栏。2026-09-16 的 30 秒 HGB `0.0007949689` 也只属于已开放 Train 的另一目标，不能跨 target 填进表。

## 现在还缺什么才叫 benchmark v1

40 场 Final 的日期数已从赛程元数据核对为 11；还需在不读 sealed label 的条件下审计其来源完整性和 cohort commitment。先在已开放 Train 上公平选拔 `Strong-Baseline-1`，再把 B0/B1/B2/Strong 的 60 秒训练方案与预测文件锁定；确认历史事件/成交时间语义。40 场继续保留作 sealed pilot，另冻结后续至少 20 个比赛日的时间块作正式 benchmark。当前文件只是 v0 设计，**没有强基线选拔成绩、没有新 benchmark 成绩，也不授权打开 Final、付费训练或购买数据**。

开发版评分器 `prediction_benchmark_v0/score.py` 已实现完整 row-key 匹配、B0 恒为零、基线和候选预测文件 SHA256 核对、训练截止日早于评分日、缺标签不补零、逐场等权 MSE、RMSE 概率百分点、逐日 paired loss 和日期块区间。主比较现对 `Strong-Baseline-1`，不是 Ridge。调用方仍须提供一次性封存 gate；这个函数本身不是访问控制。9 个合成单测通过，包括“赢 Ridge 却输 Strong 不算通过”、改动预测、时间重叠、缺行、缺标签和不足 20 日期；尚未用真实封存数据验证。正式发布前还需要把预测生成、cohort/hash、一次性开封和评分器绑定成同一个版本化运行合同。
