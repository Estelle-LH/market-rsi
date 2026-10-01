# Continuous Discovery research scheduler v2 implementation — 2026-09-29

## Scope and final status

Implemented the opt-in v2 scheduling extension and repaired every P0/P1 item in
the independent HOLD review at SHA
`16ba058f20eed11e65843c60fb4ea646a65f2349759e059d2cf738533717db9d`.
The repair follows the adopted research-credit policy at SHA
`872b1dc0bbb05f5907e45ae33910af4fbb80d1cb5e4bed25988032915f295c17`.

No experiment was run. No research result, score, KEEP/REVERT decision,
incumbent, protected-data boundary, or authority flag changed.

Frozen implementation files:

- `continuous_discovery_batch.py` SHA-256:
  `1732ff9363a37d34c79b50ea8298d1fa39d6052524c0eac543e14e18fdf1eeb5`
- `test_continuous_discovery_batch.py` SHA-256:
  `3f8db4052dd1ebff31b18fbdcdd720b9fbfd85f5a3ed9a7b1f3e62056524a5fa`

## Backward compatibility

- The v1 snapshot schema, journal envelope, v1 event payloads, evidence packet,
  serial KEEP/REVERT logic, scorer isolation and boundary flags are unchanged.
- `initialize()` still emits the original v1 event unless pool capacity 2 or 3
  is explicitly requested. v2 fields are never injected by `_empty_state()`.
- The preserved real 32-record v1 journal was copied to a private temporary
  directory, rebuilt without its copied snapshot, and matched the preserved
  snapshot exactly: state SHA
  `300a744fe4060edda8fed533c73ba6ddd65adb753fd0b5759790a3fb270d7f88`,
  journal head
  `bb254c289f7ba5ce739b2a86e26b401747271cc4eb5d10b86302f1c95095d465`.

## Credit and route admission

- Pool selection now predeclares a canonical question ID/digest, decision-rule
  hash, novel hypothesis digest, method family and bounded resource hint.
- A credit record binds the exact predeclared question/rule, result-review hash,
  authority-snapshot hash, evidence-bundle hash and independent credit-review
  hash. Question IDs/digests and `(problem_id, evidence_bundle_sha256)` are
  globally deduplicated across the batch; repeated evidence cannot mint credit.
- Credit above zero requires `execution_outcome=succeeded` and an independently
  reviewed result. Failed, invalid, leaking or unreviewed evidence is restricted
  to credit 0 and an `invalid` outcome with `stop` or `cooldown`.
- Credit 0 is ineligible as a next research parent. Credit 1 is an independently
  verified inconclusive result with exactly one bounded follow-up. Credit 2
  support may continue; credit 2 refutation must stop/cool down and is excluded
  from ordinary in-batch parent ranking.
- Credit remains research-process accounting only. It is absent from scoring,
  Brier/log-loss arithmetic, KEEP/REVERT rules and incumbent construction.

## Pool, diversity, reserve and resources

- Each active global pool has exactly 2 or 3 members; a one-member pool is
  rejected. The entire pool is reselected only after the prior active set is
  closed, while every branch remains append-only in the archive.
- `research_parent_sha256` remains separate from
  `comparison_incumbent_sha256`; an independently valid REVERT branch with an
  eligible route may be a research parent without becoming the incumbent.
- v2 initialization may declare hash-bound cross-batch archived parents with
  source batch/attempt, archive manifest, review, authority snapshot, question,
  evidence and eligible-route bindings. They enter only research-parent
  eligibility, never incumbent history or authority. Unknown, duplicate,
  incumbent-aliasing and authority-bearing declarations fail closed and replay
  exactly after snapshot loss.
- A separately reviewed archived negative branch may declare `route_action=branch`
  to seed new, globally novel questions. Two members may share that parent when
  their method families, question digests and hypothesis digests differ; this
  does not revive or re-credit the stopped historical question. Credit-1
  parents remain limited to exactly one bounded follow-up.
- Exploration reserve is restricted to 20--40%. The 30% baseline needs no
  adjustment; any non-default batch value requires an append-only reason.
  Recommended exploration slots are enforced at pool admission and actual
  exploration/exploitation consumption is recorded at the execution claim.
- Every pool member carries a bounded resource class and explicit attempts,
  time, bytes and cost ceilings with `authority_granted=false`. Hints never
  authorize execution, network, providers, data, publication or promotion.
- Method-family diversity is mandatory and hypothesis/question digests are
  globally novel. Controller selection remains global and evidence-informed,
  rather than mechanically taking the three largest historical credits.

## Verification

- Focused module suite: **25/25 PASS**.
- `py_compile` with a private temporary bytecode cache: PASS.
- Static forbidden-capability import scan: PASS.
- Real preserved 32-record v1 replay: exact PASS.
- Whitespace/diff checks: PASS.
- Adversarial coverage includes cross-attempt evidence dedupe, canonical
  question dedupe, failed/unreviewed positive-credit rejection, credit-0 parent
  exclusion, credit-2 refutation stop, credit-1 follow-up cap, route diversity,
  2--3-member pool enforcement, reserve allocation, 0%/100% reserve rejection,
  append-only adjustment reasons, resource ceilings, recovery and boundaries.
  It also covers cross-batch archived-parent recovery, parent/incumbent
  separation, and unknown/duplicate/authority-bearing import rejection.

No unresolved implementation item is known from the frozen HOLD findings. A
fresh independent replay is still required before activating a new v2 batch.

## Rereview P1 closure

The sole P1 from rereview SHA
`19acfca320129058c978f6623a33c2a52ee9cc03331fde40843f9ab9e8d50495`
is closed. `_archived_parent()` now requires exact built-in integer type and a
value in `{1,2}` before evaluating route semantics. Adversarial tests reject
`True`, `False`, `1.0`, `2.0`, `0`, and `3`; valid integer credits 1 and 2 retain
their frozen route behavior. The full 25-test file, compile check, diff check,
and exact real v1 replay all remain PASS.
