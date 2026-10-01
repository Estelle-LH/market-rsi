# PMB episode lease and artifact-store implementation — 2026-09-28

- Assigned at `2026-09-28T23:15:34Z`; base HEAD `f06214b3bb521096078d897fe60ec9ba589c00c6`; dirty Market RSI diff digest `ec4ca5ae3a5975f4c5647e4e3126ef8d5c8810c0dbfb3ece20770ed135e84f6b`.
- Write scope: `pmb_simple_lane/episode_lease.py`, `artifact_store.py`, one focused test and this log.
- Boundary: synthetic local files only; no Docker, process control, provider, data or protected state.

## Implementation

- `artifact_store.py` is stdlib-only and grants no runtime authority. It rejects
  relative roots, default temporary roots, common cloud roots and disposable
  Codex worktrees; tests must opt into a temporary root explicitly.
- Every path is bounded and relative. Directory traversal uses directory file
  descriptors plus `O_DIRECTORY|O_NOFOLLOW`; files use
  `O_CREAT|O_EXCL|O_NOFOLLOW`, mode `0600`, file `fsync` and parent-directory
  `fsync`. Root device/inode identity is rechecked on every operation.
- JSON is canonical (`sort_keys`, compact separators, UTF-8, finite values, one
  newline). Every immutable read requires the original SHA-256 and byte length.
  Journal entries are separate exclusive-create files whose canonical bodies
  bind sequence, prior head, journal name and event. Replay rejects gaps,
  unexpected files, noncanonical JSON and any hash-chain mutation.
- `EpisodeLease` has one global active-lease registry and a never-reused
  exclusive ID claim. Its replayed states are exactly `registered ->
  start_snapshotted -> running_round_N -> candidate_frozen ->
  terminal_review_pending -> closed_passed|closed_failed`, with `unresolved`
  allowed as a terminal failure from any nonterminal state.
- Slots 1--4 are sequential and each commits exactly one task+observation or an
  early stop. A stop forbids further Researcher tasks. Slot 5 is accepted only
  after four consumed task slots or an explicit stop and records synthesis plus
  a frozen candidate with `task=null` and `observation=null`.
- There is intentionally no active-lease reopen API. Read-only restart
  inspection returns `mark_unresolved_only`; interrupted recovery may only
  consume the exact active ID as `unresolved`. Artifacts written immediately
  before a crash but not journaled are hashed and quarantined in that terminal
  event. A terminal lease event that beat a registry-close crash is reconciled
  without changing its outcome. Mutation or a missing committed artifact stays
  fail-closed.

## Verification

Command run from repository root:

```text
PYTHONPATH=research/market_rsi python3 -m unittest -v research.market_rsi.tests.test_pmb_simple_lane_episode_lease
```

Result: **PASS, 9/9 tests, 0 failures/errors**, elapsed `0.072s` on the final
snapshot. Coverage includes temporary-root opt-in, canonical/exclusive create,
path traversal and symlink-ancestor rejection, journal chaining/mutation/extra
entry rejection, full five-slot PASS closure, early stop, no retry, invalid
transitions, one-active lease, never-reused ID, restart-only unresolved closure,
artifact mutation, crash-orphan quarantine and immutable read-back.

Additional checks:

```text
python3 -m py_compile research/market_rsi/pmb_simple_lane/artifact_store.py research/market_rsi/pmb_simple_lane/episode_lease.py research/market_rsi/tests/test_pmb_simple_lane_episode_lease.py
git diff --check -- research/market_rsi/pmb_simple_lane/artifact_store.py research/market_rsi/pmb_simple_lane/episode_lease.py research/market_rsi/tests/test_pmb_simple_lane_episode_lease.py
```

Both passed with no output.

## Exact final source hashes

- `artifact_store.py`: `51434782911cefa261d125ec4d1d978ac6dea7a4e923b8b4b78765d91ecc90de`
- `episode_lease.py`: `fa3c9623e4e974294d977105211098b74ac46e2537d0b0a91742fdd4fc9c32a8`
- `test_pmb_simple_lane_episode_lease.py`: `8a95a780a977b8829a5e8a135e603a75a810c2bb0249a12383e0ea45970f7ddf`

## Result and remaining boundary

**IMPLEMENTATION PASS.** The component is suitable for supervisor integration
and independent review, but does not authorize or implement Docker/process
launch, provider/network access, PMB or episode intake, protected-state access,
training, evaluation, release, commit, tag or push. Package export and
cross-component integration remain supervisor-owned steps.

## Integration import-path repair

- Supervisor integration found that repository discovery did not inherit
  `research/market_rsi` on `sys.path`, so this focused test could not import the
  new top-level `pmb_simple_lane` package. Source behavior was unaffected.
- The focused test now derives `RESEARCH_ROOT` from its own resolved path and
  inserts that exact directory before package imports, matching the neighboring
  experiment-spec test. Only the test and this log changed.
- Module-targeted command without an external `PYTHONPATH` passed **9/9**:
  `python3 -m unittest -v research.market_rsi.tests.test_pmb_simple_lane_episode_lease`.
- Required combined discovery passed **38/38**, zero failures/errors, elapsed
  `0.058s`: `python3 -m unittest discover -s research/market_rsi/tests -p
  'test_pmb_simple_lane_*.py' -v`.
- `git diff --check` on the modified test and log passed with no output.
- Superseding focused-test SHA-256:
  `2ba1d2c3fb81f6af28ccf6edde248414f37df5bd7aab046ddfc5542cccc864ad`.
- Source hashes remain unchanged: `artifact_store.py`
  `51434782911cefa261d125ec4d1d978ac6dea7a4e923b8b4b78765d91ecc90de`;
  `episode_lease.py`
  `fa3c9623e4e974294d977105211098b74ac46e2537d0b0a91742fdd4fc9c32a8`.
