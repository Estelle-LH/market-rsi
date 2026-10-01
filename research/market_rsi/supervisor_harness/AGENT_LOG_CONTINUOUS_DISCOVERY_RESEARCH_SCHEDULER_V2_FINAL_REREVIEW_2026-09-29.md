# Continuous Discovery research scheduler v2 — final independent rereview

Date: 2026-09-29  
Verdict: **PASS**  
P0: none  
P1: none

This review was performed independently of the scheduler-v2 implementation
and repair.  It did not modify the module or tests, did not initialize a real
batch, and did not run an experiment, scorer, runner, data reader, network or
provider operation.  All dynamic probes used private temporary roots or a
read-only copy of the preserved v1 journal.

## Exact frozen inputs

| Item | Required SHA-256 | Observed SHA-256 | Result |
| --- | --- | --- | --- |
| `continuous_discovery_batch.py` | `1732ff9363a37d34c79b50ea8298d1fa39d6052524c0eac543e14e18fdf1eeb5` | same | PASS |
| `test_continuous_discovery_batch.py` | `3f8db4052dd1ebff31b18fbdcdd720b9fbfd85f5a3ed9a7b1f3e62056524a5fa` | same | PASS |
| repair/implementation log | `1e2a2a8d6b84a38b42e05f1d63ef0bf1fe2f480449c82261698d50341301ba5d` | same | PASS |
| prior rereview HOLD | `19acfca320129058c978f6623a33c2a52ee9cc03331fde40843f9ab9e8d50495` | same | PASS |

The earlier HOLD review at
`16ba058f20eed11e65843c60fb4ea646a65f2349759e059d2cf738533717db9d`
was also read as the source of the repaired P0/P1 requirements.

## Closure of the last HOLD

`_archived_parent()` now applies the required exact scalar gate before route
logic:

```python
if type(credit) is not int or credit not in {1, 2}:
    raise DiscoveryBatchError(...)
```

A fresh direct probe produced:

| Value | Result |
| --- | --- |
| `True` | REJECT |
| `False` | REJECT |
| `1.0` | REJECT |
| `2.0` | REJECT |
| `0` | REJECT |
| `3` | REJECT |
| exact integer `1` with `inconclusive/bounded_followup` | ACCEPT |
| exact integer `2` with `support/continue` | ACCEPT |

Thus Python equality aliases can no longer enter imported parent ranking.
Replay applies the same `_archived_parent()` gate during `initialize_v2`, so
the check is not limited to the public initializer.

## Verification actually run

Pinned runtime:
`/Users/estelle/Library/Application Support/MarketRSI/runtime-py312/bin/python`.

Focused suite:

```text
python -m unittest supervisor_harness.test_continuous_discovery_batch -v
Ran 25 tests in 0.398s — OK
```

Both exact frozen Python files also passed `py_compile`; `git diff --check`
reported no whitespace error.  The module's complete import set is limited to
Python standard-library state/persistence facilities:
`contextlib`, `datetime`, `fcntl`, `hashlib`, `json`, `os`, `pathlib`, `re`,
`stat`, `tempfile`, and `typing` (plus `__future__`).  There is no runner,
scorer, model, data, network, provider, purchase, publication, promotion or
authorization import.

## Exact real v1 replay

The preserved root
`continuous-discovery-batch-20260929-01` was copied to a private temporary
directory.  Its copied `batch.json` hash was
`95ee26f83cd9c727a1b19782a787aeae93e363727238ed58737e01fb988cb847` and
its journal contained exactly 32 records.  The copied snapshot was moved out
of the replay root, then the frozen v2 module rebuilt state only from those
copied journal records.

Result:

- rebuilt object exactly equals the preserved copied snapshot: **true**;
- journal length: `32`;
- journal head:
  `bb254c289f7ba5ce739b2a86e26b401747271cc4eb5d10b86302f1c95095d465`;
- state SHA-256:
  `300a744fe4060edda8fed533c73ba6ddd65adb753fd0b5759790a3fb270d7f88`;
- v2-only fields present: none.

This closes backward-compatibility and snapshot-loss recovery for the actual
preserved v1 history, not only the synthetic 32-event unit fixture.

## Research-parent and pool behavior

Fresh suite coverage and source replay confirm:

- cross-batch parents bind candidate, source batch/attempt, archive manifest,
  independent review, authority snapshot, problem, question digest and
  evidence bundle;
- unknown, duplicate, incumbent-aliasing and authority-bearing imports reject;
- import state survives snapshot loss exactly;
- research parent and comparison incumbent are stored separately;
- an independently reviewed REVERT branch with an eligible research route can
  be a later parent without replacing the incumbent;
- two children may share one archived credit-2 branch parent when their method
  families, questions and hypotheses are distinct;
- a credit-1 parent cannot seed two children in one pool and disappears after
  its single bounded follow-up;
- the active global pool contains two or three members, is selected once per
  generation, and cannot overlap a still-active prior pool;
- method-family diversity and globally novel question/hypothesis digests are
  enforced at public admission and replay.

## Credit, dedupe and routing

Research credit remains exact integer `0/1/2` for native records.  Positive
credit requires successful execution plus independent result review and is
bound to the predeclared question/rule, result review, authority snapshot,
evidence bundle and independent credit review.

Question IDs/digests and `(problem_id, evidence_bundle_sha256)` are checked
against prior native credit records; imported parent question digests and
problem/evidence pairs also participate in dedupe.  Repeated evidence cannot
mint another credit record.

Route behavior is fail-closed:

- credit 0: `invalid` plus `cooldown/stop`, never an eligible parent;
- credit 1: `inconclusive/bounded_followup`, exactly one child maximum;
- credit 2 support: `support/continue`, eligible;
- native credit 2 refutation: `refute/cooldown|stop`, excluded from ranking;
- independently reviewed cross-batch refutation: explicit `branch` route only,
  allowing a new question without reviving the refuted question.

Credit is exposed in the Controller evidence packet and scheduling hint only.
It is absent from score arithmetic and cannot change a scorecard,
KEEP/REVERT decision or incumbent.

## Reserve and resource boundary

The reserve accepts only 20--40%; 30% is the default and any other accepted
value requires an append-only reason.  Pool admission enforces the recommended
exploration-slot count from claimed exploration/exploitation attempts.  Zero,
100%, missing-reason and all-exploitation probes reject.

Each pool member requires a closed resource class plus exact bounded attempts,
time, bytes and cost fields.  `authority_granted` must be exactly `false`.
These are scheduler hints only: the module cannot execute work or grant the
network, provider, data, payment or promotion authority needed to consume a
hint.

## Incumbent, scorer and protected-data boundary

`BOUNDARY_FLAGS` remain exact:

- `resident_opened_train_only=true`;
- protected Dev/Final, external acquisition, network, paid provider,
  publication, promotion, runner execution, scoring, data opening and
  authority grant are all `false`.

Boundary expansion rejects during initialization and replay.  An unreviewed or
failed KEEP cannot replace the incumbent.  In v2, a KEEP against a stale
comparison incumbent is non-promoting.  REVERT never changes the incumbent,
while its separately credited research branch may remain eligible.  Controller
packets contain hashes and scheduling evidence, not prediction metrics or a
new scorer.

## Final decision

**PASS.** The P1 exact-type defect from the prior rereview is closed, all prior
HOLD requirements replay cleanly, and no new P0/P1 issue was found in the
frozen bytes.  These hashes are admissible for Supervisor initialization of a
new scheduler-v2 batch within the already-authorized opened-Train boundary.
This review itself does not initialize or start that batch and grants no new
experimental, data, network, paid, publication or promotion authority.
