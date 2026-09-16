# Market RSI formal run — September 8, 2026

## What ran

GLM-5.3 was the researcher inside the Codex controller harness. It could inspect
Train summaries, read its own Archive, search the frozen public literature
catalog, write candidate algorithms, and send them to isolated E2B Train-CV
execution. It could not see the current Dev labels or the unopened Transfer set.

The completed Round 3 continuation started from the model selected after the
earlier Round 2 result. It used 13,943 cumulative Train rows. The reusable
Train-CV split contained 11,611 fit rows from 88 games and 2,332 evaluation rows
from 10 different games. The final sealed Dev contained 2,400 rows from 8 games.

## Round-by-round record

This three-round run used the old target: predict the next quoted midpoint at
roughly a 60-second horizon. It is separate from the later five-minute-objective
formal Round 1.

### Round 1 — test whether top-of-book depth beats midpoint persistence

- **What the controller saw:** 6,000 labeled Train rows and a label-free Dev
  catalog. The reusable Train-CV slice had 897 rows from 9 games; sealed Dev had
  1,443 rows from 5 games.
- **What it did:** GLM-5.3 used 12 turns and 18 logged tool calls. It read the
  research guide, harness profile and empty prior Archive; listed and inspected
  the algorithm catalog; inspected several Train pages; ran one public-literature
  search; wrote two candidates; and executed both in isolated E2B sandboxes.
- **Candidates:** `mid_baseline_v1.py` exactly matched persistence on Train-CV.
  `microprice_ridge_v2.py` added a ridge-fit microprice/depth correction, but its
  equal-game MSE rose from `3.2979872318e-7` to `3.4831690322e-6`, or
  **-956.15% relative skill**.
- **Decision and Dev:** the controller rejected the harmful correction and chose
  `mid_baseline_v1.py`. On sealed Dev, candidate and persistence both scored
  `7.7124485597e-7`, so the improvement was **0.00%** with full coverage.
- **What this exposed:** the target was so close to the current midpoint that a
  learned correction mostly added noise. One Train-CV day was also too narrow to
  say whether a signal was stable.

### Round 2 — try a smaller, regularized queue adjustment

- **What the controller saw:** the prior Archive plus 7,513 cumulative Train
  rows. The fixed Train-CV slice had 1,513 rows from 6 games; sealed Dev had
  1,500 rows from 5 games.
- **What it did:** GLM-5.3 used 14 turns and 22 tool calls, including two public
  literature searches, nine Train inspections, three candidate writes and three
  isolated Train-CV executions.
- **Candidates:** persistence scored 0.00% skill. `queue_delta_ridge_v1.py`
  reduced Train-CV MSE from `8.2127547521e-7` to `8.1392751103e-7`, a
  **+0.8947%** improvement. `queue_tilted_ridge_v2.py` produced exactly the same
  score as its parent because its extra tilt collapsed to zero.
- **Decision and Dev:** on the tied score, the controller chose the simpler
  `queue_delta_ridge_v1.py`. Sealed Dev MSE fell from `7.2916666667e-7` to
  `7.1462884492e-7`, a **+1.9938%** relative improvement with full coverage.
- **What this exposed:** this was a real but small one-period gain. Train-CV still
  covered only one day, and the runner did not yet explicitly label identical
  predictions as a no-op.

### Round 3 — check whether the Round 2 gain continues

- **What the controller saw:** the Round 1–2 Archive and 13,943 cumulative Train
  rows. The then-current split used 11,611 fit rows from 88 games and 2,332 CV
  rows from 10 games; sealed Dev had 2,400 rows from 8 games.
- **What it did:** GLM-5.3 used 14 turns and 19 tool calls, including two public
  literature searches, six Train inspections, three candidate writes and three
  isolated Train-CV executions.
- **Candidates:** `mid_persistence_v1.py` scored 0.00% skill.
  `imbalance_drift_v2.py` made MSE **5.87% worse**. The guarded
  `temporal_continuation_v3.py` fell back to a zero adjustment and therefore
  produced the same predictions and score as persistence.
- **Decision and Dev:** the controller rejected the harmful imbalance model and
  selected `temporal_continuation_v3.py`. On sealed Dev, both candidate and
  persistence scored `1.0833333333e-6`, so improvement was **0.00%**.
- **What this exposed:** the CV day was unusually quiet: only 8/2,332 rows moved,
  versus 77/2,400 on the following Dev day. The controller made a reasonable
  decision from unrepresentative feedback. The harness, not just the algorithm,
  had failed to show it enough time regimes. It also again allowed a more complex
  candidate with predictions identical to persistence.

### Harness problems found across these rounds

| Problem | Why it matters | Status after the run |
| --- | --- | --- |
| Objective selected before objective research | The 60-second label was 95–97% unchanged, leaving little useful learning signal | Replaced by a separate, pre-Dev objective-discovery phase; the later study froze a five-minute window target |
| One-day Train-CV | A quiet or active day could determine the choice by accident | Changed to a fixed three-day suffix with whole-game, strictly ordered splits |
| No day-level robustness | Aggregate MSE hid whether gains held across dates | Added per-day improvement, median day, worst day and positive-day count as diagnostics |
| Cross-midnight games | The same game could leak across time partitions | Fixed by keeping whole games and omitting boundary-crossing games |
| Restarted model tool calls | An abandoned partial call could look like a duplicate | Adapter now accepts one restarted complete call but rejects true duplicates; raw events remain logged |
| Lost E2B stderr on nonzero exit | Infrastructure and model-code failures could not be diagnosed | Runner now preserves exit code, stdout and stderr |
| Identical-prediction candidates | Renames or inert changes could be mistaken for progress | Exposed here and again in the five-minute Round 1; prediction-digest no-op rejection remained a required gate before a new formal round |

The main lesson is not that the controller failed to search. It did search,
write and execute models in every round. The weak point was the research harness:
the old objective was too flat, the validation window was too narrow, and the
runner did not yet distinguish a genuinely new predictor from an inert rewrite.

## Results

The earlier Round 2 continuation selected `queue_delta_ridge_v1.py`. Its one-shot
sealed Dev result was **+1.993758% relative MSE improvement over persistence** on
1,500/1,500 rows from 5 games: equal-game MSE fell from
`7.291666666666693e-07` to `7.146288449208957e-07`, an absolute reduction of
`1.45378217457736e-08`.

Round 3 found a different, much quieter period. Three candidates were executed
on Train-CV:

| Candidate | Train-CV result vs persistence |
| --- | ---: |
| `mid_persistence_v1.py` | 0.00% |
| `imbalance_drift_v2.py` | -5.873643% |
| `temporal_continuation_v3.py` | 0.00% |

The controller rejected the harmful imbalance correction and selected
`temporal_continuation_v3.py`. On the one-shot sealed Dev it completed
2,400/2,400 predictions with zero failures and scored **0.00% relative MSE
improvement**: candidate and persistence both had equal-game MSE
`1.0833333333333322e-06`.

The direct finding is simple: the Round 2 gain did not continue into the next
time period. In Round 3, adding a correction hurt on Train-CV; the best validated
choice was to fall back to persistence. This shows useful controller behavior,
but not repeated performance improvement.

These are prediction-error results only. They do not include fills, fees,
slippage, PnL, or a profitability claim. Transfer/Future Test remains unopened.

## Repairs made during the run

Three runner problems were found and preserved under failed permanent IDs:

1. A date-based Train-CV split could put a game that crossed midnight on both
   sides. The splitter now keeps whole games and requires strict time ordering.
2. GLM sometimes abandoned an unfinished tool call and started a complete one.
   The adapter now accepts only the restarted complete call while still rejecting
   real duplicate arguments. The raw provider response remains in the audit log.
3. The E2B SDK reports an ordinary nonzero process exit as an exception. The
   candidate runner previously kept only the exception name, losing stderr. It
   now preserves the exact exit code, stdout, and stderr. No failed run ID was
   reused.

All 133 offline tests pass after these repairs. Final validation confirmed the
source manifest, Archive hash chain, lifecycle ledger, and full Dev coverage.
There were zero active E2B sandboxes after completion.

## Cost

At completion, the experiment ledger reported **$11.673435002 effective
provider cost out of the $200 cap**. Two later diagnostic harness canaries added
`$0.314656672`, bringing the current total to **$11.988091674** and leaving
**$185.711908326 available** after effective cost and current holds. The separate
`$2.30` reservation total is not reported as spend. Provider invoice
reconciliation is still incomplete.

## Evidence

- Round 2 score:
  `artifacts/archive-formal-self-improvement-continuation-20260908-02/rounds/round-02/sealed-dev/score-receipt.json`
- Round 3 decision:
  `artifacts/archive-formal-self-improvement-continuation-20260908-04/rounds/round-03/workspace/submitted-decision.json`
- Round 3 score:
  `artifacts/archive-formal-self-improvement-continuation-20260908-04/rounds/round-03/sealed-dev/score-receipt.json`
- Round 3 finalization:
  `artifacts/archive-formal-self-improvement-continuation-20260908-04/rounds/round-03/finalization.json`
- Tool-protocol failure diagnosis:
  `artifacts/archive-formal-self-improvement-continuation-20260908-02/rounds/round-03/failure-diagnosis.json`
- E2B evidence-loss diagnosis:
  `artifacts/archive-formal-self-improvement-continuation-20260908-03/rounds/round-03/failure-diagnosis.json`

Because the scientific source changed during repairs, these continuations must
not be presented as one pristine fixed-code study. The inherited checkpoint and
unopened Dev boundary are hash-bound, but each repair starts a new H0 study ID.

## Post-run harness finding

The Round 3 controller was not given a representative Train-CV period. The old
split used only September 5, where just 8 of 2,332 rows moved (0.34%) and the
persistence MSE was `6.08e-8`. The next sealed Dev day, September 6, had 77 of
2,400 rows move (3.21%) and persistence MSE `1.08e-6`. On the feedback it saw,
falling back to persistence was reasonable; the feedback window itself was too
narrow.

The harness now uses a fixed three-day Train-CV suffix, chosen without looking
at candidate scores, while preserving strict time order and whole-game
isolation. On the same already-open Round 3 Train data this would use 7,513 fit
rows from 73 games and 6,307 CV rows from 23 games across September 3–5; two
boundary-crossing games are omitted. Fifty-five focused controller, lifecycle,
and sealed-Dev tests pass; the final full offline suite passes 747/747. This is
an offline source change only, not a new
performance result. A future paid run must therefore start under a fresh H0 ID
with a genuinely unopened Dev period; September 6 cannot be scored again.

The diagnostic canary `controller-harness-multiday-canary-20260908-01` then
verified this source change end to end. GLM-5.3 used 8 turns and 14 logged tool
calls, and the runner executed two candidates in isolated E2B sandboxes on the
fixed 2,823-fit-row / 2,991-CV-row split. Its first correction was 47.38% worse
than persistence, so it wrote a second candidate, selected persistence, and
finished with no pending execution. This is harness evidence, not a research
score: no sealed Dev or Transfer set was opened. Both sandboxes were removed.
The canary raised total effective provider cost from `$11.673435002` to
`$11.810483176`.

The scorer was then extended to report whole-game day robustness without
changing the primary aggregate equal-game MSE. A second fresh diagnostic canary,
`controller-harness-temporal-metrics-canary-20260908-01`, used 8 turns, 16 tool
calls and three isolated candidate executions. The controller selected a
candidate with +0.99% aggregate Train-CV improvement, positive results on 2 of
3 days, median day improvement +0.12%, and worst day -0.89%; its submitted
evidence explicitly used those day-level checks. This is harness evidence, not
a research score: no sealed Dev or Transfer set was opened. All three sandboxes
were removed, no execution remained pending, and total effective provider cost
became `$11.988091674`.

No new formal score was started after these repairs. September 6 has already
been opened once, while September 7 and later belong to the precommitted
Transfer population. Reusing September 6 or borrowing from Transfer would make
the next result invalid. The next honest formal round therefore waits for a new
predeclared learning/Dev schedule with an unopened later period.
