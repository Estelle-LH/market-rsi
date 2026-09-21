# Market RSI decision state — 2026-09-21, local verification noise separated from real failures

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | If authorized, publish the reviewed local release-gate and test-classification fixes; a fresh paid Gate 1 Controller decision still needs separate authorization. `market-rsi-gate1-controller-20260921-03` is terminal and cannot be retried. |
| Main working hypothesis | More years alone will not cure the evaluation and target problems. The 2023 public archive maps only 237/285 games under the strict rule; a frozen 12-game audit finds 5/9 sampled regular-season games with zero in-game fills, versus 59–79 in each of three sampled playoff games. Minute-price history is not proven to be trades or executable quotes. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | The revision-pinned archive has 237/285 strictly matched 2023 game identities, with 48 missing, including 47/92 Weeks 13–18 games. In the fixed 12-game audit, regular-season in-game fills are 17/4/11/0/0/8/0/0/0; playoff fills are 71/79/59. One zero-fill game has 1,020 minute-price timestamps but only one pregame value change. Full-season event-aligned label coverage, archive completeness/rights, price semantics and independent future dates remain unverified. |
| Highest-priority bottleneck | **P0 prediction-data admission is still blocked because no valid model-authored Gate 1 plan exists.** The v0.1.14 live sample chose a sensible question/source but failed closed: its tool call ended with the GLM template's empty `<|observation|>` marker and also contained one undeclared empty field. No plan or task was admitted. |
| Meaningful next progress | Publish the local repair only after authorization, rerun the zero-provider production-path canary on those exact bytes, then seek separate authority for one fresh Gate 1 sample. A valid Controller plan is required before any data fetch or admission. |
| Do not spend time on | Further iCloud debugging, broad 2021–2022 AMM searching just to count five years, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | `codex/market-rsi-round1-v2`; v0.1.15 remains the latest published release. Local commit `5a6d5de` contains the release-gate repair; the local follow-up classifies two environment-dependent integration checks. The pinned-runtime full suite is 516/516 successful with two explicit skips: absent legacy runtime artifacts in this source-only checkout and unavailable host `ps` access in the restricted test sandbox. Production artifact integrity and trainer RSS enforcement were not weakened. Zero-provider production-path canary `p0-gate1-production-cli-canary-20260921-12` passed with `$0`, no fetch/admission and no provider call. |
| Why this branch | The source audit removed a mistaken interpretation of 2023 catalog zeros, while the untouched-date audit exposed a stronger blocker. Model iteration on this cohort would not establish the intended benchmark. |
| Decision / review | **LOCAL OPERATIONAL FIXES VERIFIED; PUBLICATION AND PROVIDER DISPATCH CLOSED.** The release check still requires exact controlled bytes. Environment-dependent integrations are now labelled instead of reported as artifact corruption or code failure. These are local, human-assisted changes and do not authorize a tag, push or paid Controller sample. |

Evidence: `P0_GATE1_CONTROLLER_OUTPUT_REPAIR_REVIEW_2026-09-21.md`,
`P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
