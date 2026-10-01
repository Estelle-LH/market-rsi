# In-game predictive autonomy batch — generation-1 Controller — 2026-09-29

## Frozen pool

Batch `market-rsi-ingame-predictive-autonomy-20260929-03` is at journal 1,
state `860cfecc832f4123a9a1a1c6f38a735325b02ae725f2afbba56167084a81c3a5`,
with three attempts remaining. Its exact pool hint is
`2ba03f832fbeddfc4e27d996ffffeefe10c41ee0c5714e57ee8c3db9525f8205`:
two active slots, at least one exploration slot. Freeze:

| Attempt | Allocation | Candidate | Changed causal stage | Research parent |
| --- | --- | --- | --- | --- |
| `attempt-01` | exploitation | `InGamePreAnchorMomentumOffsetLogistic-v4` | prediction only | reviewed momentum audit `a99cf988...` |
| `attempt-02` | exploration | `InGameIdentityAnchoredMarketCalibration-v1` | prediction only | archived v0 negative state branch `c40b1df5...` |

The task-local comparison incumbent is separately fixed as raw market
`89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f`.
Neither research parent is promoted or substituted for it. The ordinary
market-only Logistic arm is the frozen v0 prediction column in predictions
SHA-256 `505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56`.

This pool uses one exploitation and one method-distinct exploration slot, so
the indivisible-slot exploration allocation is 50% and satisfies the 30%
reserve. It is a selection only: no implementation, execution, scoring, batch
append, incumbent change, or authority change is performed here.

## Shared frozen evaluation

Both candidates must reproduce the v0 runner
`e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7`,
manifest `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7`,
scorecard `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87`
and exact check-key digest
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
They keep `195 -> 193 -> 87`, the same two exclusions, one Q3 `<=08:00`
causal checkpoint per game, home-settlement label, chronological outer fit
counts `106/132/148/176`, check counts `26/16/28/17`, scorer, seed and
10,000 complete-date and complete-week paired bootstrap draws at seed
`20260929`. Every arm must emit one probability on each of the same 87 rows;
missing inputs, chronology drift, mask drift, nonfinite output or optimizer
failure is terminal and cannot drop/impute a row.

Primary metrics are equal-event Brier and log loss; also persist calibration,
all four folds, paired date/week intervals and an 87-row predictions file.
The repeatedly inspected opened-Train result can change only the task-local
Discovery incumbent under the frozen rule; it cannot authorize promotion.

## Attempt 01 — momentum-to-prediction exploitation

Question: does a fixed current-market-logit offset plus the exact reviewed
120-second pre-anchor momentum beat both raw market and ordinary market-only
Logistic on the same chronological OOF rows?

The research parent is the credit-1 reviewed audit runner
`a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9`,
manifest `9e7d5813a798a23da5e9992e079ec795e55d952529f11927f6244e9ac80f7499`
and review `48080a2ccaa188673d7a2e29bc47bb10c1761e3bfc61aab5905b29b95e5a3079`.
It found positive aggregate alignment and 3/4 positive folds, but both grouped
intervals crossed zero. The parent emitted no probability, so it is compared
by exact lineage/signal replay; prediction scores compare the new arm to raw
market and the frozen ordinary market-only arm.

For every outer fit and check row, recompute the parent's exact signal:
`reference_cutoff=floor(decision_epoch_seconds)-120`; `p_ref` is the latest
home-oriented size-weighted fill second strictly before that cutoff with age
`<=300` seconds; clip only for logits; momentum is
`logit(p_now)-logit(p_ref)`. Coverage is mandatory on all rows. Standardize
momentum using outer-fit mean/std only. Fit exactly
`logit(q)=logit(p_now)+alpha+beta*z_momentum`, with market coefficient fixed
at one and objective `sum Bernoulli NLL + 0.5*beta^2`. Use analytic-gradient
L-BFGS-B, `maxiter=1000`, `gtol=1e-8`, `ftol=1e-12`, one fit per outer fold,
no retry or alternate lag.

KEEP requires all: aggregate Brier and log loss below both raw market and
ordinary market-only; Brier wins versus each in at least 3/4 folds; and both
date- and week-grouped 95% upper bounds for candidate-minus-raw Brier below
zero. Failure of either aggregate proper score versus raw, or at most 1/4 raw
Brier wins, is scientific refutation. Any other valid result is inconclusive;
both refute and inconclusive are operational REVERT. No post-score change.

- question digest: `8b72e8eed478b3c55d6d44f83eeae27c0667dbf485b21b079378dd4f0b64d217`
- hypothesis digest: `3819263244cd2cbacbf3ea0ae244bef830e58e67a584d9f7f0387d5b5d73b3bf`
- rule digest: `914a33a6eb2361a655b136207742d05a61ceb8b6ec1cf9cdeb7f568e2b217ff4`
- complete component-spec digest: `d979e6e8e18652569baad58ed50a4c8974ae17b400cba5b126c7c7b2a4a6492d`
- resource ceiling: one process/thread, four fits, 1,200 seconds, 1 GiB RSS,
  one attempt, zero network/provider/cost.

## Attempt 02 — identity-anchored calibration exploration

Question: can a market-only calibrator penalized toward the raw-market identity
map avoid the ordinary market-only Logistic degradation and improve proper
scores over raw market? This is a trainer/calibration question with no new
information. Its research parent is the archived v0 market-plus-state negative
branch `c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d`;
the parent probability is retained as a scored comparator, distinct from raw
market. The stopped score-time route is not reopened. The failed nested
shrinkage run remains credit-0 invalid/cooldown; this candidate uses neither
its grid nor its retry path.

Using only `p_now`, standardize its clipped logit on each outer fit and fit
`logit(q)=logit(p_now)+alpha+delta*z_market`. Penalize adjustments toward the
identity map with the fixed objective
`sum Bernoulli NLL + 0.5*16*(alpha^2+delta^2)`. Use a deterministic damped
Newton solver with analytic gradient/Hessian, at most 50 iterations,
gradient-infinity tolerance `1e-8`, one fit per fold and no retry, grid or
post-score tuning. Score raw market, frozen ordinary market-only, frozen v0
market-plus-state parent and candidate on the same 87 rows.

KEEP requires all: aggregate Brier and log loss below all three comparators;
Brier wins versus raw market and ordinary market-only in at least 3/4 folds;
and both date- and week-grouped 95% upper bounds for candidate-minus-raw Brier
below zero. Failure of either aggregate proper score versus raw, or at most
1/4 raw Brier wins, is scientific refutation. Any other valid result is
inconclusive; both refute and inconclusive are operational REVERT.

- question digest: `4e074ad9b4ccc8af0373a6e50c4c1580f5dc3121fbc4ace484c6626058d02fbd`
- hypothesis digest: `736ab3792406e98d2e2c5fd443b81c06b1b3d5c9cc097e0df2d9a23ee8f55d87`
- rule digest: `92399363c928900ac549131a9db1289c7dae3db68a6f3dc51459f373d4fb643e`
- complete component-spec digest: `128321cc21f68b649b7e631c1f29891e3b9dbca4190aa11dc6e7d37b096623d4`
- resource ceiling: one process/thread, four fits, 600 seconds, 768 MiB RSS,
  one attempt, zero network/provider/cost.

## Exact scheduler selections

The canonical selection-plan digest is
`606453d5dcb1082dc3e046e8c7203bdb5a23ac4f548ab5d734c59e8d6b951122`.
For each member, `controller_decision_sha256` is the final SHA-256 of this
exact log, supplied by the Supervisor after the file is closed.

```json
{"batch_id":"market-rsi-ingame-predictive-autonomy-20260929-03","comparison_incumbent_sha256":"89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f","pool_generation":1,"selection_hint_sha256":"2ba03f832fbeddfc4e27d996ffffeefe10c41ee0c5714e57ee8c3db9525f8205","selections":[{"allocation":"exploitation","attempt_id":"attempt-01","candidate_id":"InGamePreAnchorMomentumOffsetLogistic-v4","hypothesis_digest_sha256":"3819263244cd2cbacbf3ea0ae244bef830e58e67a584d9f7f0387d5b5d73b3bf","method_family":"pre_anchor_momentum_offset_logistic_prediction","predeclared_rule_sha256":"914a33a6eb2361a655b136207742d05a61ceb8b6ec1cf9cdeb7f568e2b217ff4","question_digest_sha256":"8b72e8eed478b3c55d6d44f83eeae27c0667dbf485b21b079378dd4f0b64d217","question_id":"ingame-pre-anchor-momentum-offset-logistic-v4-q1","research_parent_sha256":"a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9","resource_hint":{"authority_granted":false,"max_attempts":1,"max_bytes":0,"max_cost_usd":0.0,"max_time_seconds":1200,"resource_class":"small_experiment"}},{"allocation":"exploration","attempt_id":"attempt-02","candidate_id":"InGameIdentityAnchoredMarketCalibration-v1","hypothesis_digest_sha256":"736ab3792406e98d2e2c5fd443b81c06b1b3d5c9cc097e0df2d9a23ee8f55d87","method_family":"identity_anchored_market_calibration","predeclared_rule_sha256":"92399363c928900ac549131a9db1289c7dae3db68a6f3dc51459f373d4fb643e","question_digest_sha256":"4e074ad9b4ccc8af0373a6e50c4c1580f5dc3121fbc4ace484c6626058d02fbd","question_id":"ingame-identity-anchored-market-calibration-v1-q1","research_parent_sha256":"c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d","resource_hint":{"authority_granted":false,"max_attempts":1,"max_bytes":0,"max_cost_usd":0.0,"max_time_seconds":600,"resource_class":"small_experiment"}}]}
```

## Boundary

Implementation and independent pre-score review are required before any
single execution. Resident opened Train only; no Dev/Final, network, provider,
payment, publication, promotion, batch mutation or score mutation is authorized
by this log. Historical event time remains distinct from publish/receive time.
