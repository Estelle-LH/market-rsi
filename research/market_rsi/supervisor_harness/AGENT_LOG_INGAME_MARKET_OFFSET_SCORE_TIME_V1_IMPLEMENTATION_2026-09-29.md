# `InGameMarketOffsetScoreTimeDiagnostic-v1` implementation — 2026-09-29

Status: **IMPLEMENTATION COMPLETE; REAL SCORE NOT RUN; INDEPENDENT PRE-SCORE REVIEW REQUIRED**

This implementation follows the frozen Controller decision in
`AGENT_LOG_INGAME_MARKET_OFFSET_SCORE_TIME_V1_CONTROLLER_2026-09-29.md`
after the exact v0 result received an independent PASS. It adds a new runner
and a new focused test module. It does not modify the frozen v0 runner,
extractor or tests, and it does not change the completed v0 artifact.

No real v1 score was executed. No Dev/Final data was opened, no network or
provider was contacted, no money was spent, and no publication, promotion or
deployment action occurred.

## Exact implementation identity

| File | SHA-256 |
| --- | --- |
| `research/market_rsi/experiments/nfl_ingame_market_offset_score_time_train_diagnostic.py` | `6194d25712df0e251fe0c56c671557967f8c7f5f7e62c28ca9981c09a3adf120` |
| `research/market_rsi/experiments/test_nfl_ingame_market_offset_score_time_train_diagnostic.py` | `72be12f0a84c46550e1f3604ae1769c261e22311dbdd2903c99b9b3812e1ea76` |

Frozen dependencies were rechecked without editing them:

| Frozen input | SHA-256 |
| --- | --- |
| v0 runner | `e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7` |
| R checkpoint extractor | `37a26997406de0e54bd9d91de10e7417a8b340c68b675892c4f16e9a51675163` |
| v1 Controller decision | `3930ab266e1983e6cd15a3472977984961b0f08a45e246eebb8feefbb048e8ce` |
| v0 result independent review | `325543498c556a1c1ba0e8e3adde42c4546c35e1b0bcffac8efbeafd3d38f983` |

The runner also fails closed on the exact seven-file v0 artifact set and the
hashes recorded in the Controller decision/result review. It binds the v0
materialized-population digest
`0bb6ae95fd26937b592569f004c16ac729b1e4c6b796c975a1d988e57c4d2c34`
and check-mask digest
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.

## Implemented frozen experiment

- The v0 195-game source denominator, exact two exclusions, 193 materialized
  checkpoints, 87 check games, outcome orientation, Q3 checkpoint, strict
  preceding-trade rule, 300-second staleness cap, 22-date initial fit and four
  5-date expanding checks are reused exactly.
- The raw market remains the unfitted in-game comparison incumbent. The two
  v0 LR arms remain archived in the immutable parent artifact and are not
  refit.
- Each of four folds fits exactly three new arms: offset intercept, offset
  linear state, and offset linear state plus `score_time_ratio_k4`. The runner
  rejects any total other than 12 fits.
- Every arm uses `eta = market_logit + b + w^T z`; the market-logit coefficient
  is not a parameter and is therefore fixed at exactly one.
- The objective is sum binary NLL plus `0.5 * ||w||^2`. The intercept is
  excluded from the penalty. A deterministic analytic-gradient L-BFGS-B call
  is made once per arm/fold with no sweep or retry.
- Continuous state features are standardized using fit-fold rows only.
  Possession and down one-hot values are unchanged. The market offset is never
  scaled. Optimizer, coefficient, scaling, rank and conditioning diagnostics
  are recorded but cannot change the decision.
- `score_time_ratio_k4` is recomputed only from the already materialized
  strictly pre-anchor score difference and regulation seconds remaining. The
  recomputed value must match the frozen extractor column before scoring.
- The v0 scorer, calibration report, 10,000 complete-group resamples and seed
  `20260929` are reused. All four arms share each row, label and checkpoint.
- The predeclared support/refute/inconclusive rule is encoded directly. No
  grouped interval or diagnostic can override it after scores are visible.
- Pre-score receipts include source, code, scorer, Controller, v0 result-review
  and v0 artifact hashes. Production output must be a fresh path under the
  persistent local MarketRSI artifact root; cloud-looking and temporary paths
  are rejected.

## Verification

Focused v1 and adjacent frozen-v0 suites:

```text
....................
----------------------------------------------------------------------
Ran 20 tests in 8.199s

OK
```

The ten new tests cover:

1. analytic gradient versus a central numerical difference and the sum-NLL
   objective;
2. explicit exclusion of the intercept from the penalty;
3. fixed coefficient-one market offset;
4. causal score/time-only nonlinear construction;
5. fit-fold-only scaling with binary columns unchanged;
6. exact three-arms-by-four-folds fit count and common masks;
7. all three decision routes;
8. exact v0 parent artifact and frozen-dependency hashes;
9. actual opened-Train 195 -> 193 -> 87 attrition, materialized/check-mask
   hashes, 106/132/148/176 fit counts and zero unavailable fit labels;
10. persistent non-cloud output rejection.

Both new modules compile with Python 3.12. Scoped no-index whitespace checks
produced no diagnostics. A persistent artifact inventory found no v1
`offset-score-time` output directory, confirming that implementation testing
did not execute the real score.

## Boundary and next gate

This is code-ready historical opened-Train Discovery only. It is not evidence
that PBP adds information, that the score-time representation works, that data
was available in real time, or that any model should be promoted. The exact
two implementation files above require an independent pre-score review. Only
an explicit PASS on their current hashes may admit the single frozen v1 run;
any edit requires a new hash and review.
