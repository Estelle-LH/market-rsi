# Market RSI local observation page

Run `python3 research/market_rsi/supervisor_harness/local_dashboard/server.py`
from the local checkout, then open `http://127.0.0.1:51361/` on this Mac.
The page binds only to loopback and reads existing state, journal, receipts and
curated human-readable logs every five seconds. It never starts a research
round, calls E2B/Tinker, or reads hidden evaluation contents.

Before assigning a subagent, the supervisor adds an entry to
`../AGENT_LOG_INDEX_2026-09-17.json` with a unique ID, task, status, next step,
and an `AGENT_LOG_*.md` filename. The agent appends timestamped material work
there: what it checked or changed, test command and result, failure, and what
remains. The supervisor updates the index when the task completes or blocks.
The dashboard discovers registered entries without another code change. An
absent log is shown as absent, never inferred from agent activity.

The index, bottleneck board, progress/intervention records and unbound agent
logs are local-only after the October 8 tracking cleanup. They remain present
in the existing local Supervisor workspace. A fresh source checkout does not
contain those private observation records; the server reports missing logs or
empty state rather than manufacturing activity. Restore original records only
from your own archive or the matching historical snapshot; do not use an old
index as evidence of currently running tasks.

Use [History and record recovery](../../../../docs/HISTORY.md#recover-records-removed-from-the-public-file-tree)
for the parent snapshot and recovery boundary. The earlier
[archive manifest](https://github.com/Estelle-LH/market-rsi/blob/cd778704138489ebb71da009b41d7b9e8223907f/research/market_rsi/LOCAL_LOG_ARCHIVE_2026-10-07.json) still records the
October 7 archive's original paths/hashes and preserved `index-snapshot.json`.

These logs are curated work records, not private reasoning, uncaptured tool
events or model trajectories. Do not put credentials, raw private data or
protected evaluation material into a log. New diagnostic code is not a live
connection or isolation pass until its own fresh gated canary confirms it.
