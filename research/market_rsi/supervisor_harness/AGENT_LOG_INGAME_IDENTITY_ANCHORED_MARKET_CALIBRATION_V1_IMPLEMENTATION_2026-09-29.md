# InGameIdentityAnchoredMarketCalibration-v1 implementation

Date: 2026-09-29  
Role: implementation only; no real experiment execution and no scheduler mutation

## Frozen authority and lineage

- Controller log SHA-256: `a6259940439dff5e6c86a0d1c4de73e634608bb7b3d82804731ac103674e4efb`
- Batch: `market-rsi-ingame-predictive-autonomy-20260929-03`, generation 1, `attempt-02`
- Scheduler branch binding SHA-256: `b2c72d468c5542e57c43c9724329e8d5c8ccb51f8d0011ee0e8cdab34b78b80b`
- Question / hypothesis / rule SHA-256 values are bound exactly as `4e074ad9...`, `736ab379...`, and `92399363...`.
- Controller component-spec SHA-256: `128321cc21f68b649b7e631c1f29891e3b9dbca4190aa11dc6e7d37b096623d4`
- Implementation component-spec SHA-256: `3befd9d507d5199329b4f18263522dc9ebba7e4f553acb5afb565206e3b513be`

## Delivered

- New independent runner: `experiments/nfl_ingame_identity_anchored_market_calibration.py`
  - SHA-256: `dc4e372440dc3f29091770394a8989c3602e83c37f0909367a5ce321bc614b05`
- New focused tests: `experiments/test_nfl_ingame_identity_anchored_market_calibration.py`
  - SHA-256: `475006ee99031374d267f2898c276fbeaab1e809e9a0ac0765ff133906738051`

The runner reads the hash-bound v0 artifact and opened Train only, preserves the
exact `195 -> 193 + 2 exclusions -> 87` denominator/mask, and emits raw market,
frozen v0 ordinary market-only, frozen v0 market-plus-state parent, and candidate
probabilities on every check row. It performs one fit in each of the four frozen
outer folds. The fit is exactly
`logit(q)=logit(p_now)+alpha+delta*z_market`, with fit-only clipped-logit
standardization, objective
`sum Bernoulli NLL + 0.5*16*(alpha^2+delta^2)`, and deterministic analytic
damped Newton capped at 50 iterations and gradient infinity norm `<=1e-8`.
There is no retry or grid.

The scorecard contains equal-event Brier, bounded log loss, calibration
slope/intercept and reliability bins for all four arms; fold reports; and
candidate-minus-each-comparator complete schedule-date and observed-game-week
10,000-draw intervals. The exact Controller KEEP/refute/inconclusive rule is
implemented, with refute and inconclusive both operationally REVERT.

The launch contract requires one process/thread (`OMP`, `OPENBLAS`, `MKL`,
`NUMEXPR`, and `VECLIB` all `1`, plus `PYTHONHASHSEED=0`). Dev/Final, network,
provider, cost, publication and promotion remain false/zero. The artifact is
explicitly historical opened-Train Discovery evidence.

## Verification

Passed 10 focused tests:

```text
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONHASHSEED=0 \
PYTHONPYCACHEPREFIX=/private/tmp/market-rsi-identity-pycache \
python -m unittest experiments.test_nfl_ingame_identity_anchored_market_calibration -v

Ran 10 tests in 0.014s -- OK
```

Also passed:

```text
PYTHONPYCACHEPREFIX=/private/tmp/market-rsi-identity-pycache \
python -m py_compile \
  experiments/nfl_ingame_identity_anchored_market_calibration.py \
  experiments/test_nfl_ingame_identity_anchored_market_calibration.py
```

The tests cover objective/analytic gradient/Hessian arithmetic, penalty on both
`alpha` and `delta`, deterministic convergence, fit-only scaling, exact identity
at zero adjustment, exact four-fit execution, frozen-arm same-mask preservation,
87-row/hash bindings, date/week bootstrap wiring, decision branches, single-thread
fail-closed behavior, and zero-retry/boundary constants.

## Not performed

No real diagnostic was run, no score was observed, no output artifact directory
was created, and scheduler state was not read-modify-written. Independent
pre-score review remains required before the single authorized execution.
