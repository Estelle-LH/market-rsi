# InGamePreAnchorMomentumOffsetLogistic-v4 — implementation

Date: 2026-09-29  
Scope: implementation and tests only; no real opened-Train execution and no scheduler mutation.

## Frozen inputs

- Controller: `AGENT_LOG_INGAME_PREDICTIVE_AUTONOMY_GENERATION1_CONTROLLER_2026-09-29.md`, SHA-256 `a6259940439dff5e6c86a0d1c4de73e634608bb7b3d82804731ac103674e4efb`.
- Candidate component-spec commitment: `d979e6e8e18652569baad58ed50a4c8974ae17b400cba5b126c7c7b2a4a6492d`.
- Rule commitment: `914a33a6eb2361a655b136207742d05a61ceb8b6ec1cf9cdeb7f568e2b217ff4`.
- Parent momentum runner/review/manifest: `a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9` / `48080a2ccaa188673d7a2e29bc47bb10c1761e3bfc61aab5905b29b95e5a3079` / `9e7d5813a798a23da5e9992e079ec795e55d952529f11927f6244e9ac80f7499`.
- v0 ordinary baseline remains the archived `market_model_probability` in predictions SHA-256 `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56`; it is never refit.

## Implementation

- Runner: `research/market_rsi/experiments/nfl_ingame_pre_anchor_momentum_offset_logistic_train_diagnostic.py`  
  SHA-256 `fa5860b465f73e57416390cc376bfde8dda9b3ecad5269d67e8c212b85dde9a6`.
- Focused tests: `research/market_rsi/experiments/test_nfl_ingame_pre_anchor_momentum_offset_logistic_train_diagnostic.py`  
  SHA-256 `8f0d8079ae15e57b97336ed82d171cdbae0597ab47209d20a53776cf245c8de6`.

The runner reconstructs the exact parent 120-second signal for every one of the 193 materialized outer fit/check rows and fails closed on any missing reference. Each outer fold standardizes momentum from fit rows only, then performs exactly one analytic-gradient L-BFGS-B fit of `logit(p_now)+alpha+beta*z_momentum` with objective `sum NLL + 0.5*beta^2`. The current-market coefficient is fixed at one; there are four fits, no retry, and zero ordinary-control refits.

The 87-row output preserves identity, label, raw market, archived v0 ordinary market-only probability, candidate probability, and parent reference/signal lineage. The scorecard includes equal-event Brier/log loss/calibration, four folds, complete-date and complete-week 10,000-draw paired intervals, and the exact support/refute/inconclusive plus KEEP/REVERT rule. Protected Dev/Final, network, provider, payment, publication and promotion stay closed.

Execution requires the external one-thread environment contract: `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`, and `PYTHONHASHSEED=0`.

## Verification

- Focused suite: `10/10 PASS`.
- Adjacent parent suites (momentum audit, offset score-time, nested shrinkage): `34/34 PASS`.
- `py_compile`: PASS using a `/private/tmp` bytecode cache.
- `git diff --check` on the new runner and focused test: PASS.
- No real runner invocation occurred.

Planned single-run command after independent pre-score approval:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0 \
PYTHONPATH=research/market_rsi \
/Users/estelle/LightHouse/venv_3.12/bin/python \
  -m experiments.nfl_ingame_pre_anchor_momentum_offset_logistic_train_diagnostic \
  --source-root "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01" \
  --output "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-pre-anchor-momentum-offset-logistic-20260929-01"
```

The source and output paths in the launch command must be rechecked against the bound `SOURCE_ROOT` and persistent artifact root before execution; a fresh output ID is mandatory.
