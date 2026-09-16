# Market RSI：预测研究

**当前研究问题：**在未见的未来比赛上，能否把 NFL prediction-market 价格变化预测得比一个充分调过的强时序基线更准？本项目只比较预测准确度；其他项目的交易收益、研究代理能力和训练分数都不是这里的 benchmark。先看 [Prediction benchmark v0](PREDICTION_BENCHMARK_V0_2026-09-16.md)和[强基线选拔研究](STRONG_FORECAST_BASELINES_2026-09-16.md)：零变化/Ridge是参考线，正式对手须在开放 Train 上公平选拔、冻结。配套 [开发版评分器](prediction_benchmark_v0/score.py)目前只用合成数据验证；它没有打开封存集，也不是新模型成绩。

目前 2025 年的 163 场 Train 已开放、旧 50 场 Route-Dev 已经用过一次，40 场 Final 仍封存；赛程元数据表明 Final 只跨 11 个比赛日，按当前规则最多算 pilot。2024 年来源扩展还只是 [数据 screen](NFL_2024_DATA_EXPANSION_SCREEN_2026-09-16.md)，并未进入正式训练。现有的 30 秒 Train-only 方法分数不能直接填到 60 秒新 benchmark 榜单。历史 play 时间也不是实时接收时间，因此离线预测与未来的实时预测分开报告。

## 历史研究代理记录（非当前预测 benchmark）

**Historical controller:** [Codex-harnessed controller v3](CONTROLLER_HARNESS_V3.md).
The new NFL event-data direction, Train-only data audit, and controlled method
library are specified in [Sports self-evolution design](SPORTS_SELF_EVOLUTION_DESIGN_2026-09-15.md).
Its frozen chronological Train/Dev/Test rules are in
[Time-series evaluation policy](TIME_SERIES_EVALUATION_POLICY.md).
Before any new model round, the controller now runs the separate
[time-series objective-discovery harness](TIME_SERIES_RESEARCH_HARNESS.md).
The September 8 implementation and real Train-only findings are summarized in
[Objective discovery MVP](OBJECTIVE_DISCOVERY_MVP_2026-09-08.md).
The next experiment is specified in
[Archive self-improvement experiment v1](ARCHIVE_SELF_IMPROVEMENT_V1.md).
The completed Round-1 pilot and v2 engineering canary showed that the one-shot
controller interface was too restrictive to measure research ability. V3 keeps
GLM-5.3 as the research decision maker, gives it a bounded multi-turn Codex
workbench, and allows 64K input and 64K output per model turn under a separate
session-wide token cap. The fixed-H0 two-session Archive carryover canary passed
on September 8. A0 `controller-harness-formal-canary-20260908-04` started from
an empty Archive; A1 `controller-archive-carryover-canary-20260908-01` read A0's
complete record, wrote and executed a new candidate whose exact parent was A0's
selected source, and submitted it successfully. The two snapshots form a
verified hash chain, Future Test stayed sealed, and post-run E2B inventory was
zero. This proves the Archive mechanism and ancestry tracking, not
research-performance improvement.

The next experiment has one cross-task memory policy: **Archive only**. It keeps
the controller's own complete, execution-verified research record. The former
Learn arm and controller-written learned guide are retired. A fixed, read-only
research guide remains part of the harness instructions; it is not a learning
mode. Literature searches and algorithm work are recorded in separate,
append-only hash-chain logs and cross-checked against the general tool journal.

**Previous experiment:** [Kalshi research-agent protocol](PILOT_PROTOCOL_2026-09-07.md).
Authorized September 7: GLM-5.3 research controller, Codex coding, existing
Tinker/Harbor/E2B infrastructure; aim $100, combined new-spend hard cap $200.
Compare reset, raw-archive and archive-plus-learned-guide researchers on real
market tasks. Data/isolation canaries precede scored work. See STATUS.md.

Everything below is the archived, superseded prototype description. It must NOT
drive new paid runs. The internal betting market and MLAgentBench-first scope
were a misunderstanding; their fixtures remain only as software-test history.

## Archived prototype

Question: can an LLM researcher learn from experiments and do better on new
research tasks? Does a prediction market help more than averaging forecasts?

Current priority: a small existing research-agent benchmark first. Trading PnL
and a standalone benchmark release are deferred. The internal prediction market
selects research experiments; those tasks need not involve financial markets.

Start with [the research protocol](RESEARCH_PROTOCOL.md). The three arms are a
researcher without carried experience, one that learns from its own experience,
and one that learns with market-based experiment selection. New tasks start
from identical downstream baselines; only researcher experience carries over.

The sections below describe the existing **within-task component**, not a
completed LLM study. The former predictor-centric framing is superseded by the
research protocol. No real LLM-learning result has been measured yet.

This is an isolated research project. No orders, production changes, Tinker jobs,
or new paid API calls are authorized by this implementation. Existing subscription
usage and local compute are not described as free; new provider charges require
a separate cap. The original sports project is read-only.

## What changes, and what does not

The researcher can propose training data, features, model/trainer settings, and
learn from previous development results. Proposals state their causal stage;
each A/B isolates one stage. The evaluator owns labels, eligibility, chronological
splits, the scoring rule, and the final holdout. A researcher cannot change them
to make a candidate win. A later compound proposal needs component ablations.

The first downstream learner is a small market predictor, not a newly fine-tuned
Qwen LLM. The planned outer LLM learns through versioned research memory; its
weights stay fixed. Live memory updates are not connected yet. Do not claim
recursive weight self-improvement from this pilot.

## The loop

1. Audit source data, reconstruct a baseline, and freeze train/development dates.
2. Freeze a small slate of candidate plans from one parent.
3. Commit private forecasts and virtual-market trades before model evaluation.
4. Execute every admitted candidate. Unexecuted/failed candidates have unknown
   scientific outcomes; they are not scored as bad forecasts.
5. Score baseline and candidates on exactly the same rows. Report Brier loss,
   AUC, and precision/recall at the same alert fraction, including game/date
   breakdowns. Candidate success means strictly lower development Brier loss.
6. Compare precommitted single-forecaster, average-forecast, and market choices.
   A price <= 0.5 keeps the parent. Ties keep the parent after observed scoring.
7. Return permitted development feedback to research memory and repeat.
8. Freeze the final choice before a later holdout. Two days are preliminary;
   promotion requires at least 20 untouched sessions and the evaluation gates.

Round-two comparisons share the visited parent; they are not independent
end-to-end RSI trajectories for each selector. Six proposals cannot establish
general superiority of prediction-market selection.

## Evidence and anti-hacking

- Use actual information-arrival timestamps, not retrospective event times.
- Split whole games chronologically; two dates containing the same game stay
  in one split. Purge labels crossing the next split's boundary.
- The same frozen evaluation mask applies to every candidate. No cherry-picking
  easy games, blank predictions, or invalid snapshots after seeing results.
- The runner stores plans, forecasts, source/code hashes, per-row predictions,
  outcomes, candidate failures, and an append-only hash-chain journal.
- Virtual market balances are bounded, identities fixed, and every trade kept.
  This is not a guarantee against collusion or strategic manipulation.
- Filesystem hashes detect accidental changes, not an adversary with the same
  OS account. External researcher isolation is a separate unfinished gate.
- Cash reserved, actual charges, token-based estimates, and unknown costs remain
  separate. Finishing a job releases its reservation; it does not spend it.
- A quote move is not a filled trade. No P&L or successful-cancellation claim
  without account-level execution evidence.

## Current source status

2026-09-06: read-only SSH to the project's Linode succeeded. September 5 source
files and manifest are present. September 6 was still being finalized during
inspection. Presence is not a complete data-quality audit.

Private reference repository branch `codex/real-nfl-venue-race` resolves to
`cdb3b0f108ff080626817fe393b41bd700b98014`. Its tree does not contain the recent
September 1 MLB or August 31 NFL model scripts. Local directories also lack those
scripts. Previously reported AUC 0.879/0.888 values are historical reports, not
reproduced results of this framework. Do not silently substitute a new model and
call it the old baseline.

## Execution status

See `STATUS.md` for the current result and next action. Tests and the fixture
smoke run use fabricated observations and are never market research evidence.

Run from this directory:

```sh
python3 -m unittest discover -s tests -v
python3 smoke.py --output /absolute/path/to/a/new/fixture-run
python3 study_smoke.py --output /absolute/path/to/a/new/study-fixture-run
```

No third-party Python dependency is required by the control-plane tests.

The second command checks within-task predictor inheritance; the third checks
the new three-arm researcher study and resets between tasks. Both use fixtures.
