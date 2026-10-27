# Code-structure maintenance contract

This repository is maintained while the research supervisors continue to work.
The contract keeps the active earnings transition readable without freezing
research or deleting historical evidence.

For newcomer navigation, use the [documentation map](README.md) and
[reproduction boundary](REPRODUCIBILITY.md). The reviewed earnings adapter now
exists under root `tools/`; this public snapshot is older than the later private
experiments. Keep those existing source-bound paths during documentation cleanup.

## Ownership map

| Area | Owner path | Maintenance rule |
| --- | --- | --- |
| Public commands and suite dispatch | `market_rsi/`, `configs/` | Keep thin; no task-specific research logic. |
| Active task scope | `benchmarks/earnings/` | Describe current financial targets and future task changes accurately. |
| Published earnings adapter | `tools/earnings_*.py`, `tools/edgar_forecast*.py` | Keep reviewed source paths and tests stable; no move implied by a preferred future layout. |
| Co-evolution engine | `research/market_rsi/supervisor_harness/` | Keep controller, worker, feedback and replay mechanics here. |
| Researcher runtime/release | `research/market_rsi/data_scientist_harness/` | Keep release maps and source publication explicit. |
| Reusable validation/provenance | `validation_tools/`, `source_review_tools/`, `data_science_tools/` | Preserve imports and release-map entries until a replacement is verified. |
| Historical NFL/prediction-market work | `benchmarks/nfl_price/`, `sports_event_research/`, local archive | Legacy only; do not extend for new earnings work. |
| Logs, run outputs and generated JSON/JSONL | local archive | Keep recoverable locally; do not add to the public tree unless a current source consumes it. |

## Supervisor checklist for every change

Before editing, classify the change as **active**, **legacy**, or
**compatibility** and record its parent commit. Then check:

1. Does a new task-specific file belong under `benchmarks/earnings/` rather
   than `research/market_rsi/*.py` or a `price_*` module?
2. Does a generic co-evolution change belong under `supervisor_harness/` and
   remain independent of the earnings adapter?
3. Does the release source map, suite configuration, import graph or source
   hash change? If so, update it in the same bounded checkpoint.
4. Is the file executable source, a compatibility dependency, historical
   evidence, or generated output? Only the last two are cleanup candidates.
5. Can the change be verified with a targeted test and the existing smoke
   suite before it is merged?

## Safe refactor order

1. Preserve the published earnings adapter/test snapshot; make any next adapter
   change explicit without moving the engine.
2. Separate task-neutral modules from legacy task modules, preserving imports
   and release hashes with compatibility shims where needed.
3. Rename the misleading `price` suite only after an alias and regression
   coverage exist.
4. Archive unused legacy paths in small, recoverable batches with an exact
   path manifest and checksum.

Do not perform a broad rename, delete source-bound modules, or change the
evaluation/data boundary as part of routine cleanup. Each checkpoint must state
the changed paths, tests run, source-map impact and rollback parent.
