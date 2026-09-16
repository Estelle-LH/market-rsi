# Market RSI research supervisor

This is an operational layer around the versioned Data Scientist Harness. It
does not change an experiment, let the controller see sealed data, or turn
human harness edits into model self-improvement. Preserve detailed machine
traces elsewhere. This page is intentionally short enough to use during work.

## Before each work block

Read `RESEARCH_STATE.md`. Pick the cheapest next action that tests the current
question or removes its direct blocker. State the hypothesis, expected evidence,
time/cost bound, and stop condition before acting. Order choices by: direct
test; removal of a direct blocker; result quality; important uncertainty;
cleanup. Do not make cleanup the main branch without evidence that it blocks
the first four. Keep experiment definitions, data and evaluation gates from
`AGENTS.md` and the published release; this supervisor cannot waive them.

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

The existing scheduled `market-rsi` task performs a supervisor check about
every two hours. Give the human one short result-first digest on that cadence,
even if the honest status is "no meaningful result"; report a material failure
or needed decision sooner. This periodic digest is not permission to poll
expensive providers or repeat an unchanged diagnostic experiment.

## Hard boundaries for the current research

- A Train-only MSE reduction is not an unseen-date result. A support/coverage
  audit, a successful canary and code written are not prediction improvement.
- Freeze target, row mask, information cutoff, objective and reward before
  looking at a held-out comparison. Compare same rows with a strong ordinary
  baseline; preserve all attempts, not only the winner.
- The old iCloud copy is an archive. The local-only migration removed the
  execution blocker; do not spend another work block perfecting iCloud sync.
- P0 is five-season historical-data admission as defined in
  `P0_FIVE_SEASON_DATA.md`. Interrupt a proposed formal model run that uses
  only the 2024 feasibility cohort. Free source inventory and bounded data
  acquisition are on the critical path; a larger dataset is not a model gain.
- Do not create a new paid process until the exact published harness, local
  ledger, run-ID claim and budget gates pass. This protocol is not spending
  authorization.
