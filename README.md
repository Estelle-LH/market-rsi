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

The research scenario is now moving to **equities earnings-event research**.
The repository currently contains the co-evolution engine and its offline
verification, but the earnings adapter, data contract and empirical scorer are
not yet active. The former NFL/prediction-market work remains recoverable
historical evidence; it is no longer the next research target.

- Active research target: earnings-event data, features, forecast and trading
  evaluation, introduced through a new task adapter.
- Active system core: Controller → Author → review → Worker → evaluation →
  feedback/memory, with separate `C` (recipe), `R` (researcher) and `H`
  (harness) changes.
- Evidence boundary: offline co-evolution checks pass; no earnings prediction
  improvement or trading profitability has been established yet.
- Public source: the thin `market_rsi/` developer CLI plus the source-bound
  implementation under `research/market_rsi/`.

## Start here

| If you want to… | Read |
| --- | --- |
| Understand the mechanism and co-evolution boundary | [Architecture](docs/ARCHITECTURE.md) |
| Decide where a file belongs | [Repository structure](docs/REPOSITORY_STRUCTURE.md) |
| Run checks or inspect the native launch | [Development](docs/DEVELOPMENT.md) |
| Understand the scenario transition | [Earnings task boundary](benchmarks/earnings/README.md) |
| Recover the former task and baselines | [NFL price profile](benchmarks/nfl_price/README.md) |
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
