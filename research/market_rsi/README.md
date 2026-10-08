# Market RSI core source

This directory contains the source-bound research implementation: the durable
research loop, reviewed candidate execution, task evaluation and R/H change
controls. The root `market_rsi/` package provides developer commands; core
runtime modules still live here.

Start with the [current architecture and code map](../../docs/ARCHITECTURE.md),
then the [development guide](../../docs/DEVELOPMENT.md). For earlier designs
and evidence, use the [history guide](../../docs/HISTORY.md).

## What goes in and comes out

The price-discovery entry consumes an explicitly bound batch configuration and
initial feedback. Each round returns reviewed results and reconciled feedback,
memory, research history and candidate-pool state for the next round. Execution
rights and resource limits come from the bound configuration, not this index.

The implemented task is historical NFL five-minute trade-VWAP change.
Equities/earnings is a planned adapter; task scores and trading value require
separate evidence.

## Where to start locally

- [Research entry](supervisor_harness/run_price_discovery.py) and
  [supervisor services](supervisor_harness/README.md): follow one complete round.
- [Data Scientist Harness](data_scientist_harness/README.md): distinguish current
  co-evolution controls from the earlier standalone research tools.
- [Research contribution rules](AGENTS.md): source, data and attribution boundaries.

Historical bindings and experiment records retain their original paths. Consult
the history guide before treating a dated record as a current operating rule.
