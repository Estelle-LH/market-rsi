# Market RSI

Market RSI studies whether a research agent can improve through experiment
feedback, including small, separately reviewed changes to its researcher
workflow (R) and execution harness (H).

The source-checkout command is `python -m market_rsi`. Its price command
delegates to the existing native entry,
[`run_price_discovery.py`](research/market_rsi/supervisor_harness/run_price_discovery.py).
It connects account-backed research roles, candidate implementation, source
review, execution, result review and durable feedback. R/H proposal and
activation hooks are integrated and covered by synthetic tests; live
co-evolution and performance gains remain research questions.

Start with [the development guide](docs/DEVELOPMENT.md) for the code map and
compatibility boundaries. The [current task profile](benchmarks/nfl_price/README.md)
indexes the existing data, target, baseline and scorer. The
[historical project README](research/market_rsi/README.md) retains earlier designs.

```text
market_rsi/             Importable developer checks and thin native-launch CLI
configs/                Development-suite selection
benchmarks/             Read-only task/source profiles
tests/                  Developer interface and layout regressions
tools/                  Compatibility scripts
docs/                   Development guide
research/market_rsi/    Existing source-bound core and research evidence
```

```sh
python3 -B -m market_rsi check --suite smoke
python3 -B -m market_rsi check --suite price
python3 -B -m unittest discover -s tests -v
```

Use the existing Python 3.12 CPU test environment. These commands run selected
synthetic regression tests, not a live batch. Equities/earnings is the planned
next data adapter; the current implementation still uses the NFL price task.

`python3 -B -m market_rsi price --help` shows the native launch arguments.
Launching requires a separately authorized, fresh bound batch and feedback;
cleanup tests do not activate a run. No package installation is required.
The old `python3 -B tools/check.py ...` command remains supported.

For future cleanup, use the repository skill
[`$market-rsi-repo-hygiene`](.agents/skills/market-rsi-repo-hygiene/SKILL.md).
[AGENTS.md](AGENTS.md) routes maintenance tasks to it; runtime research policy
and scientific evaluation remain unchanged.
