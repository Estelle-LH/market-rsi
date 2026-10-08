# Gate 1 v0.1.26 fetch-adapter component implementation receipt

Timestamp: 2026-09-28 (America/New_York)

Result: **PASS for the bounded component; integration remains intentionally fail-closed until the separately owned shared fetch seam is merged and reviewed.**

## Scope and action boundary

- Implemented only the seven code/test paths assigned to this component plus this receipt.
- Did not modify `p0_gate1_public_fetch.py`, `p0_gate1_watched_fetch.py`, `protocol_source_release.py`, durable control state, authoritative budget state, or release/Git state.
- No real source fetch, network request, provider call, credential read, purchase, data admission, Train/Dev/Final read, training, evaluation, or publication occurred.
- All transport behavior in component tests was a process-local fake behind a patched lazy shared-runner resolver. Production code exposes no callable or CLI transport injection.

## Implemented contract

- Pure adapter exports distinct `market_p0_gate1_source_scope_fetch_task_v1`, `market_p0_gate1_source_scope_fetch_admission_v1`, and `market_p0_gate1_source_scope_public_snapshot_receipt_v1` schema constants, exact closed field sets, and `validate_task_admission(task, admission)`.
- Adapter independently recompiles the exact fixed D0 decision/provenance/packet twice through `compile_document_request_plan`, requires both compilations and the caller bundle to equal the fixed `34b452...b812c` plan / `7f340e...b931` bundle commitments, replays the exact zero-effect canary verifier, binds the current v0.1.26 release/source/runtime, and requires a canonical private dual-authority file.
- Authorization input reading uses `O_NOFOLLOW`, bounded looped reads, single-link regular-file checks, fd/name identity checks, and stable ancestor dev/inode/mode checks.
- Live child has one fixed durable path layout, independently rechecks the outer-parent PID/command, exact watchdog claim, authoritative global-state active head/decision, authoritative zero-budget snapshot, and calls only the lazy shared `run_preclaimed` seam. It does not claim or close the watchdog.
- Outer parent permanently claims the fresh attempt ID before launch, sanitizes proxy/credential/custom-CA/Python injection from the child environment, binds the pinned runtime, polls/ticks the watchdog, verifies exact process/container absence, records causal cleanup/failure receipts, and leaves a successful global claim active pending independent review.
- Success preserves canonical 0600 copies of authorization, full request bundle, runtime receipt and canary-verification record, plus binding, parent claim, child result, snapshot receipt, snapshot, watchdog chain/snapshot, global-state journal, decision and budget commitments.
- Snapshot evidence includes exact final URL and normalized `content_encoding: null`; counters reject booleans; redirects/retries/provider calls remain exactly zero; no formal admission or scientific claim is made.
- Pure terminal verifier uses descriptor-based immutable reads, replays the prior canary verifier, rechecks every copied input and output commitment, exact watchdog grammar/progress endpoints/deadlines/claim head, global active-pending-review state, authoritative budget-none state, and terminal process/container evidence.
- A preterminal receipt is written before watchdog close; post-close write failure has an explicit terminal failure artifact and never enables retry.

## Exact file evidence before this log

- `p0_gate1_source_scope_fetch_adapter.py` — 671 lines — `e56ef7682464d1723bd5d97f071cbdef9713dec0db3c418a91d6f8657b072273`
- `p0_gate1_source_scope_watched_fetch_child.py` — 347 lines — `117d09153b97bf937dde936b60273d0aab8b85e17350ef3be08854d83adb4189`
- `run_p0_gate1_source_scope_watched_fetch.py` — 716 lines — `e8e514889c270da59ee36198927df0af775fea3690c5f94705861959f9b4a67b`
- `source_scope_fetch_receipt.py` — 449 lines — `09e5ac6e2e3e94ed2b228891f2e010069200d3b01f9f7223a31d03f87e4e4273`
- `test_p0_gate1_source_scope_fetch_adapter.py` — 212 lines — `59566568ff5144e3275c733fe85fecf504f99da6a802a8b0c4c8521a10ce7c0c`
- `test_run_p0_gate1_source_scope_watched_fetch.py` — 498 lines — `1d0e58fbcb88e3b059b9b7ee1e2312ac4a33fff69d7c0de4e91ebf4c47b0dd1d`
- `test_source_scope_fetch_receipt.py` — 214 lines — `aa921478ea1162ae78a92c0e14f439a348da30075532da7a97395e39b24e8109`

## Test evidence

Pinned runtime: `/Users/estelle/.cache/market-rsi/runtimes/ds-py312-20260912-01/bin/python`.

Focused component command:

```text
PYTHONDONTWRITEBYTECODE=1 <pinned-python> -m unittest \
  supervisor_harness.test_p0_gate1_source_scope_fetch_adapter \
  supervisor_harness.test_run_p0_gate1_source_scope_watched_fetch \
  supervisor_harness.test_source_scope_fetch_receipt -q
```

Result: **23/23 PASS** in 0.199 seconds. Coverage includes exact nested schema closure, D0 recompilation, real canary-summary shape, short-read completion, separate authority rejection, parent-before-child claim ordering, no child claim/close, fake receipt attacks, sanitized argv/env/cwd, authoritative path rejection before `Popen`, global close-failed on launch failure, success remaining active pending review, pinned-runtime/subset drift, cleanup before command stabilization, exact attempt-label container stop versus wrong-label no-stop/failure, identity/container/budget drift terminalization, immutable receipt-tree replay, counter/bool attacks, global closure/root aliases, symlinks, snapshot mutation, and watchdog first/last progress binding.

Adjacent command:

```text
PYTHONDONTWRITEBYTECODE=1 <pinned-python> -m unittest \
  supervisor_harness.test_p0_gate1_source_scope_request_plan \
  supervisor_harness.test_p0_gate1_source_scope_request_plan_canary_child \
  supervisor_harness.test_run_p0_gate1_source_scope_request_plan_canary \
  supervisor_harness.test_source_scope_request_plan_canary_receipt \
  supervisor_harness.test_p0_gate1_public_fetch \
  supervisor_harness.test_p0_gate1_watched_fetch \
  supervisor_harness.test_supervisor_watchdog \
  supervisor_harness.test_global_state_gate -q
```

Result: **44/44 PASS** in 0.067 seconds.

Full Supervisor discovery command:

```text
PYTHONDONTWRITEBYTECODE=1 <pinned-python> -m unittest discover \
  -s supervisor_harness -p 'test_*.py' -q
```

Result: 754 cases executed; 749 passed, 1 failed and 4 errored for pre-existing/environmental actual-runtime checks outside this component: dual-E2B local-runtime path classification (two errors plus one expectation failure), sandbox denial of a localhost socket bind, and the actual Gate 1 production-CLI canary's environment-dependent terminal acceptance. The screen CLI also emitted its expected refusal to perform network work without an explicit execution flag. No failed case named or exercised a new fetch-component module.

## Remaining integration needs (fail closed)

1. Shared integration must add `p0_gate1_public_fetch.fetch_source_scope_snapshot` using the adapter-owned schema constants and validator, with exact URL/method/params/headers, no default proxies/custom CA/credentials, duplicate case-folded header rejection before dict conversion, no redirects/retries, one request, byte/time limits, exact final URL and no content encoding.
2. Shared integration must add `p0_gate1_watched_fetch.run_preclaimed` with the exact keyword interface consumed by the child: `watchdog, task_id, task, admission, output, pid, process_command_sha256, budget_snapshot_sha256, receipt_validator, clock=None`. It must verify the existing parent claim, perform pre/post material heartbeats, report at most one incident with data gate `not_applicable` and budget `none`, and never claim or close.
3. Release integration must register all new component and test files in `protocol_source_release.py`, run the independent component review, then publish v0.1.26 before the fresh zero-provider canary and single watched documentation fetch.
4. The successful fetch leaves global state active pending independent review by design. The separately planned review/closure step must close passed only with the immutable independent-review hash; this component never self-approves or closes the global cycle passed.
