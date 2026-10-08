# `InGameMarketOffsetScoreTimeDiagnostic-v1` Controller decision — 2026-09-29

## Decision

**Freeze one plan-only next experiment; do not execute it yet.** Launch is
conditional on an independent result review passing the exact v0 artifact. No
v0 score, prediction, mask, or artifact is changed. This decision does not open
Dev/Final, authorize promotion, fetch data, call a provider, or spend money.

The v0 outcome is **trainer/representation-specific negative evidence**. It
rejects the fixed additive `LogisticRegression(C=1)` state arm under the frozen
Q3 checkpoint; it does not reject the PBP/game-state family. The next smallest
discriminating experiment fixes the market logit as an offset and adds exactly
one predeclared nonlinear score-by-time representation.

## Frozen v0 evidence

Artifact root:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-win-probability-train-diagnostic-20260929-01`

| Artifact | SHA-256 |
| --- | --- |
| `manifest.json` | `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7` |
| `pre_score_lock.json` | `dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2` |
| `scorecard.json` | `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87` |
| `predictions.csv` | `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56` |
| `checkpoint_state.csv` | `235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e` |
| `exclusions.json` | `db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1` |

The exact denominator is 195 games, 193 materialized and two explicit
exclusions (`2025_04_GB_DAL` unresolved tie outcome;
`2025_05_TEN_ARI` trade staleness 1088.157s > 300s). All three arms share the
same 87 check games, labels, checkpoints, four chronological folds, 20 schedule
dates, and seven observed game weeks.

### Arm decomposition

| Arm | Equal-event Brier | Log loss | Calibration intercept / slope |
| --- | ---: | ---: | ---: |
| raw market | `0.1419525290` | `0.4296707847` | `-0.01181 / 1.03704` |
| market-logit LR | `0.1454823125` | `0.4399219725` | `-0.02350 / 1.05681` |
| market + state LR | `0.1606809902` | `0.4711973193` | `0.04813 / 0.91869` |

The market-logit LR is worse than raw market by `+0.0035297835` Brier
(`+2.49%`) and `+0.0102511877` log loss (`+2.39%`). This is broad rather than a
single fold accident: its paired loss is worse on 18/20 schedule dates and all
7/7 weeks for Brier, and 19/20 dates and 7/7 weeks for log loss. Both the
schedule-date and observed-week 95% grouped intervals are strictly above zero:
Brier `[0.0013909, 0.0061967]` / `[0.0021747, 0.0058719]`; log loss
`[0.0053027, 0.0171065]` / `[0.0064878, 0.0165437]`. Thus re-estimating the
market coefficient/calibration is itself harmful in this sample.

The state LR is worse than market-logit LR by `+0.0151986776` Brier
(`+10.45%`) and `+0.0312753468` log loss (`+7.11%`), and worse than raw market
by `+0.0187284612` / `+0.0415265346`. State-minus-market-LR fold Brier deltas
(negative is better) are `+0.01958, -0.00854, +0.01433, +0.03226`: only fold 2
wins. Yet the harm is not uniformly signed: state is better on 11/20 schedule
dates for Brier and 12/20 for log loss. By week it wins 2/7 for Brier and 3/7
for log loss, with most aggregate harm concentrated in weeks 9, 12 and 13.
The grouped intervals cross zero: Brier date/week
`[-0.0009025, 0.0314262]` / `[-0.0009040, 0.0308357]`; log loss
`[-0.0084464, 0.0710904]` / `[-0.0062427, 0.0689778]`.

### Scientific interpretation

The most plausible explanations are not mutually exclusive:

1. raw market is already well calibrated and incorporates much of the visible
   game state, so replacing its logit coefficient creates avoidable error;
2. the v0 additive linear representation cannot express the strongly nonlinear
   score-margin-by-time relationship or related state interactions;
3. 106--176 fit games per fold are small relative to the state parameterization,
   making shrinkage/overfit and fold instability plausible;
4. residual state information may be genuinely small and concentrated rather
   than absent.

V0 uses one snapshot at one Q3 checkpoint. It does not test play sequences,
state changes, richer PBP representations, or other causal checkpoints.
Historical event wall clock is available but provider publication/local receive
time is not, so even a later positive result would remain historical diagnostic
evidence, not proof of real-time availability.

## Frozen research-credit question

`question_id`: `ingame-offset-scoretime-v1-q1`

Canonical question-record SHA-256:
`8cfabbfb4f93b2eddf31f61f7d4a2850b1e4dd0032661ae80ed433d1e36bfa9f`

**Question:** Does a fixed market-logit offset plus one predeclared nonlinear
score-by-time representation recover stable incremental settlement information
that the additive linear state representation missed?

- Changed stage: prediction representation only.
- Research parent: the archived v0 `market_plus_state_model` negative branch,
  bound to scorecard SHA-256 `74c2f23d...e87`. This preserves and develops a
  failed branch rather than pretending it became the incumbent.
- Comparison incumbent: the v0 `raw_market` arm on the exact common mask. It
  remains the current best in-game diagnostic prediction until a candidate
  passes its frozen replacement rule and independent review.
- Novel discriminatory delta: freeze the market-logit coefficient at exactly
  one, then add only the already-materialized causal
  `score_time_ratio_k4` representation to the same offset-state objective.
- Duplicate status: no prior experiment in this in-game settlement task has
  tested a fixed market offset or this single nonlinear representation on the
  frozen 87-game check mask.

## `InGameMarketOffsetScoreTimeDiagnostic-v1`

### Unchanged data and evaluation boundary

Reuse exactly the v0 source receipts, 195-game denominator, two exclusions,
193 materialized checkpoints, 87 check games, outcome orientation, Q3
checkpoint rule, strict-preceding trade rule, 300-second maximum staleness,
four chronological folds, scorer, bootstrap seed `20260929`, and 10,000
complete-group resamples. Preserve the same primary equal-event Brier,
secondary log loss/calibration, per-fold deltas, per-date deltas, and
schedule-date/observed-week intervals. All arms must use identical rows,
labels, and checkpoints. Scores must not be compared numerically with the
pregame task.

### Frozen arms and objective

Archive the v0 raw-market and two LR arms as controls; do not refit them. Fit
three new arms in each of four folds:

1. `market_offset_intercept`: `eta = market_logit + b`.
2. `market_offset_linear_state`:
   `eta = market_logit + b + w^T z_linear_state` using the exact nine v0 state
   columns.
3. `market_offset_score_time_state`:
   `eta = market_logit + b + w^T z_linear_state + gamma*z_score_time_ratio_k4`.

Here
`score_time_ratio_k4 = home_score_diff_pre * exp(4 * (1 - clip(regulation_seconds_remaining, 0, 3600) / 3600))`.
The formula and its values already exist in the frozen checkpoint artifact; no
future play or terminal field is introduced.

For every arm, clip raw market probability only for logit/numerical evaluation
at the v0 epsilon, keep the market-logit coefficient exactly `1`, fit continuous
scalers on fit rows only, preserve the v0 one-hot treatment, and minimize
`sum(binary NLL) + 0.5 * sum(non-intercept coefficients^2)` with a fixed
deterministic `L-BFGS-B` solver, analytic gradient, fixed seed, and no tuning.
The intercept is unpenalized. The component-spec hashes are:

- offset intercept: `e2f71e54a5c2d933c4554ee111b8316ac7e64198b047b053fbd39d3b12242da7`;
- offset linear state: `bd907c7048076b033611d56eb10a02a637d427a7d0dcd3d95c45da84af42d95c`;
- offset score-time state: `bcdb518f4f7c7ea1a0da70bc841d67990b07c39c953c9cf63b707b3f5cfdd56a`.

Exactly 12 new fits are allowed: three arms times four folds. No sweep,
alternate `k`, regularization selection, checkpoint change, feature search, or
automatic retry is permitted. Report optimizer success, iterations,
coefficients, fold-fit scaling, rank/conditioning diagnostics, and the paired
score-time candidate deltas. Diagnostics cannot change the decision rule.

## Predeclared decision and route actions

**Support the linear-representation-failure hypothesis** only if the nonlinear
offset arm has lower aggregate equal-event Brier and log loss than both the
linear-offset state arm and raw market, and it has lower Brier than the
linear-offset state arm in at least 3/4 folds. Grouped intervals and
date/week breadth must be reported but are diagnostic, not a post-hoc gate.

**Refute this exact nonlinear-representation hypothesis** if the nonlinear
offset arm fails either aggregate proper-score comparison against the
linear-offset state arm, or wins Brier in fewer than 3/4 folds. A valid
refutation can earn research credit 2 because it resolves the predeclared
question negatively; it does not make the model an incumbent.

**Inconclusive/narrowing evidence** is the case where the nonlinear arm beats
the linear-offset arm under the representation rule but fails to beat raw
market on both aggregate proper scores. Assign credit 1 at most, keep raw
market as incumbent, and permit no automatic follow-up.

**Stop rule:** stop after the one frozen run, or immediately on any source hash,
denominator, exclusion, checkpoint, common-mask, availability, optimizer, or
boundary failure. Do not repair, retry, select another `k`, add a feature, or
change a threshold after viewing scores.

Route actions after independent review:

- support: retain the nonlinear-offset branch as the next research parent; it
  may replace only the in-game diagnostic incumbent if the exact raw-market
  comparison also passes, never as promotion or formal OOS evidence;
- refute: archive and stop the exact `score_time_ratio_k4` branch; retain the
  broader PBP/game-state hypothesis as unproven, not disproven;
- invalid execution/review: credit 0, no active-pool or budget hint.

## Resource and authority cap

- local fits: at most `12`;
- wall time: at most `10 minutes` for the experiment process;
- memory: at most `1 GiB` RSS;
- network bytes: `0`;
- provider calls/cost: `0 / $0`;
- data: already-opened local Train artifacts only;
- Dev/Final, external acquisition, publication, promotion: forbidden;
- retry count: `0`.

This is a non-authoritative budget hint inside the existing local Discovery
scope. It does not enlarge the project budget or permissions.

## Launch gate

Do not implement or execute from this decision until the Supervisor records an
independent **PASS** for the exact v0 result artifact and then independently
reviews the frozen v1 implementation/pre-score lock. Any source or artifact
hash change requires a new review, not silent rebinding.
