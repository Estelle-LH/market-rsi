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
season-specific series but its date filter silently excluded 14 Week 1 games.
The corrected no-date-filter, season-validated inventory is
`p0-polymarket-2025-series-metadata-20260916-04/`. The intervening `-03`
attempt hit a 20 MB page safety limit; all attempts remain preserved. This is
why neither zero nor 271 is a complete 2025 coverage count. The inventory
program and no-network tests live beside this document.

| Season | Exact queried series | Events returned | Standardized game-slug events with one tokenized, two-outcome moneyline | Interpretation |
| --- | --- | ---: | ---: | --- |
| 2021 | `nfl` | 199 | 0 | Legacy event naming/type fields differ; sampled records include spread and in-game winner questions. This rule cannot classify their game/price coverage. |
| 2022 | `nfl` | 35 | 0 | Several grouped week events and missing market-type tags; not proof of no game markets. |
| 2023 | `nfl` | 0 | 0 | No events in this series/window, not a claim that no other series/provider has them. |
| 2024 | `nfl` | 285 | 284 | Consistent with the separately mapped 284-game support audit; 1 event lacks a typed moneyline. |
| 2025 | `nfl-2025`, no misleading date filter | 285 | 285 | All 285 uniquely match the NFL schedule in a later identity-only screen; season-wide trade coverage not audited. |

The catalog screen did **not** fetch trades, historical quotes or outcomes.
The later identity-only 2025 screen (`p0-polymarket-2025-schedule-screen-20260916-03/`)
matched 285/285 market events to 285 nflverse games without reading scores;
the earlier `-01` and `-02` screens remain as diagnostics of team-alias and
API-filter errors. One chronologically selected game
(`p0-polymarket-2025-trade-canary-20260916-01/`, DAL–PHI Week 1) then returned
2,148 public taker trades in a fixed 12-hour pre-game to 5-hour post-start
window: 733 before start and 1,415 after. This proves one market has timestamped
trades, **not** that all games have usable 60s/300s labels or live-observable
prices. No 2025 season-wide trade audit or event-aligned PBP join exists yet.
A market page count is not the number of usable labels, and older contracts
must not be silently pooled with 2024–2025 moneylines.

A separate bounded `title_search=NFL` query for the 2023-season window
returned 11 events, including non-game NFL topics and unrelated inflation/war
questions. That search's text filter is too noisy to certify absence or
coverage, but it did not reveal a 2024-style full-game moneyline catalog.

An independent check of Polymarket's own event pages found explicit older
game-winner markets: four in the [2021-season divisional-playoff
event](https://polymarket.com/event/nfl-playoffs-divisional-21-22), six in a
[2022 Week 5 event](https://polymarket.com/event/nfl-week-5), and eleven in
an [October 2023 daily event](https://polymarket.com/event/nfl-dailies-2023-10-22).
These are counterexamples to interpreting the modern catalog classifier's
zeros as no older NFL markets. They establish neither season-wide coverage
nor retrievable timestamped fills. Polymarket's [trade API
documentation](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets)
describes a rolling historical window of about three years; older event-page
volume is not a substitute for accessible event-level trade history.

On 2026-09-16, a **three-market discovery check** queried the public legacy
trade API with `limit=1` and fixed event-week timestamp windows. The condition
IDs came from exact public Gamma event-slug lookups; only row count and the
first timestamp were inspected, not prices or outcomes:

| Season / exact event | Winner market sampled | Window (UTC epoch seconds) | Returned rows / limit | What this establishes |
| --- | --- | --- | ---: | --- |
| 2021 season, `nfl-playoffs-divisional-21-22` | Titans–Bengals, `0xcc4a3885aee3ad32f8232e3777a63b146fbfd9f76e19907c697a73b3d5fdd600` | 1642723200–1643155200 | 0 / 1 | This market's old fills are not available through that bounded market-scoped request now; not proof that no trades occurred. |
| 2022 season, `nfl-week-5` | Colts–Broncos, `0x99b0e2fa20d738ca822fa89e4f3a083059d99a5f5abc85a08f7ac65c46078ce0` | 1664928000–1665532800 | 0 / 1 | Same narrow negative finding. |
| 2023 season, `nfl-dailies-2023-10-22` | Giants–Commanders, `0xb3395c017119cdf9b2ddebc3d195d1b10e6020efb8795bda44933db3f0af0df8` | 1697760000–1698192000 | 1 / 1; first timestamp 1697995179 | At least one timestamped fill is retrievable for this specific market. |

The contrast is consistent with the API's documented approximately three-year
floor for market-scoped requests, **not** a season-wide coverage estimate or
proof of a hard cutoff date. These exploratory responses were not persisted
with raw hashes, so they are not admitted source artifacts. A separate lawful
archive/provider route is still needed for the missing older years.

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
may block access. Betfair specifically warns that its [Historical Data API
may reject a US-based IP](https://support.developer.betfair.com/hc/en-us/articles/21165141580572-Why-am-I-receiving-the-ngErrorRedirect-error-when-attempting-to-access-the-Historical-Data-API),
which does not establish whether the browser portal has the same behavior.
Its ordinary [terms for live and historical odds](https://support.betfair.com/app/answers/detail/a_id/10559/)
restrict commercial use without prior written consent; a purchase price is
not a commercial training licence. The [vendor programme](https://developer.betfair.com/vendor-program/the-process/)
provides an application route, but no rights, delivery method or exact NFL
coverage have been agreed here. A free one-minute series could support a different,
predeclared horizon but cannot be treated as the same event-level trade/quote
target without a separate label and baseline design.

[Matchbook's B2B service](https://b2b.matchbook.com/pricingservices) advertises
historical exchange pricing/line tracking upon request, but gives neither a
five-season NFL inventory nor a public price. It is an inquiry lead, not an
admitted substitute dataset.

Another documented but **non-exchange** fallback is [The Odds API's historical
NFL bookmaker odds](https://the-odds-api.com/liveapi/guides/v4/): it advertises
moneyline snapshots from mid-2020, every ten minutes initially and every five
minutes from September 2022, on a paid plan. This could test a different
multi-year, lower-frequency forecasting question; it cannot fill missing
one-minute exchange trades or be silently blended into the current target.
No paid-plan amount or sample coverage has been verified.

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
| 2021 | `nfl` metadata fully paged: 199 legacy events, zero matching the modern typed-moneyline schema; an official playoff page shows game-winner markets. One bounded old-market trade query returned zero; season-wide trade/quote coverage unknown. | Official multi-season PBP source identified; this season not locally verified | No |
| 2022 | `nfl` metadata fully paged: 35 legacy/grouped events, zero matching the modern typed-moneyline schema; an official Week 5 page shows game-winner markets. One bounded old-market trade query returned zero; season-wide trade/quote coverage unknown. | Same boundary | No |
| 2023 | `nfl` series/window returned zero, yet an official daily event page shows game-winner markets. One bounded query returned a timestamped fill; season-wide coverage unknown. | Same boundary | No |
| 2024 | Polymarket 284-game source; 407,225 trades; 60s labels 67.64%, 300s 90.87% in historical event clock | Frozen 2024 PBP used for support audit; not staged in local execution tree | No—support audit only |
| 2025 | Corrected `nfl-2025` catalog has 285 typed moneylines and 285/285 schedule-identity matches; one earliest-game 2,148-trade source canary, not season coverage; a limited opened-Train 60s baseline exists | Identity schedule verified; full play-by-play alignment not verified here | No |

**Next bounded action:** seek a lawful archive/provider route and a concrete
season-by-season coverage/granularity/rights quote for 2021–2022 fills, with
Betfair only as a *separate* possible exchange. Decide whether a 2025
whole-season source audit is worth its public-request cost once a five-season
path is credible. No formal model training while this P0 remains open.
