# Market RSI decision state — 2026-09-16 17:40 EDT

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Can we obtain and admit roughly five completed NFL seasons of comparable, time-resolved market and game data before designing the formal benchmark? |
| Main working hypothesis | The one-season 2024 trade audit and limited 2025 opened-Train examples are too narrow for a credible multi-year result. Public catalogs suggest a modern contract-format break around 2024–2025, but five-season trade availability is still unverified; a 60-second target also loses too many labels in quiet 2024 games. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | Whether comparable NFL game markets and timestamped trades/quotes exist for 2021–2023; whether 2025's 271 metadata candidates have event-aligned trades; vendor rights and cost for gaps; whether one 60s/300s objective remains comparable across years; which dates remain genuinely untouched. |
| Highest-priority bottleneck | P0 five-season data inventory, acquisition and quality admission. Only 2024 full-season market support has been audited; its raw batches are not yet staged locally. No multi-year training set is verified. |
| Meaningful next progress | The Polymarket series-specific metadata screen is complete, but not trade admission: 2024 has 284 modern game-moneyline candidates, 2025 has 271, older series differ. Next check other catalog/provider paths and actual trade granularity, then get a concrete data quote for gaps. After P0 admission, choose target and rerun matched zero-change, HGB and other strong baselines; only then test self-iteration. |
| Do not spend time on | Further iCloud debugging, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | Local-only `codex/market-rsi-round1-v2`, published executable release `dsh-v1.6.19`; no active paid process. The sole budget authority remains the migrated local $200 ledger, not a new cap. |
| Why this branch | It preserves the audited 2024 feasibility evidence but refuses to turn one year into a five-year benchmark. Data coverage/rights are now the direct uncertainty; immediate algorithm search would answer the wrong question. |
| Decision / review | **INTERRUPT** formal model launch and **REPLAN** to `P0_FIVE_SEASON_DATA.md`. The user authorized pursuing paid data, but no vendor price/separate cap or five-year completeness has been verified. Re-review after the first five-season inventory or ~5–10 meaningful actions. |

Evidence: `P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
