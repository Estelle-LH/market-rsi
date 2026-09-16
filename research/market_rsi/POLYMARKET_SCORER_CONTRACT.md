# Polymarket 60-second scorer contract

## One sentence

At each frozen decision time, predict the first admitted Polymarket midpoint exactly 60 seconds later.

## Fixed baseline

The persistence baseline predicts that the midpoint will not move:

`baseline prediction = midpoint at decision time`

This baseline has no fitted parameters and cannot see Dev or Test outcomes.

## Primary score

MSE is calculated inside each game first. The game MSE values then receive equal weight. Therefore one game with many observations cannot dominate the result.

We report candidate improvement as:

`(baseline MSE - candidate MSE) / baseline MSE`

Positive is better. A value of `0.10` means the candidate reduced MSE by 10% relative to persistence. If baseline MSE is zero, relative improvement is undefined rather than infinite.

## Exact paired comparison

The baseline and candidate are compared on the exact same successful row IDs. A missing candidate output is never replaced with zero. A timeout or invalid output remains a failed row with its failure code.

If any frozen row is failed or missing, the official primary result is withheld. The scorer may show a clearly labelled paired-success diagnostic, but it cannot be used for promotion. Coverage, missing rows, failed rows, and failure codes are always reported.

## Auxiliary diagnostics

The scorer also reports MAE, mean prediction, mean target, calibration bias, and linear calibration slope/intercept. These help explain an MSE result; they do not replace the primary score.

This is a prediction-error score only. It does not claim fills, net PnL, or profitability.

## Test rule

Dev can be scored while developing. Test must be precommitted, untouched, and contain at least 20 distinct complete games (`game_id`). The independent unit is a game, not a calendar day, so many eligible games may occur on the same UTC day. The report records both game count and UTC-day count. The runner creates an exclusive Test gate before opening the rows. A successful score or a failed scoring attempt consumes that gate, and the same experiment cannot open Test again. Test is never used for tuning.

The scorer enforces the local gate. The outer experiment runner must keep the Test files and gate inaccessible to the researcher and preserve the gate as an immutable artifact.
