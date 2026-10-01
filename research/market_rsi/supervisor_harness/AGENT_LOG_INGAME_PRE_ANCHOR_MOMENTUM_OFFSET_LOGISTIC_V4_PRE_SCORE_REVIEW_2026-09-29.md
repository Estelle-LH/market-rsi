# InGamePreAnchorMomentumOffsetLogistic-v4 — independent pre-score review

Date: 2026-09-29  
Reviewer: independent of the implementation author  
Verdict: **REPLAN — do not execute or claim an attempt**

## Frozen materials reviewed

- Controller log SHA-256: `a6259940439dff5e6c86a0d1c4de73e634608bb7b3d82804731ac103674e4efb`
- Runner SHA-256: `fa5860b465f73e57416390cc376bfde8dda9b3ecad5269d67e8c212b85dde9a6`
- Focused tests SHA-256: `8f0d8079ae15e57b97336ed82d171cdbae0597ab47209d20a53776cf245c8de6`
- Implementation log SHA-256: `6eab7a569e2d24849412124ff475f5c9dd94e538ed977529ec33b7fbef71a5a2`

All four hashes match the supplied frozen values. The runner also validates its
Controller, parent runner/review/artifact, v0 runner/artifact, chronology helper,
settlement dependency, component-spec, scheduler branch, and one-thread launch
contract before a production run.

## Contract review

The implementation matches the frozen design in code:

- Reconstructs `reference_cutoff=floor(decision_epoch_seconds)-120` and uses the
  latest home-oriented size-weighted fill second strictly before that cutoff,
  subject to the exact `(0,300]` second reference-age gate.
- Demands signal coverage for the complete 193-row materialized population before
  selecting any outer fit/check rows. No row drop or imputation path exists.
- Uses the frozen v0 folds and the reviewed strict-prior label helper. If execution
  reached fitting, the required fit/check counts would be
  `106/132/148/176` and `26/16/28/17`.
- Standardizes momentum with outer-fit mean/std only.
- Fits `logit(q)=logit(p_now)+alpha+beta*z_momentum` with current-market logit
  coefficient fixed at one, penalty `0.5*beta^2`, an unpenalized intercept,
  analytic-gradient L-BFGS-B, exactly four fits, and no retry.
- Reads raw market and frozen v0 ordinary `market_model_probability` on the exact
  check keys; the ordinary arm is not refit.
- The prospective 87-row output and scorecard include proper scores, calibration
  slope/intercept and reliability bins, four folds, paired per-date summaries,
  complete schedule-date and observed-week 10,000-draw intervals, and the exact
  Controller support/refute/inconclusive plus KEEP/REVERT rule.
- Dev/Final, network, provider, cost, publication and promotion remain closed;
  the single-process/thread contract is fail-closed.

These code-level properties are internally consistent, but they do not make the
frozen experiment executable on the actual opened Train population.

## Blocking real-data preflight finding

A read-only, no-fit, no-score preflight validated the frozen source and v0
artifact, materialized the exact 193 rows, then attempted the exact parent signal
on every row. It failed before any fit or score because three required rows have
no reference fill inside the frozen `(0,300]` age gate:

| game | date | reference cutoff | latest strictly prior fill | age | outer role |
|---|---|---:|---:|---:|---|
| `2025_01_NYG_WAS` | `2025-09-07` | `1757271984` | `1757271650` | 334s | fit in folds 1–4 |
| `2025_02_BUF_NYJ` | `2025-09-14` | `1757876211` | `1757875792` | 419s | fit in folds 1–4 |
| `2025_03_NYJ_TB` | `2025-09-21` | `1758481140` | `1758480528` | 612s | fit in folds 1–4 |

The first failure is raised by
`market_momentum_signal` as `reference fill is outside frozen (0,300] second age gate`.
All three games are required fit rows in all four outer folds. Therefore the
current runner cannot satisfy both mandatory complete fit/check signal coverage
and the frozen 300-second reference-age rule. Dropping the games would change
the exact fit populations; imputing, changing the lag, or widening staleness
would change the frozen component spec. None is authorized post-freeze.

This is a pre-score feasibility failure, not model evidence. It is not a
scientific refutation, does not earn research credit, does not update the
incumbent, and must not consume the single execution attempt.

## Verification performed

The focused suite plus parent momentum-audit, offset score-time, and nested
chronology suites passed:

```text
Ran 44 tests in 8.621s
OK
```

`py_compile` also passed using a `/private/tmp` bytecode cache. No real runner,
fit, score, output artifact, network/provider call, or scheduler mutation was
performed during review.

The existing tests prove the intended arithmetic and fail-closed paths but do
not perform the complete 193-row real-data momentum-coverage preflight. The
parent audit's actual-data check covered the 87 check rows, whereas this candidate
newly requires the signal on earlier outer-fit rows as well; that difference is
where the three failures occur.

## Required next action

Return this feasibility evidence to the Controller and re-freeze a scientifically
defensible attempt. The Controller must explicitly choose and predeclare how to
handle missing strictly-prior reference support (for example a different signal
definition or a newly frozen population/evaluation contract). The reviewer does
not select that scientific policy. Any revised runner/spec requires a new
pre-score review before execution.
