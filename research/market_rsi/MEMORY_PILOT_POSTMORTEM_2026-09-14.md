# Memory pilot postmortem — 2026-09-14

## Short answer

The pilot did show a real-looking difference, but it is still small-sample evidence.

Archive-memory beat fresh/no-memory on the final three held-out hours. The useful part is not just the average MSE. The useful part is that the fresh agent actually found the good direction once, then dropped it; the archive agent kept it and carried it into the final answer.

So the current hypothesis is:

> Archive memory helps the research agent keep useful intermediate experiments and compose them across rounds.

This is not yet evidence of profit. It is not a formal promotion result. It is a reason to run the next, bigger, cleaner test.

## Official frozen pilot result

Run: `memory-pilot-20260913-01`

Frozen code: `f7c300f24f0d4cdc05a44d9673343f9a971725ff`

Published tag: `pm-memory-pilot-v0.1.0`

Final dates: `2026-09-10`, `2026-09-11`, `2026-09-12`

| Model | Final average MSE | Versus baseline |
|---|---:|---:|
| Baseline lag-only | `5.9648811417630666e-05` | — |
| Fresh/no-memory | `5.955168559442658e-05` | +0.16% |
| Archive-memory | `5.756171720848301e-05` | +3.50% |

Archive-memory was also about 3.34% better than fresh/no-memory.

Actual GLM spend was about `$1.97057691`, not the `$50.64` hard cap.

## What each side did

Both sides kept the same trainer:

- ridge regression
- no intercept
- no normalizer

So this pilot was not about discovering a fancy trainer. It was mostly about feature search.

Archive-memory path:

1. Round 1: tried a simple magnitude feature.
2. Round 2: kept nonlinear lag features: `cubic_lag`, `signed_sqrt_lag`.
3. Round 3: added `lag_times_spread`.
4. Final answer: `lag_delta + cubic_lag + signed_sqrt_lag + lag_times_spread`.

Fresh/no-memory path:

1. Round 1: stayed near baseline.
2. Round 2: found a complex feature set that included spread interaction.
3. Round 3: simplified to `lag_delta + signed_sqrt_lag`.
4. Final answer: almost tied baseline.

That is the important behavior difference.

Fresh was not incapable. It found the useful family in Round 2. But without memory, it did not preserve that line of thought into the final selected model.

## Post-hoc ablation

This is diagnostic only. It uses already-opened final dates, so it does not change the official result.

Artifact: `artifacts/memory-pilot-20260913-01/posthoc-ablation-20260914-01/summary.json`

| Diagnostic model | Final average MSE | Read |
|---|---:|---|
| Baseline `lag_delta` only | `5.9648811417630666e-05` | Baseline |
| Archive final full spec | `5.756171720848301e-05` | Official archive final |
| Archive without `lag_times_spread` | `6.0375307403399756e-05` | Worse than baseline |
| Fresh final simple spec | `5.955168559442658e-05` | Almost baseline |
| Fresh Round 2 complex spec replayed | `5.756171720848046e-05` | Same as archive final |

The big clue:

> The fresh Round 2 complex spec, replayed post-hoc, matches the archive final result almost exactly.

That means the archive advantage here probably came from retention and sequencing, not from access to a unique idea.

## What looks real

- The final result was frozen before scoring.
- Source hash stayed unchanged.
- Final dates were not shown to the controller before final scoring.
- The result is not just one model beating zero; it is a paired comparison against a lag-only baseline and a fresh/no-memory arm.
- The ablation points to a specific mechanism: nonlinear lag response plus spread interaction.

## What is weak

- Only three final hours. That is too little.
- Rows inside an hour are highly dependent, so row count exaggerates confidence.
- One final day had high concentration: on 2026-09-12, the top market contributed about 75% of net SSE gain.
- Calibration slopes were above 1, so the predictions may still be undersized or miscalibrated.
- No PnL was measured. Lower MSE does not mean the strategy makes money.
- This was feature search under a simple trainer, not a full proof that the whole self-improvement loop works.

## What we learned

The current archive idea is promising, but the claim should be narrow:

> Archive helps the research agent remember and reuse useful experiments across rounds.

The current result does not yet prove:

- a profitable trading signal,
- stable out-of-sample improvement,
- a better training algorithm,
- or general RSI.

## Next round design

The next round should test the same question, but with enough final sessions to know whether this is stable.

Question:

> Does archive memory make the researcher better at preserving and combining useful feature hypotheses over multiple rounds?

Primary comparison:

- archive-memory researcher
- fresh/no-memory researcher
- same data access
- same tools
- same budget
- same final scoring dates
- same baseline

Primary metric:

- paired final MSE by session, not only aggregate row-weighted MSE

Required reports:

- average final MSE
- per-session delta
- positive-session fraction
- positive-market fraction
- top-gain concentration
- calibration slope/intercept
- Pearson and rank IC
- exact spend
- exact source hash

Minimum final size:

- at least 20 untouched final sessions

Do not call it a promotion unless:

- the final set has at least 20 sessions,
- the result is positive across many sessions, not one concentrated day,
- concentration is reported clearly,
- the final scoring code and objective were frozen before scoring,
- and PnL is separately tested later under frozen costs.

## Next action

Do not jump straight to PnL.

First run a larger archive-vs-fresh replication with 20+ final sessions. If archive still wins and the gain is not concentrated in one or two markets, then run the PnL layer.

