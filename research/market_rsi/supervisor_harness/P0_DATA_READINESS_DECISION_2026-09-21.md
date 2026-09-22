# P0 data readiness — focused read-only decision, 2026-09-21

Question: can the current real-data artifacts support the first controlled prediction self-iteration cycle?

Answer: no. This is a data-admission result, not a model result or a request to expand general harness work.

| Season | Verified evidence | Missing for admission |
| --- | --- | --- |
| 2023 | 237/285 scheduled game identities matched in the revision-pinned archive. The fixed 12-game diagnostic found zero in-game fills in 5/9 sampled regular-season games. | 48 identity gaps; full-season actual-trade and event-label coverage; source-object/rights verification. The 12-game sample cannot be promoted to a season rate. |
| 2024 | Whole-cohort support audit: 284 mapped games, 407,225 historical trades; 60-second labels on 32,384/47,875 timed plays and 300-second labels on 43,506/47,875. | Formal source/rights admission and point-in-time/live-observability proof. This is support, not a self-iteration score. |
| 2025 | 285/285 schedule identities matched; one fixed game returned 2,148 trades. | Whole-season trades, PBP join, per-date labels, rights and access history. The old split has 42 Train, 11 scored Dev and 11 nominal Final dates; the Final is below the 20-untouched-date floor. |

The Gate 0 exposure ledger marks only one game `opened` by a direct local receipt and the other 284 `unknown`; prior documents report 163 opened Train games and 50 scored Dev games without a reconstructed per-game access chain. Unknown must not be relabelled untouched. The schedule-only 2026 Final candidate is not admitted; no market availability or access-log proof accompanies it.

Critical-path decision:

1. Preserve the reviewed synthetic Gate 1 result as *offline only*. It is not a real-data receipt.
2. Freeze and review the exact production source, then run its zero-provider canary. Release/push and a fresh paid Controller sample require separate explicit authorization under the current protocol.
3. Let the first valid Controller decision choose one bounded public/Train-only source investigation. The preceding invalid answer suggested a 2025 Polymarket season trade-access audit, but it is not executable authority.
4. Require source/rights, game-to-market, actual-fill, PBP-clock, missing-label and exposure receipts before an admitted three-season pilot. Report failure if 2023 remains too sparse or 2025 is unavailable; do not fill missing trades with zero or switch target after seeing Dev.
5. Keep prediction experiment design moving, but do not call a synthetic canary or an opened-Train diagnostic a scored recursive cycle. A formal Final needs at least 20 genuinely untouched dates plus a Train/Dev-only precision check.

No network request, provider call, public fetch, model fit, Dev/Final read, or spend was made for this review.

Evidence: `P0_FIVE_SEASON_DATA.md`; `P0_DATA_ADMISSION_ORCHESTRATION_2026-09-18.md`; `artifacts/p0-data-admission-gate0-20260918-01/exposure-ledger.json`; `artifacts/p0-2025-schedule-role-date-audit-20260917-01/date-audit.json`; `artifacts/nfl-2024-full-cohort-support-20260916-01/manifest.json`; `RESEARCH_STATE.md`.
