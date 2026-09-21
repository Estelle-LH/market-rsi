# Market RSI decision state — 2026-09-21, vNext Gate 1 repair verified offline

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Independently review the local vNext Gate 1 repair, then decide whether to authorize a new commit/tag/push and post-publication zero-provider canary. `market-rsi-gate1-controller-20260921-03` is terminal and cannot be retried. |
| Main working hypothesis | More years alone will not cure the evaluation and target problems. The 2023 public archive maps only 237/285 games under the strict rule; a frozen 12-game audit finds 5/9 sampled regular-season games with zero in-game fills, versus 59–79 in each of three sampled playoff games. Minute-price history is not proven to be trades or executable quotes. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | The revision-pinned archive has 237/285 strictly matched 2023 game identities, with 48 missing, including 47/92 Weeks 13–18 games. In the fixed 12-game audit, regular-season in-game fills are 17/4/11/0/0/8/0/0/0; playoff fills are 71/79/59. One zero-fill game has 1,020 minute-price timestamps but only one pregame value change. Full-season event-aligned label coverage, archive completeness/rights, price semantics and independent future dates remain unverified. |
| Highest-priority bottleneck | **P0 prediction-data admission is still blocked because no valid model-authored Gate 1 plan exists.** The v0.1.14 live sample chose a sensible question/source but failed closed: its tool call ended with the GLM template's empty `<|observation|>` marker and also contained one undeclared empty field. No plan or task was admitted. |
| Meaningful next progress | Review the two source/test files and failure report. If accepted and explicitly authorized, publish a fresh annotated release to the user's fork and repeat the production-path zero-provider canary under those exact bytes. Do not dispatch another provider sample without separate authorization and a fresh permanent ID. |
| Do not spend time on | Further iCloud debugging, broad 2021–2022 AMM searching just to count five years, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | `codex/market-rsi-round1-v2`; v0.1.14 live ID `market-rsi-gate1-controller-20260921-03` used one sample (1,393 input / 582 output tokens), metered `$0.01384128`, and failed closed with no fetch/admission. Local vNext accepts only one empty GLM observation terminator, rejects undeclared fields, and passed adapter/transaction/production zero-provider canaries plus 515/516 full tests; the sole unrelated error is the pre-existing memory-artifact hash drift. Pinned vNext input is 1,406 tokens and worst-case upper `$0.04415796`. |
| Why this branch | The source audit removed a mistaken interpretation of 2023 catalog zeros, while the untouched-date audit exposed a stronger blocker. Model iteration on this cohort would not establish the intended benchmark. |
| Decision / review | **LOCAL REPAIR VERIFIED; PUBLISH AND PROVIDER DISPATCH CLOSED.** The captured failed response remains invalid because its undeclared field is not removed. Fresh zero-provider canaries passed with no fetch/admission. No commit/tag/push or further paid Controller sample is authorized by this offline repair. |

Evidence: `P0_GATE1_CONTROLLER_OUTPUT_REPAIR_REVIEW_2026-09-21.md`,
`P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
