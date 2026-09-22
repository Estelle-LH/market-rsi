# Gate 1 offline canary runner and receipts — 2026-09-21

Observed problem: the frozen fixture and standalone compiler had direct unit
tests, but no single zero-provider runner executed all 34 declared attacks or
persisted deterministic, hash-bound audit receipts. The initial isolated
runner change was limited to `run_p0_gate1_executable_plan_canary.py` and its
focused test. The subsequent integration also repaired the compiler, trade
builder, and their tests; see the integration update below. No production
adapter, dashboard, source manifest, or release path was changed.

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
error matches the vector's expected stable diagnostic. After integration, the
lower-level builder itself checks schema, pagination, ceilings, and the full
selected rows against precommitted catalog bytes. The forged but syntactically
valid row hash is injected at that builder boundary and rejected there.
Twenty-six additional post-compile mutations cover task, materialization,
request-input and catalog bindings, exact manifest, receipt contract, budgets,
handler/policy authority and claim boundaries. The complete bundle is compared
with an independently recompiled value; self-rehashing a tampered object is
not a pass.

The `known_good` and each denial receipt contain schema, vector ID, expected
and observed outcomes, reason code, canonical input and terminal-output hashes,
manifest/materialization/request-input hashes, and request/byte/time/cost
ceilings. A rejected case has no output request artifact; its `output_sha256`
commits the stable terminal denial and `output_artifact_sha256` is null. The
catalog artifact preserves exact precommitted bytes (no newline). The optional
output directory must be fresh and outside the repository. Each file is fsynced
and hard-linked exclusively from a temporary file, and `canary-result.json`
is published last; an interrupted directory cannot be mistaken for a pass.
The same-process socket connect/send-to paths are blocked while compiling.
This is an offline code boundary, not an OS-level network sandbox.

Initial isolated-runner verification under the pinned local Market RSI Python
3.12 runtime:

- Focused new tests: 11/11 passed. Combined compiler, contract, materializer,
  builder, frozen-fixture and runner tests: 66/66 passed.
- Broad `supervisor_harness` discovery: 456 run, 454 passed, 2 unrelated
  environment errors. The retired dual-E2B real-child test exited before its
  claim; the localhost marker-server test could not bind in this sandbox.
  Neither imports or executes the new runner. These were not modified.
- A separate read-only verifier rehashed every on-disk artifact, recomputed
  the manifest, materialization input and bundle hashes, checked all six URL
  hosts/methods and ceilings, all 34 unique vector denials, all 26 post-compile
  denials, and zero authorization claims: PASS.
- `git diff --check` for tracked files and no-index whitespace checks of the
  new sources showed no whitespace errors. No provider call, network request,
  fetched bytes, Dev/Final read, admission, release, commit or push occurred.

Synthetic receipt: `/private/tmp/gate1-executable-canary-20260921-01/`.
`canary-result.json` reports `passed=true`, 34/34 vector rejections, 26/26
post-compile denials, six planned and zero dispatched requests, zero cost and
zero fetched bytes. It is not production-path canary evidence: the compiler
remains unwired to the Controller adapter/outer runner and release manifest;
no real catalog commitment or executor exists. Release, provider sampling and
public fetching remain closed and require separate review and authorization.

## Integrated checkpoint update

The final integrated source at local HEAD `b9095a7` closes two additional
receipt-contract issues found by an independent reviewer. A direct call to the
receipt builder can no longer bind a changed request budget such as 999: it
rebuilds the exact request manifest from the original builder input and trusted
catalog commitment. It compares canonical JSON so integer/float and
boolean/integer substitutions cannot pass, then derives the contract only from
the trusted rebuild. The independent reviewer gave this narrow offline receipt
boundary PASS for builder SHA-256
`60117c1ea76bfec6bca818d31ae05699f01ebe412ffd1babd1363e8da085784e`.
The final synthetic receipt is
`/Users/estelle/Library/Application Support/MarketRSI/runs/p0-gate1-executable-plan-canary-20260921-03/`.
Focused combined tests passed 37/37; repository discovery ran 516 tests with
2 environment skips and no failures. The synthetic canary remains 34/34 attack
inputs and 26/26 post-compile tamper rejections, six planned requests and zero
dispatched requests, fetches, provider calls, or cost. This is still not a full
source freeze, production integration, real Train catalog admission, release,
or paid-run authorization.
