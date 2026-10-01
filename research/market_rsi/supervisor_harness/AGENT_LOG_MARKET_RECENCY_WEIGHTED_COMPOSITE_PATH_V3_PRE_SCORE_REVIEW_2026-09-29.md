# MarketRecencyWeightedCompositePath-v3 independent pre-score review

Date: 2026-09-29  
Verdict: **PASS — 0 P0, 0 P1.**  The exact snapshot below is eligible for one
real opened-Train Discovery execution.  This review did not read or execute the
real Train source and did not fit or score a real candidate.

## Exact reviewed snapshot

- frozen Controller recipe:
  `1def15625da467de6b6130dc7f7bf3adb08ae7da00ee43de9900c1d5a73283cc`;
- runner
  `research/market_rsi/experiments/nfl_market_recency_weighted_composite_path_train_diagnostic.py`:
  `05af717084499618c99fefd034972681d4acef12b226b5fc8b8a4513c26fdbd1`;
- focused test
  `research/market_rsi/tests/test_nfl_market_recency_weighted_composite_path_train_diagnostic.py`:
  `9d2491170a1862a4239118ad8ff03d95e5c4ed5e682e131a5023ae4ac4b1363d`;
- implementation log:
  `1fc8a8ee293fac6971a5dc1f5d9b2a2193304cac5e8e3da81b408f6ad507545a`;
- passing Attempt-2 independent result review:
  `6800cd9647508963a2eb1efa525f5489c04fd9e3c920fa2a495fba0f417d9c6d`.

The runner also binds the exact Attempt-2 runner/test and all seven completed
Attempt-2 artifact hashes before fitting.  A changed source, dependency chain,
recipe, result review, archive file set, archive hash, or archive receipt fails
closed.

## Method and lineage findings

1. **Only the frozen trainer weighting changes.**  The runner delegates the
   195-event population, exact 194 materialized plus one exclusion identity,
   600-second staleness boundary, fixed orientation/cutoff, 22-date initial fit,
   four five-date expanding checks, 87-row common check mask, and exact
   Attempt-2 row selection and unweighted transform to the frozen parent chain.
   The real recent cohorts remain `44/43/41/43`, with the same three ordered,
   complete NFL weeks in each fold.
2. **Weight assignment is causal and row-order independent.**  Each selected
   event receives `0.25/0.50/1.00` from its oldest/middle/newest selected week
   label.  The exact real fold weight sums are enforced as
   `26.0/24.25/24.25/25.0`.  The implementation records an event ledger,
   week/class totals, squared-weight sum, Kish effective rows, and overall and
   per-week signed moments; these diagnostics cannot tune or gate predictions.
3. **The objective is exact.**  For `eta_i=m_i+w*z_i`, the implementation
   minimizes
   `sum_i a_i[logaddexp(0,eta_i)-y_i*eta_i]/sum_i a_i + 0.5*w^2` and supplies
   analytic gradient
   `sum_i a_i*z_i[sigmoid(eta_i)-y_i]/sum_i a_i + w`.  It retains one
   unconstrained parameter, zero initialization, lambda one, and the frozen
   L-BFGS-B convergence settings.  Tests cover finite-difference agreement,
   global weight-scale invariance, deterministic fitting, and bitwise nesting
   of the market prediction at `w=0`.
4. **The sign convention is now truthful.**  The Controller narrative reversed
   the words “gradient at zero” when interpreting its pre-fit moment arithmetic.
   The displayed objective and gradient were correct.  The implementation and
   tests explicitly enforce
   `gradient_at_zero = -weighted_mean[z*(y-p_market)]` and separately report
   gradient, moment, and coefficient descent direction.  Thus the narrative
   slip was not propagated into model code or the scoring contract.
5. **Fit accounting and controls are correct.**  Exactly four new candidate
   fits are permitted.  Market, ordinary LogisticRegression, market-only
   calibration, full offset, Attempt 1, and Attempt 2 are loaded only from the
   hash-bound archive, with zero control refits.  The scorecard has seven arms,
   exact archived identity/outcome/control parity, one common mask, and the
   unchanged equal-event Brier/log loss/calibration, paired fold deltas,
   schedule-day and observed/full NFL-week grouped inference, and KEEP rule.
6. **Semantics and boundaries are truthful.**  KEEP/REVERT changes only the
   current Discovery incumbent; every branch is retained.  The half-life was
   selected using label-dependent aggregate/fold/week/date diagnostics from
   Attempt 2, which is legitimate adaptive opened-Train Discovery but not an
   untouched or independently selected OOS result.  No alternative decay,
   window, sign, penalty, model, denominator, scorer, or KEEP rule was swept.
   The runner exposes no network/provider/fetch route and keeps Dev, Final,
   release, promotion, and formal OOS claims closed.

## Independent verification

- focused Attempt-3 suite: **6/6 passed**;
- settlement parent plus offset, calibration, Attempt 1, Attempt 2, and
  Attempt 3 suites: **69/69 passed**;
- exact-runner and exact-test `py_compile`: passed;
- `git diff --check` on the reviewed runner, test, and implementation log:
  passed;
- static import/boundary scan: no network client or provider path in the
  runner; the test suite explicitly traps socket use and every archived-control
  refit;
- no real Train execution, provider call, external fetch, Dev/Final read, or
  artifact scoring occurred in this review.

## Gate decision

There are no P0 or P1 pre-score findings.  Run only the exact hash-frozen
snapshot under a fresh, single-use artifact ID.  Any code, test, Controller,
parent, dependency, archive, or receipt change requires a new independent
pre-score review.  A real result remains opened-Train diagnostic evidence only
and requires independent result review before the next Controller decision.
