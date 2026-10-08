# Controller: next settlement-probability Train hypothesis

2026-09-29 16:55:50 UTC. Author identity supplied by this Controller dispatch:
**gpt-6-astra with high reasoning effort**. This is a Controller-authored
scientific proposal, not GLM authorship or an executed experiment.

Status: **ONE EXPERIMENT PROPOSED; NOT IMPLEMENTED OR RUN.** Mainline remains
`SettlementProbabilityTrainDiagnostic-v0`. The next candidate is
`MarketOffsetRidgeLogistic-v1`. No Dev/Final, network, provider, paid fit,
publication, deployment or promotion was used or authorized by this task.
Only this log was written. Existing dirty work was preserved.

## Evidence and decision

I read `research/market_rsi/AGENTS.md` (there is no repository-root AGENTS.md),
the current research state and supervisor instructions, the first-real-Train
pipeline audit, the runner's fitting/scoring implementation, the local
literature-to-harness record, and the indicator-prediction-evals skill and its
evaluation gates. The current research-state page contains legacy
60/300-second price-change material; none is used as evidence for this
settlement-probability proposal.

The exact parent artifact directory is:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-nfl-settlement-20260929-02`

Read `pre_score_lock.json`, `manifest.json`, `scorecard.json`,
`predictions.csv` and `exclusions.json`. Their SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| pre_score_lock.json | `1f54eb27bc22a728c67d161a512ccab0a5fa38f20c28aa6ee11f5b57f7489019` |
| manifest.json | `a36bce7debb71333caa7b35afebeaf9e7adcdd0e07c1679fbf70369dffa6bcb4` |
| scorecard.json | `98f78e0bc68f7743881d285560b5fbc1a9a6b74b5178601ff6fc4201128fb710` |
| predictions.csv | `f91647a2a5b84836bd717ce2d0c6fd404bc1f4a759342a8b8d40fc6e576f37c1` |
| exclusions.json | `cf61302708a6535b892232d3cf499575e3a8909a4aad1e8de1a0b7959a0164bd` |

These results cover 87 check events on 20 already inspected Train schedule
dates. There are 195 source events on 42 schedule dates, 194 binary rows and
one explicit unresolved-outcome exclusion: `2025_04_GB_DAL`, source ordinal
53, schedule date `2025-09-28`, settlement prices not exact [0,1]/[1,0].

| Forecast | Brier | Log loss | OLS calibration slope | OLS calibration intercept |
| --- | ---: | ---: | ---: | ---: |
| Decision-time market | 0.205533 | 0.598451 | 1.015513 | -0.029218 |
| Ordinary LogisticRegression | 0.235605 | 0.675948 | 0.636661 | 0.172735 |
| HGB candidate | 0.269768 | 0.779223 | 0.351495 | 0.335512 |

HGB minus ordinary is **+0.034164 Brier and +0.103275 log loss**. HGB wins
against ordinary only in fold 2; the original decision is correctly REVERT.
The market wins both proper losses against both fitted models in all four
folds. LogisticRegression is only an **ordinary reference**, not a validated
strong baseline. Reverting HGB does not establish logistic regression as the
scientific incumbent: the market is the best forecast measured here.

| Fold | Fit/check events | Market Brier | Ordinary Brier | HGB Brier |
| --- | --- | ---: | ---: | ---: |
| 1 | 107 / 26 | 0.212095 | 0.221736 | 0.272738 |
| 2 | 133 / 16 | 0.203744 | 0.282285 | 0.220407 |
| 3 | 149 / 28 | 0.175080 | 0.214095 | 0.250400 |
| 4 | 177 / 17 | 0.247341 | 0.248309 | 0.343585 |

The calibration calculations are OLS of outcome on probability, not logistic
recalibration coefficients. Their slopes suggest excessive fitted forecast
spread and/or weak association, especially for HGB; they do not prove a unique
cause. Market's near-unit aggregate slope does not prove calibration within
every subgroup. I will not plug these inspected check-set coefficients into
a calibrator. With only 107 initial fit events and 17 partly redundant inputs,
learning an unrestricted replacement for market is a plausible failure mode.
The residual predictiveness of those inputs has not been established or
refuted by HGB's failure.

## Exactly one next experiment

**Hypothesis:** preserving decision-time market log-odds as the default and
learning a strongly regularized residual from the unchanged causal features
will retain useful market information and improve both proper losses over
market and the ordinary reference across most chronological Train folds.

Changed causal stage: **prediction only**. Replace the HGB candidate trainer
with one market-offset ridge logistic learner. Keep raw data, feature
formulas and ordering, normalizer, settlement target, cutoff, folds, event
weights, probability policy and proper scorer fixed. There is no PnL stage.
This is a single fixed prediction recipe, not a factorial experiment: even a
KEEP would not separate the contribution of anchoring from shrinkage.

For each fold, fit the existing StandardScaler on exactly its existing prior
fit rows. Let `z_i` be all 17 resulting standardized features, including
`market_logit`; do not select, compress, residualize or drop columns. Obtain
the unstandardized offset `m_i = log(p_market_i / (1-p_market_i))` from the
same frozen decision-time market probability. Fit 18 parameters, an intercept
`b` plus a vector `w`, with:

```text
eta_i = m_i + b + dot(w, z_i)
p_candidate_i = sigmoid(eta_i)

J(b,w) = mean_i[logaddexp(0, eta_i) - y_i * eta_i]
         + (1.0 / 2) * (b*b + dot(w,w))
```

The penalty applies to the intercept and every residual coefficient.
The loss is a MEAN, so lambda=1.0 has the same meaning at every fit size;
do not silently substitute sklearn's C=1 convention. No sign constraints.
The offset coefficient is fixed at 1; the standardized market-logit column
may learn a penalized correction, so the total market sensitivity is not
hard-constrained to 1. At all-zero residual parameters, predictions equal
the market exactly. This is an informative shrinkage center, not an assertion
that market is the true conditional probability. Lambda=1.0 is one declared
strong regularization choice, not selected by a sweep or optimality claim.

Use float64, all-zero initialization, `scipy.optimize.minimize` with
`method="L-BFGS-B"`, analytic gradient, `maxiter=1000`, `gtol=1e-8`,
`ftol=1e-12`, stable logaddexp and sigmoid. Require optimizer success, finite
objective/parameters/predictions, and final infinity-norm gradient <=1e-6.
Any failure is an implementation/fit failure, never a silent fallback to
market or a row deletion. Do not tune lambda, offsets, features, blend weights
or thresholds after seeing results. Use the existing reject policy outside
`[1e-6, 1-1e-6]`; no new clipping or post-fit calibration.

The ordinary reference remains exactly
`LogisticRegression(C=1.0, solver="lbfgs", max_iter=500, random_state=23)`
with the same scaler and matrix. Market, ordinary and candidate must produce
predictions on the identical 87 check keys. Recompute the ordinary control
and require agreement with -02 within 1e-10 per probability; market keys,
outcomes and probabilities must agree with the frozen materialization.
A discrepancy stops the comparison for investigation; it is not candidate
evidence. HGB's -02 results remain an archived failed comparison; no fourth
arm or HGB refit is needed.

Canonical candidate spec (SHA-256 below uses sorted keys, compact separators,
ASCII JSON):

```json
{
  "name": "MarketOffsetRidgeLogistic-v1",
  "offset": "unstandardized_market_logit_coefficient_1",
  "residual_inputs": "all_17_unchanged_fold_standardized_features_plus_intercept",
  "objective": "mean_bernoulli_nll_plus_0.5_lambda_times_squared_l2_all_18_parameters",
  "lambda": 1.0,
  "penalize_intercept": true,
  "initial_parameters": "all_zero",
  "optimizer": "scipy.optimize.minimize_L-BFGS-B",
  "jac": "analytic",
  "maxiter": 1000,
  "gtol": 1e-8,
  "ftol": 1e-12,
  "dtype": "float64",
  "probability_policy": "existing_reject_outside_1e-6_to_1_minus_1e-6",
  "hyperparameter_search": false
}
```

Candidate spec SHA-256:
`70dc3f086f704e01bb90cabd54bb817b6fccf6765e17ff28aa0d19d97ccdd1f1`.
Ordinary spec SHA-256 remains
`0759b88c679597203ca981abe8c60919eec35b8d621c6534518baaaa4c287752`.
Feature spec SHA-256 remains
`bac49f83adbdff4e775474d820d7f1d5b8029de563c82fabb2cf046b74123cab`.
The skill's `validate_component_ids` check was actually invoked and passed
for prediction as the sole differing arm component. The full skill validator
requires Final sessions; it was not invoked with fabricated Final dates.
These inspected Train dates cannot satisfy untouched-Final gates.

## Frozen population, dates and scorer

Preserve source/cohort hashes from -02, exact 195 denominator, exact 194
binary materialized rows, and the existing one-entry exclusion ledger.
Materialized-key SHA-256:
`59128473ae6c50b4acd2436ac18478d4fcd7dbd96ee887eb5ce2ae77ddfc72bd`.
Check-mask SHA-256:
`eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.
Use `event_start_utc minus 15 minutes`; orient home probability exactly as
before; size-weight same-second trades at the latest eligible integer second.
No quote/executable-price claim is implied by this last-trade baseline.

Copy the complete 42-schedule-date fold specification byte-for-byte in
semantic content from -02 `pre_score_lock.json`: first 22 schedule dates fit,
then four expanding five-date checks. Schedule `game_date`, not UTC cutoff
date, is the grouping key. Check blocks are:

```text
1: 2025-10-23, 2025-10-26, 2025-10-27, 2025-10-30, 2025-11-02
2: 2025-11-03, 2025-11-06, 2025-11-09, 2025-11-10, 2025-11-13
3: 2025-11-16, 2025-11-17, 2025-11-20, 2025-11-23, 2025-11-24
4: 2025-11-27, 2025-11-28, 2025-11-30, 2025-12-01, 2025-12-04
```

Keep the conservative outcome-availability maximum and strict availability
before first check cutoff; expected fit counts are 107/133/149/177, check
counts 26/16/28/17, unavailable-fit-label count zero. Do not relax any clock
rule to recover a count. Any mismatch fails pre-fit integrity.

Reuse the exact proper scorer, epsilon=1e-6, reliability bins=10, bootstrap
seed=23, replicates=1000 and date-block-days=1. Report equal-event aggregate
Brier/log loss, fold metrics, existing calibration diagnostics, paired
event/date losses, intervals, breadth and coverage for ordinary-market,
candidate-market and candidate-ordinary. Compute paired differences through
the existing same-row scorer; never subtract independent interval endpoints.
Intervals on adaptively reused Train dates remain descriptive. The decision
rule below changes research selection, not scorer arithmetic or its target.

## Staleness integrity correction for the next run

The -02 pre-score lock **did not set a finite maximum staleness**. The supplied
pre-score coverage inventory observed a maximum age of 313 seconds and no
staleness exclusions. That observation is a coverage fact, not evidence that
-02 enforced a maximum. Do not rewrite its lock, retrofit an ex-ante claim,
or infer a threshold from its losses. The 313-second value here is explicitly
the inventory fact supplied in this task, not independently rederived from
the five scored artifacts.

Freeze **max_staleness_seconds=600**, inclusive, before any next-run fit or
score. Ten minutes is a simple operational upper bound below the fixed
15-minute pregame lead and within the shortest 15-minute feature window; it
accepts the resident inventory's observed 313-second gap with availability
headroom. This is a data-quality judgment, not a statistically validated
freshness optimum or a threshold optimized on scores. Do not test multiple
age limits. Compute age as cutoff seconds minus latest eligible trade second;
require finite age in [0,600].

This common gate applies to all three forecast arms and is deliberately
non-filtering for this frozen comparison. Re-inventory the source denominator,
record observed maximum and every age violation with source ordinal,
game/event ID, schedule date, cutoff, last-trade second, observed age and
`staleness_limit_exceeded`. Retain those entries in the 195-event accounting;
never drop, refresh, impute or replace them. If any of the exact 194 required
binary rows violates the gate, stop the whole run before fitting/scoring,
mark it `INVALID_DATA_QUALITY`, and emit the failure report with expected and
actual counts. Keep the existing unresolved-outcome entry separately.
An integrity failure has no scientific KEEP/REVERT score.

This is an explicit common input-validation tightening relative to -02,
not another variable between the experiment arms. Its presumed nonbinding
status must be verified before interpreting a prediction-stage A/B. If it
would change the row set, the planned comparison is invalid rather than a
second data-selection experiment hidden inside the trainer test.

## Preregistered Discovery decision

First require all source, staleness, mask, availability, control-parity,
optimizer and probability checks to pass with the exact counts above.
For a valid completed run, **KEEP** this candidate for further Discovery iff
all conditions hold (a strict win means reference minus candidate >1e-12):

1. Candidate aggregate Brier and aggregate log loss both beat market.
2. Candidate aggregate Brier and aggregate log loss both beat ordinary.
3. Candidate Brier beats market in at least 3 of 4 folds, and beats ordinary
   in at least 3 of 4 folds, counted separately.

Otherwise **REVERT** the candidate; retain market as the measured forecast
reference and preserve all negative artifacts. Ties fail KEEP. The current
market/ordinary aggregates are numerical expectations, but decisions use
the controls recomputed on the identical next-run keys. No rounding before
comparison. Passing is a research prioritization result only: these check
folds are repeatedly opened Train, no longer untouched OOS. No promotion,
formal significance, profitability or validated strong-baseline claim follows.

Failure interpretation is predeclared. Beating ordinary but losing to market
means we repaired part of model-induced damage without discovering incremental
predictive value. Losing to both means this fixed residual learner did not
help; it does not prove features have no signal or all models fail. Beating
both aggregates but lacking 3/4-fold breadth suggests a concentrated result
that fails this rule. A numerical/data failure teaches about implementation
or source consistency, not the hypothesis. A KEEP supports this complete
prediction recipe on diagnostic Train only; it does not uniquely identify
overfitting or anchoring as the cause of the prior losses.

## Research provenance, planned verification and next memory

No live literature search was performed because this dispatch forbids
network. Local query used on 2026-09-29:
`offset|shrink|ridge|regulariz|forecast combination|Tibshirani|Hastie`
against the existing literature-to-harness record, minimal probability loop
and the day's supervisor logs. Relevant existing research reused:
`LITERATURE_TO_HARNESS_2026-09-10.md`, section 4 and the preprocessing notes,
which record prior reading of FPP3 rolling-origin evaluation
(https://otexts.com/fpp3/tscv.html) and sklearn 1.6 leakage guidance
(https://scikit-learn.org/1.6/common_pitfalls.html). Their applicability is
prior-only fitting and shared preprocessing, with additional whole-event
and label-availability requirements here. I read those local notes, not the
primary pages anew. No retrieved paper in this task establishes efficacy
of the proposed offset/penalty recipe; that is the Controller hypothesis.
Comparisons considered were a new feature family, post-fit recalibration,
and further nonlinear flexibility. I choose one anchored learner because
market preservation is a direct, low-parameter response to the current losses;
none of those alternatives is an additional proposed experiment.

Implementation and empirical validation are **planned, not done**. Before
the single future run, verify the analytic gradient against finite differences
on synthetic data, exact market recovery at zero residual parameters,
intercept-penalty and mean-loss semantics, fit-only scaling, label-availability
ordering, all three masks, and fail-closed 600-second boundary behavior at
600 and 601 seconds. Bind candidate spec, implementation/runtime, unchanged
source/feature/fold/scorer hashes and the new common gate to a fresh pre-score
lock and fresh artifact directory. No source, previous artifact, or scorer
rewrite is part of this proposal. Archive optimizer status and coefficients
per fold as diagnostics. The present task ran only a spec-hash/component
consistency check, no model fit, new prediction or candidate score.

Controller memory for the next turn:

- Mainline is settlement probability at kickoff minus 15 minutes; legacy
  60/300-second price-change MSE is separate.
- Population is 195/42, binary materialization 194, one unresolved GB-DAL
  exclusion, and 87 common checks over 20 reused Train schedule dates.
- Market beats both ordinary and HGB in every fold; HGB REVERT is final for
  -02. Ordinary logistic is a reference, not a proven strong baseline.
- Test only MarketOffsetRidgeLogistic-v1, all 17 unchanged inputs, mean NLL
  plus lambda=1 penalized residual/intercept, market logit offset. No search.
- Next lock must include inclusive 600-second age gate. -02 omitted a finite
  maximum despite supplied observed max 313. Any breach aborts, never filters.
- KEEP requires both proper losses below both controls and Brier wins in at
  least 3/4 folds against each. Otherwise REVERT; technical failures invalid.
- Return fold/aggregate paired evidence and calibration before proposing a
  later step. Repeated Train scores remain Discovery; Dev/Final stay closed.
