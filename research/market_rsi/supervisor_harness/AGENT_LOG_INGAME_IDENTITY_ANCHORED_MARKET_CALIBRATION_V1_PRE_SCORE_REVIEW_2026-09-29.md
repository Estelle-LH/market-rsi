# InGameIdentityAnchoredMarketCalibration-v1 — independent pre-score review

Date: 2026-09-29  
Verdict: **PASS** — zero P0 and zero P1 findings; the single opened-Train run
may proceed only through its already selected `attempt-02` scheduler branch.

## Frozen inputs

Exact bytes verified:

| Item | SHA-256 |
| --- | --- |
| Controller log | `a6259940439dff5e6c86a0d1c4de73e634608bb7b3d82804731ac103674e4efb` |
| Runner | `dc4e372440dc3f29091770394a8989c3602e83c37f0909367a5ce321bc614b05` |
| Focused tests | `475006ee99031374d267f2898c276fbeaab1e809e9a0ac0765ff133906738051` |
| Implementation log | `81744a7a2fe56f21190cbf36bc5baaac41487e0bdc95b963b4de805dd27c82e1` |

The runner also rechecks the exact Controller, v0 runner
`e61668c7...`, frozen-v0 validator `a612371a...`, settlement dependency
`1f1bdccd...`, scheduler branch binding `b2c72d46...`, question/hypothesis/rule
digests, and both Controller and implementation component-spec digests.
Read-only batch inspection showed generation 1 selected with journal head
`5bdd1ba9a7ca16df77819a8b49f564b1b6d7dd3cbb9826345cd21ad65235ac8f`;
`attempt-02` is still `controller_selected` and unclaimed.

## Method and leakage review

The runner preserves the exact v0 `195 -> 193 + 2 exclusions -> 87` lineage,
check-key digest `2e35779f...`, four chronological fit populations
`106/132/148/176`, checks `26/16/28/17`, labels, checkpoints and folds. It
requires every fit label to be available strictly before the first check
cutoff and rejects missing, extra, duplicated or changed rows.

Only the prediction/calibration stage changes. For each outer fold it computes
market-logit mean and population standard deviation from fit rows only, then
fits
`logit(q)=logit(p_now)+alpha+delta*z_market`. The analytic objective,
gradient and Hessian implement exactly
`sum Bernoulli NLL + 0.5*16*(alpha^2+delta^2)`. The identity market-logit
coefficient remains one. Damped Newton is deterministic, capped at 50
iterations, requires gradient infinity norm `<=1e-8`, and has no retry or
hyperparameter grid. Exactly four candidate fits are required.

Raw market, frozen ordinary market-only Logistic, frozen v0 market-plus-state
research parent and candidate are cross-linked row-for-row. The output contract
requires 87 probabilities, equal-event Brier/log loss, calibration and
reliability evidence, four fold reports, plus candidate-minus-each-comparator
complete-date and complete-week 10,000-draw intervals at seed `20260929`.
The frozen KEEP/refute/inconclusive decision is implemented exactly; refute and
inconclusive are both operational REVERT.

## Boundary and verification

The runner has no network/provider/subprocess capability. It requires the
one-thread environment (`OMP`, `OPENBLAS`, `MKL`, `NUMEXPR`, `VECLIB` all
`1`, `PYTHONHASHSEED=0`) before reading Train or fitting. The pre-score lock,
scorecard, manifest and failure receipt retain opened-Train-only, Dev/Final
closed, zero provider/network/cost, zero retry and no promotion. The outer
Supervisor remains responsible for the declared 600-second and 768-MiB
process ceilings.

Pinned-runtime focused replay:

```text
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONHASHSEED=0 \
PYTHONPYCACHEPREFIX=/private/tmp/market-rsi-identity-review-pycache \
/Users/estelle/.cache/market-rsi/runtimes/ds-py312-20260912-01/bin/python \
  -m unittest experiments.test_nfl_ingame_identity_anchored_market_calibration -v

Ran 10 tests in 0.022s — OK
```

The replay covered objective/gradient/Hessian arithmetic, penalty 16,
fit-only scaling, deterministic convergence, identity at zero adjustment,
four fits, all comparators on one mask, 87-row frozen bindings, decision
branches, date/week 10k wiring, thread fail-closed behavior and zero retry.

No real diagnostic, score, artifact creation, scheduler mutation, Dev/Final
read, network/provider call, payment or Git action was performed in this
review.
