# Polymarket US data readiness

Updated: 2026-09-07. This is a data-readiness result, not a model result or a
profit claim.

## What the first experiment can test

Keep the data, 60-second target, row mask, fees and evaluation code fixed. Give
the baseline and the researcher candidate the same Train rows, then compare
their predictions on the same Route-Dev rows. The one changed stage is the
prediction method. The first question is simply: **does the candidate predict
the 60-second midpoint change better than the fixed baseline on later games?**

Primary diagnostic metric is paired MSE, reported by game and by day. Calibration
is auxiliary. PnL is a later stage and must not be changed in this first A/B. Audit-Dev is
opened only after the method is fixed. Test remains hidden.

## Data contract now implemented

- The source is the existing independent REST poller on `173.255.231.4`. It is
  not the inaccessible Kalshi WebSocket collector.
- Each successful response is a complete book snapshot. Sequence and reconnect
  reconstruction do not apply. A timeout or absent poll is missing data.
- `observed_at` is the formal feature-availability time. `receive_ns` is used
  only as a cross-check; an `observed_at` before receipt or more than five
  seconds after receipt is rejected. Exchange `transact_time` is never used for
  information availability.
- Event identity is the stable pair `event_id` / `event_slug`; all market slugs
  for one event stay in one game group. Null extra-watchlist identities are
  excluded explicitly.
- Only open, HTTP-200, unflagged, two-sided books with positive L1 sizes enter
  the materializer. Prices or sizes are not filled in.
- Decisions are sampled every 60 seconds per market. The label is the midpoint
  change at the first valid book at or after 60 seconds. If that book is more
  than five seconds late, the row is censored. No later mark is selected and no
  zero label is invented.
- Rows must be pregame and within the frozen six-hour pregame window.
- Train, Route-Dev, Audit-Dev and Test use complete game groups in start-time
  order. A split is rejected if simultaneous games cross a boundary or if an
  earlier split's labels are not available before the next split's features.
- The public projection exposes labeled Train, feature-only Route/Audit Dev,
  and only a salted commitment for Test.

Implementation: `polymarket_data.py`. Unit tests: 15/15 passing in
`tests/test_polymarket_data.py`.

## What exists on the server

Read-only inspection found closed-day archive manifests for August 26 through
September 5. Each manifest records original and compressed hashes for book,
event, change and error streams. One September 5 manifest commits a 1.695 GB
uncompressed book-observation file and a 792 MB event-observation file. The
September 6 and September 7 files remain live/unarchived at this check.

The smaller closed-day event-change archives contain 164 candidate event slugs
whose scheduled dates are August 26 through September 5:

| Prospective diagnostic block | Scheduled dates | Candidate events |
| --- | --- | ---: |
| Train | Aug 26–Sep 1 | 106 |
| Route-Dev | Sep 2–3 | 27 |
| Audit-Dev | Sep 4–5 | 31 |

These are catalog counts, not yet counts of games with valid 60-second labels.
The materializer must still scan the committed book archives and apply all
censor rules. No score was inspected when producing these counts.

The collector is an independent full-book REST polling service. Supervisor
evidence records zero service restarts since `2026-09-02T06:59:31Z`. The
reported collector-source hash begins `b6562f`; the full hash must be placed in
the experiment receipt rather than using this abbreviation.

## Test boundary and claim limit

All source periods at or before the prospective boundary
`2026-09-07T16:08:41Z` are diagnostic. A real untouched Test must use data first
available after that boundary and must not be shown to the controller,
researcher, coder or checkpoint selector. Tonight's first round can produce a
verifiable Train/Route-Dev/Audit-Dev comparison, but it cannot satisfy the
20-untouched-session promotion gate or support a profitability claim.

## Remaining data work before a scored round

1. Freeze the exact full collector-source hash and selected archive manifests.
2. Stream the selected event and book archives through the validator; publish
   accepted/censored counts by reason, game and day.
3. Freeze exact whole-game assignments only after confirming each partition is
   nonempty and passes the strict information-time embargo.
4. Give the experiment runner only Train plus feature-only Dev projections.
   Keep raw archives, labels and Test in the runner-owned area.
5. Run the fixed baseline and one candidate on the identical Route-Dev row mask;
   use Audit-Dev once after the method is frozen. Continue collecting future
   Test sessions without opening them.

No server file or service was changed, no large raw file was copied, no model or
E2B call was made, and no paid cost was incurred by this data task.

## September 8 update: first new closed day

The existing archive timer sealed September 6 normally at 05:19 UTC. The
collector stayed active with zero restarts. A read-only server-local pass of the
same materializer produced 10,958 valid 60-second rows across 12 complete games.
Using the already-declared `20 rows` and `persistence MSE >= 5e-7` learning-task
gate, 8 games and 8,757 rows are eligible. Source and downloaded-result hashes
matched before the isolated server temp directory was removed.

September 6 is before the prospective boundary, so it is learning data only. It
can support one multi-game Dev round, not three sequential rounds on the same
day: the current runner requires every prior Train label to be available on a
strictly earlier UTC date than the next Dev decision. A causal three-round plan
therefore needs separated dates, for example September 2, 4 and 6. September 7
and later remain sealed for the common Transfer set. The exact receipt is
`artifacts/polymarket-formal-data-20260908-01/readiness-2026-09-06.json`.
