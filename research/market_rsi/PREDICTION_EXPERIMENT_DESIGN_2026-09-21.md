# Prediction experiment v1 — design draft

## Research question

Using exactly the same admitted market data, target, rows, evaluation rules and
total dollar budget, can a recursively improving LLM researcher produce a
forecasting model that beats a strong ordinary model on untouched NFL
prediction-market dates?

This is a prediction experiment. It is not a trading-PnL claim yet.

## What changes

Only the **prediction search policy** changes:

- ordinary arm: a fixed Train-only search selects the strongest baseline;
- RSI arm: GLM Controller proposes research and prediction changes, researchers
  implement one bounded candidate at a time, and the Codex Supervisor checks
  provenance, budget, data boundaries and failures.

Both arms must use the same admitted rows, selected target, chronological
splits, latency assumptions and scorer. A trial may change one prediction
component at a time. It cannot change data, target or Final to rescue a score.

## Data gaps are part of the research loop

The RSI loop starts **before** model fitting. A failed data-admission check is
an observation for the Controller, not an instruction for the human Supervisor
to quietly choose a replacement dataset. Each data-research cycle is:

1. The independent auditor reports the exact gap and denominator (for example,
   unmatched games, missing real fills, unusable event clocks, rights unknown,
   or too few untouched dates), with source and access-history hashes. It does
   not expose sealed outcomes or row-level Dev/Final labels.
2. The Controller chooses the next hypothesis and a bounded investigation. It
   may propose a new lawful source, matching method, sampling method, or a
   separately versioned target/market research question; it is not limited to
   a permanently fixed menu. A novel source or tool proposal is **not** an
   executable permission. The trusted broker must review its rights, scope,
   endpoint, bytes, time, cost, and isolation before any researcher uses it.
3. The researcher runs only the admitted bounded task and saves raw receipts,
   code, errors, source versions and hashes. It may not purchase data, access
   sealed splits, or change protected scoring rules on its own.
4. An independent auditor recomputes mapping, actual-trade/quote semantics,
   event ordering, label coverage by game/date, exclusions and rights. The
   Supervisor records pass/fail and budget, then returns the factual result to
   the Controller for its next decision.

This loop can improve the *usable evidence* before it improves forecasts.
Track scheduled games, matched markets, games with verified executable-source
observations, valid labels, eligible dates, missingness by week, acquisition
cost, and independent recheck status. Increased row count alone is not a win.
Never fabricate absent trades, treat carried-forward minute prices as fills,
move inspected dates into Final, or change the target after seeing Dev. If a
source cannot close the gap within a predeclared bound, archive the negative
result and let the Controller choose a different investigation; if no lawful
and affordable source can support the current claim, report that scope change
to the user rather than silently weakening the benchmark.

The current live Gate 1 contract still offers only a small fixed source and
question registry. Its successful synthetic plan canary therefore **does not**
yet demonstrate this open-ended gap-resolution loop. Extending proposal
capture, trusted capability review, and result-to-next-input feedback is a
specific implementation requirement, not an achieved result.

## Data gate before any model fit

The experiment is blocked until a formal admission receipt proves:

- at least three completed seasons for the minimum viable experiment, with
  five completed seasons as the target;
- exact source identities, versions and hashes;
- research-use rights;
- verified game-to-market mappings;
- whether prices are actual trades or executable quotes;
- immutable event ordering and event-time alignment;
- label coverage by game and date;
- evidence-backed exclusions, with no missing-label imputation.

Previously opened 2024/2025 periods remain diagnostic only and cannot support
the final promotion claim.

## Target selection

The target is not selected yet because the data gate is still closed. After
admission, only opened Train may compare the predeclared candidates:

- future trade-price change after 60 seconds;
- future trade-price change after 300 seconds;
- future executable-quote change, only if quote semantics are verified.

Selection must measure coverage, zero-change rate, event latency, maximum mark
lateness, horizon decay, and perfect-foresight opportunity after costs. Dev is
not visible during target selection. Once selected, the target and label code
are hashed before any Dev result is opened.

## Chronological split

After data admission, the materializer must create non-overlapping manifests:

1. Train: model fitting, target selection and ordinary-baseline selection.
2. Route-Dev: aggregate feedback for RSI round selection; no row-level labels
   are returned to Controller.
3. Audit-Dev: one use after a final candidate is locked.
4. Final: at least 20 untouched dates, sealed until every candidate, baseline,
   target, cost, row and scorer hash is locked.

## Strong ordinary baseline

The Train-only library starts with zero change, persistence, Ridge and HGB. A
verified CatBoost or LightGBM implementation may be included under the same
fixed search budget. The best Train-only method becomes `Strong-Baseline-1`.
Its code, parameters and predictions are frozen before the RSI result is
compared on untouched dates.

## RSI candidate

The current roles are:

- Supervisor: Codex GPT-5.6 Sol; owns global state, gates and failure recovery.
- Controller: Tinker GLM-5.3; chooses the next scientific investigation or
  prediction trial from allowed information.
- Researchers: implement literature checks, features, representations,
  trainers, losses, ablations and new algorithm proposals.

The Controller receives Train evidence and aggregate Route-Dev feedback. It
does not receive sealed rows, per-row Dev labels or Final results. Every trial,
including failures, is archived. The ordinary and RSI arms receive the same
total dollar budget; tokens and wall time are also reported.

## Metrics and pass condition

Primary result: candidate minus strong-baseline equal-game MSE on Final.

Also report probability-point RMSE, Pearson/rank IC, calibration slope and
intercept, label coverage, positive-game/date fractions, and a paired
date-block 95% interval.

Promotion requires all of the following:

- at least 20 untouched Final dates;
- candidate MSE below the strong baseline;
- upper endpoint of the paired MSE interval below zero;
- coverage gate passed;
- calibration not worse;
- no Final-based tuning or retry.

## Current status

This is a machine-checked draft, not execution authority. Data admission,
target, split manifests, strong baseline and formal run budget are deliberately
unset. No new model fit, Dev access, Final access or paid experiment is allowed
from this document.
