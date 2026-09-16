# Polymarket quote source, v0.1.0

An independent, causal data adapter. This is human-directed source repair, not
an RSI iteration. It does not replace the production collector or old datasets.

`reconstruct.py` separates source-reported BBO from reconstructed depth. A delta's
`size` is the absolute quantity at its changed level, **not** the size of both
source BBO prices. Source sizes therefore stay null except at complete snapshots.
Every source observation retains its raw-record hash and `(ordinal, message,
change)` key. No same-millisecond batching, sorting by timestamp, forward fill,
future snapshot backfill, or complementary-token merge is performed.

`price_candidate` means only a finite, interior, uncrossed source pair with
syntactically valid, non-regressing clocks. It is **not** historical clock
attestation, feed continuity, tradable liquidity, data admission, or permission
to fit. Missing BBO is an explicit invalid observation, never a stale fallback.
Prices at 0 or 1 remain recorded as `boundary_unknown`; current documentation
does not establish empty-side sentinel semantics for this historical capture.

Depth is anchored only by a complete REST/WS snapshot. Bad deltas, malformed
snapshots, unknown target events, and clock regressions discard that anchor.
Matching source BBO does not certify deeper levels. The next snapshot comparison
is a diagnostic at its arrival, never a retroactive correction of earlier rows.

Research and alternatives: [repair record](../QUOTE_REPAIR_2026-09-11.md).
No trainer, feature, target, data split, hidden evaluation, or paid-model setting
is changed here. The existing Data Scientist Harness stays at dsh-v1.2.4; this
source adapter needs its own source commitment before any downstream use.
