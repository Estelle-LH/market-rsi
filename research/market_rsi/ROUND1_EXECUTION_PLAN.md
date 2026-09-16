# Round 1 execution plan

## What this round tests

Can the same LLM researcher do better on later, unseen market-prediction tasks
when it can remember its own executed experiments, and does writing an explicit
evidence-linked guide add anything beyond keeping the raw archive?

Polymarket US is only the data source. Changing the exchange is not the tested
idea.

The prospective-data boundary is `2026-09-07T16:08:41Z`. Data captured before
that time is diagnostic or historical input; it cannot be relabeled as an
untouched future Test result.

## Fixed comparison

All three arms receive the same nine tasks in the same order and have the same
model, prompts, token ceiling, wall time, coder, sandbox limit, scorer and
eligible rows.

| Arm | What carries to the next learning task |
| --- | --- |
| Reset | Nothing from earlier tasks. It still sees all experiment records created inside its current task. |
| Archive | Its complete proposal, score, failure and cost records from earlier learning tasks. Large raw rows, source text and event logs remain runner-owned and are referenced by hash rather than copied into every prompt. |
| Learn | The same records as Archive, plus its latest guide. Every guide revision must cite records it actually saw. |

Records never cross arms. Feedback from one transfer task is not passed to a
later transfer task. This keeps the three transfer tasks as independent checks
of the state frozen after learning.

## Exact schedule

1. Freeze six learning tasks followed by three later transfer tasks. Each task
   is a whole-game unit; no game may appear in more than one task or split.
   For this historical diagnostic pilot, a game must have at least 20 admitted
   rows and full-game persistence MSE of at least `5e-7`; this difficulty gate is
   fixed before any candidate/model call. The future untouched Test will use
   the first eligible games after the boundary and will not be filtered by score.
2. Materialize one common persistence baseline for each task.
3. For every task, run Reset, Archive and Learn in runner-controlled round-robin
   order. Each arm gets exactly two proposal responses.
4. Each proposal must name one changed causal stage: data, signal, predictor,
   objective or trading policy. The evaluation target, eligible rows and cost
   assumptions stay fixed.
5. Codex implements the declared proposal but cannot replace the research
   decision. Harbor/E2B executes it without network or hidden-data access. The
   independent scorer compares it with the common baseline on the same rows.
6. After the two results, the same researcher makes exactly one selection. A
   malformed, late or missing answer counts and falls back to the common
   baseline. There is no resampling.
7. After all arms finish task 6, freeze their learning state once. Then run the
   three transfer tasks without feeding transfer outcomes back into memory.
8. Freeze all transfer submissions before any Test artifact is opened. Test is
   opened once only after the full research loop is closed.

This is 54 maximum candidate executions and 27 selection calls. A proposal that
chooses inspection, rejects a broken measurement, fails formatting or times out
still consumes its one declared slot; it is not replaced to improve the score.

## Budget gate

The machine-readable declaration uses a fresh $50 pilot ledger and a 64k input
ceiling so later Archive/Learn prompts can carry the accumulated compact records. Its worst-case
upper includes every GLM proposal and selection call at the declared maximum
input/output tokens, every possible sandbox execution, setup allowance and any
other explicitly declared metered service. It must be at most $50 before the
runner can be bound.

Codex is paid through a subscription, so its calls do not pretend to be a zero
resource cost: count and duration are reported separately, while the dollar
allocation remains unknown. Reservations, terminal metering and invoices remain
separate numbers.

## Results to show the advisor

For each transfer task, report the paired improvement over persistence on the
same rows:

`improvement = MSE_persistence - MSE_candidate`

Then show:

- Archive minus Reset: whether retaining raw executed experience helps;
- Learn minus Archive: whether the evidence-linked guide adds value;
- calibration, missing predictions, failures, time, tokens and cost by arm;
- PnL after frozen spread, fees and latency as a secondary result only.

With only three transfer tasks, this is a pilot and a direction check. It is not
enough for a publication-level self-improvement claim. A later final result
still needs at least 20 untouched, distinct and complete `game_id` values. This
means 20 games, not 20 calendar days.

## Gates before any paid call

- Run `validate_protocol()` on the frozen Round-1 declaration.
- Create the `StudyState`, live `StudyRunner` and fresh budget from that exact
  declaration, then run `validate_study_binding()`.
- Separately pass collector provenance, chronological whole-game split, label
  materialization, scorer, process isolation, shared deadline and cleanup gates.
- Verify the runner shows no active claim, no prior charge/reservation and no
  Test access.

Only `study_runner.StudyRunner.tick` may create the next permanent claim and
dispatch it. The researcher, coder and host do not choose which arm runs next,
select a result on behalf of the model or open Test. Paid execution is one
runner-owned job at a time. Parallel subagents may audit code, data and reports,
but may not launch model or sandbox jobs.
