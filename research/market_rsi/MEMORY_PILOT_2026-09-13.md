# Three-round researcher-memory pilot

Status: implementation and synthetic checks; no new GLM round dispatched yet.
Authority: user's “go” after the proposed audit, larger chronological dataset and
three-round memory comparison. This is a separate preliminary experiment. The
original formal capture/provenance gates remain unchanged and unpassed.

## Question and fixed comparison

Does access to its previous research archive help the same GLM researcher make
better predictions over three rounds? One arm receives its own earlier tool
records, proposals, errors and consumed-Dev scores. The other starts each round
without its previous research records. Both receive the same expanding Train
data, common initial findings, tool capabilities and spending ceiling.
This changes context, not GLM weights. Human-written harness changes are not RSI.

Use the existing pinned GLM-5.3 through the actual Codex tool loop. No model
migration. Three sessions per arm, at most three candidate fits per session.
Per-session Tinker upper bound $8.44038144; per-arm ceiling $25.32114432;
combined maximum $50.64228864 inside the existing $200 experiment, not new money.
Actual metered cost is reported separately from reservations and worst cases.
Keep the existing final/repair buckets intact. No retry for score.

## Data schedule, declared before reading these objects

Only the `T12` file on each date below is included. These are recorded hour
objects, not complete market days. Dates were chosen by chronology/availability,
not by observed price movement. Every listed object must complete; no replacing
an inconvenient date. Whole-file hashes and byte counts bind the materialization.

| Round | Train | Dev, opened only after both submissions |
|---|---|---|
| 1 | August 26–28 | August 29 |
| 2 | August 26–29 | August 30 |
| 3 | August 26–30 | August 31 |

Later pilot test: September 10–12. Do not materialize or inspect those price
contents until both Round 3 submissions and the selection policy are frozen.
This pilot has only three later dates, not the 20 untouched sessions required
for formal promotion. We will not claim generalization or profitable RSI from it.
File-name availability alone does not prove no other historical exposure; bind
the checked exposure inventory and disclose any overlap before running.

Within each round's Train, use earlier files to fit and its latest file as an
opened chronological development check. Its data may be re-used. External Dev
is different: one evaluation per submitted model; after both arms finish that
round, it becomes Train. Never describe consumed Dev as untouched again.

## Fixed target and measurements

Reuse the controller's published rev6 direct-BBO price-change sampling contract
`25c420d2e5e79f6e1e5eea850127cbecb7d1c2b1471614d81996640b5b6808bb`:
causal 60-second lag feature; up-to-60-second backward-as-of future midpoint
change; strict label maturity/day purge. This variable-span target is NOT a
guaranteed exact-60-second executable return. Invalid/missing data are not zeros.
Keep all valid zero labels and the same eligible rows for every model.

Primary score: equal-hour mean MSE, plus absolute RMSE in price bps (1 bp =
$0.0001 per share), zero-prediction skill, per-date scores, paired improvement
against the same fitted baseline, IC/calibration, market-level concentration
and row availability. Overlapping rows and complementary outcomes are dependent;
do not manufacture IID confidence or count them as independent market trials.
PnL is not measured. Objective/row mask/normalization cannot change mid-run.

Candidate transformations and trainers will be frozen with the tool adapter
before any model session. The common baseline is one-feature no-intercept OLS,
fit on the same earlier data for each round. One candidate changes features OR
trainer versus its declared parent, not both. All proposals/failed fits stay in
the archive. No agent writes the grader, target, split, budget or hidden results.

The primary final comparison will use each arm's Round 3 submitted model, not
a hindsight best across different Dev days. Also report the zero and common OLS
baselines. Freeze explicit failure/fallback handling before paid dispatch.

## Minimal data adapter

Additive `memory_pilot/materialize.py`, outside the old frozen Data Scientist
Harness. Reuse the tested raw parser and exact sample kernel. Cache only derived
lag change, current midpoint, current spread, past quote count, label and an
anonymous market index. Each extra feature uses the decision row or earlier
quotes only. No future spread filters. Keep raw data on Linode; derived caches
can be stored in this project's local artifacts, never sent to hosted GLM.
GLM sees aggregate Train QA and scores only. Checks include kernel/moment parity,
feature finiteness, source hash/stat integrity and market identity continuity.
Reject incomplete files, never silently downsample or truncate.

Per object: 768 MiB worker + 256 MiB decoder, 600-second process limit,
2 GiB decoded limit. Fresh claimed output directory; no overwrite or duplicate.
Source, tests and annotated version must be published before empirical use.

## Research record — September 13

Observed problem: a one-hour fit's apparent benefit is concentrated in one
wide-spread market. Separately, prior researcher runs do not isolate the effect
of remembering earlier experiments. Do not assume either issue is fixed yet.

- Query `Reflexion language agents verbal reinforcement learning memory
  ablation`. Read [Reflexion](https://arxiv.org/html/2303.11366v4), section 3
  (actor/evaluator/archive loop), sections 4.1–4.2 (baseline and episodic-memory
  ablation). It motivates preserving feedback without updating LLM weights;
  its QA/code/environment results do not establish a financial-market benefit.
  We test archive access, not its separate self-reflection-model recipe.
- Query `TimeSeriesSplit time ordered equally spaced gap`. Read the
  [scikit-learn documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html),
  class description, `gap`, and expanding-Train behavior. Irregular event rows
  are not equally spaced, so split by declared chronological file/date blocks,
  with label maturity checks; do not randomly split rows.
- Reuse the raw-data research, exact parser/kernel and parity tests documented
  in `TYPED_RAW_RESULT_2026-09-13.md` and `CONCENTRATION_AUDIT_2026-09-13.md`.
  Polymarket quote midpoints are not execution prices. Missing original capture
  logs still limit any market-performance claim.
- For Codex wiring, checked the existing local route and official
  [MCP documentation](https://developers.openai.com/codex/mcp), tool allow-list
  and tool-timeout settings. Reuse the tested credential-isolated bridge;
  only a new committed broker route is needed. Tool transport must pass an
  actual-Codex scripted canary before real GLM calls.

Rejected for this pilot: changing the target after the audit, deleting quiet
rows by future activity, a simulator, or new broad harness features. Validation
of the new adapter and the memory comparison is still pending at this entry.
