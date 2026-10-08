# Controller: compressed conditional price-path experiment

2026-09-29 17:51 UTC. Configured identity: **gpt-6-astra / high**, supplied
by this task's Supervisor dispatch metadata. The runtime-visible self-label is
Codex/GPT-6; the exact slug is dispatch provenance, not an independently queried
backend identity. Status: **one next recipe selected before implementation or
its scores**. Only this log was written; no real Train fit or new data read,
network, provider, protected Dev/Final access, publication or promotion.

Read the opened-Train override in `AGENTS.md`, `RESEARCH_STATE.md`, applicable
supervisor guidance, both prior Controller proposals, the three scorecards,
their runner definitions for materialization/features, fitting, folds and
scoring, and the indicator-prediction-evals skill, evaluation gates and
sign-and-collinearity notes. The user's open Discovery instruction supersedes
the skill's universal single-stage and untouched-Final rules for this task.
The state page still says calibration pending; the completed artifact below
supersedes that stale line for this decision.

## Observed evidence

Calibration artifact:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-only-ridge-calibration-20260929-01`.

| Evidence | SHA-256 |
| --- | --- |
| Original settlement scorecard | `98f78e0bc68f7743881d285560b5fbc1a9a6b74b5178601ff6fc4201128fb710` |
| Full-offset scorecard | `276423d4cfe97ca1198f6f95a420036bf53b7f756bdd021d691951bc4b367907` |
| Calibration scorecard | `513856565af0cd9d4142b875d9fb38b3141bb59da58f330d4a6fa1c9144e7f2b` |
| Calibration predictions | `b9d28742157dd79cead5d2f22071daaa40526ad78b55b6a9c007f43c9e5f2358` |
| Calibration manifest | `a6e2e63b97fabab640c83f264e2c3afdbee1390f90dd2f1c39ffeb31131f37bb` |
| Calibration pre-score lock | `190a846bf29edb1418ba7a2677d8cc87aa1b488cfe3284943d75a21481537ac7` |
| Original runner | `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b` |
| Full-offset runner | `6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f` |
| Calibration runner | `71d329468c865246616b8cb1ee7b284a488c9ad382f2bda830bb529e383cc191` |

On the identical 87 reused Train checks:

| Forecast | Equal-event Brier | Log loss |
| --- | ---: | ---: |
| Market, current best | 0.20553336372767944 | 0.5984509292283796 |
| Market-only ridge calibration | 0.20585185704759978 | 0.5993850088689292 |
| Full 17-feature offset | 0.20945065421878312 | 0.6082677941274733 |
| Ordinary logistic reference | 0.23560472453952527 | 0.6759482937171853 |
| Archived HGB | 0.2697684947156754 | 0.7792234633163909 |

Calibration loses `+0.0003184933 / +0.0009340796` to market and wins Brier
on only two folds. Its diagnostic REVERT is correct. Affine-logit slopes by
fold are 1.006686, 1.003503, 1.004798 and 1.015300: the fitted changes are
small. Full offset loses `+0.0035987972 / +0.0088827853` to calibration.
Complete-day descriptive intervals for that added-column loss are
`[0.0006295251, 0.0066953670]` Brier and
`[0.00133491, 0.01662279]` log loss; calibration minus market intervals
include zero. This particular residual representation adds damage beyond
the modest calibration cost. It does not show that all calibrators fail,
all path information is useless or the Controller is weak.

There are 195 source events / 42 dates, 194 binary rows, and one explicit
unresolved-outcome exclusion. The 87 checks cover 20 schedule dates and seven
observed weeks; week 14 has one game and is partial. These adaptive Train
comparisons are Discovery. The intervals have no selection-adjusted or formal
OOS interpretation, and 20 dates do not establish adequate precision.

## Exactly one next experiment: MarketOrthogonalPricePath-v1

Question: does a small, market-conditioned representation of **signed price
history** carry useful residual information that the global 16-column
addition obscured? This combines representation/compression and a smaller
residual model. Compression and ridge interact, so any gain belongs to the
combined recipe. No per-family causal attribution will be claimed.

Use only the existing causal feature rows. For each event, let `p` be the
decision-time market probability and `m=logit(p)`. Define in probability units:

```text
g = p - mean(VWAP_15m, VWAP_60m, VWAP_240m)
d = mean(last_minus_first_15m, last_minus_first_60m,
         last_minus_first_240m)
```

Select columns by their exact frozen feature names. VWAP means existing
`weighted_mean_home_probability`; moves mean existing
`last_minus_first_home_probability`. Equal weights are fixed, not learned.
These are two distinct summaries: location of the latest price relative to
recent trading, and direction of the price path. Activity/count, size,
volatility and staleness do not enter the candidate's predictor; staleness
still applies to the common data-quality gate. They remain preserved for
later branches. No team identities, dates or outcomes become model features.

Within each fold, transform using **fit rows only**:

1. Fit the unchanged market-logit StandardScaler; obtain `z_m`. Require its
   mean/scale to match the calibration control within `1e-12`.
2. Form `A_fit=[ones, z_m_fit]`. Compute `beta =
   numpy.linalg.lstsq(A_fit, [g_fit,d_fit], rcond=1e-12)[0]`. Retain rank and
   singular values. Apply this same beta to fit and check rows: `R=[g,d]-A@beta`.
   This is ordinary linear residualization of predictors, using no labels.
   Require rank 2 on the real cohort; rank failure is INVALID, not a fallback.
3. For each residual column, save fit mean and population standard deviation.
   If standard deviation is at most `1e-8` probability units, declare that
   family inactive and set that column to zero for **both fit and check**;
   otherwise standardize with those fit moments. Record every inactive
   family explicitly; this drops no events. Nonfinite inputs are INVALID.
4. Candidate design is `[z_m, z_g, z_d]`, in that order. The two market
   residualization coefficients per family and all scaling parameters are
   saved. The arithmetic removes linear fit covariance with market logit;
   it is not proof of nonlinear conditional independence or new information.

Fit exactly four penalized parameters with the existing offset implementation:

```text
eta = m + b + w_m*z_m + w_g*z_g + w_d*z_d
p_candidate = sigmoid(eta)
J = mean(logaddexp(0, eta) - y*eta)
    + 0.5*(b*b + w_m*w_m + w_g*w_g + w_d*w_d)
```

Lambda=1, penalize every parameter, all-zero initialization, float64,
L-BFGS-B analytic gradient, maxiter=1000, gtol=1e-8, ftol=1e-12; require
success, finite outputs and gradient infinity norm <=1e-6. Reuse the existing
probability rejection contract `[1e-6,1-1e-6]`; no clipping/fallback/sweep.
With both new coefficients zero, this is the calibration submodel; with all
coefficients zero it is market. Allow both signs: present evidence does not
justify enforcing momentum or reversal.

Why this experiment: full-offset failure motivates reducing redundant market
level coordinates and unsigned nuisance directions before adding model
flexibility. Averaging the three existing horizons gives two interpretable
path families without outcome-selected horizon choice or PCA tuning.
Uncompressed family sweeps would spend more fit budget and invite more
adaptive selection before we know whether these elementary conditional
signals persist. Nonlinear interactions remain legitimate later options.
Neither averaging nor residualization is guaranteed to improve prediction.

## Measure the information before interpreting the fit

Compute the following fixed diagnostics after the recipe is locked, before
candidate fitting for fit-row diagnostics and after prediction for checks.
They must not gate, select, flip, drop or tune a family during this experiment.

For each fold and each family report raw variance, variance after linear
market residualization, residual/raw variance fraction (null if raw variance
zero), raw correlation with market logit, residual correlation with market
logit, and correlation between the two residual families. Report fit and check
Pearson and Spearman correlations of standardized family value with
`y-p_market`, using average ranks for ties; undefined correlations are null
with a reason. These are residual association diagnostics, not full nonlinear
conditional-information tests. Include `mean(z_family*(y-p_market))` per fold
and per schedule date, so one-game dates retain an interpretable signed
moment even when correlation is undefined. Report counts with every statistic.
Also report candidate coefficients and probability corrections by fold.

All pooled check diagnostics use each game's transformation from its own
prior-fit fold. Never refit a common transform on all checks. In-sample fit
associations and check associations are clearly separate. Stable association
with disappointing proper-score gain supports further trainer research;
unstable association supports questioning this representation. Neither result
certifies that the underlying feature family lacks information.

## Execution, comparisons and decision

Reuse the current local runner, materializer, fold plan, scorer and grouped
resampling. Add a thin sibling runner and direct tests; do not mutate any
frozen source or artifact. Preserve the exact 195-event denominator, 194 binary
rows and existing `2025_04_GB_DAL` exclusion. Keep home orientation, kickoff
minus 15 minutes, inclusive 600-second common gate and exact source hashes.
Any required binary row violating integrity invalidates the whole run.

Use exactly 22 initial fit dates and four expanding five-date checks;
fit/check counts are 107/26, 133/16, 149/28, 177/17, with no unavailable fit
labels. Require outcome availability before the first check cutoff. Preserve
materialized key hash
`59128473ae6c50b4acd2436ac18478d4fcd7dbd96ee887eb5ce2ae77ddfc72bd`
and 87-key mask
`eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.

Resource bound: **one fixed recipe; four candidate fits, four calibration
control fits and four ordinary control fits; no hyperparameter search; zero
provider cost or new acquisition**. Reuse calibration's `_fit_fold_models`
for the two controls. Verify recomputed ordinary and calibration predictions
against their frozen artifacts to absolute tolerance `1e-10`, identical keys,
outcomes and market values. Bind archived full-offset predictions for context;
no HGB/full-offset refit. Stop on integrity or optimizer failure, preserve the
failed run ID and repair under a fresh ID only after reviewing the cause.

Return a comparable scorecard for market, ordinary reference, market-only
calibration, archived full offset and candidate. Report equal-event Brier/log
loss, calibration, folds, complete population accounting and paired candidate
minus market, calibration, ordinary and archived full offset. Reuse seed 23,
1000 bootstrap replicates and 2.5/97.5 percentile intervals, resampling whole
schedule-day units and recomputing the pooled event mean in each draw.
Retain per-day paired sums/counts/means. The observed-week sensitivity remains
explicitly seven observed clusters with partial week 14, not seven complete
weeks. No denominator reduction to improve intervals.

For current-best replacement, KEEP iff candidate beats both market and
ordinary on aggregate Brier and log loss by more than `1e-12`, and wins Brier
against each separately on at least 3/4 folds. Otherwise REVERT current-best
replacement. Market stays incumbent until a valid KEEP. Separately report
whether candidate beats calibration on both aggregate scores and its fold
wins: that comparison diagnoses this compressed added-information recipe,
not the current-best rule. No significance gate is added. Preserve candidate
code and evidence even on REVERT; useful branch development remains allowed.

Required synthetic tests (planned, not yet run): exact named-column formulas;
future/check-row changes cannot affect transforms or fit parameters; no label
input to compression/residualization; fit residual orthogonality; rank failure;
inactive-family threshold behavior and check zeroing; all-zero market recovery;
zero family coefficients reproduce calibration; analytic-gradient finite
differences; loss-mean and all-parameter penalty; deterministic fits; changes
to unused columns leave candidate unchanged; same-mask/strict-label-time
checks; 600/601-second integrity; archive/control parity; unequal-day-size
bootstrap; and exact KEEP criteria. Reuse parent tests where already covered.

## Evidence categories and reusable Controller memory

**Literature principles reused:** temporal fits and preprocessing must use
earlier information, and paired forecast comparisons must preserve their
metric and row population. Local search on 2026-09-29:
`rolling|FPP|leakage|bootstrap|calibrat|Gneiting` in
`LITERATURE_TO_HARNESS_2026-09-10.md`; read section 4 and the preprocessing
notes. They record FPP3 temporal CV (`https://otexts.com/fpp3/tscv.html`)
and sklearn preprocessing/leakage guidance
(`https://scikit-learn.org/1.6/common_pitfalls.html`). These are reused local
records, not newly downloaded or reread primary pages. The skill's family
compression/residual diagnosis informs this experiment, but is not itself
empirical literature proof that compression helps NFL markets. No new
literature retrieval occurred within the no-network boundary.

**Project choices:** two arithmetic family averages, linear market
residualization, its numerical rank tolerance, inactive-family threshold,
lambda=1, NFL seed cohort, cutoff, staleness, folds, seeds, optimizer and KEEP
rule. Ordinary linear algebra defines the transform; no paper is claimed to
endorse these exact parameters. The cluster arithmetic preserves our chosen
equal-game estimand; coverage guarantees for this adaptive small sample are
not established.

**Hypothesis to test:** compressed signed path features may carry conditional
predictive association beyond the market and improve a market-anchored fit.
The current results have not tested this representation. Even a KEEP will
support only continued Discovery, not promotion or untouched OOS.

Reusable memory: preserve a strong market anchor; quantify calibration before
claiming added information; do not infer feature uselessness from an
overparameterized residual model's failure; use prior-only family diagnostics
to distinguish redundancy, association instability and trainer failure;
document inactive features without dropping games; separate current best
from research branches. No score improvement is required to retain useful
research memory.

These rounds do not test RSI self-evolution, transferable skill or profitability.
Those claims still require matched Astra versions/data/resources and multiple
independent fixed-process versus memory/process-improving runs, followed by
transfer tests and independent future events that occur and settle after
candidate/model freeze. Historical NFL outcome memorization remains unresolved.
This future evaluation plan does not block the authorized local Train recipe.
