# PMB compatibility lane — historical prototype

This is a frozen, zero-authority prototype retained for synthetic contract
tests. PredictionMarketBench is not Market RSI's active benchmark, replay
foundation, hidden evaluator, promotion gate or formal Final.

## Interface and caller

Start at [__init__.py](__init__.py). Synthetic callers supply validated upstream
source commitments, episode manifests and experiment specifications. The
package binds their hashes into a `SyntheticFoundationCommitment`;
`runtime_admitted`, `data_admitted` and `execution_authorized` remain false.
Supporting modules validate source/file identities, episode roles and immutable
artifact/specification records. They provide no live research execution path.

The [role correction](../PREDICTIONMARKETBENCH_ROLE_CORRECTION_2026-09-29.md)
records the decision to freeze this lane. Real PMB intake, downloads, execution
and hidden evaluation require a later reviewed decision defining a narrow need.
Any diagnostic PnL, Sharpe, fill or replay result is not evidence of improved
prediction.

Use the [current architecture](../../../docs/ARCHITECTURE.md) and
[development guide](../../../docs/DEVELOPMENT.md) for active code; the
[history guide](../../../docs/HISTORY.md) covers retained prototypes.
