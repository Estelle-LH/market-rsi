# Directional Controller–Researcher architecture — 2026-09-17

Status: **user-confirmed design direction, not yet implemented or validated.**
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
                  └─ SDK controls one E2B work sandbox: B Researcher
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
with unrestricted local filesystem access. Only B's untrusted code runs in
E2B. Supervisor is never placed in B's sandbox. If a future implementation
runs A-authored code, that code also needs isolation; this document does not
authorize executing it on the trusted host.

## Cadence and visibility

Start one B sandbox for an admitted round and reuse it for bounded research
tasks. A may observe B's append-only event stream as work proceeds and issue
new instructions at explicit decision points. Do not recreate E2B on every
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
this real one-sandbox measurement passes.

## Replacement canary and admission gates

The next **zero-paid** fixture must prove the local broker preserves exact
task/event hashes and one-way access policy. The next **real** E2B canary,
only after fresh source release, budget, unique ID, state and account checks,
uses **one** B sandbox. It must prove:

1. B has no paid keys, supervisor files, A context or sealed evaluator data;
   B cannot directly invoke or modify A.
2. A can issue a bounded task through the broker, observe B's real tool-event
   stream and read a completed result with matching hashes.
3. The broker logs both directions of the approved handoff, timing, errors and
   exact provider cost without exposing protected contents.
4. Exact B sandbox cleanup and a fresh account-clear check pass. Unknown
   cleanup or metering fails closed.

The old direct A→B and B→A HTTP probes are **not** the acceptance test for
this architecture. In particular, A→B access is an intended capability, not
a violation. The old two-E2B runner is retired for new paid dispatch. Do not
use old diagnostic outcomes to choose a reward, training data or model.

## Research claim boundary

This redesign changes execution plumbing, not the forecast benchmark. No
new prediction result, GLM-led round, isolation proof or empirical gain is
claimed. The three/five-season data gate, frozen objective before Dev,
independent evaluation and original $200 total budget remain unchanged.
The user's up-to-$5 connection-test permission is not a new global budget.
