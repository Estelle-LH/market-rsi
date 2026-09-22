# Market RSI decision state — 2026-09-21, trusted-schema repair passes offline

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Independently review and commit the local trusted-schema repair. It removes fixed protocol metadata from model output while keeping every scientific field exact. Publication and provider execution remain closed. |
| Main working hypothesis | More years alone will not cure the evaluation and target problems. The 2023 public archive maps only 237/285 games under the strict rule; a frozen 12-game audit finds 5/9 sampled regular-season games with zero in-game fills, versus 59–79 in each of three sampled playoff games. Minute-price history is not proven to be trades or executable quotes. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | The revision-pinned archive has 237/285 strictly matched 2023 game identities, with 48 missing, including 47/92 Weeks 13–18 games. In the fixed 12-game audit, regular-season in-game fills are 17/4/11/0/0/8/0/0/0; playoff fills are 71/79/59. One zero-fill game has 1,020 minute-price timestamps but only one pregame value change. Full-season event-aligned label coverage, archive completeness/rights, price semantics and independent future dates remain unverified. |
| Highest-priority bottleneck | **P0 prediction-data admission is still blocked because no valid Gate 1 plan exists.** The v0.1.17 missing-schema cause is now repaired offline: trusted code injects the fixed version label; model-supplied schema or any missing/extra scientific field still fails. |
| Meaningful next progress | Review and commit the local repair, then seek explicit authority for a new release. After publication, rerun the production-path zero-provider canary. Any fresh provider sample requires separate authorization and a new permanent ID. |
| Do not spend time on | Further iCloud debugging, broad 2021–2022 AMM searching just to count five years, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | `codex/market-rsi-round1-v2`; v0.1.17 is published at `191e03e`. Local commits `4fa02dd` (trusted-schema repair) and `b9095a7` (failure/repair reviews) are two commits ahead. The 318-file unpublished manifest is `69b0ea27…af1dd`; 55 focused and all 516 full-suite tests pass, and adapter `-06`, outer `-04`, production-CLI `-16` canaries pass with zero provider calls/cost/fetch/admission. |
| Why this branch | The source audit removed a mistaken interpretation of 2023 catalog zeros, while the untouched-date audit exposed a stronger blocker. Model iteration on this cohort would not establish the intended benchmark. |
| Decision / review | **TRUSTED-SCHEMA REPAIR PASSES OFFLINE; PUBLICATION AND PROVIDER DISPATCH CLOSED.** Fifty-five focused and all 516 full-suite tests pass; three fresh zero-provider canaries pass. No model fit, public fetch, formal admission or Dev/Final read occurred. |

Evidence: `P0_GATE1_V016_LIVE_FAILURE_REVIEW_2026-09-21.md`,
`P0_GATE1_V017_LIVE_FAILURE_REVIEW_2026-09-21.md`,
`P0_GATE1_TRUSTED_SCHEMA_REPAIR_REVIEW_2026-09-21.md`,
`P0_GATE1_RIGHTS_POLICY_REPAIR_REVIEW_2026-09-21.md`,
`P0_GATE1_CONTROLLER_OUTPUT_REPAIR_REVIEW_2026-09-21.md`,
`../PREDICTION_EXPERIMENT_DESIGN_2026-09-21.md`,
`../PREDICTION_EXPERIMENT_DRAFT_2026-09-21.json`,
`P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
