# First real Train diagnostic independent pre-score review — 2026-09-29

Verdict: **PASS — 0 P0 / 0 P1 on the post-`-01` schedule-date repair**

This is a pre-score review only. I did not execute the runner on the resident
2025 Train source, inspect any real prediction or score, open Route-Dev or
Final, access a network/provider, spend money, publish, promote, or modify the
runner/tests. I independently replayed only the focused synthetic suite after
the Supervisor requested it.

## Exact reviewed identity

- Runner:
  `research/market_rsi/experiments/nfl_settlement_probability_train_diagnostic.py`
  — SHA-256
  `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b`
- Tests:
  `research/market_rsi/tests/test_nfl_settlement_probability_train_diagnostic.py`
  — SHA-256
  `6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927`
- Domain inventory reviewed — SHA-256
  `9e70854151bad487322b1b76e4dcf48b64196b4ff7d7a90501b27db7420acbdc`
- Pipeline audit reviewed — SHA-256
  `3aabe20e98da1d994a8d36e611791bfb01bfba7a15f5b1ffb56fa4d0ae1cc375`
- Existing probability contract reviewed — SHA-256
  `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74`
- Existing proper scorer reviewed — SHA-256
  `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b`

Any runner or test change invalidates this verdict and requires a new review.

## Spec findings

The frozen design is internally coherent for a private Train-only diagnostic:

- The selected domain is the already-opened, persistent 195-event/42-date
  2025 NFL moneyline Train cohort. Selection was based on role, timestamps,
  breadth, local completeness and no-fetch readiness, not new scores.
- There is exactly one decision row per event at the scheduled start minus 15
  minutes. The market baseline is the size-weighted home-win probability over
  all trades at the latest eligible integer second. Post-cutoff trades are not
  admitted, and exact/near endpoint probabilities are rejected by the existing
  probability policy rather than clipped.
- Home/away orientation is exact, not fuzzy: the game ID proves away/home
  order, raw outcomes and token order must match the fixed alias vocabulary,
  and every trade's outcome index, token and outcome text must agree. The
  `LA -> LAR` normalization and both `LAR`/`Rams` aliases are explicit.
- The target is the selected market's exact binary settlement vector. Outcome
  availability is the maximum of the present selected-market `closedTime`,
  selected-market `umaEndDate`, and event `finishedTimestamp`; scheduled
  `endDate`, generic `updatedAt`, event `closedTime`, local capture time and all
  availability fields are excluded from features.
- The split is exactly the earliest 22 frozen cohort/catalog `game_date`
  schedule dates for the first fit, followed by four expanding checks of five
  schedule dates each. It does not substitute the cutoff's UTC calendar date.
  Whole events remain in one fold, and every fitted label must be available
  strictly before the first cutoff in its check fold.
- Logistic regression and HistGradientBoosting receive the identical causal
  feature rows, the same fold-fit `StandardScaler`, identical fit/check masks
  and equal event weight. The changed stage is therefore trainer-only.
- The existing probability contract and proper scorer enforce probability
  bounds, label chronology and exact prediction masks. Market, ordinary and
  candidate Brier/log loss and calibration are reported. Candidate versus
  ordinary is recomputed as a direct paired comparison on the same rows, not
  by subtracting separately bootstrapped interval endpoints.
- The frozen diagnostic rule is exact: KEEP only if candidate aggregate
  equal-event Brier is strictly below ordinary, candidate aggregate
  equal-event log loss is strictly below ordinary, and candidate Brier wins at
  least three of four folds; all other cases, including ties, REVERT. KEEP is
  only next-iteration Train retention, never promotion.

## Required factual correction to the inventory

The domain inventory says terminal scores have no ties and a binary target is
constructible for all 195 events. That statement is false for
`2025_04_GB_DAL`: the resident raw source records score `40-40` and selected
moneyline `outcomePrices=[0.5,0.5]`.

The repaired runner handles this correctly and does not coerce the target. The
production path fails closed unless the denominator remains 195, exactly 194
events materialize, and the sole exclusion is
`2025_04_GB_DAL / unresolved_outcome`. It also requires all 20 frozen OOF check
dates to remain. The inventory text should be corrected when Supervisor state
is next synchronized; this does not require changing the selected domain.

## Source findings and repairs closed during review

Two P1 findings were raised against the first implementation snapshot and were
repaired before the initial PASS:

1. The first source version admitted `event.closedTime` in target availability,
   beyond the frozen three-clock definition, and did not pin the definition in
   `pre_score_lock.json`. The reviewed source removes that field, records the
   exact rule in the pre-score lock, and tests that a later event close time is
   ignored.
2. The first direct candidate-versus-ordinary view relabeled event/date rows
   but left four nested paired summaries claiming a
   `candidate_minus_market` convention. The reviewed source deep-copies and
   relabels every nested summary to
   `candidate_minus_ordinary; negative loss is better`; focused assertions
   cover all four.

## Attempt `-01` pre-fit failure and scoped repair

The first real attempt root is:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-nfl-settlement-20260929-01`

It contains only `failure.json`, SHA-256
`5c9d51bbd7a2ac98300f0688970e2ddfb612ecf9c12ab73e38d59c4f4eac95f5`.
The recorded failure is:

```text
ValueError: exact 22-date fit plus four 5-date checks requires 42 dates
```

There is no pre-score lock, prediction file, scorecard or complete manifest in
the attempt root. The failure occurred before any model fit or score: the first
runner grouped by the cutoff's UTC calendar date, which expands the resident
cohort's 42 frozen schedule dates to 54 distinct UTC dates.

The reviewed repair is scoped to date identity:

- `DiagnosticRow.split_date` now uses the exact cohort `game_date` after the
  normalized catalog has been required to match it.
- The fold date list is built directly from those cohort dates, with canonical
  `YYYY-MM-DD` validation.
- `pre_score_lock.json` states that chronological grouping uses exact
  cohort/catalog schedule date and never cutoff UTC calendar date.
- A cross-UTC regression constructs an event whose schedule `game_date` differs
  from its cutoff UTC date and proves both materialization and fold selection
  use the schedule date.

Static comparison against the previously reviewed source confirms the causal
cutoff, feature definitions, same-second aggregation, target and availability
rules, LogisticRegression/HGB specifications, shared scaler, 195-to-194 exact
attrition, proper-scoring path, direct candidate-versus-ordinary comparison and
KEEP/REVERT rule are unchanged. The proper scorer's UTC-date diagnostics are
also unchanged; the repair affects chronological fold membership only.

The repaired source additionally records hashes for all 195 used catalog/trade
source-file groups and the runner itself before fitting. Input receipts,
exclusions and the complete pre-score lock are written before model fitting;
the manifest is written only after predictions and the scorecard are durable.

## Independent verification

Focused synthetic replay:

```text
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' \
  -B -m unittest \
  research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic
.........
Ran 9 tests in 0.215s
OK
```

The suite covers exact LAR/Rams orientation, ambiguity rejection,
same-second aggregation, post-cutoff rejection, endpoint rejection, exact
outcome availability, tie rejection, 22 + 4x5 folds, exact KEEP/REVERT,
production attrition, denominator/source receipts, identical masks, direct
paired candidate-versus-ordinary semantics, deterministic replay, fresh
output refusal, the cross-UTC schedule-date regression and a socket network
trap.

`git diff --check` passed on the runner and focused test. The two SHA-256
values recomputed after the replay exactly match the reviewed identities
above.

## Residual claim boundary

PASS authorizes only the already-approved single private diagnostic execution
on the bound opened Train root under a fresh persistent local output ID. It is
not evidence that the candidate wins, that the data is formally admitted, or
that the result is untouched OOS. It grants no Dev/Final read, fetch, paid
provider, retry, publication, promotion, deployment, release or PnL claim.
