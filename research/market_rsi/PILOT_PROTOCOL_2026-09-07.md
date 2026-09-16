# Kalshi research-agent experiment

Status: authorized for implementation and bounded paid execution on September 7,
2026. This document supersedes the internal-betting and MLAgentBench-first design.
Those prototypes and their fabricated test results are historical software tests,
not this experiment. Prediction markets here means real Kalshi/betting exchanges.

## What we want to learn

Does an LLM researcher make better experiments on later market data after learning
from its earlier experiments? Better means better independently measured outcomes,
not more persuasive explanations. The first experiment can find useful failures
or preliminary improvement; it cannot establish durable trading profitability.

GLM-5.3 is the research controller. It proposes questions, data transformations,
features, training methods and experiments, reads permitted results, and revises
its research instructions. Codex is the coding assistant, with the same model,
tools and limits for every arm. Tinker supplies GLM; Harbor manages independent
trials; E2B isolates candidate execution. Existing components are reused where
verified, not assumed ready merely because packages are installed.

## Budget

The user authorized $100–200 for the WHOLE new experiment. Aim for about $100;
$200 is the hard cap for all incremental provider charges combined, not $200
per agent, model, arm or round. Prior SWE budgets and artifacts do not carry over.

| Allocation | Maximum new charge |
| --- | ---: |
| Access checks, canaries and setup | $10 |
| Learning and development experiments across all arms | $120 |
| Final paired evaluation, protected from learning spend | $50 |
| Infrastructure repair, only after a recorded causal diagnosis | $20 |
| Total | $200 |

No new cloud instance, data purchase, subscription, live order, or automatic
credit purchase. Codex uses the existing ChatGPT login, not an API key. Record
subscription usage and unknown allocated cost separately; do not call it free
or claim an exact all-in economic cost without an allocation rule. No unbounded
API fallback or overage is permitted. E2B runtime and every paid failed call
count. Local work and the existing data server are separately disclosed.

For each job persist a unique permanent claim, maximum charge, provider/model,
source/input hashes, dispatch, actual returned token/runtime quantities, estimated
cost, provider-metered cost and (when available) invoiced dollars. Reservations
are NOT spend. Release the unused part on a verified terminal metering receipt;
an ambiguous dispatched job keeps its hold until reconciled. An invoice can
correct metered cost but never be added on top of the same job's metered cost.
Stop before a new job can exceed either its allocation or the global hard cap.

## First small comparison

Three separately maintained researchers use the same initial model and coding
assistant, initial task instructions, market universe, task order and ceilings:

- Reset: no experience from earlier research tasks.
- Archive: can read its own earlier raw experiment records.
- Learn: can read its own records and rewrite an evidence-linked research guide.

Archive versus reset measures access to experience. Learn versus archive measures
whether organizing/revising that experience helps. These are not internal markets.
Never share one arm's results, proposed features or successful code with another.

All arms inherit the same human-authored procedures in `COMMON_RESEARCH_START.md`.
Reset forgets NEW cross-task experience, not this shared starting knowledge.
Before scored work, freeze the text with `research_context.py`; every researcher
request must load and record the same initialization hash. The runner-only
`PRIOR_RSI_LESSONS_2026-09-07.md` records the earlier evidence and limitations.
Do not send that source ledger, historical reports or live chat to the models.
Record subsequent human interventions separately from agent-learned revisions;
never credit a human instruction change as autonomous self-improvement.

Start with five learning tasks and two later transfer tasks if audited coverage
supports them; at most three admitted experiments per arm per task. Freeze exact
dates, games, source hashes and limits BEFORE any research scores. Reduce the
task count only for demonstrated coverage/cost constraints before results, and
label the resulting study diagnostic. Random seeds and slices of one game are
not independent research tasks. Each task has its own earlier Train, visible Dev
and evaluator-only Test. Reset the downstream predictor for each new task.

This first comparison changes research memory/instructions, not GLM's weights.
Keep the Tinker training/operator infrastructure; do not claim weight-level RSI
from memory updates. A later weight-training arm needs verified researcher
trajectories and its own declared comparison. Training a market predictor inside
an experiment is different from training the LLM researcher.

## Research freedom and evaluation boundaries

Researchers may propose new features, derived training examples, alternative
trainers, hyperparameters and follow-up experiments. They can inspect their full
permitted training/Dev traces. They do not have to choose from a tiny fixed slate.
Generated examples retain provenance and are never new independent test evidence.

Require an input audit and allow `reject_measurement` with a diagnostic proposal.
Check actual executed inputs and current baseline behavior before diagnosing
difficulty. No old numerical curriculum thresholds or fixed operator shortlist
are imposed. Researchers may propose training losses and auxiliary diagnostics,
but those do not replace the frozen external scorer or justify retrospective
changes to outcomes. The prior lessons are revisable advice; access, integrity,
common evaluation and budget rules are not.

Each market A/B changes one causal stage: data, signal, predictor, objective or
trading policy. Compound ideas require component comparisons. The outer memory
comparison allows different research paths but holds the final scorer and resource
allowances fixed. Neither agent may change labels, masks, timestamps, fees, risk
limits, hidden data, evaluator code, or its own budget. No live chat history is
passed to a research model: it contains human hints and other experiments.

The first domain is one preselected Kalshi sports family, chosen by valid data
coverage, not profit. Use chronological whole-game splits, grouping related
contracts and games crossing midnight. All fitting and normalization use earlier
dates only. Historical dates can still be in an LLM's pretraining; record this
limitation and avoid claims that hiding a file removes pretraining knowledge.

Replay must carry snapshot state across files, check subscription sequence
continuity, invalidate gaps, and recover from fresh snapshots. Unknown windows
are unknown, not no-change labels. Freeze arrival-clock semantics, latency,
horizon, maximum staleness and eligible rows. No scoring from normalized quotes
alone if their observational validity is unproven.

## Immediate and final measurement

Give the researcher Train/Dev results only: valid completion, prediction error,
calibration, baseline comparison, simulated net PnL, trades, drawdown, concentration,
cost and failures. Use Brier for binary probability or MSE for return prediction;
freeze the actual target and primary metric before scored trials. Do not invent
a weighted scalar mixing unrelated quantities.

Use a fixed conservative market-taking replay first; quote changes do not prove
passive fills. Account for executable sides, fees, latency, depth, position limits
and no-overlap rules. Report prediction improvement separately from net profit.
Losing less is not profitability, and choosing no trades is not learning success.

Freeze the LAST permitted researcher state at the learning limit. Every transfer
task starts from the same task baseline with equal within-task opportunities.
Commit all final submissions before opening any hidden results; no final feedback
goes back to researchers. Report all paired tasks, failures and actual usage.
Short samples are descriptive. Promotion needs at least 20 untouched sessions
and the indicator-prediction-evals gates, normally beyond this pilot's duration.

## Execution order and acceptance

1. Permanent budget ledger and no-tools GLM canary; record exact model, tokenizer,
   package versions, raw output, returned usage and independent format checks.
2. Repair/audit source replay; create and freeze Train/Dev/Test task manifests.
3. Wire and verify the shared-initialization loader in the actual researcher
   worker; bind its hash to every request. Verify Codex and E2B isolation using
   harmless boundary tests; run a common
   baseline end-to-end. Do not expose hidden test data to coding or research tools.
4. Execute the three learning paths, preserving all proposals, failures and
   revisions. Run the final paired comparison from the protected allocation.
5. Deliver scores by task/arm, examples of learned changes, full cost reconciliation,
   reproducible artifacts, uncertainty and a clear recommendation for the next run.

Infrastructure failure is not a bad research score. Diagnose once, fix the causal
layer with tests and use a fresh ID without score-targeted retries. No duplicated
paid workers. If a critical data or access gate fails, preserve the budget and
report exactly what was tested and what remains incomplete.

## Current verified access (not research results)

- Tinker SDK 0.25.0; Cookbook 0.5.3; E2B 2.38.0; Harbor 0.17.1 locally installed.
- Read-only Tinker capability check returned `zai-org/GLM-5.3:peft:262144`.
- Codex CLI 0.153.4 reports ChatGPT login; coding isolation not yet tested.
- Existing `.env` contains Tinker/E2B credentials; values stay outside artifacts.
- September 1–6 normalized source directories exist; existence is not a replay pass.

Published GLM rates checked September 7: $4.86/M uncached input, $0.972/M cached
input, $12.15/M output, $14.58/M training tokens. Refresh before new paid jobs and
freeze the rate receipt. [Tinker source](https://tinker-docs.thinkingmachines.ai/tinker/models/).

## September 7, 09:17 UTC: task selection implementation decision

This is a human implementation rule added before any scored study, not something
the researcher learned. The common task schedule declares one to three experiment
opportunities. After those opportunities, each arm gets one GLM response to choose
its task submission from its own independently executed eligible candidates or
the task's frozen common baseline. This selection response uses the same task
token/wall ceiling, counts against the same budget, and cannot run code, propose
another experiment or revise the guide. Its raw answer, reasoning, choice and
usage remain in that arm's permitted record.

An invalid or late but independently terminal selection uses the common baseline;
there is no resampling or manual best-Dev selection. An ambiguous provider failure
does not become a completed choice: retain the pending claim/hold and investigate.
Only the owned learning history and current-task Dev evidence are available.
Earlier transfer-task feedback never enters a later task. All transfer choices
still freeze before any hidden scoring. The common initialization is unchanged.

The implementation is offline-tested with fake providers. No real task schedule,
actual selector inference, scoring-ready source or final result is created by
writing this rule. Live independent admission remains blocked.

## September 7, 11:23 UTC: unchanged-contract failure review

This prospective human implementation rule is recorded before any real scored
study. After a post-isolation failed candidate is independently confirmed terminal
with exact sandbox cleanup, its original failure remains one consumed experiment
opportunity. A trusted runner reviewer may separately record a causal judgment
that no source, runtime, data, limit or scientific rule needs changing. The runner
rechecks all original receipts before accepting that review. It does not infer
the cause merely from a candidate's own diagnostic output.

The next scheduled attempt uses a fresh ID and the original allowance. There is
no retry of the old response, replacement score, eligibility upgrade or budget
release. Review notes are runner-only; the researcher sees its original permitted
failure trace, not human troubleshooting advice. Invoices arriving later do not
rewrite the historical cost snapshot. Ambiguous remote jobs, missing isolation/
setup/cleanup and any source-changing repair remain blocked for separate causal
work and an explicitly recorded continuation policy. No automatic source migration
or repair is implemented. Tests use fabricated receipts; no real review occurred.

## September 7, 11:46 UTC: final numeric evaluation implementation

The first final worker covers the sealed transfer tasks, not the learning-task
hidden sets. Each transfer task runs its originally committed baseline and all
three already-selected arm submissions on identical hidden rows and the same
earlier Train data. It does not ask for a new researcher answer, change code or
choose an earlier researcher state. All choices freeze before any hidden file
is opened. Hidden labels/endpoints stay on the trusted host; isolated prediction
receives observations one at a time. No final result enters research memory.

The full final batch must fit the protected allocation and reporting-window
allowance before it begins. Every complete prediction log and exact sandbox
cleanup is rechecked before the single paired numeric report. A missing/failed
execution remains pending and unscored, not a zero, smaller row mask or repeat
answer. The next implementation needs separate final-failure handling. Accuracy
and net profit remain distinct; fees/execution/censoring must be independently
admitted before a PnL report. Source provenance, real task admission and end-to-end
wall enforcement still block live use. This rule and all tests are human-authored;
no actual hidden evaluation or researcher improvement has been measured.

## September 7, 12:06 UTC: final failure accounting

A fully verified post-isolation final failure is a consumed planned execution,
not a successful prediction or automatic zero score. Its observed trace and costs
remain recorded. The same trusted unchanged-contract causal-review rule permits
only the next originally planned job; it does not repair code or repeat a final
answer. Uncertain creation/command/output/cleanup and changed sources stay blocked.

The report keeps all planned transfer tasks, with null for any unavailable paired
score and explicit counts of successful, failed, pending and unstarted executions.
Available pairs may be reported as incomplete diagnostics, not a whole-study
winner or an aggregate over only successful tasks. Review notes and final results
never enter the researcher's memory. This rule is recorded before any real scored
study; all verification tests use fabricated data and provider receipts.

## September 7, 12:27 UTC: unchanged-limit phase admission

Before each next worker stage, check that its original full allowance and the
remaining planned stages fit the fixed report deadline. Slow preparation must
not cause a late new dispatch. Keep any already-created claim, response and cost;
do not replace it, shorten scientific limits, resample or silently mark the task
completed. A claimed but unstarted later phase remains pending/unscored.

Coder identity checks and generation share one request deadline, with separate
process reaping accounted for in the outer envelope. This prospective human
implementation does not establish a hard whole-step OS bound: filesystem/setup
work, nested process ownership and the final scorer still require that review.
No real scored study has started and no revised positive live path was invoked.
The common initialization and scientific target/risk/data conditions are unchanged.
