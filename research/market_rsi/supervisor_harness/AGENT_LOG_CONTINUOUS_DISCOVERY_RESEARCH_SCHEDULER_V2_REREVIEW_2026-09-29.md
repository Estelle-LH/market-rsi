# Continuous Discovery research scheduler v2 — fresh independent rereview

Date: 2026-09-29  
Verdict: **HOLD**  
P0: none  
P1: one exact-type failure in cross-batch archived-credit admission

The repair closes every prior local-batch P0/P1 counterexample: native credit
is independently admitted and deduplicated, credit 0 and credit-2 refutation
cannot remain research parents, credit 1 has one follow-up, active pools contain
two or three members, the exploration reserve is enforced, and resource hints
remain bounded and non-authoritative. The real 32-record v1 state also replays
exactly without migration.

One fresh adversarial check found a residual fail-closed defect in the new
cross-batch import surface. `_archived_parent()` compares `research_credit`
with `== 1` / `== 2` but never requires an exact integer. Python therefore
admits `True` and `1.0` as credit 1 and `2.0` as credit 2; each value is stored
unchanged and enters ranked research-parent selection. This does not grant
execution, data, scoring, network or incumbent authority, but it violates the
closed credit-0/1/2 schema and leaves the archived-parent admission contract
non-exact. Scheduler v2 should remain inactive until this small repair and a
fresh replay pass.

This review did not modify implementation or tests and did not initialize a
real batch. It used temporary local roots only. It ran no experiment, runner,
scorer, network/provider action, data read, Dev/Final access, publication,
promotion or authority mutation. The only repository write is this rereview
log.

## Frozen snapshot

| Item | SHA-256 |
| --- | --- |
| `continuous_discovery_batch.py` | `520c1149cc7803703e22e4334938b50066c908be991e1c6246cbaa64b3eea215` |
| `test_continuous_discovery_batch.py` | `634a7d823f1a752a773cb56522408ade94600c8550c22f56739bdeda1d714a9b` |
| v2 implementation log | `0ef292068ff130dafedc70e9d9f118a14b6dbe2aa51c6e9eb7e987defd7a3cfb` |
| prior HOLD review | `16ba058f20eed11e65843c60fb4ea646a65f2349759e059d2cf738533717db9d` |
| adopted research-credit audit | `872b1dc0bbb05f5907e45ae33910af4fbb80d1cb5e4bed25988032915f295c17` |
| preserved v1 `batch.json` | `95ee26f83cd9c727a1b19782a787aeae93e363727238ed58737e01fb988cb847` |

## Prior HOLD findings

### Closed — native credit binding, dedupe and independent gate

For a v2 branch, credit is admitted only after `result_reviewed` and is bound
to the exact predeclared question ID/digest and decision-rule hash, result
review, evidence bundle, problem, authority snapshot and independent credit
review. Positive credit additionally requires `execution_outcome=succeeded`
and `independently_reviewed=true`. Native `record_research_credit()` uses an
exact integer type check and replay repeats the same validation.

The state rejects reused question IDs, question digests and reused
`(problem_id, evidence_bundle_sha256)` pairs across prior native records and
initial cross-batch declarations. Credit remains append-only and one record per
branch. It appears only in the v2 Controller evidence packet and pool hint; it
does not enter score arithmetic, KEEP/REVERT review or incumbent construction.

### Closed — credit 0, inconclusive follow-up and decisive refutation routes

- Credit 0 requires `invalid` plus `cooldown` or `stop` and is excluded from
  eligible research parents.
- Credit 1 requires `inconclusive` plus `bounded_followup`; the parent is
  removed after exactly one scheduled child. Two children in one pool are
  rejected as well.
- Native credit-2 `refute` requires `cooldown` or `stop` and is excluded from
  ordinary in-batch parent ranking. Credit-2 `support` plus `continue` remains
  eligible.
- A separately declared cross-batch credit-2 refutation may be imported only
  as an explicit `branch` route, allowing a new question without reviving or
  re-crediting the stopped historical question.

### Closed — global pool, diversity, route novelty and reserve

- V2 capacity is exactly 2 or 3, and every selected active pool contains at
  least 2 members. Overlap is rejected until the previous pool is closed.
- Method-family diversity is required within a pool. A credit-2 archived
  parent may seed more than one child only when the children have distinct
  method families, question IDs/digests and hypothesis digests. Reused
  question or hypothesis routes reject both within the pool and against batch
  history. Credit-1 parents remain limited to one child.
- The reserve is restricted to `[0.20, 0.40]`; 30% is the baseline, and a
  non-default value requires an append-only reason. The selection hint computes
  required exploration slots from actual consumption, and admission rejects a
  pool with fewer exploration slots. The previous 0%, 100%, missing-reason and
  all-exploitation counterexamples now reject.
- Pool members carry exact closed resource hints. Classes are
  `local_analysis`, `small_experiment`, `metadata_lookup` or
  `bounded_page_read`; ceilings are 1--8 attempts, 1--7,200 seconds,
  0--10,000,000 bytes and USD 0--0.05. `authority_granted` must be exactly
  false. These remain scheduling hints, not execution or spend authority.

### Closed — cross-batch parent is not incumbent or authority

The import declaration binds candidate, source batch/attempt, archive
manifest, independent review, authority snapshot, problem, canonical question
and evidence bundle hashes. Candidate/archive/question, source identity and
problem/evidence duplicates reject. An imported candidate cannot alias the
initial incumbent and `authority_granted=true` rejects.

Imported parents enter only `ranked_research_parents`. Each child separately
stores that research-parent hash and the current comparison-incumbent hash;
selection does not alter incumbent history. Recovery from the append-only
journal preserves all import fields and this separation exactly.

## P1 — archived credit accepts bools and floats

At `continuous_discovery_batch.py:185-194`, `_archived_parent()` assigns the
raw `research_credit` and uses equality comparisons to determine route
eligibility. It does not apply the exact check used by native credit at
`record_research_credit()`.

Fresh temporary-root probes produced:

```text
True ACCEPT True RANK True
1.0 ACCEPT 1.0 RANK 1.0
2.0 ACCEPT 2.0 RANK 2.0
```

All three declarations also contained the required nonzero lowercase hashes,
`authority_granted=false`, and otherwise valid route combinations. Thus this
is specifically a scalar-type bypass, not an extra-field or missing-evidence
case. JSON distinguishes `true`, `1.0` and `2.0` from the contract's exact
integer credits, so accepting them makes replayed scheduler evidence
non-canonical at the semantic boundary.

Impact is bounded: the values are numerically equivalent to an existing rank,
and the imported parent still cannot become the incumbent or grant capability.
It nevertheless affects parent eligibility/ranking through an input that the
credit contract says must reject. This is P1 rather than P0, but it blocks a
fail-closed release.

### Minimum repair and mandatory regression

Before evaluating route eligibility, require:

```python
if type(credit) is not int or credit not in {1, 2}:
    raise DiscoveryBatchError("archived research credit must be 1 or 2")
```

Credit 0 is intentionally not a valid archived research parent. Add direct
initialization/replay tests rejecting `True`, `False`, `1.0`, `2.0`, strings,
null and out-of-range integers, while preserving canonical integer-1 and
integer-2 imports. Re-run the complete focused suite, exact real v1 replay,
cross-batch recovery, same-parent/different-method acceptance, duplicate-route
rejection, reserve attacks, capability scan and compile check.

## Legacy replay and verification

The preserved live v1 root was read only:

`/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts/continuous-discovery-batch-20260929-01`

Its 32 journal records were copied into a private temporary directory and the
copy's snapshot was removed. Rebuilding with the frozen v2 module produced an
object exactly equal to the preserved snapshot:

- journal length: `32`;
- journal head:
  `bb254c289f7ba5ce739b2a86e26b401747271cc4eb5d10b86302f1c95095d465`;
- stored state SHA-256:
  `300a744fe4060edda8fed533c73ba6ddd65adb753fd0b5759790a3fb270d7f88`;
- v2-only state fields present: none.

Verification results:

- focused pinned-runtime suite: **25/25 PASS**;
- `py_compile` of module and test with an external bytecode cache: **PASS**;
- static capability scan: only standard-library state/persistence imports;
  no runner, scorer, data reader, network/provider client or authorization
  path;
- exact boundary flags remain unchanged: opened-Train context only, with
  Dev/Final, acquisition, network, paid provider, publication, promotion,
  runner, scorer, data-open and authority flags false;
- fresh archived-credit type probes: **3 invalid values accepted**, yielding
  the P1 above.

An initial test invocation without the project `PYTHONPATH` failed module
import before collection; the canonical project invocation then passed 25/25.
This was an invocation issue, not a product-test failure.

## Final decision

**HOLD, P0 none, P1 one.** Do not activate a real scheduler-v2 batch yet.
Apply only the exact archived-credit type check and its regressions, then obtain
a fresh independent rereview. No reward service, RL loop, scorer change,
evaluation-kernel change or Harness expansion is warranted.
