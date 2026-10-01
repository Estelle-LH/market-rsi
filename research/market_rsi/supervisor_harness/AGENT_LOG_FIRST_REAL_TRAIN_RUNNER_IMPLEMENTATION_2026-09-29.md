# First real Train diagnostic runner implementation — 2026-09-29

Status: **IMPLEMENTATION REPAIRED; SYNTHETIC TESTS PASS; NO MODEL FIT OR SCORE**

## Scope and boundary

I implemented only the assigned offline runner and focused synthetic tests. I
did not execute the runner against the resident 2025 Train root, inspect any
real model score, read Route-Dev or Final, use a network/provider, spend money,
publish, promote, or edit Supervisor state/index files. The Supervisor later
launched real attempt `first-real-train-diagnostic-nfl-settlement-20260929-01`.
It failed closed before model fitting or scoring because the initial runner
derived fold dates from cutoff UTC dates: the frozen 42 schedule `game_date`
values became 54 UTC cutoff dates. No prediction or score resulted from that
attempt.

Observed problem: the repository had no end-to-end one-row-per-event
settlement-probability runner for the frozen resident 2025 NFL Train source.
Changed component: prediction-stage trainer A/B only. The ordinary logistic
regression and HistGradientBoosting candidate share the exact same causal
features, fold-fit StandardScaler, fit rows and check rows.

## Research record reused

No new live literature search was needed for this bounded implementation. I
reused the already-reviewed local evaluation rules in
`indicator-prediction-evals/SKILL.md`, its `evaluation-gates.md`, the existing
strict probability contract/proper scorer, the reviewed NFL alias vocabulary,
and the pre-score design frozen by the Supervisor. Their applicability was
checked for this task: one changed prediction stage, past-only fold fitting,
whole-date splits, identical masks, Brier/log loss/calibration, full source
denominator, and a Train-only inference boundary.

The older NFL experiment runners were not reused as evidence because they
predict short-horizon market-price change and report MSE. A new narrow runner
was required for binary settlement probability and proper scoring. Logistic
regression remains the fixed ordinary baseline; the only candidate is the
predeclared HistGradientBoosting classifier. No method search, tuning, or
winner substitution is present.

## Implemented files

- `research/market_rsi/experiments/nfl_settlement_probability_train_diagnostic.py`
  - SHA-256: `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b`
- `research/market_rsi/tests/test_nfl_settlement_probability_train_diagnostic.py`
  - SHA-256: `6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927`
- `research/market_rsi/supervisor_harness/AGENT_LOG_FIRST_REAL_TRAIN_RUNNER_IMPLEMENTATION_2026-09-29.md`
  - This implementation log; its final hash is reported to the Supervisor
    after writing rather than embedded recursively.

No other file was edited by this worker.

## Frozen behavior implemented

- Exact production source binding to the persistent resident Train root and
  its frozen manifest/cohort hashes; output must be a fresh child of the
  persistent local MarketRSI artifacts root.
- One row per event at `event_start_utc - 15 minutes`; all feature trades are
  constrained to `timestamp <= cutoff`.
- Exact NFL aliases, including `LA -> LAR` and `Rams -> LAR`; raw outcome,
  token and every trade's outcome-index/token pair must agree.
- Latest-second market baseline is the size-weighted home-win probability
  across every trade at that integer second. Invalid endpoint baselines are
  excluded, never clipped.
- Fixed feature matrix: market logit, staleness, and count/size/weighted
  mean/weighted standard deviation/last-minus-first drift for 15m, 60m and
  240m trailing windows. Empty windows are excluded without imputation.
- Target comes only from the selected raw moneyline's exact resolved
  `[0,1]`/`[1,0]` `outcomePrices`. Outcome availability is frozen as the
  maximum of present selected-market `closedTime`, selected-market
  `umaEndDate`, and event `finishedTimestamp`; no other clock is admitted.
- Production fails closed unless the 195-event denominator yields exactly 194
  materialized events, with the sole exclusion
  `2025_04_GB_DAL / unresolved_outcome` for raw `[0.5,0.5]`, and all 20 OOF
  check dates remain.
- Earliest 22 exact cohort/catalog `game_date` values form the initial fit;
  four expanding folds each check exactly five later schedule dates. A whole
  schedule date remains in one fold even when its UTC cutoff falls on another
  calendar date. The grouping rule is explicit in `pre_score_lock.json`. Fit
  rows require outcome availability strictly before the first check cutoff.
- Fixed LogisticRegression and HistGradientBoostingClassifier definitions are
  hashed in `pre_score_lock.json`; both consume the identical fold-standardized
  matrices.
- Proper scoring reports market, ordinary and candidate Brier/log loss and
  calibration. Candidate-minus-ordinary is computed directly by binding
  ordinary predictions as the trusted scorer reference, then explicitly
  relabeling event/date paired evidence and every nested paired-summary delta
  convention on a deep copy.
- KEEP is diagnostic only and requires all three frozen conditions: aggregate
  candidate Brier below ordinary, aggregate candidate log loss below ordinary,
  and candidate Brier wins in at least three of four folds. Ties REVERT.
- All 195 source-file hashes are preserved even though one target is excluded.
  `input_receipts`, `exclusions` and `pre_score_lock` are written before any
  fit. Predictions and scorecard follow; the complete manifest is written
  atomically last. Failure artifacts retain the no-Dev/Final/no-provider
  boundary.

## Verification performed

Focused synthetic test command:

```text
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B -m unittest research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic
```

Result: `Ran 9 tests in 0.214s` / `OK`.

The tests cover exact LAR/Rams orientation and ambiguity rejection;
same-second size weighting; post-cutoff leakage exclusion; endpoint rejection;
maximum outcome-availability clock; `[0.5,0.5]` tie rejection; exact 22 +
4x5 date folds; exact KEEP/REVERT behavior; exact real-cohort attrition rule;
full denominator reconciliation; all-source hashes; identical scoring masks;
direct candidate-minus-ordinary evidence; deterministic repeated synthetic
runs; fresh-output refusal; a regression where the event's UTC cutoff date
differs from frozen `game_date` while grouping remains on `game_date`; and a
socket trap proving the synthetic runner path does not invoke network access.

Static commands:

```text
PYTHONPYCACHEPREFIX=/private/tmp/market-rsi-train-diagnostic-pycache '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -m py_compile research/market_rsi/experiments/nfl_settlement_probability_train_diagnostic.py research/market_rsi/tests/test_nfl_settlement_probability_train_diagnostic.py
git diff --check -- research/market_rsi/experiments/nfl_settlement_probability_train_diagnostic.py research/market_rsi/tests/test_nfl_settlement_probability_train_diagnostic.py
```

Result: both passed with no output.

## Real-run command shape — not executed

```text
PYTHONPATH=/Users/estelle/Developer/market-rsi/research/market_rsi \
  '/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python' -B \
  /Users/estelle/Developer/market-rsi/research/market_rsi/experiments/nfl_settlement_probability_train_diagnostic.py \
  --source-root '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01' \
  --output '/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/first-real-train-diagnostic-<fresh-id>'
```

The command above is documentary only. No real output directory was selected
or created by this worker, and no real prediction/score was opened.

## Remaining handoff

Independent review must finish against the current source hashes. If it passes,
the Supervisor—not this worker—may choose the fresh persistent output ID and
execute the single authorized Train diagnostic. The resulting score remains
opened-Train diagnostic evidence and cannot support promotion or publication.
