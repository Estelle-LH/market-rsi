# P0 prediction-data admission: Supervisor orchestration plan

Date: 2026-09-18. Status: **Gate 0 metadata inventory executed; Gate 5 ruled out old Final and froze a schedule-only future candidate; Gates 1–7 are not admitted or complete**. The machine-checkable plan and receipts are in `artifacts/p0-data-admission-gate0-20260918-01/`; dispatch structure passed, but exact Gate 1 readiness is blocked by the live Controller→B gate and whole-plan resolution remains rejected. This plan addresses data and an independent test period, not GLM/local-B connectivity. It does not alter the frozen 60-second benchmark, open old Dev/Final, authorize purchases, or launch a paid model.

## 1. What we are trying to prove

The first controlled question is whether an iterating researcher improves NFL prediction-market price-change forecasts over a strong ordinary predictor on the **same eligible plays** and **genuinely unseen dates**. Before any such comparison, we need a versioned, legally usable table of real market events joined to independently sourced play-by-play (PBP), plus a test period the researcher and human designers did not use to select features, targets, algorithms or stopping rules.

The present gate is not “the data are too small” in the abstract. It is four concrete failures:

1. A 2023 public archive strictly matches 237/285 scheduled games; 48 are unmatched, with late-season concentration. A fixed 12-game fill diagnostic has 5/9 regular-season games with zero in-game on-chain fills. That sample is not a full-season rate.
2. The 2024 whole-season historical event-clock audit finds 284 mapped games, 407,225 trades and 47,875 timed PBP plays. A real future trade within 60 seconds is available for 32,384 plays (67.64%); within 300 seconds for 43,506 (90.87%). This is support, not a model score, live-availability proof or formal Train admission.
3. The 2025 catalog maps 285/285 game identities but only one 2,148-fill game has a direct trade canary. Whole-season fills, PBP alignment, labels and research-use rights are not audited.
4. The old 2025 split assigns 195 Train games on 42 dates, 50 already-scored Dev games on 11 dates and 40 nominally sealed Final games on **11 dates**. The predeclared formal floor is 20 untouched dates. Local receipts directly prove one Train game opened; contemporary documents separately report 163 opened Train and all 50 scored Dev. The original per-game access chain is absent locally. Unknown exposure cannot be promoted to untouched.

Evidence: `P0_FIVE_SEASON_DATA.md`, `AGENT_LOG_DATA_ADMISSION_2026-09-18.md`, and the already-frozen manifests under `artifacts/p0-*` and `artifacts/nfl-2024-full-cohort-support-20260916-01/`.

## 2. Ownership: who decides and who can see what

| Role | Owns | Must not do |
| --- | --- | --- |
| Supervisor (Codex) | Frozen data/evaluation gates, task queue, source rights, budget, global state, provenance, independent acceptance or rejection. Publishes a factual work packet and catches stalls. | Pick a favorable source/date after seeing scores; rewrite a Controller decision; call its own audit GLM self-improvement. |
| GLM Controller, **after its live path is admitted** | Choose one next bounded source investigation, joining/cleaning hypothesis, or algorithmic data-quality method from allowed public/Train-only evidence. Explain expected evidence, cost/time bound and stop rule before B runs. | Read sealed Final values, use old scored Dev as new test, create a purchase, claim missing rows are zero movement, execute code on trusted Mac. |
| B Researcher in local Docker, **after arbitrary-task isolation is admitted** | Execute the Controller's exact allowed task: public-source research, metadata mapping, Train-only code or diagnostic; emit complete tool/event logs, hashes and errors. | Reach Supervisor keys/evaluator/GLM directly; change protected state or sealed files; pull unlimited data. |
| Independent data auditor/runner | Recompute counts and hashes from permitted source objects; verify role/date isolation, label semantics, exclusions, access ledger and rights; generate a signed pass/fail receipt. | Let Controller self-grade data admission or silently repair gaps. |

**Current reality:** the live GLM→broker→B research path has not passed authorship and arbitrary-code isolation checks. Until it does, Supervisor may do only bounded public or nonsealed metadata diagnostics, clearly marked as Supervisor work. The two 2026-09-18 subagent audits were not GLM decisions. The first real Controller task below is a **future dispatch packet**, not a claim it has run.

## 3. Non-negotiable boundaries and cost

- Preserve the old 2025 Train/Dev/Final assignment and all prior score/exposure records. Do not open old sealed Final prices, outcomes, labels or predictions; do not reclassify the 50 scored Dev games.
- Keep every scheduled game and date in a denominator, including unmatched, zero-fill and malformed cases. Missing 60-second trades produce a missing label with a reason, **not** a zero movement. Price-history buckets are observations, not necessarily distinct fills or executable quotes.
- A new target (e.g. 300 seconds), a different exchange, a combined exchange cohort, or an 11-date diagnostic is a **new version and separate claim**. Decide and freeze it before looking at its Dev/Final outcomes; never silently substitute it for the old 60-second formal test.
- Polymarket and Kalshi are separate source cohorts unless a predeclared transfer/comparison protocol justifies combining them. Do not buy or bulk-download to make a coverage percentage look better.
- The existing $200 Tinker experiment cap is not a data-purchase budget. Public metadata checks have $0 provider spend. Any vendor quote needs a named object, years, event-level fields, licence, retention/delivery terms and separate approval of its amount before purchase.
- A new formal test needs at least **20 genuinely untouched dates** and a Train/Dev-only paired precision estimate able to resolve the predeclared meaningful loss improvement. Twenty dates is a minimum, not an assurance of statistical power.

## 4. Execution order and exact receipts

### Gate 0 — Freeze the current evidence and access boundary

**Owner:** Supervisor + independent auditor. **Input:** existing local receipts and source hashes only. **No model, download or sealed read.**

Actions:

1. Record exact project commit, runtime, existing source manifests, 2025 role/date receipt and known access history in an `admission-baseline.json` with SHA-256. Keep old artifacts immutable.
2. Make a date/game exposure ledger with three evidence states: `opened`, `verified_not_opened`, `unknown`, plus actor and receipt path. Put 163 documented opened Train and all 50 scored Dev into an exposed policy set, even where per-game receipts cannot be reconstructed. Do not infer `verified_not_opened` from absence of a log.
3. Check old access logs by *metadata only* in the canonical local store; record the exact missing receipt paths. Do not repeatedly hydrate the iCloud archive. If only a cloud archive has those receipts, propose one bounded, read-only recovery with byte/hash list for approval rather than a broad resync.

**Pass:** every claim is linked to an existing receipt, or explicitly `unknown`; no old Final value opened. **Failure:** unresolved exposure remains unknown and cannot create a formal test. **Output:** exposure-ledger, missing-receipts report, source/hash inventory.

### Gate 1 — Source research before a bulk transfer

**Owner:** Controller chooses a bounded investigation when its live path is ready; B executes; Supervisor screens rights and budget. Supervisor can independently collect public documentation now but cannot attribute it to Controller.

Give the Controller the public schedule, the four deficits above, allowed source catalog and cost bounds, **not** sealed test rows or per-task outcomes. Ask it to pick exactly one uncertainty: (a) 2023 missing market identities, (b) 2023 fill sparsity, (c) 2025 whole-season trade access, (d) PBP clock quality, or (e) data-use rights. Require hypothesis, a source-specific query, a small fixed sample, expected evidence and a stop rule. Archive its first raw response; no score-based resampling.

Candidate sources to investigate, separately: official Polymarket market/trade interfaces, an identified on-chain CLOB archive with pinned revision, official Kalshi historical market/trade endpoints, and nflverse PBP releases. An API endpoint is *not* proof that it holds every historical NFL market. Current Polymarket documentation describes price-history points with `resolution_seconds` and separates last trade; market-scoped trade queries have a roughly three-year default floor. This makes exact old-source coverage a question to test, not assume. [Polymarket price-history semantics](https://docs.polymarket.com/market-data/prices-order-books), [Polymarket trade endpoint](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets), [Kalshi historical endpoints](https://docs.kalshi.com/getting_started/historical_data), [nflverse PBP releases](https://github.com/nflverse/nflverse-pbp/releases).

**Pass:** source URL/API version, timestamp granularity, coverage claim, rights/licence evidence, access method, expected bytes/requests and hashes are recorded. **Failure:** a candidate is marked unavailable/unknown; Controller chooses another source in a new logged decision, not a silent retry. **Output:** source-candidate ledger and research record distinguishing documentation from validation on our games.

### Gate 2 — Predeclared small source canaries

**Owner:** Controller proposes sample logic; Supervisor freezes it *before* fetching; B/runner executes one bounded canary per candidate; auditor checks raw receipts. No Dev/Final outcomes.

Use fixed first/middle/last and late-season weeks, plus known 2023 unmatched and zero-fill cases. Declare game IDs, time windows, maximum response bytes/pages, and comparison fields before source calls. For each candidate game, check market ID and token orientation, market creation/close/settlement times, raw fill timestamps, transaction IDs where available, price/size units, duplicates/corrections and source-object hash. Fetch a corresponding PBP game from a pinned release and inspect play IDs and event clocks. Keep mismatches and zero-fill games in the result.

**Pass:** at least one source candidate yields verifiable *real* fills and PBP timestamps for the same predeclared cases and permits research use; the result explicitly lists misses. No universal fill threshold is invented from the sample. **Failure:** classify `mapping_error`, `source_window_gap`, `market_absent`, `real_zero_fill`, `clock_unusable`, `rights_unknown` or `provider_failure`, with evidence. **Output:** immutable canary raw bytes (where allowed), SHA-256, request metadata and a game-level discrepancy table. No model fit.

### Gate 3 — Full-season source and identity inventory

**Owner:** data runner; independent auditor recomputes. Only after Gate 2 justifies the exact objects and size.

For 2023, 2024 and 2025 separately, enumerate every scheduled game and every matching market; resolve the 48 currently unmatched 2023 IDs one by one or leave them missing with reason. Count typed moneyline markets, traded games, fills by game/week/date, zero-fill games, source gaps, PBP games and PBP timed plays. Do not mix an AMM and a CLOB series as though the mechanism were identical. Record full source object/revision, ETag or equivalent, SHA-256, schema, timezone, query/processing code hash, row count and permitted-use statement. Use chunked/bounded processing, not an unrecorded bulk download.

**Pass:** denominators reconcile to schedule and every gap has a reason; immutable source objects and rights are independently verified. **Failure:** a season remains `not admitted`—never silently drop its absent weeks. **Output:** per-season/game/date coverage ledger and independent recomputation receipt.

### Gate 4 — Event-time join and candidate labels

**Owner:** data runner implements; independent auditor verifies. Controller may propose a *new* joining method on opened Train only; it cannot choose one by Final score.

Freeze orientation (home YES), PBP play clock, market source timestamp, as-of feature cutoff, maximum stale prior trade, 60-second future window, and treatment of identical/multiple timestamps before materialization. Keep provider-publish and local-receive time separate where available; historical event time alone cannot prove live tradability. Create stable composite row keys `(season, game, play, outcome, market, source event ordinal)`. No look-ahead joins. Generate a 60-second label only if valid prior and future **actual trades** satisfy the frozen rule. Produce a parallel 300-second *support diagnostic* without promoting it to the 60-second target. Report reasons `no_prior_trade`, `stale_prior_trade`, `no_future_trade`, `unmapped_market`, `bad_clock`, `duplicate_or_correction`, and `rights_blocked`.

**Pass:** independent re-materialization matches hashes and per-game/per-date counts; same row mask can be applied to zero-change and strong-model baselines. **Failure:** quarantine the specific source/game with evidence; no imputation. **Output:** Train-only row manifest, source-to-row provenance, missingness/variation tables, reproducibility receipt.

### Gate 5 — Find an actually independent Final period

**Owner:** Supervisor predeclares candidate rules; independent auditor verifies exposure; Controller sees only the permitted commitment and aggregate Train/Dev facts.

First test whether *any* already-collected, same-mechanism chronological block has at least 20 dates with complete, independently verifiable non-exposure history. The old 2025 Final cannot meet this by itself (11 dates) even if all 40 games are untouched. Old scored Dev is consumed. Do not assemble a favorable Final by moving games after seeing outcomes. If no historical block qualifies, prospectively reserve a future >=20-date block (for example in 2026) **before** its labels are available; log every later access. As of 2026-09-18, do not claim that a 2026 season already has 20 eligible dates. A separate 11-date sealed diagnostic may be proposed only as a small, non-formal result after an explicit scope decision.

**Pass:** >=20 distinct eligible dates, every date `verified_not_opened` at freeze, no game/date leakage across roles, exact membership commitment, one-use Final key/evaluator. **Failure:** formal Final remains closed; report earliest plausible prospective option and wait, or request a scope change. **Output:** sealed date/game manifest and exposure proof; no labels to Controller.

### Gate 6 — Statistical sufficiency and baseline readiness, using Train/Dev only

**Owner:** independent evaluator + Supervisor. Controller may choose algorithms later but not the success criterion after scores.

On opened Train/Dev, report date/week-clustered target variance, active and zero-fill fractions, common eligible rows, baseline loss, paired loss-difference dispersion and a confidence interval/power estimate for the **predeclared** meaningful improvement. Include zero-change B0, frozen Ridge B1 and a Train-only-selected strong ordinary baseline; no final selection on Final. For a formal claim, same cohort, objective, rows and costs apply to all methods. If labels are sparse or the interval is too wide, mark the study directional/underpowered and seek more independent dates or a new preregistered target version rather than tuning on Final.

**Pass:** baseline reproducible; at least 20 Final dates *plus* enough precision to evaluate the claimed effect. **Failure:** no formal improvement claim. **Output:** preregistration and precision memo, not a Final score.

### Gate 7 — Freeze, release, and only then experiment

**Owner:** Supervisor and independent runner. Hash the source objects, rights, split, row rules, target, horizons, baselines, controller/researcher harness, costs and code. Publish a new source version only to the user's fork, with no raw data, keys or run artifacts. Verify model authorship, B isolation, global state, unique run ID, budget ledger and exact process absence. Start one bounded research cycle only if **all** gates pass. The old $200 cap is unchanged; a hold is not an invoice. Final is opened once by the independent evaluator, after the final candidate is selected.

**Pass:** a single auditable input → GLM decision → B execution/log → independent feedback → next input chain and a separately sealed test plan. **Failure:** stop only the affected action, archive evidence, fix causal layer, use a fresh ID. No score-targeted retry or old-Final reuse.

## 5. Work packets, checkpoints and escalation

The Supervisor queue should show one active task at the top of the dashboard with: owner, exact question, input/source hashes, allowed data role, source/time/byte/cost cap, start/deadline, live log tail, next decision and terminal outcome. Finished or abandoned tasks go below as archived titles, not ahead of current work. A missing log is a failure, not “still researching.”

**First Controller packet when the path is ready:** “Using only this public schedule, known 2023 mapping/fill deficits, 2024 aggregate support, 2025 exposure summary and allowed source registry, choose one bounded source/data-quality investigation most likely to change the admission decision. Specify hypothesis, exact game/date sample chosen without outcomes, requested tool calls, expected evidence, max bytes/time/cost, rights check and stop rule. You may propose a new method, but cannot open Dev/Final, change the frozen 60-second target, purchase data or claim admission.” The Supervisor preserves the first raw answer; it does not choose among multiple GLM plans.

**Review cadence:** after each bounded task or about one hour without decision-relevant evidence, Supervisor answers: What uncertainty changed? What receipt proves it? Is this still the cheapest critical-path test? Continue, redirect, or stop. The full source-inventory expansion begins only after a small canary shows that it can change the decision. Parallel work is allowed for independent source-rights, schedule identity and PBP-clock checks, but no concurrent writes to the same frozen object or multiple paid jobs.

**Human decision only if required:** approve a priced data purchase with exact terms; approve a new formal market/target/split claim if the historical same-mechanism cohort fails; or approve a clearly labelled underpowered diagnostic that is **not** the original formal benchmark. The Supervisor must not make those scope choices silently.

## 6. What would count as progress this week

1. A complete, receipt-backed *negative or positive* classification of the 48 missing 2023 games, without dropping them from the denominator.
2. One fixed-source canary proving whether a candidate supplies real timestamps/fills for previously zero-fill regular-season cases, not just minute observations.
3. A 2025 season-wide source feasibility estimate (objects, bytes, rights, trade/PBP availability), before any bulk transfer.
4. A dated exposure ledger that distinguishes known opened, known sealed and unknown, and names the missing original receipts.
5. A written decision: a credible >=20-date independent Final path, or an explicit “not yet possible” with prospective collection and a separate small-diagnostic option.

None of these alone is an improved prediction score. The `indicator-prediction-evals` data gate shaped this plan: provenance and row identity first; missingness stays visible; the baseline and candidate later use exactly the same eligible rows; prior-inspected dates remain diagnostic, never confirmation.
