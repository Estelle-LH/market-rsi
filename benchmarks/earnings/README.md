# Earnings / EDGAR task scope

The current experiments forecast financial-statement targets from information
available at a frozen cutoff. The public tree contains the reviewed earnings
research adapter and its synthetic tests; the original dataset and empirical
scorer checkout remain local. This page describes task scope, not permission
to collect data, call a model or trade.

## What the reported experiments measure

Each frozen candidate is evaluated on 25 training companies, with 5 targets per
company. The recorded scoring convention awards 0, 0.5 or 1 per target; each
company is out of 5 and the panel mean weights companies equally. A percentage
of possible fractional-award points is not binary accuracy.

[Experiment 1](../../docs/experiments/experiment-01-open-research/README.md)
is the source of the current advisor report.
[Experiment 2](../../docs/experiments/experiment-02-framework-restart/README.md)
has a separate baseline, source/state and accounting. Reused TRAIN25
improvements are adaptive Discovery, not pristine heldout or trading evidence.

## What is published?

[tools/earnings_population.py](../../tools/earnings_population.py) and its
continuation/role modules implement the reviewed population and feedback
contracts. [tools/earnings_open_program.py](../../tools/earnings_open_program.py)
parses candidate metadata on the host; actual untrusted program execution
belongs to the authorized isolated runtime.
[The earnings development guide](../../docs/EARNINGS_DEVELOPMENT.md) maps the
source and offline tests.

The public snapshot does not contain the later full experimental campaign,
original task bodies/answers, scorer, credentials or ready-to-run funding and
authority bindings. See [Reproducibility](../../docs/REPRODUCIBILITY.md) before
trying to reproduce a report score.

## Keep future market/trading tasks separate

Predicting earnings surprise or post-announcement price response, and testing
a trading position/exit rule, are separate future task contracts. Financial
target scores above do not measure either trading value or profitability.

A future market/trading adapter must freeze event identities/timestamps,
point-in-time inputs, horizons, splits, market/consensus/persistence baselines,
scoring, missing/revision handling and minimum coverage. Trading evaluation
also needs spreads, fees, slippage, holding windows and exposure limits. Such
a task change needs its own data/scorer and authority review; it is not
silently substituted into the current financial forecast.

## Boundary with the engine

The task adapter owns rows, labels, baselines and scoring assumptions. The
Supervisor engine owns review, execution, feedback, memory, R/H selection and
rollback. An R/H change cannot rewrite the protected task or scorer, and an
offline fixture cannot be presented as a financial result.

Read [Architecture](../../docs/ARCHITECTURE.md) for the mechanism and
[Quickstart](../../docs/QUICKSTART.md) for the first runnable public example.
