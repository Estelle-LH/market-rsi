# Research history and compatibility

Use [Architecture](ARCHITECTURE.md) to understand the published price-research
pipeline and [Development](DEVELOPMENT.md) to work on it. This page distinguishes
that implementation from earlier designs and private operational records.

## Read earlier designs in their original context

- [Earlier architecture](../research/market_rsi/ARCHITECTURE.md): September's
  probability/D0, GLM and local-B design, including its original trust boundaries.
- [Prototype research protocol](../research/market_rsi/RESEARCH_PROTOCOL.md):
  the archived three-arm study; its header records the superseded status.
- [Data Scientist Harness original README](https://github.com/Estelle-LH/market-rsi/blob/03d31a01bcf7bab01534379acdc5cde6322377ed/research/market_rsi/data_scientist_harness/README.md):
  preserved tool capabilities, source semantics and older setup/canary commands.
- [Original development and migration notes](https://github.com/Estelle-LH/market-rsi/blob/03d31a01bcf7bab01534379acdc5cde6322377ed/docs/DEVELOPMENT.md):
  the proposed future package layout, compatibility rationale and staged cleanup
  plan before documentation was separated by responsibility.
- [Harness version history](../research/market_rsi/HARNESS_VERSIONS.md):
  source/version changes and evidence tied to their own experiments.

These records explain their recorded source snapshots. Their old model names,
data objectives, readiness statements, paths and grants do not describe or
authorize a new run. Keep original experiment definitions and outcomes intact.

## Separate current services from compatibility packages

The published mainline uses the price-discovery entry and its R/H hook services.
The [Data Scientist Harness](../research/market_rsi/data_scientist_harness/README.md)
contains both reused controls and an earlier standalone research workflow;
its older broker is a separate entry path.

The [PMB compatibility lane](../research/market_rsi/pmb_simple_lane/README.md)
is a historical prototype, not the current benchmark. The
[quote-source adapter](../research/market_rsi/quote_source/README.md) and
[pinned shared checks](../research/market_rsi/ds_harness_core/README.md) have
their own source contracts; their presence does not imply that every mainline
round invokes them.

Layout references included
[OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve/tree/9196d8763300d1e46cc8b48cb0dc987966db3d48)
and [RSIBench-Data](https://github.com/evolvent-ai/RSIBench-Data/tree/4c807610243e7b481d382c5ed360c71c79a22f61).
They informed source/config/task/test organization. Market RSI retains its own
runtime, task and evaluation implementation.

## Locate private operational evidence

In the active local Supervisor workspace, decision state, human progress,
interventions, task indexes and per-run evidence describe actual execution.
Those local records can be newer than published main. Old copies in a remote
snapshot are historical evidence rather than a live status feed.

The existing
[local archive manifest](../research/market_rsi/LOCAL_LOG_ARCHIVE_2026-10-07.json)
maps previously archived records to original paths and hashes. Full local Git
bundles and immutable run artifacts are needed for recovery; another model call
is not guaranteed to reproduce an earlier response.

This documentation pass leaves the remaining records, source files and archive
locations in place. Removing tracked logs is a separate, inventory-based cleanup:
preserve local originals, check machine references, and publish only the reviewed
tracking changes. No historical checkpoint, consumed budget or old authority is
rewound.
