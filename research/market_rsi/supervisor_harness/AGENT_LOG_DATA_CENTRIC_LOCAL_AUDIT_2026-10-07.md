# Data-centric local source audit — 2026-10-07

## 22:33:49 UTC — scope and starting evidence

Registered task: `data_centric_local_audit_20261007`. Read-only audit of current
source and curated aggregate evidence in `/Users/estelle/Developer/market-rsi`;
starting observed HEAD `99c4be95af4cd4490973ddd27948fe046d67fa91`.
Only write scope is this dedicated log in the isolated cleanup candidate.
No raw/per-row data, live preparer imports, training, network acquisition,
paid endpoints, canonical source edits or Git mutation are authorized here.

Read all 330 lines of `research/market_rsi/AGENTS.md`, all 329 lines of
`RESEARCH_STATE.md`, all 469 lines of `RESEARCH_SUPERVISOR.md`, and the complete
`market-rsi-research-progress/SKILL.md`. An initial combined tool output was
truncated; repeated smaller reads covered the required files through EOF.
The current state is fresh02 NOT COMPLETE due semantic response admission,
with the prospective prompt repair tested, not a data-improvement result.

Commands so far: `pwd`, `wc -l`, `sed -n` instruction/audit reads,
`git rev-parse HEAD`, and source-only `rg` over ingestion/query references.
Initial curated audit confirms 4,485 anchors and 2,721 current-price eligible
anchors. The 60-second horizon entry is 1,903 scorable; the task is 300 seconds,
so the 300-second entry must be checked separately rather than mixing horizons.
No data diagnosis or repair claim yet.

## 22:34:51 UTC — source trace and repairability findings

Read `nfl_ingame_price_data.py:1-179`, the complete relevant v2 acquisition
manifest/validator sections `p0_polymarket_v2_cursor_acquisition.py:1-270,422-574`,
the audit implementation `nfl_ingame_trade_price_feasibility_audit.py:1-202`,
the curated 2025 domain inventory and PBP audit, and source-only candidate/
capacity and historical clock/quote-recorder modules. No module was imported
or executed, no artifact/raw record was opened, and no fresh tests were run.

### Established in existing curated audit; not freshly recomputed here

- `TRADE_PRICE_FEASIBILITY_AUDIT_2026-10-06.json:259-374`: 300s task has
  4,485 anchors, 2,721 current-price eligible, 1,848 label-eligible, 1,764
  missing-current and 873 missing-future-after-current; 190/195 games,
  42 dates and 14 weeks have at least one scorable anchor. This is 41.2%
  anchor eligibility, not 41.2% events and not proof of a 58.8% acquisition loss.
- `:432-487`: all 628 saved page URLs use `taker_only=true` and
  `filter_amount=0.01`; 530,222 normalized window records; 115 catalog receipts
  reorder tokens relative to raw market order. Existing audited invalid-price,
  invalid-size, timestamp, condition/token/outcome-index, exact-duplicate and
  recorded-window violation counters are zero. These checks establish source
  consistency, not whether the source omitted economic trades.
- `:472-475`: token0 inter-trade unique-time gap p50=12s/p90=56s/p99=182s
  in first125min. A30s fixed endpoint window is stringent relative to these
  gaps, but gap statistics are conditional on observed trades and do not prove
  why any particular gap exists.
- `:502-509`: existing independent second-wise occupancy recomputation agrees
  with 4,485/2,721/1,848, reducing concern about a bisect-only counting bug.

### What the code currently guarantees

- `nfl_ingame_price_data.py:36-83` checks catalog/trade byte hashes, identities,
  integer timezone-aware scheduled start, orientation from raw market token
  order, valid trade rows and count. `_load_game` uses only raw token0 for this
  target; other outcome records exist but are discarded for the price task.
- `:90-114` uses `[t-30,t)` and `[t+270,t+300)` size-weighted prices; absent
  current trades are `NO_CURRENT_WINDOW_TRADE`, absent future are
  `NO_FUTURE_WINDOW_LABEL`. This is observation eligibility, not a diagnosed
  collection failure. No forward-fill or invented same-second ordering.
- `:142-178` freezes source hashes and exact availability mask. Better data
  cannot be dropped into v1 silently. A prospective dataset/task revision can
  change coverage and rerun the same baselines; the frozen historical task
  should remain reproducible. The mask is a comparability guard, not proof
  that the project can never improve data.
- `p0_polymarket_v2_cursor_acquisition.py:422-574` validates exact page bytes,
  requested query, cursor chain, terminal `has_more=false/next_cursor=null`,
  counts, hashes, condition/token containment and duplicate full rows. It
  explicitly proves internal receipt continuity, not source authenticity,
  exchange completeness, historical retention or absence of provider omissions.
  This is a no-transport module; its existence is not a running collector.
- Curated `AGENT_LOG_FIRST_REAL_TRAIN_PIPELINE_AUDIT_2026-09-29.md:41-48`
  records that artifact-local `audit.py` reconstructs raw pages/windows and
  verifies pagination. That executable was not run/read in this task; its
  recorded result is prior evidence rather than a fresh completeness test.

### Repairability map and smallest discriminating checks (planned)

1. **Acquisition truncation/filtering — unknown amount, potentially repairable.**
   Reconcile already saved raw-page receipts to normalized windows first:
   cursor termination, max-page/full-page endings, record counts, bounds,
   every cleaning drop reason and both-token counts. If receipts are complete,
   then (only under explicit source/network scope) compare a few preselected
   same-condition/time ranges with a less-filtered query or independently
   indexed fills. Do not assume turning off taker-only adds independent trades:
   maker/taker views may duplicate counterparts. Confirm provider semantics and
   canonical economic trade identity before counting a recovery.
2. **True sparse trades — cannot be repaired by imputation.** Evidence needs
   a healthy capture/heartbeat or cross-source reconciliation. A quiet interval
   without such evidence stays `unknown`. If true sparse intervals dominate,
   revise the observation task prospectively (trade/event-time, a declared
   wider causal window, or quote-based task) and report changed estimand. Never
   use forward-filled absent trades as newly observed zero changes.
3. **Clock/schema/token mistakes — mostly checked, residual semantics unknown.**
   Raw-market token orientation and same-second commutativity already correct;
   retain tests rather than reimplement them. Check scheduled event start vs
   actual game phase/kickoff on fixed anchors. Validate BUY/SELL and size-unit
   semantics before interpreting signed volume. Full-row duplicate detection
   does not establish unique economic fills; transaction hash alone is not
   sufficient if one transaction has multiple fills. Use documented event/order
   identifiers if available, otherwise explicitly limit the claim.
4. **Unused information — cheap local diagnostic before more crawling.** Raw
   PBP/game state is resident; current price features are trade-only. Preserve
   v1 labels/masks and test a separately reviewed causal PBP feature adapter
   as a new candidate/input version. Existing Q3 checkpoint extractor is a
   pattern, not a generic arbitrary-anchor extractor: multi-anchor extraction
   requires order-sequence/correction/event-time checks. Also inspect past
   token1 support/volume as additional information, not an automatic replacement
   for token0 target (`1-p` fill prices need not match contemporaneous quotes).
5. **Historical executable quotes/receive clocks — cannot be retroactively
   invented.** Need lawful historic quote source with verified semantics or a
   small prospective shadow capture. Existing recorder/clock-audit source can
   be reused, but no entitlement/capture/result was checked or activated here.

### Research action-space mismatch

`price_candidate_author.py:192` restricts the candidate to 13 precomputed
trade features/history<=900s, fitlabels and numeric classes, no file/network/
process calls. `price_capacity_services.py:107-114` gives R/H only supplied
JSON context and a pure apply(context), no data/file/network/model/fit calls.
This pilot can test feedback interpretation, not autonomous data collection,
PBP feature discovery or a data-research tool. Improving its input/tool access
is a named prospective H/interface change with human authorship unless the
agent actually proposes/implements/reviews it under the accepted process.
Changing dataset/target is a prospective K/task version and is not an R-only
effect. Keep the comparable evaluation fixed while giving the research branch
a controlled, real data-investigation operation.

### Reusable existing capability and limitations

- `AGENT_LOG_NFL_INGAME_PBP_LOCAL_DATA_AUDIT_AND_V0_DESIGN_2026-09-29.md:64-80`
  records 195/195 hash matches and six games with backward timeOfDay; use
  orderSequence for reconstruction. `:131-173` specifies pre-play feature
  leakage constraints and denies current-play results/terminal state.
- Same log `:20-26,141-154`: retrospective nflverse PBP/trade history has event
  clocks but lacks provider-publish/local-receive history. It supports historic
  diagnostics, not proven real-time availability.
- `capture_sportradar_push_canary.py:133-175` preserves raw bytes, receive UTC,
  monotonic time and message hashes separately. `audit_live_pbp_capture.py:124-159`
  distinguishes receive/event/publish fields; descriptive event-to-receive lag
  is not publish-to-receive latency. Reuse these patterns without assuming
  current permission, paid entitlement, valid SLA or completed collection.
- `capture_quote_audit.py:97-111` already names identity/clock/unit/quiet-vs-outage
  unknowns. Its source is a historical remote reader for a different2026 date
  set, not a historical quote series attached to current2025 NFL task. It was
  not called and should not be started as a shortcut around source scope.

### Success metrics for the first zero-fit data investigation

Report complete original anchor/game/date denominator; fraction of missing
anchors with an evidenced cause vs unresolved; recovered *distinct* economic
trades and recovered eligible anchors by game/date; exact duplicate/identity/
clock violations before/after; added information/usable feature coverage;
receipt chain and replay coverage; local wall time and intervention count.
For a newly revised source/target, report both unchanged common-row comparison
and revised-population coverage, with baseline rerun under the new version.
Forecast scores are a later result, not a pass requirement for investigating
data. A larger row count alone is not research learning or prediction gain.

**Decision:** no current evidence warrants a mandatory domain switch. Historical
trade-price diagnostics remain feasible with known eligibility limits. Tradeable
PnL claims require executable quotes, costs and availability evidence; a domain
switch is justified only after comparing task-compatible data availability and
rights/cost, not merely because a30s trade window is sparse. This audit did not
repair data or show self-improvement. The next smallest useful action is a
bounded zero-fit missingness-cause report using existing saved source receipts,
then one evidence-selected remedy. No new framework is required first.

## 22:35:51 UTC — four competing causes requested by the user

Additional source-only reads: complete `nfl_ingame_price_score.py:1-174`,
`nfl_ingame_price_change_train_diagnostic.py:1-203`, current state `:1-80`,
existing PBP extraction pattern and quote/clock-reader source. One exploratory
`rg` used a nonexistent guessed `minimal_prediction_loop/price_scoring.py`
path and exited2; corrected to actual `experiments/nfl_ingame_price_score.py`.
No production repair or executable test was needed for that search error.

| Competing explanation | Evidence / present judgment | Unknown | Cheapest discriminating next experiment (not run) |
| --- | --- | --- | --- |
| Weak or faulty data | Frozen30s same-token endpoint windows yield41.2%scorable anchors. Existing integrity/occupancy checks pass; no established acquisition-loss count. | Genuine no-trade vs filtering/provider omissions; semantic fill identity/size/clock; label sensitivity to sparse fills. | Zero-fit reason report from saved receipts/raw-to-window reconstruction, with a preselected small sample for cross-source/filter reconciliation only if scope is authorized. Measure evidenced cause share and distinct recovered anchors. |
| Missing extra/other people's information | Current13pricefeatures are entirely trade-derived; resident rawPBP exists and previously supports193Q3probability rows. Data access is absent from current capacity apply(context). | Whether causalPBP or other permitted information predicts this five-minute price target beyond market history; contemporary availability unproven. | First audit same-data arbitrary-anchor PBP support and leakage. Then one matched common-row price ablation with/without a reviewedPBP family under equal model/budget, if authorized. More external crawling should follow a named hypothesis, not precede resident-information use. |
| Benchmark/evaluation wrong | Existing price scorer uses equal-gameMSE, MAE/correlation, paired date/week intervals and full denominator;B0zero-change andB1fixedHGB share rows. This is a coherent *predictor* diagnostic, not an evaluation of researcher growth or tradability. | No matched fixed-vs-evolving researcher process; only7checkweeks, repeatedly openedTrain; few candidates/predictor choices do not establish no-learning or superiority. | On the same task/information/tools/base model/total budget, compare frozen versus memory/workflow-evolvingR on subsequent independent matched tasks. Measure valid experiments/budget, correct provenance/diagnosis and reduced repeated errors; forecast metrics remain separately reported. Don't replace the predictor score with activity count. |
| Task definition/scope mismatch | Task is future30s historical tradeVWAP minus current30sVWAP, not BBO/executable return. Sparse/noisy fills may obscure effects; pure-context capacity cannot investigate data. Latest actual pilot stopped before anyRimplementation/fit at semantic admission, not data/prediction evaluation. | Is target economically useful, predictable with available information, and sensitive enough to discriminate research progress? Is broad autonomous-data research intended but not executable? | First complete one reviewedRchange with measured operational benefit plus one downstreamuse; separately freeze a task-feasibility comparison (existingVWAP task vs a quote/event-time task if lawful compatibledata exists) before new score exposure. Tradeability needs quotes/fees/slippage/availability; no mandatory domain switch yet. |

`nfl_ingame_price_score.py:79-84,138-174` explicitly limits intervals to reused
Train/fitted predictors, not selection adjustment, process superiority or
profitability. `nfl_ingame_price_change_train_diagnostic.py:27-33,45-57` confirms
the fixedHGB baseline recipe and13feature matrix. No claim that this one HGB
recipe is the strongest attainable model was established here.
`RESEARCH_STATE.md:3-29` confirms fresh02 produced anR1evidence-index proposal
but rejected it at semantic admission with0authors/attempts/fits/predictions.
This is positive evidence of a specific interface defect; it is not evidence
that data preventedR1from helping, nor proof thatR1would improve research.

Current priority conclusion: evidence is strongest for an action-space/task-
evaluation mismatch and a real pipeline admission defect. Sparse data is a
verified limitation with undiagnosed cause; insufficient extra information is
a credible untested explanation. Nothing supports declaring that every agent
attempt failed because the dataset was unusable, or that changing domain alone
will make self-improvement emerge. Source-level scope diagnosis complete;
root owns integration/verification/checkpoint/status. This log only records
actual read-only checks and proposed discriminating tests.
