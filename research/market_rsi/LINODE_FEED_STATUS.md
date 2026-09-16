# Linode feed status

Latest bounded read-only check: September 10, 2026, 09:07 UTC. The two exact
services below are active/running, with PIDs409353/504855 and NRestarts=0.
Polymarket US lists date directories August26-September10; Kalshi tennis REST
lists daily filenames September7-10. This check read service properties and
directory names only: it did NOT verify fresh quote arrivals, complete sessions,
archive hashes, disk capacity or current discovery counts. No raw data transfer,
service mutation, restart or redeployment. Sports capture is not an automatic
compatible validation source for the selected historical BTC predictor.

Latest bounded read-only check: September 7, 2026, 13:19 UTC.
Both exact services remain active/enabled with the same PIDs and zero restarts.
Polymarket US has actual fresh HTTP200 book observations (last read 13:19:48 UTC,
no QA flags). Kalshi tennis has fresh discovery (file updated 13:19:44 UTC) with zero active
pairs: healthy idle, not quote coverage. Disk free: 78.792 GiB. No service, code,
rate, universe or storage changes. Existing restart/boot recovery stays intact.

Research was closed at **September 7, 13:20 UTC**, before its 13:33 UTC deadline.
The final report records no scored research comparison. Only the already-authorized
feed-health monitoring continues. This supersedes all earlier research scheduling
notes; it does not authorize another experiment or additional paid work.

## Initial check (preserved)

Checked September 7, 2026, 04:58 UTC (00:58 ET).

Server: `173.255.231.4`. No new server or duplicate collector was launched.

| Feed | What is actually happening |
| --- | --- |
| Polymarket US | Existing service is running. Real book observations are arriving; the current file grew from 349,267,439 to 350,053,959 bytes during the checks. |
| Kalshi tennis REST | Existing service is running. It has written 78 fresh discovery records but reports zero active pairs. No orderbook observations yet; this is healthy idle, not a market-data sample. |
| Older native Kalshi WebSocket | Local files are copied from a separate capture host. Latest inspected local file ended around 02:14 UTC. Source liveness and timestamp/session provenance remain unverified because direct SSH access was denied. |

Both local collector units are enabled for boot and have `Restart=always`,
`RestartSec=5`. There were no recorded systemd restarts at this check. These
processes run on Linode independently of the Mac. No healthy service was restarted.

Disk: 78 GiB available, 48% used. Keep the existing Polymarket US 20 GiB free-space
floor. No data was deleted, no rate limit changed and no port opened.

The existing task heartbeat, now **Market RSI and Linode feed health**, checks
every 15 minutes and reports material failures/recoveries here and in this task.
Only one heartbeat can attach to this task, so the existing one was updated;
no second monitor was created. The pre-existing daily
**Linode 每日检查与 Orderbook Backfill** automation was left unchanged. App-based
checks require their host to be available; server-side restart/boot recovery does
not. Research still stops at its original completion/deadline (September 8,
03:00 UTC); only feed-health checks continue afterward. This does not extend
the experiment's budget or authorize additional paid runs/backfills.

Exact units:

- `ez-kalshi-tennis-l2.service`, PID 504855 at this check.
- `ez-polymarket-us-capture.service`, PID 409353 at this check.

Data locations:

- `/opt/ez/data/kalshi_tennis_l2/live/`
- `/opt/ez/data/polymarket_us/live/`
- `/opt/d10/raw/data/kalshi/` (downstream copy, not proof of live capture)

Do not treat discovery/health records as real quotes, confuse daily-sync latency
with a dead source feed, or repeatedly restart a collector when no matches are live.
