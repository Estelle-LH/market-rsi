# Gate 1 v0.1.26 independent source review

Timestamp: 2026-09-28 (America/New_York)

Reviewer: non-author `controller_launch_preflight` agent, read-only.

Verdict: **PASS**, limited to the new frozen source candidate and the exact
clean-origin public release method.  The earlier candidate
`b31533d23e04afbd9ece9b95d6487005ffb464a7774160d5da786b378bbf7969`
remains a terminal REPLAN and was not upgraded or published.

## Exact reviewed candidate

- Controlled manifest: 358 files, no duplicates.
- Controlled source digest, stable across two independent reads:
  `2e3b6b14e64630be8ed7b4cdc434a9c8b66766df88d01e73ede5bcc9f741a23f`.
- Manifest contains no `AGENT_LOG`, `SUPERVISOR_GATE`, authorization, state,
  roadmap or `ARCHITECTURE` path.
- D0 compiled twice to bundle
  `7f340e20702a03200628cbad06f300257252d06a8b564985cbbf60ad8535b931`
  and plan
  `34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c`.
- Durable D0 file hashes independently matched: decision
  `01054900be9075f0fef57b9e1481abb73f722b2223d664df24db8e6c81dcc216`,
  provenance
  `bcd768989e33af91e42ba4d3db35201f294fb6be6d9a3182165f890140eeec65`,
  packet
  `bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd`.

## Independent adversarial replay

- Duplicate case-folded `Content-Type` mapping: REJECT.
- More-than-500-byte `Content-Type`: REJECT.
- Empty environment plus pinned `python -I -B <exact CHILD_ENTRY> --help`:
  PASS; the child inserts only the controlled source root derived from
  `__file__` before project imports.
- Focused integration/publication suite: 82/82 PASS.
- Global-state/watchdog/local-control adjacent suite: 22/22 PASS.
- `git diff --check`: PASS.
- The separate Supervisor full pinned-runtime discovery on the same bytes was
  516/516 PASS with one existing skip.

The reviewer confirmed the distinct closed task/admission languages, separate
fetch and retention authority, release/runtime/canary/authorization cross
bindings, explicit `ProxyHandler({})`, no redirect/retry, parent-before-Popen
global claim, exact PID/command/budget/container monitoring, two material
heartbeats, at most one failure incident, and pure terminal replay.  A success
closes only the watchdog and leaves global state active pending independent
review; a failure closes failed and the ID cannot be reused.  Passed global
state closure requires a nonzero independent review file hash.

## Exact public allowlist

Only these 22 repo-relative paths under
`research/market_rsi/supervisor_harness/` may be transferred from the reviewed
candidate into a fresh clean `origin/main` worktree:

```text
p0_gate1_public_fetch.py
p0_gate1_source_scope_fetch_adapter.py
p0_gate1_source_scope_request_plan.py
p0_gate1_source_scope_request_plan_canary_child.py
p0_gate1_source_scope_watched_fetch_child.py
p0_gate1_watched_fetch.py
protocol_source_release.py
run_p0_gate1_source_scope_request_plan_canary.py
run_p0_gate1_source_scope_watched_fetch.py
source_scope_fetch_receipt.py
source_scope_request_plan_canary_receipt.py
test_p0_gate1_public_fetch.py
test_p0_gate1_source_scope_fetch_adapter.py
test_p0_gate1_source_scope_fetch_integration.py
test_p0_gate1_source_scope_request_plan.py
test_p0_gate1_source_scope_request_plan_canary_child.py
test_p0_gate1_watched_fetch.py
test_protocol_source_release.py
test_run_p0_gate1_source_scope_request_plan_canary.py
test_run_p0_gate1_source_scope_watched_fetch.py
test_source_scope_fetch_receipt.py
test_source_scope_request_plan_canary_receipt.py
```

Privacy scan found no absolute `/Users/` path, private key, bearer token or
credential-like value in these files.  `ARCHITECTURE.md` and every internal
orchestration/state/budget/progress artifact remain excluded.

## Release constraint

Current local `main` at `8e4a02b1bf619a9f6e4d09e415c3fcbac089ccca`
must not be pushed.  The last locally observed `origin/main` was
`6403028a39eae77536e033eef6b505294f1699bb`; it must be freshly network-verified
with tag absence before a new isolated worktree is created.  Transfer exactly
the 22 paths, reproduce their hashes/source digest/tests, create a new annotated
`market-rsi-protocol-v0.1.26` tag, push only a fast-forward release commit and
that new tag, then verify the remote bytes.  No force push or tag move is
allowed.

This PASS is not canary, fetch, state/budget mutation, data-admission, training
or scientific-result evidence.
