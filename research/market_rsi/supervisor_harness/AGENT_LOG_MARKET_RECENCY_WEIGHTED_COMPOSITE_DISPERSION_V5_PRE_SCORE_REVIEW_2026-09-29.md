# MarketRecencyWeightedCompositeDispersion-v5 pre-score independent review

Date: 2026-09-29  
Verdict: **PASS**  
P0: none  
P1: none

This is a methodology and frozen-source review only. I did not run the real
opened-Train entry, create a real result artifact, read Dev/Final, contact a
network or provider, or authorize promotion. PASS means only that the
Supervisor may consider the separately controlled fresh-ID Train Discovery
run.

## Frozen review inputs

- Controller recipe
  `research/market_rsi/supervisor_harness/AGENT_LOG_DISCOVERY_ATTEMPT5_CONTROLLER_2026-09-29.md`
  = `29bd05297afca88a6949aa1e75241cf88da458be7018862317deb74618758436`.
- Runner
  `research/market_rsi/experiments/nfl_market_recency_weighted_composite_dispersion_train_diagnostic.py`
  = `7e384cb18a2b11595c0e6ab77446be59f538033c7fed842a3af572571e18a658`.
- Focused test
  `research/market_rsi/tests/test_nfl_market_recency_weighted_composite_dispersion_train_diagnostic.py`
  = `b6202edb2f68996424287352e0d090643f9c900e38d1f6b870b5323aec6f4547`.
- Implementation log
  `research/market_rsi/supervisor_harness/AGENT_LOG_MARKET_RECENCY_WEIGHTED_COMPOSITE_DISPERSION_V5_IMPLEMENTATION_2026-09-29.md`
  = `3a69cfdbeeac76cb876bc966bc5f7525df17f5a9dc087944c667ea5f977310f6`.
- Passing Attempt-4 result review
  `research/market_rsi/supervisor_harness/AGENT_LOG_MARKET_ALL_PRIOR_DECAY_COMPOSITE_PATH_V4_RESULT_INDEPENDENT_REVIEW_2026-09-29.md`
  = `c5b706e474af4ef1fac34eab1c19567f03c300f0c77f03bafcd129d09913f882`.

I independently rehashed all five inputs and reviewed the full new runner and
test source at the hashes above.

## Methodology and implementation findings

### Causal transform and candidate objective

The candidate retains Attempt 3's exact most-recent-three-complete-week rows,
per-event weights `0.25/0.50/1.00`, and fit-only market/price-path composite.
Its sole scientific delta is the predeclared dispersion family: the exact mean
of the 15m, 60m, and 240m trailing weighted probability standard deviations.

For every fold, selected-fit rows alone determine the residualization
`v_raw ~ [1, z_market, z_composite]` with `numpy.linalg.lstsq(rcond=1e-12)`.
Rank must equal three. The same fitted coefficients are applied to older and
check rows. The residual mean and population standard deviation are also
selected-fit only. A selected residual scale at or below `1e-8` makes the
dispersion feature identically zero on selected, older, and check rows; rank,
shape, endpoint, and nonfinite failures are fail closed before candidate fit.
No check outcome enters transformation fitting.

Each of the four folds fits exactly two unconstrained coefficients:

`eta = market_logit + w_c*z_composite + w_v*z_dispersion`.

The objective is weighted mean Bernoulli NLL divided by the sum of event
weights plus `0.5*(w_c**2 + w_v**2)`, with its exact analytic gradient,
float64 zero initialization, and frozen L-BFGS-B convergence checks. Zero-zero
coefficients preserve the market probabilities bit for bit. Tests cover the
formula, finite-difference gradient, common-weight-scale invariance,
determinism, market-logit parity, rank failure, the inactive path, and
nonfinite dispersion rejection.

### Lineage, controls, scorer, and decision

- The original 195-event denominator, exact 194+1 tie lineage, 87-event check
  mask, outcome orientation, chronological 22-date fit plus four 5-date
  checks, inclusive 600-second staleness gate, and runtime/source bindings are
  inherited and fail closed through the reviewed parent chain.
- Exactly four candidate fits are permitted. Market, ordinary, market-only
  calibration, full offset, and Attempts 1-4 are immutable archived controls;
  there are zero control refits and nine scored arms. The Attempt-4 archive is
  bound by hashes plus key, ordering, outcome, market-probability, and stored
  control-prediction parity.
- Every pair uses the frozen proper scorer on one complete-mask hash. Brier and
  log loss are equal-event estimands. Schedule-day and observed-NFL-week
  grouped inference resample complete groups and recompute the pooled
  equal-event metrics rather than averaging group metrics.
- KEEP retains the existing market and ordinary gates and additionally
  requires strict (`>1e-12`) aggregate Brier and log-loss wins over archived
  Attempt 3 plus Brier wins in at least three of four paired folds. Otherwise
  the current best remains Attempt 3. Attempt 4 and every failed candidate
  remain research branches. Focused tests exercise KEEP, aggregate REVERT,
  and fold-gate REVERT.

The scorecard reports event/date/week breadth, fold results, pairwise deltas,
grouped inference, and fixed diagnostics. Diagnostics do not tune or gate this
frozen attempt.

### Provenance and boundaries

The recipe truthfully records that Attempt 5 was adaptively selected after
reading earlier opened-Train results, including Attempt-4 diagnostics. It is
therefore reusable Train Discovery, not untouched OOS evidence. The source and
receipts explicitly preserve `route_dev_opened=false`,
`sealed_final_opened=false`, zero provider cost, no external fetch, and no
promotion authority. Static inspection found no network/provider/fetch route
in the new runner.

Project choices (the 600-second gate, folds, three-week weights, dispersion
family, `1e-8` inactivity threshold, ridge penalty, optimizer, and KEEP rule)
are presented as frozen project parameters. General principles such as
fit/check separation, paired proper scoring, and clustered uncertainty are
kept distinct from the still-unverified hypothesis that orthogonalized
dispersion contains incremental settlement information.

## Independent verification

Pinned runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`.

- Focused frozen suite: **5/5 passed**.
- Full transitive settlement/offset/calibration/Attempts 1-5 suite:
  **80/80 passed** in 17.989 seconds.
- `py_compile` for the frozen runner and test: passed using a temporary
  bytecode cache.
- `git diff --check` for the frozen files: passed.
- Static boundary scan: no network client or provider route; only explicit
  zero-cost/no-fetch/no-promotion receipt fields.

All executions above used synthetic fixtures only. The end-to-end suite traps
socket creation, traps every archived-control fit path, confirms exactly four
candidate optimizer calls, and checks nine-arm common-mask archive parity.
The joblib physical-core detection warning during the transitive suite fell
back to logical cores and did not affect results.

## Decision

**PASS, P0 none, P1 none.** The frozen snapshot implements the exact Attempt-5
recipe and preserves the causal, scoring, archive-control, incumbent/branch,
and protected-evaluation boundaries. This review does not authorize or imply
promotion, Dev/Final access, provider use, retry, profitability, formal OOS
improvement, or generalization beyond the opened 2025 NFL Train cohort.
