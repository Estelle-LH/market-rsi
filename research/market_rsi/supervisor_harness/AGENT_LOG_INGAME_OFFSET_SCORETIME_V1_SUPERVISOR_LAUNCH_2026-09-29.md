# `InGameMarketOffsetScoreTimeDiagnostic-v1` Supervisor launch record — 2026-09-29

This record preserves a Supervisor launch-path error separately from the one
completed scientific execution. It does not change the frozen experiment,
score, decision rule, or artifact.

## Pre-import launch failure

The first shell invocation used this reviewed runner and persistent output ID,
but set the process working directory to
`/Users/estelle/Developer/market-rsi/research/market_rsi` without adding the
repository's `research/market_rsi` directory to `PYTHONPATH`:

```text
PYTHONDONTWRITEBYTECODE=1 \
  "/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python" \
  experiments/nfl_ingame_market_offset_score_time_train_diagnostic.py \
  --source-root "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01" \
  --output "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-market-offset-score-time-train-diagnostic-20260929-01"
```

It exited with code 1 during module import, before `main()` or `run()` could be
entered:

```text
Traceback (most recent call last):
  File "/Users/estelle/Developer/market-rsi/research/market_rsi/experiments/nfl_ingame_market_offset_score_time_train_diagnostic.py", line 28, in <module>
    from minimal_prediction_loop import probability_contract, proper_scoring
ModuleNotFoundError: No module named 'minimal_prediction_loop'
```

Immediately after the failure, the Supervisor verified both:

- the intended output path did not exist; and
- the runner SHA-256 was still
  `6194d25712df0e251fe0c56c671557967f8c7f5f7e62c28ca9981c09a3adf120`,
  exactly matching the independent pre-score review.

Because Python failed while importing the module, this invocation performed
zero model fits and created no experiment artifact. It is a Supervisor launch
failure, not a completed or scored candidate attempt. It receives no research
credit.

## One completed scientific execution

The corrected invocation ran from `/Users/estelle/Developer/market-rsi` with
`PYTHONPATH=research/market_rsi`, the same frozen runner, source root, and output
ID. It completed exactly once with 12 model fits and produced the sole v1
artifact directory at the persistent output path above. There was no parameter,
feature, threshold, seed, data, or decision-rule change.

The completed manifest SHA-256 is
`b9840bc2fe6258be40f61800fa212e157821230bd3e5c0af6bc8bf43f537ab4b`.
It reports `SCORE_TIME_K4_HYPOTHESIS_REFUTED`, 195 source games, 193
materialized games, two exclusions, 87 check games, 12 fits, zero provider
cost, and closed Dev/Final/network/publication/promotion boundaries.

