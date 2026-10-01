# Continuous Discovery research scheduler v2 independent review — 2026-09-29

## Verdict

**HOLD.** The frozen snapshot preserves the zero-authority boundary, replays the
real 32-record v1 journal exactly, and correctly separates a branch's research
parent from its comparison incumbent.  It does **not** yet satisfy the adopted
research-credit contract.  Two P0 findings allow unverified or duplicate
credit to steer the next pool, and two P1 findings leave the active-pool and
exploration-reserve rules weaker than specified.

This review was read-only except for this new log.  It did not modify source,
tests, the historical batch, state documents, scores, the incumbent, or any
experiment artifact.  It ran no real Train experiment and used no network,
provider, Dev, Final, publication, or promotion path.

## Exact reviewed snapshot

| Item | SHA-256 |
| --- | --- |
| `continuous_discovery_batch.py` | `f3f1f5297aee6f906217519401806bdf41f7e6e7cbd88a31c705f381a0d5e1b5` |
| `test_continuous_discovery_batch.py` | `29eeac56a30eeb05ac4f6616f6aeb433acd2446edf6cb52bb1f9e2fcf7d32862` |
| v2 implementation log | `4a667c87902d6ded0f483221d160c55262c25f4b27fda05648515ac13cfc7181` |
| adopted research-capability/credit audit | `872b1dc0bbb05f5907e45ae33910af4fbb80d1cb5e4bed25988032915f295c17` |
| preserved v1 `batch.json` | `95ee26f83cd9c727a1b19782a787aeae93e363727238ed58737e01fb988cb847` |

The governing credit audit requires one canonical question digest, duplicate
search, authority snapshot, evidence bundle, independent Supervisor credit
decision, and route action.  Credit 0 removes/cools down the route; credit 1
permits at most one bounded follow-up; credit 2 support may keep a route active
while credit 2 refutation executes its predeclared stop/branch action.  It also
sets a baseline 30% exploration reserve, adjustable only to 20--40% before a
batch with an append-only reason, without expanding any ceiling or authority.

## Findings

### P0-1 — Credit is neither globally deduplicated nor independently admitted

`record_research_credit()` and replay validate only that the value is in
`{0,1,2}`, the branch is at `result_reviewed`, and that this same branch has no
credit yet (`continuous_discovery_batch.py:1177-1210,1887-1925`).  The event has
only `attempt_id`, `credit`, `evidence_sha256`, `problem_id`, and `reason`.  It
has no question digest, independent credit-review hash, authority/evidence
bundle binding, or global duplicate check against `research_credit_records`.

An independent temporary-root counterexample recorded credit 2 twice for two
different attempts with the exact same `evidence_sha256` and `problem_id`.
Both records were accepted and both entered feedback.  The focused regression
at `test_continuous_discovery_batch.py:1006-1014` rejects only a second call on
the same attempt, so it does not test semantic/evidence deduplication across
attempts.  This lets one evidence bundle mint multiple scheduling credits.

The same probe also showed that a REVERT with
`independently_reviewed=false` can receive credit 2, reach
`controller_feedback_ready`, and become the next research parent.  Review
logic requires independent review only for KEEP
(`continuous_discovery_batch.py:1130-1137,1821-1827`); the credit transition
does not independently require it.  Credit can therefore affect ranking and
slot hints without the required independent Supervisor admission.

Required repair: bind each credit decision to a canonical question digest,
evidence bundle, authority snapshot, result-review hash and independent credit
review; reject reuse of the same question/evidence across the complete batch;
and require the exact independently reviewed terminal evidence before any
nonzero credit can influence scheduling.

### P0-2 — Credit 0 and credit 2 refutation do not execute their route semantics

Every terminal branch with any non-`None` credit, including 0, is added to
`ranked_research_parents` (`continuous_discovery_batch.py:710-727`).  Every
terminal branch is also accepted as a known parent regardless of credit or
route action (`:907-914,1654-1665`).  A temporary-root counterexample confirmed
that a credit-0 branch remains ranked and can be selected immediately as the
next research parent.

There is no support/refute classification, `route_action`, cooldown, distinct
follow-up digest, or credit-1 follow-up counter.  Consequently credit 2
refutation cannot stop a route, credit 0 cannot remove/cool it down, and credit
1 is not limited to one bounded follow-up.  Moreover, slot count uses the
maximum of every historical credit (`:754-761`), so an old credit 2 keeps
recommending up to three slots without regard to whether it was a refutation or
whether the credited question is already resolved.

Required repair: persist and validate the predeclared support/refute and route
action, exclude credit-0/stopped routes, cap credit-1 follow-up lineage, and
make credit-2 refutation stop/free the route rather than raise its priority.

### P1-1 — The 30% reserve is advisory and admits out-of-policy values

The implementation correctly keeps `max_attempts` unchanged, counts actual
claims by allocation, and sets `authority_granted=false`.  It does not grant
network, provider, data, scoring, release, or promotion capability.

However, `_reserve_fraction()` accepts the full `[0,1]` interval
(`continuous_discovery_batch.py:126-132`), and initialization stores it without
an append-only adjustment reason (`:830-870,1443-1493`).  Independent probes
confirmed that both `0.0` and `1.0` are accepted.  With the default 30% reserve,
the hint recommended one exploration slot in a two-slot pool, yet the selector
accepted two exploitation allocations because it checks only total pool
length, not the recommended exploration count (`:902-906,1647-1677`).

The returned "budget hint" contains slot counts and historical allocation
counters only (`:776-790`); it does not bind the adopted bounded resource class
or maximum attempts/time/bytes.  Repair by enforcing or explicitly
reason-binding a 20--40% batch-time reserve, validating the selected allocation
against it, and keeping resource hints non-authoritative but concretely bounded.

### P1-2 — Capacity is 2 or 3, but an active global pool may contain only one

Capacity itself is restricted to 2 or 3 and persists correctly.  Ordered
`active_attempt_ids`, `pool_generation`, research-parent lineage, and the
frozen comparison-incumbent hash survive snapshot deletion and journal replay
(`continuous_discovery_batch.py:848-870,874-981`).  Overlapping pool selection
is rejected.

The selector nevertheless accepts any non-empty list up to the recommended
maximum (`:1585-1653`).  The project's own REVERT-parent and credit tests create
one-member pools despite capacity 2 or 3
(`test_continuous_discovery_batch.py:861-892,952-968`).  If "global active pool
2--3" means actual concurrent membership while at least two attempts remain,
that acceptance is not met.  Define the intended minimum explicitly and test
the remaining-budget exception.

## Acceptance items that pass

- **REVERT branch versus incumbent:** a fully archived REVERT runner can be a
  later research parent while the incumbent remains unchanged.  Each child
  stores `research_parent_sha256` separately from
  `comparison_incumbent_sha256`; a stale concurrent KEEP is fail-closed rather
  than silently replacing a newer incumbent.
- **Persistence and lineage:** capacity 2/3, ordered active IDs, pool generation,
  branch archive, allocation, parent and comparison hashes are journaled and
  recover exactly after snapshot deletion.
- **No score/KEEP contamination:** credit is recorded only after the frozen
  result-review transition; it is absent from score arithmetic, the KEEP test,
  and incumbent construction.  The module has no scorer or runner capability.
- **Ceilings and protected boundaries:** attempts remain capped by the original
  `max_attempts`; all exact `BOUNDARY_FLAGS` remain unchanged, including
  Dev/Final, acquisition, network, paid provider, publication, promotion,
  runner, scoring, data-open and authority flags.
- **Actual v1 replay:** this review copied the preserved 32-entry journal to a
  temporary local root, removed only the temporary copy's snapshot, and
  replayed it with the frozen v2 source.  The reconstructed state was exactly
  equal to the preserved snapshot: journal head
  `bb254c289f7ba5ce739b2a86e26b401747271cc4eb5d10b86302f1c95095d465`,
  state SHA-256
  `300a744fe4060edda8fed533c73ba6ddd65adb753fd0b5759790a3fb270d7f88`,
  and no v2-only fields.  This is stronger than the synthetic 32-record unit
  fixture at `test_continuous_discovery_batch.py:1072-1126`.

## Verification

- Focused module suite with pinned Python 3.12.3: **23/23 PASS**.
- `py_compile` with an external temporary bytecode cache: **PASS**.
- Static import/capability scan: only standard-library persistence imports;
  no network, provider, runner, data-reader, or scoring call path found.
- Protected boundary comparison against the preserved v1 snapshot: **exact**.
- Temporary-root adversarial probes: duplicate evidence accepted twice;
  unreviewed REVERT credit 2 accepted and reusable as parent; credit 0 reusable
  as parent; 0%/100% reserves accepted; default 30% exploration hint could be
  ignored by an all-exploitation pool.

The passing unit suite establishes storage and the happy-path mechanics, but it
does not close the acceptance-critical credit and reserve counterexamples.
Do not activate scheduler v2 until the P0 items are repaired and independently
replayed; resolve the P1 semantics in the same frozen revision.
