# In-game static-state nested shrinkage v2 — implementation — 2026-09-29

## Status and scope

Implemented the frozen Controller candidate
`InGameStaticStateNestedShrinkageDiagnostic-v2` as a new runner and focused
test module. No real candidate run, experiment artifact, scheduler/credit
mutation, network/provider call, Dev/Final access, publication, promotion, or
incumbent change occurred.

The implementation is bound to the Controller pool log
`AGENT_LOG_INGAME_DISCOVERY_V3_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md`
at SHA-256
`a2c1c060b3ddf63ee3c0e1b6f7baebdba08b550c91be0a7d5585ead9b5dac18f`.
It records the exact scheduler-facing question, hypothesis, rule, and pool
digests:

- question: `8935256d05239c242b6492b29338c8c50381e6988ac69cc0acc3642adedc671c`;
- hypothesis: `c11b589592bb2c62c5c9cc7d11bdaf546cba425adfdc3ec68c15daf28c675d9c`;
- rule: `b91582ce2d23dac111b50457e78c8a451407695d47f5a61aa0f1252fd857251d`;
- pool plan: `415c47dd6f8a6ca99df78a03f102256ba981923b8bfb0992a8f6aea02b87e0a8`.

## Exact implementation

The runner keeps the v0 data, target, static representation, chronology, and
outer scorer fixed:

- source denominator `195`, materialized population `193`, and the exact two
  named exclusions;
- exact v0 nine static state features and 87-row check mask;
- outer fit/check counts `106/26`, `132/16`, `148/28`, and `176/17`;
- market logit fixed at coefficient one;
- an unpenalized intercept;
- fit-only scaling of score difference, regulation time, yards to go, and field
  advantage; possession and four down indicators remain raw;
- equal-event Brier primary score, with log loss, calibration, fold summaries,
  and complete schedule-date/week paired intervals.

For each outer fold the last six outer-fit dates become three consecutive
two-date inner checks. Each inner model uses every earlier outer-fit date and
requires each fit outcome to be available strictly before the check cutoff.
Each of `[0.25, 1, 4, 16, 64]` is fit once per inner split. Selection uses the
pooled equal-event Brier over all three inner checks; exact ties choose the
largest lambda. The selected lambda is refit once on the full outer fit.
Therefore the exact budget is `5 * 3 * 4 + 4 = 64` candidate fits with zero
automatic retries.

The attribution control is read only: the runner validates the complete frozen
v1 artifact and reads only its `market_offset_linear_state_probability` column
from predictions SHA-256
`f79a3f61a8bdcb71bcdf0f673bb87cfffe5a600a52ed523ec854978fa01fda54`.
It never calls the v1 fit entry point. Candidate, raw-market, and control rows,
labels, checkpoints, and folds must match exactly before scoring.

The implementation-specific component record hashes to
`d73680e8aaa47b28a073c7a916fab14d76b9d3a480c11e4ea5b897f4365a1f76`.

## Frozen decision and reporting

The runner emits exactly one of:

- `STATIC_STATE_NESTED_SHRINKAGE_SUPPORTED` only when candidate aggregate
  Brier and log loss beat both raw market and the frozen linear control, and
  candidate Brier beats each comparator in at least three of four folds;
- `STATIC_STATE_NESTED_SHRINKAGE_REFUTED` when either aggregate proper score
  fails against either comparator, or candidate Brier beats raw market in at
  most one of four folds;
- `STATIC_STATE_NESTED_SHRINKAGE_INCONCLUSIVE` for every other valid result.

Paired candidate-minus-market, candidate-minus-control, and control-minus-
market Brier/log-loss evidence uses 10,000 complete-group resamples at seed
`20260929` for both schedule date and observed game week. The scorecard awards
no research credit and never changes the incumbent; independent result review
and scheduler routing remain separate steps.

## No-fit production-data preflight

A no-optimizer preflight reconstructed the actual opened-Train population and
verified:

- `195 -> 193 + 2 -> 87` with check-key digest
  `2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`;
- all outer fit counts exactly match `106/132/148/176`;
- all 12 inner blocks have nonempty checks, both-class strictly prior fits,
  and zero unavailable fit labels;
- inner fit/check counts by outer fold are
  `[(76,13),(89,3),(92,14)]`,
  `[(104,3),(107,12),(119,13)]`,
  `[(120,13),(133,13),(146,2)]`, and
  `[(147,14),(161,2),(163,13)]`;
- every outer check key, outcome, and raw-market probability exactly matches
  the hash-bound frozen v1 control.

This preflight did not fit a model or create a result artifact.

## Tests performed

Using the pinned Python 3.12 runtime, the focused plus v1/v0 regression chain
passed:

```text
python -m unittest -v \
  experiments.test_nfl_ingame_static_state_nested_shrinkage_train_diagnostic \
  experiments.test_nfl_ingame_market_offset_score_time_train_diagnostic \
  experiments.test_nfl_ingame_win_probability_train_diagnostic

Ran 33 tests in 14.400s — OK
```

The 13 new tests cover analytic objective/gradient and lambda penalty,
unpenalized intercept, exact inner chronology, largest-lambda tie breaking,
fit-only transforms, exact 64-fit accounting, zero control refits, common-mask
failure, unavailable-label failure, support/refute/inconclusive decisions,
date/week 10,000-draw wiring, actual 195/193/87 no-fit preflight, frozen
artifact/digest binding, persistent-output guards, and static no-network/
provider authority.

Both new Python files passed `py_compile` with bytecode redirected to
`/private/tmp`; `git diff --check --no-index` and a static network/provider scan
also passed.

## Exact frozen hashes

- runner
  `research/market_rsi/experiments/nfl_ingame_static_state_nested_shrinkage_train_diagnostic.py`:
  `a3026d5a12fa0028087f470e44b71f4e6eb9de1432e351e415e72a039b83f65b`;
- focused test
  `research/market_rsi/experiments/test_nfl_ingame_static_state_nested_shrinkage_train_diagnostic.py`:
  `4f6797fe09646c09143b657ae320decc38f32524a066a006a68f0f5fd52ee05e`.

Any byte change requires new hashes and another pre-score review.

## Research-source classification and remaining gate

No live literature search was performed. The scientific method and parameter
grid were already frozen by the Controller, and implementation reused the
existing reviewed offset objective, proper scorer, chronological folds, and
scaler behavior. Prior-only nested selection and proper-score/common-mask
discipline are general evaluation principles; the exact nine features, six
dates, three two-date splits, lambda grid, tie rule, 64-fit budget, and decision
thresholds are project parameters. Whether shrinkage rescues stable static
state information remains the untested project hypothesis.

The next allowed step is independent pre-score review of these exact source
and test bytes. A real run remains separate and was not performed here.
