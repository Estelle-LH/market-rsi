# Architecture

## Goal and published boundary

Market RSI studies whether an automated researcher can improve its predictions
and its research process through verified experimental feedback. The system
tracks three change types separately: a prediction recipe (**C**), a researcher
policy (**R**), and a research-side harness/tool policy (**H**). Co-evolution means
that reviewed R/H versions can influence later scientific decisions, alongside
the ordinary candidate-development loop.

Public main includes the shared native engine and a reviewed earnings adapter
with offline tests. Later private experiment checkpoints and their reported
scores are different artifacts. Start with the [offline quickstart](QUICKSTART.md);
the [reproducibility guide](REPRODUCIBILITY.md) lists what is still needed to
rerun the empirical experiment.

The current experiments forecast financial-statement targets from point-in-time
filings; they do not measure trading returns. Their separate baselines, report
provenance and prospective protocol are in the [experiment index](experiments/README.md).
The [earnings task scope](../benchmarks/earnings/README.md) separates this task
from future earnings-surprise or trading evaluation.

The opened-Train NFL 300-second trade-VWAP-change diagnostic remains a legacy
task and source-compatibility path. Its trade prices are not executable quotes.

## One round, five logical roles

The **Controller** receives reviewed feedback, memory, history, a candidate pool,
and source context, then chooses the next scientific action. The **Author**
implements that decision as a versioned prediction recipe or R/H source/test
pair. The **Worker** runs the admitted experiment or matched capacity replay.
The **Independent Reviewer** reviews input, source and results. The trusted
**Supervisor runtime** coordinates stages, checks bindings and limits, and
records the result for the next input.

These are logical responsibilities rather than a fixed number of models or
machines. Account calls return structured text; trusted adapters decide what
can be written or executed. Model responses do not become arbitrary host
commands. Actual model and runtime identities belong in each run's bindings.

A complete research cycle uses seven durable stages; an invalid or rejected
proposal can close before execution or scoring:

```text
input → controller → implement → source_review → execute → result_review → reconcile
```

`reconcile` produces a new five-part bundle: `feedback`, `memory`, `history`,
`pool`, and `source_context`. The next `input` consumes that exact bundle and
its hashes. Process failures and resource/timing observations travel with the
history; scientific findings and candidate/capacity decisions travel with the
feedback. This makes delivery inspectable; better decisions still require
experimental evidence.

## Two development loops inside one protected runtime

```mermaid
flowchart TD
  subgraph Native[Protected native runtime: admission, accounting, review, task and scorer]
    I[Verified input and selected R/H hook outputs] --> D[Controller decision]
    SC[Candidate source review] --> E[Bounded prediction worker]
    E --> RC[Paired score and result review]
    SH[Capacity source and scope review] --> T[Matched parent/child replay]
    T --> RHReview[Independent capacity effect review]
    F[Reconcile feedback, memory, history and selected versions] --> I
  end
  subgraph Versions[Versioned research-side proposals]
    C[Prediction recipe C]
    RH[Child version: one R or H hook]
    Selected[Selected R/H pair]
  end
  D -->|prediction| C
  C --> SC
  RC -->|KEEP or REVERT; retain evidence| F
  D -->|researcher or harness| RH
  RH --> SH
  RHReview -->|accept child| Selected
  RHReview -->|reject; retain parent| Selected
  Selected --> F
```

**Prediction route (C).** A candidate names its actual research parent and the
comparison incumbent. The author creates source-bound material; review admits
the fixed worker operation. Results compare the candidate, parent, incumbent
and ordinary reference on identical rows. `KEEP` updates the prediction
incumbent; `REVERT` retains it. Failed or unscored candidate attempts can return
`UNCHANGED`, also retaining the incumbent. The archive preserves failed candidates
and reviewed findings. A separate research-credit route can retain useful branches
for further exploration without declaring them the best predictor.

**Capacity route (R/H).** The Controller selects one researcher or harness
component, triggering evidence and a named expected effect. The author writes
a fresh versioned source/test pair. The reviewed child is tested alongside
the selected parent on frozen success, failure, restart and historical-replay
contexts, plus the current downstream context. An independent effect review
accepts or rejects it. Acceptance changes the selected R/H pair while idle;
rejection leaves the parent selected. Both outcomes return findings and the
selected identity to the next round, which invokes the selected hooks.

The shared/legacy extensible interface is a restricted, pure `apply(context)` hook
that returns research advice/tool output. **H here is a research-side policy,
not permission to rewrite the native runtime.** The proposal cannot change
the candidate pool, protected data, scorer or authority. Capacity identity
checks keep kernel **K**, base model **M**, predictor **C**, runtime and memory
commitment fixed during an R/H comparison. Static source admission is a
restricted-language check, not OS containment. The activation registry also
supports an evidence-bound rollback to a previous accepted pair.

Matched supplied-context replay establishes a narrow behavioral effect, not
general research ability or prediction gain. Source existence, passing tests,
completed delivery, accepted capacity changes and sustained self-improvement
are distinct evidence claims.

The published earnings paths also include literal `PROFILE` adapters and an
executable `PROGRAM` / `run(payload)` contract. Host parsing checks metadata;
untrusted candidate execution belongs in its authorized isolated runtime.
These interfaces are not interchangeable. A run must bind the exact version,
inputs, review and execution contract it actually uses. The quickstart tests
selected deterministic fixtures, not a live Controller/Author experiment.

## Code map

Paths below are relative to the repository root. Module READMEs describe their
own interfaces, not necessarily the current earnings launch.

### Published earnings path

| Responsibility | Source entry points |
| --- | --- |
| Research pool and evidence-linked retention | [earnings_population.py](../tools/earnings_population.py), [population loop](../tools/earnings_population_loop.py) |
| Completed-window continuation | [population continuation](../tools/earnings_population_continuation.py), [runtime](../tools/earnings_population_runtime.py) |
| Controller/Author/review delivery | [open roles](../tools/earnings_open_roles.py), [population roles](../tools/earnings_population_roles.py) |
| Candidate metadata and isolated execution contract | [open program](../tools/earnings_open_program.py), [open researcher](../tools/earnings_open_researcher.py) |
| Task/forecast integration | [population tasks](../tools/earnings_population_tasks.py), [forecast transport](../tools/edgar_forecast_openai.py) |
| Portable demonstration | [common engine fixture](../tests/test_capacity_feedback_engine.py), [R/H fixture](../tests/test_earnings_capacity_adapter.py) |

[Earnings development](EARNINGS_DEVELOPMENT.md) gives the selected test commands.
These published files do not contain the complete later experimental state or
its empirical data/scorer. The newer three-child search protocol is documented
separately and is not a claim of activation in this public source snapshot.

### Shared engine and retained legacy/compatibility paths

| Responsibility | Source entry points |
| --- | --- |
| Developer CLI and regression selection | [`market_rsi/cli.py`](../market_rsi/cli.py), [`checks.py`](../market_rsi/checks.py), [`configs/checks.json`](../configs/checks.json) |
| Native launch, preflight and reviewed recovery | [`supervisor_harness/run_price_discovery.py`](../research/market_rsi/supervisor_harness/run_price_discovery.py) |
| Durable stages and existing ledger admission | [`feedback_linked_loop.py`](../research/market_rsi/supervisor_harness/feedback_linked_loop.py), [`feedback_loop_runtime.py`](../research/market_rsi/supervisor_harness/feedback_loop_runtime.py), [`coevo_pilot_transaction.py`](../research/market_rsi/supervisor_harness/coevo_pilot_transaction.py) |
| Feedback packet, branch pool and reconciliation | [`price_loop_services.py`](../research/market_rsi/supervisor_harness/price_loop_services.py), [`price_loop_handoff.py`](../research/market_rsi/supervisor_harness/price_loop_handoff.py) |
| Account-backed Controller/Author/review transport | [`price_account_roles.py`](../research/market_rsi/supervisor_harness/price_account_roles.py), [`account_controller_feedback_consumer.py`](../research/market_rsi/supervisor_harness/account_controller_feedback_consumer.py) |
| Candidate implementation and independent review | [`price_candidate_author.py`](../research/market_rsi/supervisor_harness/price_candidate_author.py), [`price_independent_review.py`](../research/market_rsi/supervisor_harness/price_independent_review.py) |
| R/H branching, child authorship and hook delivery | [`price_capacity_loop.py`](../research/market_rsi/supervisor_harness/price_capacity_loop.py), [`price_capacity_services.py`](../research/market_rsi/supervisor_harness/price_capacity_services.py) |
| R/H source checks and measured replay | [`price_capacity_source.py`](../research/market_rsi/supervisor_harness/price_capacity_source.py), [`price_capacity_trial.py`](../research/market_rsi/supervisor_harness/price_capacity_trial.py), [`price_capacity_replay.py`](../research/market_rsi/supervisor_harness/price_capacity_replay.py) |
| Identity, small-step journal and idle activation | [`research_capacity_identity.py`](../research/market_rsi/supervisor_harness/research_capacity_identity.py), [`research_capacity_activation.py`](../research/market_rsi/supervisor_harness/research_capacity_activation.py), [`co_evolution_loop.py`](../research/market_rsi/data_scientist_harness/co_evolution_loop.py) |
| Native scheduling, execution and attempt history | [`continuous_discovery_batch.py`](../research/market_rsi/supervisor_harness/continuous_discovery_batch.py), [`opened_train_discovery_worker.py`](../research/market_rsi/supervisor_harness/opened_train_discovery_worker.py) |
| Current financial-task scope | [`benchmarks/earnings/README.md`](../benchmarks/earnings/README.md) |
| Legacy NFL/prediction-market rows and scoring | [`nfl_ingame_price_data.py`](../research/market_rsi/experiments/nfl_ingame_price_data.py), [`nfl_ingame_price_change_train_diagnostic.py`](../research/market_rsi/experiments/nfl_ingame_price_change_train_diagnostic.py), [`nfl_ingame_price_score.py`](../research/market_rsi/experiments/nfl_ingame_price_score.py) |

## Directory ownership

```text
market_rsi/                         Thin developer CLI; forwards legacy helper APIs
configs/                            Named developer-check suites
benchmarks/earnings/                 Current task scope; empirical inputs stay local
benchmarks/nfl_price/                Legacy task/source reading index
tests/                              Developer interface/layout regression tests
tools/                              Earnings adapter/contracts and developer compatibility
docs/                               Project architecture, development and history
research/market_rsi/                 Source-bound native implementation
  supervisor_harness/               Loop services, roles, workers, review and state
  experiments/                      Legacy task definitions and diagnostics
  data_scientist_harness/            Co-evolution controls and earlier research tools
  ds_harness_core/                   Domain-neutral feature/quality validators
  quote_source/                     Separate causal source-quote reconstruction
  minimal_prediction_loop/           Earlier probability protocol/scoring components
```

The root `market_rsi/` package delegates legacy price execution to the native
module from its original working directory. Earnings-specific published modules
remain under `tools/`; shared implementation remains under `research/market_rsi/`.
Many native `test_*.py` files remain beside their modules.
The directory split reflects source-binding and compatibility constraints, not
a completed migration into the root package. Earlier/adjacent lanes are not
additional stages of the current price entry.

Retired memory-study runners and the PMB prototype are available through the
[history and recovery guide](HISTORY.md#recover-retired-experiment-components).

Runtime configuration, authority, ledgers and immutable outputs use the
configured local artifact store. Some historical records remain tracked in
this published snapshot; their presence does not make them current execution
instructions. Local working logs and new run evidence belong outside the
public source inventory. Prediction-market/NFL modules remain for source-bound
compatibility and historical checks; new earnings research should not extend
those legacy task definitions.

For environment setup and exact checks, see [Development](DEVELOPMENT.md).
For earlier designs and operational records, see [History](HISTORY.md).
During the earnings transition, apply the [code-structure maintenance
contract](CODE_STRUCTURE_MAINTENANCE.md) before moving or renaming source.
