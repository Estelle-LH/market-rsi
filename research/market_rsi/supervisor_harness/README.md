# Outer research supervisor harness

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

The user-corrected role split is
`CONTROLLER_RESEARCHER_SUPERVISOR_CONTRACT_2026-09-17.md`: supervisor watches
and gates, controller chooses each scientific step, inner researcher executes
in an isolated environment, and an independent runner measures. This is a
written operating contract with a synthetic provenance canary, not yet a
verified model-led end-to-end implementation.

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
