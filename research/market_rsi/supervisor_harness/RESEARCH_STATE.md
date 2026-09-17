# Market RSI decision state — 2026-09-16 22:45 EDT

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Can we obtain and admit roughly five completed NFL seasons of comparable, time-resolved market and game data before designing the formal benchmark? |
| Main working hypothesis | The one-season 2024 trade audit and limited 2025 opened-Train examples are too narrow for a credible multi-year result. Public catalogs suggest a modern contract-format break around 2024–2025, but five-season trade availability is still unverified; a 60-second target also loses too many labels in quiet 2024 games. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | A revision-pinned, publisher-licensed free on-chain archive contains timestamped AMM rows for seven sampled 2021/2022 NFL winner markets, correcting the earlier impression from empty Data API queries. Whole-season NFL coverage, archive completeness, in-game label density, AMM/CLOB target comparability, 2023 and 2025 event-aligned coverage, downstream rights beyond the publisher's stated CC-BY licence, and genuinely untouched dates remain unverified. |
| Highest-priority bottleneck | P0 five-season data inventory, acquisition and quality admission. Only 2024 full-season market support has been audited; its raw batches are not yet staged locally. No multi-year training set is verified. |
| Meaningful next progress | The corrected Polymarket screen has 284 modern 2024 moneylines and 285/285 2025 schedule-matched moneylines; a one-game 2025 canary has 2,148 trades, not a season audit. A free on-chain archive canary now found 251/406 November 2021 regular-season AMM rows, 332–870 rows in each of four January 2022 playoff winner markets, and 420 in one October 2022 game. These are selected raw-trade counts, not usable labels or a model score. Next map the full old-season NFL catalog and measure per-game event-clock support before any purchase or model run. |
| Do not spend time on | Further iCloud debugging, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | Local-only `codex/market-rsi-round1-v2`, published executable release `dsh-v1.6.19`; no active paid process. The sole budget authority remains the migrated local $200 ledger, not a new cap. |
| Why this branch | It preserves the audited 2024 feasibility evidence but refuses to turn one year into a five-year benchmark. The newly found free AMM source should be tested before paying a vendor; immediate algorithm search would answer the wrong question. |
| Decision / review | **CONTINUE P0**, not the formal model launch. The free archive is a material source lead and seven exact-market canaries pass, but no full-season completeness, cross-era label equivalence or independently verified licence/rights determination exists. Re-review after a schedule-matched old-season coverage audit. Do not spend the Tinker cap or purchase data yet. |

Evidence: `P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
