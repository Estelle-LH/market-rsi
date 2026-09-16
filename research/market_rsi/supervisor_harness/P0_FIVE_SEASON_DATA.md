# P0 — five completed NFL seasons of usable market history

**Supervisor decision, 2026-09-16:** INTERRUPT the proposed formal model
comparison; REPLAN to data acquisition and admission. The user asked for about
five years, but the completed 2024 Polymarket 284-game audit is only one year.
The 2025 opened-Train HGB result does not fill the missing multi-year source
inventory. No model claim may describe the small cohort as a five-year test.

## What must be obtained and checked

Candidate window: five completed NFL seasons 2021–2025. This is an inventory
target, **not** a claim that any one exchange offered equivalent NFL contracts
throughout. For each season and exchange, record the number of scheduled games,
matching pre-game/in-game markets, distinct markets and traded games, timestamped
trades and—if offered—historical bid/ask updates; price/size units, outcome and
settlement mapping, cancellation/correction rules, coverage by game/date and
the rights to use the data for research. Join to independently sourced NFL
play-by-play with a documented event clock. Record provider-publish and local-
receive timestamps separately when available; historical event timestamps do
not establish live availability.

Keep Polymarket and Kalshi as separate cohorts and baselines unless a predeclared
cross-exchange transfer test justifies combining them. Do not fill missing
trades with zero moves or retain only active games to inflate coverage. For
candidate 60s/300s labels, report all games in the denominator, per-season and
per-date missingness, target variation, a zero-change forecast, and the reason
each row is unavailable. Verify source hashes and run local-only; do not
rehydrate iCloud as an execution strategy.

## Acquisition order and cost

1. Inventory free official sources without bulk downloading or choosing models:
   Polymarket market discovery and public trade history; Kalshi historical
   markets and trades; nflverse season play-by-play. Endpoint availability
   does **not** prove that the required NFL contracts existed in every year.
2. If free sources miss a season, price granularity, quotes or usable rights,
   seek a direct vendor/exchange quote for the exact gap (years, markets,
   event-level trade/quote timestamps, format, licensing, delivery). Compare
   a small sample and coverage before committing to a bulk purchase. The user
   has authorized pursuing paid data, but no vendor price or separate ceiling
   has yet been established; do not bill the $200 Tinker experiment ledger.
3. Purchase only after the exact quote, permitted use and separate amount are
   recorded and approved. Preserve invoice and source/version hashes. Do not
   use multiple accounts or trial identities to bypass a provider's terms.

Official source checks made 2026-09-16: [Polymarket market listing](https://docs.polymarket.com/api-reference/markets/list-markets)
and [public market trades](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets)
describe market discovery and trade timestamps; [Kalshi historical data](https://docs.kalshi.com/getting_started/historical_data)
lists archived markets/trades/candlesticks and a moving live-data cutoff;
[nflverse PBP](https://github.com/nflverse/nflverse-pbp) points to official
season releases. These document *access mechanisms*, not actual five-season
NFL market completeness, purchase price or historical quote availability.
No all-provider NFL inventory, vendor catalog or price quote has yet been
validated; the Polymarket series-specific metadata screen below is narrower.

### Complete public series-keyset screen (metadata only)

The bounded read-only screen on 2026-09-16 followed every cursor in the
Polymarket `nfl` series for 2021–2024 and the separate `nfl-2025` series for
2025. Raw pages, request URLs, SHA-256 receipts and manifests are preserved in
local ignored artifacts `p0-polymarket-five-season-metadata-20260916-01/`
and `p0-polymarket-2025-series-metadata-20260916-02/`. The first run queried
the generic series for 2025 and got zero; the second correctly queried the
season-specific series. This is why the first zero is **not** a data-absence
claim. The inventory program and no-network tests live beside this document.

| Season | Exact queried series | Events returned | Standardized game-slug events with one tokenized, two-outcome moneyline | Interpretation |
| --- | --- | ---: | ---: | --- |
| 2021 | `nfl` | 199 | 0 | Legacy event naming/type fields differ; sampled records include spread and in-game winner questions. This rule cannot classify their game/price coverage. |
| 2022 | `nfl` | 35 | 0 | Several grouped week events and missing market-type tags; not proof of no game markets. |
| 2023 | `nfl` | 0 | 0 | No events in this series/window, not a claim that no other series/provider has them. |
| 2024 | `nfl` | 285 | 284 | Consistent with the separately mapped 284-game support audit; 1 event lacks a typed moneyline. |
| 2025 | `nfl-2025` | 271 | 271 | Candidate metadata only; not schedule-matched or trade-coverage audited. |

The screen did **not** fetch any trades, historical quotes or outcomes; it did
not map 2021–2023 or 2025 to the NFL schedule. A market page count is not the
number of usable 60-second/300-second labels, and the older contracts must not
be silently pooled with 2024–2025 moneylines.

A separate bounded `title_search=NFL` query for the 2023-season window
returned 11 events, including non-game NFL topics and unrelated inflation/war
questions. That search's text filter is too noisy to certify absence or
coverage, but it did not reveal a 2024-style full-game moneyline catalog.

Kalshi's [January 2025 sports-market announcement](https://news.kalshi.com/p/game-on-kalshi-sports-trading-is-now-100-legal-in-all-50-states-2)
is evidence against assuming that its API can supply five earlier NFL seasons,
even though [historical endpoints](https://docs.kalshi.com/getting_started/historical_data)
now exist. [Betfair's exchange historical-data service](https://support.developer.betfair.com/hc/en-us/articles/360002407732-What-data-is-provided-by-the-Historical-Data-service)
advertises market/price history since 2015 and is a candidate *different
exchange* to investigate for five-year NFL coverage and a quote. It cannot
be substituted for Polymarket/Kalshi in the formal benchmark without an
explicit scope decision and separate matched baselines.

Betfair's [own tier guide](https://betfair-datascientists.github.io/data/usingHistoricDataSite/)
describes free BASIC as one-minute last-traded price without volume, ADVANCED
as one-second top-three ladder with volume, and PRO as tick-level full ladder.
Its [Other Sports description](https://support.developer.betfair.com/hc/en-us/articles/8085210924957-Which-Sports-Are-Included-in-the-Other-Sports-package)
explicitly includes American Football. Public [bulk-price guidance](https://support.developer.betfair.com/hc/en-us/articles/360019984158-Are-bulk-purchase-discounts-available)
lists Other Sports ADVANCED at £39/month or £399 for any 12 months, but this
is **not** an NFL coverage quote or purchase authorization. Registered-account
and [jurisdiction restrictions](https://support.developer.betfair.com/hc/en-us/articles/360008664937-Which-juristictions-is-Betfair-Exchange-Historical-Data-available-to-)
may block access. A free one-minute series could support a different,
predeclared horizon but cannot be treated as the same event-level trade/quote
target without a separate label and baseline design.

### First public metadata probe (not a season inventory)

On 2026-09-16 a read-only call to Polymarket's documented `events/keyset`
endpoint with `title_search=NFL`, `start_date_min/max` and requested limit 500
returned a first page of 100 in 2021, 100 in 2024 and 100 in 2025 with more
pages. The 2022 first page had 59 and included an unrelated EU inflation event;
the 2023 first page had 79. A 2021 example was a **point-spread** question,
not the same moneyline contract as the 2024 cohort. Thus this broad search is
noisy and page-limited: none of these numbers is a verified game, market or
trade count. The next inventory must follow every cursor, strictly classify
contract type and map candidates to the frozen NFL schedule. Do not conclude
that five comparable seasons exist from this probe.

## Admission / exit rule

P0 passes only with a frozen per-season source matrix, rights/cost ledger,
local verified manifests and hashes, end-to-end event/market mapping and
timestamp-quality report, and enough nontrivial labels to predeclare the
objective and date split. The exact seasons and exchange used for the formal
benchmark must be stated from this evidence. Previously inspected 2024
coverage and 2025 Train examples are diagnostics, not magically untouched
final data. After admission, freeze target, row mask, information cutoff,
features and search budget, then rerun zero-change, HGB and other strong
ordinary baselines on the same rows before testing self-iteration. A new
held-out confirmation still needs at least 20 untouched dates.

If five comparable seasons are unavailable, mark P0 **blocked with evidence**
and ask the user whether to change market, target or scope. Never pass P0 by
silently treating a single 2024 season as five years or by fabricating data.

## Current verified status

| Season | Market-data status | PBP status | Formal admission |
| --- | --- | --- | --- |
| 2021 | `nfl` metadata fully paged: 199 legacy events, zero matching the modern typed-moneyline schema; trade/quote coverage unknown | Official multi-season PBP source identified; this season not locally verified | No |
| 2022 | `nfl` metadata fully paged: 35 legacy/grouped events, zero matching the modern typed-moneyline schema; trade/quote coverage unknown | Same boundary | No |
| 2023 | `nfl` series/window returned zero; other series and providers not ruled out | Same boundary | No |
| 2024 | Polymarket 284-game source; 407,225 trades; 60s labels 67.64%, 300s 90.87% in historical event clock | Frozen 2024 PBP used for support audit; not staged in local execution tree | No—support audit only |
| 2025 | `nfl-2025` metadata fully paged: 271 typed moneyline candidates; trades and schedule match not yet checked; a limited opened-Train 60s baseline exists | Full-season source not verified here | No |

**Next bounded action:** match the 2025 candidates to the NFL schedule and
screen their trade coverage; inspect whether any comparable 2023 or legacy
2021–2022 contracts exist outside the modern catalog. In parallel, request
coverage/granularity and a price quote for five-season NFL exchange data,
including Betfair as a *separate* possible scope. No formal model training
while this P0 remains open.
