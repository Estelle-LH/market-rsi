# Market RSI decision state — 2026-09-29, predictive-autonomy work completed

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the batch report, independent reviews and immutable artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating research Agent can discover, implement and validate repeatable probability-prediction improvements over decision-time market probability and strong ordinary models, then transfer that capability across time or domain. |
| Immediate result | The requested feedback-dependent loop ran through real prediction experiments. Three candidates were attempted: one failed pre-fit feasibility, two completed 4 chronological fits and 87 paired predictions each. Both valid candidates were independently reviewed and REVERT. |
| In-game incumbent | `InGameWinProbabilityTrainDiagnostic-v0-raw_market`: equal-event Brier/log loss `0.1419525290 / 0.4296707847` on 87 opened-Train chronological checks, 20 dates and 7 weeks. It remains unchanged. |
| Candidate 1 | `InGamePreAnchorMomentumOffsetLogistic-v4`: invalid/cooldown. Three mandatory outer-fit games had reference ages `334/419/612s`, above the frozen `300s` maximum. Zero fits and zero predictions; this is an execution-feasibility failure, not a scientific refutation of momentum. |
| Candidate 2 | `InGameIdentityAnchoredMarketCalibration-v1`: Brier/log loss `0.1436504644 / 0.4335652209`; better than ordinary but worse than raw market by `+0.0016979354 / +0.0038944362`, with candidate Brier wins versus raw `0/4`. Exact route refuted/stopped; REVERT. |
| Candidate 3 | `InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4`: `0.1419536874 / 0.4296330177`; versus raw market Brier `+0.0000011584` and log loss `-0.0000377670`, candidate Brier wins versus raw `1/4`, date/week Brier intervals both cross zero. Exact route refuted/stopped; REVERT. |
| Feedback dependency | Candidates 1 and 2 were the parallel first generation. Their verified outcomes caused the Controller to abandon the stale momentum route, stop the calibration route, and then choose candidate 3 because its causal feature covered all 193 materialized games. Candidate 3's result then stopped that exact stratified route. |
| Active research pool after close | Incumbent remains a separate comparator. Two future question slots are retained: market-freshness interaction (recommended next) and a coarse causal-state residual backup. No third slot is filled mechanically. Exact calibration and prior-play-stratification routes are stopped; all artifacts remain archived. |
| Resource result | `18:19:47–19:06:08 EDT`, about 46 minutes; 3 attempts, 2 scored runs, 8 fits, 174 candidate prediction rows, zero retries/control refits, zero provider/network/cost. No round-by-round user intervention. |
| Scheduler bookkeeping | The combined three-attempt research work is complete. Primary v2 `...-03` is persisted at `2/3`, no active attempt and `stopped_reason=null` because it cannot schedule a singleton pool; recovery `...-04` is formally closed at `1/1`, `max_attempts_reached`. |
| Research mechanism evidence | The loop autonomously optimized prediction candidates: verified feedback changed the later choice, implementation, execution and stop decision. It did not modify the research tools/workflow. No matched fixed-process control ran, so there is no evidence that self-iteration outperforms a fixed research process. |
| Evaluation boundary | All scores are repeatedly inspected opened-Train Discovery. Protected Dev/Final, external acquisition, paid provider, publication, deployment and promotion remain closed. Historical event time does not establish realtime provider-publish/local-receive availability. |
| Next separately budgeted experiment | Controller recommends `InGameMarketFreshnessInteractionOffset-v1`: first prove full causal fill-age coverage, then fit one frozen market-logit-offset interaction on the same protocol. This is a recommendation only, not an authorized attempt. |
| Formal confirmation | Before seeing a new evaluation result, freeze the candidate-selection rule and submission; later evaluate on games not used for selection, ideally future-settling events after model/version freeze. |
| Detailed report | `INGAME_PREDICTIVE_AUTONOMY_BATCH_REPORT_2026-09-29.md` |

Decision: **THE COMBINED AUTONOMOUS PREDICTOR-OPTIMIZATION WORK IS COMPLETE; NO CANDIDATE BEAT THE RAW-MARKET INCUMBENT UNDER THE FROZEN RULE; MECHANISM SUPERIORITY REMAINS UNTESTED.**
