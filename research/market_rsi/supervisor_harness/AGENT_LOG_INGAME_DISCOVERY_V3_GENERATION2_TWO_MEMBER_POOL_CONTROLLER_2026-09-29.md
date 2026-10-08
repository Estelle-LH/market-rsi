# In-game Discovery v3 generation-2 pool — scientific Controller — 2026-09-29

## Frozen selection

Freeze the second and final global two-member pool for batch
`market-rsi-ingame-discovery-v3-20260929-02`:

| Attempt | Allocation | Candidate | Method family | Research parent |
| --- | --- | --- | --- | --- |
| `attempt-03` | exploitation | `InGamePriorPlaySuccessMarketUncertaintyAudit-v3` | `prior_play_success_market_uncertainty_regime_audit` | credit-1 attempt-01 candidate `a612371a...` |
| `attempt-04` | exploration | `InGamePreAnchorMarketMomentumResidualAudit-v3` | `pre_anchor_market_momentum_residual_audit` | eligible archived v0 negative branch `c40b1df5...` |

This generation has one exploration member out of two, satisfies the global
reserve, and consumes the two remaining attempt slots without expanding the
batch. The methods are distinct: one explains heterogeneity in a frozen PBP
signal; the other audits a new market-path raw signal.

Canonical selection-plan SHA-256:
`c10ed553121ac9c0da123138a4e3d7b2f03979cf7143dc7092b8d8dad513a92c`.

No member is implemented, claimed, or executed by this Controller decision.

## State and feedback accepted

The 14 canonical journal records independently replay exactly to state
`e5e2761f00642f9a18cf68ce138d03002198d7946f17da2c31134f882ac75a71`
and head
`997432927a04c0bb9fa2ef43737c14a47754c356aecccf676623937bb291d9e6`.
There are two claimed attempts out of four, no active attempt, and exactly two
attempts remaining. The current selection-hint SHA-256 is
`d5a34817985da019fd14a7f36bec12ed411bed2a983e664a3960a00b491ecd71`.

The task-local incumbent remains the v0 raw market, candidate SHA-256
`89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f`.
Neither completed generation-1 member changes it.

Applied feedback exactly:

- `attempt-01` is valid but unresolved evidence: credit `1`, outcome
  `inconclusive`, route `bounded_followup`, independent review
  `0fd2d3dacefe1d7233721076f210710e3ed3e44661e39a325b6f2e0627068c73`,
  evidence bundle
  `addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144`,
  and candidate/runner
  `a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`.
  It permits exactly one bounded descendant. `attempt-03` uses that single
  allowance and adds a predeclared market-uncertainty regime contrast that can
  distinguish the parent's log-loss/Brier sign conflict; it is not a rerun,
  retuning, or prediction claim.
- `attempt-02` is credit `0`, outcome `invalid`, route `cooldown`, independent
  review
  `003a96e3cd65f9bf3ad70221f07509512a49c3e4f56960bcbdc087b3ca32d938`.
  It stopped before predictions or scores. It is neither continued nor used as
  a parent or scientific refutation. Its failed attempt remains consumed.
- The eligible archived v0 market-plus-state negative branch remains a
  credit-2/refute/branch research parent at
  `c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d`.
  It parents the orthogonal market-path question, not another shrinkage repair.

## Complete scheduler fields

The generation is `2`; the comparison incumbent is
`89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f`;
the selection-hint SHA-256 is
`d5a34817985da019fd14a7f36bec12ed411bed2a983e664a3960a00b491ecd71`.
For both selections, `controller_decision_sha256` is the SHA-256 of this exact
Controller log, reported after the file is written.

### `attempt-03`

- `candidate_id`: `InGamePriorPlaySuccessMarketUncertaintyAudit-v3`
- `research_parent_sha256`:
  `a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb`
- `allocation`: `exploitation`
- `method_family`: `prior_play_success_market_uncertainty_regime_audit`
- `question_id`: `ingame-prior-play-success-market-uncertainty-v3-q1`
- `question_digest_sha256`:
  `7d9baa1a8e0568f9273811492716400ebc19dfc65d5d77e950e281da85757fe3`
- `hypothesis_digest_sha256`:
  `6c22574911e625875ef8d97bfc4580d20d82ac2f620adfcbceb85829ee52ff84`
- `predeclared_rule_sha256`:
  `23a956a5ffee6d7fe800a67fbf1eb9146d34f367d4a5745d98abbd96537a7e1a`
- `resource_hint`: `resource_class=local_analysis`, `max_attempts=1`,
  `max_time_seconds=180`, `max_bytes=0`, `max_cost_usd=0.0`,
  `authority_granted=false`.

### `attempt-04`

- `candidate_id`: `InGamePreAnchorMarketMomentumResidualAudit-v3`
- `research_parent_sha256`:
  `c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d`
- `allocation`: `exploration`
- `method_family`: `pre_anchor_market_momentum_residual_audit`
- `question_id`: `ingame-pre-anchor-market-momentum-residual-v3-q1`
- `question_digest_sha256`:
  `f82528a6d379831c10e9d98979d29fc9cb77037fd5749ad9f59f041214b1ddfa`
- `hypothesis_digest_sha256`:
  `d581adb57a3a6d554bd23248d9325c8fb0d2082db8c73c74fd944f616b5e9d6d`
- `predeclared_rule_sha256`:
  `d1a3369bbedc9c9c01848986ecf7c387bfeef6c124e9d1e85343ab19e68f2270`
- `resource_hint`: `resource_class=local_analysis`, `max_attempts=1`,
  `max_time_seconds=300`, `max_bytes=0`, `max_cost_usd=0.0`,
  `authority_granted=false`.

## Member 1 — bounded follow-up with new discrimination

**Question:** Is the parent prior-play-success signal mixed because its
positive residual alignment is confined to low-market-uncertainty games while
high-market-uncertainty games reverse the sign?

Use only the exact parent 87-row event audit, mask, signal, outcome, raw-market
probability, folds, dates, and weeks. Recompute no PBP feature. Define
`uncertainty = p_raw * (1 - p_raw)`. High uncertainty is
`uncertainty >= 0.1875`, equivalently inclusive `p_raw` in `[0.25, 0.75]`;
low uncertainty is everything else. The threshold is fixed now and may not be
learned or changed.

The hypothesis is that parent log alignment is positive in the low-uncertainty
regime, negative in the high-uncertainty regime, high-uncertainty Brier-logit
alignment is negative, and the pooled low-minus-high log-alignment contrast is
positive. This directly discriminates the observed positive unweighted log
alignment from the negative Brier-weighted alignment. It does not assert that
either regime is a profitable prediction policy.

Report regime counts and date/week breadth; mean log and Brier-logit alignment
per regime; low-minus-high log contrast; all four fold contrasts; and 10,000
complete schedule-date and game-week bootstrap draws at seed `20260929`.
Within each draw recompute both pooled equal-event regime means. A draw lacking
either regime is undefined and must be counted, not imputed.

Decision order is fail-closed integrity, then insufficient-breadth
inconclusive, then support, then refute, then inconclusive:

- **Support** only if each regime has at least 12 events, each grouped
  bootstrap has at least 9,000 valid draws, low log alignment is positive,
  high log and Brier-logit alignments are negative, the contrast is positive,
  both grouped 95% lower bounds are positive, and at least 3/4 fold contrasts
  are positive.
- **Refute** if the contrast is nonpositive, or low alignment is nonpositive
  while high alignment is nonnegative, or at most 1/4 fold contrasts is
  positive.
- Otherwise **inconclusive**. Fewer than 12 events in either regime or fewer
  than 9,000 valid draws is explicitly inconclusive, not a post-hoc regrouping.
- Parent-hash, mask, identity, nonfinite, or regime-assignment failure is
  credit 0.

**Stop:** exactly this one bounded follow-up. No signal/threshold edit,
prediction fit, row drop, retry, or second descendant. Regardless of result,
the credit-1 parent's follow-up allowance is exhausted when this attempt is
claimed.

## Member 2 — orthogonal market-path raw-signal audit

**Question:** Does the strictly-prior 120-second decision-time market-logit
change contain stable home-settlement information beyond the current
raw-market snapshot?

Preserve the v0 195 -> 193 + 2 lineage and exact 87 check keys, labels, anchor
times, raw-market incumbent probabilities, folds, dates, and weeks. `p_now` is
the exact v0 latest strictly-prior home-oriented size-weighted fill-second
probability. Set the reference cutoff to
`floor(decision_time_epoch_seconds) - 120`. `p_ref` is the home-oriented,
size-weighted probability at the latest trade second strictly before that
cutoff, with age at the reference cutoff no greater than 300 seconds. Use the
same v0 side orientation and probability normalization. Clip both probabilities
to `[1e-6, 1-1e-6]` only when taking logits.

The frozen signal is `logit(p_now) - logit(p_ref)`. The hypothesis is that
positive recent homeward momentum has stable positive alignment with the
current-market residual `y - p_now`. This changes the raw data/signal family,
not the prediction trainer, and is orthogonal to static PBP state, score-time,
support geometry, prior-play success, and failed shrinkage.

Report Pearson and Spearman association with `y - p_now`, mean log-loss
directional alignment `signal * (y - p_now)`, mean Brier-logit directional
alignment `signal * (y - p_now) * p_now * (1 - p_now)`, all four folds,
schedule-date/week breadth, and 10,000 complete-group bootstrap draws with seed
`20260929`, recomputing pooled equal-event means inside each draw.

- **Support** only if Pearson and Spearman are positive, both directional
  alignments are positive, both date- and week-grouped log-alignment 95% lower
  bounds are positive, and at least 3/4 folds have positive log alignment.
- **Refute** if both correlations are nonpositive, or both directional
  alignments are nonpositive, or at most 1/4 folds has positive log alignment.
- Otherwise **inconclusive**.
- Source-receipt, mask, chronology, nonfinite, or any check-row reference
  coverage failure is credit 0. No row may be dropped or imputed.

**Stop:** one frozen audit; no alternate lag, staleness, indicator, row mask,
prediction fit, or retry.

## Interpretation and authority boundary

The follow-up can resolve why the parent metric directions disagree; the
market-path member can determine whether a new non-PBP information family has
raw incremental direction. Neither emits a candidate probability or can
change KEEP/REVERT or the raw-market incumbent. A valid raw-signal support
result would require a later separately frozen prediction experiment, outside
this exhausted batch.

Both members use only resident, already authorized opened-Train artifacts.
No external acquisition, live literature search, network, provider credential,
payment, Dev, Final, publication, promotion, or realtime-availability claim is
needed or authorized. Historical trade/PBP event time remains distinct from
provider-publish and local-receive time.

## Canonical plan record

The plan digest above is SHA-256 of this sorted compact JSON object:

```json
{"comparison_incumbent_sha256":"89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f","pool_generation":2,"selection_hint_sha256":"d5a34817985da019fd14a7f36bec12ed411bed2a983e664a3960a00b491ecd71","selections":[{"allocation":"exploitation","attempt_id":"attempt-03","candidate_id":"InGamePriorPlaySuccessMarketUncertaintyAudit-v3","hypothesis_digest_sha256":"6c22574911e625875ef8d97bfc4580d20d82ac2f620adfcbceb85829ee52ff84","method_family":"prior_play_success_market_uncertainty_regime_audit","predeclared_rule_sha256":"23a956a5ffee6d7fe800a67fbf1eb9146d34f367d4a5745d98abbd96537a7e1a","question_digest_sha256":"7d9baa1a8e0568f9273811492716400ebc19dfc65d5d77e950e281da85757fe3","question_id":"ingame-prior-play-success-market-uncertainty-v3-q1","research_parent_sha256":"a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb","resource_hint":{"authority_granted":false,"max_attempts":1,"max_bytes":0,"max_cost_usd":0.0,"max_time_seconds":180,"resource_class":"local_analysis"}},{"allocation":"exploration","attempt_id":"attempt-04","candidate_id":"InGamePreAnchorMarketMomentumResidualAudit-v3","hypothesis_digest_sha256":"d581adb57a3a6d554bd23248d9325c8fb0d2082db8c73c74fd944f616b5e9d6d","method_family":"pre_anchor_market_momentum_residual_audit","predeclared_rule_sha256":"d1a3369bbedc9c9c01848986ecf7c387bfeef6c124e9d1e85343ab19e68f2270","question_digest_sha256":"f82528a6d379831c10e9d98979d29fc9cb77037fd5749ad9f59f041214b1ddfa","question_id":"ingame-pre-anchor-market-momentum-residual-v3-q1","research_parent_sha256":"c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d","resource_hint":{"authority_granted":false,"max_attempts":1,"max_bytes":0,"max_cost_usd":0.0,"max_time_seconds":300,"resource_class":"local_analysis"}}]}
```

The question, hypothesis, and rule digests are computed from separate sorted,
compact canonical JSON records whose full semantics are stated above. This log
does not mutate scheduler, credit, budget, incumbent, score, or protected data.
