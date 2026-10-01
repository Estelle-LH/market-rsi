# In-game state support geometry audit v1 — independent result review — 2026-09-29

## Verdict

**PASS.** Zero P0 and zero P1 findings. The completed artifact is internally
consistent with the frozen runner and independently reproduces the exact
decision `SAMPLE_SUPPORT_EXPLANATION_REFUTED` on all 87 frozen check games.
This is a valid negative result for the predeclared sample-support explanation,
not a prediction-model failure, KEEP/REVERT decision, promotion result, or
rejection of all possible play-by-play representations.

This review did not modify the runner, the completed artifact, the incumbent,
research credit, scheduler state, Dev/Final, or any historical result.

## Frozen source and artifact integrity

The runner remains frozen at SHA-256
`fc8f1492e82998bc582d2e0f86cc1b1d0f1f393573f22b6826ac315d11cb7f19`.
The completed artifact is
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-state-support-geometry-audit-20260929-01`.

| Artifact file | SHA-256 |
| --- | --- |
| `manifest.json` | `f9554bbf552f269807000da33474860133414e839e3fd7cdeb20bf459a6713fd` |
| `pre_audit_lock.json` | `cae9835f8898ebc447abb8b2a2d10c0bcc70a265963c4858fd145e582a24df0f` |
| `scorecard.json` | `7fdb2ea94f14bb38260291eeffff2cf01a0aa9be7e418bf1508166c070d19882` |
| `support_geometry.csv` | `24dc4c0bd77989e90df1cf8c567467f0223679722e135e06d7cd86043a4335a5` |

The manifest exactly binds the other three artifact hashes, is complete, and
records the same decision. The lock binds the frozen Controller log SHA
`d8a28ecce7e46f2ccebc2280d4e425bf0674325351d4f55c1b923d7b6b49108f`,
question/rule digest
`bd0f59c86735a2f20175b9b0784ecfe33fc51468ca3614edbdea07f454c2b8ae`,
and all seven reviewed v0 inputs:

| Frozen v0 input | SHA-256 |
| --- | --- |
| `manifest.json` | `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7` |
| `pre_score_lock.json` | `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2` |
| `input_receipts.json` | `0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18` |
| `exclusions.json` | `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1` |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |
| `predictions.csv` | `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56` |
| `scorecard.json` | `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87` |

## Independent reconstruction

I independently reconstructed the audit from the frozen v0 checkpoint,
predictions, exclusions, and fold calendar rather than reading summary values
from the new scorecard. The lineage reproduced exactly as
`195 source -> 193 materialized + 2 named exclusions -> 87 check games`.
All 87 game IDs were unique and survived into `support_geometry.csv`; they span
20 schedule dates and seven observed game weeks. Fold fit/check counts were
`106/26`, `132/16`, `148/28`, and `176/17`.

For each fold I independently applied fit-only population-variance scaling to
the four frozen continuous features, left the five binary possession/down
features unchanged, computed each fit row's leave-one-out mean distance to its
five nearest other fit rows, and used NumPy linear interpolation for the fit
95th percentile. The reconstructed cutoffs and unsupported counts were:

| Fold | Fit/check | Fit-only q95 | Unsupported |
| --- | ---: | ---: | ---: |
| 1 | 106/26 | `2.0842158940523148` | 1 |
| 2 | 132/16 | `2.0138095141498926` | 0 |
| 3 | 148/28 | `1.9730709759294878` | 3 |
| 4 | 176/17 | `1.9783566325008397` | 0 |

Every independently reconstructed row matched the artifact on fold, game/date/
week identity, outcome, frozen Brier delta, five-neighbor distance, q95 cutoff,
and strict-above unsupported classification to absolute tolerance `1e-15`.
The one feature-range violation (`regulation_seconds_remaining`) remained a
diagnostic flag and did not remove the event.

## Independent decision arithmetic

The frozen delta is `state-model Brier - market-model Brier`. Recomputed
aggregate evidence was:

- supported: 83 events, mean delta `0.016226004480669964`, signed sum
  `1.346758371895607`;
- unsupported: 4 events, share `0.04597701149425287`, mean delta
  `-0.006118354479309212`, signed sum `-0.024473417917236846`;
- all-event signed sum: `1.3222849539783703`;
- unsupported signed contribution:
  `-0.024473417917236846 / 1.3222849539783703 = -0.01850842955113681`;
- unsupported-minus-supported mean contrast: `-0.022344358959979174`.

Fold contrasts were `-0.02807964153334861`, undefined (zero unsupported),
`-0.022420083584548885`, and undefined (zero unsupported), so there were zero
positive fold contrasts. Thus all four independently frozen refutation clauses
hold: unsupported share is below 5%, signed contribution is nonpositive,
aggregate contrast is nonpositive, and positive fold contrasts are at most
one of four. The exact decision is therefore
`SAMPLE_SUPPORT_EXPLANATION_REFUTED`.

The complete-schedule-group bootstrap was also independently rerun with seed
`20260929` and 10,000 draws:

| Group | Breadth | Valid/undefined | 95% interval |
| --- | ---: | ---: | --- |
| schedule date | 20 | 9,616 / 384 | `[-0.03997150303581008, -0.004740007975445543]` |
| observed game week | 7 | 9,799 / 201 | `[-0.0405098518240005, -0.004623583152577997]` |

Both intervals are wholly negative and agree with the predeclared refutation;
they remain repeatedly inspected opened-Train diagnostic evidence, not an
untouched OOS claim.

## Zero-fit, incumbent, and authority boundary

The result performs zero prediction-model fits and exactly four fit-only
`StandardScaler` preprocessing fits. Static inspection found no estimator,
candidate-probability arm, network/provider/child-process client, or hidden
fit path. The CSV has no candidate prediction field. Manifest and scorecard
both record `no_prediction_candidate_emitted=true`,
`incumbent_or_keep_revert_changed=false`, and `model_fits=0`.

The completed lock, scorecard, and manifest consistently record zero provider
cost/calls and false flags for external fetch, Dev access, sealed Final,
promotion, and incumbent mutation. Historical event-clock use is explicitly
diagnostic because play-by-play publish/receive latency remains unobserved.

## Verification performed

Using the pinned Python 3.12 runtime, the frozen parent plus audit suites passed:

```text
python -m unittest -v \
  experiments.test_nfl_ingame_win_probability_train_diagnostic \
  experiments.test_nfl_ingame_state_support_geometry_audit

Ran 19 tests in 9.902s — OK
```

The runner and focused test also passed `py_compile` with bytecode redirected
to `/private/tmp`. No real audit was rerun during this review.

## Credit and route recommendation (not applied)

Recommend **research credit 2**, outcome **`refute`**, route action **`stop`**
(equivalently scheduler-valid `cooldown`) for the exact predeclared
sample-support question. The completed manifest SHA
`f9554bbf552f269807000da33474860133414e839e3fd7cdeb20bf459a6713fd`
is the natural evidence-bundle root because it binds the lock, event audit,
scorecard, and frozen v0 lineage. Preserve the branch in the archive, release
its active-pool slot, and do not rank it as an eligible continuation parent.

The reason is decisive refutation, not invalid execution: weak prior-state
support is rare and the unsupported rows reduce rather than concentrate the
observed state-arm harm. This settles the exact frozen question while leaving
other state representations, timestamps, and mechanisms open. The Supervisor
must still perform the append-only, duplicate-checked credit/state write; this
review intentionally performs neither.
