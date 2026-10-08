# Data Scientist Harness

This package combines current co-evolution contracts with an earlier standalone
data-science workbench. These are distinct call paths: the current price loop
imports the small-step controls, while the older broker/controller tools retain
their own workspace, tool and release procedures.

Read the [current architecture](../../../docs/ARCHITECTURE.md) for the system
flow, the [development guide](../../../docs/DEVELOPMENT.md) for checks, and the
[history guide](../../../docs/HISTORY.md) for earlier integrations.

## Current use: small-step R/H controls

[co_evolution_loop.py](co_evolution_loop.py) builds hash-bound change records.
Its micro-evolution API takes a fixed context, a harness/researcher pair and
explicit write scopes; it records one provisional change, independent review,
acceptance/rejection and rollback. The other axis stays fixed.

The price handoff, capacity-activation and continuous-batch services in
`../supervisor_harness/` call these functions. Their outputs are lineage/state
records, not executed patches. Trusted callers must verify actual changed files
and evidence, persist the records and perform any permitted activation.

## Earlier workbench: research tools and checked fitting

Start at [broker.py](broker.py) to inspect the registered tool interface and
[run_controller.py](run_controller.py) for its separate session entry.
The workbench consumes a frozen workspace, research intents, data contracts and
training plans. It writes tool records, trial predictions, quality reports and
research traces.

Its local components include:

- [literature.py](literature.py): bounded public metadata search and HTML/text
  reading, with source and read-range records.
- [profiles.py](profiles.py), [sanity.py](sanity.py) and
  [checked_learning.py](checked_learning.py): statistics and declared quality
  checks around feature generation, normalization, fitting and scoring.
- [worker.py](worker.py), [store.py](store.py) and [trajectory.py](trajectory.py):
  bounded CPU trials and intent/result/reflection history.

The quality adapter uses an explicit UTC millisecond grid, not recovered raw
event order or exchange-session timing. Its pinned shared dependency is
documented in [ds_harness_core](../ds_harness_core/README.md). Contract checks and
synthetic canaries do not certify a real data source or prediction improvement.

## Historical setup and operating details

The [original workbench README at the published parent commit](https://github.com/Estelle-LH/market-rsi/blob/03d31a01bcf7bab01534379acdc5cde6322377ed/research/market_rsi/data_scientist_harness/README.md)
preserves the detailed setup, tool catalog, release/canary procedures, workspace
record layout, source/temporal contracts, sports-event guidance, one-shot Dev
procedure and known limitations. Those instructions belong to that historical
workflow; they do not select current role models or launch the price loop.
