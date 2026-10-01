# In-game prior-play success residual audit v2 — independent pre-score review — 2026-09-29

## Verdict

**PASS.** Zero P0 and zero P1 findings. The exact frozen implementation is
suitable for one separately authorized execution of
`InGamePriorPlaySuccessResidualAudit-v2` in a fresh persistent local artifact
directory. This review did not execute the audit, extract the real indicator,
produce a support/refute result, fit a model, or mutate the v0 artifact,
incumbent, scheduler state, Dev/Final, or any research score.

This is a zero-fit opened-Train information audit over an already frozen raw
market residual. It is not a prediction candidate, untouched OOS evidence,
realtime evidence, a promotion test, or a PnL claim.

## Exact reviewed snapshot

| Item | SHA-256 |
| --- | --- |
| R extractor | `fe3e4096f80ea37a8074fc6e404b659474aa4c9e7586367cc218fb50e1650bea` |
| Python runner | `a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb` |
| tests | `4820e1366684b23a0ca94f238fc84d599980e0708e7760d76bc4c89dd4cdc514` |
| implementation log | `990a0a7e85994ec6f1da62c6b7cd39e79703f40d187ee1292bef496ce172f78b` |
| Controller pool log | `a2c1c060b3ddf63ee3c0e1b6f7baebdba08b550c91be0a7d5585ead9b5dac18f` |

The runner binds question digest
`402ccc0147784eedf540918028d297b2d645d9f374e515bf403e9930682e14f5`,
hypothesis digest
`53f74d1204bf3c991b68f01455ca4234d86dcd832c01fe7f512970587291b5c3`,
predeclared rule digest
`96c92f3ce51d779412e3953392eb037c2190ef0522fc8454a4f4f6701424b40e`,
and scheduler branch digest
`5c9bb22d34b1e950883c2396d653451990f940d4d2fe4cf78bff55a55e64996f`.
The pool-plan and scheduler snapshot/state/journal-head bindings also match the
Controller declaration.

## Frozen v0 lineage and common mask

The no-result preflight independently validated all seven frozen v0 hashes and
their manifest/receipt bindings:

| Frozen input | SHA-256 |
| --- | --- |
| `manifest.json` | `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7` |
| `pre_score_lock.json` | `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2` |
| `input_receipts.json` | `0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18` |
| `exclusions.json` | `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1` |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |
| `predictions.csv` | `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56` |
| `scorecard.json` | `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87` |

The exact lineage remains `195 -> 193 + 2 -> 87`. Both named v0 exclusions
and reasons are exact, the 87 check games are unique, and the common-mask key is
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
Fold counts are exactly `26, 16, 28, 17`; the existing expanding chronology and
check-date assignments are revalidated. The indicator loader requires an
eligible materialized row for every one of the 193 nonexcluded games, while
the event join requires all 87 frozen checks. Missing or malformed rows fail
closed rather than being dropped or imputed.

## Causality, eligibility, orientation, and integrity

The R extractor first validates the complete play table's `playId` and
`orderSequence`, resolves the exact hash-bound v0 anchor, and constructs
`prior_plays` using strict `orderSequence < anchor_order`. Only after that
filter does it read play type, deletion flag, timestamp, down, yards,
yards-to-go, or possession for eligibility and success. Anchor and later plays
therefore cannot enter the signal through those fields.

Eligible plays are exactly nondeleted, parseably timed, typed and not
`UNSPECIFIED`, down 1–4, finite in both yards fields, and possessed by the exact
source home or away abbreviation. Success is frozen as 45% of yards-to-go on
first down, 60% on second, and 100% on third/fourth. The signal orientation is
home success rate minus away success rate. An independent comparison of the
source PBP team abbreviations against the raw away/home components of all 195
frozen game IDs found 195 exact matches and zero orientation mismatches.

If either side has no eligible strictly-prior play, extraction emits
`missing_side_eligible_plays`; the runner treats this as an integrity failure.
It does not delete the game, substitute a neutral value, or shrink the common
mask. Counts, successes, rates, and the home-minus-away arithmetic are
independently recomputed by the loader.

## Association, resampling, and decision lock

For every check game the residual is exactly `y - p_raw`. The reported
diagnostics are Pearson and tie-aware Spearman association with that residual,
mean log-loss directional alignment `signal * (y - p_raw)`, and mean
Brier-logit directional alignment
`signal * (y - p_raw) * p_raw * (1 - p_raw)`. They are reported for the full
87-game population and each of the four frozen folds.

For both directional alignments, schedule-date and observed-game-week
bootstraps resample complete groups for 10,000 replicates at seed 20260929 and
recompute the pooled equal-event mean. Breadth, valid/undefined draws, and
intervals are explicit.

The predeclared decision is exact and mutually ordered:

- support requires both correlations positive, both aggregate alignments
  positive, both date/week log-alignment lower bounds positive, and positive
  fold log alignment in at least 3/4 folds;
- refutation requires both correlations nonpositive, both aggregate alignments
  nonpositive, or positive fold log alignment in at most 1/4 folds;
- every other valid result is inconclusive.

No result is available before execution, and this pre-score review awards no
research credit or route action.

## Zero-fit and protected boundary

`MODEL_FITS` is exactly zero. There is no estimator, candidate probability,
KEEP/REVERT decision, or incumbent mutation. The source contains no network or
provider client; its only child process is the local frozen R extractor invoked
during a real audit. Production inputs are exact local hash-bound opened-Train
and v0 artifacts, and production output must be a fresh persistent non-cloud,
non-temporary MarketRSI artifact directory.

Dev/Final, external fetch, paid provider, publication, promotion and retry
remain closed; provider cost is zero. The runner explicitly limits the claim:
historical provider play order is available, but provider publication/receipt
latency is unobserved, so this cannot establish realtime availability.

## Verification performed

Using the pinned Python 3.12 runtime:

```text
python -m unittest -v \
  experiments.test_nfl_ingame_win_probability_train_diagnostic \
  experiments.test_nfl_ingame_prior_play_success_residual_audit

Ran 19 tests in 4.526s — OK
```

`Rscript extract_nfl_prior_play_success.R --self-test` passed. A separate
`Rscript` parse-only invocation passed without extraction. Runner and focused
test passed `py_compile` with bytecode redirected to a private temporary cache.
The actual no-result preflight called only path, v0 artifact, source receipt,
Controller/dependency and scheduler-binding validators. It confirmed
`195/193/87`, `26/16/28/17`, 195 PBP receipts and zero fits; a sentinel guarded
the extractor, no output directory was created, and neither `run()` nor
`_audit()` was called.

No unresolved pre-execution issue remains. Any byte change requires a new hash
and independent review. A real audit must still receive an independent result
review before credit, routing, or state mutation.
