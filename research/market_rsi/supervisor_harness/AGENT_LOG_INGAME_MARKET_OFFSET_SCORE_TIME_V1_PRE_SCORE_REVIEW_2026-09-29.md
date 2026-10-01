# `InGameMarketOffsetScoreTimeDiagnostic-v1` independent pre-score review

Date: 2026-09-29  
Verdict: **PASS**  
P0: none  
P1: none  
Launch disposition: **the exact reviewed source may run once on the already-opened local Train data**

I independently reviewed the frozen implementation without modifying the
runner or its tests and without executing the real v1 score. The implementation
is bound to the exact reviewed v0 result, preserves the 195 -> 193 -> 87
population and four chronological folds, implements exactly three offset arms
per fold (12 fits), and encodes the Controller's support/refute/inconclusive
rule without a post-score override. No source, artifact, mask, score, KEEP/
REVERT decision, protected split, provider, or project authority was changed.

This PASS admits only one historical opened-Train Discovery run of the exact
hashes below. It is not permission to retry, sweep, fetch, pay, open Dev/Final,
publish, promote, deploy, or compare the resulting scores with the separate
pregame task. Any source or bound dependency change invalidates this review.

## Frozen identities reviewed

| Item | SHA-256 |
| --- | --- |
| v1 runner | `6194d25712df0e251fe0c56c671557967f8c7f5f7e62c28ca9981c09a3adf120` |
| v1 focused tests | `72be12f0a84c46550e1f3604ae1769c261e22311dbdd2903c99b9b3812e1ea76` |
| v1 Controller decision | `3930ab266e1983e6cd15a3472977984961b0f08a45e246eebb8feefbb048e8ce` |
| two-member active-pool decision | `d8a28ecce7e46f2ccebc2280d4e425bf0674325351d4f55c1b923d7b6b49108f` |
| v0 independent result review | `325543498c556a1c1ba0e8e3adde42c4546c35e1b0bcffac8efbeafd3d38f983` |
| v0 runner | `e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7` |
| frozen R checkpoint extractor | `37a26997406de0e54bd9d91de10e7417a8b340c68b675892c4f16e9a51675163` |
| settlement dependency | `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b` |
| probability contract | `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74` |
| proper scorer | `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b` |

The active-pool log is an independently checked scientific-selection record;
the runner itself correctly binds the Controller decision, v0 review, v0
artifact and empirical dependencies. Pool scheduling/state mutation remains
outside this empirical runner, as the pool decision declares. Inside the
pre-score lock, the research parent is the archived v0 negative state branch,
while the comparison incumbent is separately recorded as v0 raw market.

The v0 artifact directory contains exactly seven regular files, and all seven
hashes match the runner's frozen map:

| File | SHA-256 |
| --- | --- |
| `checkpoint_state.csv` | `235510db382de0e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |
| `exclusions.json` | `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1` |
| `input_receipts.json` | `0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18` |
| `manifest.json` | `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7` |
| `pre_score_lock.json` | `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2` |
| `predictions.csv` | `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56` |
| `scorecard.json` | `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87` |

The frozen parent manifest remains complete, with 195 source games, 193
materialized games, two explicit exclusions, 87 check games, eight v0 fits,
decision `PBP_INCREMENT_NOT_SUPPORTED`, zero cost, and Dev/Final unopened.

## Population, mask and chronology preflight

The focused actual-data preflight ran extraction and materialization but did
not call the v1 fitting/scoring path. It reproduced:

- all 195 source games and 42 schedule dates;
- checkpoint-state SHA-256
  `235510db382de0e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e`;
- exactly 193 materialized rows and the exact two ordered exclusions:
  `2025_04_GB_DAL / unresolved_outcome` and
  `2025_05_TEN_ARI / market_trade_too_stale`;
- materialized-key SHA-256
  `0bb6ae95fd26937b592569f004c16ac729b1e4c6b796c975a1d988e57c4d2c34`;
- 87 disjoint check rows, one checkpoint per game, and check-key SHA-256
  `2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`;
- prior-only fit counts `106 / 132 / 148 / 176` and check counts
  `26 / 16 / 28 / 17`;
- zero outcome-unavailable fit candidates in all four folds.

The same prediction records carry the raw-market and all three fitted-arm
probabilities, so labels, games and checkpoints cannot diverge by arm. The
runner rejects any changed parent artifact, checkpoint state, materialized
population, exclusion ordering, common-mask digest, fold counts, or label-
availability ledger before accepting a result.

## Model and preprocessing review

The three fitted arms are exactly:

1. market-logit offset plus an intercept;
2. the same offset plus the nine frozen linear state columns;
3. the same offset plus those columns and the one frozen
   `score_time_ratio_k4` feature.

Across four folds this is exactly 12 fits, and the code raises if the count is
not 12. There is no hyperparameter loop, alternative `k`, feature search,
automatic retry, or random model-selection path.

The market logit enters `offsets + intercept + X @ coefficients` and never
enters the parameter vector. Its coefficient is therefore exactly one in both
the objective and prediction functions. The analytic objective is exactly
`sum(logaddexp(0, eta) - y*eta) + 0.5 * lambda * (w @ w)`, with
`lambda=1`; the intercept is excluded from `w`. The analytic gradient matches
a central numerical difference in the focused test.

`L-BFGS-B` is called once with the frozen `maxiter=1000`, `gtol=1e-8` and
`ftol=1e-12`. Non-success, nonfinite values, or gradient infinity norm above
`1e-5` is terminal. No fallback or retry exists. Runtime diagnostics cannot
change the score decision.

Only continuous state columns are standardized, using fit-fold rows only.
Possession and down indicators remain unchanged, and the market offset is
never scaled. The intercept-only arm is handled as a valid zero-column design.

## Causal feature and availability review

`score_time_ratio_k4` is exactly
`home_score_diff_pre * exp(4 * (1 - clip(regulation_seconds_remaining, 0, 3600) / 3600))`.
The runner recomputes it solely from the already materialized pre-anchor score
and regulation time, and requires equality to the extractor's frozen value to
`1e-12`. The extractor selects the first eligible Q3 pre-play row at or below
08:00 by `orderSequence`; reconstructed scoring summaries/PATs must complete
strictly before the selected play. The current play result, later plays and
terminal score are not feature inputs.

The market snapshot remains the latest fill in an integer second strictly
before the PBP event second, with a maximum 300-second staleness. This remains
historical event-clock evidence only because provider publish/local receive
timestamps are absent; the lock and scorecard state that limitation.

## Scoring, uncertainty and decision review

Primary scoring is equal-event Brier on the exact 87-game common check mask.
Log loss, calibration, reliability, per-fold and per-date evidence are
secondary. Paired losses are computed on the same game for every arm.

Both uncertainty reports use the frozen seed `20260929` and 10,000 resamples.
They resample complete schedule-date or observed-game-week groups, then
recompute the pooled equal-event mean inside each draw. The interval does not
pretend multiple plays from the same game are independent.

The encoded decision exactly matches the frozen Controller rule:

- `LINEAR_REPRESENTATION_FAILURE_SUPPORTED` only when score-time has lower
  aggregate Brier and log loss than both linear offset and raw market and wins
  Brier versus linear offset in at least 3/4 folds;
- `SCORE_TIME_K4_HYPOTHESIS_REFUTED` when either aggregate proper-score
  comparison to linear offset fails or fewer than 3/4 fold Brier comparisons
  win;
- otherwise `SCORE_TIME_K4_NARROWING_INCONCLUSIVE`.

Grouped intervals are reported but cannot override this rule. The focused
tests exercised all three routes.

## Authority and output boundary

The production runner accepts only the exact local opened-Train source and a
fresh output below the persistent local MarketRSI artifact root. Existing
paths, source-root descendants, temporary locations and cloud-looking paths
are rejected. The code contains no HTTP/network/provider client and no
Dev/Final path. Receipts and final records explicitly preserve zero external
fetch, zero provider calls/cost, Dev/Final unopened and no promotion authority.

No v1 artifact matching `offset-score-time` existed at review time. Therefore
this review did not inspect or reveal a real v1 score.

## Verification executed

Using the persistent Python 3.12 runtime (Python `3.12.3`, NumPy `1.26.4`,
SciPy `1.14.0`, scikit-learn `1.6.1`):

```text
....................
----------------------------------------------------------------------
Ran 20 tests in 7.576s

OK
```

This was the v1 focused suite plus the adjacent frozen v0 suite. Both v1
Python modules compiled with a redirected temporary bytecode cache, and the R
checkpoint extractor parsed successfully. The first repository-root unittest
invocation produced two import-path errors (`experiments` was not on
`sys.path`); rerunning from `research/market_rsi`, which is the module's
documented import root, passed all 20 tests. That invocation error did not run
the experiment or alter its code/artifacts.

**Final verdict: PASS.** The Supervisor may execute exactly one real local
opened-Train run using the reviewed runner SHA-256 above, a fresh persistent
artifact path, no retry, and the already-frozen boundaries. The completed
artifact still requires an independent result review before any research
credit, active-pool update, incumbent decision, or follow-up experiment.
