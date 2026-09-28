# Outer research supervisor harness

当前全局结构先看 [`../ARCHITECTURE.md`](../ARCHITECTURE.md)。本文保留 Supervisor Harness 的细节和历史 canary 说明；带日期的旧 E2B 设计不再代表当前生产路径。

The user-supplied charter is preserved byte-for-byte in
`USER_SUPERVISION_CHARTER_2026-09-16.txt` (SHA256
`c0b103a4299778c31db51d9a88955392b528684b6ce5b3ee091d83fe1567d296`).
`RESEARCH_SUPERVISOR.md` translates it into a short operating protocol for
Market RSI; `RESEARCH_STATE.md` is the replaceable compact decision state,
while `HUMAN_PROGRESS.md` and `HUMAN_INTERVENTIONS.md` are append-only human
records. The project's `AGENTS.md` and the active `market-rsi` scheduled task
point here, so the protocol is read at each new work block.

`P0_FIVE_SEASON_DATA.md` is the current supervisor gate: the one-year pilot
cannot become a formal five-year benchmark until source coverage and admission
are verified. This is a decision gate, not a claim that five seasons were found.

The current role split is summarized in `../ARCHITECTURE.md`: the outer Codex
Supervisor owns authorization, version, state, budget and evidence; the inner
GLM Controller chooses scientific steps through a bounded tool interface; a
future Researcher B executes only admitted work in one local Docker container;
and an independent trusted runner measures. The earlier two-E2B design in
`CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md` is historical. The
later local-B direction supersedes it, and neither synthetic transport nor a
Controller D0 response is a prediction result.

This is the *outer* Codex research supervisor, not the GLM experiment's
`data_scientist_harness`. It does not change frozen scientific code, its
published release, the $200 cap, or sealed evaluation boundaries. Research
results still require an actual same-row experiment and independent evidence.

## Fixture gate

The active responsibility split, exact round sequence, claim limits and
implementation status are in
`CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md`. The zero-paid
provenance canary is `run_research_cycle_fixture.py`; its gate is
`research_cycle_gate.py`. A passing fixture is not a model-authored round or
an E2B/Harbor isolation test.

The runner now requires `--prior-canary PATH` for every non-bootstrap fixture
cycle and `--global-state-root PATH` for every fixture cycle. Only
`--bootstrap-canary` may create the first zero-paid proof. The gate checks the
prior complete record against current gate/runner/worker/global-state source
and Python runtime before creating a new cycle. The supervisor-owned journal
pins the exact current `RESEARCH_STATE.md`, serializes one active cycle and
forbids ID reuse. Its current local path is
`artifacts/supervisor-global-state-20260917-01/`. A deliberate change to
`RESEARCH_STATE.md` needs `global_state_gate.py --revise-decision REASON`
while no cycle is active; otherwise the runner fails closed. Crash recovery
requires verifying the exact process has ended before closing the active
claim as failed.

Current-source zero-paid example: `research-cycle-fixture-20260917-10`
bootstrapped, then `-11` used it as preflight and advanced the same global
journal. After a source change, older `-09` was rejected before creating
`-10`; its earlier result remains preserved but is stale as a new canary.
All live/paid evidence modes still fail closed until their own adapters and
canaries are implemented; this fixture never opens Dev/Final.

`controller_tool_adapter.py` provides a host-side, role-bound route to the
existing Data Scientist Broker's live search, bounded public read and
actual-reading record operations. A real-broker offline integration test
passes with a fake public transport. The new GLM/E2B tool channel,
broker-only A→B transfer and effective network isolation have not passed a
live canary; the adapter alone does not authorize paid execution.

The E2B canary now keeps a dispatched budget hold open inside its child.
The trusted parent waits for that exact child to exit, checks both role IDs,
their kill acknowledgements and the account's active Market RSI listing,
then records an **uncertain upper bound, not an invoice**. If any evidence is
missing, the hold remains unresolved and a new paid launch is blocked. This
post-exit sequence passed offline tests, including one real local subprocess;
it has **not** passed a new live E2B canary. The live entry remains explicitly
blocked because the old blanket-deny network probe did not establish the
required role-specific isolation. A local-only `runtime-e2b-py312` now has
the pinned `e2b==2.38.0` SDK and passed dependency/runtime checks, without
touching the Tinker runtime or iCloud archive.
