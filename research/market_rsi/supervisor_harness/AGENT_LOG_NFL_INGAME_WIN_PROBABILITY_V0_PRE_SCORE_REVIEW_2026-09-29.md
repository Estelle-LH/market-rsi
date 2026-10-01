# `InGameWinProbabilityTrainDiagnostic-v0` independent pre-score review — 2026-09-29

Review time: `2026-09-29T20:38:25Z`

Verdict: **PASS for one historical, repeatedly inspected, opened-2025-Train diagnostic only.** The reviewed bytes may proceed to a separately controlled score run. This PASS does not establish real-time PBP availability, executable market prices, untouched OOS evidence, Dev/Final evidence, promotion, PnL, publication or deployment.

No real model fit, prediction, or score was produced or viewed during this review. No Dev/Final path, network, provider, credential or paid service was accessed. The only real-data action was a local preflight over the already-opened Train receipts and checkpoint rows; it did not call `_fit_and_predict`, `_aggregate`, a scorer, or `run()`.

## Exact reviewed snapshot

| File/evidence | SHA-256 |
| --- | --- |
| `experiments/nfl_ingame_win_probability_train_diagnostic.py` | `e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7` |
| `experiments/extract_nfl_ingame_checkpoint.R` | `37a26997406de0e54bd9d91de10e7417a8b340c68b675892c4f16e9a51675163` |
| `experiments/test_nfl_ingame_win_probability_train_diagnostic.py` | `6198546e99467ec22d45db42ec609199c7a7b8c21cf07c609b216f8b8d3fb29d` |
| frozen data audit/design | `ac68542d41c2e8b4f1387a7ed51e64f683b16cb33707efba41ffe4c43a23fd86` |
| inherited settlement runner | `1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b` |
| probability contract | `7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74` |
| proper-scoring implementation | `64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b` |
| opened-Train `manifest.json` commitment | `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f` |
| opened-Train `cohort.csv` commitment | `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885` |

The runner writes its own source hash, extractor hash, settlement dependency hash, probability-contract hash and proper-scoring dependency hash into `input_receipts.json`; it also binds the exact source manifest/cohort, every PBP receipt, extracted checkpoint state and every materialized receipt.

## Findings by required gate

### 1. Fixed denominator and common population — PASS

- Production source is hard-bound to 195 games on 42 schedule dates.
- The extractor always emits one status row for every one of the 195 unique cohort game IDs.
- Production execution requires exactly 193 materialized games and exactly these two exclusions in cohort order:
  - `2025_04_GB_DAL`: `unresolved_outcome`;
  - `2025_05_TEN_ARI`: `market_trade_too_stale`.
- Any additional, missing, reordered or differently coded exclusion rejects before fitting.
- One materialized `InGameRow` object supplies the raw-market, market-only LR and market-plus-state LR arms, so their check checkpoint, label and row mask are the same by construction. Prediction keys are unique across folds.
- The real-data preflight independently reproduced 195 extracted rows, 193 materialized rows and the exact two exclusions without fitting or scoring.

### 2. Outcome-independent Q3 anchor and causal score — PASS

Anchor selection uses only a nondeleted play's quarter, game clock, pre-play down/distance/yard line/possession completeness and `orderSequence`. It selects the minimum causal order satisfying Q3 and `clockTime <= 08:00`. Price, settlement target, current score and play outcome do not choose the anchor.

The source audit found 19/195 selected anchors that are themselves scoring plays. The extractor reconstructs score only from scoring summaries whose effective completion order is strictly lower than the anchor order. Effective completion is the maximum of a scoring play's and PAT/two-point play's `orderSequence` when a PAT exists. Equality is excluded, so a field goal or scoring anchor cannot contribute its own result; a touchdown whose PAT follows the anchor is also excluded.

The actual preflight exercises `2025_01_BAL_BUF`, whose anchor play ID `2394` is a BUF touchdown: the extractor returns the strictly prior score differential `13-27 = -14`, not the current scoring play's `19-27 = -8` result. The generalized comparison is `completed_order < decision_order`.

Play IDs must be nonempty and globally unique; all orders must be finite. Order uniqueness is enforced only on the causal identity domain—nondeleted timed typed plays plus scoring/PAT identities—so two deleted/administrative `UNSPECIFIED` order-zero rows do not erase valid games. This distinction was materially tested during review: an interim over-broad global-order uniqueness check reduced eligibility to 132 and caused a 9/10 suite failure; the final repaired snapshot restores the exact 195/193 preflight.

### 3. Same-second trades and 300-second staleness — PASS

- Trade timestamps have only integer-second resolution. For a PBP event timestamp `t`, the runner uses `floor(t)-1` as the latest permitted trade second, excluding the whole event second.
- At the latest admissible second, all home-oriented fills are combined by size-weighted probability; later rows cannot enter.
- Staleness uses the fractional PBP event timestamp minus the latest integer trade timestamp. Exactly `300.000` seconds is admitted; `300.001` is rejected. Negative age also rejects.
- Focused tests cover exclusion of an event-second trade and both staleness boundary sides.

### 4. Frozen three-arm comparison and trainer budget — PASS

The three arms are:

1. raw latest strictly prior home-win market probability;
2. L2 logistic regression on only its decision-time market logit;
3. the same logistic regression on that same market logit plus the frozen pre-play state whitelist.

The state whitelist is: prior home-score differential, regulation seconds remaining, home-possession indicator, four down one-hot columns, yards to go, and home-oriented field-position advantage. It excludes `goalToGo`, score-time interactions, current-play results, future plays, terminal score and final outcome. The R CSV retains some unused audit columns, but only `STATE_FEATURE_NAMES` can enter the state matrix.

Both fitted arms use the exact same `LogisticRegression` configuration: L2, `C=1.0`, `lbfgs`, intercept, `max_iter=1000`, `tol=1e-10`. Only continuous columns are standardized on each fold's fit rows; possession and down indicators remain unscaled. A `ConvergenceWarning` is promoted to an exception, and reaching the iteration ceiling also rejects. The different feature width is the intended information-set change; family, hyperparameters, fold rows, labels and iteration/tolerance budget are held fixed.

### 5. No future play, terminal score or false time claim — PASS with permanent boundary

- The feature whitelist does not expose play result, descriptions, play stats, later play/drive aggregates, scoring flags, terminal totals or final outcome.
- The settlement target is read only as a trusted label and paired with a conservative source-resolution availability timestamp. It cannot enter the feature matrices.
- Fit labels are admitted only when `outcome_available_ms` is strictly earlier than the first check cutoff. Every fold persists the omitted game IDs and their canonical hash; production additionally requires the exact frozen run to have no label-unavailable prior-date games.
- `timeOfDay` is explicitly classified as `historical_event_clock_only`. The internal `feature_available_ms=cutoff_ms` field is only the structural event-clock proxy needed by the probability-row contract; it is not a provider-publish or local-receive observation. The pre-score lock, per-row receipt, scorecard inference boundary and terminal manifest all preserve that limitation. No real-time or latency claim may be derived from this run.

### 6. Folds and inference — PASS

- The inherited checked fold constructor requires exactly 42 unique schedule dates: 22 initial fit dates followed by four disjoint five-date chronological checks, with expanding prior-date fits.
- Production execution additionally requires 106 first-fold fit games, check-fold counts `[26, 16, 28, 17]`, no fit-label-unavailable games, and therefore 87 unique checked games.
- Primary scoring is pooled equal-event Brier; equal-event log loss and calibration slope/intercept plus a ten-bin reliability table are also retained.
- Paired loss differences are emitted by event and schedule date. The bootstrap resamples complete schedule dates and, separately, observed game weeks, then recomputes the pooled equal-event mean in each draw. It is fixed at 10,000 draws and seed `20260929`.
- Game-week inference remains a low-breadth sensitivity, not promotion evidence. All dates are repeatedly inspected opened Train.

### 7. Protected, external and persistence boundaries — PASS

- The production CLI accepts only the exact opened-Train source root; its manifest and cohort hashes are fixed.
- The implementation contains no fetch/provider path. It reads only local catalog, PBP and trade receipts. Artifacts mark Route-Dev/Final, external fetch, paid provider and promotion as false/zero.
- Output must be a fresh path below the persistent local MarketRSI artifact root; source-root, temporary and cloud-looking output paths reject.
- Pre-score lock, input receipts, exclusions, predictions and scorecard are written before a terminal hash manifest. A failure before manifest creation leaves an explicit local failure record.

## Test and static-check evidence

Final focused command:

```text
PYTHONPATH=research/market_rsi \
  /Users/estelle/.cache/market-rsi/runtimes/ds-py312-20260912-01/bin/python \
  -m unittest -v experiments.test_nfl_ingame_win_probability_train_diagnostic
```

Result on the exact hashes above: **10/10 PASS in 4.040 seconds**. Coverage includes exact local 195/193 preflight and scoring-anchor prior-score behavior, same-second/staleness boundaries, state whitelist/down one-hot encoding, continuous-only scaling, optimizer failure, label-availability recording, common masks, grouped equal-event resampling, decision rule and persistent-path rejection.

The Python runner and test pass `py_compile` using a private temporary bytecode cache and pass `tabnanny`. The R extractor passes parse-only `Rscript` validation. These checks created no result directory and no score artifact.

## Final authorization boundary

**PASS only to run the exact reviewed bytes once as the named historical opened-Train diagnostic under the existing Supervisor boundary.** The result must still receive an independent result review before it can guide the next Discovery question. It may not be presented as a real-time edge, untouched OOS improvement, Dev/Final evidence, KEEP for the pregame task, promotion, PnL or deployment evidence. A future live claim requires separately captured provider-publish and local-receive timestamps; this historical experiment cannot close that gate regardless of its score.
