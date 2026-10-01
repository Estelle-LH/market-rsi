# Continuous Discovery minimal orchestrator independent review — 2026-09-29

Review timestamp: `2026-09-29T14:30:19-04:00`.

Original verdict on the `acddc79...` source: **REPLAN**, P0 **0**, P1 **3**.
Fresh repair verdict on the `4023bc...` source: **REPLAN**, P0 **0**, P1 **1**.
Final inode-repair verdict on the `ee082f...` source: **PASS**, P0 **0**, P1 **0**.

The state machine, count semantics, branch/incumbent separation and explicit
zero-capability boundary are sound in the reviewed happy path, but the current
bytes are not ready to serve as the durable continuous-Discovery authority.
The journal publication, clock/deadline boundary and filesystem identity
boundary each have a deterministic fail-closed or bypass problem described
below.

## Exact review inputs

All three assigned inputs matched their expected SHA-256 exactly before review:

| Input | SHA-256 |
|---|---|
| `continuous_discovery_batch.py` | `acddc79b08d223c16375ee4da3324128888d1f2e40ab6e2ed70fcaf57940ad5b` |
| `test_continuous_discovery_batch.py` | `49388666dca50f8be8dddfea9c7ac31249b03271a74f530a17f6647f4c8af8ae` |
| `AGENT_LOG_CONTINUOUS_DISCOVERY_MINIMAL_ORCHESTRATOR_2026-09-29.md` | `e9abddfb1d4c925580588936dd0bf6cf335d54d4e29dabb7ab419f894faaf328` |

I read the repository `AGENTS.md`, current compact `RESEARCH_STATE.md`,
`RESEARCH_SUPERVISOR.md`, the batch policy, the full module/tests and the
implementation receipt.  I did not change either reviewed source file.

## Findings

### P1 — the live deadline is controlled by an untrusted caller timestamp

`select_controller_candidate`, `claim_execution` and `stop_if_due` accept a
caller-provided `now`; `_assert_live_batch` compares only that supplied value
with the stored deadline (`continuous_discovery_batch.py:641-647,722-745,
748-788,814-848`).  The replay validator also canonicalizes timestamps but
does not require selection to be at/after batch start or claim/terminal times
to be monotone with the preceding event.

Deterministic reproduction under the pinned runtime:

- with actual UTC later than a synthetic `18:13:21Z` deadline, a selection
  supplying `18:12:21Z` was accepted;
- a selection at `18:12:21Z`, claim at `18:04:21Z`, and successful terminal at
  `18:03:21Z` were all accepted into one branch.

Therefore the stored deadline and event chronology are not machine-enforced;
an integrating caller can backdate a claim.  Repair should use a trusted
internal UTC clock in production (with an explicit test-only clock seam) and
replay-time chronological checks: start <= selection <= claim <= terminal,
and a deadline stop time at/after the deadline.  Add backdating and reordered
timestamp adversarial tests.

### P1 — path checks do not establish stable, private file identities

`_safe_root` rejects visible symlink ancestry but does not require stable
ancestor/root device+inode+mode+owner identities or private modes
(`continuous_discovery_batch.py:137-168`).  `_read_records` and
`_read_snapshot` use pathname check/stat/read sequences rather than bounded
`O_NOFOLLOW` descriptor reads with fd/name identity and `st_nlink == 1`
checks (`:235-275,569-585`).  The lock checks its opened fd type/link count,
but does not cross-check the pathname identity after locking (`:217-233`).

Deterministic reproductions under a temporary test root:

- an existing root explicitly changed to mode `0777` initialized and replayed
  successfully;
- after hard-linking `journal/00000001.json`, the entry had `st_nlink == 2`
  and `snapshot()` still accepted it.

This makes the claimed private append-only evidence vulnerable to aliasing and
pathname replacement races.  Repair should bind stable directory identities,
require the effective user and non-group/world-writable modes for the durable
root/journal, use directory-relative `O_NOFOLLOW` opens and bounded looped
reads, require regular single-link files, and compare fd/name identity before
and after every read/write/lock operation.  Add mode, hard-link, ancestor/root
replacement and read-race adversarial tests.

### P1 — a journal record is not atomically published

`_append_record` creates the final numbered path with `O_EXCL`, then writes and
fsyncs that same pathname (`continuous_discovery_batch.py:277-310`).  A crash
after final-name creation but before the full canonical record is durable
leaves a sequence entry that replay can neither accept nor reconstruct.

I simulated that exact post-create crash boundary by placing a one-byte
`00000002.json` after a valid initialization.  Every subsequent `snapshot()`
failed with `DiscoveryBatchError: batch journal entry is not JSON`.  This is
fail-closed, but it is not the crash recovery claimed by the component and
leaves it impossible to determine or safely retry whether an execution claim
was consumed.

Publish each journal event through a private same-directory temporary file:
write the complete canonical record, fsync it, atomically link/rename it to the
exclusive final sequence name, then fsync the journal directory.  Orphan
temporary files can be ignored safely because they were never authoritative.
Add fault injection at create/write/fsync/publish/directory-fsync boundaries
and prove exact claim/count behavior after restart.

## Passing properties

- **Hash/journal grammar:** closed event fields, canonical JSON, exact sequence,
  previous-head linkage and per-record digest replay are enforced.  Snapshot
  self-hash drift, journal gaps and non-prefix divergence reject.
- **Snapshot atomicity:** snapshot content is written to a same-directory
  temporary file, file-fsynced, replaced and directory-fsynced.  A missing or
  valid-prefix snapshot rebuilds from a complete journal.
- **Idempotency:** exact repeated selection/readiness/claim/terminal/review/
  feedback calls do not append a second event; conflicting IDs or hashes
  reject.  A failed execution increments `failed_attempts` once.
- **Count and branches:** the attempt count increments only at the single
  execution claim; failed outcomes consume that count; only one branch is
  active; completed branches remain in history; new selection binds the then
  current incumbent.
- **Incumbent:** only a successful execution with `KEEP` and
  `independently_reviewed is True` replaces the incumbent.  `REVERT`, failure
  and unreviewed KEEP do not.  Incumbent history remains separate from branch
  history.
- **Evidence binding:** the authoritative branch/journal binds Controller
  decision, parent incumbent, runner, spec, claim, execution receipt,
  scorecard and review hashes.  The compact feedback packet binds the main
  execution/result hashes and incumbent before/after.  It is not a standalone
  verifier and should continue to be consumed with the journal/snapshot; it
  does not validate the contents behind caller-supplied hashes.
- **Capability boundary:** static source/AST inspection found no subprocess,
  shell, socket, HTTP client, provider, credential, data-reader, scorer,
  evaluator, publication, promotion or runner invocation.  Public methods
  only mutate/replay this recorder's local metadata.  The fixed flags keep
  network/provider/Dev/Final/publication/promotion and external authority
  false.  No external action occurred during this review.

## Test replay and added read-only adversarial probes

Pinned runtime:
`/Users/estelle/.cache/market-rsi/runtimes/ds-py312-20260912-01/bin/python`.

Focused replay:

```text
PYTHONDONTWRITEBYTECODE=1 <pinned-python> -m unittest -v \
  supervisor_harness.test_continuous_discovery_batch
```

Result: **10/10 PASS** in `0.054s`.

Additional probes used only temporary roots and made no repository or live
state writes.  They reproduced: mode-0777 root acceptance, hard-linked journal
acceptance, nonmonotone event-time acceptance, backdated-deadline acceptance,
and the unrecoverable partial-final-journal condition.

## Live state: read-only verification

Inspected without calling the mutating/recovery `snapshot()` API:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/continuous-discovery-batch-20260929-01`

The root and journal were mode `0700`; lock, snapshot and all five journal
files were mode `0600`, owned by uid `501`, and the files each had one link.
All files were read only.  Exact byte hashes were:

| Live file | SHA-256 |
|---|---|
| `batch.json` | `a4b7d080c3f287e8aabfe8f091d10226ddd51773bb5771f302955df327529906` |
| `journal/00000001.json` | `b0f58561a98b34617f79466e0ce7c78a58c042e89388cdb69cd57338b74c19a2` |
| `journal/00000002.json` | `b1b4484913288a18ed9dc3dfef3d2d98d64eeb7a0cc545d8e85359d313f1a709` |
| `journal/00000003.json` | `9f5ea84a00fb696327ded19dad0b191d08e4a5ce426d52efb07e9ae646e7fffc` |
| `journal/00000004.json` | `be54664a86a97d2f4d486a5272f7a86c5072826f37fa8550ebf8a10cce7c9211` |
| `journal/00000005.json` | `22265d45a276e65ae525f648feed1655c17ac4e1825092ee72503139716beb41` |

Independent in-memory replay verified the exact event sequence:

```text
initialize -> controller_selected -> implementation_ready ->
execution_claimed -> execution_terminal
```

The complete hash chain head is
`139bf53df41c2e503b6c635d357a62ad3396ea8135da6525df57a4087f0b3921`.
Replayed state equals `batch.json` exactly and has state SHA-256
`75e94a57cbe9bc3e7c509456cf0b2224836566286da1e3e8d61dc17493550716`.
It represents exactly one consumed execution claim (`attempts_claimed == 1`),
one branch at `execution_terminal`, outcome `succeeded`, zero failed attempts,
and no review/feedback/incumbent change yet.  This confirms the requested live
fact; it does not cure the three source-level P1 findings.

## Required re-review boundary

Repair only the three failed boundaries, add their deterministic regression
tests, then freeze new module/test hashes and rerun this focused review.  Do
not mutate or reconstruct the existing live journal as part of that repair.
No experiment, runner, scorer, data, provider, network or authority action is
needed for re-review.

---

## Fresh independent repair re-review — 2026-09-29

Re-review timestamp: `2026-09-29T14:46:09-04:00`.

Verdict: **REPLAN**.  P0 findings: **0**.  P1 findings: **1**.

The trusted-clock/monotonic-time repair and atomic journal publication repair
pass.  The private-filesystem repair closes file hard links, unsafe modes,
descriptor reads and root replacement, but does not preserve the identity of
the journal directory or lock file across the protected operation boundary.
That residual redirection/lock-splitting issue keeps the component from PASS.

### Exact repaired inputs

All assigned hashes matched before testing and remained unchanged afterward:

| Input | SHA-256 |
|---|---|
| `continuous_discovery_batch.py` | `4023bc712841fdc690c798f0b8404f4baf7f6238cd95ff6190faea3431b6a61f` |
| `test_continuous_discovery_batch.py` | `6eaf43b26712ccbf9e5fa5a436751615e979f2a0fb64e078d0716d520e55303a` |
| updated implementation log | `750aa58284efd62bf936b9559bd555ae7cc9ebc300bd8b47eea7c4bd6e7c5d97` |
| prior independent REPLAN log | `16cbfd9db8ca3a5b8597eba6a421105ae5da5d692a5b3ca2749531b0b14ec0e4` |

### Closed finding — trusted production time and monotonic replay

Production actions now reject caller-supplied time and use internal UTC.
Clock injection requires both explicit test-only enablement and a temporary
root.  Selection and claims enforce start/deadline; claim and terminal times
cannot predate their predecessors; optional event times on the other modern
events make the complete new sequence nondecreasing.  `_append_record`
replays the candidate transition before creating durable state, so a rejected
backdated event does not consume its sequence or attempt.

The focused tests cover a genuinely expired production batch, caller backdate
rejection, an unapproved injected clock, and backward implementation/claim/
terminal timestamps.  Source inspection confirms public production calls do
not use the caller value unless the temporary test seam was established in the
constructor.  Legacy events without the newly optional event-time member
inherit the prior time and remain replayable.

### Closed finding — atomic journal publication and crash recovery

Each proposed event is fully replayed first, then written completely to a
private pending inode, file-fsynced, atomically hard-linked to the exclusive
final sequence name, directory-fsynced, unlinked from its pending name and
directory-fsynced again.  Recovery distinguishes an unpublished one-link
pending inode from the exact two-link pending/final publication pair and
rejects aliases/conflicts.  The final entry is descriptor-reread and compared
with the bytes proposed.

Fault tests cover interruption before publication, immediately after final
link creation and at the first directory fsync.  Restart observes either zero
or one complete claim, and exact replay remains idempotent.  The original
partial-final-file crash is no longer producible by this writer.

### P1 — journal and lock identities can still be replaced between opens

The object pins ancestor and root identity, and each individual regular-file
read verifies `O_NOFOLLOW`, effective-user ownership, private mode, single
link, stable fd metadata and fd/name identity.  However:

- `_open_journal` verifies the currently opened directory against its current
  name but does not retain/compare a journal-directory identity on subsequent
  opens;
- `_locked` verifies the lock fd against `.batch.lock` before and after one
  yielded operation, but does not retain/compare that lock inode across
  operations; and
- load and append open `journal/` separately, so a replacement can occur
  after records are loaded and before the next event is published.

Two deterministic temporary-root probes reproduced the gap:

1. rename `journal/`, copy its exact private single-link contents into a new
   mode-0700 `journal/`, then call `snapshot()` on the same object: accepted;
2. rename `.batch.lock`, create a different mode-0600 single-link regular lock,
   then call `snapshot()` on the same object: accepted.

An exact copy makes the content hashes pass, but the missing stable identity
allows journal redirection and a second lock inode.  A racing same-euid process
can therefore split serialization or switch the append target between the
load and commit phases.  Detecting only the root identity and the currently
opened pathname is insufficient for the TOCTOU property claimed by the repair.

Repair by pinning the journal-directory and lock-file dev/inode/uid/mode
identities on first creation/open and requiring the same identities at every
later open for that batch object.  More strongly, retain the root, journal and
lock descriptors for the complete locked load/validate/append/snapshot
transaction, and recheck their named identities before and after mutation.
Add exact journal-directory replacement, lock replacement, and a swap between
`_read_records` and `_append_record` tests.  A deliberate process restart can
establish a fresh in-memory identity only after verifying the existing chain;
within one process/transaction, replacement must fail closed.

### Focused replay and legacy live-state result

Pinned runtime:
`/Users/estelle/.cache/market-rsi/runtimes/ds-py312-20260912-01/bin/python`.

```text
PYTHONDONTWRITEBYTECODE=1 <pinned-python> -m unittest -v \
  supervisor_harness.test_continuous_discovery_batch
```

Result: **16/16 PASS** in `0.164s`.  The suite verifies all six repair tests
plus the original lifecycle, count, idempotency, incumbent, branch, corruption
and zero-capability tests.  The missing cross-open journal/lock identity attack
is not in those 16 tests.

The live state root was read only; neither `snapshot()` nor pending recovery
was invoked.  Its file hashes and modes remain exactly those recorded in the
original review: five single-link mode-0600 journal records under mode-0700
root/journal, snapshot SHA-256
`a4b7d080c3f287e8aabfe8f091d10226ddd51773bb5771f302955df327529906`,
head `139bf53df41c2e503b6c635d357a62ad3396ea8135da6525df57a4087f0b3921`
and state hash
`75e94a57cbe9bc3e7c509456cf0b2224836566286da1e3e8d61dc17493550716`.

Independent raw-byte/hash-chain validation followed by the repaired module's
pure in-memory `_replay` produced exactly:

```text
initialize -> controller_selected -> implementation_ready ->
execution_claimed -> execution_terminal
```

The replay equals the existing snapshot byte-for-object, with one claimed
attempt, zero failed attempts, `execution_terminal`, `succeeded`, and no
review/feedback/incumbent change.  Legacy compatibility therefore passes.

Static source/AST inspection and the focused capability test still confirm no
runner, scorer, data reader, process launcher, socket/HTTP client, provider,
credential, publication, promotion or external-authority path.  No experiment,
data, network, provider, state mutation, release or Git action occurred.

---

## Final residual-inode repair re-review — 2026-09-29

Re-review timestamp: `2026-09-29T14:52:54-04:00`.

Verdict: **PASS**.  P0 findings: **0**.  P1 findings: **0**.

Exact reviewed inputs matched the assignment:

| Input | SHA-256 |
|---|---|
| `continuous_discovery_batch.py` | `ee082f626e6af6319b032ddb6d6d55ad6daacd19a58fce8d1938ce674015e886` |
| `test_continuous_discovery_batch.py` | `9ce131f64625b54f2a73c2da55e64f8938d9f5ac97fb2ce32cb631dc39394dcb` |
| updated implementation log | `07227b04ee01bb6467606174000b38ba466f993c23f71c7c93bd5ff85640f42e` |
| prior review log before this section | `771febf73880601a53471c836efd838e1142c7f3311c55de02b3e63918e2ac0f` |

The residual filesystem P1 is closed.  The batch object now pins exact
`dev+ino+uid+mode` identities for the root, journal directory and lock file.
Every later journal/lock open must match the pinned identity.  The lock is
verified before flock, after flock and again before release.  Journal reads
verify the directory before and after the complete read; appends verify it
before publication and after final-byte verification.  Each named regular file
continues to require effective-user ownership, private mode, one link,
`O_NOFOLLOW`, stable fd metadata and matching fd/name identity.

The two new regressions reproduce the former attacks and now reject them:

- replacement of `journal/` or `.batch.lock` is rejected by the same object;
- a journal swap after `_read_records` but before `_append_record` rejects
  without appending an event or consuming an attempt.

A deliberately restarted object may establish new in-memory identities only
after reading the existing private canonical hash chain; this preserves normal
process restart while closing replacement within an object's transactions.

The earlier repairs remain intact: production time is internal and caller time
is test-only/temporary-root-only; event chronology and deadline checks are
monotone and prevalidated; journal publication remains complete-file fsync plus
exclusive hard-link, directory fsync and safe pending recovery.  Count,
idempotency, incumbent, branch and evidence-binding behavior did not regress.

Focused pinned-runtime command:

```text
PYTHONDONTWRITEBYTECODE=1 <pinned-python> -m unittest -v \
  supervisor_harness.test_continuous_discovery_batch
```

Result: **18/18 PASS** in `0.155s`.

The live state was read only with raw file reads and pure in-memory replay; the
state API and pending recovery were not called.  It remains the unchanged exact
five-event legacy chain
`initialize -> controller_selected -> implementation_ready -> execution_claimed
-> execution_terminal`, one claimed attempt, zero failed attempts, outcome
`succeeded`, and no review/feedback/incumbent change.  Replay equals the stored
snapshot.  Stable evidence remains snapshot file SHA-256
`a4b7d080c3f287e8aabfe8f091d10226ddd51773bb5771f302955df327529906`,
journal head
`139bf53df41c2e503b6c635d357a62ad3396ea8135da6525df57a4087f0b3921`,
and state SHA-256
`75e94a57cbe9bc3e7c509456cf0b2224836566286da1e3e8d61dc17493550716`.

The module remains a local metadata recorder with no runner, scorer, data,
network, provider, credential, publication, promotion or external-authority
capability.  No live-state mutation, experiment, provider/network action,
release or Git action occurred during final re-review.
