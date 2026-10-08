# v0.1.26 exact fetch-binding integration and candidate test receipt

Timestamp: 2026-09-28 (America/New_York)

Result: **PASS for shared integration and candidate test/privacy scope; ready
for a fresh non-author source review.**  This is not release, canary or fetch
evidence.

## Plan and scope

- Superseding plan
  `SUPERVISOR_GATE1_V0126_RELEASE_CANARY_FETCH_2026-09-28-v3.json` passed its
  dispatch gate and the `exact_fetch_binding_integration` ready-step after both
  component logs were independently hash-checked.
- No public network request, provider/model call, credential read, purchase,
  authoritative budget/state claim, release/Git mutation, canary, data
  admission, Train/Dev/Final read, training or evaluation occurred.
- The source candidate still grants no rights, data-admission or prediction
  authority.  It can only execute the later separately authorized fixed
  documentation GET after release and canary gates pass.

## Shared integration

- `p0_gate1_public_fetch.py` preserves the legacy task/admission API and adds a
  distinct `fetch_source_scope_snapshot(task, admission, output)` path with no
  injectable transport.  `UrlLibTransport` now installs `ProxyHandler({})`,
  rejects duplicate case-folded `Content-Type`, `Content-Encoding`, `ETag` or
  `Last-Modified` before dict conversion, follows no redirect, performs one
  bounded GET, accepts only absent/identity content encoding and records exact
  final URL plus all-false downstream authority.
- `p0_gate1_watched_fetch.py` preserves legacy `run` and adds
  `run_preclaimed`.  It requires the parent's exact active research claim,
  PID/command/input/deadlines, emits the input and receipt hashes as its two
  material heartbeats, invokes the fixed source-scope seam, reports at most one
  failure incident, and never claims or closes the watchdog itself.
- `protocol_source_release.py` registers the bridge, dedicated canary,
  release/canary-bound fetch adapter, parent/child/verifiers and all relevant
  adversarial tests.  It does not include plans, logs, private run artifacts,
  `ARCHITECTURE.md`, fetched bytes or durable control state.
- The new integration test compiles the reviewed D0 twice, exercises one exact
  fake transport call, rejects cross-schema/authority/redirect/encoding/size
  mutations before success, and proves the dedicated bridge canary imports no
  fetch or network module.
- The first formal non-author review correctly rejected the earlier
  `b31533d2...bbf7969` candidate.  It reproduced a fake mapping with duplicate
  case-folded Content-Type fields and an oversized Content-Type that bypassed
  the seam-level checks, and it found that the live child still used
  non-isolated `python -B -m` startup.  The candidate was not published.
- The repaired seam normalizes the mapping again and caps Content-Type at 500
  UTF-8 bytes.  The live parent now starts the exact child file with
  `python -I -B`; before project imports the child adds only the controlled
  source root derived from `__file__`.  New adversarial tests cover both
  findings.  This produced a new candidate requiring a wholly fresh review.

## Final shared-file evidence

- `p0_gate1_public_fetch.py` —
  `c427e837f92b9a2cc8368f9cb0a85147d2adeea908a225e75ba4252fcb08cbfe`
- `p0_gate1_watched_fetch.py` —
  `c694e9104e865590ba9aa5345ce1c79fd6c067010f748abf7f4202fa2cd64ec7`
- `p0_gate1_source_scope_watched_fetch_child.py` —
  `e5b21783c1594eabd2e89d0bc46fc23c4fd1c525a3bdea2fcdbb11f9511bbaec`
- `run_p0_gate1_source_scope_watched_fetch.py` —
  `e604bde85cee62c5b70399fb087c3a323668c249edcee6bac6c08e4023888e93`
- `protocol_source_release.py` —
  `b3c4c69d5776f601ba0849f579380a864d711ed313d26efe60705afd8e9ccd9c`
- `test_p0_gate1_public_fetch.py` —
  `8531bfa07e36533703c76001f66b3f6a90f3891818d9b0f90931cf26a12e27fa`
- `test_p0_gate1_watched_fetch.py` —
  `a39be95da341f029cb7084193d74320184fe5da04770a2d6af7b9b6364f105f5`
- `test_p0_gate1_source_scope_fetch_integration.py` —
  `45b8043ed3662b761dd5ec33e29775a8744d829299f03c231fa8a94442ee6cda`
- `test_run_p0_gate1_source_scope_watched_fetch.py` —
  `6f32421ca98147dffd184c69d71fc0d396ee9e6d3a8641a17945cd11ce487658`
- `test_protocol_source_release.py` —
  `2576d10bd7ff8b763bd0bf344cd497324071899f20162d9f0f87786620386f40`

## Test and privacy evidence

- Integrated bridge/fetch/manifest suite: **82/82 PASS**.
- Final complete pinned-runtime discovery from `research/market_rsi`:
  **516/516 PASS, 1 existing skip**, 56.966 seconds.  It ran outside the
  filesystem/process sandbox because the exact actual-child identity test
  cannot observe its child correctly inside that sandbox; that test also
  passed alone outside the sandbox before the complete run.
- `git diff --check`: PASS.  All v3/board/index JSON parses, the v3 dispatch
  gate and shared-integration ready gate pass, and the bottleneck board passes
  with eight active items.
- Exact controlled manifest: **358 files**, canonical source digest
  `2e3b6b14e64630be8ed7b4cdc434a9c8b66766df88d01e73ede5bcc9f741a23f`.
- The controlled manifest contains no `AGENT_LOG`, `SUPERVISOR_GATE` or
  `ARCHITECTURE` path.  The new public candidate paths contain no literal
  `/Users/` path or common private-key/token pattern.  The only earlier broad
  `sk-` scan match was the harmless test identifier suffix `task-001`; the
  refined credential scan is empty.

## Remaining gates

1. Fresh non-author review must replay the exact D0, all source hashes, tests,
   public allowlist and clean-origin release method.
2. Only after that PASS may the Supervisor create v0.1.26 from a fresh
   `origin/main` worktree.  Current local `main` remains private and must not be
   pushed.
3. Release-bound canary, independent canary review, one-shot fetch, independent
   fetch review and review-hash global-state closure remain serial gates.
