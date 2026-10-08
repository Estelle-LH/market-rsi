# Pinned statistics and quality-check core

This is a consumer-local subset of shared source used by the Data Scientist
Harness. Its five Python files are pinned to
[data-scientist-harness commit df963b0](https://github.com/Estelle-LH/data-scientist-harness/tree/df963b02f8e1fae7db4f4d99d34507e1f339b416).
That is an explicitly selected prerelease commit, not a claim of an upstream
release or an installed PyPI distribution.

## Interface and caller

The core takes declared numeric panels, field/clock specifications and research
callbacks. It returns moments, quality reports and guarded callback results.
[profiles.py](../data_scientist_harness/profiles.py) uses `moments`;
[sanity.py](../data_scientist_harness/sanity.py) adapts grid inputs to
`quality_checks`, `feature_batch` and `research_gate.guarded_research`.
The adapter declares millisecond grid timing and UTC diagnostic dates; these do
not establish finer event order or exchange sessions.

Start at [core_dependency.py](../data_scientist_harness/core_dependency.py) for
the upstream revision and all five SHA256 pins. It verifies local bytes and
import origin before loading the dependency. Missing or changed files fail;
there is no runtime download, silent upgrade or fallback to another checkout.
Frozen workspaces keep their original source. A future dependency update needs
its own explicit pin and project verification.

See the [architecture](../../../docs/ARCHITECTURE.md),
[development guide](../../../docs/DEVELOPMENT.md) and
[history guide](../../../docs/HISTORY.md) for project context. Shared-core tests
do not replace validation of Market RSI's real data adapters.
