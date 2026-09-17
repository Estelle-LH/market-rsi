# Market RSI research supervisor

This is the intended outer GPT-5.6-Sol + Codex Supervisor Harness around the
separately versioned GLM Controller Research Harness. A live run must record
the actual supervisor model/session identity; this document does not prove
which model executed a prior task. It
does not change an experiment, let the controller see sealed data, or turn
human harness edits into model self-improvement. Preserve detailed machine
traces elsewhere. This page is intentionally short enough to use during work.

The user clarified on 2026-09-17 that this layer is a **watcher/gatekeeper**,
not the scientific controller. Read
`CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md`. The controller
chooses the next literature question, data investigation, algorithm, code or
candidate harness edit. The inner researcher executes the controller's plan
in an isolated, logged workspace. For a live cycle, controller tool execution
and researcher execution must be on different E2B sandbox IDs/microVMs, with
broker-only communication; the supervisor/runner and protected evaluator stay
outside both. Harbor is not a substitute for this role boundary. The exact
runtime, access-denial and cleanup canaries must pass first. The supervisor checks the
result, frozen test/rights/cost boundaries and next-cycle readiness. Earlier
supervisor-authored data diagnostics remain useful P0 evidence but are not
controller decisions or self-improvement results.

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
E2B/Harbor or empirical work. If the harness, tools, runtime or sandbox image
changes, repeat the relevant canary under a fresh ID. Until a real live
adapter and isolation canary are checked, keep those operations blocked while
continuing safe public/Train-only work.

Also require the supervisor-owned append-only global-state journal before the
cycle claim. Its head must bind the current `RESEARCH_STATE.md`, the previous
canary/source, and show no active cycle or reused ID. Close each exact claim
after review or verified failure; never silently clear a crash. Only the
synthetic fixture runner currently enforces this in code. A future live
controller/E2B entry must wire the same gate before it can be called ready.

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

The `market-rsi` scheduled task was explicitly resumed by the user on
2026-09-16 and is **active**. It wakes about hourly to continue the recursive
loop. Give the human one short result-first digest about every two hours, even
if the honest status is "no meaningful result"; report a material failure or
needed decision sooner. This periodic digest is not permission to poll
expensive providers or repeat an unchanged diagnostic experiment.

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
