# InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4 — independent pre-score review

Date: 2026-09-29  
Verdict: **PASS for the single reviewed execution**  
Scope: implementation/pre-score review only; no candidate run or scheduler mutation

## Frozen identity

- Controller: `db9481637ab55dec104bdd9cde4a0199022ea404781e60bec9563c05aad94eb8`
- Runner: `b827eecdd669451d92a24a1023e2407a10ddebd26585f4515e395c0f486ff589`
- Focused tests: `5f0ae9f9e001b56e29bdd68f2fb48941ad37c4e58a0a7b9119e80d9638dcae5a`
- Implementation log: `3d93ea7b18724a2a4b73a9e80b61bead4a917a7477b211ee6c6c6712b27247d4`

All hashes match the supplied frozen values. Controller question, hypothesis,
rule and component-spec digests are bound in the runner, as are the scientific
selection digest `0d7e7fc6...`, recovery state hint `a702cf03...`, Controller
SHA and scheduler branch digest `3a980cf0...`.

## Feasibility and data boundary

The independent read-only no-fit/no-score preflight passed:

- `prior_play_success.csv` SHA-256 is exactly
  `cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764`.
- The file has 195 unique game rows. After the exact two frozen exclusions,
  all 193 materialized games have one finite validated signal; there are no
  missing or duplicate materialized keys.
- Every materialized row can compute `u=p_now*(1-p_now)`. The exact threshold
  yields 112 low-uncertainty and 81 high-uncertainty rows.
- Strict chronology produces fit counts `106/132/148/176`, check counts
  `26/16/28/17`, and no unavailable fit labels.
- The 87 check keys, labels, cutoffs, outcome-availability stamps and game
  identities match v0 exactly; check-key SHA-256 is
  `2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.

No candidate prediction or score was read during this preflight.

## Model and scoring contract

The implementation exactly computes:

```text
x_low  = s when p_now*(1-p_now) < 0.1875, otherwise 0
x_high = s when p_now*(1-p_now) >= 0.1875, otherwise 0
logit(q) = logit(p_now) + beta_low*x_low + beta_high*x_high
```

There is no intercept and the market-logit coefficient is fixed at one. The
objective is sum Bernoulli NLL plus
`0.5*16*(beta_low^2+beta_high^2)`. The solver is deterministic analytic damped
Newton with at most 50 iterations, gradient-infinity tolerance `1e-8`, exactly
one fit per outer fold, no grid and no retry.

All four arms use the exact same 87 rows: raw market, frozen v0 ordinary
market-only, frozen v0 market-plus-state parent, and candidate. The prospective
scorecard contains equal-event Brier/log loss, calibration slope/intercept and
reliability tables, all folds, and candidate-minus-each-control complete-date
and complete-week 10,000-draw intervals at seed `20260929`. The coded KEEP rule
requires both proper scores below all three controls, raw and ordinary Brier
wins in at least 3/4 folds, and both candidate-minus-raw grouped Brier upper
bounds below zero. Either raw aggregate proper-score failure or at most 1/4 raw
Brier wins is REFUTED; every other valid result is INCONCLUSIVE. Only SUPPORTED
maps to KEEP.

## Recovery batch and execution boundary

The recovery batch snapshot and its two-record journal chain were independently
hash-recomputed without mutation:

- batch: `market-rsi-ingame-predictive-autonomy-recovery-20260929-04`
- state: `44a71ad61b2de1d7e9b90cba3226b1f7cf9f6cac4bee5122c419d26355d1f8d3`
- journal head: `3fb81d26688c0304eb5f2f30ab2e42d4598127bfeb3334582daa53f33822496c`
- one branch only: `attempt-03`, candidate and Controller exact, stage
  `controller_selected`, `attempts_claimed=0`, with no claim, runner or
  scorecard receipt yet.

The recovery batch grants no execution authority itself. Its flags keep
Dev/Final, network, provider, payment, publication, promotion and scoring
closed and allow resident opened Train only. The runner independently requires
the exact single-process/thread environment and records zero network/provider/
cost with no retry. Normal Supervisor claim/receipt/review transitions remain
required around the one execution.

## Verification

```text
Ran 8 tests in 0.028s
OK
```

`py_compile` passed for runner and focused tests using a `/private/tmp` bytecode
cache. Tests cover the exact threshold, zeroing behavior, analytic objective/
gradient/Hessian, no-intercept ridge-16 arithmetic, deterministic Newton,
four fits and zero control refits, feature/control fail-closed behavior,
support/refute/inconclusive decisions, 10,000-draw date/week wiring and static
network boundaries.

No real experiment, fit, prediction, score, output artifact or scheduler/state
write was performed by this review.
