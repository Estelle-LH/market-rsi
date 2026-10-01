# In-game state support geometry audit v1 — implementation — 2026-09-29

## Scope and status

Implemented the frozen `InGameStateSupportGeometryAudit-v1` as a new,
standalone, zero-model-fit runner and test module.  No real audit was executed.
The frozen v0 runner, extractor, predictions, scorecard, KEEP/REVERT result and
historical artifacts were not modified.

This is the exploration member selected by the Controller in
`AGENT_LOG_INGAME_DISCOVERY_V2_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md`
(SHA-256
`d8a28ecce7e46f2ccebc2280d4e425bf0674325351d4f55c1b923d7b6b49108f`).
The exact question/rule digest remains
`bd0f59c86735a2f20175b9b0784ecfe33fc51468ca3614edbdea07f454c2b8ae`.

## Observed problem and changed component

The reviewed v0 state arm was worse than the market-only model in aggregate,
but its harm was not uniform across chronological folds and its grouped
intervals crossed zero.  The Controller predeclared a distinct diagnostic:
test whether the already-frozen state-arm harm is concentrated in check games
whose nine-dimensional game-state vectors have weak prior fit-game support.

Only the new audit runner and its tests were added:

- `research/market_rsi/experiments/nfl_ingame_state_support_geometry_audit.py`
- `research/market_rsi/experiments/test_nfl_ingame_state_support_geometry_audit.py`

## Frozen inputs and integrity binding

The production path is bound to the exact reviewed v0 artifact and validates
all of these SHA-256 values before analysis:

- manifest:
  `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7`;
- pre-score lock:
  `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2`;
- input receipts:
  `0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18`;
- exclusions:
  `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1`;
- checkpoint state:
  `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e`;
- predictions:
  `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56`;
- scorecard:
  `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87`.

It additionally verifies the v0 manifest-to-file bindings, the input receipt's
checkpoint binding, exact `195 -> 193 + 2` lineage and exclusion codes, four
expanding chronological folds, fit counts `106/132/148/176`, check counts
`26/16/28/17`, exact 87 unique check games, and check-key digest
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
The per-event Brier deltas are recomputed from the frozen probabilities and
must reproduce the reviewed v0 aggregate before the audit can proceed.

## Implemented frozen method

For each chronological fold independently, the runner:

1. uses exactly the nine v0 state columns;
2. fits `StandardScaler` only on that fold's fit rows and only on the four
   continuous fields; possession and down indicators remain unchanged;
3. computes every fit row's leave-one-out mean distance to its five nearest
   other fit rows;
4. fixes the threshold at the fit-only 95th percentile using NumPy's explicit
   `method="linear"` interpolation;
5. computes every check row's mean distance to five fit rows and marks it
   unsupported only when distance is strictly above the threshold;
6. preserves all 87 check rows and stratifies the already-frozen
   state-minus-market-model Brier delta.

The output schema reports supported/unsupported counts, feature-range
violations, signed sums, exact unsupported contribution, aggregate and
per-fold contrasts, schedule-date/week breadth, and complete-group bootstrap
intervals.  A negative fold total is valid; only the frozen all-87 sum is
required to be positive for the predeclared signed-contribution ratio.

The support, refute and inconclusive rules are copied exactly from the frozen
Controller selection.  The audit cannot emit a probability candidate, change
the incumbent or apply KEEP/REVERT.  It reports research-credit eligibility,
but awards zero credit until Supervisor independent review.

## Alternatives and research-source handling

No new method choice was made in implementation, so no live literature search
was performed.  The exact k-nearest-neighbor geometry, scaling, interpolation,
thresholds and decision criteria were already frozen by the Controller; a new
search would not authorize changing them.  The implementation reuses the
reviewed v0 chronology and score definitions and treats that applicability as
an implementation constraint, not a literature consensus.  Mahalanobis
distance, learned embeddings, alternative `k`, alternative quantiles and
post-score tuning remain possible future hypotheses but are deliberately not
implemented here.

## Tests actually run

Runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`.

Targeted audit suite:

```text
python -m unittest experiments.test_nfl_ingame_state_support_geometry_audit -v
Ran 9 tests in 0.013s — OK
```

Coverage includes:

- support/refute/inconclusive decision arithmetic;
- fit-only scaling and threshold invariance to check-row changes;
- unchanged binary columns;
- strict `distance > cutoff` classification;
- leave-one-out five-neighbor distances;
- signed-contribution and equal-event group arithmetic, including a negative
  fold total;
- fit-relative range violations without row deletion;
- mutation-sensitive hashes;
- chronological and persistent-local boundary guards;
- actual reviewed v0 hash/mask/lineage preflight without running the audit;
- static zero-prediction-model-fit guard.

Regression with the frozen v0 suite before the negative-fold guard correction:

```text
python -m unittest \
  experiments.test_nfl_ingame_win_probability_train_diagnostic \
  experiments.test_nfl_ingame_state_support_geometry_audit -v
Ran 19 tests in 4.005s — OK
```

After correcting fold summaries to allow their observed negative totals, the
targeted 9-test suite passed again, and both new Python files compiled cleanly
with `PYTHONPYCACHEPREFIX` directed to persistent-safe temporary test output.

## Final source hashes

- runner:
  `fc8f1492e82998bc582d2e0f86cc1b1d0f1f393573f22b6826ac315d11cb7f19`;
- tests:
  `b210d969abcc5c51da632b4dba67977787ec4c07d08eb8a04f36e82123ef2fc9`.

These hashes must be recomputed if an independent review requires a repair.

## Boundaries and remaining gate

- Actual audit executions: `0`.
- Prediction-model fits: `0`.
- Network bytes, provider calls and cost: `0`.
- Protected Dev/Final access: `0`.
- Publication, release, promotion and cross-task score comparison: `0`.

The next permitted step is independent pre-execution review of the exact new
runner/test bytes.  Only after PASS should the Supervisor execute the one-shot
audit in a new non-cloud, non-temporary persistent artifact directory.  A real
result still requires an independent result review before research credit or a
branch-routing decision is recorded.
