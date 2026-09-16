# 强预测基线：不能只拿 Ridge 当论文对手

日期：2026-09-16。状态：文献选择与实验设计，**不是这些模型已在本数据上跑出的成绩**。

## 要解决的问题

旧 60 秒任务里，`state_wp_delta + Ridge` 是认真做过一次 Route-Dev 的候选，但它不一定代表现代时序预测的强度。若自迭代系统只是击败它，无法说明自迭代比一个足够强、经过公平调参的预测方法有价值。本轮只改变 benchmark 的**对手选择设计**，不碰已封存数据、旧分数或目标。

## 2026-09-16 公开检索与实际阅读

检索词：`N-HiTS neural hierarchical interpolation time series forecasting paper arxiv irregular time series covariates`；`Temporal Fusion Transformers interpretable multi-horizon time series forecasting 2021 paper covariates`；`LightGBM A Highly Efficient Gradient Boosting Decision Tree NeurIPS 2017 paper time series tabular`；`CatBoost unbiased boosting with categorical features NeurIPS 2018 paper`。

| 原始来源与阅读范围 | 它证明什么 | 转到本项目的限制 |
|---|---|---|
| [CatBoost，NeurIPS 2018，摘要及 ordered boosting §4–5](https://proceedings.neurips.cc/paper_files/paper/2018/file/14491b756b3a51daac41c24863285549-Paper.pdf) | ordered boosting/类别处理可减少特定的 prediction shift；公开数据上有竞争力。 | 这**不**消除我们的跨比赛、跨日期或未来信息泄漏。若使用历史 play/交易 lag，仍须由外层时间切分和 feature availability 审计。适合做事件表格强基线候选。 |
| [LightGBM，NeurIPS 2017，摘要](https://papers.neurips.cc/paper_files/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html) | 高效 GBDT，面向大量表格特征。 | 不是专门的非规则事件序列模型；必须给它同样的仅过去 lag/状态输入。其论文的速度/准确度不是本项目数据上的保证。适合另一个强表格基线候选。 |
| [Temporal Fusion Transformer，作者预印本摘要](https://arxiv.org/abs/1912.09363) | 将静态、历史可观察和已知未来变量分开，面向多跨度预测。 | 我们的 play 不等间隔、当前只确定 60 秒单一主目标；需要另做 event-sequence 编码和足够数据的能力检查，不能直接套公共 regular-grid 分数。可列为深度时序压力测试，不强制它赢。 |
| [N-HiTS，AAAI 2023，方法及实验](https://ojs.aaai.org/index.php/AAAI/article/download/25854/25626) | 在规则采样、长跨度预测数据上用多速率采样与插值取得好的结果。 | 当前目标是非规则的逐 play、60 秒市场反应；先变成规则网格会改任务或增加缺失插值。**本版不直接把 N-HiTS 当主对手**，除非另起严格同信息的表示实验。 |

这里只是 `found/read`。没有把任何论文声称的优势当成 `validated on our data`。TFT 出版社页此次打开失败；只使用作者预印本摘要作模型定位，没有声称已读完整技术细节。未来若真正实施 TFT，应再读方法正文与软件实现合同。

## 公平的强基线选拔

先在**已开放 Train** 内，把零变化、已有 `state_wp_delta + Ridge`、CatBoost、LightGBM，以及可执行且不需改目标/样本的时序序列模型放到同一张表。所有方法使用相同 60 秒标签、完整比赛 cohort、相同历史可用信息、滚动时间起点、训练预算与调参预算。对深度序列模型，输入转换不得把缺失 play/交易补成零标签；若 adapter 做不到，记为未执行而不是差分数。超参数候选数、训练时长和失败也要入账。

在 Train rolling-origin 上按**事前规则**选一个冠军，命名 `Strong-Baseline-1`。冻结它的模型、数据窗、feature、target、种子、完整预测和成本后，才允许它与自迭代系统在更晚的同一批未见比赛上成对评分。零变化与 Ridge 仍作为解释性地板，但不是“发表级”正式对手。旧 50 场 Route-Dev 已看过，不可用于这次冠军选拔后的独立确认；2025 sealed 40 场只有 11 日期，最多是 pilot。

## 值得写论文的结果应长什么样

核心数字为 `gain = 1 - MSE(RSI) / MSE(Strong-Baseline-1)`，按比赛等权、同一批有标签的 play、同一目标计算。我们以 **10%** 作为有意义的目标、**20%** 作为更强的目标；这不是承诺，也不是文献规定的通用发表门槛。例如强基线 MSE 为 `0.0010`，自迭代为 `0.0009` 才是 **MSE 降 10%**；这不等于 RMSE 降 10%。

仅有这个百分比仍不够：新时间块至少 20 个比赛日、成对日期块区间支持改善、覆盖率和校准不恶化、多个时间段都有收益；记录所有尝试。还要和**同计算/同数据预算**的普通手工或自动超参搜索相比，并做去掉 Archive/反馈选择的消融。否则提高可能来自更多试验、更多数据或更强模型，而不是“自迭代”。若新方法用了额外历史数据，另做同数据 baseline 重训，把“数据收益”与“迭代方法收益”拆开。最好再有第二个未见赛季或任务重复方向；单一 11 日期 pilot 不能支撑论文主张。

当前真实状态：尚无 `Strong-Baseline-1`，没有 10%/20% 结果，未开 Dev/Final，也未启动付费模型。下一步是实现同信息的强基线选拔 runner，在已开放 Train 上跑出基线，然后冻结新的时间段。不能把现有 30 秒 HGB MSE 和 60 秒 Ridge MSE直接比较。

## 确定性第一步：只换 trainer，不改数据和目标

先复用现有的 2025 Train 163 场、60 秒目标和历史 NFL 状态模型，固定 `state_wp_delta` 一个表示；对 `Ridge(alpha=1)`、现有固定参数 Random Forest、现有固定参数 Histogram Gradient Boosting 做同样 3 个 21 场向前滚动块。所有算法的种子、参数、fit 权重、row mask、缺失标签政策和预处理都在 score 前锁定；不根据第一个结果临时加模型。此比较只改 **trainer**，不能同时加 2024 数据、改 30 秒目标或加新 lag。它的目的不是立刻产生论文结果，而是先确认不用自迭代、只靠标准确定性方法，60 秒基线能提高多少。

旧 `state_wp_delta + Ridge` 在 2025 Train 的已开放三个块为 `0.0016700963`，在旧一次性 Route-Dev 为 `0.0016587970`。这些是不同 cohort 的历史记录；新 runner 必须先在同一 Train cohort 复现前者，随后才能把 RF/HGB 的差写成 trainer-only 变化。CatBoost/LightGBM 当前本机运行环境未安装，TFT还需 event-sequence adapter；因此第一步不是把缺失的模型假装已测。它们进入后续**单独版本化**的强基线扩展。所有 Train 结果只供选拔，不是新独立测试。

## 第一轮实际结果：Opened-Train，2026-09-16

运行源码已锁定并只发布到用户自己的 origin：commit `abc7f6f45b6dc5b96d30d761bf0c6c146803ec6e`、annotated tag `dsh-v1.6.12`；release receipt SHA256 `317609f38ff4471ff67030befc417a6ae3e24014f9ddf45aeea40ffcb587bc28`。真实运行前锁 `artifacts/nfl-deterministic-60s-baseline-20260916-01/pre_score_lock.json` 的 SHA256 是 `c4cfc2813792844bf9d455cbe2219c781442938141a659bfcec78db5ef7ea340`，结果 SHA256 是 `208fc04b08c8f63f8d595a2c9621fd4c2dc21af1ee853fd82a724ceb5e2feb80`；0 Tinker，0 Dev/Final。

同一批 163 场中，最初 100 场 fit，随后三个各 21 场的前滚 check，共 63 场、9,615 条有标签 play、21 个 UTC 日期。逐场等权的 60 秒 MSE：

| 固定方法 | 3 个 Train check 块合计 MSE | 相对旧 state-delta Ridge |
|---|---:|---:|
| 零变化 | 0.0020001183 | 只作参照 |
| state-delta Ridge | 0.0016700963 | 旧值精确复现 |
| Random Forest | 0.0014083304 | 低 15.7% |
| Histogram Gradient Boosting | 0.0013540355 | 低 18.9% |

HGB 在三个块的 MSE 分别为 `0.0015672906`、`0.0013853027`、`0.0011095134`，各自低于同块 Ridge 和 RF。按照运行前写死的最小 Train MSE 规则，选 HGB 为**第一版固定挑战基线候选**。这是普通、可复现的 trainer 改进，不能归功于 self-iteration；旧 50 场 Route-Dev 不重新当独立确认，40 场 Final 仍封存。不能把 18.9% 写成未来比赛的提升。

时间可用性也仍有限制：`state_wp_delta` 来自同一 play 的历史 `end_situation`，现有档案不能证明该状态在真实交易决策时已经收到。所以上表是**历史事件条件下的 60 秒市场反应预测**，不是可交易的实时收益或已验证的实时预测。最终基线与自迭代方法必须在同一信息截止点比较；若转为实时任务，要先做 live receive-time 审计并重新建基线。

下一步仍要用相同信息、同预算把 CatBoost/LightGBM 等强表格方法加入 Train 选拔，记录普通超参搜索预算，然后冻结 `Strong-Baseline-1`。自迭代系统可以跨轮提出不同特征和算法，但每个候选的结果要和同数据、同计算预算的固定搜索对照并列。只有足够新的、从未用于设计的时间块才能给独立结论。
