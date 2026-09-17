# Recursive research execution contract — 2026-09-17

Status: **user-directed architecture correction; not yet an operating paid
pipeline or a model result.** This contract replaces the mistaken assumption
that the outer supervisor should choose each scientific step. Historical
supervisor-authored 2023/2025 data audits retain their original attribution.

## What is running versus what is only designed

| Piece | Evidence today | Claim boundary |
| --- | --- | --- |
| Existing Codex/GLM Data Scientist Harness | Has logged literature, Train diagnostics and CPU fitting tools; its broker still says Harness releases are human-directed, and a capability/algorithm proposal does not activate code. | Legacy research path, **not** proof of this new recursive architecture. Do not silently use its old output as a new controller/researcher round. |
| Controller/worker/Harbor components elsewhere in the repo | Existing bounded candidate execution and isolation code. | Not yet bound to this contract's controller decision, inner researcher task and supervisor return path. |
| New provenance gate | `research_cycle_gate.py` and the `-03` canary bind synthetic facts → scripted decision → real local subprocess trace/output → review; 9 unit tests pass. The `-01` canary had an incorrectly bound facts hash; `-02` predates the added re-verification at handoffs. Both remain preserved. | **Fixture only**: no model authored the choice, local subprocess is not E2B/Harbor isolation, and no predictive evidence was produced. |
| Formal controller-led round | No passing end-to-end receipt yet. | Must be reported as **not started**. |

| Role | Decides / does | Cannot do |
| --- | --- | --- |
| Supervisor | Watches run health, source provenance, protected-data boundaries, budget and held-out admissions; gives the controller a factual allowed-information packet; validates or rejects researcher outputs and records why. | Pick the controller's literature question, algorithm, feature, code edit or candidate harness revision; rewrite its plan; grade its own candidate on sealed Final. |
| Controller | Reads the allowed archive and aggregate failures; chooses the next question, paper search/read, data investigation, experiment, code task and candidate harness change; writes hypothesis, expected evidence, cost bound and stop rule **before** execution. | Read sealed labels or raw protected tests; bypass the supervisor/runner; modify the frozen reference evaluator or budget ledger; change old attempt IDs. |
| Inner researcher | Performs the assigned searches, reads sources, writes and tests code, runs source-only/Train-only experiments and returns artifacts and exact tool traces in an isolated workspace. E2B/Harbor are permissible backends after canaries. | Self-approve a paid run, upload raw market data to an unapproved provider, mutate protected files, hide failed attempts or select a new task without a controller decision. |
| Independent runner/evaluator | Enforces source/input hashes, per-run claims, exact process and budget checks, same-row scoring and sealed one-time evaluation. | Treat controller prose or a researcher's own score as independent verification. |

Cycle: supervisor **observes** → controller **decides** → researcher
**executes** → runner **measures** → supervisor **checks and records** →
controller sees only the allowed feedback and decides again. A closed P0 or
budget gate blocks only the relevant paid/evaluation action; the controller
can still choose lawful public-source, code or Train-only research. This is
the requested recursive loop, not an instruction to make unsafe retries.

## Required state transition for every new round

1. **Input frozen.** Supervisor prepares a factual packet with source/harness
   version, allowed Train/public evidence, prior accepted feedback, rights,
   time and remaining budget. It cannot insert a preferred scientific action.
   Hash it and claim a fresh cycle ID before asking the controller.
2. **Controller decision frozen before execution.** Save the first valid raw
   response, model/runtime and paid-provider receipt (or explicitly mark a
   scripted fixture), exact input hash, hypothesis, task, expected evidence,
   maximum time/cost and stop rule. No choosing among multiple responses for
   score, editing its plan, or calling a supervisor choice a controller choice.
3. **Researcher order.** The runner copies that exact admitted task into an
   isolated fresh work area with the least necessary files/tools. The researcher
   may search/read, code and run only within the order; it cannot approve its
   own budget, score, data access or next task. Record the real tool calls,
   read-page hashes, code diff, failures, timeouts and cleanup. Search hits do
   not count as papers read.
4. **Independent measurement and review.** The runner verifies artifacts and
   Train-only results against frozen input/decision hashes. Supervisor checks
   provenance, rights, process, budget, leakage and whether the claimed output
   actually answers the predeclared question. It may accept, reject or block
   with a reason, but cannot substitute a different scientific result.
5. **Feedback then next choice.** Only a verified, bounded feedback packet goes
   into the next controller input. A failed attempt remains in the archive; a
   fresh controller decision and run ID are required to act again. The loop
   continues across scheduled work blocks, not by retrying the same paid ID.

There are **two lanes**, not one global stop switch. The research lane allows
public-source, software and admitted Train-only work while P0 is closed; its
outputs are hypotheses/diagnostics, not a held-out improvement claim. The
formal lane opens only after comparable data, frozen target/baseline/row mask,
genuinely untouched dates, published source, budget and exact process gates.
Only the independent evaluator may open its one-shot held-out comparison.

## Non-negotiable acceptance checks

- A missing/mutated input, decision, raw response, worker trace, output or
  review makes the cycle invalid. Each artifact is write-once; a correction
  uses a fresh ID and preserves the failed one.
- A model-authored claim needs a real controller adapter receipt. The current
  synthetic fixture always emits `controller_led_result=false` and
  `empirical_improvement_claim_allowed=false`; no prose may override this.
- A live researcher claim needs a verified E2B/Harbor runtime/isolation and
  cleanup receipt. A local fixture process is never an isolated researcher.
- A controller-proposed capability or algorithm is an archived proposal until
  the researcher implements it and independent tests admit it in a **new**
  Harness version. The protected evaluator, permissions, data splits and
  budget ledger are not self-editable.
- To attribute a score change, compare on the same frozen rows/budget and
  report model/algorithm changes separately from Harness/data/target changes.
  Preserve the no-memory/ordinary-model control; Dev is not free training data.
- Review progress after about an hour without decision-relevant evidence.
  Timebox source/debug branches by the decision they can change. Do not spend
  a day on data plumbing merely because P0 formal scoring is closed.

The first controller response must be bound to an immutable input packet,
model/runtime identity, one lineage/run claim, raw response and decision hash.
The researcher receives only the approved task and tools. Preserve searches,
papers **actually read**, code diff, test output, source hashes, row IDs,
cost/timeout/failure and researcher output; a search hit is not a paper read.
For candidate harness changes, run in a fresh sandbox/worktree, test and
publish a new version before an empirical comparison. Keep the previous
harness/control arm frozen. A model gain across different harness versions
cannot be attributed to the model alone.

E2B/Harbor are execution options, not scientific authorities. Before using
either, verify exact container/image/runtime, network and credential isolation,
file mounts, real tool execution, timeout/cleanup and cost/accounting on a
zero-paid canary. Until those adapters and the decision-to-execution binding
exist, describe activity as **outer diagnostics**, not controller-led rounds.

Next implementation gate: bind a **real** controller decision to a fresh
researcher order using the existing provenance paths; run a zero-paid
E2B/Harbor isolation and cleanup canary; then verify the allowed feedback can
reach a second controller decision. Until each receipt passes, remain in the
research lane and describe the fixture as a fixture. Do not launch formal paid
training or use sealed Dev/Final merely to demonstrate architecture.
