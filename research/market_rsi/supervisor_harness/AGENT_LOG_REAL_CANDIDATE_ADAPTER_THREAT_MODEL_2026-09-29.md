# Real candidate adapter threat model — 2026-09-29

- 2026-09-29 — Assigned to `real_candidate_adapter_threat_reviewer_20260929`.
  Scope is read-only inspection of the exact synthetic prediction protocol and
  existing local Docker containment code. The worker may edit only this log.
  All fixtures must be synthetic; no real outcome, Route-Dev, Audit-Dev or
  Final read, no Docker run, network, provider, training, evaluation, release
  or Git operation is allowed.

## 2026-09-29 10:49 EDT — independent threat-model result

### Scope and decision

Observed problem: the durable label-free protocol is already fail-closed, but
there is no process adapter that sends its one current public row to a local
Docker candidate and commits the returned probability before sending another
row.  The component under review is only that prediction transport boundary.
No target, scorer, data lifecycle, KEEP rule, candidate science or Docker
canary is changed.

This review reuses the repository's existing protocol and local-containment
research.  No live literature or network search was performed because this
assignment expressly prohibits network access and the operation is an
unchanged local isolation/IPC threat model, not a new statistical method.

**Decision: implementation may proceed, but only as synthetic, zero-provider
adapter development.**  It must use the interface and stop conditions below.
It must not reuse the historical E2B server or the historical writable-work
file channel as if either were current local-candidate isolation proof.  Unit
tests cannot set `real_isolation_admitted=true`; a separately authorized,
fresh, exact-source Docker canary and a later independent integrated review are
still required.

### 1. Minimal adapter interface

The smallest acceptable public entry point is conceptually:

```text
run_local_candidate_prediction(
    protocol_root,
    artifact_root,
    run_key,
    candidate_source,
    expected_candidate_sha256,
    public_rows,
    frozen_resource_limits,
) -> adapter_receipt
```

Inputs are limited to a frozen candidate source and the exact
`PUBLIC_AS_OF_FIELDS` rows already accepted by
`LabelFreePredictionProtocol`.  The adapter must not accept outcomes,
`outcome_available_ms`, Train labels, a Dev/Final identifier, scorer object,
scorer/evaluator path, protected-root path, provider credential, network
configuration or arbitrary environment additions.  The candidate interface
for this first adapter is exactly `predict(public_row) -> probability`; there
is no `fit` request and no full-sequence request.  Past rows may remain in the
candidate process's memory, but future rows are host-owned and unreleased.

The result is a host-authored receipt binding the candidate/source hash,
protocol run ID, prediction journal and completion receipt, exact container
command/config hash, process evidence and cleanup evidence.  It contains only
aggregate process facts and hashes, and must say:

```text
scored=false
real_data_admitted=false
real_isolation_admitted=false
promotion_authorized=false
```

The adapter returns no score and performs no lifecycle promotion.  A separate
trusted caller may extract verified prediction records only after successful
candidate termination and exact-container absence.

### 2. Ownership boundary

| Asset/action | Trusted host owns | Candidate may own/observe |
| --- | --- | --- |
| Candidate identity | source staging, byte hash, immutable mount, expected interface | read-only copy of its own source |
| Evaluation input | complete ordered public-row sequence | exactly one current released public row; past rows retained in its own memory |
| Hidden state | outcomes, future rows, scorer, Dev/Final lifecycle, protected paths | none |
| Protocol state | run claim, row release, journal, checkpoint, completion receipt and lock | no filesystem access; may only return one untrusted probability response |
| Process control | image digest, argv, mounts, environment, limits, deadlines, container identity, kill/reap/absence check | computation and ephemeral in-container state only |
| Durable output | exact response validation, fsync commit, process/cleanup receipt | stdout response is untrusted until host validation and durable commit |
| Scoring | loaded and run only after candidate and container are gone | never sees scorer source, input, output or path |

The trusted host must never import or execute candidate code.  Static
`candidate_integrity.py` can remain a control-plane filter, but it is not an
isolation boundary.  Its current `fit(train_rows, feature_names)` / two-argument
`predict` contract is also incompatible with this new minimal one-row
interface and must not be silently substituted.

### 3. Exact mount, environment and IPC contract

**Source staging.** Copy the fixed guest server and candidate bytes into a
fresh supervisor-owned staging directory using no-follow regular-file reads,
bounded sizes and exclusive creation.  Fsync and re-hash the staged bytes;
reject symlinks, directories, devices, FIFOs, source/hash changes and reused
staging roots.  Use controlled path names without Docker `--mount` delimiter
characters.  Candidate artifacts and receipts belong in the durable local
Market RSI tree, not iCloud or `/private/tmp`; unit-test scratch may remain
temporary.

**Docker argv.** Use direct argv, never a shell, with the already pinned image
digest and at least the following exact controls:

```text
docker run --rm --pull never --name <fresh-bounded-name> -i
  --label market-rsi-candidate=<fresh-id>
  --label market-rsi-task-id=<fresh-id>
  --network none --read-only --cap-drop ALL
  --security-opt no-new-privileges --ipc none
  --pids-limit 32 --memory 512m --cpus 1
  --user 65534:65534 --log-driver none
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m
  --mount type=bind,src=<staged-server>,dst=/opt/market-rsi/server.py,readonly
  --mount type=bind,src=<staged-candidate>,dst=/opt/market-rsi/candidate.py,readonly
  <pinned-image>
  /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8
  LC_ALL=C.UTF-8 HOME=/nonexistent PYTHONHASHSEED=0
  PYTHONDONTWRITEBYTECODE=1
  /usr/local/bin/python -I -B -u /opt/market-rsi/server.py
  /opt/market-rsi/candidate.py
```

There are exactly two read-only host bind mounts.  There is no writable host
bind, Docker socket, home, project, protocol, journal, data, key, evaluator or
artifact mount.  `/tmp` is an ephemeral bounded tmpfs.  The container receives
no `--env`, `--env-file`, published port, privileged mode, device, host PID/IPC
namespace or added capability.  The fixed guest validates Linux, UID/GID,
empty supplementary groups, no-new-privileges, minimal process environment and
the mounted source hashes before handling a row.  Guest self-report is
diagnostic only; host staging hashes and daemon config/cleanup evidence are
authoritative.

**IPC.** Use only attached stdin/stdout; do not reuse the writable `orders`,
`acks` and `events` bind mount.  Before candidate import/use, the host freezes
the command/source receipt.  For each row:

1. `release_next()` durably appends and checkpoints exactly one release.
2. Host writes exactly one bounded canonical-JSON `PUBLIC_RELEASE_FIELDS`
   object plus newline to candidate stdin.
3. Host reads exactly one bounded UTF-8 JSON line within the per-row and total
   deadlines. Duplicate JSON members, NaN/Infinity, invalid UTF-8, pre-output,
   a second line, trailing bytes and oversized stdout/stderr fail closed.
4. Response must contain exactly `PREDICTION_SUBMISSION_FIELDS`.  The host calls
   `commit_prediction`; it must return only after journal and checkpoint fsync.
5. Only then may the host call `release_next()` and write another request.

After the last durable commit, close stdin, require clean bounded process exit,
reap the exact Docker client, verify the exact labelled container ID is absent,
reject any ambiguous inspect/cleanup result, then and only then write protocol
completion.  Any timeout, crash, fsync uncertainty, extra output, descendant
process, container residue or cleanup ambiguity leaves the run incomplete and
unscored.  Cleanup must run in `finally`; stop only the exact ID whose expected
labels were independently inspected.  A used or dangling deterministic run ID
is never replayed.

`prediction_candidate_server.py` is historical E2B code and is not suitable
unchanged: it requires an E2B-style UID/network setup, accepts a full Train
`fit` payload and old feature schema, has an 8 MiB request surface, does not
enforce the new exact request schema, and is not connected to the durable
protocol.  `prediction_stream.LineChannel` is useful protocol precedent but
its process-group cleanup does not prove a Docker container and descendants
are absent.  `local_b_container.docker_command` remains valid for its old
synthetic directional canary, but its writable work mount, current-host UID,
file IPC and `{1,20}` order count are not the new adapter contract.

### 4. Attack matrix and mandatory synthetic tests

| ID | Severity | Attack/failure | Required fail-closed test |
| --- | --- | --- | --- |
| A01 | P0 | Outcome, label, future row, scorer/evaluator path or protected path reaches request | Inject each forbidden/alias/extra field before launch; assert no process creation or first write |
| A02 | P0 | Second row becomes visible before first prediction is durably committed | Block/inject commit and checkpoint fsync failure; spy on transport and prove exactly one request was written |
| A03 | P0 | Candidate can read journal, lifecycle, evaluator, home, credential or data files | Offline exact-mount/env assertion plus later fresh decoy canary; no admission from unit tests |
| A04 | P0 | Candidate gets network, Docker socket, host namespace, privilege or device | Assert exact Docker argv forbids them; later canary tests DNS/TCP/Unix socket and common secret paths |
| A05 | P0 | Candidate forges run/sequence/row, skips, duplicates or replays a prediction | Wrong/stale/future IDs, duplicate response, extra authority fields and response-before-request all fail without commit |
| A06 | P0 | Candidate mutates or truncates host prediction state | Prove protocol root is never mounted; mutate journal/checkpoint from host fixture and require integrity failure |
| A07 | P0 | Candidate source/server is swapped after approval | Reject symlink/FIFO/directory/oversize/hash mismatch; inject mutation between copy, hash and launch; compare staged and command-bound hashes |
| A08 | P0 | Scoring or outcome loading occurs while candidate/container may still live | Instrument call order; hung/forking candidate and ambiguous inspect must prevent completion, prediction extraction and scorer invocation |
| A09 | P0 | Timeout or host exception leaves a live candidate/descendant | Synthetic fake-process timeout/exception tests verify exact-ID cleanup, reap and terminal absence; foreign label/name is never killed |
| A10 | P0 | Candidate output grants isolation/data/promotion authority | Return `scored`, `real_isolation_admitted`, `real_data_admitted`, `promotion_authorized`; exact schema rejects it and host receipt remains false |
| A11 | P0 | Writable shared input permits future-row fabrication, symlink/path substitution or host artifact overwrite | Command must contain no writable host bind; regression asserts only the two source mounts and bounded tmpfs |
| A12 | P1 | Multiple/unsolicited JSON lines smuggle later predictions | Pre-output, two lines in one write, delayed extra line and trailing bytes fail; no next row is sent |
| A13 | P1 | Parser ambiguity from duplicate keys, NaN, Infinity, booleans, invalid UTF-8 or nesting | Byte-level parser fixtures reject all before protocol commit |
| A14 | P1 | stdout/stderr flood, no newline, slow drip, CPU/memory/PID/file exhaustion | Enforce byte, per-row, wall and Docker limits; kill/cleanup; no completion receipt |
| A15 | P1 | Candidate exits nonzero, closes stdin/stdout, or emits valid probability then hangs | Each variant leaves incomplete journal, is reaped/removed and cannot be scored |
| A16 | P1 | Replay after crash or released-but-uncommitted row | Resume must reject both resend and commit; fresh retry requires a fresh run key/ID |
| A17 | P1 | Probability is nonnumeric, out of epsilon range or identity-mismatched | Exercise bool/string/null/0/1/NaN/Infinity/out-of-range and wrong run/row/sequence; zero commits |
| A18 | P1 | Docker config drifts: unpinned image, pull, mount, env, user, capability or limit changes | Golden argv/config test rejects every single-field mutation and records exact config hash |
| A19 | P1 | Container-name collision or cleanup races with a foreign container | Preexisting name, wrong/missing label, ID change and inspect permission error all block launch/cleanup authority and score |
| A20 | P1 | Candidate or Docker writes durable logs outside the artifact policy | Require `--log-driver none`; bound/hash host stderr and protocol trace; assert no candidate-created durable host file |
| A21 | P1 | Candidate code relies on old `fit`/full-Train interface or gets full evaluation sequence | Reject fit/full-sequence messages and old server response schema; candidate observes one current row only |
| A22 | P1 | Host interruption occurs between final commit, process exit, cleanup and completion | Inject failure at every boundary; recovery may verify existing evidence but never rescore, replay or infer cleanup |

P0 means a possible hidden-data, future-row, trusted-state, process-boundary or
authority breach.  P1 means a fail-open integrity, replay, resource or evidence
defect that can invalidate a run.  The matrix is an implementation acceptance
list, not evidence that a not-yet-written adapter has passed it.

### 5. Existing evidence and current gaps

- `prediction_protocol.py` already has the correct closed public/response
  schemas, deterministic candidate/row binding, exclusive ownership,
  release/commit fsync ordering, restart replay denial, hash-chained journal,
  checkpoint readback and false isolation authority.
- The synthetic loop binds scorer rows back to the verified completed journal
  and frozen Dev commitment.  The new adapter must add the stronger process
  ordering: candidate gone and exact container absent before `finish` and any
  scorer access.
- The local Docker helper already demonstrates useful flags, pinned image and
  no-follow bounded file patterns.  Its existing command and containment
  canary are historical evidence only and deliberately insufficient for this
  new stdin/stdout candidate boundary.
- No P0/P1 defect was found in the frozen protocol within its stated trusted
  callback scope.  The absent adapter itself is the blocker; implementing it
  without A01-A22 would be a P0/P1 readiness failure.

### Synthetic tests run (no Docker)

- `test_minimal_prediction_protocol.py`: 18/18 passed.
- `test_prediction_stream.py`: 21/21 passed.
- `test_local_b_container.py` + `test_local_b_containment_canary.py`: 12/12
  passed with fake/offline processes only.
- `test_minimal_prediction_loop_integration.py`: 8/8 passed.
- An initial `unittest` module-path invocation produced two import errors while
  the 12 supervisor-harness tests ran; the two suites were rerun with the
  repository `PYTHONPATH` and passed as counted above.  This was a command
  invocation error, not a source-test failure.
- No Docker command, real data/outcome read, protected split, network/provider,
  training, empirical evaluation, release or Git mutation occurred.

### Exact project files inspected

- `research/market_rsi/AGENTS.md`
- `research/market_rsi/supervisor_harness/RESEARCH_STATE.md`
- `research/market_rsi/PREDICTION_FIRST_MINIMAL_LOOP_2026-09-29.md`
- `research/market_rsi/supervisor_harness/SUPERVISOR_REAL_INPUT_CONTAINMENT_2026-09-29-v1.json`
- `research/market_rsi/minimal_prediction_loop/prediction_protocol.py`
- `research/market_rsi/minimal_prediction_loop/loop.py`
- `research/market_rsi/prediction_stream.py`
- `research/market_rsi/prediction_candidate_server.py`
- `research/market_rsi/candidate_integrity.py`
- `research/market_rsi/supervisor_harness/local_b_container.py`
- `research/market_rsi/supervisor_harness/local_b_containment_canary.py`
- `research/market_rsi/supervisor_harness/local_b_containment_guest.py`
- `research/market_rsi/supervisor_harness/directional_guest_worker.py`
- `research/market_rsi/tests/test_minimal_prediction_protocol.py`
- `research/market_rsi/tests/test_minimal_prediction_loop_integration.py`
- `research/market_rsi/tests/test_prediction_stream.py`
- `research/market_rsi/tests/test_candidate_integrity.py`
- `research/market_rsi/supervisor_harness/test_local_b_container.py`
- `research/market_rsi/supervisor_harness/test_local_b_containment_canary.py`
