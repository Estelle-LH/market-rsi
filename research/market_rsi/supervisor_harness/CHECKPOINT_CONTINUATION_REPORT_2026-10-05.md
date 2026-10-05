# Market RSI: feedback-driven Train continuation — October 5, 2026

## Outcome

Two new prediction candidates completed eight real chronological fits and independent numerical review. The verified first result changed the original Controller’s second choice. Neither candidate improved primary Brier versus the raw market or C7 research parent; the market incumbent is unchanged. Negative evidence is retained separately from prediction replacement.

This batch demonstrates actual continuation and observed use of accumulated evidence. It does not demonstrate better research capacity, a market edge, autonomous workflow modification, or superiority over a matched fixed research process. Both separate learning checkpoints are independently accepted at credit2, with canonical deduplication, unchanged REVERT and preserved distinct-question exploration eligibility.

Batch: `market-rsi-learning-checkpoint-continuation-20261005-01`. New authority was 2 candidates / 8 actual fits / 2 original Controller decisions, at most 90 minutes. Start 18:32:32 EDT; selection cutoff 19:47:32; hard deadline 20:02:32. All three count limits are consumed. No third input or decision is prepared. Older C1 and repair results, clocks and caps are preserved, not rerun or reset.

## Comparable result table

Lower loss is better. All rows use the same 87 historical Train check games, labels and frozen scorer. References are replayed from frozen predictions, with no new reference fits.

| Predictor | Equal-game Brier | Log loss | Δ Brier vs market | Δ Brier vs C7 | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Raw market: incumbent | 0.141952529 | 0.429670785 | 0 | −0.000001575 | Hold |
| C7 temperature: actual research parent | 0.141954104 | 0.428886089 | +0.000001575 | 0 | Existing research branch |
| N1: field-position conditional slope | 0.141983546 | 0.428988574 | +0.000031017 | +0.000029442 | REVERT; valid negative retained |
| N2: distance conditional slope | 0.142002449 | 0.429143844 | +0.000049920 | +0.000048345 | REVERT; valid negative retained |
| Ordinary market-only reference | 0.145482313 | 0.439921972 | +0.003529784 | +0.003528208 | Frozen ordinary reference |
| Historical v0 market-plus-state reference | 0.160680990 | 0.471197319 | +0.018728461 | +0.018726886 | Frozen comparison, not selected strong baseline |

Both new recipes improve log loss relative to raw market but worsen Brier, and both worsen both proper losses relative to C7. N1 wins 2/4 parent Brier blocks; N2 wins 1/4. The unchanged predeclared parent-increment annotation and market KEEP rule fail. There is no need to relax a threshold to keep Discovery moving: valid negatives can inform new questions without replacing the predictor.

## Paired time-block evidence

Each block is five fixed schedule dates, not five equally weighted observations. Deltas below are loss differences multiplied by one million; negative is better. Individual predictions, all five-arm block scores, 20 date-level pairs, calibration and grouped intervals remain in the scorecards and parent supplements.

| Block / check date range | Games | N1 Δ Brier/C7 | N2 Δ Brier/C7 | N1 Δ Brier/market | N2 Δ Brier/market |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1: Oct 23–Nov 2, 2025 | 26 | +214.070 | +51.723 | +615.916 | +453.570 |
| 2: Nov 3–13 | 16 | −1.093 | −54.347 | +909.733 | +856.480 |
| 3: Nov 16–24 | 28 | +2.525 | +132.322 | −435.657 | −305.860 |
| 4: Nov 27–Dec 4 | 17 | −179.859 | +1.513 | −921.924 | −740.552 |

Parent Brier 95% descriptive intervals cross zero. N1: complete-date [−0.000094057, +0.000158796], complete-week [−0.000083735, +0.000177817]. N2: complete-date [−0.000033106, +0.000117904], complete-week [−0.000020631, +0.000114165]. Each bootstrap draw resamples whole dates or observed game weeks and recomputes the game-equal mean. These adaptively reused Train intervals are not independent confirmation.

## Verifiable feedback trajectory

1. Preserved earlier C1 down-slope negative: parent Brier +0.000297071 and log loss +0.001515585, 2/4 parent blocks. Original new Controller response `cc35bb18…` explicitly stopped that exact recipe and proposed N1, rather than repeating it or declaring all down/PBP information useless.
2. N1 added a field-position-by-market-logit term and jointly fitted its coefficient with temperature, fixed alpha16. Actual research parent was C7; the evidence trigger was C1; the comparison incumbent was raw market. These are different roles. Source `c133df27…`, actual run commit `5b1ee069…`; four real fits, 87 predictions, 4.602 seconds. Independent result `03375e7f…`; independent learning `8979e981…`. Valid negative earned credit2, REVERT held, and exploration eligibility remained. Accepted feedback `e9a256fd…` was actually delivered in the next model input.
3. Original second Controller response `dcc7607d…` cited N1’s worse parent losses and 2/4 block wins as the reason to stop the exact field-position recipe. It also distinguished an earlier composite-pressure failure from a not-yet-isolated distance question. It selected N2, not a prearranged independent parallel model.
4. N2 added `u=t/(10+t)` times market logit, with t the causal pre-play required yards. Fixed10 is a project choice; goal-to-go means this is not always literal yards to a first down. Temperature and the new coefficient were jointly fitted with unchanged alpha16 and solver. Source `88b4f9e9…`, actual run commit `ba5d642b…`; four real fits, 87 predictions, 4.383 seconds. Independent result `b77c5026…` reconstructed all predictions exactly without fitting.
5. N2’s exact recipe worsened both parent losses and won 1/4 blocks. Separate learning review `c09dfcee…` passed, and native accepted feedback `be23c4f2…` was saved. Preserve the negative and code, stop the exact recipe, retain distinct-question eligibility. Its feedback will be saved for a later authorized batch; it has not been consumed by another Controller decision in this capped batch.

The trace is sequential feedback-driven candidate selection with parallel implementation/audit assistance. It is not two preselected models mislabeled as iteration. Only one candidate trained at a time. There were three AI helper roles: mechanical operations, implementation and independent review; Root alone executed account calls and fits and wrote authoritative state.

## What changed, and what did not

| Axis | Actual change | Supported evidence | Not established |
| --- | --- | --- | --- |
| Predictor C | N1 field-position slope; N2 required-yards slope | Actual code, tests, strict-past fits and paired predictions | Better predictor or pure data increment: basis and parameter count change together |
| Harness H | Exact prospective 2/8 authority binding: 12 added / 1 removed production lines, one module; reviewed operational preclaim recovery | Approved window worked; old windows remained closed; first-only execution preserved | General efficiency improvement, autonomous harness evolution or OS isolation |
| Researcher R | Existing factual memory/feedback accumulated and changed selection | C1→N1 and N1→N2 observed negative-evidence reuse | Causal benefit of memory, transfer, better scientific capacity or self-modified tools/workflow |
| Judge/data K | Unchanged | Same population, masks, time cuts, scoring and exclusions reconstructed | Untouched OOS, realtime availability or prospective edge |
| Base model M | Requested `gpt-6.1-sol`, pinned local CLI/runtime unchanged | Two original recorded transactions; serving snapshot unknown | Authenticated exact serving version, model post-training or gain attributable to RSI |

N1 has 233 production lines in one new module; N2 has 221. Both exceed the 200-line warning and received explicit independent semantic admission as one inseparable fit/predict/replay/entry component. They were not compressed to evade the warning. Existing solver, scorer and worker were not rewritten. This is controlled scope, not a claim that any 221-line change is intrinsically safe.

## Learning checkpoints, branches and memory

Prediction replacement, execution validity, research credit and exploration eligibility are separately recorded. N1’s independent credit2 is for a distinct valid hypothesis test, not for a score improvement. Credit is never added to Brier, does not loosen KEEP and grants no extra data, calls or fits. N2 independent learning review `c09dfcee…` and accepted feedback `be23c4f2…` also record credit2. Native branch `inconclusive` denotes eligibility under the recorder policy; the scorecard’s `REFUTED` tag denotes failure of this exact predeclared recipe, not statistical proof that the feature family lacks information.

The last actual Controller-selected global pool contains two branches, not a score-ranked top three:

| Branch | Why retained | Status |
| --- | --- | --- |
| C7 conditional market-calibration family | Verified earlier parent improvement; distinct conditional questions can still be tested | Both fresh recipes negative; exact recipes stopped; C7 parent retained |
| Archived B3 nonlinear causal-state representation | Material method diversity and unresolved conditional information | Retained, not trained in this batch |

Raw market incumbent is separate. REVERT does not erase N1/N2 code, evidence or potential for genuinely different descendants. Pool eligibility does not require automatically keeping every negative child active. This snapshot preserves the second Controller’s actual selection; it is not an invented post-N2 scientific decision.

The saved handoff memory should emphasize that the isolated down, field-position and distance alpha16 recipes failed conditional parent-increment tests; coefficient signs were unstable across fits; this does not refute all PBP or nonlinear state information. Avoid re-running exact stopped recipes. The next scientific choice remains Controller-owned. Observed use of memory has not been shown to improve cost or prediction against a no-memory control.

## Resources, failures and human coordination

Actual usage: 2 new attempts, 8 entered/completed fits, 174 candidate prediction versions on the SAME87 games; zero control refits, paid-provider calls or provider dollars, worker retries or account retries. Two original account calls consumed 333,112 input tokens and 3,824 output tokens, including 64 reported reasoning tokens; do not add reasoning a second time. Account/subagent CPU, total tokens and monetary cost are not fully metered.

Training-worker wall time totals 8.984 seconds; sampled peak child RSS is 139,888 KiB (about136.6MiB). One thread per candidate; RSS is polled, not an OS-hard bound. At final verification (23:47:07 UTC), elapsed batch time is 74.6 minutes. Most elapsed time went to implementation, tests, review and coordination—not fitting. Relevant full suites grew from245 to256 to267 unique tests; each candidate’s 11 focused tests is included, not added again. Producer, Root and independent reruns of the same suite do not multiply the unique test count. This is not a claim that every repository/legacy test is green.

Preserved failures and bounded repairs:

- N1 synthetic decimal-complement fixture was corrected to an exact binary fixture; production numerical tolerance was not relaxed. Missing R provenance was added in a separately reviewed v2 contract before training. Root shorthand/dry-request errors were corrected before execution.
- N2 Root supplied a relative contract path to an operation requiring an absolute repository path. It failed after the original three-event selection prefix, BEFORE worker claim, Train read or fitting. All original records were preserved. Two unactivated recovery drafts remained archived; independent review caught a missing explicit candidate-source guard, which was restored and mutation-tested in v3. Only v3 was activated, producing N2’s first/only worker start. This is a Supervisor operational error and repair, not a failed scientific test, Controller discovery credit or autonomous R evolution.
- Root initially used a wrong supplement field while saving post-run bookkeeping; that save failed without changing evidence, code, fits or scoring, then was corrected. This is coordination overhead, not experimental evidence.

Human supplied one fresh batch/payload approval, and no per-round hypothesis, algorithm, implementation repair or scientific continuation decision in this fresh batch. That does not mean a self-running unattended system: AI Supervisor instructions, handoffs and repairs were substantial. Measure end-to-end valid-experiment latency and total coordination/review cost, not only the nine seconds of worker execution.

## Boundaries and next batch

Frozen denominator195 games across42 dates;193 materialized,2 explicitly excluded. Checks87 games/20dates/7observedweeks; 22 initial fit dates followed by four5-date expanding checks. Q3 first pre-play clock≤08:00, strict prior market trade, maximum300-second staleness and home-token orientation remain fixed. These cutoff, fold, seed and model choices are project parameters, not asserted literature consensus. Same-game pairing and whole-group uncertainty prevent treating many plays or dates as independent game samples.

All results are repeatedly inspected historical opened-Train Discovery. Historical event time is not proven provider-publication/local-receive time. Dev/Final, new external acquisition/literature retrieval, paid providers, release and promotion remain closed. Existing account transport was separately authorized; there is no new data fetch. Trusted-host boundaries are not OS-enforced network isolation.

Supervisor recommendation, NOT an already-made next Controller decision: pass both newly accepted negatives and coordination costs to the next Controller; require a distinct, falsifiable question rather than another exact failed slope recipe. Let it choose whether to develop the retained nonlinear branch, change representation/training, or investigate already-authorized information. Keep the same task/judge and report its actual rationale, valid-experiment latency and total cost. A matched fixed-versus-evolving process pilot remains needed with equal initial memory/tools, base-model version, branch capacity, permissions and end-to-end budget; one trajectory cannot establish mechanism superiority. Freeze submissions before new independent/prospective results; do not rebrand these Train folds as untouched evaluation.

## Evidence locations

Repository source, contracts, original response references, independent result/learning reviews, acceptance and plans: `/Users/estelle/Developer/market-rsi/research/market_rsi/supervisor_harness/`. Append-only trace: `CHECKPOINT_PILOT_TRAJECTORY_2026-10-05.jsonl`.

Persistent, non-cloud artifacts: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/market-rsi-learning-checkpoint-continuation-20261005-01`. Each `n1`/`n2` has source-bound worker receipts, prediction CSV, scorecard, fit states, supplements and learning evidence. `cap_consumption_terminal.json` records the cap rejection and absent children. `CHECKPOINT_CONTINUATION_CLOSEOUT_2026-10-05.json` is the final exact acceptance/resource/state index. No raw Train files, credentials or live artifact tree are published or staged.
