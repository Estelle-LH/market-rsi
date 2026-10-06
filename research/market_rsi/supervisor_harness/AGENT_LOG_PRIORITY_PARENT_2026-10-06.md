# P1 — accepted prediction reference (2026-10-06)

Author: user-directed AI implementer `/root/priority_parent_20261006`.
Axis: H; one read-only comparison evidence component. K/M/C/R unchanged.
Parent/source checkpoint: `2f11b18fe9adf448e0b22d138f1875bef26b6dfb`.
Frozen scope: the new comparison module, matching synthetic test module, this log.
Supervisor owns integration/independent review/local source checkpoint.

## Observed problem and reused engineering basis

16:32–16:42 UTC: read applicable AGENTS, Supervisor, state and both research/eval
skills completely. Read the actual immutable H1 adapter and shared CSV loader,
current authorized results and production-shaped source/result/learning records.
The older shared CSV loader is model-agnostic, but H1 adds model-specific C1/C7
numeric-state restrictions and binds the real87 key mask in a module global.
Reusing it by monkeypatching would affect concurrent branches. Existing state
replay is useful for a model-specific warm start, not necessary for comparison.
This is reuse of established hash/row/probability verification engineering, not a
new predictive method. No new literature retrieval; no claim that a local
summary is full-paper reading. Project fold/cutoff/model choices are not consensus.

## Small change and trust boundary

New `load_reference(binding, controls, frozen, acceptance_binding)` returns exact
probabilities keyed by event/market/cutoff plus a verification receipt. It verifies
original source and artifact bytes, full frozen control rows/labels/baselines,
folds, full v0 lock (time/orientation), PBP/materialized provenance, denominator
and exclusion codes. It does not refit, decode model states, inherit weights,
choose a model, admit a branch, update an incumbent or consume a budget slot.
Valid KEEP and REVERT may both be compared; invalid/failed/leaking evidence cannot.

Acceptance is a separate, exact Supervisor pin of an independently reviewed
normalization of original source/result/learning evidence. The receipt binds the
complete reference and original proof bytes. Hashes establish integrity, not
reviewer identity or scientific semantics. Candidate-authored `accepted=True`
is not supported. Historical formats vary, so the code does not guess acceptance
from an arbitrary MD/JSON file or `passed=True`. Actual historical normalization
and source-reviewed integration remain Supervisor work; no Train artifact was
read or normalized here. The pure `validate_header` is structural preflight only.

Legacy adapters/runners/scorer/recorders/live ledgers are untouched. Optional
artifact hashes are byte-verified, but model states are never parsed/inherited.
Rollback is leaving this new capability inactive, not rewinding operational history.

## Verification

Focused synthetic artifact-only verification: pending at initial source write.
Test fixtures retain production-shaped source/result/learning review originals;
all games, CSV predictions, timestamps and proof contents are synthetic. No model
calls, estimator imports, Train/Dev/Final reads, fits or network operations.
No claim of live autonomy, forecast gain, researcher improvement or promotion.

## Actual freeze and verification — 16:48:30 UTC

Focused new suite: 21 artifact-only tests. Combined with two inherited CSV
validation tests: **23/23 PASS**, 0.108 seconds reported by unittest (0.459
seconds command execution). Every fixture synthetic; zero estimator fits,
account/provider calls, raw Train/Dev/Final reads or operational ledger writes.

Exact command, cwd `/Users/estelle/Developer/market-rsi/research/market_rsi`:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONHASHSEED=0 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -m unittest experiments.test_nfl_ingame_prediction_reference experiments.test_nfl_ingame_market_freshness_brier_offset.FreshnessBrierOffsetTests.test_exact87_parent_hash_key_label_and_control_validation experiments.test_nfl_ingame_market_residual_hgb.MarketResidualHGBTests.test_generic_actual_parent87_hash_key_label_controls_and_identity -q
```

Runtime alias preserved; actual binary SHA256
`80ee2dd97bc26259d4e30853336f72ad38aa4aa0531bb196cc444d899422689d`.
Import-only version check: Python3.12.3, NumPy1.26.4, SciPy1.14.0,
sklearn1.6.1. Test input/output hashes are dynamic synthetic tempfile fixtures;
no empirical data or memory manifest applicable. Source recovery is available;
scientific rerun/real archived-parent normalization not tested.

Module SHA256:
`664b9566ad61c7c4e60e1aeeea0602482a37e8a2ab6db2d2cd319ea56d89b19d`.
Test SHA256:
`38755f1e7a9feb127edfb292c943195344dff557b26679616d37d56f2e279b51`.
Legacy H1 adapter exact SHA256 still
`f62a5459a8e3c78bcdd7810e25291d1ef164ccc2d41f876fa37fb166f9dcc8bc`;
shared old loader `a17220dea91373b73c3f2e3a5d6e36f2b3e1b2866c8714cdc292dd921aefad79`;
probability contract `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74`.
`git diff --check` PASS; no commits made by implementer.

Early independent review identified Python bool/int equality and the lack of a
frozen exclusion-code comparison. Before freeze, added exact flag/count types,
full frozen-check-row/control consistency, and `frozen['exclusion_codes']` hash
and comparison; the proposed future entry augments the validated old v0 view
from `dict(common.identity.EXPECTED_EXCLUSIONS)` without editing old validators.
Tests reject coordinated CSV/control label or baseline changes, changed
exclusion codes even after a rebound acceptance, duplicate/reordered/missing
rows, task/fold/time/orientation drift, source/proof/artifact mutation,
failed/invalid/leaking references, nonfinite/endpoints, malformed schema,
symlink/traversal, incorrect denominator and wrong runtime-independent identities.

Production size **209 lines, one module** triggers the approximately200-line
warning. Requested explicit inseparability review: strict header/protocol,
evidence byte verification and exact CSV pairing are one read-only comparison
component. Splitting nine excess lines into another production dependency would
not reduce permission, scientific or operational blast radius. Final acceptance
belongs to Supervisor/independent reviewer; this request does not self-approve.

Next use: separately source-reviewed versioned entry, pure preflight header plus
original proof/source/output byte verification before native selection, then
full reference load before any candidate fit. Existing H1 remains untouched;
no global monkeypatch. Optional predictor-state artifact bytes may be hashed as
part of original manifest integrity; the returned receipt explicitly distinguishes
byte verification from state decoding/inheritance (neither performed).

Outcome: bounded comparison capability demonstrated on synthetic accepted
negative/nonlinear fixtures and inherited CSV guards, **L2 synthetic scope only**.
Actual live operational benefit, real archive normalization, autonomous research
capacity, prediction gain and matched fixed-process superiority remain untested.
