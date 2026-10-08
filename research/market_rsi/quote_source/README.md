# Polymarket quote reconstruction

This is an independent causal source adapter (`pm-source-quotes-v0.1.0`),
preserved from earlier human-directed data repair. It is separate from the
current price task and does not replace the production collector or existing
datasets.

## Inputs, outputs and caller

Start at `QuoteReconstructor` in [reconstruct.py](reconstruct.py). A data
validation caller configures one exact historical asset/market pair and passes
raw capture records, strictly increasing ordinals and raw-record hashes to
`process()`. The adapter performs no I/O. It returns rows with separate
source-reported BBO and reconstructed-depth fields, provenance keys, clock
issues and explicit validity/admission flags.

Rows belong in the runner's local data store; external Controller prompts use
aggregate diagnostics and provenance hashes, not these raw identifiers.

## Causal semantics

A delta's `size` is the absolute quantity at its changed level, not the size of
both source BBO prices. Source BBO sizes stay null except at complete snapshots.
Every observation retains its raw hash and `(ordinal, message, change)` key.
Processing preserves arrival order: no same-millisecond batching, timestamp
sorting, forward fill, future-snapshot backfill or complementary-token merge.

`price_candidate` means only an interior, uncrossed finite source pair with
syntactically valid, non-regressing clocks. Missing BBO remains invalid. Prices
at 0 or 1 retain `boundary_unknown`: historical empty-side sentinel semantics
are not established. A candidate flag does not attest historical clocks, feed
continuity, tradable liquidity or downstream data admission.

Depth is anchored only by a complete REST/WS snapshot. Bad deltas, malformed
snapshots, unknown target events and clock regressions discard that anchor.
Matching BBO does not certify deeper levels. The next snapshot comparison is a
diagnostic at its arrival, never a correction to earlier rows.

The [repair record](../QUOTE_REPAIR_2026-09-11.md) preserves research and
alternatives. The adapter changes no trainer, target, split or evaluator; any
downstream use needs its own source binding and admission evidence.
For project context see the [architecture](../../../docs/ARCHITECTURE.md),
[development guide](../../../docs/DEVELOPMENT.md) and
[history guide](../../../docs/HISTORY.md).
