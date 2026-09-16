# Historical sports capture for Train/Dev

Runner-only source context. Do not pass sports-project analyses, conclusions,
thread messages or this note to the researcher as learned experience.

## Read-only findings

Inspected the existing sports betting project and its research Linode
173.255.231.4 on September 7. No source files, services or jobs were changed.

- Native Kalshi raw hourly archives exist under /opt/d10/raw/data/kalshi/,
  starting August 20. Daily derived metadata is under /opt/d10/research/.
- Daily manifests report: August 20 21 hours; August 21 24; August 22 4;
  August 23 and 24 zero; August 25 22; every day August 26–September 6 24.
  The last range is twelve consecutive days with all hourly files present.
  It does not prove every game or reconstructed book is continuously valid.
- September 6 manifest reports complete_day=true and was generated at
  2026-09-07T03:28:29Z. Its QA file was generated earlier, at 02:31:22Z.
  The QA volume-change warnings are not proof of missing capture; reconcile
  generation times and source files before classifying them.
- Normalized market metadata includes venue, market, outcome, league, matchup,
  outcome_label, game_start_utc and market_slug. Normalized files contain more
  than one venue; isolate native Kalshi and preserve stream/source identity.
- Separate Polymarket US capture directories exist for August 26–September 7
  under /opt/ez/data/polymarket_us/live/. Closed days include compressed raw
  observations, changes, events and archive manifests with hashes. This is a
  different venue/source, not an automatic replacement for the Kalshi experiment.

## Proposed use, not a frozen scientific split

Use audited Kalshi games from August 26–September 2 for Train, September 3–6 for
Dev, and later untouched games for final Test. Coverage and whole-game chronology
must be verified before fixing these dates. Games span UTC file boundaries;
place all related contracts and rows together, exclude boundary-crossing labels,
and enforce information availability at decision time.

The sports project already analyzed some September 1–6 data. This history can
support learning and diagnostics, but it is not untouched final-test evidence.
Do not choose a market or target because that project's PnL looked attractive.
Count games and dates, not order-book updates, as the independent groups.

## Checks still needed

1. Verify the original native Kalshi collector's clock and session semantics
   using a permitted mirror/export. The denied source-host SSH must not be
   retried or bypassed. Existing REST collector code is not proof of this
   historical WebSocket envelope.
2. Replay with this source's explicit yes_asks convention; carry snapshots
   across files, exclude gaps and invalid books, and keep immutable ordinals.
3. Materialize causal features/labels and hash a real whole-game split. Existing
   split_manifest.py only validates metadata and is diagnostic-only.
4. Integrate the real isolated researcher/coder worker before scored calls.

The separate Polymarket US panel builder is not ready to reuse unchanged as a
Kalshi task: it selects exchange time or receipt time for row ordering, joins
event state as of receipt, deduplicates exchange timestamps, and constructs
last-observed-mid horizon labels. That requires an availability/staleness audit;
it does not establish executable fills, queue position or realizable PnL.

There is enough archived material to pursue Train/Dev preparation now. There is
not yet a verified, scored task dataset. If later untouched games are insufficient
by the eight-hour deadline, report final evaluation pending without weakening
the separation rule.

## September 7, 09:23 UTC: actual metadata breadth audit

A new read-only count processed the 12 daily market CSVs for August 26–September 6
on the authorized research host: 27,695,490 bytes total, each source SHA-256 saved.
The script groups recognized native Kalshi tickers by event stem, joining the two
outcome contracts and repeated mentions across daily files. This convention is
a candidate game mapping, not yet independent event/quote admission.

For the observed MLB GAME series it found:

- 418 distinct contracts corresponding to 209 candidate game entries.
- 109 with scheduled start dates in August 26–September 2, and 55 in September 3–6.
- The other 45 start outside that window: 9 on August 25 and 36 on September 7–9.
- 169 entries occur in multiple daily files. **44 occur in both proposed file-date
  partitions**, so simply calling older files Train and newer files Dev leaks
  game identity across the split. Group all related contracts/rows by whole game,
  then enforce chronological availability and embargo rules.
- All 209 recognized MLB event groups had consistent schedule/matchup/league
  metadata across their mentions. This is consistency of derived metadata, not
  external proof of the scheduled time or actual capture.

Across all series, 48 native metadata rows did not match the audited ticker/outcome
shape and were counted as exclusions, not silently repaired or added to these
event totals. Other recognized series were NCAAF (449 candidate events), NFL (48)
and WNBA (17); these are listings, including future games, not usable task counts.
No family was selected by historical returns or another project's results.

This shows materially more candidate breadth than the seven games in the small
two-hour label diagnostic. It does NOT establish 109 usable Train games, 55 usable
Dev games, any untouched final tasks, continuous book coverage or valid arrival
clocks. Original source/session provenance and quote-level auditing still block
scoring. No model was trained or scored, no trade occurred, and no source file
was changed.

Evidence and full read-only script: `artifacts/kalshi-research-glm53-20260907-01/
historical-metadata-breadth-01.json`. The full event-detail list is reproducible
from the recorded CSV/script hashes; its hash is saved, but the summary transfer
does not claim to contain that list. Seven offline counter tests cover outcome
grouping, midnight duplicates, future listings and inconsistent metadata.
