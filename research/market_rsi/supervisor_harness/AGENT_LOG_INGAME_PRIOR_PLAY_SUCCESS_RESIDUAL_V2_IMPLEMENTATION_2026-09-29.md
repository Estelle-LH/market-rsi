# In-game prior-play success residual audit v2 — implementation — 2026-09-29

## Status

Implemented scheduler-v2 batch `market-rsi-ingame-discovery-v3-20260929-02`
attempt `attempt-01`, candidate `InGamePriorPlaySuccessResidualAudit-v2`.
No real audit was executed and scheduler state was not changed.  Frozen v0,
v1, support-geometry, scheduler and prior experiment files were not modified.

Controller source:
`AGENT_LOG_INGAME_DISCOVERY_V3_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md`,
SHA-256
`a2c1c060b3ddf63ee3c0e1b6f7baebdba08b550c91be0a7d5585ead9b5dac18f`.

Frozen identifiers:

- question ID: `ingame-prior-play-success-residual-v2-q1`;
- question digest:
  `402ccc0147784eedf540918028d297b2d645d9f374e515bf403e9930682e14f5`;
- hypothesis digest:
  `53f74d1204bf3c991b68f01455ca4234d86dcd832c01fe7f512970587291b5c3`;
- decision-rule digest:
  `96c92f3ce51d779412e3953392eb037c2190ef0522fc8454a4f4f6701424b40e`;
- pool-plan digest:
  `415c47dd6f8a6ca99df78a03f102256ba981923b8bfb0992a8f6aea02b87e0a8`.

## Scheduler branch binding

The runner records the exact attempt-01 branch binding, including exploration
allocation, `prior_play_success_residual_audit` method family, Controller,
question, hypothesis and rule hashes, archived v0 research parent, task-local
raw-market comparison incumbent and non-authoritative resource hint.  Its
canonical digest is
`5c9bb22d34b1e950883c2396d653451990f940d4d2fe4cf78bff55a55e64996f`.

The selection evidence observed before implementation was:

- batch snapshot:
  `359fb5e57814a745bb81e265db0fe400fcee3cb4ba169d2882ebb0fce8c113ca`;
- state:
  `d40e848bfceabeeb47915f1cc0d9e2ee4f1a71653818d2054c494b707d6d4f93`;
- journal head:
  `ebc3225a811e7cc12b130b12366ac0f6a2e4f723d44e7cfb7bd54a1cc319130d`.

These selection digests are recorded as immutable provenance; the runner does
not require the live batch snapshot to remain unchanged after the Supervisor
later binds implementation/review evidence.

## New files

- `research/market_rsi/experiments/extract_nfl_prior_play_success.R`
- `research/market_rsi/experiments/nfl_ingame_prior_play_success_residual_audit.py`
- `research/market_rsi/experiments/test_nfl_ingame_prior_play_success_residual_audit.py`

Final source hashes:

- R extractor:
  `fe3e4096f80ea37a8074fc6e404b659474aa4c9e7586367cc218fb50e1650bea`;
- Python runner:
  `a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`;
- tests:
  `4820e1366684b23a0ca94f238fc84d599980e0708e7760d76bc4c89dd4cdc514`.

## Implemented data-time boundary

The R extractor receives the exact frozen v0 anchor CSV.  It verifies each
game's anchor play ID and `orderSequence`, then subsets plays by
`orderSequence < anchor_order` before reading any eligibility feature.  The
anchor and later plays therefore cannot contribute play type, time, down,
yards, yards-to-go, deletion or possession fields.

An eligible prior play is exactly:

- nondeleted;
- has a parseable event time;
- has a nonempty type other than `UNSPECIFIED`;
- has down exactly 1 through 4;
- has finite `yards` and `yardsToGo`;
- possession abbreviation equals the exact home or away team;
- has causal order strictly below the anchor.

The frozen success thresholds are implemented without change: 45% of needed
yards on first down, 60% on second down, and 100% on third/fourth down.  The
signal is home success rate minus away success rate.  A missing eligible side
is an integrity failure; no value is imputed and no row is removed.

The extractor preserves all 195 source games.  The Python runner requires
every one of the 193 v0 materialized games to have a valid two-sided signal,
preserves the same two named exclusions and scores exactly the frozen 87 check
games.  V0 manifest, pre-score lock, input receipts, exclusions, anchors,
predictions and scorecard are all exact-hash bound.  The opened source
manifest/cohort and all 195 PBP RDS receipt hashes must also reproduce the v0
input receipt set.

## Frozen analysis

For each exact check game the runner computes:

- market residual `y - p_raw`;
- log-loss directional alignment `s * (y - p_raw)`;
- Brier-logit directional alignment
  `s * (y - p_raw) * p_raw * (1 - p_raw)`.

It reports aggregate and all four fold Pearson/Spearman associations and both
alignment means.  It additionally reports fold date/week breadth and performs
10,000 complete schedule-date plus 10,000 complete game-week bootstrap draws
for each directional alignment using seed `20260929`; every draw recomputes
the pooled equal-event mean.

Support/refute/inconclusive conditions are copied exactly from the Controller
record.  The runner emits no probability candidate, performs zero prediction
fits, has no KEEP/REVERT path and cannot change the incumbent.  A valid result
only reports possible research-credit eligibility pending independent review.

## Alternatives and research-source handling

No new scientific method was selected during implementation.  The exact raw
indicator, thresholds, correlations, alignment metrics, grouped resampling and
decision rule were already frozen by the Controller.  Accordingly no live
literature search was used to change the recipe.  The implementation labels
the success rule as a project-frozen diagnostic rather than literature
consensus.  Other sequence summaries, thresholds, learned representations or
predictive uses remain separate future hypotheses and were not added here.

## Verification actually run

Pinned Python runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`.

Targeted suite:

```text
python -m unittest \
  experiments.test_nfl_ingame_prior_play_success_residual_audit -v
Ran 9 tests in 0.341s — OK
```

Frozen v0 plus new-runner regression:

```text
python -m unittest \
  experiments.test_nfl_ingame_win_probability_train_diagnostic \
  experiments.test_nfl_ingame_prior_play_success_residual_audit -q
Ran 19 tests in 4.460s — OK
```

Additional checks:

- R synthetic self-test: PASS;
- R parse: PASS;
- Python `py_compile`: PASS;
- `git diff --check`: PASS;
- actual v0 hash/mask/lineage preflight: PASS;
- actual opened-Train source/cohort and all 195 PBP receipt hash preflight:
  PASS;
- one local RDS schema inspection confirmed all frozen required field names;
  it did not calculate the real indicator.

Tests cover strict-prior subsetting, anchor identity/order, threshold and
home/away arithmetic, missing-side terminal behavior, exact 87-mask guards,
tie-aware average ranks, Pearson/Spearman input checks, both alignment
formulas, pooled equal-event complete-group resampling, exact decision rules,
scheduler digests, zero prediction fits, and persistent-local output guards.

## Boundary and next gate

- Real audit executions: `0`.
- Prediction-model fits: `0`.
- Scheduler mutations/claims: `0`.
- Network bytes, provider calls and cost: `0`.
- Dev/Final access: `0`.
- Candidate emission, KEEP/REVERT, publication and promotion: `0`.

The next step is an independent pre-execution review of the three exact source
hashes above.  Only a PASS may let the Supervisor bind the runner/spec in
attempt-01 and execute the single authorized local audit.  Any source repair
requires new hashes and another review; no retry or post-result feature edit
is allowed.
