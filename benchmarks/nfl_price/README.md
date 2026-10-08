# Historical NFL price-change task

This directory is a read-only index of the current task implementation.
It helps readers locate the data adapter, baseline and scorer; execution
continues to use the existing source-bound implementation.

## Prediction target

Predict the same token's trade-VWAP change 300 seconds ahead, comparing
trailing 30-second VWAP windows. Inputs use the task's historical trade-derived
features at the anchor; output is a forecast of that price change.

## Evaluation and baselines

The existing scorer computes paired, game-equal MSE and reports date/week
uncertainty and coverage on common rows. Comparisons include no price change
and the frozen ordinary HGB recipe defined by the indexed runner.

Trade VWAP is a historical trade statistic, not an executable bid/ask quote.
The repeatedly inspected Train task therefore measures historical forecasting
performance; profitability and untouched evaluation need separate evidence.

## Implementation and integration

[profile.json](profile.json) contains the canonical source paths, task ID,
horizon and baseline IDs. The [Architecture code map](../../docs/ARCHITECTURE.md#code-map)
places these files in the research loop.

The profile does not configure, authorize or launch a run. Existing batch and
operation manifests remain authoritative. Equities/earnings is planned and
has no implemented profile here.
