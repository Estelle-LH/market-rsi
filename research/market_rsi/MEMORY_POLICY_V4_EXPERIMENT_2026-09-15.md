# Market RSI memory-policy v4

## Question

Does the controller do better when it starts each round with no memory, its full
own-arm archive, or a compact structured summary of its own earlier rounds?

## What changed after v3

V3 stopped before Round 3 submission because the controller spent all 65,536
output tokens on research. V4 changes only the shared harness: ordinary research
cannot spend the final 16,384 output tokens, and terminal mode starts with 32,768
tokens remaining or four tool calls remaining. In terminal mode the model must
call `submit_candidate` itself. The runner never guesses a decision from prose and
never resamples a paid answer.

All three arms receive the same repair. The target, eligible rows, controller
model, tool and trainer libraries, fit limits, seed, number of attempts, number
of rounds, Dev metric, and Final rule stay unchanged.

## Fresh evidence

V4 does not reuse any v3 checkpoint, controller memory, score, plan, or trial.
It excludes every previously opened source, including v2 Dev T22/T23 and v3 Dev
T04/T05. A score-free admission checked 39 later captures and selected exactly
3 Train, 8 rolling Dev, and 20 Final sessions across four UTC dates. Admission
computed no target statistics, fit no model, and called no provider.

## Run and stop rules

- Run eight paired rounds. In each round all arms use the same accumulated Train
  data and the same newly opened Dev session; only own-arm memory differs.
- Use the Round 8 submitted model for the untouched 20-session Final. Do not pick
  a hindsight-best round.
- Candidate fits use 6 GiB/480 seconds. Mandatory refits use 8 GiB/600 seconds.
  Do not subsample. Stop if cumulative selected Train observations exceed ten
  million.
- A complete fresh/archive/compact block must fit the remaining USD 200 global
  cap before it begins. Reservations are not spend; metered and uncertain costs
  remain separate.
- Preserve valid low scores, lack of improvement, model errors, and timeouts as
  outcomes. Retry only a pre-result infrastructure failure after one cause is
  identified, the affected layer is fixed, tests and canaries pass, and a fresh
  permanent ID is used. If a failure happens after scores are opened, invalidate
  the run and use fresh unopened evidence.

This hourly prediction experiment does not claim profitability or general RSI
improvement. Its result is limited to the memory-policy comparison under the
frozen prediction-MSE setup.
