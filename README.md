# Market RSI

Market RSI is a research system for testing whether an automated researcher can
improve both a prediction recipe and the way it conducts research. Each round
turns verified feedback into one bounded next decision; the decision is reviewed,
executed, scored, and recorded before it can influence the next round.

## The shortest useful picture

```text
bound input
  → Controller chooses C, R, or H
  → Author implements one versioned change
  → source review and bounded execution
  → independent measurement
  → reconcile feedback, memory, history and selected versions
  → next round
```

`C` is a prediction recipe. `R` is a researcher-policy change. `H` is a
research-side harness/tool change. R/H changes are evaluated on their own
matched replay path; they cannot rewrite the protected task, scorer or authority.

## Current published status

- Current task: historical NFL five-minute trade-VWAP-change diagnostic.
- Current evidence: synthetic engineering checks and opened-Train diagnostics;
  no claim of live self-improvement or trading profitability.
- Planned task: equities/earnings, with a new task adapter and evaluation
  contract rather than a silent substitution of the NFL profile.
- Public source: the thin `market_rsi/` developer CLI plus the source-bound
  implementation under `research/market_rsi/`.

## Start here

| If you want to… | Read |
| --- | --- |
| Understand the mechanism and co-evolution boundary | [Architecture](docs/ARCHITECTURE.md) |
| Decide where a file belongs | [Repository structure](docs/REPOSITORY_STRUCTURE.md) |
| Run checks or inspect the native launch | [Development](docs/DEVELOPMENT.md) |
| Understand the active task and baselines | [NFL price profile](benchmarks/nfl_price/README.md) |
| Recover older designs and private archives | [History](docs/HISTORY.md) |

## Checks

From the checkout root, using the existing Python 3.12 CPU environment:

```sh
python3 -B -m market_rsi check --suite smoke
python3 -B -m unittest discover -s tests -v
```

These are synthetic regression checks. They do not authorize a live research
run or open protected evaluation data. The broader price suite and native launch
interface are documented in [Development](docs/DEVELOPMENT.md).

## Source and archive boundary

Keep executable source, task contracts, tests and release manifests in Git.
Keep raw data, credentials, run logs, generated JSON/JSONL, and private research
records in the local archive. Before moving a file, classify it as active source,
compatibility source, historical evidence, or generated output; preserve an
exact local copy and run the checks on the tracked tree.

Contribution and branch rules live in [AGENTS.md](AGENTS.md).
