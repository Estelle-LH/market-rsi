# `InGamePriorPlaySuccessMarketUncertaintyAudit-v3` independent pre-score review — 2026-09-29

## Verdict

**PASS. P0: none. P1: none.**

The frozen implementation is consistent with the generation-2 Controller
question and is ready for one supervised, zero-fit opened-Train audit after the
Supervisor separately advances/claims `attempt-03`. This review did not call
the real audit, create an experiment artifact, read a new score, or mutate the
scheduler.

## Frozen bytes and Controller binding

- runner:
  `research/market_rsi/experiments/nfl_ingame_prior_play_success_market_uncertainty_audit.py`
  SHA-256
  `e51f85ed368c53545369dfdd7505dcee3331917cba115ebacb5194290808e745`;
- focused tests:
  `research/market_rsi/experiments/test_nfl_ingame_prior_play_success_market_uncertainty_audit.py`
  SHA-256
  `9de0b91f9add89229f8587d3383532f4bbd1a78b6fa3248daac23f78f130cd0c`;
- generation-2 Controller log SHA-256
  `4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986`;
- pool-plan SHA-256
  `c10ed553121ac9c0da123138a4e3d7b2f03979cf7143dc7092b8d8dad513a92c`.

The runner freezes the selected scheduler fields for `attempt-03`: exploitation
allocation, candidate/task ID, method family, credit-1 research-parent SHA
`a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`,
raw-market comparison incumbent, and zero-authority resource hint. The binding
digest reproduces as
`71a1e48c0b82378e17030dbc9045fcd68eb01bcf5ba78ad015c6629bf72804a9`.
The current batch branch contains the same question, hypothesis and rule
digests and remains `controller_selected`; runner/spec/claim/result fields were
still null during review.

Question/hypothesis/rule digests match the Controller exactly:

- question:
  `7d9baa1a8e0568f9273811492716400ebc19dfc65d5d77e950e281da85757fe3`;
- hypothesis:
  `6c22574911e625875ef8d97bfc4580d20d82ac2f620adfcbceb85829ee52ff84`;
- rule:
  `23a956a5ffee6d7fe800a67fbf1eb9146d34f367d4a5745d98abbd96537a7e1a`.

## Exact parent and row-mask review

Production execution is bound to the reviewed parent artifact:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-prior-play-success-residual-audit-20260929-01`

The validator requires the exact six-file set and SHA-256 map:

| parent file | SHA-256 |
| --- | --- |
| `manifest.json` | `addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144` |
| `pre_audit_lock.json` | `d046d70927f0f29f327b0ed8552e523fbaf3c1955db257af19a225250f9e2929` |
| `input_receipts.json` | `0f8902d5aee81a08d5c17c44f2025e10ca650cc6f825c4be150735c0ac7934e0` |
| `prior_play_success.csv` | `cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764` |
| `event_audit.csv` | `0b85a96491237edcf1b74e8718db0582bae28d0bf380c0d0f89564edaf20e2f5` |
| `scorecard.json` | `db53da50fecbebce76eb105915d53db51ce44eced92fbf41dd9688ac40e71846` |

It additionally verifies manifest cross-links, parent completion and
`PRIOR_PLAY_SUCCESS_RESIDUAL_INCONCLUSIVE`, the parent review/runner hashes,
zero-fit/no-candidate/incumbent-unchanged flags, and closed network/provider/
Dev/Final/promotion boundaries.

The parent CSV must have an exact closed header, 87 unique games, fold counts
`26/16/28/17`, 20 dates, seven weeks, and event-identity SHA-256
`92513bfe46e9f023b1afd8ca6218e67ce1810a333424c69e1e3a699d060fae10`.
It preserves the v0 check-key SHA-256
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.
For every event it independently recomputes market residual, log alignment and
Brier-logit alignment within `2e-15`; duplicate, blank, out-of-domain or
nonfinite rows fail closed. Regime assignment preserves all input rows and the
run rechecks exact game identity before writing results. No PBP is recomputed.

## Frozen method and decision-order review

The implementation uses exactly
`uncertainty = p_raw * (1 - p_raw)`. `uncertainty >= 0.1875` is high,
equivalently inclusive `p_raw` in `[0.25, 0.75]`; lower uncertainty is low.
Tests cover `0.25`, `0.75`, `0.5`, both adjacent outside floating values, and
invalid probability endpoints.

It reports low/high event, date and week breadth; mean log and Brier-logit
alignment; the low-minus-high log contrast; and all four fold contrasts. Date
and week uncertainty each use 10,000 complete-group resamples, seed `20260929`,
and recompute pooled equal-event low and high means inside every draw. A draw
missing either regime is counted as undefined and never imputed. Valid plus
undefined draws must equal 10,000.

The decision order is implemented exactly:

1. malformed, nonfinite, identity/hash/mask evidence raises and fails closed;
2. fewer than 12 events in either regime or fewer than 9,000 valid draws in
   either grouping returns insufficient-breadth **inconclusive**, before any
   refutation rule;
3. support requires every frozen sign, grouped-lower-bound, and 3/4-fold gate;
4. otherwise any frozen refutation clause yields refute;
5. remaining evidence is inconclusive.

Focused tests cover exact support, each ordered refute/inconclusive path,
breadth precedence, bootstrap accounting, nonfinite evidence and undefined
draws. No post-result threshold, regrouping, row deletion, retry, or alternate
decision path exists.

## Zero-fit and authority boundary

Static and test inspection found no estimator, `predict_proba`, PBP extractor,
R/subprocess path, network client, socket, provider, credential, Dev/Final,
promotion or KEEP/REVERT capability. `MODEL_FITS=0`; outputs explicitly say no
prediction candidate and no incumbent change. Production input is the exact
parent artifact and production output must be a new path below the persistent
local MarketRSI artifact root; an existing, temporary, cloud-looking, or
parent-nested output is rejected. Cost is fixed to zero.

The evidence remains a heterogeneity diagnostic on repeatedly inspected
opened Train. Even a support decision would not be a probability improvement,
untouched OOS result, realtime-availability proof, PnL result, or promotion.

## Verification performed

Pinned runtime:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/market_rsi \
  /Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python \
  -m unittest -v \
  experiments.test_nfl_ingame_prior_play_success_market_uncertainty_audit

Ran 10 tests in 0.012s — OK
```

Both frozen files also passed `py_compile` with bytecode redirected to
`/private/tmp` and passed `tabnanny`. No real audit function or CLI was invoked.

## Conclusion

PASS for pre-score admission after the trusted scheduler separately binds the
runner/spec and claims the fresh attempt. This review grants no execution or
state authority and does not itself advance `attempt-03`.
