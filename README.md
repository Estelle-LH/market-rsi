# Market RSI

Market RSI studies whether an automated researcher can improve both **what it
predicts** and **how it researches**. Reviewed feedback drives the next bounded
change; candidate code, actual parents, measurements and failures stay traceable.

## Start here

- **New reader:** [five-minute offline quickstart](docs/QUICKSTART.md).
- **What are we doing?** [Architecture](docs/ARCHITECTURE.md) explains the roles
  and feedback loop; the [documentation map](docs/README.md) routes deeper reading.
- **What have we observed?** [Two earnings experiments](docs/experiments/README.md)
  separates the current report, the independent restart and their baselines
  (Chinese reports/protocol).
- **Can I reproduce it?** [Reproducibility and publication boundary](docs/REPRODUCIBILITY.md)
  distinguishes runnable public checks from the still-local 25-company experiment.

## One research cycle

```text
observed problem → Controller hypothesis → Author change → review
       ↑                                              ↓
next decision ← feedback, memory and selection ← execution and scoring
```

Changes are classified as **C** (prediction recipe), **R** (research policy) or
**H** (research-side tools/harness). A better prediction, a demonstrated R/H
behavior and a human-directed engineering repair are reported separately.
Not every proposal reaches scoring: rejected and failed branches remain evidence.

## Public source versus experiment results

The public tree contains the reviewed earnings adapter, version-pool and
feedback-continuation code, shared engine, and synthetic regression tests.
The public source snapshot and the private experiment checkpoints are different
versions; publishing a protocol does not make its latest tree policy implemented.

The current advisor report comes from **Experiment 1**, whose recorded Round17
scored **3.18/5** against its own **3.00/5** Round0. **Experiment 2** has its own
**2.98/5** baseline and separate state and accounting. These are reused-training
Discovery results, not established causal/generalization gains or trading profit.
The [experiment index](docs/experiments/README.md) fixes the report provenance
and the scope of these dated snapshots.

A public clone can reproduce offline mechanics. It cannot yet reproduce the
reported full25 scores from source alone: exact experiment candidates, task data,
scorer, runtime/configuration bindings and original run evidence remain local.
See the [reproduction levels and missing-material checklist](docs/REPRODUCIBILITY.md).

## Try the public checks

With Python 3.12, from this checkout:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -B -m market_rsi check --suite smoke
```

The smoke suite uses synthetic fixtures: no API key, provider call, Docker or
original dataset is needed. See [Quickstart](docs/QUICKSTART.md) for a small
two-round R/H demonstration and [Development](docs/DEVELOPMENT.md) for wider checks.

## Where does the code live?

| Area | Purpose |
| --- | --- |
| [market_rsi/](market_rsi/) | Thin CLI and regression dispatch; not a second engine |
| [tools/](tools/) | Published earnings population, roles, execution and source contracts |
| [research/market_rsi/supervisor_harness/](research/market_rsi/supervisor_harness/) | Shared native engine, review, feedback, R/H identity and activation |
| [tests/](tests/) | Public developer and synthetic earnings regressions |
| [docs/](docs/README.md) | Architecture, setup, reproduction and experiment navigation |
| [benchmarks/earnings/](benchmarks/earnings/README.md) | Current financial-forecast task scope and future trading boundary |

[Repository structure](docs/REPOSITORY_STRUCTURE.md) explains active versus
compatibility paths. NFL/prediction-market code is legacy material, not the
current earnings benchmark; use [History](docs/HISTORY.md) for recovery.

## Contributing safely

Follow [AGENTS.md](AGENTS.md) and [Development](docs/DEVELOPMENT.md).
Keep original data, credentials, ledgers and private run records local.
Public tests and documentation do not grant paid execution or heldout access;
do not pull this cleanup into a live experiment or move source-hashed modules.
