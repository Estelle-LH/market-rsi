# Round 1 v2: component fixes after the pilot

## Experiment design first

The scientific question is unchanged: can the same LLM researcher use independently executed
Train/Dev results to improve later research decisions, and does that improvement transfer to later
games? Reset, Archive, and Learn keep the same researcher, coder, tasks, scorer, and budget. Only
their memory differs.

The first run is treated as a pipeline pilot, not as evidence that RSI works or fails. The future
test remains sealed.

## What the pilot showed

- 21 selections completed; 20 retained persistence and one selected a new predictor.
- Of 13 scored learning candidates, one improved, seven tied, and five were worse.
- The one small Dev improvement did not transfer to the next game.
- Learn produced only one scored candidate in 12 learning opportunities, so Reset, Archive, and
  Learn were not compared on equal effective evidence.

## Component findings and fixes

| Component | Pilot failure | v2 rule |
|---|---|---|
| Researcher output | Eight Learn responses hit the 4,096-token limit; two more were unreadable. | Short JSON only, bounded fields, low reasoning effort, temperature 0.2, and exact failure codes. |
| Research guide | Unexecuted or diagnostic observations could become durable-sounding rules. | A guide revision may cite only an independently executed experiment with a numeric Dev score. |
| Opportunity allocation | Inspect and prediction shared the same two slots. | A task targets two scored candidates, allows one diagnostic, and has a hard cap of four research calls. |
| Failed calls | A format, coding, or sandbox failure could consume a candidate slot. | It consumes a total call but not a scored-candidate slot. At most one replacement opportunity exists. |
| Selection | Persistence won almost every task. | Keep the selector. It correctly blocked weak candidates; it is not expected to create improvement. |
| Transfer | The only small Dev gain disappeared on the next game. | Report per-game paired results and transfer separately; never call one Dev win improvement. |
| Provider timeout | One reaped local call left remote usage unknown and the reservation unresolved. | The runner now closes a verified local timeout as a failed call, charges the full reserved upper bound until an invoice replaces it, and never retries the same request. |

## Bounded v2 schedule

- 9 tasks: 6 learning, then 3 transfer.
- 3 arms per task: Reset, Archive, Learn.
- Target: 2 independently scored candidate experiments per arm-task.
- Diagnostic allowance: at most 1 inspect/reject action per arm-task.
- Total research-call cap: 4 per arm-task. A failed or unscored call does not fill a candidate slot,
  but it still consumes this cap.
- One selection call per arm-task.
- No automatic resampling, no score-targeted retry, and no reuse of a trial ID.
- The worst-case model and sandbox upper bound is USD 49.511264 under the USD 50 pilot cap.

## Verification completed

- Focused component tests: 108 passed.
- Full offline suite: 651 passed.
- The frozen local GLM tokenizer renders the v2 request with `Reasoning Effort: Low`.
- No paid live v2 call has been launched.

## Remaining gate before live v2

1. Materialize a fresh run ID and new scientific hashes. Never resume the old pilot with changed code.
2. Run one paid canary through researcher, coder, E2B, scorer, budget settlement, and cleanup.
3. Start the formal v2 only if that canary is fully terminal and no sandbox remains.
