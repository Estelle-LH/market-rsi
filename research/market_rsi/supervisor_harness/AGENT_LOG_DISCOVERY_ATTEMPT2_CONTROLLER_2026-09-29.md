# Discovery Attempt 2 Controller decision — MarketRecentCompositePath-v2

Time: 2026-09-29, after completion of continuous-Discovery Attempt 1.

Status: **one next candidate selected and frozen before implementation or its
scores**.  This Controller task only read resident local Train artifacts and
the existing research memory.  It did not implement, fit, score, open
Dev/Final, use network/provider services, publish, promote, or spend money.
The exact backend slug was not independently queried in this task; do not infer
a model upgrade or attribute one to RSI.

## Evidence read and boundaries

Attempt-1 artifact:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-orthogonal-price-path-20260929-01`.

| Artifact | SHA-256 |
| --- | --- |
| exclusions | `e6ccbe815a5872261d3c07958506a602ed96ca0355913b079a1594c44a91fa3a` |
| input receipts | `51fa298e2f6c7b672aedba1ed3d14aa5542e0f00232498f957a84298578c584d` |
| manifest | `e3ec0981f705ec511fa830680ddbe5f2e490e6a6be6eaa58550204de20725da4` |
| pre-score lock | `365416786811f393ffa0e39f808404b8987f67c69b0c7bdce0b498363a51d9f4` |
| predictions | `9d2d15a4a61d91aabc0862809906aebf8be7382dfaa380064676284ecd02dcc6` |
| scorecard | `263acc091232f0d3c27a3e4cd8bd0ef7aa392e00f06a0fc89dc6323c2692e4a4` |
| staleness inventory | `3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e` |
| Attempt-1 runner | `af4508f0c808fbc236daae6607343c47238db26e2148289a08670fe71102f380` |

The artifact is complete, zero-cost, uses 195 source events / 42 schedule
dates, materializes 194 binary events with the one frozen GB-DAL tie
exclusion, and scores the identical 87-event / 20-date / seven-observed-week
Discovery mask.  It reports 12 fits as frozen and no archived full-offset
refit.  The manifest says no network, provider, Dev/Final, publication or
promotion.  The Supervisor must still require its independent result review
to pass before admitting Attempt 2; a later P0 review finding invalidates this
scientific handoff rather than being worked around.

Read research memory includes the original settlement scorecard, full-offset
and market-only calibration results, the pre-Attempt-1 Controller recipe, the
opened-Train override, the continuous batch record, and the
`indicator-prediction-evals` family-compression/sign guidance.  A read-only
inventory of the already authorized Train was used only to bind the exact
recent-week row counts below.  No candidate fit or score was computed, so this
planning work does not consume a batch execution attempt.

## Attempt-1 interpretation

Attempt 1 correctly returns **REVERT current-best replacement**.  Lower loss
is better.

| Arm | Brier | Log loss |
| --- | ---: | ---: |
| Decision-time market, incumbent | **0.2055333637** | **0.5984509292** |
| Market-only calibration | 0.2058518570 | 0.5993850089 |
| `MarketOrthogonalPricePath-v1` | 0.2069233196 | 0.6025293021 |
| Archived full offset | 0.2094506542 | 0.6082677941 |
| Ordinary LogisticRegression reference | 0.2356047245 | 0.6759482937 |

Attempt 1 loses to market by `+0.0013899559` Brier and `+0.0040783729`
log loss and loses to calibration by `+0.0010714625 / +0.0031442933`.
It nevertheless recovers `-0.0025273346 / -0.0057384920` relative to the
17-feature full offset.  All complete-day and observed-week descriptive
intervals for these three comparisons cross zero.  In particular,
candidate-minus-market complete-day intervals are
`[-0.0011675608, 0.0047585259]` Brier and
`[-0.0016193761, 0.0120504197]` log loss.  These are reused Train diagnostics,
not formal uncertainty guarantees.

The failure is informative at the raw-signal-to-trainer boundary:

1. Both residual path families stay active and retain most raw variance after
   linear market residualization.  Across folds, residual/raw variance is
   about `0.9568–0.9963` for `g` and `0.9258–0.9711` for `d` on fit rows.
   This rejects the narrow explanation that the market-level projection
   mechanically erased the families; it does not establish predictiveness.
2. The two residual families are strongly redundant: fit correlations are
   `0.7913, 0.8210, 0.8190, 0.8259`; check correlations are
   `0.9118, 0.8218, 0.8684, 0.8975`.  Their separately fitted coefficients
   also move together.  Keeping two coefficients spends degrees of freedom
   without clearly separating two information sources.
3. The expanding-fit signed moments `mean(z*(y-p_market))` for both families
   are negative in folds 1–3 and only become slightly positive in fold 4.
   The resulting `(w_g,w_d)` are respectively
   `(-0.03794,-0.03520)`, `(-0.01894,-0.01797)`,
   `(-0.01124,-0.00585)`, then `(0.00897,0.00859)`.
4. In contrast, aggregate check moments are positive for both families in all
   four folds.  Check Pearson associations are positive in all eight
   fold/family cells; rank association is less convincing, especially for
   `g`.  Per-date breadth is mixed rather than universal: positive signed
   moments occur on 10/20 dates for `g` and 12/20 for `d`.  Therefore this is
   evidence of temporal mismatch and event concentration, not a basis for a
   permanent hard momentum sign.
5. The candidate loses to market on both scores in folds 1–3.  Once the
   expanding fit finally turns both coefficients positive in fold 4, it beats
   calibration on both scores and beats market on Brier, but still loses
   market log loss slightly.  This is consistent with stale history delaying
   adaptation, though the small check folds cannot prove that cause.

Classification: the compressed path family is **Category B/C unresolved**.
It has residual variance and repeated aggregate check association, but weak
date breadth, high within-family redundancy and a trainer whose historical
sign is late.  It should not replace the market.  One direct adaptive trainer
test is worth more than adding another broad feature set.  If that test fails,
the path branch should be deprioritized rather than endlessly tuned.

## Exactly one next candidate: `MarketRecentCompositePath-v2`

### Question and changed component

Question: can a strictly prior, recent three-game-week estimate of one
compressed signed path family adapt to the observed midseason relation while
preserving the market exactly when the family coefficient is zero?

This is a combined **representation + training-window + trainer** Discovery
change.  Any improvement belongs to the whole recipe.  It is not a causal
ablation of recency, compression, or removal of calibration terms.

### Frozen population, timing and controls

Keep unchanged:

- exact source hashes, 195-event denominator, 194 binary events, and sole
  `2025_04_GB_DAL / unresolved_outcome` exclusion;
- home/token orientation, kickoff minus 15-minute cutoff, inclusive
  600-second latest-trade gate, outcome-availability rule, and no imputation;
- 22 initial dates plus four expanding five-date check folds;
- exact 87-key check mask
  `eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`;
- equal-event Brier primary, log loss, calibration, folds, complete-day
  resampling and observed-week sensitivity with seed 23 / 1000 replicates.

The current best remains raw decision-time market.  Bind the complete Attempt-1
artifact by all seven hashes above.  Reuse its market, ordinary, calibration,
archived full-offset and Attempt-1 prediction columns as immutable controls;
require exact keys/order/outcomes/market values and their artifact hashes.
Do not refit any control.  The new scorecard therefore has six arms:
market, ordinary reference, market-only calibration, archived full offset,
archived Attempt 1, and the new candidate.

### Strictly prior recent candidate fit rows

For each outer fold, derive NFL game-week labels using the existing exact
`YYYY_WW_AWAY_HOME` parser.  Let `first_check_week` be the numerically earliest
week label represented in that fold's check rows.  Eligible candidate weeks
are distinct fit-row week labels **strictly less** than
`first_check_week`; this excludes a partially observed same-week Thursday or
Sunday even if that game's result is already available.  Select the three
largest eligible labels and use every eligible fit row in those weeks.  Do not
select by score, feature value, team, outcome or row count.

The frozen real candidate fit cohorts are:

| Fold | Selected fully prior week labels | Rows | y=1 / y=0 | Per-week rows |
| ---: | --- | ---: | ---: | --- |
| 1 | `2025_05, 2025_06, 2025_07` | 44 | 22 / 22 | 14 / 15 / 15 |
| 2 | `2025_06, 2025_07, 2025_08` | 43 | 26 / 17 | 15 / 15 / 13 |
| 3 | `2025_08, 2025_09, 2025_10` | 41 | 20 / 21 | 13 / 14 / 14 |
| 4 | `2025_10, 2025_11, 2025_12` | 43 | 25 / 18 | 14 / 15 / 14 |

Require these exact labels/counts on the frozen real cohort, at least three
eligible prior week labels, at least 30 selected rows, both outcome classes,
and every selected outcome available before the first check cutoff.  Failure
is `INVALID_DATA_QUALITY`, not fallback to expanding history.

### Frozen feature transform

Use the same exact-name causal inputs as Attempt 1.  For event `i`, with
decision-time market probability `p_i` and market logit `m_i`:

```text
g_i = p_i - mean(VWAP_15m, VWAP_60m, VWAP_240m)
d_i = mean(last_minus_first_15m,
           last_minus_first_60m,
           last_minus_first_240m)
```

Fit all transforms on the selected three-week candidate rows only:

1. Standardize `m` to `z_m` with a population-standard-deviation scaler.
2. Residualize `[g,d]` by
   `beta = numpy.linalg.lstsq([1,z_m], [g,d], rcond=1e-12)[0]`.
   Require rank two and apply the same beta to candidate-fit, older-fit
   diagnostics, and check rows.
3. Standardize each residual family by its selected-fit mean and population
   standard deviation.  Preserve Attempt 1's inclusive inactive threshold:
   if a residual standard deviation is at most `1e-8` probability units, set
   that family to zero on every row and report it; never drop a row.
4. Form the fixed equal-weight composite
   `c_raw = (z_g + z_d) / 2`.  Re-standardize `c_raw` using only its selected
   fit mean and population standard deviation to obtain `z_c`.  If both
   families are inactive or the composite standard deviation is at most
   `1e-8`, set `z_c=0` on fit/check and report the composite inactive.

Equal family weights are frozen before scores.  No PCA, horizon selection,
outcome-selected weights, team/date identity, activity, size, volatility or
staleness value enters the predictor.  Staleness remains a common integrity
gate.  The selected-fit composite population standard deviations observed in
the read-only recipe inventory are approximately
`0.96395, 0.97130, 0.96473, 0.95962`; this is a pre-fit arithmetic check, not a
performance result or tuning gate.

### Frozen one-parameter trainer

Do not fit an intercept or market recalibration slope.  Fit exactly one
unconstrained residual coefficient:

```text
eta_i = m_i + w_c * z_c_i
p_i_candidate = sigmoid(eta_i)
J(w_c) = mean(logaddexp(0, eta_i) - y_i*eta_i) + 0.5*w_c^2
```

Use float64, lambda `1`, all-zero initialization, analytic gradient,
L-BFGS-B, `maxiter=1000`, `gtol=1e-8`, `ftol=1e-12`; require optimizer
success, finite values and final gradient infinity norm at most `1e-6`.
Allow both signs.  The evidence does not justify a hard permanent momentum
constraint.  Reuse the probability rejection interval
`[1e-6, 1-1e-6]`; no clipping, fallback, early stopping, hyperparameter sweep
or post-score coefficient change.

When `w_c=0`, the candidate is bit-for-bit the decision-time market forecast.
This removes the known small calibration cost and gives a clean test of the
recent composite path correction.  Fit budget is exactly **four new
single-parameter candidate fits**: one per outer fold.  Ordinary,
market-only calibration, full offset and Attempt 1 are archive-only controls,
so their refit counts are all zero.  Provider cost remains `$0`.

### Fixed diagnostics; never gates or tuning inputs

For each fold, report separately for selected recent fit rows, older eligible
fit rows, and check rows:

- row/date/week counts and the exact selected week labels;
- `g`, `d` and composite raw/residual variance and residual/raw fraction;
- raw and residual correlation with market logit;
- `g`/`d` residual correlation and composite scale;
- Pearson, average-rank Spearman, and
  `mean(z*(y-p_market))` for `g`, `d` and `z_c`;
- per-schedule-date and per-game-week composite signed moments;
- `w_c`, optimizer diagnostics and min/mean/max probability correction.

The selected three-week composite signed moments found by the read-only
arithmetic inventory, before any candidate fit/score, are
`-0.12484, -0.00747, +0.08830, +0.11884`; corresponding check moments are
`+0.08799, +0.10550, +0.16866, +0.09949`.  These values motivate the recency
test and make its failure mode explicit: fold 1 still has a prior/check sign
reversal, fold 2 is nearly neutral, and folds 3–4 agree.  They must not select,
flip, constrain, drop or tune anything during execution.

### Scorecard and decision

Report six-arm equal-event Brier/log loss and calibration, all fold metrics,
complete population accounting, and paired candidate-minus-market,
candidate-minus-ordinary, candidate-minus-calibration,
candidate-minus-full-offset and candidate-minus-Attempt-1 deltas.  Resample
whole schedule-day units and observed game-week units, pooling all games in
each sampled draw before recomputing the equal-event metric.  Preserve the
partial right-edge week and label week inference secondary/descriptive.

Current-best `KEEP` rule is unchanged:

- candidate aggregate Brier and log loss each beat market by more than
  `1e-12`;
- candidate aggregate Brier and log loss each beat ordinary by more than
  `1e-12`;
- candidate Brier beats market in at least 3/4 folds; and
- candidate Brier beats ordinary in at least 3/4 folds.

Otherwise REVERT current-best replacement.  No confidence-interval gate is
added.  Separately report whether the candidate beats Attempt 1 and
calibration on both aggregate proper scores and their fold Brier wins.  A
failure does not delete either branch.  If recent composite association is
present but proper scores fail, retain the evidence as trainer/category-B
memory.  If association and proper-score breadth both fail, deprioritize this
path branch and move to a different information family next round instead of
tuning week count on these same checks.

### Invalidation gates

Fail the fresh run with a structured receipt, consuming its execution attempt,
for any of the following:

- source/artifact/code/runtime/hash drift or archive-control parity above
  `1e-10`;
- denominator, exclusion, materialized-key, check-mask, fold or exact recent
  cohort mismatch;
- missing/nonfinite named inputs, stale required row, outcome-time leakage,
  fewer than three strictly prior week labels, fewer than 30 recent rows, or
  one-class recent labels;
- residualization rank failure, nonfinite transform/objective/gradient,
  optimizer failure, gradient norm above `1e-6`, or rejected probability;
- any network/provider/Dev/Final access, control refit, hidden sweep, or
  denominator reduction.

Do not repair in place or reuse a failed artifact ID.  A source-code repair
requires review and a fresh ID; it counts as another attempt only when its
real runner is invoked.

## Evidence categories

**Literature-supported evaluation principles reused:** strictly prior temporal
fitting/preprocessing; identical paired rows and scoring rules; dependence-
aware grouped resampling; diagnosing raw/partial association before declaring
a family useless; and controlling correlated feature families by compression.
These principles do not endorse this exact NFL window or guarantee gain.

**Project-chosen parameters, not literature consensus:** NFL seed domain;
15-minute cutoff; 600-second staleness; 22 + 4x5 outer folds; exactly three
fully prior game-week labels; equal `g/d` weights; linear market
residualization; `1e-12` rcond; `1e-8` inactive threshold; lambda 1; the
one-parameter no-calibration offset; optimizer tolerances; seed 23; 1000
resamples; and KEEP rule.

**Hypotheses still to validate:** recent weeks better represent the conditional
path relation than the expanding season; one composite reduces harmful
redundancy; removing affine market calibration preserves the stronger market
anchor; and these changes improve proper scores.  Attempt 2 cannot establish
formal OOS performance, profitability, cross-domain transfer, RSI
self-evolution, or freedom from historical-event memorization.

## Controller memory handed to implementation/result review

- Market remains the incumbent; `REVERT` only rejects current-best
  replacement.
- Attempt 1 improved materially over the broad full offset but still damaged
  both proper scores versus market and calibration.
- Its most decision-relevant pattern is stale expanding-fit sign plus high
  `g/d` redundancy, not a lack of residual variance.
- Attempt 2 is deliberately the last immediate path-family trainer test unless
  its raw/prediction diagnostics justify more.  Do not respond to a weak score
  by sweeping 1/2/4/5-week windows on the same 87 checks.
- Preserve every branch/result.  Reused Train validation remains Discovery;
  Dev/Final and future formal evaluation stay closed.
