# P0 — three-season pilot floor, five-season primary target

**Supervisor decision, 2026-09-16:** INTERRUPT the proposed formal model
comparison; REPLAN to data acquisition and admission. The user asked for about
five years, but the completed 2024 Polymarket 284-game audit is only one year.
The 2025 opened-Train HGB result does not fill the missing multi-year source
inventory. No model claim may describe the small cohort as a five-year test.

**Updated supervisor judgment, 2026-09-16 late evening:** Three *completed,
comparable* seasons are the minimum for a separately labelled first controlled
prediction experiment; five seasons remain the stronger primary benchmark
target, not a reason to search indefinitely or to mix incompatible trading
mechanisms. This is our design judgment, **not** a literature-proven magic
sample size or a declaration that three years have already been acquired.
The natural first candidate is 2023–2025 Polymarket CLOB, subject to actual
schedule-matched trade and label audits. The old 2021–2022 AMM observations
may be useful as a distinct historical cohort but cannot silently enlarge the
same-mechanism pilot. The old five-season gate still applies to any claim of a
five-season result; the three-season pilot has its own distinct gate below.

For the pilot, use chronological development (provisionally 2023 Train, 2024
Route-Dev, 2025 one-time Final). This split is conditional: prior 2025
opened-Train and canary exposure must be inventoried, and all dates or games
already inspected for model development excluded from Final. If the exposed
aggregate 2025 results or other leakage make independent confirmation
unverifiable, do **not** relabel 2025 as untouched; defer a final claim until
a genuinely independent period exists. At admission, record full schedule
denominators and every mapped/unmapped game, per-game and per-date trade and
candidate-label coverage, missingness by week/team, source rights/hashes,
point-in-time observation rules, and a predeclared target/row mask. Require
at least 20 genuinely untouched Final dates and the same eligible rows for
zero-change, strong ordinary baselines and the iterating researcher. Before
opening Final, estimate the precision of a *paired, week-blocked* loss
difference using only opened Train/Dev. If that estimate cannot resolve the
predeclared meaningful improvement, the pilot can report a directional result
but cannot make a strong improvement claim; acquire more comparable data or
wait for another completed season. A year count or thousands of correlated
play rows alone is never evidence of sufficient statistical power.

**2026-09-16 23:56 ET correction:** The pre-existing 2025 split has 163
opened-Train games and 50 old Route-Dev games already scored; its 40 sealed
Final games occupy only **11 distinct game dates** (schedule-metadata-only
inspection recorded in `PREDICTION_BENCHMARK_V0_2026-09-16.md`). Thus the
provisional year assignment above does **not** yield a qualifying >=20-date
Final. Do not silently promote 2025 Train/old Dev into an unseen test or open
the 40 labels to decide a new split. Three nominal seasons alone cannot pass
the independent-confirmation gate. A distinct future time block or another
prospectively frozen, genuinely uninspected >=20-date period is needed; its
availability is not yet proven. The existing 40 can only be separately labelled
as a small sealed pilot under its original rules.

The local [nflverse schedule](https://github.com/nflverse/nfldata/blob/master/data/games.csv)
revision `9c00ef3c24ac5fd8979bd8b40da4b2800bf0bc17` lists, respectively,
285/284/285/285/285 games and 62/61/63/65/64 distinct game dates in the
2021–2025 seasons. Thus one untouched season can in principle exceed the
minimum 20-date check, but it has only 22 game weeks and market/label gaps
reduce effective evidence. A three-season design leaves roughly one season
to learn, one to choose, one to test; five seasons allow more training and
cross-season replication. These are design inferences from the schedule,
not observed forecast gains. Rolling-origin evaluation uses only prior data
for each forecast as described by [Hyndman](https://robjhyndman.com/hyndsight/tscv/);
repeated strategy selection on the same history creates overfitting risk as
analyzed by [Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
Neither source asserts that exactly three or five NFL seasons are sufficient.

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
archive/provider route was needed for the missing older years; the next
section records a newly found free candidate, not its formal admission.

### Free on-chain AMM archive canary, 2026-09-17 UTC

A new **candidate** route is the public
[Polymarket On-Chain v1 archive](https://huggingface.co/datasets/moose-code/polymarket-onchain-v1)
at immutable dataset revision `7eeb860dea5b79d5c74f3182b70bd08c85c8f833`.
Its publisher labels it CC-BY-4.0 with attribution to Envio, and says its
`fpmm_transaction` table contains AMM buys/sells from the early era while
`order_filled` contains later CLOB fills. This is a publisher claim, not yet
our own completeness or rights audit. Polymarket's
[FPMM subgraph schema](https://github.com/Polymarket/polymarket-subgraph/blob/main/fpmm-subgraph/schema.graphql)
independently specifies an FPMM transaction with timestamp, market address,
trade amount, fee, outcome index and token amount. It is a different execution
mechanism from modern CLOB; equal-looking prices are not automatically equal
labels or executable quotes.

We downloaded only three small monthly AMM shards (November 2021, January
2022, October 2022; 8,873,616 bytes combined). Their local SHA-256 values
match the publisher's revision-pinned LFS object IDs. Using the already saved
Gamma `marketMakerAddress` mapping, an exact case-insensitive market-ID query
found 251 and 406 rows for two November 2021 regular-season games; 556, 332,
661 and 870 rows for the four January 2022 divisional-playoff winner markets;
and 420 rows for the October 2022 Colts–Broncos game. The full source URLs,
hashes, addresses and query rule are in ignored local artifact
`artifacts/p0-polymarket-amm-archive-canary-20260917-01/manifest.json`.
These seven selected markets prove some old timestamped trade records are
available for free, correcting the tempting inference from empty Data API
responses. They **do not** prove whole-season coverage, adequate in-game
frequency, correct price reconstruction, legal downstream use beyond the
publisher's licence statement, or comparability with 2024–2025 CLOB labels.
The raw row counts include post-game timestamps and are not label counts.
Using a separately hashed [nflverse game schedule](https://github.com/nflverse/nfldata/blob/master/data/games.csv)
for only those seven games, the fixed one-hour-before to five-hours-after
kickoff window contained 231–856 rows per market. Median gaps between unique
trade timestamps were 10–39 seconds, but each game's largest observed gap
was 398–6,027 seconds. These broad game-window counts are encouraging for
source discovery yet **not** a play-aligned 60s/300s label-support estimate;
the schedule revision and all seven diagnostics are in the same manifest.

A public Polygon RPC returned `History has been pruned` for the 2022 block
range. The Blockscout address-logs endpoint returned only one historical log
for the sampled Titans–Bengals market and none for Colts–Broncos, whereas the
revision-pinned archive returned 556 and 420 rows. Thus a zero or tiny count
from those convenience endpoints is **not** a reliable absence test here.
The exact archive rows still need independent sampled event/receipt checks.
At the time of this free-archive canary, mapping a schedule-matched
2021–2023 catalog to AMM/CLOB addresses was the cheapest proposed check.
That proposed old-season work was later deferred by the explicit three-season
pilot decision above; the seven-game canary remains evidence, not an executed
whole-season audit. Seek a paid quote only for documented gaps; do not buy
a broad package first.

### Bounded discovery rule after the 2026-09-16 review

The user requires both a finite search and a dataset large enough for the
stated claim. **The time limit applies to speculative source discovery,
not to the data-admission standard.** The stronger five-season target remains,
with a schedule denominator and market/trade/label coverage reported separately
for every season. A seven-game canary cannot pass either admission gate.
Before any model comparison, require source/version/hash and rights receipts,
an auditable game-to-market join, event-time quality and missingness reports,
one predeclared comparable target and row mask, a zero-change and strong
ordinary baseline on the same rows, and at least 20 untouched out-of-sample
dates. Do not invent a percentage cutoff from the seven selected games;
establish a label-support and power criterion on Train-only data before opening
Dev/Final.

The **old-season free-source pass** was originally limited to two hours: one
reproducible 2021–2023 address-to-schedule mapping with every scheduled game
in the denominator, followed by a fixed first/middle/last-game density sample
that counts unmapped games as failures. **That pass was not executed before
the later supervisor decision to prioritize a three-season pilot; it is now
deferred rather than treated as completed evidence.** Apply the same bounded
approach to the 2023–2025 same-mechanism candidate first: decide whether
season-wide market identities, timestamped fills and untouched Final dates
can plausibly be admitted. If not, stop broad public-source searching. Produce a
per-season missing-data table and seek itemized sample, coverage, permitted-use,
delivery and price terms for only those gaps. If no lawful affordable source
passes even the three-season pilot gate, mark that gate blocked and ask the
user to choose a changed scope. Do not label a three-season pilot a five-season
primary result. Diagnostic
work on already opened Train can be labelled as such, never substituted for
the held-out benchmark. The $200 Tinker ceiling is not a data-purchase budget.

The first bounded archive-catalog check used revision
`7eeb860dea5b79d5c74f3182b70bd08c85c8f833` of the
[publisher's dataset](https://huggingface.co/datasets/moose-code/polymarket-onchain-v1).
Two small metadata objects, `market.parquet` (251,627 bytes; SHA-256
`63b8a630c768c8171ae45f6d504c6fedd2aab6e3f0da4859d8b7a15144e51b57`)
and `fixed_product_market_maker.parquet` (4,454,044 bytes; SHA-256
`daa8d2746d8e044f805a58436afe2dbf8dd3ddc7f74b44d918a543dd7ae89c8e`),
matched the revision's LFS object IDs. The former has game IDs but not public
questions; the latter has AMM addresses but not the NFL game labels. A
read-only column-range query of `market_data.parquet` (not a full-file
download) found, using the **strict `nfl-` slug prefix** and `endDate` season
windows, 0 candidate conditions in Sep 2021–Mar 2022, 32 in Sep 2022–Mar
2023, and 237 in Sep 2023–Mar 2024. These are *unmatched metadata candidates*,
not scheduled-game coverage. The zero conflicts with known 2021 AMM trade
samples because this newer metadata join/classifier is incomplete for that
era; it does **not** disprove those trades or establish that the whole early
season is absent. The catalog cannot by itself certify five seasons. The
two downloaded metadata files remain in ignored local artifact
`artifacts/p0-polymarket-archive-catalog-20260917-01/`; no raw file was pushed.

### 2023 source-only identity and fixed price/fill canaries

On 2026-09-16, the strict `nfl-` archive candidate screen above was joined to
the revision-pinned nflverse 2023 schedule by game date/team identity, without
reading scores. The first attempt matched 222/285 because archive slugs use
`LAS` for the Raiders while the schedule uses `LV`; it remains preserved as
`artifacts/p0-polymarket-2023-archive-catalog-20260917-01/`. After adding and
testing that explicit alias, **237/285** scheduled games matched unique
two-token market conditions; **48** did not. The unmatched games cluster in
Weeks 13 (13), 16 (3), 17 (15), 18 (16), 22 (1). This is identity coverage,
**not** 237 games with usable trades, event-aligned labels or verified winner
semantics. The corrected ignored artifact is
`artifacts/p0-polymarket-2023-archive-catalog-20260917-02/`, mapping SHA-256
`e6e1c0501ea9831e2bbf97460b86d4db2f31352117a9df70ae16d2b01f40dbea`.
The large remote `market_data.parquet` was queried by revision-pinned HTTPS
column/range; its full bytes were **not** downloaded or independently hashed.

A deterministic first/middle/last game sample (sorted game date and ID)
queried three fixed monthly `order_filled` partitions for kickoff minus 12h
to plus 5h. The in-game fill counts were **0**, **6**, and **137**; total
window fills 18, 6, 206, respectively. The middle game had only three
distinct fill seconds, despite spanning a full game. The partition object
hashes are publisher LFS claims, not locally verified full-object hashes.
Sample artifact `artifacts/p0-polymarket-2023-fixed-fill-canary-20260917-01/`
has results SHA-256
`acc4c78732396d16bfb42a106d5ec674214715d352f2d563e742aba678ff1e23`.
The same middle-game official Data API returned three taker trade rows in
the fixed window. Neither route supports calling the whole 2023 season
adequately liquid for the current event-horizon target.

The official [Polymarket prices-history endpoint](https://docs.polymarket.com/api-reference/markets/get-prices-history)
returned **1,020/1,019/1,020 one-minute historical price points** for the
same three game windows, with **41/34/133** consecutive price changes and
longest unchanged runs **137/214/661 minutes**. Thus a timestamp at each
minute is not a distinct new trade. The documentation calls this historical
price data; it does not establish our required fill-price, bid/ask,
executability or point-in-time event-label semantics. This may be a *different*
predeclared target after validation; it must not silently replace the existing
trade-based objective. Raw fixed responses and manifest remain only in ignored
`artifacts/p0-polymarket-2023-fixed-price-history-canary-20260917-01/`,
results SHA-256
`6da3451760f65415d681bb3e271afe67b40eb11297ad387231a4eaae573f01d0`.
The source-only scripts and eight offline tests are in `supervisor_harness/`.
Zero Tinker, zero vendor spend, no Dev/Final opening, no model result.

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

The **five-season primary P0** passes only with a frozen per-season source matrix, rights/cost ledger,
local verified manifests and hashes, end-to-end event/market mapping and
timestamp-quality report, and enough nontrivial labels to predeclare the
objective and date split. The exact seasons and exchange used for the formal
benchmark must be stated from this evidence. Previously inspected 2024
coverage and 2025 Train examples are diagnostics, not magically untouched
final data. After admission, freeze target, row mask, information cutoff,
features and search budget, then rerun zero-change, HGB and other strong
ordinary baselines on the same rows before testing self-iteration. A new
held-out confirmation still needs at least 20 untouched dates.

The separately labelled **three-season pilot** can proceed only after its
three comparable completed seasons and the earlier pilot-specific source,
leakage, target, precision and untouched-date checks pass. If five comparable
seasons are unavailable, mark the *five-season primary claim* blocked with
evidence; do not block a properly labelled pilot merely to keep searching.
If even the pilot cannot be admitted, report the gaps and ask the user whether
to change market, target or scope. Never relabel a single 2024 season as a
multi-year result or fabricate data.

## Current verified status

| Season | Market-data status | PBP status | Formal admission |
| --- | --- | --- | --- |
| 2021 | `nfl` metadata fully paged: 199 legacy events, zero matching the modern typed-moneyline schema; an official playoff page shows game-winner markets. One old Data API query returned zero, but a revision-pinned free AMM archive yielded 251/406 rows for two November 2021 games and 332–870 rows for four January 2022 playoff games. Whole-season coverage/label quality unknown. | Official multi-season PBP source identified; this season not locally verified | No |
| 2022 | `nfl` metadata fully paged: 35 legacy/grouped events, zero matching the modern typed-moneyline schema; an official Week 5 page shows game-winner markets. One old Data API query returned zero, but the free AMM archive yielded 420 rows for the selected Colts–Broncos market. Whole-season coverage/label quality unknown. | Same boundary | No |
| 2023 | `nfl` series/window returned zero, yet the revision-pinned archive has 237/285 strict schedule-matched two-token markets. Fixed first/middle/last samples have 0/6/137 in-game on-chain fills; official minute-price history varies but its trade/quote semantics are unverified. Forty-eight schedule games are unmatched and season-wide usable label coverage remains unknown. | Schedule identity verified only; event-aligned PBP coverage unknown | No |
| 2024 | Polymarket 284-game source; 407,225 trades; 60s labels 67.64%, 300s 90.87% in historical event clock | Frozen 2024 PBP used for support audit; not staged in local execution tree | No—support audit only |
| 2025 | Corrected `nfl-2025` catalog has 285 typed moneylines and 285/285 schedule-identity matches; one earliest-game 2,148-trade source canary, not season coverage; opened-Train baseline and old scored Dev exist. The 40-game sealed Final spans only 11 dates, below the >=20-date gate. | Identity schedule verified; full play-by-play alignment not verified here | No |

**Next bounded action:** make a read-only 2025 exposure/date inventory without
opening sealed prices/labels, then decide where a genuinely independent
>=20-date Final can come from. Resolve whether 2023 historical prices are
carried-forward/trade/mid/quotes before changing any objective; do not keep
scanning more years simply because a metadata candidate exists. Document the
48-game 2023 identity gap and the regular-season fill-density gap before
seeking exact sample/rights/cost terms. Both pilot and five-season primary
remain closed. Betfair remains a *separate* exchange, not a silent fill.
The supervisor's outcome-blind sampling and cleaning procedure is fixed in
`P0_SAMPLING_CLEANING_DECISION_2026-09-17.md`; its 12-game diagnostic receipt
is **not** a substitute for a full-cohort coverage audit. In the current
archive classifier, 47 of the 92 scheduled games in Weeks 13–18 are unmatched,
a strong late-season catalog bias that must remain visible in the denominator.
The frozen 12-game fill diagnostic is now complete: 5/9 sampled regular-season
games have zero in-game fills, while three sampled playoff games have 59–79
each. Result SHA-256
`82946dfb60edbdb98d18771752452ceaeb27f52dc767645122421419f3e292bd`
in ignored `artifacts/p0-polymarket-2023-stratified-fill-density-20260917-02/`.
The `-01` attempt failed before any query because the local interpreter lacked
DuckDB; it remains preserved. A fixed zero-full-window-fill game
(`2023_14_CAR_NO`) had 1,020 official minute-price points but only one pregame
price change and none in-game; its response SHA-256 is
`25e482261b05a191eae7b6d5e224bf504ffc57f2b1488af8a279a33674dfece3`.
These selected samples are a warning, **not** a season-wide missingness rate
or proof that the archive is complete. Separately, source-only reconstruction
of the old 2025 split gives 42/11/11 distinct Train/Dev/Final dates with no
same-date overlap, but does not recreate a complete prior access history.
That date report SHA-256 is
`8d8a243792d93d5a7c0d740ca524bb622d77ac0c5034e39edfb51faae5609f15`.
