# Earnings research source and offline tests

This publication preserves the current population entry and its reviewed
implementation dependencies through private checkpoint `c1b644b`, on top of
published main. It does not include that private
branch's ancestry, experiment records or later unfinished campaign work.
Publication does not activate a run or establish predictive improvement.

## Code map

- `tools/earnings_population*.py`: bounded version pool, diagnostics, feedback
  handoff, completed-window inheritance and reviewed execution entry.
- `tools/earnings_open*.py`: Controller/Author/review interfaces, source
  validation, original evidence tools and isolated researcher execution.
- `tools/earnings_capacity*.py`, `earnings_night_budget.py`, `earnings_entry.py`:
  source-bound worker, shared accounting, resource and request boundaries.
- `tools/edgar_forecast*.py`: original forecast transport, filing tools and
  scoring adapter. The original dataset and scorer checkout remain local.
- `research/market_rsi/supervisor_harness/capacity_feedback_engine.py` and
  `feedback_linked_loop.py`: durable stage execution and receipt verification.
- `tests/`: reusable synthetic unit/contract tests. Local historical-response
  regression fixtures remain in the private acceptance archive.

The public set keeps population/feedback inheritance, Author delivery,
source execution, filing-tool contracts, accounting and failure boundaries.
Older candidate-transfer/followthrough entrypoints and nonessential historical
test modules are retained locally rather than added to the current interface.
Supporting test modules imported by those key tests remain required fixtures.

## Offline checks

Use the existing Python 3.12 environment; no provider calls are needed:

```sh
PYTHONPATH=tools:tests:research/market_rsi python3 -B -m unittest discover -s tests -p 'test_earnings_population*.py'
PYTHONPATH=tools:tests:research/market_rsi python3 -B -m unittest test_author_delivery_handoff test_earnings_open_program test_earnings_open_incomplete_author test_earnings_open_researcher test_earnings_filing_tool_contract
```

Real-resident-data checks are separate from portable tests. Explicitly set
`MARKET_RSI_RESIDENT_DATA_TESTS=1` only on a host with the original hash-pinned
snapshots. Missing, mismatched or modified files still fail their original
checks; a fresh clone does not download or substitute data automatically.

## Local-only operational inputs

Raw filings, hidden answers, provider replies, ledgers, authority manifests,
run-specific plans, generated candidates and receipts are not distributed.
Historical paths, hash commitments and resource constants in source are
preserved rather than rewritten into a new experiment configuration.
The runtime JSON is a historical pinned configuration, not a statement of
current pricing or permission to spend.

The prepared entry requires its original reviewed local bindings. A public
clone alone is intentionally insufficient to launch a paid experiment.
This snapshot supports completed-window inheritance, not a delivered automatic
twenty-round scheduler or recovery of a rejected run as a completed run.
