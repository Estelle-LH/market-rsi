# Market RSI core source

This directory contains the source-bound research implementation: the durable
research loop, reviewed candidate execution, task evaluation and R/H change
controls. The root `market_rsi/` package provides developer commands; core
runtime modules still live here.

Start with the [current architecture and code map](../../docs/ARCHITECTURE.md),
then the [development guide](../../docs/DEVELOPMENT.md). For earlier designs
and evidence, use the [history guide](../../docs/HISTORY.md).

## What goes in and comes out

The co-evolution entry consumes an explicitly bound batch configuration and
initial feedback. Each round returns reviewed results and reconciled feedback,
memory, research history and candidate-pool state for the next round. Execution
rights and resource limits come from the bound configuration, not this index.

The active research target is equities earnings events. Its point-in-time data,
forecast target, baselines and trading-value scorer are still being added. The
implemented NFL/prediction-market task remains a legacy replay path; its scores
and trading value do not transfer to the earnings claim.

## Where to start locally

- [Co-evolution entry](supervisor_harness/run_price_discovery.py) and
  [supervisor services](supervisor_harness/README.md): follow one complete
  round. The `price_*` filenames in that directory are historical names kept
  for source and replay compatibility.
- [Data Scientist Harness](data_scientist_harness/README.md): distinguish current
  co-evolution controls from the earlier standalone research tools.
- [Research contribution rules](AGENTS.md): source, data and attribution boundaries.

Historical bindings and experiment records are preserved in the local recovery
archive rather than mixed into the active source tree. Consult the history
guide before treating a dated record as a current operating rule.

For ongoing refactors, classify a change before moving it and follow the
[code-structure maintenance contract](../../docs/CODE_STRUCTURE_MAINTENANCE.md).
