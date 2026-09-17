# Market RSI decision state — 2026-09-16 20:32 EDT

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Can we obtain and admit roughly five completed NFL seasons of comparable, time-resolved market and game data before designing the formal benchmark? |
| Main working hypothesis | The one-season 2024 trade audit and limited 2025 opened-Train examples are too narrow for a credible multi-year result. Public catalogs suggest a modern contract-format break around 2024–2025, but five-season trade availability is still unverified; a 60-second target also loses too many labels in quiet 2024 games. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | Older Polymarket game-winner pages exist and one 2023 market yielded a timestamped public fill, but two sampled 2021/2022 market-scoped queries returned zero, consistent with the documented roughly three-year floor. Whether lawful archived 2021–2022 fills/quotes exist at season scale remains unknown; so do 2025 event-aligned coverage, Betfair NFL coverage/US delivery/rights/cost, cross-year target comparability and genuinely untouched dates. |
| Highest-priority bottleneck | P0 five-season data inventory, acquisition and quality admission. Only 2024 full-season market support has been audited; its raw batches are not yet staged locally. No multi-year training set is verified. |
| Meaningful next progress | The corrected Polymarket screen has 284 modern 2024 moneylines and 285/285 2025 schedule-matched moneylines; a one-game 2025 canary has 2,148 trades, not a season audit. Exact old-event smoke checks found a retrievable 2023 fill but zero rows from sampled 2021/2022 market-scoped requests. This narrows the direct free API route, not the existence of historic fills. Next seek an itemized lawful archive/provider quote for missing older years and decide separately if a 2025 season-wide audit is worthwhile. After P0 admission, freeze target/split and rerun matched strong baselines before self-iteration. |
| Do not spend time on | Further iCloud debugging, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | Local-only `codex/market-rsi-round1-v2`, published executable release `dsh-v1.6.19`; no active paid process. The sole budget authority remains the migrated local $200 ledger, not a new cap. |
| Why this branch | It preserves the audited 2024 feasibility evidence but refuses to turn one year into a five-year benchmark. Data coverage/rights are now the direct uncertainty; immediate algorithm search would answer the wrong question. |
| Decision / review | **INTERRUPT** formal model launch and **REPLAN** to `P0_FIVE_SEASON_DATA.md`. The exact older-trade smoke check now supports 2023 retrievability but leaves 2021–2022 missing via this market-scoped route; it did not establish five years or licensing. No vendor quote/separate cap or five-year completeness has been verified. Re-review after an archive/provider coverage and rights response. |

Evidence: `P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
