# Learning-checkpoint feedback precheck — 2026-10-05

## Scope and actual checks

- Registered role: `learning_checkpoint_feedback_precheck_20261005`, auxiliary mechanical feedback helper, not the scientific Controller.
- Actual repository: `/Users/estelle/Developer/market-rsi`; parent HEAD `83461bd6d0011b72d6e364bde684b7f4a378331b`.
- Plan: `LEARNING_CHECKPOINT_UPGRADE_2026-10-05-v1.json`, SHA256 `ca94a389fc416296d79f615dd7096d96a87eece11376d0aaf7409c6b1784853e`.
- Clock readings: work acknowledged at 2026-10-05 20:36:29 UTC; baseline/check summary at 20:38:06; unchanged source hashes reconfirmed at 20:39:51. These are tool readings, not estimated run timestamps.
- Read the applicable project instructions, full current upgrade plan and Market RSI research-progress skill; inspected actual recorder eligibility, credit validation, journal replay, feedback sealing, pool selection, archive import and corresponding tests; read the feedback consumer and its matching tests. No claim that a proposed helper API already exists.
- Skill influence: assess validity, prediction quality, learning and exploration separately; a valid negative or ordinary memory reuse is not proof of stronger research capacity or research-policy self-modification.
- Serving model identity is not independently authenticated; exact version unknown. This task uses no actual account Controller call, provider or scientific selection.
- Only this new registered log is written. Other agents' dirty source/metadata/document work is preserved. Closed six-attempt/24-fit authority is not reopened.

Read/check bindings, unchanged during this precheck:

| File | SHA256 |
| --- | --- |
| `continuous_discovery_batch.py` | `1b3065ea2990e886ff05869d5c6afd39bc0e80ebb053436f51fd9d9cee0d148c` |
| `account_controller_feedback_consumer.py` | `b0c4c7a28f2eeb333587b9a53faa230a3b751d707433c0dc3b6f4d3e78e0e68e` |
| `test_continuous_discovery_batch.py` | `3f8db4052dd1ebff31b18fbdcdd720b9fbfd85f5a3ed9a7b1f3e62056524a5fa` |
| `test_account_controller_feedback_consumer.py` | `304801701b69dd37912c903b4e5a46fd7ea36b1d55b12bd89535223df7ea455a` |

Existing synthetic baseline command, actual source working directory:

```sh
env PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 '/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python' -B -m unittest supervisor_harness.test_account_controller_feedback_consumer supervisor_harness.test_continuous_discovery_batch
```

Result: **50 tests passed in 0.614 seconds**. This is the existing baseline, not evidence that the proposed upgrade is implemented. No real fits, model calls, authority writes or protected-data reads. No test errors occurred; a long combined source display was truncated, so relevant missing sections were reread rather than claiming the truncated display was complete.

## Minimal prospective integration

1. Place the new assessment in an explicitly opt-in recorder feedback schema. `prepare_input` already copies the exact sealed `feedback` object unchanged. Therefore a new assessment nested there reaches the Controller without expanding historical `NUMERIC_KEYS`, `_compact`, the eleven input roles or the response schema. Do not add default assessment/null fields to old packets.
2. Expose one public pure eligibility function for the new protocol, returning eligibility/route plus an explicit reason. Reuse it in recorder ranking and consumer validation. The consumer must evaluate the immutable original packet's ranked records during response recovery, not consult a changed live batch snapshot.
3. Keep old schemas and credit predicates exact for historical replay. Future opt-in assessment must separate scientific validity, frozen forecast KEEP/REVERT, learning evidence/credit, and justified exploration route. A valid zero-credit or REVERT candidate with a distinct bounded question should not be automatically invalidated or excluded. A failed or leaking candidate is not valid performance evidence merely because repair work was useful.
4. Seal and bind assessment/evidence in the same public-method and journal-replay paths. Both `mark_controller_feedback_ready` and `_apply(controller_feedback_ready)` compute/check packet hashes; changing only the public method or a log would fail recovery or leave a log-only feature.
5. Preserve all historical authorities, scorer judgments, parent/source identities, once claims, costs and protected-data gates. New eligibility is not permission to execute after the closed cap/cutoff.

## Code-derived compatibility risks

- Recorder `_eligible_parent_records` currently couples credit 2 with support/continue or v3 refute/branch, and credit 1 with one inconclusive bounded follow-up; credit 0 is only the baseline route. Consumer `_recover` repeats these predicates. A core-only change would still reject new valid zero-credit parents at the response boundary.
- `_archived_parent` accepts old credit 1 or 2 shapes only; new zero-credit archives need a prospective schema path. Do not normalize old archives, reset consumed C2, or mint a fresh bounded follow-up by importing a new batch.
- `record_research_credit` and its `_apply(research_credit_recorded)` counterpart currently force credit 0 to invalid/cooldown-or-stop and credit 1 to inconclusive/bounded-follow-up. New opt-in validity/outcome/route semantics must be enforced consistently in both paths. Positive repair learning after an execution failure must not imply successful prediction execution.
- `_is_v2` recognizes versions 2 and 3, while the final-singleton special case is v3. A new scheduling version must consciously preserve the pool/cap/replay behavior rather than accidentally falling through to old v1 rules.
- Pool selection separately checks method diversity, unique identities/questions, exploration allocation and follow-up consumption. Routing separation should preserve those constraints and global capacity; it must not mechanicalize score-top-three selection or let repeated evidence consume new credit.
- `_compact` removes reliability tables, by-date tables, date correction diagnostics and trainer fields only from numerical/supplement projection. New assessment nested in sealed feedback is not currently stripped. Keep that distinction; do not silently expand old numerical inputs or strip assessment proof through a broad recursive projection.
- Current response schema already carries `evidence_used` with source SHA, finding and choice consequence, plus memory additions and stopped exact recipes. No response-schema change is required merely to expose a reviewed assessment or inspect evidence-to-choice provenance. A later richer structured reuse response requires a fresh schema/claim, not reinterpretation of old responses.
- `_hashes` and the citation allowlist establish that a reference was provided, not that the alleged finding or successful reuse is true. Verified reuse should bind the reviewed prior finding to the actual subsequent decision/implementation/result artifact and distinguish proposed, observed and independently verified reuse. Mentioning the same finding again must not earn duplicate discovery credit.
- New assessment artifact SHAs nested only in feedback are not automatically in the consumer's current citation set, which reads role bindings plus memory/history. If needed, admit only exact reviewed opt-in assessment bindings; do not broaden to arbitrary 64-character strings or create circular review/artifact hashes.
- `consume` binds original input/schema, CLI, consumer source and scope. Existing completion recovery deliberately makes no fresh model call or budget check. Preserve exact old transactions and source-drift rejection: do not weaken provenance guards or regenerate old inputs under new code. Original-code recovery remains available from its frozen checkpoint.
- Current `check_budget` fixes deadline/cutoff and six-attempt/24-fit authority. The actual window is closed. Learning credit or a new route cannot revive it. Provider cost remains exact string `"0"`; all existing false permission flags and historical-clock assertion stay unchanged.

## Small prospective regressions recommended

These are recommendations to the implementer/reviewer, not newly executed tests or scientific experiments:

1. Valid prediction REVERT plus learning credit zero remains eligible for one justified distinct question under the new protocol; source-invalid/leaking output is not a valid forecast parent.
2. No novel finding earns zero learning credit without automatically asserting invalid science or stopping a reasonable first small test. Prediction improvement/significance is not required for Discovery eligibility.
3. Independently verified negative evidence earns credit without changing frozen Brier, forecast KEEP/REVERT or incumbent. A useful failed-run repair is separately labeled and cannot supply fabricated performance evidence.
4. Shared recorder/consumer eligibility agrees for all new records, archived-but-not-active valid parents and baseline deduplication. Old v1-v3 route combinations remain exact; consumed C2 and one-follow-up exhaustion survive fresh import/restart.
5. Deduplicate learning by actual finding/question/evidence identity. Later reuse may be recorded but cannot repeatedly mint the same discovery credit. Planned reuse/citation does not imply observed benefit.
6. Assessment is recorded before feedback sealing; public and replay paths reproduce identical packet/assessment hashes. Missing or drifting reviewed evidence and late overwrites fail closed.
7. Historical journals, snapshots and packet bytes remain unchanged with no opt-in; no added defaults/nulls or retroactive credit/routing normalization.
8. New assessment reaches the real prepared prompt intact while old compact omissions, numerical projection, roles and strict response schema remain unchanged.
9. Original-ack and pending-claim recovery preserve zero resampling after cutoff/authority changes. New calls remain rejected at the closed six-attempt/24-fit cap despite scientifically eligible branches.
10. Reuse evidence requires provided, reviewed artifact bindings and an actual downstream choice or execution trace. Unknown hashes or persuasive prose cannot establish factual reuse; predictive or research-capacity benefit remains a separate later test.

## Handoff and claim boundary

Code-derived integration recommendations were sent promptly to Supervisor and coreworker before this log was saved. Root integrates the consumer only after the independently reviewed core interface exists. This precheck establishes feasible integration points and baseline compatibility evidence, not implemented upgrade, prediction gain, autonomous research improvement, matched fixed-versus-evolving success or a new research-policy mechanism.

No source, old records, account calls, Train fits, protected data, external retrieval, fees, commits, publication or cap-reset actions were performed.
