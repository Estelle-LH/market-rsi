# PMB lease ownership snapshot repair — 2026-09-28

## Verdict

**PASS** for the scoped `repair_lease_ownership_snapshot` worker step in
`SUPERVISOR_PMB_SYNTHETIC_FOUNDATION_2026-09-28-v3.json`.

The weak membership-only live-handle set was replaced with a weak, external,
identity-keyed ownership registry.  An entry freezes the exact `ArtifactStore`
object, store root path and device/inode identity, lease ID, journal name,
registration-claim receipt, lifecycle state, journal head, next controller
slot, and early-stop flag.

## Repair behavior

- Every public live transition validates the complete external ownership and
  replay snapshot before its first artifact write.
- The internal journal append validates ownership again immediately before the
  transition append.
- In-memory lifecycle fields and the external snapshot update only after the
  append, full hash-chain replay, artifact replay, state, head, slot, and
  early-stop result verify exactly.
- Normal terminal close verifies the global registry close and revokes the
  exact object.  Interrupted recovery also revokes any matching in-process
  owner, preventing a stale authentic object from being retargeted.
- The registration-only crash window remains recoverable exactly once through
  `mark_interrupted_unresolved`; it does not reopen controller work.
- The create-time registration append is separate from the owned-transition
  path, so there is no caller-selectable ownership-bypass flag on `_append`.

## Adversarial replay

The focused tests now reject, before any new artifact or journal write:

- same-store stale authentic handle retargeting to a fresh claim;
- different-store stale authentic handle retargeting;
- mutation of `store`, `lease_id`, `journal_name`, `_state`, `_head`,
  `_next_slot`, `_early_stopped`, and store device/inode identity;
- shallow copy, deep copy, pickle round trip, direct constructor, and
  `object.__new__` reconstruction;
- mutation of the durable registration claim.

Each negative case records the path and SHA-256 of every file in every
involved synthetic store immediately before and after the attempt and asserts
exact equality.  The unchanged authentic object still advances normally.

## Verification

- Focused command:
  `python3 -m unittest research.market_rsi.tests.test_pmb_simple_lane_episode_lease`
  — **15/15 PASS**.
- Combined command:
  `python3 -m unittest discover -s research/market_rsi/tests -p 'test_pmb_simple_lane_*.py'`
  — **57/57 PASS**.
- `python3 -m py_compile` for the implementation and focused test — **PASS**.
- `git diff --no-index --check /dev/null <path>` for each owned path — **PASS**
  (exit 1 only because each path is an untracked addition; no check output).
- Import/capability scan — implementation imports only stdlib plus the local
  `artifact_store`; no network, subprocess, Docker, provider, payment, data,
  training, evaluation, release, or Git-mutation capability was added.

## Exact code identity

- `research/market_rsi/pmb_simple_lane/episode_lease.py`:
  `2f98d86d71856096d9cfe1b3a6209a222ce723c3da2e2bfdd0004c5f8440c51f`
- `research/market_rsi/tests/test_pmb_simple_lane_episode_lease.py`:
  `c59bfddc45da559998ea49367659b2d70fab5fd048543422380596734b5489fa`

## Boundary

Only the assigned implementation, focused test, and this log were edited.
Receipt/binder files were not edited.  No network, PMB or episode bytes,
provider, payment, Docker, runtime, protected state, training, evaluation,
release, commit, tag, or push action occurred.
