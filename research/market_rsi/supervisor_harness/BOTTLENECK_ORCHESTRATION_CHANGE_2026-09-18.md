# Supervisor bottleneck orchestration change — 2026-09-18

Observed problem: the data-admission blocker needed a detailed orchestration
plan, but the Supervisor Harness did not require one. Earlier stalls and
dashboard visibility gaps showed that a prose instruction alone did not make
ownership, acceptance evidence or progress visible.

Research reuse: this is an operational control, not a new forecasting method.
It reuses the existing local `P0_DATA_ADMISSION_ORCHESTRATION_2026-09-18.md`
as the detail standard and the prior Supervisor review rule in
`RESEARCH_SUPERVISOR.md`. No new external literature claim is made.

Alternatives considered: documentation-only (insufficient to reject incomplete
plans); a new autonomous scheduling service (too much runtime machinery while
the live Controller runner is not ready); a small fail-closed plan checker plus
mandatory harness instructions (selected). The checker requires each step's
owner, dependency, expected evidence, verification, pass/fail handling and time
bound. It rejects a resolved claim without passing step receipts, intact file
hashes, and a separate whole-bottleneck check.

Validation: `test_bottleneck_gate.py` ran 5 tests successfully (valid dispatch,
missing owner, missing/tampered resolution evidence, cyclic dependencies,
unready external/dependency steps, and visible state/evidence paths).
`git diff --check` passed. This validates the Supervisor plan checker, **not**
an autonomous agent scheduler, a live GLM→B round, or a prediction result.

Limit: the current live experiment entry does not yet exist; operational
compliance still depends on the Supervisor calling the checker at delegation
and closure. Before a future live runner is admitted, wire the same check at
its task-dispatch/closure boundaries and test that it fails closed.
