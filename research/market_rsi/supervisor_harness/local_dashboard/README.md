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

These logs are curated work records, not private reasoning, uncaptured tool
events or model trajectories. Do not put credentials, raw private data or
protected evaluation material into a log. New diagnostic code is not a live
connection or isolation pass until its own fresh gated canary confirms it.
