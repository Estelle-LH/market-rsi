# Market RSI decision state — 2026-09-16 17:07 EDT

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Is the historical target/data cohort sound enough to support a fair, nontrivial benchmark before fitting more candidates? |
| Main working hypothesis | A 60-second post-play trade-price target loses too many labels in quiet games; a longer predeclared horizon may improve coverage, but any target change needs new same-row baselines and cannot inherit the old MSE result. This is not yet a model-quality conclusion. |
| Best known evidence | 2025 opened-Train fixed HGB MSE 0.0013540355 vs Ridge 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | Whether the 300-second objective is useful rather than merely less missing; whether source/publish/receive timing makes a historically aligned play feature usable live; whether a strong CatBoost/LightGBM/HGB baseline can be beaten on untouched dates; how much new historical data can be admitted without leakage. |
| Highest-priority bottleneck | Freeze a defensible target and comparable full-cohort Train rows before another model search. The local execution tree has the audit's aggregate receipts, but not the frozen 2024 source/batch files needed for target-value analysis. |
| Meaningful next progress | First stage the already-frozen opened-Train source/batches from an authorized resident archive into the local tree with exact hash checks (no new data purchase or iCloud retry loop). Then measure 60s/300s target-value variation, per-game/date missingness and a zero-change/persistence comparator on matching eligible rows; lock one objective and rerun matched strong baselines. |
| Do not spend time on | Further iCloud sync debugging, more generic harness polish or another paid controller call before objective/baseline admission; do not reopen old Dev/Final to choose target. |
| Current branch | Local-only `codex/market-rsi-round1-v2`, published executable release `dsh-v1.6.19`; no active paid process. The sole budget authority remains the migrated local $200 ledger, not a new cap. |
| Why this branch | It uses the already audited full 2024 source coverage and prevents another paid proposal from optimizing an unstable target. Immediate algorithm search or new harness features would confound data/target changes with method changes. |
| Decision / review | **REPLAN** from infrastructure recovery to opened-Train objective and strong-baseline work. The iCloud workaround is complete; research improvement remains unproven. Re-review after the first target-support decision or ~5–10 meaningful actions, whichever comes first. |

Evidence: `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
