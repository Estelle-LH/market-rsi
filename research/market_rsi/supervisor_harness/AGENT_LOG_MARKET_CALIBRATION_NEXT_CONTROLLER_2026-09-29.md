# Controller: market-only calibration after the offset diagnostic

2026-09-29 17:33 UTC. Configured Controller: **gpt-6-astra, high reasoning
effort**, confirmed by Supervisor dispatch metadata (`fork_turns=4`). The
runtime-visible self-label is Codex/GPT-6; the exact slug is dispatch provenance,
not an independently queried backend identity. Status: **recipe chosen before
calibration fit or score; implementation and real execution pending**.

Only this log is written by this Controller task. No Train fit, protected
Dev/Final access, network, paid provider, release or promotion occurred.

## Evidence and interpretation

Read the opened-Train override in `AGENTS.md`, `RESEARCH_STATE.md`,
`HUMAN_INTERVENTIONS.md`, applicable supervisor guidance, the prior Controller
proposal, the complete current offset runner and tests, both completed Train
scorecards, local literature notes, and the indicator-prediction-evals skill
and evaluation gates. The human override supersedes universal single-component
restrictions and untouched-Final requirements for this private Discovery.

Parent directory:
`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-market-offset-ridge-20260929-02`.

| Evidence | SHA-256 |
| --- | --- |
| offset runner | `6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f` |
| offset tests | `409fd88d93c59b5d0bb25a1765471ad9249c0a5872cc77d31e69922a77fd0f41` |
| parent scorecard | `276423d4cfe97ca1198f6f95a420036bf53b7f756bdd021d691951bc4b367907` |
| parent predictions | `d917a1980bc0b4621ee9ab0cdc6672b47e58cbea0ae4ed335c952d40dd51288c` |
| parent manifest | `2296835ec561858383750cba8d81124daf479de1caa288908d98503a7b93acc6` |
| parent pre-score lock | `264341f66c382001c86a01ab45835b03780b06e926d79176b141d6c86d3492a1` |

On the same 87 checks, market Brier/log loss are
`0.20553336372767944 / 0.5984509292283796`; ordinary reference
`0.23560472453952527 / 0.6759482937171853`; full offset candidate
`0.20945065421878312 / 0.6082677941274733`. Offset minus market is
`+0.003917290491103701 / +0.009816864899093742`; offset minus ordinary is
`-0.02615407032074219 / -0.06768049958971191`. Offset loses Brier to market
on all four folds and beats ordinary on three. REVERT correctly retains
market as current best, with the offset and HGB research branches preserved.

The corrected complete-schedule-day percentile interval for offset-minus-market
is `[0.0008447572935078003, 0.007129935098859866]` for Brier and
`[0.0015841786527093012, 0.018286087395410912]` for log loss. These describe
repeatedly inspected Train checks. There are only 20 schedule dates and seven
observed game-week clusters; week 14 contains one event. These are not
independent final significance results or proof that feature families lack
information. The full offset repaired much replacement-model damage but
did not add a measured benefit over market. Its market-logit residual and
other features remain mixed; calibration control is the smallest direct
attribution step.

## Exactly the next concrete experiment

Name: **MarketOnlyRidgeCalibration-v1**. Question: can a past-fitted,
identity-shrunk affine calibration of market log-odds improve the unchanged
market forecast, and how much does the existing full offset gain or lose
relative to that restricted calibration model?

For each existing fold, let `m = log(p_market / (1 - p_market))`. Fit a
one-column `StandardScaler` on **only that fold's earlier fit rows**. Use its
population variance convention (`ddof=0`; sklearn zero-variance scale=1).
Set `z = (m - mu_fit) / scale_fit`. Only market probability enters the
calibrator at prediction time. Fit exactly two parameters `b,w`:

```text
eta_i = m_i + b + w*z_i
p_cal_i = sigmoid(eta_i)
J(b,w) = mean_i[logaddexp(0,eta_i) - y_i*eta_i]
         + 0.5*(b*b + w*w)
```

The unstandardized market offset has coefficient 1; lambda is exactly 1.0,
and both parameters are penalized. At zero residual, output equals market
up to floating-point sigmoid/logit round-trip precision. This is precisely
the two-parameter restricted submodel of `MarketOffsetRidgeLogistic-v1`,
with its other 16 residual coefficients fixed at zero. The one-column
scaler's market-logit mean/scale must agree with column 0 of the unchanged
fit-only 17-column scaler within absolute tolerance `1e-12`. No labels from
the check block enter scaling or fitting. No check outcomes are used to
pick coefficients, calibration bins, penalty or model shape.

Use the existing offset objective/analytic gradient and optimizer functions
with the single standardized column. Float64, initialization `[0,0]`,
L-BFGS-B, `maxiter=1000`, `gtol=1e-8`, `ftol=1e-12`; require optimizer success,
finite objective/parameters/probabilities, and final gradient infinity norm
at most `1e-6`. No coefficient constraints, clipping, fallback, hyperparameter
search, alternate penalties or blending. Retain rejection outside
`[1e-6, 1-1e-6]`. Report `b,w,mu,scale` and equivalent affine-logit
intercept `b-w*mu/scale` and slope `1+w/scale` for each fold.

Why this choice: a flexible isotonic calibrator has much more freedom at
107 initial fit events, and an unregularized two-parameter fit changes the
shrinkage convention as well as input information. The restricted offset
keeps the existing shrinkage and solver intact, making its comparison to
the full offset directly interpretable as the contribution of adding the
16 additional columns under this particular fitted recipe. This choice is
a project diagnostic, not a claim that lambda=1 or affine calibration is
universally optimal.

## Execution and comparison contract

Reuse the existing local materializer, chronological folds, probability
contract, proper scorer, grouped-resampling functions and artifact writer.
Do not change either frozen parent runner or artifacts. A small sibling
runner plus direct synthetic tests is enough; no new harness is needed.

Preserve all 195 source events / 42 source dates; materialize exactly 194
binary events, retaining the sole explicit unresolved-outcome exclusion
`2025_04_GB_DAL`, ordinal 53, `2025-09-28`. Home-win orientation, token
mapping, same-second size-weighted last trade, cutoff at kickoff minus
15 minutes and inclusive 600-second staleness gate remain unchanged.
Any required binary row failing that gate invalidates the whole comparison;
never filter to a better subset. Bind unchanged source/cohort hashes.

Copy the exact four fold definitions from the offset lock: first 22 schedule
dates fit, then four five-date checks with expanding fit history. Strictly
require outcome availability before the first check cutoff. Fit/check
counts remain `107/26`, `133/16`, `149/28`, `177/17`, with zero unavailable
fit labels. Validate these structural facts before fitting when practicable.
The materialized-key hash is
`59128473ae6c50b4acd2436ac18478d4fcd7dbd96ee887eb5ce2ae77ddfc72bd`;
the canonical common 87-key mask hash is
`eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb`.

Run four calibration fits and, for control reproducibility, four unchanged
ordinary LogisticRegression fits. Keep its exact 17 features, fit-only
scaler, `C=1`, `lbfgs`, `max_iter=500`, seed 23. Require identical event keys,
outcomes and market probabilities to the original parent; ordinary
probabilities must match within `1e-10`. Compare the **archived full-offset
predictions** against the calibration predictions after verifying the parent
hash and exact row identity. Do not refit the archived offset or HGB.

Return aggregate/fold Brier and log loss, calibration diagnostics, complete
population accounting and all pairwise loss deltas relevant to:

- market-only calibration minus market: fitted calibration benefit/cost;
- archived full offset minus market-only calibration: added-column benefit/cost
  for this nested, equally penalized model family;
- market-only calibration minus ordinary reference;
- archived full offset minus market and ordinary, reproduced for continuity.

The scorecard must keep raw market, ordinary reference, archived full offset
and new calibration rows explicitly named. A gain from calibration alone
contains no new prediction-time information beyond market probability.
Even a full-offset gain over this calibration control would establish only
a benefit for this finite recipe on reused Train, not causal information
content of each feature or the absence of other calibration explanations.

## Inference, decision and resource bound

Primary scores remain equal-event on all 87 check games, across 20 schedule
dates. Report observed game-week counts `08:13,09:14,10:14,11:15,12:14,13:16,14:1`.
For paired deltas, resample 20 complete source schedule-date units with
replacement and pool every event in sampled units, including duplicates,
before recomputing the event mean. Use seed 23, 1000 replicates and 2.5/97.5
percentile limits. Preserve all per-date paired sums, counts and means.
Do not average date means as the primary estimand. The existing seven-cluster
observed-week sensitivity may also be returned with the right-edge partial
week disclosed; do not call it seven complete weeks. No primary row is
removed to obtain prettier week coverage. Day clustering does not remove
dependence across adjacent dates, and seven observed weeks are limited
precision evidence. All these intervals remain descriptive Discovery.

Use the existing diagnostic KEEP rule for this run: new calibration must
beat both market and ordinary on aggregate Brier and log loss by more than
`1e-12`, and beat each separately on Brier in at least three of four folds.
Then it replaces current best for Discovery; otherwise REVERT retains
market. Full-offset-versus-calibration is an attribution comparison, not an
additional condition for replacement. No interval-based significance gate
is added. Either outcome preserves all branches and can justify further
research. Integrity/optimizer failures are INVALID/FAILED, not REVERT.

Bound: one fixed recipe, eight inexpensive local fits, zero provider cost,
no new data acquisition. Stop an execution on integrity or optimizer failure;
preserve the failed ID, diagnose, and use a new ID for any authorized repair.
Do not expand into a search sweep within this experiment.

Required direct synthetic checks before execution: zero-residual market
recovery; finite-difference gradient; loss-mean/intercept-penalty semantics;
one-column scaling uses fit rows only and matches column 0; arbitrary
changes to the 16 unused check-feature columns leave calibration unchanged;
strict availability and same-mask checks; 600/601-second gate; archived
prediction identity/hash/parity; unequal-date-size resampling; deterministic
fits; exact KEEP interpretation. Reuse parent tests instead of duplicating
infrastructure. All are planned here, not reported as run.

## Evidence categories and Controller memory

**Literature-supported principles, reused locally:** strictly earlier fitting
for temporal evaluation and fit-only preprocessing are recorded in
`LITERATURE_TO_HARNESS_2026-09-10.md` section 4 and preprocessing notes,
with FPP3 temporal cross-validation (`https://otexts.com/fpp3/tscv.html`) and
sklearn leakage guidance (`https://scikit-learn.org/1.6/common_pitfalls.html`).
Local query on 2026-09-29: `calibrat|proper|Gneiting|rolling|FPP|leakage|bootstrap`.
I read existing notes, not those primary pages anew. Dependence-aware grouping
is the existing evaluation principle; the pooled-event arithmetic directly
follows this project's estimand. This task did not retrieve new literature
or establish that a particular cluster interval has guaranteed coverage here.

**Project choices:** NFL seed cohort, 195 denominator, 15-minute cutoff,
600 seconds, 22+4x5 dates, affine-logit calibration, lambda=1, solver tolerances,
seeds/replicate count and KEEP thresholds. None is presented as paper consensus.

**Hypotheses awaiting the next score:** a small past-fitted calibration may
help market; additional columns may damage or improve that calibrated
prediction. The aggregate check-set OLS slope near one is descriptive and is
never used as a fitted calibration coefficient. Negative results do not prove
the Controller is weak, all features useless or all calibrators unhelpful.

After this experiment, return the actual paired results and coefficients to
Controller. The next research decision should use the calibration comparison
to prioritize conditional feature-family residual diagnostics or combined
representation/training changes. That subsequent recipe is not selected
before this evidence. Open Discovery permits combinations and further work
on unsuccessful branches; it does not demand a score gain each iteration.

Preserve the larger untested hypothesis: under matched Astra version, data
permissions and resource budget, accumulated research memory/process changes
should improve discovery compared with the same Astra following a fixed
process, over repeated independent runs and later transfer periods/domains.
No result here tests that hypothesis. Formal final evaluation still needs
independent future events occurring and settling after candidate/model freeze
to address historical-result memorization. This planning does not block the
authorized Train experiment.
