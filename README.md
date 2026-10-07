# Market RSI

Market RSI studies whether a research agent can improve through experiment
feedback, including small, separately reviewed changes to its researcher
workflow (R) and execution harness (H).

The current price-task entry point is
[`run_price_discovery.py`](research/market_rsi/supervisor_harness/run_price_discovery.py).
It connects account-backed research roles, candidate implementation, source
review, execution, result review and durable feedback. R/H proposal and
activation hooks are integrated and covered by synthetic tests; live
co-evolution and performance gains remain research questions.

Start with [the development guide](DEVELOPMENT.md) for the code map and named
test suites. [The project README](research/market_rsi/README.md) retains the
historical research designs and test instructions.

```sh
python3 -B tools/check.py --suite smoke
python3 -B tools/check.py --suite price
```

Use the existing Python 3.12 CPU test environment. These commands run selected
synthetic regression tests, not a live batch. Equities/earnings is the planned
next data adapter; the current implementation still uses the NFL price task.
