# Independent one-shot state review — synthetic adapter canary — 2026-09-29

Status: `PASS_FOR_IMPLEMENTATION_ONLY`

Reviewer: `synthetic_adapter_canary_oneshot_reviewer_20260929`

Authorized canary ID:
`market-rsi-real-candidate-isolation-canary-20260929-01`

Scope: independent read-only design review of one-shot ID consumption,
preflight/dispatch ordering, persistent local paths, replay and terminal
evidence for the exact v4 synthetic adapter.  This review did not run Docker,
create the authorized canary directory, consume the ID, open real or protected
data, call a provider, score, train, fetch, release or publish anything.

## 2026-09-29 — initial one-shot design result

### Verdict

`PASS_FOR_IMPLEMENTATION_ONLY` — **0 P0 and 0 P1 findings against the proposed
one-shot design below**, provided every requirement R01-R18 is implemented and
then receives a fresh independent prelaunch review on exact hashes.

This is not launch approval and is not a canary result.  The current v4 adapter
is a sound synthetic transport primitive, but it is deliberately not a durable
authorization-ID ledger.  The future fixed runner must supply that missing
outer state machine.  Using `run_local_candidate_prediction()` directly as the
authorized canary entry point would fail this review.

The design changes only launch/evidence orchestration.  It grants no real-data,
outcome, Train, Route-Dev, Audit-Dev, Final, provider, scoring, training,
empirical-evaluation, release or promotion authority.  Every adapter artifact
must continue to state `real_isolation_admitted=false` and all other authority
fields false.  A successful live canary plus independent review is evidence
only for this exact synthetic isolation path.

### Exact inspected snapshot

The six-file v4 aggregate was independently recomputed from the standard
`shasum -a 256` output, in the order shown:

```text
container_adapter.py                         34d4df25da4cea9807a39874cf04c0ed52af1c83f23d3851476a947f998590c9
container_candidate_guest.py                 d79d927d0ca3affda43639455c18b164c59014186092a2183fe765fcf4ac7b36
prediction_protocol.py                       eb6bdc1367f62c2910225218389d7381cebb2477e92a523c83f0693ae21a5dd3
local_b_container.py                         76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be
test_minimal_prediction_container_adapter.py 98cda5b55bad2b29e4fd6f139125ced9abc740a4500fe2e85770c185610dfc2d
test_minimal_prediction_protocol.py          9931c44f8d689386b3cb134965bcf704743226c02f587ae6aa7aa5a79e38197a
ordered aggregate                            87a32217bca2919e1a4724785ef578a6b7cda23b10bf99c56319017235e9472b
```

Other exact inspected evidence:

```text
AGENTS.md                                     4e0ac2d5a17f0c19e05582ccbb93482cb6db690b01fbf570689b6226360f39f0
REAL_CANDIDATE_ADAPTER_INTEGRATION            f59c5d541470b2c776c8a2ea30e38fb4518ed2543e09f6c7584d111df8c0d52a
adapter threat model                          3a60f92a1f39253702ec8bf2c7ce735fe33c4d8927a0a547b79f979c2f99b41b
adapter independent review                    b33146f3eb59909a1b83c314a0f1dfc9a0ef35482716d04afc13aeaf7180957b
one-shot supervisor plan                      5e7d293cfb4224b2bd87903a240594dc684bd44386ab7799263e1743d3e735e0
bottleneck_gate.py                            386f88f2f4d0e70ba19b01aa40b85289dfa27eec31d5c8ac2270600ee06dae0d
```

The plan passes `bottleneck_gate.py --phase dispatch` with six steps.  That
validates plan structure only; it does not prove the not-yet-written runner.

Frozen runtime commitments observed in the reviewed adapter:

- image:
  `python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`;
- Docker CLI SHA-256:
  `346b99a72cc44a7bdd91f6840aa46f14cdd9370b70eddcd7b0a48151fbfc060c`;
- exactly two read-only source mounts, no writable host mount, no network,
  read-only root, UID/GID 65534, dropped capabilities, no-new-privileges,
  disabled Docker logs and bounded tmpfs/process resources; and
- strict synthetic row/run-key gates and all-false external authority fields.

### Critical ordering observation

The adapter currently performs these operations in order:

1. validate synthetic inputs and persistent paths;
2. freeze/recheck Docker client, context and daemon identity;
3. create `artifact_root`;
4. stage sources and calculate the deterministic protocol run ID;
5. inspect the exact container name for freshness;
6. write `adapter-claim.json`;
7. create the deterministic protocol directory; and
8. construct `DockerJSONLTransport`, whose constructor calls `Popen`.

Several failures between steps 3 and 7 occur before the adapter's main
exception handler, and protocol creation occurs before `Popen`.  This is safe
for protocol replay, because partial directories remain and are not reused,
but it does not by itself define whether the separately authorized canary ID
was consumed.  The outer runner must therefore own a stricter, earlier and
unambiguous consumption point.

### Mandatory one-shot contract

#### R01 — one exact, argument-free production entry

The production runner must hard-code the authorized canary ID, a distinct
synthetic run key such as
`synthetic-market-rsi-real-candidate-isolation-canary-20260929-01`, exact
synthetic rows, candidate path/hash, v4 aggregate, image digest, Docker CLI
hash and persistent paths.  It must not accept an alternate ID, row set,
candidate, root, transport, Docker binding, retry flag or `allow_temporary`
through CLI arguments, environment variables or imported configuration.

#### R02 — fixed persistent non-cloud root

The sole attempt root must be exactly below:

```text
/Users/estelle/Library/Application Support/MarketRSI/synthetic-adapter-canaries/
```

The attempt directory name must be the exact authorized ID.  Its nested
adapter and protocol directories must stay under the same attempt root.  The
runner must reject symlinks, non-directories, unresolved parents, `/tmp`,
`/private/tmp`, `/var/folders`, iCloud/CloudStorage paths and any root outside
the resolved local `Application Support/MarketRSI` tree.  No important canary
artifact may be written to temporary or cloud-backed storage.

#### R03 — preflight is read-only with respect to the ID

All checks that can be performed without dispatch must finish before the
attempt root is created: exact source/test/manifest hashes, fixed synthetic
row validation, deterministic run/container identity, parent-path policy,
Docker CLI hash, Docker availability/context/daemon observation, pinned image
availability, and absence of the exact attempt directory.

Preflight may query Docker read-only.  It must not call `docker run`, create
the attempt/protocol/adapter directories, write an ID-scoped runtime artifact,
or mark the ID consumed.  A preflight failure therefore leaves the authorized
ID unconsumed.  A prelaunch manifest stored in the repository is not the
runtime attempt ledger and must be clearly labelled as non-consuming.

#### R04 — conservative, atomic consumption point

After every preflight passes and immediately before entering any code path
that can dispatch the candidate, the runner must atomically create the exact
attempt directory with exclusive semantics.  Directory creation itself is the
irreversible consumption event.  It must then write and fsync an immutable
canonical `launch-intent.json` and fsync the parent directory before calling
the adapter.

The intent must bind at least: canary ID, synthetic run key, deterministic run
ID and container name, candidate/guest/adapter/protocol/runner/test hashes,
ordered v4 aggregate, public-row hash/count, image digest, Docker CLI hash,
exact resolved attempt/adapter/protocol paths, all-false authority fields and
`test_mode=false`.

This point is deliberately earlier than `Popen`.  Once the directory exists,
an adapter preflight failure, Docker identity drift, host exception, interrupt,
power loss or uncertain process construction still consumes the ID.  This
conservatism is necessary to make “no retry after possible dispatch” provable.

#### R05 — root existence is the replay tombstone

Every later invocation must fail before Docker access if the exact attempt
directory already exists.  It must never infer “safe to retry” from a missing,
partial or corrupt intent.  The classifications are:

- no attempt directory: unconsumed;
- directory plus valid intent, no trusted terminal: consumed/unknown;
- directory plus terminal failure: consumed/failed;
- directory plus terminal success: consumed/succeeded; and
- directory plus both success and failure, or any corrupt state:
  consumed/failed-or-ambiguous.

The attempt directory and protocol/adapter children must never be deleted,
renamed away, repaired in place or reused to enable the same ID.

#### R06 — atomic concurrency exclusion

Two simultaneous processes must race only on the exact exclusive attempt
directory creation.  Exactly one may succeed.  The loser must stop without
Docker access.  A check-then-create sequence without exclusive creation is not
sufficient.

#### R07 — no test or dependency-injection path

The live call must use `run_local_candidate_prediction()` with
`allow_temporary=False` and default `transport_factory`, `control_run` and
`docker_binding`.  Success verification must call
`verify_adapter_terminal()` with its default `allow_test_mode=False`.  The
runner must additionally require `test_mode=false` in claim, receipt, success
marker and outer terminal evidence.  A copied or otherwise valid test-mode
fixture has no canary authority.

#### R08 — any post-consumption exception is terminal

The runner must wrap the adapter entry across ordinary exceptions and process
interrupts.  It should attempt to write one immutable, canonical, fsynced
`execution-failure.json` recording the error class and the presence/hashes of
available lower-level evidence, without secrets or traceback contents.  If
that write itself fails or the process is uncatchably terminated, the existing
attempt directory remains sufficient to classify the ID as consumed/unknown.
No exception handler may call the adapter again.

#### R09 — partial launch never authorizes replay

Failure before `Popen`, during `Popen`, after process creation, during pipe
setup, during protocol release/commit, after process exit, during cleanup,
after protocol completion, after adapter receipt, or after outer success must
all consume the same ID once R04 has occurred.  Recovery may inspect and
classify existing evidence; it may never dispatch another candidate process
under this ID.

#### R10 — Docker identity drift is failure, not a retry signal

The adapter must retain its v4 rule that one absolute hash-pinned CLI,
environment, context and daemon identity is frozen and rechecked through
run/inspect/stop.  The outer preflight observation must be recorded in the
launch intent or manifest.  If the identity changes before or during adapter
execution, the result is consumed failure/unknown.  It must not fall back to a
different context, daemon, CLI or same-ID retry.

#### R11 — cleanup uncertainty dominates

Outer success is impossible unless the adapter terminal verifier proves the
client process reaped with exit code zero and its cleanup record proves exact
container absence.  `unknown`, `foreign`, malformed inspect, daemon mismatch,
permission error, stop failure without final absence, or missing cleanup
evidence is terminal failure/unknown.  Neither runner nor reviewer may stop a
foreign container.  The later independent terminal reviewer must also perform
a fresh read-only absence check under a Docker binding whose public receipt
exactly matches the run receipt.

#### R12 — closed command/config evidence

Before outer success, the runner/verifier must require `claim.image == IMAGE`,
validate the exact Docker-client receipt schema and values, reconstruct
`docker_prediction_command()` from the trusted run ID/container name, staged
absolute paths and source hashes, and require the canonical command hash to
equal the claim and receipt.  This is required because the current v4
`verify_adapter_terminal()` cross-binds claim and receipt values but does not
itself compare `claim.image` to `IMAGE` or reconstruct the claimed command.

Omitting this check would be a **P1 launch-evidence finding**: a coherently
rewritten claim/receipt/marker chain could describe an image or command other
than the reviewed frozen runtime while passing the current terminal helper.
The runner may close this without changing the already-reviewed adapter by
using a separate strict canary-evidence verifier, but the requirement must be
covered by mutation tests and the independent prelaunch review.

#### R13 — missing/corrupt/coexisting evidence rejects

Outer success requires all of the following and exact cross-binding:

- valid immutable launch intent;
- no outer or adapter failure artifact;
- valid adapter claim, staged sources, receipt and success marker;
- exact deterministic protocol claim, journal, checkpoint and completion;
- exact source, row, run, command, image and Docker-client commitments;
- process reaped, exit zero, exact response count;
- exact owned container absent; and
- every authority boolean false.

Missing, noncanonical, partial, corrupt, hash-mismatched or coexisting success
and failure artifacts reject.  Failure/ambiguity always dominates success.
The runner must never manufacture a success from protocol completion alone.

#### R14 — immutable outer terminal records

After the adapter returns and strict verification passes, the runner may write
one immutable, canonical, fsynced `execution-success.json` bound to the launch
intent and complete adapter/protocol receipt hashes.  If this write or its
directory fsync reports failure, the ID remains consumed and cannot be called
successful by the runner.  The attempt uses append-only/write-once evidence;
there is no in-place mutable `status.json` whose last writer wins.

#### R15 — independent terminal review remains separate

The runner's success record is not the independent result.  A non-author must
recompute exact source and artifact hashes, run the strict terminal verifier,
resume the protocol read-only, validate the fixed synthetic rows and all-false
authority fields, compare a fresh Docker public binding with the receipt, and
inspect the exact container name for current absence.  Review failure leaves
the canary consumed and untrusted; it does not authorize replay.

#### R16 — synthetic-only content

The fixed candidate and rows may contain only synthetic identifiers and
synthetic filesystem/network decoys.  No real market/game data, outcome,
label, Train, Dev, Final, scorer, provider, credential or external fetch path
may be accepted or mounted.  No metric or empirical-performance claim is
permitted.  This preserves the indicator-evaluation causal ladder at the
transport/isolation boundary without opening prediction, objective or PnL
evaluation.

#### R17 — no implicit retry mechanisms

The production runner must contain no retry loop, retry library, recursive
re-entry, job resubmission, cleanup-and-recreate path, or automatic fallback.
The exact candidate process constructor may be reached at most once per
process, and R05 prevents another process from reaching it for the same ID.

#### R18 — exact snapshot rereview

After implementation, freeze hashes for runner, candidate, strict verifier,
adapter, guest, protocol, local container config and all focused tests.
Prelaunch review must rerun only offline/synthetic tests and return `PASS` with
0 P0 / 0 P1 before any Docker `run`.  Any byte change after that PASS requires
a new reviewed snapshot; it does not silently inherit this review.

### Required offline regression matrix

The implementation is not launch-ready until focused tests prove at least:

1. preflight failure leaves the attempt directory absent and ID unconsumed;
2. an existing attempt directory rejects before any Docker call;
3. two concurrent invocations yield exactly one exclusive claimant;
4. failure after directory creation but before intent completion is consumed;
5. failure after intent fsync but before adapter entry is consumed;
6. every adapter pre-dispatch failure is captured as consumed failure;
7. process-constructor/partial-launch failure cannot retry;
8. Docker CLI/context/daemon drift becomes consumed failure;
9. foreign, unknown and ambiguous cleanup cannot succeed;
10. missing/corrupt adapter receipt or marker cannot succeed;
11. outer success plus any failure artifact is rejected;
12. a persistent copied test-mode receipt is rejected;
13. temporary, cloud, symlink and alternate roots reject before consumption;
14. coherent mutation of image, command hash or Docker-client receipt rejects;
15. interruption at each write/fsync boundary never enables replay; and
16. success can reach the adapter process constructor exactly once and leaves
    all real-data/scoring/provider/training/promotion authority false.

### Attack disposition for this state review

| Attack | Initial one-shot disposition |
|---|---|
| Pre-launch artifact creation | CLOSED BY R03/R04: no ID-scoped runtime directory before all non-dispatch checks pass. |
| Same-ID replay | CLOSED BY R04-R06: exclusive root is an irreversible tombstone, including partial/corrupt state. |
| Partial launch | CLOSED BY R08/R09: possible dispatch consumes the ID; recovery inspects only. |
| Docker identity change | CLOSED BY R10: drift is failure/unknown and never fallback or retry. |
| Ambiguous cleanup | CLOSED BY R11/R15: exact absence twice, with matching binding, or no success. |
| Missing/corrupt terminal receipts | CLOSED BY R13/R14: exact closed chain required; ambiguity/failure dominates. |
| Test-mode acceptance | CLOSED BY R01/R07: fixed default production path and explicit false checks. |
| Image/command evidence rewrite | CLOSED ONLY IF R12 IS IMPLEMENTED; otherwise P1. |
| Cloud/temporary persistence | CLOSED BY R02 and path-policy regressions. |

### Next gate

Implement only the fixed synthetic candidate, strict canary-evidence verifier,
one-shot runner and offline tests above.  Do not run Docker.  Then append a
fresh independent prelaunch result to this log against exact hashes.  Only a
later `PASS` with 0 P0 / 0 P1 can make the plan's single live dispatch step
ready.  Regardless of outcome, this ID may never be reused after R04 occurs.
