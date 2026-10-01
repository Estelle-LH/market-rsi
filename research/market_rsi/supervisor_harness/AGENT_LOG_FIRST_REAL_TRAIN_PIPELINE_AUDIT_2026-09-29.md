# First real Train diagnostic pipeline audit — 2026-09-29

Status: **AUDIT COMPLETE; ONE THIN REAL-TRAIN RUNNER IS MISSING**

This was a code-path and resident-input audit only. I did not run a model fit,
score a prediction, open Route-Dev/Audit-Dev/Final, use a provider or network,
fetch data, run a canary, publish, or change protected state. Historical result
artifacts are not treated as current evidence or as a reusable baseline.

## Ex-ante domain choice

Use the already-opened, durable local **2025 NFL Train** cohort for the first
diagnostic:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01`

This choice is made before opening any new score and only from readiness:

- it is an explicitly frozen Train cohort with 195 events on 42 dates;
- the cohort ends before the separately defined Route-Dev and Final dates;
- all files are in a persistent, non-cloud, non-temporary local root;
- each event already has a hashed Gamma catalog snapshot, a unique two-token
  moneyline identity, a historical trade tape and an event start timestamp;
- the raw catalog schema contains the two outcomes, token IDs, settlement
  prices and close timestamps needed for a binary outcome;
- the source audit reports `dev_final_opened=false`, `model_fits=0`, and zero
  provider cost, and can be rerun offline;
- it has enough event/date breadth for chronological Train diagnostics without
  fetching anything.

The 2024 cohort is larger, but its current artifact is a source/candidate
ledger rather than the already-frozen 2025 Train role. Choosing 2025 minimizes
new role and population logic. Rights, trade-not-quote semantics and historical
provider-clock caveats remain and prevent promotion, but do not block the
user-authorized private Train diagnostic.

## What is executable now

### Resident input and source verification

- `nfl-2025-train-refresh-20260922-01/audit.py` verifies the exact 195-game
  population, source hashes, unique condition/token identities, raw pagination,
  reconstructed fixed-window trade CSVs and the Train/Dev/Final boundary.
- The safe trade schema is
  `side,token_id,condition_id,size,price,timestamp,event_slug,outcome,outcome_index,transaction_hash`.
- `sports_event_research/build_play_trade_canary.py` already contains the
  conservative NFL team-name aliases and a fail-closed home-token orientation
  pattern. Its play-response target is not reused.

### Chronological model pattern

- `sports_event_research/run_train_method_screen.py` is a working example of
  fold-fit preprocessing, expanding whole-game folds, equal-game weighting,
  deterministic scikit-learn estimators and date-block reporting.
- `learner.py` is a small local logistic probability learner, but lacks feature
  selection, event/date weighting and the desired rolling orchestration.
- `sports_event_research/run_state_surprise_discovery.py` confirms the local
  scikit-learn logistic-probability pattern.

These are implementation patterns only. The existing NFL runners require an
older 163-game panel and predict `home_change_60s`; they produce MSE, not
settlement-probability Brier/log loss. Their historical scores and models must
not be relabelled as the current baseline.

### Probability contract and scoring

- `minimal_prediction_loop/probability_contract.py` already enforces exact
  settlement row schemas, whole-event split isolation, availability ordering,
  probability bounds and identical prediction keys.
- `minimal_prediction_loop/proper_scoring.py` already computes equal-event and
  row-weighted Brier/log loss, calibration slope/intercept, reliability,
  complete-mask checks, event/date breadth, concentration, paired event/date
  deltas and block intervals against the decision-time market probability.
- The scorer is arithmetic only. Its `coverage=1` means complete coverage of
  the rows handed to it, not coverage of all 195 source events. The real runner
  must separately preserve the full population denominator and exclusion
  reasons.

## Shortest defensible first experiment

Use one fixed pregame cutoff per event. A conservative default is 15 minutes
before the catalog `event_start_utc`; freeze it before inspecting coverage or
scores. For each event:

1. Verify the selected raw moneyline market, its two outcomes and token order.
2. Orient every trade to home-win probability. Never infer orientation only
   from sorted token IDs; validate outcome text against the existing NFL alias
   table.
3. Use only trades with `timestamp <= cutoff`. At the latest eligible second,
   combine all same-second trades deterministically (prefer size-weighted
   home-oriented price) rather than inventing sub-second order.
4. Freeze the decision-time market baseline from that value. Reject, rather
   than clip, invalid endpoint probabilities under the existing probability
   policy.
5. Derive only cutoff-causal pregame features, such as market logit, staleness,
   fixed-window trade count/volume, price drift and dispersion. Every window
   ends at the cutoff.
6. Derive the binary settlement label from the selected raw market's paired
   `outcomes`/`outcomePrices`, accept only an unambiguous 0/1 resolution, and
   use a conservative source close/finished timestamp as
   `outcome_available_ms`. Ties, ambiguous resolution, absent baseline, stale
   market or invalid probability receive explicit exclusion codes; do not
   impute.

Recommended outer diagnostic split: group by UTC game date, use the earliest
22 dates for the first fit, then four expanding checks of five dates each.
This consumes all 42 Train dates, yields 20 diagnostic check dates and keeps an
event/date wholly on one side of each boundary. Before every fold, call
`validate_train_evaluation_rows` so all fit labels must be available strictly
before the first check cutoff.

For the first fixed trainer-only A/B, a minimal reproducible pair is:

- ordinary baseline: regularized `LogisticRegression(C=1.0, solver="lbfgs",
  max_iter=500, random_state=23)`;
- candidate: `HistGradientBoostingClassifier(max_iter=150,
  learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
  l2_regularization=1.0, early_stopping=False, random_state=23)`;
- both receive the identical frozen feature matrix, fit rows, check rows and
  event weights; only the prediction trainer changes.

This is an executable first comparison, not proof that the logistic model is
already a strong baseline. No existing settlement-probability baseline has
been validated on these rows. If the supervisor requires a best-of-library
`Strong-Baseline-1`, select it in an earlier nested Train window and freeze it
before the candidate comparison; do not pick it on the same outer check rows.
The Controller may replace the proposed candidate before scores are opened,
but must declare one changed causal stage and freeze its spec first.

Run the existing proper scorer three ways on the exact same materialized check
mask:

1. ordinary baseline versus decision-time market;
2. candidate versus decision-time market;
3. candidate versus ordinary baseline.

The third comparison needs a small generic reference-forecast wrapper (or a
generalized scorer argument). Do not subtract independently bootstrapped
interval endpoints. Recompute event/date paired candidate-minus-reference
losses and their intervals on the common rows.

## Minimal missing implementation

There is no current end-to-end executable for this exact task. The narrowest
addition is one offline runner plus focused tests, for example:

`experiments/nfl_settlement_probability_train_diagnostic.py`

It should:

- re-run or call the resident source-verification checks without network;
- materialize the 195-event denominator, complete rows and exclusion ledger;
- freeze cutoff, feature, fold and model specs before scoring;
- fit the two classifiers in the expanding Train folds;
- assert identical rows for market, ordinary and candidate predictions;
- call the existing probability contract and proper scorer;
- add direct candidate-minus-ordinary paired event/date summaries;
- emit input hashes, per-fold predictions, a scorecard and diagnostic
  KEEP/REVERT; and
- write only beneath a new persistent local directory under
  `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts`,
  never a cloud or temporary path.

Focused synthetic tests should cover orientation, same-second aggregation,
cutoff leakage, outcome availability, endpoint rejection, whole-event/date
fold isolation, full-population coverage accounting, identical masks and all
three paired comparisons. Tests may use temporary synthetic fixtures; the real
artifact may not.

## Runtime and proposed command shape

Verified local persistent runtime:

- Python `3.12.3` at
  `/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`
- NumPy `1.26.4`
- SciPy `1.14.0`
- scikit-learn `1.6.1`
- pandas is not installed and is not required; use the standard `csv`, `json`
  and `gzip` modules already used by the source audit.

Required imports for the probability contract, scorer,
`LogisticRegression`, and `HistGradientBoostingClassifier` succeed in this
runtime. Once the missing runner and tests exist, the intended zero-network
command shape is:

```text
PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B \
  /Users/estelle/Developer/market-rsi/research/market_rsi/experiments/nfl_settlement_probability_train_diagnostic.py \
  --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' \
  --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-<fresh-id>'
```

Do not run that command until the runner exists, its synthetic tests pass, the
cutoff/model spec is frozen and a fresh output ID is chosen. This diagnostic
still cannot read protected splits, support promotion, or become formal OOS
evidence.

## Decision for the supervisor

The blocker is no longer data access, Docker, canary, provider budget or a
general governance layer. It is a bounded code gap: **one offline 2025 NFL
settlement-probability materializer/rolling classifier runner and direct
candidate-versus-ordinary paired scorer**. Implementing that is the shortest
path to the first real Train scorecard.
