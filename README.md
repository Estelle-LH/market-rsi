# Market RSI

Market RSI is an experimental system for feedback-driven automated research.
A Controller chooses the next hypothesis, an implementation role builds it,
and independent review and measurement return evidence to the next decision.
The research question is whether this process improves when the researcher
workflow and its execution hooks can also evolve in small, reviewed steps.

## How the system works

Each round carries forward its verified results, memory and candidate history.
The Controller can propose a prediction recipe (**C**), a researcher-workflow
change (**R**), or a research-side harness change (**H**). Candidate changes
are evaluated on the task; R/H changes have their own review and trial path
before an accepted version can be used in later research.

Read [Architecture](docs/ARCHITECTURE.md) for the round flow, the co-evolution
branch and the single current code map.
Read [Repository structure](docs/REPOSITORY_STRUCTURE.md) before adding or
moving files; it explains the boundary between the public CLI and research
implementation.

## Where to start

- **Understand the system:** [Architecture and code ownership](docs/ARCHITECTURE.md).
- **Work on the code:** [Environment, checks and commands](docs/DEVELOPMENT.md).
- **Understand the current task:** [Historical NFL price-change profile](benchmarks/nfl_price/README.md).
- **Find older designs and records:** [Research history and compatibility notes](docs/HISTORY.md).

## Run developer checks

Use the existing Python 3.12 CPU environment, from the checkout root:

```sh
python3 -B -m market_rsi check --suite smoke
python3 -B -m unittest discover -s tests -v
```

These commands exercise synthetic engineering regressions.
[Development](docs/DEVELOPMENT.md) describes the broader price suite and the
separate, explicitly authorized native launch command.

## Published implementation status

The published pipeline uses historical NFL five-minute trade-VWAP changes as
its current task. R/H proposal, trial and activation paths are present in
source and have synthetic regression coverage. Continuous live co-evolution,
matched improvement over a fixed research process and trading profitability
still need their own experimental evidence. Equities/earnings is the planned
next task adapter.

The top-level `market_rsi/` package provides developer commands and a thin
native-launch bridge. Core implementations remain under `research/market_rsi/`.
This documentation describes the published source; active Supervisor work and
private run status can be newer.

[AGENTS.md](AGENTS.md) records contribution and branch-naming guidance.
