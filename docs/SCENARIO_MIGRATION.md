# Scenario migration: prediction markets → earnings events

This is the historical scenario-transition plan, not the current implementation
status. The reviewed earnings adapter/tests are now public, and the present
financial-target experiments are separate from future market/trading work.
Use [Architecture](ARCHITECTURE.md), [Earnings task scope](../benchmarks/earnings/README.md)
and [Reproducibility](REPRODUCIBILITY.md) for the current reading path.

## Decision

The next scientific task is equities earnings-event research. The shared
co-evolution engine stays in place; the task boundary changes from historical
NFL/prediction-market rows to point-in-time filings, estimates, announcements
and post-event market outcomes.

## What stays active

The following layers are scenario-neutral and remain the system core:

- Controller, Author, Worker and independent review roles;
- `C` / `R` / `H` identity and small-step change contracts;
- source review, bounded execution, feedback, memory and rollback;
- release/source hashing, test selection and local artifact preservation.

## What becomes legacy

The former task-specific surface is retained for replay until an equivalent
earnings adapter is tested:

- `benchmarks/nfl_price/`;
- `research/market_rsi/experiments/nfl_ingame_*`;
- `research/market_rsi/sports_event_research/`;
- Polymarket-specific historical data, quote reconstruction and scoring modules;
- old probability/PMB compatibility lanes documented in `docs/HISTORY.md`.

These paths are not the place for new earnings features. They remain in the
source tree temporarily because current compatibility tests and release-bound
imports still reference parts of them. Removing them is a separate audited
archive batch, after the earnings adapter supplies an equivalent boundary.

## New earnings boundary

The new adapter belongs under a task-specific earnings namespace and must own:

1. point-in-time input materialization and publication timestamps;
2. event identity, announcement cutoff and target horizon;
3. consensus, market and persistence baselines;
4. forecast metrics and a separate cost-aware trading simulation;
5. missingness, revisions, duplicate events and split rules;
6. source, data, scorer and candidate hashes.

The adapter must not import the old Polymarket/NFL modules. The engine must not
know whether a task is an event probability, an earnings surprise or a price
response. This keeps the scenario switch attributable and makes the old task
replayable without allowing it to shape the new benchmark.

## Refactor sequence

1. Add the earnings profile and synthetic contract tests.
2. Add the point-in-time data adapter and frozen baselines.
3. Add the scorer and trading-value report as separate outputs.
4. Register the earnings tests without changing the protected engine kernel.
5. Run matched offline co-evolution checks with the new task boundary.
6. Archive only legacy modules with no remaining import or release binding.
