# Recursive research execution contract — 2026-09-17

> **Superseded execution topology (later 2026-09-17 user correction):** the
> two-E2B symmetric A↔B denial design below is historical. A Controller must
> be able to see/direct B Researcher; B must not directly access A. The new
> one-E2B, brokered directional design and its P0 handoff-latency gate are in
> `DIRECTIONAL_RESEARCH_ARCHITECTURE_2026-09-17.md`. Preserve this document
> for provenance, but do not dispatch another paid run through its old A/B
> canary or use old isolation findings as new admission evidence.

Status: **user-directed architecture correction; not yet an operating paid
pipeline or a model result.** The intended outer supervisor is
**GPT-5.6-Sol operating through the Codex harness**. The GLM controller is
inside that supervision layer; it is not the owner of the outer Codex harness.
This contract replaces the mistaken assumption that the outer supervisor
should choose each scientific step. Historical
supervisor-authored 2023/2025 data audits retain their original attribution.

## Current system map and connection-debug boundary (2026-09-17)

This is the **designed** live route, not a claim that a GLM research round has
run. The local read-only dashboard displays existing supervisor/receipt logs;
it does not make unlogged agent tool calls observable retroactively.

```text
LOCAL MAC (trusted)                              REMOTE E2B (canaries only)
Codex Supervisor -- global state, rights, budget
          |
          v
Broker / runner -- E2B SDK commands -----------> A: Controller role sandbox
          |                                        (no GLM invoked in -03/-04)
          +-- admitted task, via broker --------> B: Researcher role sandbox
          |                                        (marker service only in -03/-04)
          +<-- artifacts / observed receipts -----+
          v
Independent evaluator --> append-only Archive --> allowed next input

Direct A <--> B is forbidden in the real workflow. The synthetic network
canary deliberately tries both directions to check that prohibition; it is
not the task-delivery channel. Hosted GLM inference is brokered and was not
invoked by either canary. Protected data and provider keys stay local.
```

**Communication cadence:** A and B do not chat across remote sandboxes on
every tool action. A sends a bounded, hash-bound research order through the
local broker; B does its own internal tool loop and returns one result bundle
through the broker. A can then make another decision. Reuse each role sandbox
within an admitted round rather than creating a sandbox per message; record
the actual broker handoff count and latency. Direct A↔B HTTP is a deliberately
forbidden-path diagnostic, **not** the production communication path. If the
normal broker-mediated handoff itself proves too slow, re-evaluate the
two-remote-sandbox design instead of hiding that cost.

The earlier immutable run `market-rsi-protocol-canary-20260917-03` reached these
boundaries, in order:

| Boundary | Observation | What it does **not** show |
| --- | --- | --- |
| Local parent -> E2B A/B creation | Two distinct sandbox IDs; both guest boundary checks passed. | No GLM decision or researcher execution. |
| E2B network-policy `get_info()` | Both returned `allow_internet_access=false`, `deny_out=["0.0.0.0/0"]`, `allow_public_traffic=false`; both omitted optional `allow_out`. | Missing echo is not proof that the request was ignored or the policy enforced. The strict policy gate remains unconfirmed. |
| B-local marker service | Responded on B's own loopback after two checks. | No A-to-B connectivity conclusion. |
| Local E2B SDK -> A probe command | `commands.run(timeout=25)` raised `TimeoutException` during the first A-to-B-direction diagnostic. That timeout applied to one command containing four sequential public/peer × proxy/direct HTTP attempts. | There is no complete guest HTTP/TLS report, so neither an E2B network outage nor successful isolation is proven. The exact slow sub-attempt is unknown. |
| Reverse B-to-A probe | Not started. | No reverse-path conclusion. |
| Cleanup and accounting | Both exact sandboxes and the peer process were killed, parent reaped, last account check had zero active Market RSI sandboxes; $0.20 is an unknown-usage upper bound, not an invoice. | This is not a research result or an actual billed cost. |

Debug each boundary separately, with source, timestamps, per-attempt progress,
failure type, exact sandbox/process ID, and cleanup visible in the local
dashboard. First use offline tests and the prior immutable receipts. A future
fresh-ID remote diagnostic, if separately admitted under the existing budget
and published-source gates, must establish: (1) which network fields E2B
actually echoes; (2) a trivial A-local command and its SDK receipt;
(3) each A-to-B public/peer proxy/direct probe independently, preserving
partial results on timeout; (4) the symmetrical B-to-A probes; and (5) exact
cleanup and account state. A missing report is **unknown**, not blocked.
One expired command must not prevent recording that the reverse direction was
not attempted. Do not rerun `-03` or turn a diagnostic-only observation into
an isolation pass.

The newer `market-rsi-protocol-canary-20260917-04` used the published 60-second
outer deadline. Two sandbox IDs and their guest boundary checks passed, as did
the B-local marker service. A emitted complete progress for public/proxy and
public/direct, then only a start receipt for peer/proxy; the outer command
expired at 60 seconds without a complete HTTP/TLS report. B→A did not start.
The direction-level peer-service kill was **not** acknowledged, while both
entire sandboxes were killed and the account subsequently listed zero active
Market RSI sandboxes. Its $0.20 is an uncertain upper bound, not an invoice.
The P0 fix adds a hard deadline to each guest request; until a fresh versioned
canary validates that change, this is a diagnosis, not an isolation result.

The conditional E2B decision is evidence-based: if independently repeated,
fresh-ID diagnostics show an E2B-specific defect or a documented policy
capability mismatch that prevents this design from working, stop using E2B in
a **new versioned protocol** and validate a local isolated execution backend
before any model-authored code runs. A timeout in our bundled probe alone is
insufficient to delete E2B. Until a new backend passes its own isolation,
provenance, cleanup and budget canaries, keep arbitrary model-written code
off the unsandboxed Mac. Formal scoring has an independent P0 blocker: only
11 untouched 2025 Final dates versus the predeclared minimum of 20.

## What stays, what is added

The original research architecture stays, but the levels must be named
correctly. **Outer:** GPT-5.6-Sol + Codex harness supervises the whole
programme, keeps the ledger, watches progress and enforces boundaries.
**Inside:** the GLM controller chooses a scientific step; the Data Scientist
Harness exposes admitted literature, data-quality, feature and trainer tools;
a researcher/worker performs bounded work; the independent runner checks
results; the Archive preserves every attempt. Within one experiment batch,
the executable research Harness is fixed at version **H_t**. An older
Codex/GLM Responses adapter exists inside the project, but its use of the
Codex CLI does not make that GLM session the *outer* supervisor.

The addition is a **second, slower loop around H_t**. After a completed batch
or a documented blocking failure, the GLM controller may use the Archive to
propose a change to the research Harness: for example a better
data-acquisition tool, diagnostic, literature workflow or algorithm interface.
The outer GPT-5.6-Sol/Codex supervisor can surface a bottleneck and request a
review, but does not rewrite the controller's scientific proposal. Candidate
changes to either the outer research workflow or inner Data Scientist tools
must have separate version/hash and test receipts; they cannot silently change
the active experiment.
The researcher implements candidate changes in a separate workspace and
tests them. The supervisor checks permissions, provenance, cost, canary and
comparison validity; it does not pick the scientific idea. Only a passing,
versioned release becomes **H_(t+1)**, and only the next batch may use it.
The data/evaluation authority kernel (protected splits, scorer, budget and
rights) does **not** self-edit. An H_t-to-H_(t+1) improvement is reported as
a Harness-version effect, not automatically as model learning. The previous
H_t/control remains reproducible.

## Two harnesses and one independent measurement boundary

The **Supervisor Harness** is the outer GPT-5.6-Sol/Codex operating layer:
schedule and observe work, detect bottlenecks, assemble a factual input packet,
enforce rights/budget/split/canary gates, inspect receipts, and version releases.
It must be capable of suggesting that a research workflow is inadequate, but
must not quietly become the scientific controller or alter its proposal.

The **Controller Research Harness** is the inner GLM workbench: allowed Archive,
live source search and bounded public-source reading, Train-only data and feature probes,
algorithm design, cost estimates, and bounded task submission. It must give the
controller enough context and tools to choose a useful next step; a large model
with a narrow workbench is not a strong controller system. The researcher has
an execution harness in a separate sandbox. The independent runner/evaluator
and protected data are not tools owned by either model. Model strength and
harness strength are separate variables and must be recorded separately.

**Self-directed literature research is required, not a preselected paper list.**
The controller chooses its own search terms, examines returned metadata, chooses
which public sources to open, reads bounded text, follows discovered links when
useful, and records what was actually read before citing it or proposing a new
method. The trusted broker fetches and receipts the public source; the E2B
guest need not have unrestricted internet access. Reuse the existing
`data_scientist_harness/literature.py` and `broker.py` operations
`search_literature_live`, `read_public_source`, and `record_research` rather
than substituting the older frozen synopsis-only `search_public_literature`.
Those legacy operations already distinguish metadata search from actual page
reading; they are **not yet wired into the new A/B E2B controller cycle**.
The current reader admits bounded public HTML/text, not PDF full texts, so a
failed or paywalled read must be recorded as a limitation, not called a read
paper. No fixed paper-count quota or permanently closed algorithm catalog is
implied; each cycle still has explicit time/bytes/cost limits and archives all
queries, URLs, content hashes, read ranges, failures and subsequent decisions.

GLM weakness is **not established** by weak prediction scores or failed data
collection. Before replacing it, compare GLM with a GPT-5.6-Sol controller on
the same frozen allowed inputs, controller tools, time/cost ceiling, researcher
and scorer. Archive each first response and blind-review whether the proposal
was feasible, evidence-based, novel enough to test, and useful after bounded
Train-only execution. A better result is a new controller-model variant, not a
retroactive relabeling of previous GLM decisions.

## Host and trust layout (required for a live cycle)

```text
Trusted local/control host: GPT-5.6-Sol + Codex Supervisor Harness
  owns: scheduler, budget/rights ledger, protected splits, admission,
        independent runner/evaluator, immutable Archive
  sends a hashed allowed input -> Controller E2B sandbox A

Controller E2B sandbox A: GLM Controller Research Harness + scoped tools
  model inference is brokered remotely; no Tinker/provider key in the guest
  reads: allowed Archive, public sources, opened Train summaries
  writes: one frozen scientific decision/task order and source citations
  cannot read: sealed Dev/Final, raw grader output, provider credentials,
               researcher workspace, or a shared writable data mount
  sends the exact admitted order -> trusted broker -> Researcher E2B sandbox B

Researcher E2B sandbox B: bounded execution harness
  reads: only the approved task, selected public/Train inputs and scoped tools
  writes: code/artifacts/traces in its own run workspace
  cannot read: Controller A files, sealed Dev/Final, budget ledger, keys
  returns artifacts -> trusted broker -> independent runner -> allowed feedback
```

**A and B must be distinct E2B sandbox IDs and distinct microVMs**, not two
processes or users in one sandbox. The supervisor/runner stays outside both;
it is not a third model permitted to edit an answer. Only the trusted broker
transfers allowlisted, hash-bound messages. No shared writable mount, direct
A-to-B network channel, inherited provider keys or cross-role sandbox reuse.
The broker logs creation IDs, image/runtime hashes, role, network policy,
allowed file manifest, input/output hashes, process/timeout, provider cost and
terminal cleanup for both sandboxes. E2B documents a separate microVM for each
sandbox, but **distinct physical machines are not established** by sandbox IDs;
if physical-host separation is required, verify a deployment/placement guarantee
before claiming it. The current local scripted fixture proves none of this.

Candidate changes to the Supervisor Harness and Controller Research Harness
receive separate version numbers. The controller may propose either research
workflow change, the researcher tests it in a fresh B sandbox, and the trusted
supervisor admits a passing release only for the next fixed-Harness batch.
Protected scorer, split, rights and budget rules are outside co-evolution.
The experiment manifest records the full tuple
`(supervisor_harness_version, controller_harness_version,
researcher_image_version, controller_model_id, data_version,
evaluator_version)`; changing more than one element requires separate controls
before attributing a gain. `H_t` is shorthand for this frozen tuple, not a
single mutable prompt.

```text
Outermost: GPT-5.6-Sol supervisor + Codex harness (watch, gate, version, record)
             |
Fixed-Harness batch H_t:
  GLM controller -> Data Scientist tools -> researcher
      -> independent measurement -> Archive -> GLM controller
        ^                                             |
        +----------- allowed checked feedback --------+

Outer co-evolution after evidence:
  GLM controller proposes Harness change -> researcher implements/tests
  -> GPT-5.6-Sol/Codex supervisor admits or rejects
  -> publish H_(t+1) -> next fixed batch
```

## What is running versus what is only designed

| Piece | Evidence today | Claim boundary |
| --- | --- | --- |
| Existing Codex/GLM Data Scientist Harness | Has logged literature, Train diagnostics and CPU fitting tools; its broker still says Harness releases are human-directed, and a capability/algorithm proposal does not activate code. | Legacy research path, **not** proof of this new recursive architecture. Do not silently use its old output as a new controller/researcher round. |
| Controller/worker/Harbor components elsewhere in the repo | Existing bounded candidate execution and isolation code. | Not yet bound to this contract's controller decision, inner researcher task and supervisor return path. |
| New provenance and supervisor-state gate | `research_cycle_gate.py` binds synthetic facts → scripted decision → real local subprocess trace/output → review. `global_state_gate.py` adds a supervisor-owned append-only decision state, one active cycle and never-reused IDs. The current-source bootstrap canary is `-10`; `-11` passed only after rechecking `-10` and the global journal. Stale `-09` was rejected before its proposed successor was claimed. | **Fixture only**: no model authored the choice, local subprocess is not E2B/Harbor isolation, and no predictive evidence was produced. The new live entry must reuse this gate; it is not implemented yet. |
| Controller literature tool adapter and mailbox | `controller_tool_adapter.py` routes a host-observed controller sandbox identity to the existing Broker's live-search, bounded-read and research-record calls. `controller_mailbox.py` now reads only the host-numbered A outbox, requires an active supervisor cycle, claims a call before dispatch, delivers the bounded response only to A and records hashes or a terminal failure. Offline tests use separate A/B object-shaped sandboxes and a real Broker with a fake public transport. | Still an offline connection: no GLM/E2B guest tool call, actual public fetch or live A→B handoff yet. Duplicate IDs and a failed broker call cannot be replayed in one mailbox; the live runner must also enforce durable claim/restart and exact source/version checks. Metadata search is not paper reading. |
| Broker-only synthetic handoff | `broker_handoff.py` accepts the first bounded A-written synthetic order under the active global cycle, sends a hash-bound copy only to the observed B object, independently checks B's public-string hash, and sends only host-reviewed feedback to A. It preserves raw guest messages, rechecks them against claims before each downstream step, and archives terminal failures. Ten handoff tests plus one integrated mailbox→handoff→feedback test passed with separate fake A/B objects and an actual local broker using fake public transport. | Canary-only message connection: the admitted task is a zero-cost synthetic hash, not a general scientific order. There was no GLM-authored choice, real E2B execution, network-isolation proof or prediction result. A live runner must bind model/provider receipts, prove A/B isolation and validate a separate scientific order policy. |
| Dual-E2B parent accounting | The child now leaves the dispatched hold open. A trusted parent waits for process exit, verifies exact A/B sandbox IDs and kill acknowledgements plus no active Market RSI sandbox, then may conservatively settle at the upper bound. Offline tests include a real local subprocess; a separate local E2B 2.38.0 runtime passes dependency checks. | Not a new live E2B canary or provider invoice. Missing cleanup/account proof leaves the hold outstanding. The old network canary still blocks live dispatch. |
| Formal controller-led round | No passing end-to-end receipt yet. | Must be reported as **not started**. |

| Role | Decides / does | Cannot do |
| --- | --- | --- |
| Outermost supervisor (GPT-5.6-Sol + Codex harness) | Watches run health, source provenance, protected-data boundaries, budget and held-out admissions; gives the controller a factual allowed-information packet; validates or rejects researcher outputs and records why. Its exact model/session identity must be captured for live runs, not inferred from this document. | Pick the GLM controller's literature question, algorithm, feature, code edit or candidate harness revision; rewrite its plan; grade its own candidate on sealed Final. |
| Inner controller (GLM) | Reads the allowed archive and aggregate failures; chooses the next question, paper search/read, data investigation, experiment, code task and candidate harness change; writes hypothesis, expected evidence, cost bound and stop rule **before** execution. | Read sealed labels or raw protected tests; bypass the supervisor/runner; modify the frozen reference evaluator or budget ledger; change old attempt IDs. |
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
- **Every new round begins with a same-source canary preflight, not a remembered
  checklist.** `require_new_recursive_round` re-verifies the canary's full
  record and exact current gate/runner/worker source plus Python identity.
  An old, absent or mismatched canary blocks admission before a new run claim.
  `--bootstrap-canary` is only for a new zero-cost synthetic check. A fixture
  cannot authorize a live model, paid provider or sealed evaluation. The live
  adapter must add equivalent provider, dependency, sandbox-image, tool and
  cleanup identity checks before its first use and after each such change.
- The outer supervisor maintains one current global decision state. The cycle
  entry must check the append-only journal head against the exact
  `RESEARCH_STATE.md` hash, require no other active cycle and a fresh ID, and
  bind the claim to the current canary/source. Review or verified failure
  closes the exact claim. A decision-document revision is explicit and only
  allowed while idle. This is enforced in the synthetic runner now, but the
  live GLM/E2B entry is still blocked until wired and canaried.
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

E2B/Harbor are execution/evaluation infrastructure, not scientific
authorities. For a live two-agent cycle, distinct E2B sandboxes A and B are a
required role boundary; Harbor may run eligible tasks but cannot substitute
for A/B isolation. Before use, a zero-paid canary must prove different IDs,
no shared writable filesystem or direct channel, per-role network/credential
policy, exact image/runtime, real tool execution, hash-bound broker handoff,
timeout/cleanup and cost accounting. A negative canary must show that B cannot
read A's files or protected data and A cannot read B's workspace. Until those
adapters and the decision-to-execution binding exist, describe activity as
**outer diagnostics**, not controller-led rounds.

Next implementation gate: (1) freeze the two harness versions and allowed
message schemas; (2) bind a **real** controller response to the first fresh
decision claim; (3) run a zero-paid, distinct-A/B E2B isolation and cleanup
canary with positive and negative access tests; (4) prove the hash-bound order
executes only in B and bounded feedback reaches a second A decision. Until
each receipt passes, remain in the research lane and describe the fixture as
a fixture. Do not launch formal paid training or use sealed Dev/Final merely
to demonstrate architecture.
