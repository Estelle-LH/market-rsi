# Continuous opened-Train Discovery batch — 2026-09-29

Status: **COMPLETE — `deadline_reached`**. Five real candidate attempts ran;
all used the resident opened Train cohort only. The durable journal closed with
32 records, head `bb254c289f7ba5ce739b2a86e26b401747271cc4eb5d10b86302f1c95095d465`
and state `300a744fe4060edda8fed533c73ba6ddd65adb753fd0b5759790a3fb270d7f88`.

- Start: `2026-09-29T18:03:21Z` (`2026-09-29 14:03:21 ET`).
- Hard deadline: `2026-09-29T20:03:21Z`.
- Attempt limit: 10; actual attempts consumed: 5.
- Frozen evaluation: 195-event 2025 NFL moneyline population, 194 materialized
  events plus one reported exclusion, 87 paired check events across 20 schedule
  dates and seven observed game weeks, with four chronological expanding checks.
- Boundaries: no protected Dev/Final, external acquisition, network, paid
  provider, release, publication, or promotion.
- Interpretation: adaptively reused opened-Train Discovery, not untouched OOS.

## Closed-loop evidence and attempts

| # | Candidate | Evidence that selected it | Equal-event Brier / log loss | Delta vs market | Fold Brier wins vs market | Decision |
| ---: | --- | --- | --- | --- | ---: | --- |
| 1 | `MarketOrthogonalPricePath-v1` | The full offset candidate was too flexible, so the Controller compressed the path family to one market-orthogonal direction. | `0.206923 / 0.602529` | `+0.001390 / +0.004078` | `1/4` | `REVERT` |
| 2 | `MarketRecentCompositePath-v2` | Attempt 1 had fit/check sign instability; the Controller restricted training to the most recent three complete weeks and used one composite. | `0.204238 / 0.596373` | `-0.001295 / -0.002078` | `2/4` | `REVERT` |
| 3 | `MarketRecencyWeightedCompositePath-v3` | Attempt 2 improved aggregate scores but missed fold stability; the Controller retained the same representation and added fixed `.25/.50/1.00` recency weights. | `0.203857 / 0.595837` | `-0.001677 / -0.002614` | `3/4` | `KEEP` |
| 4 | `MarketAllPriorDecayCompositePath-v4` | Attempt 3 suggested recency mattered; the Controller tested whether all prior weeks with one-week exponential decay would reduce variance. | `0.204422 / 0.597080` | `-0.001111 / -0.001371` | `3/4` | `REVERT` |
| 5 | `MarketRecencyWeightedCompositeDispersion-v5` | Attempt 4 diluted the recent regime; the Controller returned to Attempt 3 and added only market/composite-orthogonal within-window dispersion. | `0.202260 / 0.591819` | `-0.003273 / -0.006632` | `2/4` | `REVERT` |

Attempt 5 beat Attempt 3 in aggregate Brier/log loss by
`-0.001597 / -0.004018` and in three of four paired folds, but it beat the raw
market in only two of four folds. The predeclared KEEP rule required at least
three market-fold Brier wins, so aggregate improvement did not replace the
incumbent. Its dispersion coefficient also changed sign across folds
(`-0.0115`, `-0.1164`, `+0.0629`, `+0.1153`). Schedule-day and observed-week
95% intervals for candidate-minus-market Brier were respectively
`[-0.01036, +0.00466]` and `[-0.00940, +0.00435]`.

## Batch result

- Current Discovery incumbent: `MarketRecencyWeightedCompositePath-v3`.
- Incumbent minus market: Brier `-0.0016768`; log loss `-0.0026142`.
- Effective findings: recent-window restriction, representation compression,
  and fixed recency weighting each reduced the damage of the original broad
  offset branch; the dispersion branch produced a larger aggregate signal but
  not stable market-fold evidence.
- Ineffective findings: an unconstrained broad price-path offset, equal-weight
  recent history, and all-prior exponential decay did not meet the frozen
  replacement gates.
- All candidate and failed-branch code/results are retained separately from the
  incumbent; `REVERT` does not erase a research branch.
- Local provider cost: `$0`; network/external fetches: `0`; protected Dev/Final
  opens: `0`; control refits in Attempts 4-5: `0`.
- Per-round human intervention after batch start: none. The Supervisor performed
  one internal worker interruption/recovery and independent review repair loops;
  these did not choose scientific results or change the scorer.

## Claims not supported

This batch does not establish formal OOS improvement, promotion readiness,
profitability, generalization beyond the 2025 NFL seed domain, or benefit from
RSI self-evolution. The grouped intervals cross zero and the same Train checks
were inspected adaptively.

## Next Controller memory

The next batch should preserve Attempt 3 as incumbent and retain Attempt 5 as a
promising branch. The immediate question is why dispersion helps aggregate loss
while failing the market-fold gate: test a causal shrinkage or sign-stability
treatment for the dispersion residual, without changing the scorer or masks.
Separately, once the continuous loop is stable, compare the same frozen Astra
under a fixed research process against the same Astra with accumulated research
memory, using equal permissions and resource budgets across repeated runs.
