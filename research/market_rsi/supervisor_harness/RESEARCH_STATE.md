# Market RSI decision state — 2026-09-22, v0.1.21 format repair released; real data still blocked

Keep this page compact. Replace stale decisions; do not append a transcript.
Detailed evidence stays in the daily log and immutable run artifacts.

| Item | Current decision state |
| --- | --- |
| Ultimate objective | Test whether an iterating LLM researcher can improve NFL prediction-market price forecasts over a strong ordinary model on genuinely unseen dates, under the same data and evaluation rules. |
| Immediate question | Can the first response through the newly published five-field short-choice interface produce a valid, reviewable data-investigation plan? The v0.1.21 strict parser and shorter interface passed independent integrated review and a fresh postrelease zero-provider production-CLI canary. The two old responses remain terminal failures, not candidates for repair or reuse. No new model response has been taken through v0.1.21. |
| Main working hypothesis | More years alone will not cure the evaluation and target problems. The 2023 public archive maps only 237/285 games under the strict rule; a frozen 12-game audit finds 5/9 sampled regular-season games with zero in-game fills, versus 59–79 in each of three sampled playoff games. Minute-price history is not proven to be trades or executable quotes. |
| Best known evidence | 2025 opened-Train histogram-based gradient boosting (HGB, boosted decision trees) MSE 0.0013540355 vs Ridge (regularized linear regression) 0.0016700963 (18.9% lower, not self-iteration/OOS). On the 2024 full 284-game source, 60-second labels cover 32,384/47,875 timed plays (67.64%); 300-second labels cover 43,506/47,875 (90.87%). No new held-out model result. |
| Uncertainties | The revision-pinned archive has 237/285 strictly matched 2023 game identities, with 48 missing, including 47/92 Weeks 13–18 games. In the fixed 12-game audit, regular-season in-game fills are 17/4/11/0/0/8/0/0/0; playoff fills are 71/79/59. One zero-fill game has 1,020 minute-price timestamps but only one pregame value change. Full-season event-aligned label coverage, archive completeness/rights, price semantics and independent future dates remain unverified. |
| Highest-priority bottleneck | **P0 prediction-data admission remains blocked: there is no admitted real Train catalog or validated Controller-led acquisition plan.** Two one-shot GLM decisions failed formatting, for different reasons; neither is a data result. v0.1.21 has repaired the engineering boundary but has not been tested on a new live Controller response. No fetch, rights admission or prediction fit occurred. |
| Meaningful next progress | The next discriminating step is one new Controller data-investigation decision through v0.1.21, only after fresh authorization and full unique-ID, global-state, process and budget checks. Independently review its first response before any public source fetch. A new packet has been generated without provider/fetch: 3310 input tokens, 2750 output maximum, $0.0494991 hard upper. Do not resample for score or formatting. If a valid plan emerges, source rights, exact public request and real Train catalog still require separate gates. |
| Do not spend time on | Further iCloud debugging, broad 2021–2022 AMM searching just to count five years, generic harness polish, target tuning or paid model searches on the one-season cohort. Do not silently mix exchanges or reopen old Dev/Final. |
| Current branch | `codex/market-rsi-round1-v2`; annotated `market-rsi-protocol-v0.1.21` is published on the user's fork at `f06214b3bb521096078d897fe60ec9ba589c00c6`, with 324-file source digest `872f05ae48fa49deeb811bc6ca4705652168f198b5f1f9d69d3ce172ad0986da`. Independent integrated review, 132 Gate 1 tests and 20 parser/schema tests passed. Fresh postrelease zero-provider no-catalog canary `market-rsi-gate1-v021-postrelease-canary-20260922-01` passed. Other documents/logs remain locally dirty and were not pushed. |
| Why this branch | The source audit removed a mistaken interpretation of 2023 catalog zeros, while the untouched-date audit exposed a stronger blocker. Model iteration on this cohort would not establish the intended benchmark. |
| Decision / review | **NO VALID GATE 1 PLAN OR PREDICTION RESULT YET.** The v0.1.18 and v0.1.20 first responses are immutable invalid outcomes, terminal-metered at $0.01666737 and $0.01790424. The second used an exact rule in raw text, but malformed `<arg_key>`/`<arg_value>` tags around `max_minutes_placeholder` caused the then-current adapter to miss `question_id`; the later strict parser rejects those raw tags. The earlier “well-formed extra field” diagnosis was incorrect. v0.1.21 publication and zero-provider canary do not establish future model compliance, real Train admission or prediction gain. No fetch, training or Dev/Final read. |

Evidence: `P0_GATE1_V016_LIVE_FAILURE_REVIEW_2026-09-21.md`,
`P0_GATE1_V017_LIVE_FAILURE_REVIEW_2026-09-21.md`,
`P0_GATE1_TRUSTED_SCHEMA_REPAIR_REVIEW_2026-09-21.md`,
`P0_GATE1_RIGHTS_POLICY_REPAIR_REVIEW_2026-09-21.md`,
`P0_GATE1_CONTROLLER_OUTPUT_REPAIR_REVIEW_2026-09-21.md`,
`GATE1_CANARY_RUNNER_AND_RECEIPTS_2026-09-21.md`,
`../PREDICTION_EXPERIMENT_DESIGN_2026-09-21.md`,
`../PREDICTION_EXPERIMENT_DRAFT_2026-09-21.json`,
`P0_FIVE_SEASON_DATA.md`, `NEXT_PREDICTION_CYCLE_2026-09-16.md`,
`DAILY_LOG_2026-09-16.md`, `LOCAL_STORAGE_RECOVERY_2026-09-16.md`.
