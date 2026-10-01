# Discovery Attempt 3 Controller decision — MarketRecencyWeightedCompositePath-v3

Time: 2026-09-29, after completion of real opened-Train Discovery Attempt 2.

Status: **exactly one next candidate selected and frozen before implementation
or its scores**.  This Controller task read resident local Train artifacts and
existing research memory, plus performed arithmetic on already-recorded
Attempt-2 diagnostics.  It did not implement, fit, score, invoke a candidate
runner, open Dev/Final, access a network/provider, spend money, publish or
promote.  It therefore does not consume a continuous-Discovery execution
attempt.

## Evidence and boundary read

Completed Attempt-2 artifact:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-recent-composite-path-20260929-01`.

| Artifact | SHA-256 |
| --- | --- |
| exclusions | `1ee1b77e6f1f71b4382c452916afe51d19d7edfa8b1a9844fd81e21f18d887e2` |
| input receipts | `eeb0449123c55e6b0b3e7f7b314c9b5327b1404041d3dd5fb18dededdf718640` |
| manifest | `3434aef3a97fc54b61a6d0c762a1f80523d24f3a96c0071dd77944befef7683c` |
| pre-score lock | `fc462890587cc7dc9a079acb128590a7a7ccdf5494c30be5d5136c3ee1a8ce62` |
| predictions | `7691a6dbee6b7dc0949583a7a421e7a421ad7565caaf20ebf559121b1b76cca2` |
| scorecard | `29632c1a8879be045ffb5018067ec72c3eca70fad44f43b9b5a60060f1e992d8` |
| staleness inventory | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |

The manifest is complete and reports exactly four candidate fits, zero control
refits, zero provider cost, external fetch false, Dev/Final closed and
promotion false.  It preserves the 195-event / 42-date source, 194 binary
events after the sole frozen GB-DAL tie exclusion, and the identical 87-event
/ 20-date / seven-observed-week Discovery check mask.  Before Attempt 3 is
executed, the Supervisor must separately require a passing independent
Attempt-2 result review bound to these exact hashes.

Research memory read includes the settlement, full-offset, market-only
calibration and Attempt-1 results; both prior Controller recipes; the
Attempt-2 implementation/pre-score review; the opened-Train override; and the
`indicator-prediction-evals` temporal, sign and family-collinearity guidance.
No new literature or external source was queried.

## What Attempt 2 established diagnostically

Attempt 2 correctly returns **REVERT current-best replacement** under the
frozen rule, even though its aggregate proper scores improve.  Lower is
better.

| Arm | Equal-event Brier | Equal-event log loss |
| --- | ---: | ---: |
| Decision-time market, incumbent | 0.2055333637 | 0.5984509292 |
| `MarketRecentCompositePath-v2` | **0.2042380588** | **0.5963727488** |
| Market-only calibration | 0.2058518570 | 0.5993850089 |
| Attempt 1 | 0.2069233196 | 0.6025293021 |
| Full offset | 0.2094506542 | 0.6082677941 |
| Ordinary reference | 0.2356047245 | 0.6759482937 |

Attempt 2 improves on market by `-0.0012953049` Brier and
`-0.0020781804` log loss; on calibration by `-0.0016137983` and
`-0.0030122601`; and on Attempt 1 by `-0.0026852608` and
`-0.0061565533`.  Its calibration slope is `1.00143`, versus market's
`1.01551`, while all forecasts use the same rows.  This is meaningful
Discovery evidence that the compressed path family can add information; it
is not formal OOS evidence.

The frozen decision remains REVERT because candidate-minus-market Brier by
fold is `+0.0036841, +0.0002418, -0.0045167, -0.0050518`: only folds 3 and 4
win.  Log-loss deltas have the same signs.  Complete-day and observed-week
intervals still cross zero.  Candidate loss improves on 12/20 schedule dates
and 4/7 observed game weeks; the gains are not universal or statistically
resolved.

The representation itself remains usable rather than collapsed.  Selected-fit
composite residual/raw variance fractions are `0.9815–1.0064`, composite
scales are `0.9596–0.9713`, and both families remain active.  Residual `g/d`
correlations are still high at `0.8417–0.8868`, supporting the one-composite
representation rather than reopening separate coefficients.

The decision-relevant failure is now isolated to **temporal weighting in the
trainer**:

| Fold | Equal-three-week fit moment | fitted `w_c` | check moment | score result |
| ---: | ---: | ---: | ---: | --- |
| 1 | -0.12484 | -0.10151 | +0.08799 | loses |
| 2 | -0.00747 | -0.00616 | +0.10550 | near-tie loss |
| 3 | +0.08830 | +0.07331 | +0.16866 | wins |
| 4 | +0.11884 | +0.09783 | +0.09949 | wins |

Within the same frozen three-week transformed rows, weekly composite moments
from oldest to newest are:

- fold 1: `-0.04208, -0.15736, -0.16955`;
- fold 2: `-0.13912, -0.12970, +0.28547`;
- fold 3: `+0.30339, -0.14370, +0.12058`;
- fold 4: `+0.10991, -0.06207, +0.32160`.

Thus equal weighting makes fold 2 almost exactly zero even though its newest
fully prior week and its check aggregate are positive.  It also attenuates the
same positive direction in folds 3 and 4.  Fold 1 remains a genuine prior/check
sign reversal that no honest past-only weighting can remove.  The evidence
does **not** justify a permanent positive sign constraint: weekly and date
breadth remain mixed and fold 1 points the other way.

For the single frozen weighting rule below, the pre-fit arithmetic weighted
moments are `-0.1488757, +0.0914056, +0.0687925, +0.1768619`.  These values
were computed from the already-recorded Attempt-2 per-week moments and row
counts, not from an Attempt-3 fit or score.  They establish that the proposed
convex objective's gradient at zero has negative/positive/positive/positive
directions before implementation.  They are diagnostics, not acceptance
gates.

## Exactly one next candidate: `MarketRecencyWeightedCompositePath-v3`

### Question and changed stage

Question: keeping the exact three-week population, representation, market
anchor and regularization fixed, does a causal half-weight-per-week loss reduce
the observed one-week sign lag enough to improve proper-score breadth?

Only the **prediction trainer's row weights** change.  This is not a sweep of
one-, two-, four- or five-week windows: the exact Attempt-2 three-week cohort,
transform and one-parameter model stay fixed.  No feature, scorer, mask,
cutoff, exclusion, penalty, control or KEEP rule changes.  This focused A/B is
the one further path-family experiment justified by Attempt 2's aggregate
gain and later-fold breadth.

### Frozen population, time and controls

Preserve exactly:

- source/cohort hashes, 195-event denominator, 194 binary materializations,
  sole `2025_04_GB_DAL / unresolved_outcome` exclusion, home/token
  orientation, kickoff-minus-15-minute cutoff, inclusive 600-second
  staleness gate, outcome-availability rule and no imputation;
- 22 initial dates plus four nonoverlapping five-date check folds and exact
  87-key check mask
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`;
- equal-event Brier primary, log loss, calibration, folds, complete-date
  resampling and observed-week sensitivity with seed 23 and 1000 replicates.

The current best remains raw market because Attempt 2 did not meet the frozen
fold-breadth rule.  Bind all seven Attempt-2 artifact hashes above and require
exact identity/order/outcome/market parity.  Reuse these six immutable control
arms without refitting: market, ordinary reference, market-only calibration,
full offset, Attempt 1, and Attempt 2.  The Attempt-3 scorecard has those six
controls plus the new candidate.  Any control refit is invalid.

### Frozen three-week rows and transform

Reuse Attempt 2 byte-for-byte in semantics:

1. Numerically parse exact `YYYY_WW_AWAY_HOME` game-week labels.
2. For each fold, select the three largest fit-week labels strictly below the
   earliest check week.  Same-week outcome-known games remain ineligible.
3. Require the exact production cohorts: weeks `05/06/07`, `06/07/08`,
   `08/09/10`, `10/11/12`; rows `44/43/41/43`; class counts
   `22/22`, `26/17`, `20/21`, `25/18`; and per-week counts
   `14/15/15`, `15/15/13`, `13/14/14`, `14/15/14`.
4. Require at least three fully prior week labels, at least 30 rows, both
   classes, and every selected outcome available before the first check
   cutoff.

Use the same exact-name causal families:

```text
g = p_market - mean(VWAP_15m, VWAP_60m, VWAP_240m)
d = mean(last_minus_first_15m,
         last_minus_first_60m,
         last_minus_first_240m)
```

Fit the market-logit population scaler, rank-two
`numpy.linalg.lstsq([1,z_market],[g,d],rcond=1e-12)` residualizer, residual
family population scalers, equal-weight `c_raw=(z_g+z_d)/2`, and composite
population scaler on all selected three-week rows **without row weights**.
Apply those exact transforms to older-fit diagnostics and check rows.  A family
or composite fit standard deviation at most `1e-8` makes it inactive and zero
everywhere without dropping a row.  Require finite values and rank two.

Keeping preprocessing unweighted is deliberate: it changes only the trainer
and makes archived Attempt 2 the exact unweighted-loss control.

### Frozen recency-weighted one-parameter trainer

Order the selected week labels from oldest to newest and assign every event in
that week the label-only weight:

```text
a_oldest = 0.25
a_middle = 0.50
a_newest = 1.00
```

This is a fixed one-week half-life.  Do not renormalize by week count, outcome,
feature value, date, team or score.  The weighted mean below normalizes by the
sum of event weights:

```text
eta_i = market_logit_i + w_c * z_composite_i
p_i_candidate = sigmoid(eta_i)
J(w_c) = sum_i a_i * (logaddexp(0, eta_i) - y_i*eta_i) / sum_i a_i
         + 0.5 * w_c^2
dJ/dw_c = sum_i a_i*z_i*(sigmoid(eta_i)-y_i) / sum_i a_i + w_c
```

Use float64, lambda `1`, one unconstrained coefficient, zero initialization,
analytic gradient and L-BFGS-B with `maxiter=1000`, `gtol=1e-8`,
`ftol=1e-12`.  Require optimizer success, finite objective/parameter/gradient
and final gradient infinity norm at most `1e-6`.  Fit no intercept or market
slope.  Perform no early stopping, sign constraint, sweep, clipping, fallback,
post-score change or retry.

When `w_c=0`, return the original market probabilities bit-for-bit.  All
nonzero probabilities must satisfy the unchanged `[1e-6,1-1e-6]` rejection
contract.  Fit exactly four new one-parameter candidates, one per fold.  Every
control fit count is zero and provider cost is `$0`.

The unnormalized weight sums implied by the frozen cohorts are exactly
`26.0, 24.25, 24.25, 25.0`; verify them before fitting.  Report Kish effective
row counts as diagnostics, but do not gate or tune on them.

### Frozen diagnostics; never model inputs or gates

For each fold, retain all Attempt-2 selected/older/check diagnostics and add:

- exact event weight for every selected row, weight totals by week and class,
  total weight, squared-weight sum and Kish effective row count;
- unweighted and weighted composite signed moments overall and by selected
  week;
- gradient at zero and its sign, fitted `w_c`, optimizer diagnostics and
  min/mean/max probability correction;
- candidate-minus-market, candidate-minus-Attempt-2 and
  candidate-minus-each-other-control fold deltas;
- selected/older/check row, schedule-date and game-week counts/labels, family
  variance, residual/raw fractions, market correlations, `g/d` residual
  correlation, Pearson/rank associations and per-date/per-week moments.

Diagnostics must be computed in a fixed order and cannot select weights,
change a sign, alter the transform, gate predictions or affect KEEP/REVERT.
Check diagnostics remain after prediction.  No candidate uses check labels.

### Scorecard and current-best decision

Use one common 87-event mask for all seven arms.  Report equal-event
Brier/log loss and calibration, all four folds, full denominator accounting,
paired candidate-minus-each-control deltas, complete-schedule-day resampling
and observed-game-week sensitivity.  Whole units are resampled and their
events pooled before recomputing the equal-event loss.  Retain the one-event
right-edge observed week and label week inference descriptive only.

The current-best KEEP rule is unchanged.  KEEP only if the new candidate:

- beats market on aggregate Brier and log loss by more than `1e-12`;
- beats ordinary on aggregate Brier and log loss by more than `1e-12`;
- beats market on Brier in at least three of four folds; and
- beats ordinary on Brier in at least three of four folds.

Otherwise REVERT current-best replacement.  Separately report whether it
beats archived Attempt 2 on both aggregate scores and on fold Brier breadth.
No confidence interval is a KEEP gate.  KEEP/REVERT concerns only the current
Discovery incumbent, never promotion, publication or formal OOS status.

### Structured invalidation gates

Fail the fresh ID with a structured receipt, consuming an execution attempt,
for any of the following:

- source, artifact, Controller recipe, passing Attempt-2 result review, code,
  runtime or dependency drift; archive file-set/hash/control parity failure;
- denominator, sole exclusion, materialized keys, staleness, check mask, fold,
  selected week, row/class/per-week count, weight assignment or weight-sum
  mismatch;
- missing/nonfinite exact-name input, outcome-time leakage, rank failure,
  inactive-rule violation or any dropped/imputed event;
- objective/gradient mismatch, optimizer failure, gradient norm above
  `1e-6`, nonfinite value or rejected probability;
- any control refit, network/provider/Dev/Final access, hidden candidate,
  hyperparameter/window/decay sweep, score-driven repair or denominator
  reduction.

The failure receipt must truthfully distinguish pre-fit, optimizer-started and
scoring-started phases.  Do not repair or retry in place; a code repair needs
independent review and a fresh artifact ID.

## Evidence categories

**Literature-supported evaluation principles reused from the established
research record:** prior-only temporal preprocessing/fitting; proper scores on
identical paired rows; dependence-aware grouped resampling; diagnosing
raw/partial information separately from trainer failure; and compressing a
highly correlated family before top-level fitting.  These principles do not
endorse exponential weighting or prove path predictiveness.

**Project choices, not literature consensus:** NFL seed domain; 15-minute
cutoff; inclusive 600-second staleness; 22 + 4x5 folds; exact three fully prior
weeks; unweighted transform; equal `g/d` composite; weights
`0.25/0.50/1.00`; lambda one; no intercept/market slope; optimizer tolerances;
seed 23; 1000 resamples; and the KEEP rule.

**Unvalidated hypotheses:** the path relation evolves quickly enough that
half-weight-per-week loss is preferable to equal-three-week loss; the newest
week contains useful regime information rather than noise; fold 2's sign lag
is representative rather than validation overfit; and the same weighting can
retain folds 3–4 gains without worsening calibration or concentration.

## Controller memory for implementation and the next round

- Attempt 2 is a retained positive research branch but not the incumbent.  It
  improved both aggregate proper scores while failing the predeclared fold
  breadth rule.
- Attempt 3 must be a thin trainer-only delta and must archive every control.
  Do not change the cohort, representation, penalty or scorer while
  implementing it.
- Selection of the half-life used label-dependent Attempt-2 fold/week/date
  evidence from repeatedly inspected Train.  The new result is therefore
  adaptive Discovery, not untouched validation, even though prediction-time
  row weights are causal and label-blind.
- If Attempt 3 fails proper-score breadth or loses materially to Attempt 2,
  retain both branches and move to a different information family.  Do not
  sweep alternative half-lives, windows or sign constraints on these same 87
  checks in this batch.
- Nothing here supports promotion, profitability, cross-domain transfer,
  formal OOS gain, RSI self-evolution, or freedom from historical-event
  memorization.  Dev/Final and future-event final evaluation remain closed.
