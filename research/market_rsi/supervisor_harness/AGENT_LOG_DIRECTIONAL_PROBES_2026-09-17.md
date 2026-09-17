# Directional protocol-probe work log — 2026-09-17

All times are America/New_York (EDT). This is local, unpaid repair evidence, not
an E2B connectivity or isolation result.

## By 14:29 — Inspect and diagnose

- Read `research/market_rsi/AGENTS.md`, `supervisor_harness/RESEARCH_STATE.md`,
  `protocol_network_probe.py`, the host directional component, and both focused
  test files. The existing guest probe made four sequential public/peer ×
  proxy/direct GETs but wrote only a final report. An SDK command timeout could
  therefore leave the host with no application-level result even if an earlier
  request had finished. The prior live canary timed out during A→B, while B→A
  was not attempted; neither direction has a route verdict.
- Compared retaining only the final report with per-attempt progress. Chose
  immutable start and complete receipts plus flushed stdout milestones so the
  host has evidence during a long-running command. Kept the final report shape
  and fail-closed full review unchanged. Coordinated the CLI and receipt schema
  with the SDK-timeout agent before integrating the host call.

## By 14:29 — Implement and check

- Changed only `protocol_network_probe.py` and
  `test_protocol_network_probe.py` for probe behavior. Added optional
  `--progress-prefix`: each of four attempts atomically publishes a
  `<prefix>-NN-start.json` receipt before its GET and a
  `<prefix>-NN-complete.json` receipt after it. Matching bounded JSON lines are
  flushed to stdout. Receipts bind both host-selected URL hashes, attempt
  index, endpoint role and proxy mode; complete receipts contain only HTTP
  status, response-body hash/truncation or error type, never a raw URL, body,
  marker or credential.
- Added `review_progress(...)` to validate partial receipt shape, URL binding,
  unique attempt/phase and completed observations. It reports started and
  completed indexes and any positive HTTP/peer-marker observation, but never
  asserts isolation. Missing or in-flight attempts are inconclusive, not
  blocked. Existing full `review(...)` retains its report shape and uses the
  same bounded observation validator. The final output freshness check now
  happens before network activity.
- Added focused tests for four receipts, stdout content, an interruption after
  one complete request, malformed/forged partial records and stale receipts.
  Ran `PYTHONPATH=research/market_rsi python3 -m unittest
  supervisor_harness.test_protocol_network_probe
  supervisor_harness.test_e2b_role_network_component -v`: **16 tests passed**.
  `git diff --check` found no whitespace errors. No paid E2B or Tinker call was
  made, and no old canary artifact was changed.

## Remaining caveats

- These object-shaped offline tests do not prove that E2B delivers stdout
  callbacks or allows post-timeout receipt reads in the live setting. The host
  component now attempts bounded capture/recovery separately; its live behavior
  still requires a fresh authorized canary under a new source identity.
- A completed negative request does not prove the route is blocked, and a
  partial or absent report cannot establish effective network isolation. A
  validated HTTP response remains positive application-channel evidence that
  must fail closed in host review.
- No A→B or B→A application-route verdict, GLM-authored round, or empirical
  prediction result is claimed here.
