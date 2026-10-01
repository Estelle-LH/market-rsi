# In-game state support geometry audit v1 — independent pre-score review — 2026-09-29

## Verdict

**PASS.** Zero P0 and zero P1 findings. The frozen implementation is suitable
for one separately authorized execution of `InGameStateSupportGeometryAudit-v1`
in a fresh persistent local artifact directory. This review did not execute the
audit, produce a support/refute result, fit a prediction model, or mutate the v0
artifact, incumbent, scheduler state, Dev/Final, or any research score.

The changed causal stage is a raw-data/support diagnostic over an already
frozen prediction error. It is not a new prediction, objective, PnL policy, or
promotion test. The repeatedly inspected opened-Train boundary is explicit.

## Exact reviewed snapshot

| Item | SHA-256 |
| --- | --- |
| runner | `fc8f1492e82998bc582d2e0f86cc1b1d0f1f393573f22b6826ac315d11cb7f19` |
| tests | `b210d969abcc5c51da632b4dba67977787ec4c07d08eb8a04f36e82123ef2fc9` |
| implementation log | `eb69fe621e2862889c8f8ddde22c171839c681ee92605977e65a77a2c62d0578` |
| Controller pool log | `d8a28ecce7e46f2ccebc2280d4e425bf0674325351d4f55c1b923d7b6b49108f` |

The runner binds the Controller question/rule digest
`bd0f59c86735a2f20175b9b0784ecfe33fc51468ca3614edbdea07f454c2b8ae`.

## Frozen v0 integrity and population

The no-result preflight loaded, but did not audit, the exact reviewed v0
artifact. All seven required hashes matched:

| Frozen input | SHA-256 |
| --- | --- |
| `manifest.json` | `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7` |
| `pre_score_lock.json` | `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2` |
| `input_receipts.json` | `0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18` |
| `exclusions.json` | `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1` |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |
| `predictions.csv` | `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56` |
| `scorecard.json` | `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87` |

The manifest-to-file bindings and checkpoint receipt binding are checked before
any output directory is created. The exact lineage is `195 -> 193 + 2 -> 87`:
the two named exclusions and reasons are exact, no other row is removed, and
the 87 check games are unique. The exact check-key digest is
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.

Four expanding chronological folds reproduce fit/check counts
`106/26`, `132/16`, `148/28`, and `176/17`. Each check block contains five
schedule dates, every fit date precedes its check dates, and each later fit set
equals the prior fit plus prior check dates. The 87 checks span 20 schedule
dates and seven observed game weeks.

Outcomes and both frozen probabilities are read from the hash-bound prediction
artifact. Per-event `market_plus_state_probability` minus
`market_model_probability` Brier loss is recomputed before geometry and exactly
reproduces the v0 scorecard mean delta `0.015198677631935291` within the frozen
`1e-15` tolerance.

## Leakage, geometry and row-mask review

- The state representation is exactly nine columns. Only score difference,
  regulation seconds remaining, yards to go, and field advantage are
  standardized. Possession and the four one-hot down columns remain raw.
- Every scaler is fit on that fold's prior fit-game matrix only. Check features,
  outcomes, probabilities and Brier deltas do not enter scaling, neighbor
  selection or threshold construction.
- Fit support distance is the mean Euclidean distance to the five nearest
  *other* fit rows. The diagonal is set to infinity and each fit fold has more
  than five rows.
- The support cutoff is exactly the fit-only 95th percentile with NumPy linear
  interpolation. Check distance uses five prior fit rows, and unsupported is
  exactly `check_distance > cutoff`; equality remains supported.
- Feature-range violations are diagnostic and fit-relative. They never remove a
  check row. The runner asserts all 87 unique rows survive before scoring the
  predeclared explanation.

## Arithmetic, inference and decision lock

The frozen loss delta is signed `state_model_loss - market_model_loss`. The
unsupported signed contribution is exactly
`sum(unsupported delta) / sum(all delta)` and the exact all-87 sum must be
positive. A fold's signed total may legitimately be negative; it is not used as
an invalidation gate.

The runner reports aggregate and four-fold supported/unsupported counts, means,
signed sums and contrasts, plus feature-range counts. Complete schedule-date
and observed-week bootstraps resample whole groups and recompute the equal-event
unsupported-minus-supported mean contrast. Seeds, 10,000 replicates, valid and
undefined draw counts, breadth and insufficient-draw status are explicit.

The decision matches the Controller lock exactly:

- support requires unsupported share at least 10%, signed contribution at least
  50%, a positive aggregate contrast, and positive contrast in at least 3/4
  folds;
- refutation requires any of share below 5%, nonpositive signed contribution,
  nonpositive aggregate contrast, or positive contrast in at most 1/4 folds;
- all other valid outcomes are inconclusive.

Support and valid refutation are only *eligible* for research credit 2;
inconclusive is eligible for at most 1. The runner always writes awarded credit
as zero pending independent result review.

## Zero-fit and authority boundary

`MODEL_FITS` is exactly zero. The runner contains no estimator, probability
prediction, candidate arm, KEEP/REVERT transition, or incumbent mutation. Four
fit-only `StandardScaler` preprocessing operations are reported separately and
must not be described as prediction-model fits.

The source imports no network/provider/child-process client. Production input
is pinned to the reviewed local v0 artifact and output is restricted to a fresh
non-cloud, non-temporary MarketRSI artifact path. Dev/Final, external fetch,
paid provider, publication and promotion flags remain false; cost remains zero.
The output lock, per-event CSV, scorecard and manifest are atomically written
and hash-bound. A partial run writes a failure receipt and cannot masquerade as
a complete manifest.

## Verification performed

Using the pinned Python 3.12 runtime:

```text
python -m unittest -v \
  experiments.test_nfl_ingame_win_probability_train_diagnostic \
  experiments.test_nfl_ingame_state_support_geometry_audit

Ran 19 tests in 9.972s — OK
```

Both new files also passed `py_compile` with bytecode redirected to a private
temporary cache. A static import scan found no network/provider capability.
The actual no-result preflight called only `_load_frozen_inputs`; it created no
output directory and did not call `_audit()` or `run()`.

No unresolved pre-execution issue remains in the reviewed snapshot. Any byte
change requires a new hash and review. A real audit result still requires an
independent result review before research credit or route action is recorded.
