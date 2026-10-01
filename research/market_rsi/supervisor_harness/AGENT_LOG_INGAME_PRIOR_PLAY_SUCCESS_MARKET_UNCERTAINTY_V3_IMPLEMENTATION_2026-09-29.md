# InGamePriorPlaySuccessMarketUncertaintyAudit-v3 — implementation log

Date: 2026-09-29  
Scope: implementation and tests only; no real audit execution and no scheduler mutation  
Status: **READY FOR INDEPENDENT PRE-SCORE REVIEW**

## Frozen specification and parent

The new runner is bound to generation-2 Controller log SHA-256
`4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986`
and the exact attempt-03 scheduler branch digest
`71a1e48c0b82378e17030dbc9045fcd68eb01bcf5ba78ad015c6629bf72804a9`.

It reads only the completed parent artifact
`nfl-ingame-prior-play-success-residual-audit-20260929-01`. It requires the
exact six-file set and hashes:

| Parent file | SHA-256 |
| --- | --- |
| `manifest.json` | `addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144` |
| `scorecard.json` | `db53da50fecbebce76eb105915d53db51ce44eced92fbf41dd9688ac40e71846` |
| `event_audit.csv` | `0b85a96491237edcf1b74e8718db0582bae28d0bf380c0d0f89564edaf20e2f5` |
| `prior_play_success.csv` | `cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764` |
| `input_receipts.json` | `0f8902d5aee81a08d5c17c44f2025e10ca650cc6f825c4be150735c0ac7934e0` |
| `pre_audit_lock.json` | `d046d70927f0f29f327b0ed8552e523fbaf3c1955db257af19a225250f9e2929` |

The runner also binds parent runner SHA
`a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`
and parent independent-review SHA
`0fd2d3dacefe1d7233721076f210710e3ed3e44661e39a325b6f2e0627068c73`.
It validates the parent manifest/scorecard/receipt bindings, zero-fit and
non-candidate boundary, directional arithmetic, exact 87 unique games, fold
counts `26/16/28/17`, 20 dates, seven weeks, and event-identity digest
`92513bfe46e9f023b1afd8ca6218e67ce1810a333424c69e1e3a699d060fae10`.

## Implemented audit

New files:

- `experiments/nfl_ingame_prior_play_success_market_uncertainty_audit.py`
  - SHA-256: `e51f85ed368c53545369dfdd7505dcee3331917cba115ebacb5194290808e745`
- `experiments/test_nfl_ingame_prior_play_success_market_uncertainty_audit.py`
  - SHA-256: `9de0b91f9add89229f8587d3383532f4bbd1a78b6fa3248daac23f78f130cd0c`

The runner does not import or invoke the parent extractor, R, subprocess, a
source/PBP directory, a network client, or a prediction trainer. It uses the
parent's already materialized signal, outcome, raw probability, folds, dates,
weeks, residual and directional-alignment terms without dropping a row.

For every parent row it computes exactly:

```text
uncertainty = p_raw * (1 - p_raw)
high = uncertainty >= 0.1875
low  = uncertainty < 0.1875
```

Thus `p_raw=0.25` and `p_raw=0.75` are inclusively high. It reports per-regime
event/date/week breadth, mean log alignment, mean Brier-logit alignment, the
pooled low-minus-high log-alignment contrast, and all four fold contrasts.

Schedule-date and observed-game-week intervals each use 10,000 complete-group
draws with seed `20260929`. Every draw recomputes the pooled equal-event low
and high means. If either regime is absent, the draw is counted as undefined
and is neither imputed nor included in the quantile sample. The artifact reports
total, valid, and undefined draw counts.

Decision order is implemented exactly as integrity failure, insufficient-
breadth inconclusive, support, refute, then otherwise inconclusive:

- support requires at least 12 events in each regime, at least 9,000 valid
  draws for both groupings, positive low log alignment, negative high log and
  high Brier-logit alignment, positive pooled contrast, positive lower bounds
  for both grouped intervals, and at least three positive fold contrasts;
- refute requires nonpositive pooled contrast, or low nonpositive with high
  nonnegative, or at most one positive fold contrast;
- breadth failure is explicitly inconclusive before any refute condition is
  evaluated.

Nonfinite evidence, hash/file-set drift, mask/identity drift, invalid regime
assignment, or bootstrap-accounting drift fails closed. The runner creates a
pre-audit lock before calculating the new aggregate, then would persist an
enriched 87-row regime audit, scorecard, receipts and manifest. It declares
zero fits, no candidate probability, no incumbent or KEEP/REVERT change, one
bounded follow-up, and no retry.

## Verification

Using the pinned local Python 3.12 runtime:

- `py_compile` for the new runner and tests: **PASS**.
- 10 new targeted tests plus 19 parent/v0 regression tests: **29/29 PASS** in
  4.178 seconds.
- `git diff --check` for the new runner and tests: **PASS**.

Targeted coverage includes exact parent hashes and 87-row mask, hash-map drift,
inclusive regime endpoints, row preservation and duplicate rejection,
undefined bootstrap draws, pooled equal-event contrast arithmetic, exact
support/refute/otherwise-inconclusive rules, breadth-first ordering, nonfinite
and bootstrap-accounting failures, scheduler binding, zero-fit/no-PBP static
guards, and persistent non-cloud output guards.

No production artifact directory was created. No real regime means, intervals
or decision were calculated by the runner. No network/provider access, payment,
Dev, Final, publication, promotion, candidate update, or scheduler-state write
occurred.

## Evaluation discipline

The implementation follows the indicator-evaluation rule that raw-signal
heterogeneity must be measured on the exact paired event mask before proposing
a downstream prediction change. This is historical opened-Train diagnostic
evidence only and cannot establish realtime availability, untouched OOS,
prediction improvement, or monetization.
