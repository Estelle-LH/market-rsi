# Self-evolving research harness v1

> 这是主 Archive 实验之后的独立研究方向。当前 `A0 → A3` 主实验固定使用已经通过 canary 的
> Codex H0 harness；H1 提案只记录，不启用。

## 研究问题

固定同一个 GLM researcher、任务和预算以后，让 AI 修改帮助自己工作的 inner harness，能不能
让后面的研究更有效、更便宜，并且在新比赛上更好？

Prediction-market forecasting 是实验环境。主要研究对象是 LLM researcher 和它的 harness。

## 两层必须分开

外层 kernel 由人审核并冻结。它管理数据 lifecycle、Dev 和 Transfer 标签、scorer、预算、E2B、
日志、版本和回滚。AI 没有权限修改这些内容。

内层 harness profile 可以由 AI 写。它可以改变研究说明、Archive 检索方式、工作顺序建议和
工具说明，也可以提出并实现新工具。基础工具不能删除；新工具只能请求外层 kernel 已批准的
能力，例如读学习数据、读 Archive、查公开文献、做统计、写 inner workspace 或请求 runner
执行 candidate。它不能通过新工具读取当前 Dev / Transfer 标签、密钥、scorer、任意本机文件，
也不能自行开通网络或付费权限。新工具通过隔离测试和 outer admission 后，最早从下一轮启用。

## 一次自我修改

`H0 → AI 提出 H1 → Codex 写成 profile → 独立测试 → H0/H1 同题同预算比较 → 下一轮才可启用 H1`

H0 和 H1 必须使用同一个 controller model、同一批 Meta-Dev 任务和相同预算。两边的答案都先
冻结，之后标签只打开一次。Meta-Dev 用完后进入学习历史，不能再次用于评价 H2。

第一版同时看：

- 新比赛上的主要预测分数；
- 能真正执行并拿到分数的实验比例；
- 每个有效实验的费用；
- 协议违规数。

只有主要分数更好、有效实验率不降低、单位费用不增加超过 10%、违规为零时，H1 才进入
“下一轮可采用”状态。程序不会自动替换；每个版本和评估 receipt 都要先冻结。

## 当前实现

- `harness_evolution.py` 定义 AI 可以修改的 profile 和不可修改的 kernel。
- `controller_workspace.py` 把当前 profile 作为 controller-visible、hash-bound 输入。
- `controller_provenance.py` 把 harness evolution 代码加入正式源码冻结集合。
- `data_lifecycle.py` 继续负责 Dev 一次评分、评分后转 Train 和 Transfer 一次性开放。

第一版允许 AI 修改 declarative profile，也允许提交隔离的 inner-tool implementation 和权限
清单。新工具必须带源码、输入 schema 和测试 receipt 的 hash；不能在当前 session 热加载。
外层 kernel 始终不开放。
