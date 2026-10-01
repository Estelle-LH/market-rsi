# Continuous Discovery minimal orchestrator implementation — 2026-09-29

## Scope and outcome

Implemented the bounded, zero-authority continuous Discovery state recorder in
the durable canonical repository.  The original snapshot received an
independent **REPLAN**; the three P1 boundaries were then repaired below.  The
current focused verdict is **PASS, pending fresh independent re-review**.

Owned files only:

- `continuous_discovery_batch.py`
- `test_continuous_discovery_batch.py`
- this dedicated log

No experiment runner or existing experiment source was changed.  No real
experiment ran.  No data was opened, scored or copied; no network, provider,
payment, protected Dev/Final, publication, promotion or execution authority was
used or granted.

## Observed problem and reused research record

The active opened-Train Discovery batch was recorded in a human-readable table,
but did not yet have one machine-enforced, crash-recoverable state transition
record for Controller selection through reviewed feedback.  This change affects
the orchestration component only.

Reused and confirmed applicable local policy:

- `research/market_rsi/AGENTS.md`, including the 2026-09-29 opened-Train
  Discovery override, preservation of failed branches, KEEP/REVERT separation,
  reused-Train-not-OOS labeling and the prohibition on silently crossing into
  protected or external actions.
- `supervisor_harness/DISCOVERY_BATCH_2026-09-29.md`, including batch start,
  deadline/max-attempt stop semantics and the definition that an execution
  claim consumes an attempt even when the run fails.
- The causal separation in the local `indicator-prediction-evals` skill was
  used only to keep orchestration evidence distinct from runner/scorer behavior.

No live literature search was performed.  This is an implementation of the
already-reviewed local persistence and authority boundary, not a new scientific
method or prediction claim.

## Implemented contract

`ContinuousDiscoveryBatch` stores an authoritative append-only, canonical JSON
hash-chain journal and an atomically replaced, self-hashed `batch.json`
snapshot.  The root must be absolute, local, non-cloud, non-temporary by
default, outside disposable Codex worktrees and free of symlink ancestry.
Tests may explicitly opt into a temporary root.

The state binds:

- batch ID, start, deadline and maximum actual execution attempts;
- fixed zero-authority boundary flags;
- a separate incumbent and append-only incumbent history;
- append-only exploratory branches;
- the exact ordered stages
  `controller_selected -> implementation_ready -> execution_claimed ->`
  `execution_terminal -> result_reviewed -> controller_feedback_ready`;
- Controller decision, runner, spec, execution receipt, scorecard and review
  hashes.

An execution claim appends exactly one event and increments the attempt count
exactly once.  Replaying the same claim ID is idempotent; a different claim ID
fails closed.  Failed and integrity/implementation-failed terminal outcomes
still consume the claim and increment the failure count.

Missing snapshots and valid prefix snapshots recover from the journal.  Invalid
JSON, noncanonical JSON, self-hash drift, journal gaps, altered hash chains or a
non-prefix snapshot fail closed.  Terminal branches are immutable; exact replay
returns the same state without another event.

Only `KEEP` after a successful execution with `independently_reviewed=true`
updates the incumbent.  `REVERT` and all failed/unreviewed branches remain in
history without changing it.  The final compact Controller packet contains only
IDs, status, exact evidence hashes, attempt counts, incumbent before/after
hashes and the explicit reused-opened-Train/zero-authority labels.  It contains
no raw rows, metrics, paths or data.

The module imports no runner, scorer, data library, network client, provider or
process launcher and exposes no run/execute/score/open-data/authorize/publish
method.

## Verification

Final focused command:

```text
PYTHONPYCACHEPREFIX=/private/tmp/market-rsi-discovery-pycache \
  python3 -m py_compile \
  supervisor_harness/continuous_discovery_batch.py \
  supervisor_harness/test_continuous_discovery_batch.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  supervisor_harness.test_continuous_discovery_batch
```

Result: **10/10 PASS** in 0.067 seconds.  Coverage includes:

- the complete six-stage chain and compact feedback packet;
- independent KEEP versus REVERT incumbent behavior;
- crash recovery from a valid stale snapshot and a missing snapshot;
- same-ID idempotent claim replay and different-ID double-claim rejection;
- failed attempt counting exactly once;
- deadline and maximum-attempt stops;
- terminal branch immutability and preservation into the next branch;
- fixed authority boundary flags;
- relative/cloud/temporary/symlink root rejection;
- snapshot and journal corruption rejection; and
- an AST/public-API capability scan.

The first run was 9/10: the wrong-claim behavior correctly failed closed and
left the journal unchanged, but the test expected a narrower error-message
substring.  Only that assertion was widened; the implementation did not change
for the failure.  The initial direct `py_compile` also could not write a pycache
inside the restricted durable repository, so the deterministic rerun placed
pycache under `/private/tmp`; source execution was unaffected.

Scoped whitespace checks passed.  Static text/AST inspection found no process,
socket, HTTP or data-analysis imports/calls in the implementation.

## Original implementation hashes before independent review

| File | SHA-256 |
|---|---|
| `continuous_discovery_batch.py` | `acddc79b08d223c16375ee4da3324128888d1f2e40ab6e2ed70fcaf57940ad5b` |
| `test_continuous_discovery_batch.py` | `49388666dca50f8be8dddfea9c7ac31249b03271a74f530a17f6647f4c8af8ae` |

The log's own SHA-256 is reported externally after its final bytes are frozen.

## Residual gates

This implementation is a recorder, not permission to execute.  The Supervisor
must independently review these exact bytes before integrating them.  Any
runner invocation remains subject to its existing source/spec/data/runtime and
authorization gates.  Protected Dev/Final, external acquisition, paid provider,
release, publication, deployment and promotion remain outside this batch.

## Independent REPLAN and bounded repair

The exact independent review log was read and bound before repair:

`AGENT_LOG_CONTINUOUS_DISCOVERY_MINIMAL_ORCHESTRATOR_REVIEW_2026-09-29.md`
SHA-256
`16cbfd9db8ca3a5b8597eba6a421105ae5da5d692a5b3ca2749531b0b14ec0e4`.

It reported zero P0 and three P1 findings: untrusted caller time/deadline and
nonmonotone timestamps; insufficient private file identity/TOCTOU controls; and
direct writes to the final journal sequence path.  The repair touched only the
owned module, focused tests and this log.  It did not read through the live
state API, mutate live state or run an experiment.

### P1-1 — trusted clock, deadline and monotone time

- Production actions now obtain UTC from the internal system clock.  A supplied
  `now` or injected clock is accepted only behind an explicit test-only seam;
  the injected clock additionally requires a temporary test root.
- Selection must be at/after batch start and before deadline; claims must be at
  or after selection and before deadline; terminal evidence must be at or after
  its claim; every new event time is nondecreasing; and a deadline-stop event
  cannot predate the deadline.
- New implementation-ready, review and feedback events store an event time.
  Legacy events without that optional field inherit the preceding valid time,
  preserving the existing event schema and replayed state.
- Proposed events are fully replay-validated before any durable journal path is
  created, so backdated or otherwise invalid calls cannot consume/poison the
  next sequence slot.

### P1-2 — private stable filesystem identities

- The durable root and journal must be owned by the effective user and not be
  group/world writable.  Existing ancestry and the opened root identity are
  bound and rechecked; root replacement fails.
- Lock, snapshot and journal entries are opened with `O_NOFOLLOW`, verified by
  descriptor as regular/private/single-link files, read through bounded loops,
  checked for mutation during the read, and compared with their directory-entry
  device/inode/mode/owner identity afterward.
- The lock pathname is checked against the locked descriptor before and after
  every protected operation.  Hard-linked lock, snapshot or journal files fail
  closed.
- Snapshot publication remains same-directory atomic replace plus file and
  directory fsync, followed by a descriptor-based verification read.

### P1-3 — atomic journal publication and crash recovery

- A journal event is first replay-validated, then fully written and fsynced to
  a private same-directory `.pending-<sequence>-<nonce>.tmp` file.
- `link` publishes the complete inode to the exclusive final sequence name;
  the journal directory is fsynced, the pending name is removed, and the
  directory is fsynced again.  The published bytes are reread securely.
- Recovery deletes only a safe single-link unpublished pending file.  If final
  publication won before interruption, recovery accepts only the exact
  two-name/same-inode pair, removes the pending name and preserves the complete
  final hash-chain entry.  Conflicting, hard-linked or newly appearing pending
  artifacts fail closed.
- Fault tests prove interruption before publication consumes zero claims, while
  interruption after link or during the first directory fsync produces exactly
  one complete claim that replays idempotently.

### Legacy live-state compatibility

The repair does not change `SCHEMA`, `EVENT_SCHEMA`, existing state fields or
the grammar of the five old event payloads.  A synthetic exact old-shape journal
with the sequence

`initialize -> controller_selected -> implementation_ready ->`
`execution_claimed -> execution_terminal`

replayed without migration as one consumed, successful attempt at
`execution_terminal`.  This specifically covers the structure of the existing
five-event live journal reported by the independent reviewer; the live files
themselves were not opened or modified during repair.

## Final repair verification

```text
PYTHONPYCACHEPREFIX=/private/tmp/market-rsi-discovery-repair-pycache \
  python3 -m py_compile \
  supervisor_harness/continuous_discovery_batch.py \
  supervisor_harness/test_continuous_discovery_batch.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  supervisor_harness.test_continuous_discovery_batch
```

Result: **16/16 PASS** in `0.144s`.

The six added regressions cover internal production clock/deadline enforcement,
event backdating, unsafe modes/hardlinks/root replacement/read races, pending
journal recovery, pre/post-publication plus directory-fsync interruption, and
legacy five-event replay.  The original ten lifecycle, count, incumbent,
corruption, path and zero-capability tests continue to pass.  `py_compile` and
scoped whitespace checks passed; static inspection still finds no runner,
scorer, data, process, socket, HTTP, provider or authority path.

## Current repaired hashes

| File | SHA-256 |
|---|---|
| `continuous_discovery_batch.py` | `4023bc712841fdc690c798f0b8404f4baf7f6238cd95ff6190faea3431b6a61f` |
| `test_continuous_discovery_batch.py` | `6eaf43b26712ccbf9e5fa5a436751615e979f2a0fb64e078d0716d520e55303a` |

The repaired log's own hash is reported externally after these final bytes are
frozen.  Fresh independent re-review of the repaired hashes remains mandatory
before this recorder is treated as accepted durable orchestration evidence.

## Fresh residual re-review and object-lifetime identity repair

The same independent review log was reread after its fresh residual review and
is bound here at SHA-256
`771febf73880601a53471c836efd838e1142c7f3311c55de02b3e63918e2ac0f`.
That review left one P1: a single `ContinuousDiscoveryBatch` object did not bind
the `journal/` directory or `.batch.lock` inode across separate operations, so
an exact private replacement could redirect later work or create a split lock.

The bounded repair adds object-lifetime device/inode/owner/mode bindings for
both root-relative objects at their first secure creation/open.  Every later
journal open and lock transition must match the pinned identity.  Journal
descriptors are also checked against both the pinned identity and the current
root-relative pathname before and after reads and appends; lock descriptors are
checked before acquisition, after acquisition and before release.  A replaced
directory or lock therefore fails closed before a subsequent operation can use
it.  A deliberate process restart may establish a new in-memory binding only
after the replacement journal independently passes its full canonical
hash-chain and snapshot replay checks.

Two focused test methods add three direct regressions: exact private journal
replacement is rejected by the existing object but remains replayable by an
explicit fresh object; exact private lock replacement is rejected; and a
journal swap after load but before append is rejected without publishing a new
event.  Existing legacy five-event replay and pending-crash recovery remain
covered.

```text
PYTHONPYCACHEPREFIX=/private/tmp/market-rsi-discovery-identity-pycache \
  python3 -m py_compile \
  supervisor_harness/continuous_discovery_batch.py \
  supervisor_harness/test_continuous_discovery_batch.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  supervisor_harness.test_continuous_discovery_batch
```

Result: **18/18 PASS** in `0.144s`; scoped `git diff --check` also passed.

No live state was opened or mutated, and no experiment, runner, data, network,
provider, scoring, publication or payment path was used or added.  This remains
a zero-authority recorder; fresh independent review of the hashes below remains
mandatory.

## Superseding exact hashes after residual repair

| File | SHA-256 |
|---|---|
| `continuous_discovery_batch.py` | `ee082f626e6af6319b032ddb6d6d55ad6daacd19a58fce8d1938ce674015e886` |
| `test_continuous_discovery_batch.py` | `9ce131f64625b54f2a73c2da55e64f8938d9f5ac97fb2ce32cb631dc39394dcb` |
