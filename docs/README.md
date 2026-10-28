# Documentation map

Start with the research question and the public checks, then choose whether you
want to inspect the implementation or understand the experiments. The public
source, the latest local experiment and a dated report are separate artifacts.

## A new reader's route

1. [Quickstart](QUICKSTART.md): run offline checks from a clean Python environment.
2. [Architecture](ARCHITECTURE.md): understand Controller, Author, execution,
   review and how feedback changes the next decision.
3. [Reproducibility](REPRODUCIBILITY.md): see what the public tree can reproduce
   today and what a complete experiment package still needs.
4. [Experiment index](experiments/README.md): read Experiment 1's report provenance,
   Experiment 2's protocol and the future comparison plan (Chinese).

## If you want to work on the code

| Question | Canonical document |
| --- | --- |
| Which environment and test command should I use? | [Development](DEVELOPMENT.md) |
| What really passed on an independent clean machine? | [Devin verification and portability repair](DEVIN_VERIFICATION.md) |
| Which earnings modules and tests are published? | [Earnings development](EARNINGS_DEVELOPMENT.md) |
| Where does a change belong? | [Repository structure](REPOSITORY_STRUCTURE.md) |
| How should an AWS move preserve state and memory? | [Deployment and memory plan](deployment/README.md) |
| What may a cleanup safely change? | [Maintenance contract](CODE_STRUCTURE_MAINTENANCE.md) |
| What does the current task actually predict? | [Earnings task scope](../benchmarks/earnings/README.md) |

## If you want to understand the evidence

- [Experiment 1](experiments/experiment-01-open-research/README.md) is the source
  of the current advisor report. Its dated score snapshot is not live telemetry.
- [Experiment 2](experiments/experiment-02-framework-restart/README.md) keeps its
  own baseline, state and accounting. Its
  [complete Supervisor prompt](experiments/experiment-02-framework-restart/SUPERVISOR_PROMPT.zh-CN.md)
  is a human-supplied prospective method, not proof of implementation.
- [Comparison plan](experiments/COMPARISON_PLAN.zh-CN.md) specifies how to compare
  the trajectories when Experiment 2 has complete results.

## Historical reading

[History](HISTORY.md) preserves earlier designs and recovery checkpoints.
[Scenario migration](SCENARIO_MIGRATION.md) records the transition from NFL/
prediction markets. The [NFL source index](../benchmarks/nfl_price/README.md) and
module READMEs describe their own legacy interfaces; their old launch commands,
model names and grants are not current earnings instructions.

