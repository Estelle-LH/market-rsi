# In-game Discovery v3 two-member pool — scientific Controller — 2026-09-29

## Frozen decision

Freeze one global two-member pool:

| Member | Allocation | Changed causal stage | Research parent | Comparison incumbent |
| --- | --- | --- | --- | --- |
| `InGamePriorPlaySuccessResidualAudit-v2` | exploration | raw data -> raw signal | archived v0 market-plus-state negative branch | v0 task-local raw market |
| `InGameStaticStateNestedShrinkageDiagnostic-v2` | exploitation | raw signal -> prediction/trainer | archived v0 market-plus-state negative branch | v0 task-local raw market |

There is one exploration member out of two, or 50%. With two indivisible slots
this is the smallest nonzero allocation satisfying the approximately-30%
exploration reserve. The two members are methodologically different: member 1
asks whether a new strictly-prior sequence feature contains raw incremental
information and emits no candidate probability; member 2 keeps the existing
static data fixed and asks whether prior-only regularization selection can
extract a better prediction.

Pool-plan canonical SHA-256:
`415c47dd6f8a6ca99df78a03f102256ba981923b8bfb0992a8f6aea02b87e0a8`.

This is a plan-only scientific selection. It does not authorize implementation
or execution and does not change any score, incumbent, credit journal,
scheduler state, Train artifact, Dev, or Final.

## Exact feedback consumed and slot release

The Controller consumes the following independently reviewed feedback as
fixed input:

- v0 completed artifact manifest
  `9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7`,
  scorecard
  `74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87`,
  and result review
  `325543498c556a1c1ba0e8e3adde42c4546c35e1b0bcffac8efbeafd3d38f983`:
  `PBP_INCREMENT_NOT_SUPPORTED`. The v0 negative branch has
  `route_action=branch`: it may parent genuinely distinct questions but is not
  a prediction incumbent and cannot be relabelled as a positive result.
- v1 `score_time_ratio_k4` manifest
  `b9840bc2fe6258be40f61800fa212e157821230bd3e5c0af6bc8bf43f537ab4b`,
  scorecard
  `2301883843090a09326f03403be9564d6fbeddd962c3cc71789eba7b5155bcaf`,
  and result review
  `2eb30f66be68721957e0cae68899ffb23e35a15d59587af535fea4359217f688`:
  **credit 2 / refute / stop** for the exact
  `ingame-offset-scoretime-v1-q1` route.
- support-geometry manifest
  `f9554bbf552f269807000da33474860133414e839e3fd7cdeb20bf459a6713fd`,
  scorecard
  `7fdb2ea94f14bb38260291eeffff2cf01a0aa9be7e418bf1508166c070d19882`,
  and result review
  `d8d9c89dbbcea9e765de0308c4f4fe74d285b1fda8188f06fcbb06ef2de485f5`:
  **credit 2 / refute / stop** for the exact
  `ingame-v0-state-support-geometry-v1-q1` route.

Credit here rewards a resolved research question, including a valid negative
answer; it is not a Brier bonus and never enters KEEP/REVERT or independent
evaluation. Consequently both credit-2 refutations stop and archive their
exact routes. They are ineligible to occupy, parent a same-method continuation
in, or be ranked into the new active pool. That releases both old v2 slots.
The two freed slots are assigned below to nonduplicate questions. No extra
slot, run, or budget is created.

Raw decision-time market remains the task-local comparison incumbent. The
negative v0, v1, and support results do not reject all PBP/state hypotheses:
they reject the tested static linear model, the exact `score_time_ratio_k4`
representation, and the exact sparse-support explanation respectively.

## Member 1 — exploration: prior-play success residual audit

### Frozen question and hypothesis

- Candidate: `InGamePriorPlaySuccessResidualAudit-v2`
- Question ID: `ingame-prior-play-success-residual-v2-q1`
- Question digest:
  `402ccc0147784eedf540918028d297b2d645d9f374e515bf403e9930682e14f5`
- Hypothesis digest:
  `53f74d1204bf3c991b68f01455ca4234d86dcd832c01fe7f512970587291b5c3`
- Rule digest:
  `96c92f3ce51d779412e3953392eb037c2190ef0522fc8454a4f4f6701424b40e`

**Question:** Does a strictly-prior possession-adjusted play-success
differential contain directionally stable home-settlement information beyond
the decision-time raw market on the exact v0 common mask?

**Hypothesis:** a home-minus-away success-rate indicator formed from completed
plays strictly before the v0 anchor has positive alignment with the market
residual `y - p_raw`. This tests a new temporal PBP data family, not another
transform of the checkpoint score/time state.

### Frozen raw indicator

Use the exact v0 anchor order for every game. An eligible play must be
nondeleted, timed, typed, have `orderSequence` strictly less than the anchor,
have down 1 through 4, have finite `yards` and `yardsToGo`, and have possession
identified exactly as home or away. Never inspect the current anchor play or a
later play.

Define success as:

- down 1: `yards >= 0.45 * yardsToGo`;
- down 2: `yards >= 0.60 * yardsToGo`;
- down 3 or 4: `yards >= yardsToGo`.

The indicator is home-possession eligible-play success rate minus
away-possession eligible-play success rate. It is a project-frozen diagnostic
definition, not a claim of literature consensus. A game missing either side's
eligible plays fails integrity; it is not silently dropped or imputed.

Preserve the exact v0 87-check-game key digest
`2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9`,
folds, labels, raw-market probabilities, 195 denominator, 193 materialized
games, and the same two named exclusions.

### Frozen scoring and decision

Report Pearson and Spearman association with `y - p_raw`, mean log-loss
directional alignment `s * (y - p_raw)`, and mean Brier-logit directional
alignment `s * (y - p_raw) * p_raw * (1 - p_raw)`. Positive alignment means a
small positive signed use of the indicator points toward lower loss. Report
all four folds, schedule-date and game-week breadth, and 10,000 complete-group
bootstrap draws with seed `20260929`, always recomputing the pooled equal-event
mean within the draw.

**Support** only if Pearson and Spearman are positive, both directional
alignments are positive, the date- and week-grouped 95% lower bounds for the
log-loss alignment are positive, and at least 3/4 folds have positive
log-loss alignment.

**Refute** if both Pearson and Spearman are nonpositive, or both directional
alignments are nonpositive, or at most 1/4 folds has positive log-loss
alignment. Otherwise record inconclusive. Integrity, chronology, common-mask,
nonfinite, or missing-side failure is credit 0 rather than a scientific result.

**Stop:** one frozen audit; no row drop, prediction fit, retry, feature edit,
or threshold change. This member emits no candidate prediction and cannot
change the incumbent or KEEP/REVERT.

Resource ceiling: zero prediction fits, at most 3 wall minutes, 768 MiB RSS,
10,000 date and 10,000 week bootstrap draws, zero retries, zero network bytes,
zero provider calls, and zero cost.

## Member 2 — exploitation: nested shrinkage on fixed static state

### Frozen question and hypothesis

- Candidate: `InGameStaticStateNestedShrinkageDiagnostic-v2`
- Question ID: `ingame-static-state-nested-shrinkage-v2-q1`
- Question digest:
  `8935256d05239c242b6492b29338c8c50381e6988ac69cc0acc3642adedc671c`
- Hypothesis digest:
  `c11b589592bb2c62c5c9cc7d11bdaf546cba425adfdc3ec68c15daf28c675d9c`
- Rule digest:
  `b91582ce2d23dac111b50457e78c8a451407695d47f5a61aa0f1252fd857251d`

**Question:** Can strictly-prior nested ridge selection rescue the existing
static checkpoint-state family into a stable proper-score gain over raw market?

**Hypothesis:** the v0/v1 static-state failure is partly trainer shrinkage,
not missing data; selecting ridge strength using only earlier dates will make
the fixed-market-logit state offset outperform both raw market and the frozen
`C=1` linear offset.

This member keeps the data fixed. Use only the nine v0 static state features,
the exact 87-row mask and folds, the same target, and a market-logit coefficient
fixed at one. The intercept is unpenalized. Standardize the four continuous
features on the applicable fit rows only; leave possession/down binaries
unchanged. Do not add `score_time_ratio_k4` or any new PBP field.

For each outer fit, freeze ridge lambda to one of
`[0.25, 1, 4, 16, 64]`. Use the last six outer-fit schedule dates as three
consecutive two-date inner checks. Each inner model fits all outer-fit dates
strictly before its check. Select the lambda with the lowest pooled equal-event
inner Brier; exact ties choose the largest lambda. Refit that lambda once on
the full outer fit and evaluate the untouched outer check.

The attribution control is the frozen v1
`market_offset_linear_state` prediction column in predictions file SHA-256
`f79a3f61a8bdcb71bcdf0f673bb87cfffe5a600a52ed523ec854978fa01fda54`.
That stopped v1 route is a read-only control, not a research parent, active
member, or incumbent. Raw market remains the comparison incumbent.

### Frozen scoring and decision

Primary score is pooled equal-event Brier; also report log loss, calibration,
all four outer folds, selected lambdas, all inner losses, and paired complete
schedule-date/game-week intervals with 10,000 draws and seed `20260929`.

**Support** only if candidate aggregate Brier and log loss are lower than both
raw market and the frozen `C=1` linear control, and candidate Brier wins against
each comparator in at least 3/4 folds.

**Refute** if the candidate fails either aggregate proper score against raw
market, fails either aggregate proper score against the frozen `C=1` control,
or wins Brier against raw market in at most 1/4 folds. Otherwise record
inconclusive. Integrity, mask, chronology, nonfinite, optimizer, or inner
selection failure is credit 0.

**Stop:** one frozen run, maximum 64 fits (five lambdas times three inner
splits times four outer folds, plus four outer refits), no retry, no grid/split
change, and no post-score tuning.

Resource ceiling: at most 64 local fits, 15 wall minutes, 1 GiB RSS, one
process, zero retries, zero network bytes, zero provider calls, and zero cost.

## Why these are new and separable

Member 1 changes the raw-information question: it summarizes the strictly
prior play sequence, which neither v0's single checkpoint state, v1's
`score_time_ratio_k4`, nor the support-distance audit tested. Its output can
classify the new family as directionally incremental, absent, or inconclusive
without blaming a trainer.

Member 2 changes only the trainer: it uses the already frozen static-state
columns and asks whether nested prior-only shrinkage changes prediction
quality. It cannot attribute a gain to new data. The common raw-market
incumbent, mask, target, folds, and scoring keep the causal distinction clear.

Joint interpretation is frozen:

| Raw-sequence audit | Nested shrinkage | Interpretation |
| --- | --- | --- |
| support | any | new sequence data merits a separately frozen predictive test; no prediction gain is yet claimed by the audit |
| refute | support | static data may be usable under better shrinkage; new sequence indicator is stopped |
| support | refute | data may be incremental but the static-state trainer route remains stopped |
| refute | refute | both exact branches stop; broader PBP remains unproven, not globally rejected |
| any inconclusive | any | preserve uncertainty; do not tune either question on these same results |

## Ability and authority boundary

Both questions require only the already authorized, locally resident,
repeatedly inspected opened-Train PBP/checkpoint and frozen result artifacts.
Implementation and an independent pre-score review are still required before
any execution. Neither question needs external acquisition, live literature
search, provider credentials, paid compute, new rights, Dev, Final, publication,
promotion, realtime availability claims, or a new reward/RL service.

Historical PBP event order is usable for this diagnostic, but it does not prove
provider-publish or local-receive time. Results remain opened-Train Discovery,
not untouched OOS or executable evidence. No numerical comparison with the
pregame task is allowed.

## Canonical digest records

Each digest above is SHA-256 of the corresponding UTF-8 JSON object with keys
sorted recursively and compact separators. The canonical pool record is:

```json
{"dev_final_opened":false,"execution_authorized":false,"members":[{"allocation":"exploration","candidate_id":"InGamePriorPlaySuccessResidualAudit-v2","hypothesis_sha256":"53f74d1204bf3c991b68f01455ca4234d86dcd832c01fe7f512970587291b5c3","question_sha256":"402ccc0147784eedf540918028d297b2d645d9f374e515bf403e9930682e14f5","rule_sha256":"96c92f3ce51d779412e3953392eb037c2190ef0522fc8454a4f4f6701424b40e"},{"allocation":"exploitation","candidate_id":"InGameStaticStateNestedShrinkageDiagnostic-v2","hypothesis_sha256":"c11b589592bb2c62c5c9cc7d11bdaf546cba425adfdc3ec68c15daf28c675d9c","question_sha256":"8935256d05239c242b6492b29338c8c50381e6988ac69cc0acc3642adedc671c","rule_sha256":"b91582ce2d23dac111b50457e78c8a451407695d47f5a61aa0f1252fd857251d"}],"pool_id":"ingame-discovery-v3-two-member-pool-20260929","research_parent":"archived_v0_market_plus_state_negative_branch_route_action_branch","reserve":{"active_slots":2,"exploration_fraction":0.5,"exploration_slots":1},"score_mutation_authorized":false,"stopped_routes":["ingame-offset-scoretime-v1-q1","ingame-v0-state-support-geometry-v1-q1"],"task_local_comparison_incumbent":"v0_raw_market"}
```

No research credit or scheduler/state update is performed by this Controller
log. A trusted Supervisor may separately import the stopped-route feedback and
this plan under its append-only, duplicate-checked rules.
