# In-game predictive autonomy — generation-2 scientific Controller — 2026-09-29

## Frozen choice

Select exactly one remaining prediction candidate:

`InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4`

It is an exploitation prediction experiment, not another signal audit. Its
scored research parent is the archived v0 market-plus-state negative branch
`c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d`;
raw market `89a8ef92...` remains the separate comparison incumbent. The frozen
ordinary market-only and v0 parent prediction columns are both retained as
paired controls.

## Feedback that forces this choice

`attempt-01` is credit `0 / invalid / cooldown`: three required fit games have
120-second reference ages `334/419/612` seconds, above the exact 300-second
gate. It produced zero fits and predictions. No row drop, imputation, lag
change or staleness relaxation is allowed, so the exact momentum route is not
continued.

`attempt-02` is credit `2 / refute / stop`: identity-anchored calibration
improved over ordinary market-only (`0.143650 / 0.433565`) but was worse than
raw market (`0.141953 / 0.429671`) and won raw-market Brier in `0/4` folds.
The exact penalty-16 market-only calibration route is therefore stopped.

The remaining feasible information branch is the already frozen strictly-prior
play-success signal. Its artifact proves eligible feature coverage for all 193
materialized games, not only the 87 checks: feature SHA-256
`cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764`,
manifest `addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144`.
The later uncertainty audit is valid but inconclusive; it supplies a frozen
regime definition, not a supported result or prediction.

## Exact candidate

Preserve the v0 `195 -> 193 + 2 -> 87` population, check-key digest
`2e35779f...`, fit counts `106/132/148/176`, check counts `26/16/28/17`,
checkpoint, target, folds, scorer and seed. No row may be dropped or imputed.

Let `s` be the exact home-minus-away eligible prior-play success rate and
`u=p_now*(1-p_now)`. Freeze:

```text
x_low  = s if u < 0.1875 else 0
x_high = s if u >= 0.1875 else 0
logit(q) = logit(p_now) + beta_low*x_low + beta_high*x_high
```

The market-logit coefficient is fixed at one; there is no intercept, so this
does not reopen the stopped market-only calibration route. Fit `beta_low` and
`beta_high` without sign constraints using
`sum Bernoulli NLL + 0.5*16*(beta_low^2+beta_high^2)`. Use deterministic
analytic damped Newton, at most 50 iterations, gradient-infinity tolerance
`1e-8`, exactly one fit in each outer fold, and no retry/grid/tuning.

Emit exactly 87 paired predictions for raw market, frozen ordinary market-only,
frozen v0 market-plus-state parent and candidate. Persist equal-event Brier/log
loss, calibration, all folds, and candidate-minus-each-comparator complete-date
and complete-week 10,000-draw intervals at seed `20260929`.

KEEP requires candidate aggregate Brier and log loss below all three controls,
Brier wins against raw and ordinary in at least 3/4 folds, and both date- and
week-grouped candidate-minus-raw Brier 95% upper bounds below zero. Failure of
either aggregate raw-market proper score, or at most 1/4 raw Brier wins, is
refute. Otherwise the scientific result is inconclusive. Refute and
inconclusive are operational REVERT; no post-score change is allowed.

- question digest: `07f351446245acacefb0a21b5e24ac82e590936a753dc7347a735a1ab7377026`
- hypothesis digest: `21255a12838e33b05df9dc4fc92b4a0a7d063216c3cf475f2558416c167f0fea`
- rule digest: `aa9a76e5a245c5cc353cb1ca236d19069f72cda1e522afad956cda72bb70bb4d`
- complete component-spec digest: `a0f6647768c575fa95b9826a917faf53baed4891125d549ae9d892cadfa7dbde`
- resource ceiling: one process/thread, four fits, one execution, 900 seconds,
  768 MiB RSS, zero network/provider/cost.

## Selection fields

```json
{"allocation":"exploitation","attempt_id":"attempt-03","candidate_id":"InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4","hypothesis_digest_sha256":"21255a12838e33b05df9dc4fc92b4a0a7d063216c3cf475f2558416c167f0fea","method_family":"prior_play_success_uncertainty_stratified_offset_prediction","predeclared_rule_sha256":"aa9a76e5a245c5cc353cb1ca236d19069f72cda1e522afad956cda72bb70bb4d","question_digest_sha256":"07f351446245acacefb0a21b5e24ac82e590936a753dc7347a735a1ab7377026","question_id":"ingame-prior-play-success-uncertainty-stratified-offset-v4-q1","research_parent_sha256":"c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d","resource_hint":{"authority_granted":false,"max_attempts":1,"max_bytes":0,"max_cost_usd":0.0,"max_time_seconds":900,"resource_class":"small_experiment"}}
```

The scientific one-member selection record has digest
`0d7e7fc61de795ca13ac546c7c96ffd55f2362bb62c94647a0eb2155b533003e`
when bound to state hint
`a702cf0354cdac9c088c742d1197ec41e80e4c00719f44fc487c2ff57ff63137`.
The current v2 API correctly reports zero admissible global-pool slots when
only one attempt remains; this log does not bypass it. The Supervisor may bind
this exact scientific selection and final log SHA to its existing single-slot
recovery-batch record without changing the harness.

No implementation, execution, scheduler/batch mutation, score change,
Dev/Final read, network/provider call, payment or promotion is authorized or
performed here.
