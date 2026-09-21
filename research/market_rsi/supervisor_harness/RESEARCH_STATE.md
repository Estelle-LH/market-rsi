# Market RSI decision state — 2026-09-21, release-gate friction fixed locally

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Independently review and, only if authorized, publish the local release-gate fix before any fresh paid Gate 1 Controller decision. `market-rsi-gate1-controller-20260921-03` is terminal and cannot be retried. |
| Main working hypothesis | More years alone will not cure the evaluation and target problems. The 2023 public archive maps only 237/285 games under the strict rule; a frozen 12-game audit finds 5/9 sampled regular-season games with zero in-game fills, versus 59–79 in each of three sampled playoff games. Minute-price history is not proven to be trades or executable quotes. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | The revision-pinned archive has 237/285 strictly matched 2023 game identities, with 48 missing, including 47/92 Weeks 13–18 games. In the fixed 12-game audit, regular-season in-game fills are 17/4/11/0/0/8/0/0/0; playoff fills are 71/79/59. One zero-fill game has 1,020 minute-price timestamps but only one pregame value change. Full-season event-aligned label coverage, archive completeness/rights, price semantics and independent future dates remain unverified. |
| Highest-priority bottleneck | **P0 prediction-data admission is still blocked because no valid model-authored Gate 1 plan exists.** The v0.1.14 live sample chose a sensible question/source but failed closed: its tool call ended with the GLM template's empty `<|observation|>` marker and also contained one undeclared empty field. No plan or task was admitted. |
| Meaningful next progress | Review the two-file release-gate change. It permits documentation-only HEAD commits after a tag but compares every controlled current byte directly with the annotated tag; committed or uncommitted controlled-source drift still fails. Keep provider dispatch closed until a fresh release and separate paid authorization. |
| Do not spend time on | Further iCloud debugging, broad 2021–2022 AMM searching just to count five years, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | `codex/market-rsi-round1-v2`; v0.1.15 remains the latest published release. A local two-file publication verifier change has manifest `b87721914b3a90b133298598c9ae050da9a0b9aabca98d13ed394cd0e4ce60cb`. Thirty-three adjacent tests and 515/516 full tests passed; the sole unrelated error is the pre-existing memory-artifact hash drift. Zero-provider production-path canary `p0-gate1-production-cli-canary-20260921-12` passed with `$0`, no fetch/admission and no provider call. |
| Why this branch | The source audit removed a mistaken interpretation of 2023 catalog zeros, while the untouched-date audit exposed a stronger blocker. Model iteration on this cohort would not establish the intended benchmark. |
| Decision / review | **LOCAL RELEASE-GATE FIX VERIFIED; PUBLICATION AND PROVIDER DISPATCH CLOSED.** The fix removes a docs-only HEAD coupling without weakening exact source/tag equality. It is local, human-assisted, and does not authorize a tag, push or paid Controller sample. |

Evidence: `P0_GATE1_CONTROLLER_OUTPUT_REPAIR_REVIEW_2026-09-21.md`,
`P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
