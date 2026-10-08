# Small-step co-evolution: implemented controls and rollout

Status: local source implementation, opt-in, not published or activated in live
research. Human-directed engineering, not evidence of autonomous self-improvement.

## What changed

The existing `ContinuousDiscoveryBatch` gained an optional new scheduling policy
and optional paired-evolution events. It still has no runner, provider, scorer,
network, data reader or permission-granting capability. No second scheduler,
control database, or research framework was added.

1. `initialize(..., active_pool_capacity=2, scheduling_policy="final-singleton-v1")`
   creates a new v3-policy batch. When exactly one attempt remains it recommends
   one slot and accepts one valid candidate. Two/three-member behavior otherwise
   remains unchanged. Omitting the option preserves the old initialization and
   v1/v2 replay exactly. Old records are never silently upgraded.
2. Optional `record_micro_evolution` events use the same existing lock, append-only
   journal, replay validation and atomic snapshot. They record one pending change,
   independent review, activation between jobs, and rollback.
3. Configured batches require every `claim_execution` to carry an active
   harness/researcher pair hash and a nonzero memory-snapshot hash. They appear in
   the branch and subsequent feedback. Existing batches need no new arguments.

## Controls enforced at the recorder/claim boundary

- Separate `harness_sha256` and `researcher_sha256` identities. Each identity
  should refer to an immutable manifest of its source/configuration/dependencies,
  not a convenient mutable filename.
- Exactly one changed axis and one named component per proposal; both/no axes
  changing is rejected. Researcher policy evolution holds the base model fixed.
- Fixed model, data-scope, evaluator, authority and resource-policy commitments.
  A proposal cannot change them. A model upgrade is outside this micro-evolution
  comparison, not a disguised researcher-policy improvement.
- Exact supervisor-configured file scope plus protected paths. Budget, artifact,
  global-state and the micro-evolution control module cannot be allowlisted.
- One pending proposal per configured batch lineage. A second is rejected.
  Ordinary research can still claim work on the unchanged active pair.
- Review bound to the specific proposal, tested pair and original capability
  anchor, from the configured reviewer, distinct from the declared proposer.
- Accept requires evidence-bearing checks for success replay, failure feedback,
  restart, historical replay, protected boundaries, rollback, anchor compatibility
  and a bounded trial; measured file scope must equal the proposal; the named
  benefit must have been observed. No score gain or novelty quota is required.
- Accept and rollback require no active research branches, including selected
  branches not yet executed. No running job is silently switched to different code.
- Compare-and-swap on the batch state prevents a stale review from overwriting a
  newer transition. Journal replay revalidates the evolution transitions too.
- Rejection preserves the active pair and archives the proposal/review. Rollback
  restores the immediate prior pair and appends evidence; completed attempts,
  branch feedback, budget accounting and exposed data are not rewound.

No-change requires no mutation: keep researching with the current pair. There is
no requirement to invent a harness update every batch or submit multiple repairs.
The legacy alternating-release/portfolio contract remains untouched for its old
users; the optional micro-evolution path does not call its novelty-quota selector.

## What these controls do NOT establish

These are trusted-supervisor provenance and transition checks, **not a new
arbitrary-code sandbox**. Receipt hashes and reviewer IDs do not independently
prove test truth, authenticate a person, measure actual filesystem writes or
inspect the worker's loaded code. The existing outer supervisor must verify the
real receipts, exact source/dependency manifests, measured diff and runtime
identity outside the candidate before calling these methods. Do not expose the
mutation methods or journal directory to an untrusted researcher.

Changing a pair in this journal is not installing/deploying a patch. A real
executor must launch the matching immutable artifact and present its measured
pair binding at claim time. The recorder deliberately cannot launch that worker.
No standalone live auto-research dispatcher was added or claimed ready here.

The one-pending rule is per configured batch lineage; this is not a new global
cross-batch lock. Existing single-owner/global-state rules still govern live
dispatch. Starting a new lineage must not be used to evade a pending review,
reset the capability anchor, or regain exhausted authority.

## API sequence for the existing integration owner

1. Create a **fresh** v3-policy batch under existing authority. Do not migrate the
   expired September 29 records or extend their budgets/deadlines.
2. Before selecting any research branch, call:

   `record_micro_evolution("initialize", config, expected_state_sha256=current_head)`

   `config` contains `pair`, `fixed_context`, `allowed_write_paths` for both axes,
   `protected_paths`, and the trusted `reviewer_id`. Freeze real manifests first;
   unit-test placeholder hashes are not acceptable runtime evidence. The exact
   fields are defined by `initialize_micro_evolution` in the existing
   `data_scientist_harness/co_evolution_loop.py`.
3. For ordinary research claims, pass `runtime_pair_sha256` from the verified
   execution manifest and `memory_snapshot_sha256` from the actual decision input.
   A pending proposal does not require a release, extra approval or positive score
   for these normal permitted research steps.
4. Submit one problem-bound proposal via action `propose`. Keep its parent,
   artifact, exact file scope and protected commitments frozen. No mainline code
   is switched at this point.
5. The supervisor tests the isolated candidate under existing authority, checks
   the complete measured diff and receipts, and records `review` with `accept` or
   `reject`. Accept may update the recorded active pair only when the batch is
   idle. A bad/missing compatibility check rejects acceptance without poisoning
   the journal; an explicit reject remains available without a successful trial.
6. The next separately admitted job may use the accepted pair. If a later defect
   warrants rollback, use action `rollback` at an idle boundary. Preserve the
   candidate reader/runtime for candidate-owned records. Never feed v3 journals
   to an incompatible old reader, overwrite history, or retry external actions
   merely because a version was rolled back.

Ordinary researcher experiments remain governed by the September 29 opened-Train
policy. These small-step controls apply to version promotion of the research
system, not a new one-feature-only restriction on scientific exploration.

## Verification actually run

- 75 focused unit/integration tests passed, including all pre-existing selected
  tests. The suite covers the 2+1 and 2+2+1 scheduler paths, invalid/expired claims,
  negative candidates, restart, duplicate claims, paired evolution, immutable
  context, exact write scope, stale review, failed checks, rejection, rollback
  and preserved completed-attempt history.
- Pre-implementation source generated both v1 and v2 journals in temporary
  directories. Current source reconstructed identical entire states and hashes;
  journal bytes remained unchanged and the parent reader still replayed them.
- The combined synthetic integration exercises two parent-pair attempts, a
  reviewed idle-boundary pair change, a final singleton under the new pair, then
  rollback without erasing any of the three attempts or their feedback.
- No market data read, protected evaluation, actual model dispatch, live worker,
  publication or paid run occurred. These are operational tests, not independent
  scientific evidence or a live autonomous-harness trial.

Command, run from `research/market_rsi` with the existing pinned Python:

```sh
python -B -m unittest \
  data_scientist_harness.test_micro_evolution \
  data_scientist_harness.test_co_evolution_loop \
  data_scientist_harness.test_strong_harness_contract \
  supervisor_harness.test_continuous_discovery_batch \
  supervisor_harness.test_continuous_discovery_small_steps \
  supervisor_harness.test_research_cycle_gate
```

Compatibility receipt and saved pre-change source:
`/Users/estelle/.codex/worktrees/3c5e/self-evolving-v18-local/research/harness_continuity_audit_20261001/`.
Use `legacy_compatibility_final.json` for the final candidate-source comparison.

## Concrete next rollout

1. Independent review of this local diff and source/runtime manifest; preserve the
   existing dirty/untracked source rather than staging the repository wholesale.
2. Trace the existing actual worker dispatch call site. Bind its measured pair and
   memory manifest to this claim API. Do not replace it with a new research engine.
3. Run one fresh bounded opened-Train operational batch only under valid authority,
   with unchanged task/data/controller configuration and no protected evaluation.
   Require actual feedback-dependent continuation, zero manual transition repair,
   and a clean terminal state. Do not require prediction gain to pass this test.
4. Only then evaluate an agent-authored micro-change. Today's implementation is a
   human-directed repair. A local passing suite is not automatic permission to
   activate a researcher-written harness patch.

Implementation rationale reuses the October 1 continuity audit, its observed
singleton/replay failure, and the existing versioned co-evolution/strong-harness
contracts. No new research-method or literature-performance claim is introduced.

## Local Git checkpoints

The user explicitly requested version control on October 1. The source branch is
`codex/market-rsi-coevolution-checkpoint-20261001` in
`/Users/estelle/Developer/market-rsi`; `main` and published tags are unchanged.

- Baseline `793c30248b085edd673fd95472db91d2d4efe973` preserves the previously
  uncommitted September 28–29 code, tests, plans and curated logs. Its scheduler
  is the verified pre-control source with SHA-256
  `1732ff9363a37d34c79b50ea8298d1fa39d6052524c0eac543e14e18fdf1eeb5`.
  The saved pre-change bytes were staged without reverting working files.
- The following implementation commit isolates the October 1 controls, tests
  and accompanying notes. Compare it with that baseline to see the actual
  incremental change rather than all earlier uncommitted research at once.
- Reports, DOCX deliverables and synthetic audit receipts are preserved in the
  separate task repository on `codex/market-rsi-research-records-20261001`.

These are local preservation checkpoints, not release approvals. The 75-test
focused suite passed again before checkpointing; it is not a fresh validation
of all 247 files in the baseline. A credential-pattern scan found no matches
among the pending source/report files. Historical Markdown whitespace warnings
were retained rather than rewriting evidence. Raw data, paid-source content,
credentials, runtime files, budget/global-state ledgers and raw run artifacts
remain outside these commits. No remote push, release tag or live activation
was requested or performed.
