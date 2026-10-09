# Repository structure

This repository has one public execution surface and one research implementation
surface. Keep that distinction stable when adding files.

```text
market-rsi/
├── market_rsi/                 # public developer CLI and check dispatch
├── configs/                    # suite selection; no task logic
├── benchmarks/                 # active task profile and benchmark README
├── tests/                      # small repository/layout/CLI regression suite
├── docs/                       # architecture, development and history
└── research/market_rsi/        # implementation and research-side adapters
    ├── supervisor_harness/     # active orchestration, review and capacity hooks
    ├── data_scientist_harness/ # release boundary and researcher runtime
    ├── data_science_tools/     # review/report preparation utilities
    ├── validation_tools/       # source and evidence validators
    ├── source_review_tools/    # source-scope and provenance review
    ├── sports_event_research/  # task-side event/PBP materialization
    ├── experiments/            # retained active price/evidence candidates
    ├── audit_tools/            # retained release-bound audit inputs only
    └── *.py                    # compatibility and release-bound research modules
```

## Which path should a change use?

| Change | Location | Rule |
| --- | --- | --- |
| New CLI command or check-suite dispatch | `market_rsi/` | Keep it thin; delegate to research code. |
| Check membership or suite selection | `configs/checks.json` | Do not duplicate suite lists in Python. |
| Active task identity/baselines | `benchmarks/nfl_price/` | Update the profile and its README together. |
| Controller, worker, review or R/H capacity behavior | `research/market_rsi/supervisor_harness/` | Preserve the protocol source boundary. |
| Researcher release/runtime contract | `research/market_rsi/data_scientist_harness/` | Keep source publication explicit and reproducible. |
| Data/evidence materialization | `research/market_rsi/sports_event_research/` or the named task adapter | Keep raw inputs and receipts out of Git. |
| Historical notes, logs, generated JSON/JSONL | local archive | Do not add them to the public tree unless a current source explicitly consumes them. |

## Compatibility rule

`research/market_rsi/market_rsi.py` is a compatibility implementation. The
top-level `market_rsi/` package forwards the public API to it; this is why two
similarly named paths exist. Do not copy the implementation into the CLI
package or rename it without updating `tests/test_layout.py`, the release
source map, and the benchmark profile in one reviewed change.

## Cleanup rule

Before moving or untracking a file, classify it as one of:

1. active source selected by `configs/checks.json` or the release source map;
2. compatibility source imported by an active entrypoint;
3. historical experiment/test/documentation;
4. generated data or run output.

Only categories 3 and 4 are cleanup candidates. Preserve the original locally,
record an exact-path archive, and run the repository checks on a fresh tracked
tree before opening a PR.
