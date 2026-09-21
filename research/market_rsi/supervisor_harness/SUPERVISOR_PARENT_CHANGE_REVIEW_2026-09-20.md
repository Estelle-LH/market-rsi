# Supervisor parent binding — source review packet

Status: **published and accepted for Supervisor-parent control only; not admitted for paid prediction work**.

Current unpublished protocol manifest: 305 files, SHA-256
`75eb4b7b989fb3a84baaf2748176f9fff6c26a2e2b20cc33c5ef0a468fd4be62`.
`git diff --check` passes for the reviewed parent, canary, tests, manifest and
review documents.

## What changes

1. The bounded live entry waits for one fresh Supervisor claim before reading
   the provider credential. The claim must bind the cycle, child PID and
   command hash, parent Supervisor PID and command hash, and durable watchdog
   head. A missing, late, symlinked, malformed, or mismatched claim fails
   before credential access.
2. A new fixed parent constructs the live-entry command. It owns the child
   log, emits watchdog heartbeats, counts only allowlisted artifact hashes as
   material progress, and reads the authoritative local budget ledger.
3. A stalled or failed child becomes one immutable incident. The parent stops
   only the matching PID and task-labelled Docker container, writes cleanup
   and Controller repair receipts, and never retries.
4. A zero exit is not enough for success. The parent independently requires
   the child and container absent, an allowed terminal budget state, and a
   regular result artifact before closing the watchdog task.
5. Local-B containers now include `market-rsi-task-id=<exact container name>`
   in addition to the historical canary label. The label gives the parent an
   independent cleanup identity.
6. The watchdog, monitor, local control, and parent are now included in the
   immutable protocol publication manifest. This deliberately makes the old
   release stale and keeps paid launch closed until a new authorized release.

## Exact production-source hashes

| File | SHA-256 |
| --- | --- |
| `bounded_live_entry_v1.py` | `b1903924cc851b135cb86d16b3f7a55c4a6783031efe3c121b673a07b31eaf03` |
| `bounded_live_supervisor_parent_v1.py` | `56d3fd5e94ccbeeebc9cefa75e50f730faa7897d5f7ba3f252df391fae9ad8ff` |
| `local_b_container.py` | `76b0420fdd9c0fdc6b90cbfdc35979e5c196f0917102936edb9ea3f03e8525be` |
| `protocol_source_release.py` | `d41ecba9ec500a19dd109d39be3ab81a10add92fdece91b8a919e52e12b80b30` |
| `supervisor_watchdog.py` | `1fb25a6f7e94f09ddf76d9af945a52ae1abeed109a895e58b8f57d66b42051ba` |
| `supervisor_watchdog_monitor.py` | `1f5b8299528c7f11e2c4bf72331515cd7b7e7ab999c12eb2fba927f3d2fbefc7` |
| `supervisor_watchdog_local_control.py` | `4f79687e1b643ea05e1a3d70122ca1a0b1c2cbba8ff85c5f8818b41764f88522` |

Immutable parent acceptance executables are now also in the protocol manifest:

| File | SHA-256 |
| --- | --- |
| `run_bounded_live_supervisor_parent_canary.py` | `230437cacfa0e4a94b85e250383a1843659ed9e70a5d63ac26e9dfb7f9f74156` |
| `run_bounded_live_supervisor_parent_success_canary.py` | `806d002c62eef14b6dfc107dabfc03cfd4266345dafa350cfce4bca3f445c908` |

## Verification

- 89 adjacent unit/integration tests pass in the pinned project environment,
  including the new deterministic clean-exit race reproduction and success-
  canary contract tests.
- Fresh zero-paid blocked-runner proof:
  `artifacts/supervisor-live-parent-blocked-20260921-03/canary-result.json`.
- The proof used a real macOS child and a real local Docker container. It
  produced one incident and one cleanup receipt, confirmed both targets
  absent, made zero provider calls, and cost `$0`.
- A separate read-only review recomputed the result and cleanup hashes and
  checked 15 conditions, including both child and Supervisor identities.
- Failed precursor canaries remain unchanged and were not reused.
- The first fresh success-path proof,
  `artifacts/supervisor-live-parent-success-20260921-01`, exposed a distinct
  clean-exit race: the child completed its result and container, then became a
  transient zombie between the parent's loop poll and the monitor's `ps`
  observation. The changed zombie command string was correctly rejected by
  the watchdog but was not an identity substitution. The failed ID is
  preserved.
- The parent now reaps the exact owned `Popen` before monitor evidence and
  handles only the narrower race where that same child exits during the
  monitor read. Strict live identity checks remain unchanged; an immediately
  reused PID is still rejected by terminal evidence.
- Fresh zero-paid success-path proof
  `artifacts/supervisor-live-parent-success-20260921-02` passed: one real
  macOS child, one real task-labelled Docker container, allowlisted preflight
  and result artifacts, exit 0, no incident, no cleanup invocation, both
  targets absent, zero provider calls and `$0` cost. A separate read-only
  check recomputed the Supervisor-result, child-result and claim hashes and
  found no matching process, cleanup receipt or labelled container.

## Boundaries

- This proves the blocked/failure control path, not prediction quality.
- It does not admit the prediction dataset, open Final, or authorize a paid
  Controller sample.
- The success path now has a fresh zero-paid local fixture under the current
  unpublished bytes. It must be rerun under the eventual immutable published
  source version; this local proof cannot authorize paid work.
- Both blocked and healthy parent canary runners are now mandatory protocol
  source files. Publication verification will reject a release that omits or
  changes either acceptance executable.
- Publication requires an explicit commit/tag/push authorization. Only the
  user's `origin` may be used; never push to upstream.

## Publication and post-publication acceptance

- Authorized commit: `a3a33fe9ba29ee03375dcd5ac3c4311fa583981b`.
- Annotated tag: `market-rsi-protocol-v0.1.10`; tag object
  `c0ea00014a80965718f7716304412583739a2cc1`.
- Remote verification: 305 files; aggregate SHA-256
  `75eb4b7b989fb3a84baaf2748176f9fff6c26a2e2b20cc33c5ef0a468fd4be62`.
- Published blocked proof: `supervisor-live-parent-blocked-20260921-04`, one
  incident, one cleanup, exact targets absent, zero provider calls, `$0`.
- Published healthy proof: `supervisor-live-parent-success-20260921-03`, no
  incident, no cleanup, exact targets absent, zero provider calls, `$0`.
- The Supervisor parent control gate is closed under the published bytes. Gate
  1 data-source selection remains separately blocked until its source is
  reviewed and immutably released.
