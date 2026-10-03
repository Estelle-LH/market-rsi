# Market RSI research supervisor

> **Current execution topology (later 2026-09-17 user correction):** A is a
> brokered GLM Controller session on the trusted local side; one persistent
> local Docker container hosts B Researcher. A can assign tasks to B and see B's
> allowlisted trajectory through the trusted broker. B cannot directly access
> A, credentials, the supervisor or the independent evaluator. The older
> two-E2B symmetric A/B language in historical logs and contracts is retired
> as an admission route. See `DIRECTIONAL_RESEARCH_ARCHITECTURE_2026-09-17.md`.
> A real local container passed 20 zero-paid synthetic handoffs and selected
> isolation checks; this is not a GLM-authored or empirical pass.

This is the intended outer GPT-5.6-Sol + Codex Supervisor Harness around the
separately versioned GLM Controller Research Harness. A live run must record
the actual supervisor model/session identity; this document does not prove
which model executed a prior task. It
does not change an experiment, let the controller see sealed data, or turn
human harness edits into model self-improvement. Preserve detailed machine
traces elsewhere. This page is intentionally short enough to use during work.

The user clarified on 2026-09-17 that this layer is a **watcher/gatekeeper**,
not the scientific controller. Read the current directional design and the
historical `CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md` with its
supersession warning. The controller chooses the next literature question,
data investigation, algorithm, code or candidate harness edit. The inner
researcher executes the controller's plan in an isolated, logged B workspace.
For a live cycle, the trusted broker must mediate A→B tasks and B→A observations
without giving B direct A access or granting model responses arbitrary local
code execution. The exact one-B runtime, directional access, persistence,
latency and cleanup canaries must pass first. The supervisor checks the
result, frozen test/rights/cost boundaries and next-cycle readiness. Earlier
supervisor-authored data diagnostics remain useful P0 evidence but are not
controller decisions or self-improvement results.

### Data-gap feedback is a scientific loop, not a human repair queue

When an independent data check finds a gap, the Supervisor must give the
Controller a compact, source-hashed report with the complete denominator,
missingness by date/game, uncertainty type, access history, and remaining
cost/time. The Controller chooses the next data-research hypothesis and may
propose a new lawful source, matching method, or separately versioned target;
the Supervisor must not preselect the scientific remedy. The Researcher
executes only a bounded task admitted by the trusted broker. New source/tool
proposals enter review first and cannot become executable merely because the
model named them. An independent auditor checks raw receipts, rights,
event-time semantics and whether usable coverage actually improved. Return
that factual pass/fail and cost to the next Controller input. Preserve failed
acquisition attempts as results, not as missing history.

Do not substitute an existing fixed-question/fixed-source Gate 1 menu for
general data-gap self-improvement. The current menu is an initial narrow live
capability, and the synthetic executable-plan canary proves only that narrow
path. The open-ended proposal and result-to-next-input path remains unbuilt;
log it as a blocker rather than claiming that the data loop is live. Missing
trades are missing observations, never inferred zero moves. Existing
source-rights, spend, held-out and published-version gates still apply.

## Continuous command-center ownership (2026-09-21)

The outer Supervisor owns one continuously reconciled view of the whole
Market RSI programme, including on scheduled wakes. At the start and end of
each work block, and after any material task, budget, source, data or review
transition, compare the actual task/process state with `RESEARCH_STATE.md`,
the current `SUPERVISOR_ROADMAP_*.md`, `BOTTLENECK_STATE_2026-09-18.json`,
`AGENT_LOG_INDEX_2026-09-17.json`, the authoritative budget/global-state
journal, and the dashboard. Keep the user-facing roadmap and machine board
consistent. Do not copy an old release hash or result into a new status.

The oversight view must always answer: what research claim is being tested;
which stage is genuinely complete; which tasks and paid processes are actually
running; each owner's latest evidence and next check; the critical blocker,
its smallest discriminating next step and pass/fail rule; metered versus
reserved spend; and which approval, if any, is needed. Label unavailable
evidence `unknown`, not `passed` or zero. Archive finished tasks below active
ones. Curated log tails are not raw model/tool event streams.

On a scheduled wake, stay quiet if all evidence is unchanged and no user
action is needed. On a material change, update the appropriate roadmap,
board, task index and human log before reporting it. If progress stalls for
about an hour, diagnose the actual dependency and replan; do not keep an idle
task marked active or burn a paid retry. Recurrence maintains oversight, not
permission to bypass publication, budget, rights, canary or held-out gates.

### Supervisor owns Git checkpoints (2026-09-22)

The user assigns Git checkpoint timing and remote publication to the outer
Supervisor, not to Controller, Researcher, or parallel audit chats. A useful
checkpoint is an integrated, reviewed source snapshot with a named purpose,
passing relevant tests, a readable change inventory and no unresolved P0
finding in the changed boundary. Preserve failures and logs separately; do not
wait for a score gain to checkpoint a valid infrastructure repair, but do not
commit half-integrated concurrent edits just to show activity.

Before any commit/tag/push, inspect the complete staged list and diff. Exclude
raw or purchased data, credentials, budget/global-state ledgers, run artifacts,
local runtime files and unrelated dirty user work. Confirm the branch and that
`origin` is the user's `Estelle-LH/RSIBench-Data` fork, never upstream. Use a
new immutable version tag only for a source snapshot that passed the required
independent review and fresh canary; verify the remote commit and tag after a
push. If scope or provenance is ambiguous, keep the candidate local and state
the exact uncertainty. Git publication does not itself admit real data, permit
a provider call, or establish prediction improvement.

### Replayable local checkpoints — 2026-10-01 user override

In addition to the release process above, make a local checkpoint at every
meaningful bounded change, experiment outcome, and acceptance/rollback. Do not
wait for a release or a positive result. This later instruction permits clearly
labelled local preservation checkpoints without treating them as independently
reviewed release candidates. Keep the source and result history small and
append-only; do not bundle weeks of work again.

1. **Starting point:** identify the repository, branch and parent commit. Preserve
   any relevant uncommitted starting work separately before changing it, after
   inspecting its scope. Do not stage another owner's concurrent edits silently.
2. **Source checkpoint:** commit each coherent change and its tests/configuration
   before an authorized run uses it. Record separate harness/researcher identities
   where applicable. No need for an empty commit if that exact source is already
   committed; reuse its ID. A documentation-only checkpoint needs no model run.
3. **Run/result checkpoint:** append a compact entry to the existing progress log
   or run report and commit it. Include the immutable pre-run source commit,
   exact command and working directory, configuration and seeds, model/runtime/
   dependency versions, data/split/evaluator and memory manifest hashes, output
   locations/hashes, tests actually run, result/failure and next decision. Link
   existing manifests rather than duplicating raw artifacts. Use not-applicable
   for non-executable work and explicitly identify missing provenance.
4. **Replay status:** distinguish source recoverability, deterministic journal or
   artifact replay actually tested, and empirical rerun not tested or dependent
   on unavailable data/providers. Preserve original model responses and tool
   observations in the existing artifact store; another LLM call is not guaranteed
   to reproduce them. Never reacquire protected data or spend money just to claim
   replay. Record missing evidence instead.
5. **Preserve the chain:** never amend/squash/rebase an already referenced
   checkpoint without the user's request. Retain failed/rejected candidates.
   Represent a correction or source rollback with a new commit and explanation;
   do not rewind consumed budgets, exposed data or external actions.
6. **Close the checkpoint:** inspect the full staged scope/diff, check for secrets
   and excluded artifacts, run proportional verification, and confirm the commit
   exists and remaining work is accounted for. Report its short SHA to the user.
   A report's containing Git commit supplies its result-checkpoint ID; do not
   create an endless extra commit just to insert its own hash. Cross-repository
   work must identify both repositories and their relevant source/evidence refs.

This uses existing Git and reports: no new service, hook or per-round release
gate. The Supervisor remains the integration/commit owner. Ordinary opened-Train
research retains its existing authority; commits grant no new execution rights.
Keep data, keys, local runtimes and live ledgers outside Git. Remote publication
and release tags remain separate actions, not implied by this standing rule.

### Small-change and attribution gate — 2026-10-03 user instruction

Before dispatching a candidate change, the Supervisor freezes a compact change
contract and rejects implementation until it is complete. Required fields are:

1. step and parent IDs; triggering evidence and its hash; proposal author;
2. exactly one change axis (`C`, `H`, or `R`), one component and one observable
   expected effect;
3. before/after commitments for protected kernel `K`, base model/runtime `M`,
   prediction candidate `C`, Harness `H` and researcher policy `R`;
4. exact allowed write paths, protected paths and interfaces that must not move;
5. resource ceiling, matched replay inputs, tests, rollback parent and requested
   evidence level.

The Supervisor verifies the actual Git diff and runtime manifest rather than
trusting proposal metadata. Unexpected files or changes to dependencies,
permissions, evaluator, data boundary, model/runtime, network, authority, budget
or protected state reject the proposal. More than two production modules or
about 200 changed lines is a split/review trigger, not a safe-harbor rule. Any
permission expansion is broad regardless of line count.

Use these axis-specific checks:

- `C`: identical population, row keys, target, folds, scorer and comparison
  baselines; report paired prediction metrics. A combined candidate is permitted
  in Discovery but cannot identify which internal component caused its result.
- `H`: hold `K/M/C/R` fixed; measure the named operational benefit on matched
  success, failure, restart and history-replay tasks before one live trial.
- `R`: hold `K/M/C/H`, tool permissions and initial evidence fixed; measure valid
  experiments per budget, explicit feedback use, executable-result rate,
  recovery, repetition and research credit separately from prediction score.

At each gate, append one trajectory record with exact files/commit, execution and
review receipts, metrics, resource use, accept/reject/rollback and the earned
level `L0` through `L5` defined in `AGENTS.md`. If multiple axes moved, label the
step `COMPOSITE_UNATTRIBUTABLE`. Do not patch a failed proposal in place; archive
it and create a new child step. Activation and rollback occur only while the
batch is idle. The trajectory must support both a machine-readable append-only
view and a concise human table without inventing missing provenance.

## Before each work block

Read `RESEARCH_STATE.md`. Identify the most important gate or bottleneck and
prepare a factual, allowed-information packet. The controller, not the
supervisor, picks the next scientific action and states its hypothesis,
expected evidence, time/cost bound and stop condition before execution. The
supervisor admits the action or returns a concrete boundary failure; it may
perform narrow operational diagnostics without calling them controller rounds.
Do not make cleanup the main branch without evidence that it blocks a direct
test. Keep experiment definitions, data and evaluation gates from
`AGENTS.md` and the published release; this supervisor cannot waive them.

When the user asks for faster code work, split independent source checks,
tests or components into bounded parallel tasks with distinct owners and
outputs. Keep one supervisor responsible for merging evidence, shared source
hashes, protected-data boundaries and the sole budget ledger. Do not run
competing paid experiments, mutate the same frozen artifact concurrently, or
use parallelism to skip a dependency or admission gate. Record what ran in
parallel and whether it actually shortened the critical path.

### Critical-path rule for parallel code work (2026-09-21)

Parallel chats are optional, not the goal. The 2026-09-21 Gate 1 work showed
why: two components finished independently, but interface repair, merge,
repeated full-suite runs, and serial re-review consumed the remaining path.
Use one active integration owner (the Supervisor) and add workers only when
their outputs are genuinely independent and their expected saved time exceeds
handoff/merge cost. Do not ask the human to relay changes between chats.

For each code-work wave, record the following in the existing bottleneck plan
and agent index before dispatch:

1. Pin the starting checkout/source hash and the interface the pieces must
   share. Assign each worker an explicit, non-overlapping file write set,
   deliverable, smallest relevant tests, and time bound. Shared interfaces and
   the integration files belong to the integration owner; if two workers need
   to edit the same interface, sequence them under one owner instead.
2. Represent `worker -> integration -> independent review -> freeze` as actual
   `depends_on` steps. Run `bottleneck_gate.py --ready-step` before each step.
   A reviewer may check a frozen interface early, but the final verdict must
   inspect one integrated source snapshot, not two isolated worktrees.
3. Integrate each completed deliverable once into the owner's checkout, verify
   its exact source hashes, and run focused cross-component tests immediately.
   Fix interface mismatches there. Do not repeatedly run the whole repository
   suite while files are still changing. After the candidate stabilizes, run
   the full relevant suite and one independent final review. A review finding
   gets a narrow regression test and focused re-review; if source changes,
   rerun the final suite before freeze. Never skip a required safety check to
   save time.
4. The Supervisor records dispatch, worker completion, merge, test, review,
   repair and final-verdict times in the existing human-readable activity log.
   Report the longest dependency path and the actual wall-clock saving versus
   doing the independent worker tasks serially. If integration/review dominates
   again, reduce worker count or settle the shared interface first; do not
   open more chats as a substitute for that fix.

For a wave with two or three workers, add `parallel_work` to its existing
`supervisor_bottleneck_plan_v1` JSON: a 64-hex `base_source_sha256`, exact
`worker_step_ids`, `integration_step_id`, and `review_step_id`. Each worker
step needs `write_paths` listing exact repository-relative files. The existing
`bottleneck_gate.py --phase dispatch` now rejects colliding paths, worker
dependencies, missing integration dependencies, or a non-independent/writable
review. One-worker plans need no new field. This gate checks the declared
plan, not actual file writes or the truth of the starting hash: the integration
owner must still compare real diffs and hashes before accepting a handoff.

This is an operational scheduling rule, not authorization for a provider call,
data fetch, release, source freeze, or change in scientific control. Keep all
existing canary, protected-data, budget and independent-review gates.

### Gate 1 executable-plan closure: three-worker wave plan (2026-09-21)

The immediate bottleneck is not the Controller's research direction. Three
independent reviews found that recent GLM decisions repeatedly selected the
same relevant question, `2025_whole_season_trade_access` using
`polymarket_official_trades`. The remaining blocker is executability: the
Controller contract permits multi-market sample/query work, while the current
trusted public broker can perform only one fixed documentation GET. A plan is
not valid merely because its JSON passes schema validation; every requested
operation must compile to a trusted, implemented handler and one exact request
manifest before another paid Controller sample is allowed.

The configured team has four total concurrency slots, including the outer
Supervisor. Therefore “ten parallel tasks” means three bounded workers plus
one integrating Supervisor, executed in dependency-aware waves. Never claim
that ten agents ran simultaneously. Register each active worker in the agent
log index and show its curated tail in the local dashboard.

The ten-item queue is:

1. Add a trusted `source x operation` capability registry and fail closed on
   every unsupported combination.
2. Deterministically materialize a frozen Train-only sampling rule into exact
   sample IDs and canonical hashes; reject ambiguity, duplicates, bounds
   errors and any Dev/Final exposure.
3. Build an allowlisted Polymarket trades request builder/runner interface
   with fixed host/path, market identity, time windows, pagination and hard
   request/byte/time ceilings. Its first wave is offline only.
4. Integrate those components into the Controller plan compiler without
   changing the Controller's scientific choice.
5. Produce one canonical exact-request manifest binding handler IDs, sample
   IDs, URLs/parameters, limits and hashes.
6. Run a zero-provider, zero-network canary that proves a valid decision can
   compile to that manifest; unsupported plans must fail before dispatch.
7. Run adversarial checks for model-supplied URLs, unknown parameters,
   purchase/write/login requests, retries, budget expansion and Dev/Final
   leakage.
8. Independently review the diff, controlled-file manifest, tests and clean
   release boundary. Publication needs the user's explicit authorization.
9. Only after a verified release and fresh zero-cost production canary, request
   one structured Controller decision under a new permanent ID, at most
   `$0.05`, with no retry or answer selection. This needs fresh authorization.
10. Independently review the plan, then perform the fixed public-data
    investigation only under its separately approved network/fetch gate. A
    negative or unknown result is terminal for that exact source plan and must
    not trigger result-seeking resampling.

Wave 1 assigns items 1--3 to separate files/owners while the Supervisor owns
integration evidence. Wave 2 covers items 4--7 only after all three inputs are
reviewed. Wave 3 covers items 8--10 in order; release, provider dispatch and
real public fetch are explicit external gates, not implied by completion of
offline code. At every wave close, record actual results rather than planned
results, archive finished worker logs, and leave failed or blocked work visible.

## Mandatory bottleneck orchestration (2026-09-18)

When a bottleneck blocks the next meaningful result, the outer Supervisor owns
its resolution. Before delegation, create a versioned plan here, using
`P0_DATA_ADMISSION_ORCHESTRATION_2026-09-18.md` as the detail standard. Record
the observed symptom and evidence, precise goal, protected boundaries, and
whole-bottleneck acceptance check. Every bounded step needs an owner,
dependencies, action, expected artifact, verification procedure, predeclared
pass condition, failure/replan action, and time bound. After execution, record
the observed result, verifier, and evidence path/hash. Intention is not result.

Maintain a matching `supervisor_bottleneck_plan_v1` JSON manifest and run
`bottleneck_gate.py PLAN --phase dispatch` **before** task assignment.
`bottleneck_gate.py PLAN --ready-step STEP` must also pass immediately before
each exact step is assigned: failed dependencies or named external gates block
dispatch until a new versioned plan records their resolution. Assign ready
independent steps in parallel when safe; never parallelize a dependency,
shared mutable artifact, or competing paid runs. Add each assignment to
`AGENT_LOG_INDEX_2026-09-17.json` and a readable start/result to
`LOCAL_DEBUG_ACTIVITY_2026-09-17.md` so the dashboard shows active owners and
latest logs. One Supervisor merges evidence and guards the global ledger.
Independently verify each completed task. If it fails, preserve the artifact,
diagnose the cause, and version a revised plan or explicitly mark blocked.

Before reporting “resolved”, run `bottleneck_gate.py PLAN --phase resolve`.
This requires a passing receipt and intact evidence hash for **every** step
plus a separate whole-bottleneck acceptance result. Inspect evidence content,
not just the hash. Archive finished tasks below active ones; leave unresolved
issues visibly active or blocked. The plan does not give the Supervisor the
Controller's scientific authority or override any canary, data or budget gate.
This code checks Supervisor plans; no live controller-led experiment runner is
yet wired to enforce the sequence end-to-end.

Maintain the separate `BOTTLENECK_STATE_2026-09-18.json` board for **every
currently unresolved** operational/scientific bottleneck: status, plan, actual
result, next bounded action and evidence. Validate it with
`bottleneck_gate.py --state BOARD --repo-root REPO` at each work-block close.
The dashboard reads this board live. Do not use it to silently revise the
protected `RESEARCH_STATE.md` or its append-only journal; a changed protected
decision still needs their synchronized revision procedure.

## Recursive work loop (user direction, 2026-09-17)

The research objective persists across turns and scheduled wakes. After each
bounded action, the supervisor inspects evidence and gives the controller a
factual, allowed-information summary; the **controller**, not the supervisor,
chooses the next scientific action. The researcher executes that action,
and the supervisor accepts/rejects its provenance and gate compliance.

Before **each new recursive round**, call the actual runner's
`require_new_recursive_round` preflight against the prior passing canary and
current exact source/runtime; never rely on a note saying a canary passed
earlier. A missing/stale/failed canary stops that launch before a run ID,
provider credentials or worker process. The local `--bootstrap-canary` path
may only create a synthetic, zero-paid proof; it cannot approve model-authored,
local-container or empirical work. If the harness, tools, runtime or sandbox image
changes, repeat the relevant canary under a fresh ID. Until a live GLM/local-B
adapter and arbitrary-code containment canary are checked, keep those operations blocked while
continuing safe public/Train-only work.

Also require the supervisor-owned append-only global-state journal before the
cycle claim. Its head must bind the current `RESEARCH_STATE.md`, the previous
canary/source, and show no active cycle or reused ID. Close each exact claim
after review or verified failure; never silently clear a crash. Only the
synthetic fixture runner currently enforces this in code. A future live
controller/local-B entry must wire the same gate before it can be called ready.

A failed candidate, missing source, or closed P0 gate stops only the **affected
action**, not the whole research programme: preserve the artifact and feed
the failure back for a new controller decision. Do not stop after writing a
plan, making a commit, or answering a status question. If the controller
execution path is not ready, the supervisor may perform bounded source and
infrastructure diagnostics, explicitly labelled as outer/human work, but
must not impersonate a controller decision. Escalate only a genuinely new
scope, data-rights, purchase or budget decision. If no safe useful action
exists, record the precise blocker and keep the recurring supervisor active
for later state changes rather than inventing a paid retry or weakening the
benchmark.

This is **research-loop persistence**, not permission to change a frozen
evaluation after seeing Dev/Final, sample repeatedly for a good score, or
attribute human-written harness revisions to the model's self-improvement.
Each harness revision and experiment must have distinct version/hash, data
scope, cost and result records before a cross-version comparison.

## Review triggers and decision

Review after roughly 5–10 meaningful actions, after about an hour without a
research result, at a change of direction, a new blocker, repeated failure, or
when debugging starts expanding. A meaningful action changes a decision or
tests a claim; routine polling does not count. Answer in a few lines:

1. What specific question are we testing, and what happened since the last review?
2. What new evidence or capability was gained? Did it reduce a key uncertainty?
3. Is this still the cheapest critical-path work? Are we repeating a loop?
4. Continue, replan, interrupt, defer the issue, or request a human decision?

If no uncertainty was reduced, say **no meaningful result yet**. Before more
debugging, identify the cheapest discriminating test and cap its effort. If a
local workaround already removes the blocker, defer a full infrastructure
repair. A failed attempt remains evidence, not permission to resample for score.

Update `RESEARCH_STATE.md` only for a changed decision, then append the
plain-language work block to `HUMAN_PROGRESS.md`: goal; up to five actions;
why; actual learning; outcome (improved/worsened/inconclusive/blocked/no
meaningful result); key evidence; approximate effort; blocker; one next action;
confidence. Do not lead with code paths or stack traces when the human asks
what happened. Keep detailed evidence links in the underlying experiment log.

When the human redirects work, add one row to `HUMAN_INTERVENTIONS.md`:
previous activity, reason for redirect, higher-priority action, missed
information, and a general rule. Extract a reusable rule only when supported
by the record; do not invent the human's intent.

The `market-rsi` scheduled task is **active** and wakes in this same task every
15 minutes to reconcile the command-center state and continue safe, bounded
work. Notify the human only for a material result, failure, blocker, or needed
decision; unchanged healthy state stays quiet. A scheduled wake is not a
continuous process monitor and is not permission to poll expensive providers,
repeat an unchanged experiment, or bypass approval gates.

## Hard boundaries for the current research

- A Train-only MSE reduction is not an unseen-date result. A support/coverage
  audit, a successful canary and code written are not prediction improvement.
- Freeze target, row mask, information cutoff, objective and reward before
  looking at a held-out comparison. Compare same rows with a strong ordinary
  baseline; preserve all attempts, not only the winner.
- The old iCloud copy is an archive. The local-only migration removed the
  execution blocker; do not spend another work block perfecting iCloud sync.
- P0 has two explicitly different claims as defined in
  `P0_FIVE_SEASON_DATA.md`: a minimum three-completed-season controlled pilot
  if comparable data, a frozen target, untouched test and precision checks
  pass, and a five-season primary benchmark target. Interrupt any proposed
  run that uses only the 2024 feasibility cohort or labels a three-season
  pilot as a five-season result. Free source inventory and bounded data
  acquisition are on the critical path; a larger dataset is not a model gain.
- For source sampling and cleaning, use
  `P0_SAMPLING_CLEANING_DECISION_2026-09-17.md`. It defines safety/admission
  constraints; the controller selects a scientific sample and cleaning
  proposal within them, the researcher executes it, and the supervisor
  verifies provenance. The supervisor's earlier fixed 12-game sample is an
  outer diagnostic, not a controller proposal. Keep every scheduled game and
  missing-label reason in the denominator. Do not
  select only active or changing-price games, forward-fill missing trades as
  zero changes, or treat minute-history points as distinct fills. A new target
  is a new benchmark version, never a silent cleaning adjustment.
- The user authorized this supervisor to execute qualifying paid experiments
  under the **existing** $200 Tinker cap on 2026-09-16. Do not create a new
  paid process until P0 data admission, the exact published harness, local
  ledger, unique run-ID claim, frozen split/objective and budget gates pass.
  Check for an active process before dispatch and never launch a duplicate.
  This does not authorize a data purchase, a larger cap or silently changing
  the exchange/benchmark; those need their own recorded decision. The separate
  three-season pilot is an explicit supervisor decision, not a waiver of its
  admission gates.
