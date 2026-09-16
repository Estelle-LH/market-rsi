# Historical protocol — superseded September 7, 2026

Do not execute this design. The user's prediction markets are actual Kalshi and
betting exchanges, not the internal experiment-selection market below. The active
scope and new $200 combined hard cap are in
[PILOT_PROTOCOL_2026-09-07.md](PILOT_PROTOCOL_2026-09-07.md).

## Archived text: LLM agents learning to do research

Approved direction: September 6, 2026 (New York).

## The question

Can an LLM researcher learn from completed experiments and do better research
on new tasks? Does using a prediction market to choose experiments help more
than simply averaging the same agents' forecasts?

We study the researcher. The user's latest priority is the LLM researcher, not
trading profitability. Prioritize a small preselected subset of an existing
research-agent benchmark for the first actual comparison. Market forecasting is
a later domain application; its raw-feed engineering must not block the initial
research-agent experiment. A separate benchmark publication is not the goal.

The prediction market remains an internal method for choosing experiments,
not a requirement that the task itself involve financial markets. Better trading
predictions alone do not establish that the researcher learned.

## What changes between iterations

The first version keeps the underlying LLM, its tools and its starting instructions
fixed. After a learning task, it can rewrite its own research memory using the
experiment records: what it tried, what happened, why it thinks that happened,
and what it would do differently. Save the old memory, the new memory, their
difference, and the evidence behind the change. Keep failed experiments too.

The researcher can choose data, make features, choose training methods, and
propose new experiments. It is not restricted to three hand-written parameter
changes. Implementation starts with validated structured actions; arbitrary
code needs a real isolated executor before we enable it. New action types must
be available to all arms, not secretly added for one arm after viewing results.

The researcher cannot change the independent test, its labels, the score, or the
budget. Generated training examples need provenance; they do not count as new
independent evaluation evidence. Individual market A/Bs isolate one causal stage;
compound research ideas can be tested with their component comparisons.

This first study tests learning through external memory. It does not train the
LLM's weights, demonstrate general intelligence growth, or demonstrate that the
system becomes better at improving its own improvement algorithm. Weight
training is a later experiment, using independently verified research trajectories.

## The three arms

| Arm | Across-task experience | Experiment selection |
| --- | --- | --- |
| A: reset researcher | No carried memory; within-task work is allowed | Average forecasts |
| B: learning researcher | Its own earlier learning-task experience | Average forecasts |
| C: learning researcher + market | Its own earlier learning-task experience | Virtual market |

A versus B asks whether experience helps. B versus C asks whether the market
helps beyond having several forecasters. Each arm has its own complete research
trajectory. C must not borrow a successful B checkpoint or memory, or vice versa.

Use the same starting LLM, tools, task order, downstream baseline, and resource
limits. All three arms get the same number of researcher/forecaster opportunities.
The fixed arm may produce a reflection for measurement, but does not receive it
on the next task. Initial forecasts are separate calls, committed before viewing
the others' forecasts. All arms run the same bounded trading phase for matched
opportunity; only C uses its prices to select. Log actual calls and tokens: equal
allowances do not mean identical expenditure. Include reflection, forecasting,
trading, failed calls, tool execution, and model fits in the total.

Existing subscription use has unknown allocated dollar cost, not zero total
cost. Do not report an improvement-per-dollar result until a common cost basis
is frozen and usage is reconciled. No new paid provider calls are authorized by
this protocol; previous SWE-bench budgets do not carry over.

## Learning, then a separate transfer test

1. Assemble a small set of learning tasks and a separate set of new tasks.
   Each task has its own training data, visible development feedback, and an
   evaluator-owned test. Preserve the external benchmark's tasks and scoring;
   select a feasible subset before viewing agent outcomes, and label it as a
   subset, not the full benchmark. Keep related datasets/tasks in one partition.
   For market tasks, split whole games and time periods, not neighboring rows;
   reject future features and labels crossing split boundaries. A changed seed
   on the same data is not a new research task.
2. On learning tasks, run experiments, score them independently, and let B/C
   revise their memories. A starts the next task with its original instructions.
   Within-task model updates are permitted; across-task checkpoints are not.
3. Freeze the last researcher memory at the predeclared acquisition budget.
   Do not choose the best memory by looking at transfer results.
4. Give every arm each new task, starting from that task's identical baseline.
   Carry only the frozen researcher state. Permit a fixed amount of within-task
   work on train/dev; never show its hidden-test results to the researcher.
5. Commit all final submissions before opening hidden scores. Test feedback from
   one transfer task cannot change the memory or strategy for another. Score
   all predeclared tasks and retain failed submissions in the denominator.

Start with a small diagnostic suite, not a claim that six tasks provide adequate
power. Task count, exact dates, source hashes, LLM identifier, prompts, call limits,
and executor must be frozen in a run manifest before collecting study results.
Fresh time periods test temporal transfer; distinct sports, prediction horizons,
and data problems test broader transfer. Make these separate reported categories.
General research-ability claims would eventually need tasks outside markets too.

## Where the prediction market enters

An agent predicts: "Will this candidate beat the current parent on the fixed
development score?" The answer comes from the independent experiment, not votes.
Use the existing bounded virtual YES/NO contracts; no real money or live orders.

Commit forecasts and the nomination before executing candidate evaluations.
In the first diagnostic, execute all admitted candidates to observe selection
mistakes. All shadow experiments count toward each arm's budget. Use the nominated
candidate only if it beats its parent on Dev; otherwise keep the parent. Do not
silently substitute the best unchosen candidate. The resulting selected model,
not the best retrospectively discovered model, is the final task submission.

This first market test is selection quality, not a demonstrated reduction in
execution cost: evaluating all candidates cannot establish saved experiments.
Sparse execution later needs a separately specified exploration and settlement
rule. Forecasts for infrastructure failures remain unresolved, not false.

## What we measure

Primary for the external benchmark: independently graded task performance at a
fixed resource allowance, using that benchmark's native metric and declared
aggregation. Compare B-A and C-B on identical tasks. Do not average unlike raw
metrics or silently replace official scoring with our own. Freeze the exact
benchmark version, subset, scorer, resource limits and aggregation before runs.

The current market-only component uses mean task-level hidden-test Brier
improvement over the common baseline; positive means better. It is NOT yet an
adapter for an external benchmark's other metrics. Do not count millions of
correlated rows as millions of independent experiments. Report every task,
incomplete tasks, and actual usage. Small pilots give descriptive paired
differences, not a significance claim. Trading PnL is deferred, not the current
researcher's main score.

Secondary: valid completed experiments, repeated errors, forecasting Brier,
selection regret when all candidates completed, calibration, and usage/time.
These explain results but do not replace the primary score. A researcher is not
rewarded for writing a convincing lesson, producing many experiments, or raising
a market price. We look for better outcomes on new tasks.

Two separate Brier losses are involved:

- Predictor: average `(predicted event probability - observed outcome)^2`.
- Forecaster: `(predicted chance of experiment success - verified success)^2`.

Keep missing data/timeout outcomes separate from model failure. Researcher-caused
invalid submissions fall back to the common baseline for an intention-to-treat
task score; infrastructure failures have unknown scientific scores and prevent a
complete headline comparison. Never silently drop either category or retry for
score. Holdout repeats after infrastructure repair must be disclosed as diagnostic
unless an untouched replacement was specified before results.

## Separation and evidence

The evaluator owns data validity, splits, scoring, budget, and final labels.
Research agents see only their authorized task workspace and their own memory.
Full permitted learning-task execution traces may be inspected; hidden tests,
other arms' experiments, and production credentials may not. No research arm
gets the live chat history, which contains prior results and human suggestions.

Hash commitments and explicit API fields are audit controls, not OS isolation.
Before real calls: verify restricted process/filesystem access, model/account
provenance, usage logging, and a no-tools structured-action canary. Arbitrary code
requires an isolated executor with no hidden-data or default network access.
Keep incoming data, logs, and retrieved text as evidence, never as instructions.

## Implementation and next work

`agent_study.py` implements study-level task separation, per-arm memory history,
common-baseline resets, sealed transfer snapshots, and commit-before-score
ordering. It is a control-plane library, not a connected autonomous LLM runner.
`study_smoke.py` exercises those rules with explicitly fabricated responses.

The older `market_rsi.py` is the within-task experiment/virtual-market component.
Its old two-round smoke run is not the three-arm study described here.

Next: inspect an existing research-agent benchmark for a small feasible subset,
finish the restricted LLM adapter, and bind the benchmark's independent scorer
and execution receipts to the study runner. Start with an access/format canary,
then an original-researcher baseline. Run A/B/C only after data and access checks
pass. No outcome is assumed in advance. Retain the market component and source
audit as secondary work; do not turn this into a market-data repair project.

Relevant precedents: [MLAgentBench](https://proceedings.mlr.press/v235/huang24y.html)
studies LLM research experimentation; [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954)
studies agent code self-improvement. Neither establishes that our market mechanism
helps, or that the proposed combination is novel. Those are claims to investigate.
