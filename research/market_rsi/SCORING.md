# How predictions are checked

12:06 UTC update: a verified closed final failure now remains a failed/unscored
planned result, with an explicit runner review before the next original job.
Ambiguous jobs stay pending. Final reports retain all planned tasks and use null
for unavailable pairs; no failure imputation, selective row mask or aggregate
winner. status_report() lists failed, pending and unstarted jobs without computing
new scores. 561 offline tests pass. No actual market/final evaluation occurred.

## September 7, 11:46 UTC — sealed transfer stage

final_stage.py now verifies all learning/transfer submission seals before hidden
reads, runs only frozen sources through the existing isolated prediction path,
and independently rechecks every final prediction/cleanup receipt. It reports
Reset/Archive/Learn against the common baseline, Archive against Reset, and Learn
against Archive for each transfer task. It never opens learning-task hidden sets
or returns final scores to a researcher. No overall winner or net PnL is inferred.

The 550-test suite includes 21 new final-stage checks, using fabricated providers,
execution receipts and market rows. No real final task/score exists. Live source/
task admission is closed. Failed or incomplete final jobs remain pending; their
failure/PnL handling and independent whole-step wall enforcement are unfinished.
Source snapshot: final-stage-sources-01.json. Follow latest STATUS/RUNBOOK entries.

## Numeric scoring is implemented; market admission is not

market_scoring.py reads the runner-owned prediction journal independently. It
requires the exact Train/evaluation/code hashes, every expected row in order,
finite predictions inside frozen bounds, an intact hash chain and a matching
completion receipt. It rejects missing/extra predictions instead of comparing
only the surviving rows. It never imports candidate code or accepts its scores.

The scorer recomputes the materializer's numeric labels from saved quote
endpoints. This catches inconsistent artifacts, not a false source clock or an
incorrect first-observed endpoint. Original capture provenance, replay/label
selection, task assignment, pre-score freezing and permitted phase still need
independent admission by the outer worker. There is no live-scoring CLI or
unconditional admission callback.

Current arithmetic supports the materializer's mid change and gross YES/NO
round-trip price changes. The actual research target has NOT been selected or
frozen. These are not settlement labels or net-profit targets. The numeric report
keeps net PnL null. Separate taking-simulation arithmetic is now implemented below;
it has not been admitted or run as a real market research experiment.

## What it reports

- MSE, MAE, Pearson/rank correlation, and calibration slope/intercept.
- Paired candidate-minus-baseline changes on identical complete rows. Negative
  error change is better; unchanged output gets zero improvement.
- Results by UTC session and whole game, plus row-weighted, equal-session and
  equal-game summaries. Dense quote streams do not become independent games.
- Missing frozen sessions are errors, not silently imputed empty days.
- Constant predictions/targets have undefined correlation, not an invented zero.
- Frozen-seed circular session-block intervals are available only for at least
  20 declared untouched sessions. Short or previously inspected samples stay
  descriptive. Twenty sessions do not automatically authorize promotion; source
  validity, breadth, other gates and trading results remain separate.

The evaluation skill drove these distinctions. Its full experiment-spec validator
must still run on the eventual pre-score market A/B specification; toy arithmetic
tests are not a substitute and do not establish a 20-session final experiment.

## Fee check — runner note, not a frozen trading rule

The [official Kalshi schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf)
read September 7 is effective July 7, 2026. It specifies a price-dependent taker
formula with a per-series multiplier, and describes rounding the fee plus
position cost to a centicent. Its displayed examples are cent-denominated.
Do not silently assume an older whole-cent rule, a universal multiplier or that
perpetual-futures tiers apply to sports event contracts. Before net PnL, freeze
the relevant historical series schedule, rounding interpretation and any declared
conservative approximation. Record entry and exit costs separately. Quote motion
does not prove passive fills or actual order execution.

## Evidence at 07:21 UTC

250 offline tests pass, 21 added for scoring. Read-back of the already completed
Harbor/E2B fixture returns its three expected predictions without another provider
call. This is numeric/receipt validation only. No historical market experiment,
agent improvement, net PnL or hidden-Test score has been computed.

## Taking-simulation arithmetic — 07:40 UTC

taking_replay.py is a separate runner-only module with no live-order or dispatch
CLI. It accepts a frozen numeric/latency contract, fixed integer size, threshold,
adverse slippage, initial cash and one global pending/open order. Every market
requires an explicit fee rule, historical validity interval and source hash.
The implemented fee rounding is deliberately named a declared approximation;
the fixture's 0.07 coefficient and cent quantum are not a chosen real-market
fee contract or a claim about the exchange's precise rounding.

The policy selects long YES, long NO or flat from the signed prediction alone.
YES buys the observed ask and exits at the bid; NO uses the corresponding
complement prices. Fees apply to both modeled legs. Cash is reserved at the
decision using the worst possible collateral/fee amount, not a future cheap
entry. It is released only after the result is observable. Equal timestamps
remain pending rather than inventing cross-stream order.

Insufficient entry depth produces an unfilled FOK approximation, with the hold
retained until that entry time. Insufficient later exit depth is not a deleted
trade: it creates a conservative write-off diagnostic and stops future trading.
It does not claim a real sale or a successfully closed position. The cash model
is conservative under its stated assumptions, not a proven bound on real fills,
exchange charges or actual profitability. There is no passive-fill model.

Any unresolved/censored scheduled windows reject PnL computation. In particular,
the existing 5,213-row historical label diagnostic cannot become a backtest by
dropping its 308 censored windows or setting an unverified zero count. The outer
worker must derive coverage from independently checked materializer receipts.
This gate is not yet wired to a real task. Neither a hash-shaped fee source nor
a caller-provided zero is sufficient scientific admission.

Reports include modeled cash PnL, fees, turnover, entry notional, per-day/game
results, entry shortfall, and realized-only drawdown. Intrahorizon mark-to-market
drawdown remains unavailable. A trade with zero PnL counts as active; no trades
never count as learning success. After-midnight accounting does not manufacture
another evaluated session. Missing evaluation dates are rejected, not imputed.

Perfect-foresight diagnostics include an unconstrained positive sum, a non-overlap
bound and an exactly baseline-trade-count non-overlap bound. The interval solver
is tested against independent exhaustive enumeration. These bounds relax cash
and post-writeoff halts, and are NOT achievable strategies or researcher results.

274 local tests pass, including 24 new simulator tests. All use human-written
synthetic cases. No provider call, historical simulation score, trained model or
hidden-Test evaluation was added. Next: separate inspect execution and the actual
outer worker/data admission; capture provenance is still blocked externally.
