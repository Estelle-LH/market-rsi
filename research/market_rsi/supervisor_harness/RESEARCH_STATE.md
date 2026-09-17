# Market RSI decision state — 2026-09-16 23:56 EDT

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Is there a genuinely untouched >=20-date Final and a comparable, event-aligned target for 2023–2025? The currently sealed 2025 40-game block has only 11 distinct dates. |
| Main working hypothesis | More years alone will not cure the evaluation and target problems. The 2023 public archive maps only 237/285 games under the strict rule, and fixed game samples have sparse actual fills; minute-price history varies but may include carried-forward values and is not proven to be trades or executable quotes. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | The revision-pinned archive has 237/285 strictly matched 2023 game identities, with 48 missing, especially Weeks 13/17/18. Three fixed games have 0/6/137 in-game on-chain fills in a +5h window, versus 300 minute-price points each; whether those prices encode carry-forward, last trade, mid or executable quotes is not established. Full-season label coverage, source completeness/rights and independent future dates are unverified. |
| Highest-priority bottleneck | The proposed 2023 Train / 2024 Dev / 2025 Final split is **not admissible with the existing sealed 40-game Final**: it has 11 dates, below the predeclared 20-date floor; 2025 Train and old Dev were already inspected. No paid model run until a new legitimately untouched time block and a common label semantics pass. |
| Meaningful next progress | The 2023 identity screen maps 237/285 (83.16%) NFL games, not 237 usable training games; sampled regular-season fills are sparse. Historical price series has 1,019–1,020 minute points per sampled window and 34–133 actual value changes, but its semantics remain open. Make a read-only 2025 exposure/date inventory without opening protected prices/labels; document the exact target/rights gap and identify an independent later period, rather than keeping the old 11-date Final as formal confirmation. |
| Do not spend time on | Further iCloud debugging, broad 2021–2022 AMM searching just to count five years, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | Local-only `codex/market-rsi-round1-v2`, published executable release `dsh-v1.6.19`; no active paid process. The sole budget authority remains the migrated local $200 ledger, not a new cap. |
| Why this branch | The source audit removed a mistaken interpretation of 2023 catalog zeros, while the untouched-date audit exposed a stronger blocker. Model iteration on this cohort would not establish the intended benchmark. |
| Decision / review | **REPLAN, P0 STILL CLOSED.** Three completed comparable seasons remain the minimum *candidate*, five the stronger primary target; neither is admitted. The existing sealed 2025 block can only be a labelled 11-date pilot, not formal Final. First verify independent dates and target semantics; do not open Dev/Final, purchase unquoted data or spend the Tinker cap. |

Evidence: `P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
