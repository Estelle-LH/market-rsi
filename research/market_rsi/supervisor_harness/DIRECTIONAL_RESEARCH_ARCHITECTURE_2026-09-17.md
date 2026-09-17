# Directional Controller–Researcher architecture — 2026-09-17

Status: **local Docker B synthetic transport validated; GLM-led research not
yet admitted.** The user's later 2026-09-17 correction retires new E2B
connection tests. Fresh local canary `local-b-canary-deaa4549f9a34effb009`
passed 20/20 synthetic tasks and exact cleanup. Selected isolation probes
passed; none of this is a model result.
This supersedes the two-E2B, symmetric A↔B denial assumption in
`CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md`. Preserve that
contract and canary `-02` through `-04` as historical diagnostics; do not
reinterpret their failures as research results or use their IDs again.

## The actual trust and information flow

```text
TRUSTED LOCAL MAC
  GPT-5.6-Sol / Codex Supervisor
    ├─ global state, version and budget gates
    ├─ local broker: permitted tools, task handoff, event collection
    └─ independent evaluator + sealed Dev/Final
                  │
                  ├─ invokes A: GLM Controller through a brokered model session
                  │    A sees permitted B tool/events/artifacts and decides next task
                  │    A has no direct filesystem, paid key or sealed evaluator access
                  │
                  └─ Docker controls one local work container: B Researcher
                       B executes bounded research tasks and writes event receipts
                       B cannot read/write A's state or call A directly

Allowed: A → broker → B task; B → broker → A recorded results and trajectory.
Forbidden: B → A direct process/network/file access; B → local keys or evaluator.
```

“B → broker → A results” is an authorized, recorded return channel, not a
direct B→A privilege. A must be able to inspect B's permitted research
trajectory, including tool names, inputs/outputs or bounded summaries,
timestamps, errors and artifacts needed to choose a next step. Do not reduce
this to only a score or a small filtered feedback string. The broker excludes
secrets, raw protected-evaluation contents and unrelated local files. B's
events remain untrusted data; A's decisions remain separate from what B did.

The GLM model is invoked by the local broker; model output is not granted
arbitrary execution on the trusted Mac. The Controller Research Harness is a
broker-enforced tool interface and versioned prompt/context, not a process
with unrestricted local filesystem access. Only B's untrusted code may run in
the local container after its own admission. Supervisor is never placed in B's
container. If a future implementation
runs A-authored code, that code also needs isolation; this document does not
authorize executing it on the trusted host.

## Cadence and visibility

Start one B container for an admitted round and reuse it for bounded research
tasks. A may observe B's append-only event stream as work proceeds and issue
new instructions at explicit decision points. Do not recreate Docker on every
message or route every internal B tool call through A. Measure (a) sandbox
startup, (b) broker task handoff, (c) event publication and A read latency,
and (d) task execution separately. Display those timings and A/B event logs
on the localhost dashboard. Never claim live visibility for an uncaptured
event stream.

**P0 friction acceptance, declared before the live test:** with one persistent
B sandbox, make 20 small, distinct A→broker→B task handoffs and 20 matching
B-event→broker→A reads, excluding GLM inference and B task computation from
transport latency. Require zero lost/duplicated messages, zero timeout, p95
handoff latency at most 2 seconds, p95 event-visibility latency at most
2 seconds, and no single transport leg above 5 seconds. Record all raw
timestamps and the exact run version, not only the average. This is an
engineering responsiveness gate, not a market-prediction result. If it fails,
do not just raise the deadline: diagnose once, then redesign the placement or
communication path before a research round. Do not claim a guarantee before
this real one-sandbox measurement passes. The fresh local synthetic run passed:
20/20, no lost/duplicate/timed-out messages, handoff p95 28.78 ms and event
visibility p95 7.07 ms, with maximum legs 188.82 ms and 7.29 ms. This proves
only the synthetic local transport, not GLM choice or arbitrary B code.

## Replacement canary and admission gates

The zero-paid local fixture proved exact task/event hashes in one B container.
Before a GLM-led or arbitrary-researcher cycle, a fresh source release,
unique ID, protected state and model-authorship checks must additionally prove:

1. B has no paid keys, supervisor files, A context or sealed evaluator data;
   B cannot directly invoke or modify A.
2. A can issue a bounded task through the broker, observe B's real tool-event
   stream and read a completed result with matching hashes.
3. The broker logs both directions of the approved handoff, timing and errors
   without exposing protected contents. Paid model calls have a separate ledger.
4. Exact B container cleanup and a fresh container-list readback pass.

The old direct A→B and B→A HTTP probes are **not** the acceptance test for
this architecture. In particular, A→B access is an intended capability, not
a violation. The old two-E2B runner is retired for new paid dispatch. Do not
use old diagnostic outcomes to choose a reward, training data or model.

## Research claim boundary

This redesign changes execution plumbing, not the forecast benchmark. No
new prediction result, GLM-led round, full arbitrary-code isolation proof or empirical gain is
claimed. The three/five-season data gate, frozen objective before Dev,
independent evaluation and original $200 total budget remain unchanged.
The user's up-to-$5 connection-test permission is not a new global budget.
