# PredictionMarketBench role correction — 2026-09-29

Status: **authoritative strategy correction**. This decision supersedes the
architectural role assigned to PredictionMarketBench (PMB) in:

- `PREDICTIONMARKETBENCH_REPLAN_2026-09-28.md`, SHA-256
  `d08c213ddaec28abd0b7561811c52ad162713f9b3945f6afdb1d4980ef8ad2f4`;
- `PREDICTIONMARKETBENCH_REPLAN_2026-09-28-v2.md`, SHA-256
  `39ad796ff16ce88ea0ad01fb813f07a317b93853467e57625c488d239a7ee0e9`;
- their PMB replan and synthetic-foundation orchestration records.

Those files and their reviews remain immutable historical evidence. Their
contract-integrity PASS results are not scientific validation of PMB.

## Decision

Market RSI withdraws PMB as:

- the primary benchmark or replay foundation;
- a trusted or hidden evaluator;
- a promotion gate or formal Final;
- the architecture driver for the self-evolving loop;
- evidence that a prediction method improved merely because PMB PnL improved;
- the basis for a Controller comparison or swap.

`pmb_simple_lane/` is frozen as an optional, public,
non-trusted compatibility/smoke prototype. Any future PMB run must be labelled
public, diagnostic and overfit-prone. Its PnL, Sharpe, drawdown, fill ratio and
other trading outputs have **zero promotion authority** and cannot substitute
for a prediction score.

The following prospective work is cancelled unless a later, separately
reviewed decision creates a narrow smoke-test need: PMB source/submodule and
dependency intake, episode download, real adapter/runner, PMB hidden Dev/Final,
PMB-based Controller experiments, Controller Swap, aggregate-evidence or Final
policy work, and further PMB receipt/lease governance.

## Why the role changed

The paper/source audit shows that PMB 0.2.0 Alpha is a historical Kalshi
trading replay, not a prediction-first benchmark. It does not require a frozen
probability forecast and does not supply Brier score, log loss, calibration,
incremental predictive value versus the market, Train/Dev/hidden-Final splits,
or a self-iteration research loop. Its public corpus has 33 tickers but only
four highly related January 2026 events, so repeated development is especially
vulnerable to backtest overfitting.

The implementation is also not a security or fidelity boundary for an open
research agent:

1. Agent and simulator share one process. A Python-capable agent can traverse
   the bound `AgentContext` callback or read episode/settlement files to reach
   future order-book, trade and settlement information.
2. Taker fills update the agent portfolio without decrementing the current
   historical order book, so one `act()` can consume displayed liquidity more
   than once.
3. A partially filled crossing GTC order does not reliably rest its remainder
   as documented.
4. The queue model is displayed-size-ahead plus agent FIFO, not the advertised
   pro-rata allocation; latency, real priority, market impact and strategic
   interaction are absent.
5. Portfolio accounting does not enforce cash, collateral, margin or position
   limits.
6. `SimulatorConfig.max_tool_calls_per_step` is not wired into the context,
   which retains a hard-coded limit.

These findings do not make PMB useless. They restrict it to interface and
replay smoke testing under public, non-adversarial conditions.

## Replacement core

The Market RSI causal ladder is:

```text
raw as-of data
  -> raw signal
  -> frozen-cutoff probability prediction
  -> proper-score objective
  -> execution/PnL only after the prediction is frozen
```

The primary prediction evidence is produced over many independent markets and
strict chronological splits. At a precommitted cutoff each candidate must emit
a probability before the outcome or future event stream is available. The
evaluator reports at least:

- Brier score and log loss;
- calibration slope/intercept and reliability diagnostics;
- paired improvement versus the decision-time market probability;
- event/date breadth, concentration and block intervals;
- out-of-sample stability on identical rows.

Previously inspected periods are diagnostic only. Formal promotion requires a
new untouched block with at least 20 dates and sufficient independent events.
Prediction must be frozen before any separate execution or PnL experiment.

## Evaluator boundary

The candidate and evaluator must not share a Python process or writable
filesystem. Candidate execution receives only as-of features, public metadata
and row identifiers. Dev/Final outcomes, future event streams, scorer source,
evaluator state and parent-control files remain in a separate process and
filesystem boundary. The candidate is terminated before host-side scoring.
Dev feedback may update later research memory only in aggregate. Final feedback
never re-enters the research loop.

## Current authority

This correction authorizes local planning, code review and zero-cost synthetic
tests only. It does not authorize PMB or other data intake, network access,
provider calls, paid work, protected split access, real training/evaluation,
release, canary, Git publication or a prediction claim.

