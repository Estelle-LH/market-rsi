# `InGamePriorPlaySuccessMarketUncertaintyAudit-v3` independent result review — 2026-09-29

## Verdict

**PASS. P0: none. P1: none.**

The sole completed `attempt-03` artifact is hash-consistent and independently
reproduces the frozen decision
`PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_INCONCLUSIVE`. The proposed aggregate
regime mechanism is directionally visible—low-uncertainty alignment is
positive and high-uncertainty alignment is negative—but it is not stable
enough to pass the predeclared grouped-interval or fold gates. It is also not
decisively reversed, so the refutation rule does not apply.

Scheduler recommendation: **REVERT**, with no incumbent update. Research-credit
recommendation under the current contract: **credit 1 / outcome
`inconclusive` / route action `bounded_followup`**. That contract label records
valid unresolved information; it is not execution authority. The predeclared
one-follow-up stop remains binding, and this batch has already claimed all four
attempts, so this review does not recommend or authorize another descendant.

## Frozen artifact integrity

Reviewed read-only:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-ingame-prior-play-success-market-uncertainty-audit-20260929-01`

The directory contains exactly five result files:

| file | SHA-256 |
| --- | --- |
| `manifest.json` | `0d14e0fc312500f086cd30368ab71096f9292334546b02c7b7ccd1e42af365a6` |
| `scorecard.json` | `554eecd201eeea96bbc1a3f436ce65700dd698ac5df488546ceb4743bd4d4c28` |
| `pre_audit_lock.json` | `db0a5d2f005e5a126bd572c38ec06299a418f12d717c0e9ba01ecfd5cdef93f7` |
| `input_receipts.json` | `43d1854b57319ef328251d0b47faf74d1c142499b85f55b3cea8a0359c0cbc82` |
| `regime_event_audit.csv` | `ece4e6776bb58888702f178a9f58df3ec2d7e002fab9110cec09003ea4c6e60a` |

Every manifest-to-file hash matches. The manifest is complete, records 87
checks, zero model fits, no dropped parent row, no prediction candidate, no
incumbent/KEEP/REVERT mutation, and the same decision as the scorecard.

The lock and receipts bind:

- frozen runner
  `e51f85ed368c53545369dfdd7505dcee3331917cba115ebacb5194290808e745`;
- Controller log
  `4186a3554b7f7aed50596123c135943dbf986d5e39b84fe507fac91c6e04e986`;
- parent runner
  `a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`;
- parent independent review
  `0fd2d3dacefe1d7233721076f210710e3ed3e44661e39a325b6f2e0627068c73`;
- parent manifest
  `addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144`;
- parent event audit
  `0b85a96491237edcf1b74e8718db0582bae28d0bf380c0d0f89564edaf20e2f5`;
- exact question, hypothesis, and rule digests
  `7d9baa1a8e0568f9273811492716400ebc19dfc65d5d77e950e281da85757fe3`,
  `6c22574911e625875ef8d97bfc4580d20d82ac2f620adfcbceb85829ee52ff84`,
  and
  `23a956a5ffee6d7fe800a67fbf1eb9146d34f367d4a5745d98abbd96537a7e1a`.

The batch terminal record independently cross-links successful `attempt-03`
execution receipt SHA-256 to the manifest above, with runner/spec hashes equal
to the frozen values. The branch had no result review, research credit, route,
or incumbent transition at the time of this read-only review.

## Independent 87-row and arithmetic replay

I parsed the child and parent CSVs directly without importing the runner. All
87 child rows match the parent row-for-row on fold, game/date/week identity,
outcome, and raw-market probability. There are 87 unique game IDs, fold counts
`26/16/28/17`, 20 schedule dates, and seven observed game weeks. The
independently reconstructed parent identity SHA-256 is
`92513bfe46e9f023b1afd8ca6218e67ce1810a333424c69e1e3a699d060fae10`,
matching the lock and scorecard; the v0 common-mask SHA remains
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`.

For each event I independently recomputed:

```text
market_residual = outcome - p_raw
log_alignment = parent_signal * market_residual
brier_logit_alignment = log_alignment * p_raw * (1 - p_raw)
market_uncertainty = p_raw * (1 - p_raw)
regime = high iff market_uncertainty >= 0.1875, else low
```

Every stored arithmetic value and regime assignment matches to the frozen
`2e-15` numeric tolerance. No row was dropped or imputed.

## Independently reproduced regime evidence

Aggregate values reproduced exactly:

| regime | events | dates | weeks | mean log alignment | mean Brier-logit alignment |
| --- | ---: | ---: | ---: | ---: | ---: |
| low uncertainty | 51 | 16 | 7 | `0.004830652150683469` | `0.0003013376376831029` |
| high uncertainty | 36 | 10 | 6 | `-0.0035317702185954526` | `-0.0008628046281144594` |

Low-minus-high mean log alignment is
`0.008362422369278921`. Both regimes exceed the frozen 12-event breadth floor.

The four independently recomputed contrasts are:

| fold | events | low/high counts | low-minus-high log alignment | positive? |
| --- | ---: | ---: | ---: | --- |
| 1 | 26 | 18 / 8 | `-0.002922278142247257` | no |
| 2 | 16 | 11 / 5 | `0.01962424972085538` | yes |
| 3 | 28 | 14 / 14 | `-0.004438651564382148` | no |
| 4 | 17 | 8 / 9 | `0.026912222079421597` | yes |

Thus only 2/4 folds have a positive contrast; the support rule requires at
least 3/4 and the refute rule requires at most 1/4.

## Independent grouped bootstrap replay

Using a fresh NumPy generator for each grouping, seed `20260929`, 10,000
complete-group draws, and pooled equal-event low/high means inside each draw,
I reproduced:

| grouping | groups | valid / undefined | 95% interval |
| --- | ---: | ---: | --- |
| schedule date | 20 | 10,000 / 0 | `[-0.006031627940572708, 0.02817575562563265]` |
| observed game week | 7 | 10,000 / 0 | `[-0.005500080619457915, 0.02220549888774189]` |

Both valid-draw counts exceed 9,000. Both intervals cross zero, so neither
grouped lower bound is positive. Undefined draws were correctly counted as
zero; none were silently imputed.

## Exact decision

Breadth passes. Five directional conditions hold: low log alignment is
positive, high log alignment is negative, high Brier-logit alignment is
negative, aggregate contrast is positive, and all draw-count requirements
pass. Support nevertheless fails because both grouped lower bounds are negative
and only 2/4 folds are positive.

No refutation clause holds: the aggregate contrast is positive; low is not
nonpositive while high is nonnegative; and positive folds number two rather
than at most one. Under the frozen order, the only valid result is therefore
`PRIOR_PLAY_SUCCESS_MARKET_UNCERTAINTY_INCONCLUSIVE` at the
`otherwise_inconclusive` stage.

This is useful diagnostic evidence that the parent's metric-sign conflict is
compatible with market-uncertainty heterogeneity, but the evidence is unstable
by time block. It cannot be converted into a supported gated signal, prediction
candidate, or refutation by changing thresholds or rules after observing the
result.

## Scheduler, credit, and scientific disposition

- **Performance:** `REVERT`. The audit emitted no probability candidate and
  cannot compete with the incumbent.
- **Incumbent:** keep the task-local raw market unchanged.
- **Research outcome:** `inconclusive`.
- **Research credit:** `1`, because the result is valid, independently
  reproducible, and adds a new regime diagnosis, but does not resolve the
  question.
- **Contract route label:** `bounded_followup`, the only current scheduler
  contract pairing for credit-1/inconclusive evidence.

The route label is not a recommendation to spend another attempt. The
Controller froze this as the one and only child of the prior credit-1 branch,
forbade a second descendant/retry, and the batch now shows four claimed attempts
out of four. Preserve the evidence and stop this exact market-uncertainty route;
do not alter the 0.1875 split, bootstrap, folds, or signal on these inspected
rows.

## Boundary verification

Manifest, scorecard, lock and receipts agree on zero model fits, no PBP
recomputation, no row drop, no prediction candidate, no incumbent change, no
external fetch, no paid provider, cost exactly `0`, Dev unopened, Final sealed,
and no promotion. The result uses only the historical parent event audit; it
does not prove realtime availability, untouched OOS gain, PnL, or cross-task
comparability.

No artifact, runner, scheduler, credit, incumbent, budget, Dev/Final, network,
provider, or Git state was modified during this independent review.
