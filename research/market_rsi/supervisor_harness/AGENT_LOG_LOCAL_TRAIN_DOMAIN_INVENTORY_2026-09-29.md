# Local Train domain inventory — 2026-09-29

## Mandate and hard boundary

- Task: select exactly one already-resident prediction-market domain for the first real, non-promotion Train diagnostic, before any new score is computed.
- Allowed evidence: local presence, research-use caveat, as-of timestamp fields, chronological-split feasibility, independent event/date breadth, decision-time market baseline, target availability, and ability to proceed without a new fetch.
- Excluded: existing model-score/performance artifacts, model fitting, scoring, protected Dev/Final, provider/network access, and new external data. No such action was performed for this inventory.
- Storage inspected: `/Users/estelle/Developer/market-rsi` and the persistent, non-temporary `/Users/estelle/Library/Application Support/MarketRSI` tree.

## Pre-score selection

**Selected domain: the opened 2025 NFL two-outcome moneyline Train cohort** at:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01`

This selection was frozen before any new training or score. It is the only resident real-data cohort found that is explicitly labelled Train, has a fixed boundary before protected Route-Dev/Final games, has complete local market trade tapes and raw game data for every selected event, and has enough distinct dates for whole-event chronological rolling diagnostics. The choice does not depend on an observed model result.

## Selected-cohort inventory

### Identity and immutable anchors

- Dataset ID / root schema: `nfl-2025-train-refresh-20260922-01` / `nfl_2025_train_fresh_source_audit_v1`.
- Root manifest: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01/manifest.json`.
- Manifest SHA-256: `429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f`.
- Cohort file: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01/cohort.csv`.
- Cohort SHA-256: `ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885`.
- Manifest's per-game aggregate SHA-256: `99d2485e8b0b1a9eb3abf152e8a3df829d2f5b62ef9770f16f37d9f7cd5e668f`.
- The artifact is in the persistent local Application Support tree, not cloud-backed or temporary storage. The inventory made no copy and changed no source byte.

### Population and time breadth

- 195 unique Train games on 42 distinct game dates, from `2025-09-04` through `2025-12-04`.
- The fixed cohort ends before the documented 50-game Route-Dev block beginning `2025-12-07`; the later 40-game Final block was not read.
- 195 fresh normalized event catalogs, 195 raw PBP game files, and all 195 games have in-game trades.
- 628 raw trade pages; 531,148 raw rows; 530,222 rows in the fixed local event windows.
- 35,460 timed plays. A preceding market trade exists within 60 seconds for 31,881 plays (89.91%) and within 300 seconds for 35,275 plays (99.48%).
- The 42-date/195-event breadth supports past-to-future expanding or rolling-origin diagnostics with whole games/dates kept together. It is diagnostic breadth, not untouched OOS evidence.

### Schemas and as-of fields

- `cohort.csv`: `game_id, game_date, event_slug`.
- Normalized catalog per game under `catalog/<game_id>.json`: `condition_id`, `event_id`, `event_slug`, `event_start_utc`, `game_date`, `game_id`, `market_id`, source byte/hash receipts, and exactly two token IDs.
- Per-game trade manifest under `trades/<game_id>/manifest.json`: schema `polymarket_2025_train_v2_trade_capture_v1`, `condition_id`, tokens, raw-page receipts, fixed `window_start`/`window_end`, and row/hash reconciliation.
- Derived trade tape `trades/<game_id>/trade_window.csv`: `side, token_id, condition_id, size, price, timestamp, event_slug, outcome, outcome_index, transaction_hash`.
- Derived play clock `plays/<game_id>.csv`: `game_id, play_id, play_type, time_utc`.
- Raw game object `pbp/<game_id>.rds`: nested `data.viewer.gameDetail`; it includes teams, `phase`, terminal home/visitor scores, and play records with `timeOfDay`, `playType`, game state, possession and scoring fields.
- The local audit states that raw API and derived-file SHA-256 receipts reconcile. All 195 derived trade files are nondecreasing by `timestamp`; all observed prices are finite and in `[0,1]`.

### Baseline and target availability

- Decision-time market baseline is locally constructible from the latest same-market fill at or before a declared decision timestamp; no future fill may be used. Canonical outcome/token orientation must be frozen, with the opposite outcome represented consistently (for example as `1-p`). These are taker fill prices, not executable order-book quotes, so this baseline is a historical decision-time market probability diagnostic only.
- Exactly two market outcomes are present in all 195 trade files. Outcome names match the PBP team nicknames in 194 games; `2025_13_LA_CAR` has the deterministic alias `LAR` versus `Rams`, which must be normalized explicitly rather than inferred from scores.
- Terminal home/visitor scores are locally present for all 195 games. Phase is `FINAL` for 184 and `FINAL_OVERTIME` for 11. A post-freeze materialization check corrected one inventory error: `2025_04_GB_DAL` resolved `[0.5, 0.5]` after a tie, so the binary diagnostic must retain the 195-event denominator and exclude that event explicitly; 194 events have an unambiguous binary team-win target without external access.
- Leakage boundary: terminal totals at the root of `gameDetail` are target-only. Features must be derived only from play/trade records available at or before the row's decision time. Rows from the same game must remain in one chronological fold, and primary summaries should be equal-event/date aware because play rows repeat one terminal outcome.

### Research-use caveat

- The capture README records public Polymarket Data API/Gamma inputs and nflfastR per-game PBP sources, but the manifest says `formal_train_admitted=false`; combined-source rights and redistribution are not formally resolved.
- This caveat does not block the user's authorized private, non-promotion Train diagnostic. It does block treating the data/result as formally admitted evidence, redistributing it, publishing it, or using it for promotion without a later rights/admission decision.
- Source/receipt timestamps establish local historical capture and event time, not contemporaneous provider publication or an executable quote guarantee.

## Resident alternatives considered before scoring

### 2024 NFL fresh full-season source — not selected first

- Path: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2024-refresh-20260921-01`.
- Schema / manifest SHA-256: `nfl_2024_fresh_source_version_v1` / `699b6d86a48f55fa3719fdc6195babb6b3e7dedeac24d3439f4a4e492c399945`.
- 284 mapped games, 561 raw pages, 409,419 raw trades, 407,225 fixed-window trades, and 47,875 timed typed plays; 60-second support is 32,384 rows (67.64%) and 300-second support is 43,506 rows (90.87%). Every mapped game has window trades.
- Rejected for the first run because this source is not an explicit protected-boundary Train cohort (`train_admitted=false`), its rights status is unresolved, and contemporaneous provider publication/local receipt is unproven. It remains a possible later opened-data diagnostic only after its role boundary is made explicit; it was not selected by comparing scores.

### 2023 NFL fresh archive source — rejected

- Path: `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/nfl-2023-refresh-20260922-01`.
- Schema / manifest SHA-256: `nfl_2023_fresh_source_version_v1` / `af5aaf661709b9c37d150559110716024ab8a3207dfb5fba3ee15f07c4459e7c`.
- 285 scheduled games, 237 mapped and 48 unmapped; only 4,130 fixed-window on-chain fills for 48,194 timed plays. Support is only 499 plays at 60 seconds (1.04%) and 1,492 at 300 seconds (3.10%).
- Rejected because the stored safe fill projection omits a usable numeric decision-time probability, coverage is too sparse, 48 events are unmapped, `numeric_target_constructed=false`, and the on-chain fill event is not an executable quote. Rights are also unresolved.

### Metadata inventories and one-game canaries — rejected

- `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-polymarket-five-season-metadata-20260916-01` and `p0-polymarket-2025-series-metadata-20260916-04` are NFL metadata catalogs, not aligned Train examples: their manifests say `formal_data_admitted=false`, `schedule_matched=false`, and trade coverage is not verified.
- `/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/p0-polymarket-2025-trade-canary-20260916-01` contains only one event's trade canary and says both `event_aligned_labels_verified=false` and `season_trade_coverage_verified=false`; it lacks independent event/date breadth.
- Repository PMB/minimal-loop fixtures are synthetic protocol fixtures, not a resident real Train domain, so they are not eligible for the first real diagnostic.

## Domain conclusion

Within the two authorized roots, the only complete resident real prediction-market domain found is NFL moneyline. No comparably aligned resident weather, crypto, politics, other-sport, or general-market Train cohort was found. The exact first diagnostic domain is therefore frozen as **2025 NFL moneyline / the 195-game opened Train cohort**. This is a seed diagnostic domain, not the project's permanent scope.

## Handoff rule

The training worker may now freeze a whole-game/date chronological rolling design, one causal feature set, the latest-pre-decision market baseline, one strong ordinary baseline, and one candidate on these same rows. It must preserve the alias normalization and target-only terminal-score boundary above. Any result is Train diagnostic only: no Dev/Final access, promotion, publication, external fetch, or provider call is implied.
