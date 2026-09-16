# Historical Kalshi collector evidence needed

We already have the copied market-data files. We do **not** need another large
data download. We need a small, non-secret export from the original capture host
`173.255.234.236` so we can tell whether a price was available at the time the
backtest says it was.

Please export only:

- The exact collector source that produced `/opt/d10/raw/data/kalshi/`.
- Its systemd unit text or other startup command, without environment values.
- Existing startup, reconnect, subscription and snapshot logs for the relevant
  August 26–September 6 sessions. If no such logs were saved, record that fact.
- The existing capture/archive manifest that links those sessions to the raw
  files and source version.

Do not export `.env` files, SSH material, API keys, tokens, passwords, complete
process environments, unrelated services or another copy of the raw books.

The review needs to answer five concrete questions:

1. Is envelope field `t` Unix milliseconds from the collector host?
2. Is `t` recorded immediately after a WebSocket message is received and before
   that message is written to the archive?
3. Is `seq` scoped to one subscription/session, rather than one market?
4. On reconnect or sequence reset, does the collector start a new stream epoch
   and require a fresh snapshot before accepting deltas?
5. Which exact sessions/files were captured by this source version, and where
   are gaps or restarts recorded?

An evidence export is not automatically trusted just because it contains a JSON
claim. The source and existing records will be reviewed, hashed and frozen. If a
fact was never recorded, we keep it unknown rather than reconstructing a log.

Current access status: the in-app Linode page is open at its login screen. Once
the account is logged in, we can use the original server's read-only console to
locate and export these files. No collector restart or configuration change is
needed.
