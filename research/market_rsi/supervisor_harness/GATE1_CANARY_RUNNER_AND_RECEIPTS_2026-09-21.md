# Gate 1 offline canary runner and receipts — 2026-09-21

Observed problem: the frozen fixture and standalone compiler had direct unit
tests, but no single zero-provider runner executed all 34 declared attacks or
persisted deterministic, hash-bound audit receipts. This change is limited to
`run_p0_gate1_executable_plan_canary.py` and its focused test. No production
adapter, compiler, contract, materializer, trade builder, packet builder,
dashboard, source manifest, or release path was changed.

Research record reused: `P0_GATE1_EXECUTABLE_PLAN_CANARY_DESIGN_2026-09-21.md`,
the Wave 1 audit and Wave 2 integration logs, and the frozen component tests.
This is implementation of their unchanged offline provenance and fail-closed
contract, not a new scientific method or changed source assumption; no live
literature query or data acquisition was needed. The simple baseline—separate
component tests—did not produce a complete-chain receipt. The alternative of
wiring a network executor was excluded by the current Gate 1 boundary.

The runner compiles the same synthetic decision twice and compares canonical
bundle bytes and literal frozen hashes. It executes all 34 frozen vector IDs
through their declared boundary. Rejection is counted only when the observed
error matches the vector's expected stable diagnostic. The lower-level builder
is actually tested for its schema, pagination and ceilings; the one forged
but syntactically valid row hash is denied at the canary's trusted-input
provenance guard because the builder alone does not authenticate that hash.
Post-compile checks now mutate every scalar leaf in the compiled bundle (370
fields, including commitments, limits and authority flags) and remove each of
the five top-level artifacts. All 375 mutations must fail against an
independently recompiled bundle; self-rehashing a tampered object is not a pass.

The `known_good` and each denial receipt contain schema, vector ID, expected
and observed outcomes, reason code, canonical input and terminal-output hashes,
manifest/materialization/request-input hashes, and request/byte/time/cost
ceilings. A rejected case has no output request artifact; its `output_sha256`
commits the stable terminal denial and `output_artifact_sha256` is null. The
catalog artifact preserves exact precommitted bytes (no newline). The optional
output directory must be fresh and outside the repository. Each file is fsynced
and hard-linked exclusively from a temporary file, and `canary-result.json`
is published last; an interrupted directory cannot be mistaken for a pass.
Same-process Python socket creation and DNS resolution are blocked while compiling.
This is an offline code boundary, not an OS-level network sandbox.

Verification under the pinned local Market RSI Python 3.12 runtime:

- Focused new tests: 11/11 passed. Combined compiler, contract, materializer,
  builder, frozen-fixture and runner tests: 66/66 passed.
- Broad `supervisor_harness` discovery: 456 run, 454 passed, 2 unrelated
  environment errors. The retired dual-E2B real-child test exited before its
  claim; the localhost marker-server test could not bind in this sandbox.
  Neither imports or executes the new runner. These were not modified.
- A separate read-only receipt check rehashed every on-disk artifact, checked
  six GET requests on the fixed HTTPS endpoint and their ceilings, all 34
  unique vector denials, all 375 post-compile denials, and zero authorization
  claims: PASS.
- `git diff --check` for tracked files and no-index whitespace checks of the
  new sources showed no whitespace errors. No provider call, network request,
  fetched bytes, Dev/Final read, admission, release, commit or push occurred.

Synthetic receipt: `/private/tmp/gate1-offline-canary-delivery.JbYJbj/receipts/`.
`canary-result.json` reports `passed=true`, 34/34 vector rejections, 375/375
post-compile denials, six planned and zero dispatched requests, zero cost and
zero fetched bytes. It is not production-path canary evidence: the compiler
remains unwired to the Controller adapter/outer runner and release manifest;
no real catalog commitment or executor exists. Release, provider sampling and
public fetching remain closed and require separate review and authorization.
