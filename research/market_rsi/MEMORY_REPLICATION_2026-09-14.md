# Eight-round archive-memory replication

## One question

Does a complete own-arm archive help the same GLM researcher retain and combine
useful Train-only hypotheses across eight rolling rounds?

The two arms differ only in memory. `archive` can read its own prior tool records,
candidate results, interpretations, Dev summaries and costs. `fresh` starts each
round with an empty archive. Both arms receive the same expanding Train, tools,
model library, controller model, candidate limit, seed and budget admission rule.

## Frozen path

- Initial Train: 2026-08-26T12 through 2026-08-28T12.
- Rolling Dev: eight T12 sessions from 2026-08-29 through 2026-09-05.
- Final: twenty previously unopened hourly source objects from 2026-09-13T03
  through T15 and 2026-09-14T03 through T09.
- Each round opens one Dev only after both arm submissions are immutable. That
  Dev then becomes Train for the next round.
- After Round 8, the submitted model specifications are refit and frozen before
  any Final contents are materialized.

The exact filenames and compressed byte counts are in
`MEMORY_REPLICATION_SPEC_2026-09-14.json`. Selection used chronology and source
availability, not targets, model errors or Final scores.

## Replacement provenance

`memory-replication-20260914-01` stopped in Round 3 before Final. The archive
controller completed three candidate fits but used all 24 controller turns
before submitting a choice. This was a harness completion failure, not a data,
provider or budget failure. The failed run and its costs remain immutable.

The replacement is `memory-replication-20260914-02`. Its only operational
changes are a 32-turn allowance, equal to the existing 32-tool-call ceiling,
and an instruction to reserve the last four calls for correction and
submission. Candidate, token and dollar ceilings are unchanged. No artifacts,
plans or checkpoints from the failed run are imported. The same Final remains
sealed. These changes respond only to the observed completion failure, not to
Dev performance.

## What remains unchanged

This reuses the published causal target, row eligibility kernel, valid-zero
policy, feature library, four CPU trainer implementations, Codex/GLM bridge and
append-only accounting from the three-round pilot. The prior pilot's controller
archives, candidate plans, checkpoints, Dev scores, Final scores and post-hoc
ablation are not imported. Reuse is applicable because this experiment changes
the length and evidence breadth of the same memory comparison, not the target or
prediction layer.

The existing time-series research record remains applicable: fit uses earlier
sessions only; scaling is fit-only; Dev advances forward once per round; Final is
opened once after selection. See `TIME_SERIES_EVALUATION_POLICY.md`, including
its references to rolling-origin evaluation and backtest overfitting.

## Metrics and limits

Primary metric: equal-session mean MSE. Also report row-weighted MSE, per-session
archive-minus-fresh delta, positive-session fraction, positive-market fraction,
top positive-gain concentration, IC and calibration. Baseline is the frozen
lag-only model under the same rows.

This is an expanded pilot, not formal promotion. Twenty hours cover only two UTC
dates; intraday rows and neighboring hours are dependent. It does not measure
execution costs or PnL and cannot support a profitability claim.

## Stop and budget rules

Run all eight rounds regardless of Dev direction. Stop only for a persistent
infrastructure failure, source/hash mutation, or before the next paired archive
and fresh controller sessions if their full hard upper bounds do not fit the
remaining original $200 ledger. Never retry a controller response or source
session for score. A stopped partial run is not a completed comparison.
