# Independent synthetic local candidate adapter review — 2026-09-29

Status: `REPLAN`

Reviewer: `independent_real_candidate_adapter_reviewer_20260929`

Scope: read-only adversarial review of exact aggregate
`4aa3ff640c5c6773ff8400f1ef6699f04c04ca957d4bffde5863e2578a5625ba`.
Only this log may be edited by the reviewer.  Synthetic fixtures only; no live
Docker canary, real/protected data, provider, scoring, training, fetch, release
or Git publication.

## 2026-09-29 11:09 EDT — independent result

### Verdict

`REPLAN` — the exact snapshot has **2 P0 and 3 P1 findings**.  It therefore
does not meet the required `0 P0 / 0 P1` independent-review gate.  The current
code remains fail-closed with respect to scores, real-data admission and
promotion, and all receipts keep external authority false; however, the local
candidate lifecycle and evidence are not yet strong enough to request a live
Docker canary.

Even a later PASS would grant synthetic-adapter readiness only.  This review
does not grant live-isolation, real-data, protected-split, canary, provider,
training, scoring, release or promotion authority.

### Exact snapshot verification

I recomputed SHA-256 for the six files in the integration report, in the
reported order and with repository-relative paths.  The individual hashes
match the report and the aggregate of the standard `shasum -a 256` output is:

```text
4aa3ff640c5c6773ff8400f1ef6699f04c04ca957d4bffde5863e2578a5625ba
```

Tests rerun under the persistent local runtime, with synthetic fixtures only:

- focused plus adjacent suites: `75/75 PASS`;
- repository discovery: `516/516 PASS`, `2` designed skips;
- `git diff --check`: PASS.

No Docker container was started and no real/protected data was opened.

### Severity-ranked findings

#### P0-1 — run, inspect and cleanup do not bind one Docker CLI and daemon identity (A09/A18/A19)

`docker_prediction_command()` and `_inspect_container()` use the bare program
name `docker` (`container_adapter.py:218,240,269`).  The attached run gets a
new environment containing ambient `PATH`, `LANG` and `HOME` only
(`container_adapter.py:296-304`), while preflight, inspect and stop receive no
explicit environment (`container_adapter.py:245,269`) and therefore inherit
ambient `DOCKER_HOST`, `DOCKER_CONTEXT`, `PATH` and related client state.

Reproduction without starting Docker:

1. Put a synthetic `DOCKER_HOST` or `DOCKER_CONTEXT` in the host environment.
2. Observe that `_inspect_container(..., run=subprocess.run)` receives no
   `env=` and therefore uses that endpoint.
3. Observe that `DockerJSONLTransport` removes those variables before
   `docker run`, causing it to select the default endpoint instead.
4. On timeout, killing the attached client can leave the container running on
   the default endpoint, while cleanup inspects the other endpoint, sees the
   name absent and can set `exact_container_cleanup_verified=true`.

The current host resolves `docker` to `/opt/homebrew/bin/docker`, a symlink to
the Homebrew 27.1.1 client, but neither that absolute/real path nor a daemon
identity is frozen in the claim.  A changed or untrusted `PATH` can therefore
also substitute the control binary.  This is the exact live-process/cleanup
failure class designated P0 by A09.

Narrow repair: resolve an allowlisted absolute Docker CLI once, reject unsafe
or changed identity, build one exact host client environment/endpoint, and
pass both to every version/preflight/run/inspect/stop call.  Bind the CLI and
daemon/context identity in the claim and receipt.  Add a fake-control test
with conflicting ambient `PATH`, `DOCKER_HOST` and `DOCKER_CONTEXT` proving
that all calls use the same absolute executable and endpoint, and that an
endpoint mismatch can never produce verified cleanup.

#### P0-2 — process creation and abort are not failure-atomic or proven reaped (A09)

`DockerJSONLTransport.__init__` starts the process at lines 301-305 and only
then configures its pipes at lines 306-307.  If any pipe setup raises, the
constructor never returns, the caller's `transport` variable remains `None`,
and the outer exception path cannot kill or wait for that Docker client.
Container cleanup does not prove the client process was reaped.  Separately,
`abort()` swallows a five-second `wait()` timeout and sets `closed=true`
(`container_adapter.py:426-443`) without returning or recording reaping
evidence.

Narrow repair: wrap every post-`Popen` initialization step in a local
`try/finally` that kills the exact new process group, waits successfully and
closes pipes before re-raising.  Make `abort()` return structured evidence and
leave lifecycle state explicitly uncertain unless `poll()` proves reaping;
the outer cleanup record must preserve that uncertainty.  Add injected
`set_blocking` failure, wait-timeout, kill failure and descendant-process
tests.  A success receipt must remain impossible unless both the client is
reaped and the exact container is absent.

#### P1-1 — staged sources are not readable by the declared container UID (A07 availability)

`_copy_once()` creates both staged sources with mode `0400`
(`container_adapter.py:138-144`), while Docker is commanded to use
`65534:65534` (`container_adapter.py:224`).  A synthetic local probe of the
exact helper produced:

```text
mode=0400 uid=501 gid=20 container_uid=65534
owner_read=true group_read=false other_read=false
```

Under normal Linux bind-mount permission semantics, UID 65534 is neither the
owner nor a readable group/other identity, so Python cannot open the mounted
guest or candidate source.  The read-only mount protects mutation but does not
grant read permission.  Docker Desktop ownership virtualization is not a
substitute for a portable exact-mode assertion, and no live canary was allowed
to establish an exception.

Narrow repair: after exclusive write and fsync, explicitly `fchmod` staged
source descriptors to a frozen read-only mode usable by UID 65534 (normally
`0444`), then restat and reject any different mode/type/identity before
launch.  Add a regression that checks the final modes and a later separately
authorized live canary that proves UID/GID 65534 can read the two sources but
cannot write them.

#### P1-2 — delayed unsolicited stdout is not checked before the next release/write (A12)

`exchange()` returns immediately after one newline when the same read has no
trailing bytes (`container_adapter.py:371-376`).  It retains no cross-call
stdout buffer or quiet-boundary check.  After the durable commit, the adapter
calls `release_next()` before the next `exchange()` (`container_adapter.py:525-530`).
Bytes emitted just after the first read, including while commit fsync is in
progress, are therefore not checked before the next row is durably released;
depending on selector ordering, the next request can also be written before
the queued extra line is rejected.  The only transport regression emits two
lines in one immediate write; it does not exercise the A12 delayed-extra case.

Narrow repair: add an explicit bounded nonblocking `assert_quiet()` at the
post-commit/pre-release boundary, preserve any observed byte as a terminal
protocol violation, and never call `release_next()` after it.  Add a
controlled subprocess fixture that emits a valid first response, queues a
delayed duplicate during commit, and proves row 2 is neither released nor
written.  Identity binding should remain the fallback for bytes that race the
next request; the residual timing guarantee must be stated precisely rather
than claiming perfect silence for an unbounded future interval.

#### P1-3 — a post-completion receipt failure creates contradictory durable evidence (A22)

The protocol completion is durably written at line 541, but the adapter
receipt is not written until line 562.  If that final write/fsync fails, the
exception path writes `prediction_complete=false` unconditionally at line
578 even though `complete.json` already exists and is integrity-valid.  There
is no A22 failpoint/recovery test for interruption after final commit, process
exit, cleanup, protocol completion or adapter receipt.

Narrow repair: track each durable boundary explicitly.  On failure after
`protocol.finish()`, reopen/verify the immutable completion receipt and record
truthfully that protocol prediction is complete while adapter receipt
finalization failed; never replay, rescore or infer cleanup.  Add one failpoint
test at every A22 boundary and require mutually consistent recovery artifacts.

### A01-A22 disposition

| Attack | Review result |
|---|---|
| A01 | PASS: exact public-row schema rejects hidden/outcome/evaluator/path aliases before process creation. |
| A02 | PASS: host release/commit fsync order and injected commit failure prevent normal next-row exchange. |
| A03 | STATIC PASS ONLY: exactly two source mounts and an allowlisted guest environment; live decoy proof remains a separate canary gate. |
| A04 | STATIC PASS ONLY: no-network/read-only/cap-drop/NNP/no-host-namespace command is present; no live isolation claim. |
| A05 | PASS: run/row/sequence/schema/authority mismatches cannot commit. |
| A06 | PASS: protocol root is not mounted and journal/checkpoint mutation is rejected by adjacent tests. |
| A07 | REPLAN P1: source substitution checks exist, but staged files are unreadable by UID 65534. |
| A08 | PASS: no scorer is imported or called; process finish and cleanup precede protocol completion. |
| A09 | REPLAN P0: daemon/CLI identity can split and constructor/abort do not prove exact process reaping. |
| A10 | PASS: output cannot grant authority and host receipts keep every authority boolean false. |
| A11 | PASS: only two read-only file mounts plus bounded tmpfs; no writable host bind. |
| A12 | REPLAN P1: immediate multi-line output fails, but delayed queued output lacks a pre-release quiet check. |
| A13 | PASS: duplicate members, non-finite values, invalid UTF-8, nonobjects, booleans and endpoint probabilities fail closed. |
| A14 | PASS: per-row/total time and output/resource bounds are present; live exhaustion behavior remains canary work. |
| A15 | PASS BY LOGIC/PARTIAL TEST: EOF, timeout and nonzero exit block completion; add valid-then-hang coverage during repair. |
| A16 | PASS: deterministic replay and released-but-uncommitted restart are denied. |
| A17 | PASS: exact identity plus finite epsilon-bounded numeric probability is enforced. |
| A18 | REPLAN P0: argv is fixed, but Docker binary/endpoint identity is not. |
| A19 | REPLAN P0: foreign labels and ambiguous inspect fail, but mismatched daemon identity defeats the absence proof. |
| A20 | PASS: Docker logs are disabled, stderr is memory-bounded/hashed and no candidate-writable host path exists. |
| A21 | PASS: guest accepts one current public row and `predict(public_row)` only; old fit schema is rejected. |
| A22 | REPLAN P1: final-boundary recovery evidence is contradictory and not failpoint-tested. |

### Required rereview snapshot

Repair only the causal adapter/lifecycle boundary.  Preserve the frozen
prediction protocol, synthetic-only identity gate and all-false authority
fields.  Rerun the focused, adjacent and repository suites, publish new exact
source/test hashes, and request a fresh non-author review of that new
aggregate.  Do not run a Docker canary or open real data as part of this
repair.

## 2026-09-29 11:26 EDT — v2 independent rereview

### V2 verdict

`REPLAN` — the exact v2 aggregate has **0 P0 and 2 P1 findings**.  Four of the
five first-review causal defects are closed.  The A22 repair handles a failure
before receipt creation but not a failure after the success receipt becomes
visible, and the public entry point still permits unmarked test injection to
produce a success-shaped persistent receipt without running Docker.

This is a materially safer snapshot than v1: the two prior P0 lifecycle
findings are closed in synthetic/offline evidence.  It still does not meet the
required `0 P0 / 0 P1` gate, so no Docker canary should be requested on this
aggregate.

As before, even a later PASS grants synthetic-adapter readiness only.  It does
not grant live-isolation, real-data, protected-split, provider, training,
scoring, release, canary or promotion authority.

### V2 exact identity and tests

I independently recomputed every reported SHA-256 and the ordered aggregate:

```text
container_adapter.py                         661310716a8a275c293326c79848fa136874840eba15e4e16583f4c12ca7fbfc
container_candidate_guest.py                 d79d927d0ca3affda43639455c18b164c59014186092a2183fe765fcf4ac7b36
prediction_protocol.py                       eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3
local_b_container.py                         76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be
test_minimal_prediction_container_adapter.py 8f9c2ebc658824d1988758d578a2d26b91fefb8262a165a7de9ac5d96ccfdba9
test_minimal_prediction_protocol.py          9931c44f8d689386b3cb134965bcf704743226c02f587ae6aa7aa5a79e38197a
ordered aggregate                            5fcecc072eb518be7397d55d20b6a85094590637116b4244dd9f27fd24468ea1
```

The integration report independently hashes to
`69ed48a5f7829dd000d11da968c9398567fe2327617355c3d8d5cbb412ad6938`.

Synthetic-only verification rerun:

- adapter plus adjacent suites: `82/82 PASS`;
- repository discovery: `516/516 PASS`, `2` designed skips;
- scoped `git diff --check`: PASS;
- staged-mode probe: exact `0444`, other-readable, no owner write bit;
- actual pinned CLI bytes: SHA-256
  `346b99a72cc44a7bdd91f6840aa46f14cdd9370b70eddcd7b0a48151fbfc060c`.

No Docker container, real/protected data, provider, scorer, trainer, fetch,
release or Git mutation was used.

### Replay of the five v1 findings

1. **Docker CLI/environment/context/daemon binding — CLOSED.**  The resolved
   absolute executable is byte-hashed; one immutable environment is passed to
   context, info, run, inspect and stop; context/daemon identity is rechecked.
   Ambient conflicting Docker variables and a changed daemon fail closed.
2. **Post-Popen and abort lifecycle — CLOSED.**  Post-creation setup failure
   terminates and reaps locally before raising structured evidence.  Abort
   timeout/kill uncertainty remains `process_reaped=false` and cannot reach a
   success receipt.
3. **Staged source readability — CLOSED FOR STATIC READINESS.**  Exclusive
   staging now fsyncs, `fchmod(0444)`, restats, rehashes and remains mounted
   read-only.  Actual UID 65534 readability still belongs to the separately
   authorized live canary.
4. **Delayed stdout — CLOSED FOR THE DECLARED BOUNDED GUARANTEE.**  A
   post-commit/pre-release quiet check plus output-first readiness ordering
   blocks the controlled delayed duplicate before row 2 is released.  Row
   identity remains the fallback for an unavoidable later race.
5. **Post-completion receipt failure — PARTIALLY CLOSED, P1 REMAINS.**  The
   new recovery truthfully verifies protocol completion and replay denial when
   adapter-receipt creation fails, but it does not establish one canonical
   terminal result when receipt creation succeeds and a later durability step
   raises.

### V2 findings

#### P1-v2-1 — A22 can leave simultaneous success and failure terminal artifacts

The v2 regression replaces `_write_once(adapter-receipt.json)` with a function
that raises *before* invoking the real writer.  The harder durability boundary
is still open: `_write_once` writes and fsyncs the success receipt and then
fsyncs its parent directory.  If an error is reported after the file becomes
visible, the exception path writes `adapter-failure.json` while leaving the
complete, self-hashed `adapter-receipt.json` in place.  There is no canonical
adapter-result loader that makes failure/ambiguity dominate, so a later
consumer can select the success-shaped file and ignore the failure.

Exact synthetic reproduction used the current `AdapterFixture` and wrapped
the real `_write_once` so it completed the `adapter-receipt.json` write and
then raised.  The adapter raised fail-closed, but the artifact state was:

```text
receipt_exists=True
failure_exists=True
failure.adapter_receipt_present=True
failure.prediction_complete=True
```

Replay remains blocked, so this is not a P0 future-row or real-data breach.  It
is P1 terminal-evidence ambiguity under A22: the filesystem contains a valid
success document and a failure document with no machine-enforced precedence.

Narrow repair: add one canonical `verify_adapter_result(root)` path and require
every later canary/scorer consumer to use it.  It must verify the claim,
protocol completion, receipt self-hash, process/cleanup evidence and exact
authority booleans, and reject coexistence with any failure/ambiguity record.
An error after success-file creation must produce a durable ambiguity/failure
state that dominates the visible receipt.  Add post-write, file-fsync,
directory-fsync and post-return failpoints; test both `receipt only` recovery
and `receipt + failure` rejection.  Do not infer cleanup from protocol
completion alone.

#### P1-v2-2 — test injection can produce an unmarked success-shaped persistent receipt

`run_local_candidate_prediction()` correctly rejects an injected
`docker_binding` when `allow_temporary=false`, but it does not similarly reject
`transport_factory` or `control_run`, and neither `allow_temporary` nor test
injection is recorded in the claim/receipt.  A trusted caller can therefore
use the real frozen Docker binding and real preflight/cleanup while supplying
a fake transport that fabricates probabilities and process evidence without
starting the container.  With a persistent artifact root, the resulting
receipt is not distinguishable from the default runtime path by its schema.

This does not itself grant real isolation because every authority field stays
false, so it is P1 rather than P0.  It is nevertheless an A08/A18 evidence
integrity defect: a future live-canary consumer cannot prove from the receipt
that the non-test transport path ran.

Narrow repair: keep dependency injection behind an explicitly test-only
entry point, or reject all non-default `transport_factory`, `control_run` and
`docker_binding` values whenever `allow_temporary=false`.  Every
`allow_temporary=true` or injected run must bind `test_fixture=true` and
`live_canary_eligible=false` into claim, receipt and failure artifacts.  A
future canary verifier must require the persistent/default path and reject
those markers.  Add a regression proving a fake transport/control cannot
create a production-shaped persistent receipt.

### V2 A01-A22 disposition

| Attack | V2 result |
|---|---|
| A01 | PASS: closed public schema and synthetic identity gate remain unchanged. |
| A02 | PASS: durable commit still precedes the post-commit quiet check and any next release. |
| A03 | STATIC PASS ONLY: exactly two source mounts and no credential/data mount; live decoys remain canary work. |
| A04 | STATIC PASS ONLY: hardened Docker argv remains exact; no live isolation claim. |
| A05 | PASS: strict run/sequence/row/schema binding remains intact. |
| A06 | PASS: protocol state is not mounted and journal/checkpoint integrity tests pass. |
| A07 | PASS: exact 0444 mode, type, hash and source-mutation checks close the static defect. |
| A08 | REPLAN P1: default ordering is correct, but unmarked fake transport injection can fabricate process evidence. |
| A09 | PASS: client uncertainty is preserved and exact daemon-bound cleanup is required. |
| A10 | PASS: all output authority fields remain false and extra authority output is rejected. |
| A11 | PASS: two read-only source mounts only; no writable host bind. |
| A12 | PASS for bounded queued-output guarantee; delayed duplicate regression prevents row 2 release. |
| A13 | PASS: strict byte/parser and probability rules are unchanged. |
| A14 | PASS: byte/time/process/container resource bounds remain fail-closed. |
| A15 | PASS: timeout, EOF, nonzero exit and unreaped uncertainty cannot complete. |
| A16 | PASS: completion and released-pending replay remain rejected. |
| A17 | PASS: exact identity and finite epsilon-bounded numeric probability remain enforced. |
| A18 | REPLAN P1: real Docker identity is fixed, but the public entry point can substitute a fake transport without a test marker. |
| A19 | PASS: foreign identity, daemon drift and ambiguous inspect cannot verify cleanup. |
| A20 | PASS: no durable candidate log or writable host path is exposed. |
| A21 | PASS: one current row and `predict(public_row)` remain the only candidate interface. |
| A22 | REPLAN P1: visible success plus failure has no canonical machine-enforced terminal precedence. |

### Required v3 rereview snapshot

Repair only the two evidence-boundary defects above.  Preserve all v2 Docker
identity, lifecycle, staging, quiet-boundary, protocol and authority controls.
Rerun focused, adjacent and repository suites; publish a new exact aggregate;
then request a fresh non-author review.  Do not run Docker or open real data as
part of this repair.

## 2026-09-29 11:34 EDT — v3 independent rereview

### V3 verdict

`REPLAN` — the exact v3 aggregate has **0 P0 and 1 P1 finding**.

The v3 success marker closes success/failure coexistence for the artifacts it
actually verifies, and test-mode injection is now clearly marked and rejected
from the persistent/default path.  However, the canonical terminal verifier
does not verify the durable claim or protocol journal/completion that the
receipt purports to bind.  Mutating either one after a successful run leaves
`verify_adapter_terminal()` returning success.  That is a remaining A06/A22
evidence-chain defect, so the required `0 P0 / 0 P1` gate is not yet met.

No live Docker, real-data, protected-split, provider, training, scoring,
release, canary or promotion authority is granted.

### V3 exact identity and verification

The six individual hashes and ordered aggregate independently recomputed as:

```text
container_adapter.py                         9d237907ce27691df40d2c72e8a2b6d636f71e70c1db9e6ccd5cbe1c52713800
container_candidate_guest.py                 d79d927d0ca3affda43639455c18b164c59014186092a2183fe765fcf4ac7b36
prediction_protocol.py                       eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3
local_b_container.py                         76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be
test_minimal_prediction_container_adapter.py fa9f99d5bf00abc4100959db172dd31f253d24c0a72e6495379f393a1aa92b58
test_minimal_prediction_protocol.py          9931c44f8d689386b3cb134965bcf704743226c02f587ae6aa7aa5a79e38197a
ordered aggregate                            f880ab38ae5b7d66eaaacc157f63abb1ab047f2b3e02264f0150632ea316e720
```

The integration report independently hashes to
`74bc96926ff91bb0cbfdf5d7b5bde960fb094ce79ec3190833d8965535236134`.

Synthetic-only reruns:

- adapter plus adjacent suites: `84/84 PASS`;
- repository discovery: `516/516 PASS`, `2` designed skips;
- scoped `git diff --check`: PASS.

Additional adversarial probes confirmed:

- missing success marker rejects;
- noncanonical receipt rejects;
- mutated receipt rejects;
- mutated success marker rejects;
- failure coexistence dominates both a post-receipt-write and a
  post-success-marker-write exception;
- a test-mode receipt is rejected by the default verifier; and
- injected hooks with `allow_temporary=false` reject before artifact/process
  creation.

No Docker container or non-synthetic dataset was used.

### Replay of all prior findings

- **V1 P0 Docker binary/endpoint split:** CLOSED.
- **V1 P0 process initialization/abort reaping:** CLOSED.
- **V1 P1 staged 0400 unreadability:** CLOSED for static readiness with exact
  `0444`; live UID proof remains canary work.
- **V1 P1 delayed unsolicited output:** CLOSED for the declared bounded
  pre-release check.
- **V1 P1 post-completion truth/replay:** CLOSED for missing receipt and replay.
- **V2 P1 success/failure coexistence:** CLOSED at the receipt/marker terminal
  layer; any failure path dominates.
- **V2 P1 unmarked dependency injection:** CLOSED. `allow_temporary=true`
  yields `test_mode=true`; the default verifier rejects it, and any injected
  hook with `allow_temporary=false` is rejected before artifacts/processes.

The remaining issue is narrower: the terminal layer does not close over the
claim and protocol evidence below it.

### P1-v3-1 — terminal success does not verify the actual claim or protocol state

`verify_adapter_terminal(artifact_root)` reads only
`adapter-receipt.json` and `adapter-success.json` after checking that no
failure artifact exists.  It verifies receipt/marker canonical encoding,
self-hashes, process/cleanup booleans, authority booleans and test mode.  It
does **not** read `adapter-claim.json`, compare its fingerprint with
`receipt.claim_sha256`, validate the claim's candidate/guest/row/command/Docker
identity against the receipt, or reopen the label-free protocol to verify its
journal and completion receipt.  Its signature has no protocol root or frozen
row inputs with which to do the latter.

Exact synthetic reproduction on a valid v3 fixture:

1. Complete a successful test-mode adapter run and verify it once.
2. Change only `adapter-claim.json.expected_predictions` from `3` to `999`,
   preserving canonical JSON.  Leave receipt and success marker untouched.
3. `verify_adapter_terminal(..., allow_test_mode=true)` still returns success.
4. Change only the protocol run's `complete.json.predictions` to `999`, again
   leaving receipt and marker untouched.
5. The same terminal verifier still returns success.

Observed output:

```text
mutated_claim_accepted=True
mutated_protocol_completion_accepted=True
```

This is P1 rather than P0 because the candidate has no mount to those host
artifacts and all authority booleans remain false.  It nevertheless violates
A06 durable-state integrity and leaves A22 recovery evidence incomplete: the
canonical API intended for future consumers can accept a terminal whose
underlying claim or protocol evidence has changed.

Narrow repair:

1. Read `adapter-claim.json` canonically and require its exact field schema,
   `fingerprint(claim) == receipt.claim_sha256`, and equality of run,
   candidate, guest, rows, command, Docker client, test-mode and authority
   commitments with the receipt.
2. Extend the verifier with the protocol root plus the exact frozen
   `run_key`, candidate hash and public rows (or an equivalent trusted protocol
   verifier input).  Resume `LabelFreePredictionProtocol`, verify the complete
   journal/checkpoint/receipt, and require exact equality with
   `receipt.protocol_completion`.
3. Reverify staged source type, exact `0444` mode and hashes against the
   receipt/claim, so the terminal source evidence is closed too.
4. Add regressions for canonical claim mutation, completion mutation, journal
   truncation/extension, staged-source mode/hash mutation, and claim/receipt
   identity disagreement.  Each must fail through the one canonical terminal
   verifier.

### V3 A01-A22 disposition

| Attack | V3 result |
|---|---|
| A01 | PASS: public-row schema and synthetic identity remain closed. |
| A02 | PASS: durable commit and quiet check precede any next release. |
| A03 | STATIC PASS ONLY: only two source mounts; live decoys remain canary work. |
| A04 | STATIC PASS ONLY: pinned hardened Docker configuration; live proof remains separate. |
| A05 | PASS: response identity and authority injection remain rejected. |
| A06 | REPLAN P1: terminal verifier accepts mutated actual claim/protocol artifacts. |
| A07 | PASS at run time; add terminal staged-source revalidation to close durable evidence. |
| A08 | PASS: unmarked fake transport path is closed and process/cleanup order is enforced. |
| A09 | PASS: exact client/daemon and reaping uncertainty remain fail-closed. |
| A10 | PASS: receipt/marker authority fields are exact and false. |
| A11 | PASS: no writable host mount or shared input channel. |
| A12 | PASS for the bounded delayed-output guarantee. |
| A13 | PASS: strict canonical JSON and probability parsing remain intact. |
| A14 | PASS: byte, time and container resource limits remain bounded. |
| A15 | PASS: EOF, timeout, nonzero exit and unreaped process cannot complete. |
| A16 | PASS: run replay remains blocked after success or post-completion failure. |
| A17 | PASS: exact identity and finite epsilon-bounded probability remain enforced. |
| A18 | PASS: production default path has no unmarked injection bypass found. |
| A19 | PASS: foreign identity, changed daemon and ambiguous cleanup reject. |
| A20 | PASS: no candidate-writable durable host path or Docker log. |
| A21 | PASS: one-row `predict(public_row)` remains the only candidate interface. |
| A22 | REPLAN P1: receipt/marker terminal precedence is correct, but underlying claim/protocol evidence is not verified. |

### Required v4 rereview snapshot

Repair only the terminal evidence-chain closure described above.  Preserve all
v3 receipt/failure precedence, test-mode, Docker identity, lifecycle, staging,
quiet-boundary and authority controls.  Rerun synthetic-only focused,
adjacent and repository suites, publish a new exact aggregate, then request a
fresh non-author rereview.  Do not run Docker or open real data as part of the
repair.

## 2026-09-29 11:43 EDT — v4 independent rereview

### V4 verdict

`PASS` — the exact v4 aggregate has **0 P0 and 0 P1 findings** in this
synthetic-only independent rereview.  The v3 evidence-chain finding is closed:
the canonical terminal verifier now binds trusted inputs to the deterministic
run, canonical claim, staged sources, complete protocol journal/checkpoint and
completion receipt before accepting the success marker.

This PASS grants **synthetic adapter readiness only**.  It grants no live
Docker-isolation, real-data, protected-split, provider, scoring, training,
fetch, release, canary, promotion or Final authority.  No live Docker command
or non-synthetic dataset was used in this review.

### V4 exact identity

The six individual hashes and ordered `shasum -a 256` aggregate were
independently recomputed as:

```text
container_adapter.py                         34d4df25da4cea9807a39874cf04c0ed52af1c83f23d3851476a947f998590c9
container_candidate_guest.py                 d79d927d0ca3affda43639455c18b164c59014186092a2183fe765fcf4ac7b36
prediction_protocol.py                       eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3
local_b_container.py                         76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be
test_minimal_prediction_container_adapter.py 98cda5b55bad2b29e4fd6f139125ced9abc740a4500fe2e85770c185610dfc2d
test_minimal_prediction_protocol.py          9931c44f8d689386b3cb134965bcf704743226c02f587ae6aa7aa5a79e38197a
ordered aggregate                            87a32217bca2919e1a4724785ef578a6b7cda23b10bf99c56319017235e9472b
```

The integration report independently hashes to
`f59c5d541470b2c776c8a2ea30e38fb4518ed2543e09f6c7584d111df8c0d52a`.

### Synthetic verification and adversarial replay

- focused plus adjacent suites: `85/85 PASS`, including the focused adapter
  `26/26`;
- repository discovery: `516/516 PASS`, `2` designed skips;
- scoped `git diff --check`: PASS;
- source-only import inspection: no data reader, scorer, trainer, provider,
  credential loader or network client in the adapter/guest; the guest's
  `socket` use is limited to checking the isolated interface set; and
- additional terminal mutation matrix: `11/11` fail-closed.

The additional matrix started from a fresh successful synthetic receipt for
each case and independently mutated: claim `container_name`; protocol
`complete.json`; an appended journal record; checkpoint `journal_entries`;
guest mode; guest bytes with restored `0444`; candidate mode; candidate bytes
with restored `0444`; and each trusted verifier input (`run_key`, candidate
hash and public rows).  Every case was rejected by the canonical terminal
verifier.  The repository regression also covers claim
`expected_predictions`, completion mutation, journal truncation and combined
staged-candidate mutation.

The success path writes its receipt and marker while owning the protocol, then
leaves the `with protocol:` scope before calling `verify_adapter_terminal`.
The passing success tests therefore exercise a fresh protocol resume only
after lock release; the same nonblocking resume would reject a still-owned
lock.

### Replay of all prior findings

- **V1 P0 Docker binary/endpoint split:** CLOSED.  One resolved absolute
  executable hash, frozen environment, context and daemon identity are reused
  and revalidated for context/info/run/inspect/stop; conflicting ambient
  Docker variables do not replace the frozen binding.
- **V1 P0 process initialization/abort reaping:** CLOSED.  Post-`Popen`
  nonblocking setup failure and kill/wait uncertainty preserve explicit
  non-success evidence.
- **V1 P1 staged-source readability:** CLOSED for static readiness.  Both
  staged files are exact `0444`, hash checked and read-only mounted.  POSIX
  mode permits UID/GID 65534 reads; Docker Desktop bind behavior remains a
  live-canary availability check, not synthetic isolation evidence.
- **V1 P1 delayed unsolicited stdout:** CLOSED for the stated bounded
  pre-release guarantee.  The quiet check and output-first readiness ordering
  prevent a queued extra response from releasing/writing row 2; identity
  binding remains the race fallback.
- **V1 P1 post-completion truth/replay:** CLOSED.  Receipt failure after durable
  protocol completion records verified `prediction_complete=true`, and the
  deterministic completed run cannot replay.
- **V2 P1 success/failure coexistence:** CLOSED.  Any failure path dominates;
  missing, noncanonical or mutated receipt/marker rejects.
- **V2 P1 unmarked injection:** CLOSED.  `allow_temporary` or injected
  transport/control/Docker bindings produce `test_mode=true`, the default
  verifier rejects test mode, and injection with `allow_temporary=false`
  rejects before artifact or process creation.
- **V3 P1 incomplete terminal evidence:** CLOSED.  The verifier recomputes the
  run ID from exact trusted inputs, checks claim fingerprint and cross-fields,
  revalidates staged guest/candidate type, exact mode and hashes, resumes the
  exact protocol, verifies journal/checkpoint/completion and requires exact
  equality with the adapter receipt.

### V4 A01-A22 disposition

| Attack | V4 result |
|---|---|
| A01 | PASS: exact public-row schema and synthetic identities reject outcomes, labels, future/unknown fields and evaluator/credential/path aliases before process creation. |
| A02 | PASS: release/commit/checkpoint durability plus the quiet boundary precede every next-row release. |
| A03 | STATIC PASS ONLY: exactly two source-file mounts and an allowlisted guest environment; live decoy proof remains a separately authorized canary gate. |
| A04 | STATIC PASS ONLY: no network, read-only root, cap drop, no-new-privileges, private/default namespaces, bounded resources and no host/device/socket mount; live proof remains separate. |
| A05 | PASS: run/row/sequence/schema/authority mismatch, skip, duplicate and replay cannot commit. |
| A06 | PASS: protocol state is not mounted; terminal verification rejects claim, journal, checkpoint and completion mutation. |
| A07 | PASS: original and staged source type/mode/hash checks reject symlink, FIFO, substitution and mutation; terminal verification rechecks both staged sources. |
| A08 | PASS: no scorer/outcome loader is reachable; clean process exit and exact container absence precede protocol completion. |
| A09 | PASS: initialization, timeout and abort uncertainty remain non-success; cleanup acts only on exact owned identity and requires terminal absence. |
| A10 | PASS: candidate output cannot grant authority and every claim/receipt/marker authority field is exact and false. |
| A11 | PASS: the command has only two read-only file binds and bounded tmpfs, with no candidate-writable host channel. |
| A12 | PASS for the bounded delayed/multiple/trailing-output guarantee; no row is released across an observed queued extra response. |
| A13 | PASS: duplicate members, non-finite numbers, booleans, invalid UTF-8, nesting/nonobjects and endpoint probabilities reject. |
| A14 | PASS: request/response/stderr, row/total time, pids, memory, CPU and tmpfs are bounded; failure cannot complete. |
| A15 | PASS: EOF, valid-then-hang, nonzero exit, early exit and unreaped process cannot produce completion. |
| A16 | PASS: deterministic replay and released-but-uncommitted restart remain fail-closed. |
| A17 | PASS: exact response identity and finite epsilon-bounded probability are enforced before commit. |
| A18 | PASS: image/argv are frozen and the production path uses one hash-pinned absolute Docker CLI and one frozen environment/daemon binding; no unmarked injection bypass was found. |
| A19 | PASS: foreign/missing labels, name collision, changed daemon/ID and ambiguous inspect/cleanup reject. |
| A20 | PASS: Docker logging is disabled, host stderr is bounded/hashed, and no candidate-writable durable host path exists. |
| A21 | PASS: only one current public row reaches `predict(public_row)`; no fit/full-sequence or old response surface is accepted. |
| A22 | PASS: final-boundary failures preserve protocol truth without replay; failure dominance and the closed claim/staging/protocol/receipt/marker chain are machine-verified. |

### Residual gate boundary

The exact v4 snapshot is ready for the supervisor's synthetic adapter gate.
It is not evidence that UID 65534 can read these mounts through the actual
Docker Desktop backend, that live network/credential/data decoys are denied,
or that real inputs are admissible.  Those facts require a separately
authorized fresh live-isolation canary and its own independent review.  No
release, canary or real-data action was performed here.
