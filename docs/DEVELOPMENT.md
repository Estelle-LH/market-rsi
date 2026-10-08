# Developing Market RSI

This guide covers the environment, developer checks and command behavior.
[Architecture](ARCHITECTURE.md) owns the current system explanation and code map;
[History](HISTORY.md) routes older designs and research records.

## Use the existing runtime

Use Python 3.12 and the existing CPU environment described by
[requirements-cpu.txt](../research/market_rsi/data_scientist_harness/requirements-cpu.txt).
Commands below assume that environment's interpreter is `python3`.
The check runner uses its own interpreter and does not install or upgrade
packages. This is a source-checkout interface; package installation is not
required.

Some inherited price tests use host-specific runtime paths and `/bin/ps` to
measure child-process RSS. A restricted environment that denies process
inspection cannot run those tests faithfully. Start with the root developer
tests and smoke suite; preserve an environment failure instead of disabling
the measurement.

## Choose the checks for your change

Run from the checkout root:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B -m market_rsi check --suite smoke
python3 -B -m market_rsi check --suite price --list
python3 -B -m market_rsi check --suite price
```

- **Root developer tests:** command delegation, layout/API compatibility and
  nested test-fixture cleanup.
- **Smoke:** five control, identity and activation test modules.
- **Price:** 24 selected modules covering native entry, feedback, R/H capacity,
  worker execution and price-task scoring.
- **`--list`:** print the exact module selection without running it.

[configs/checks.json](../configs/checks.json) is the single suite-selection
source. `--verbose` shows individual test results. Each selected suite has a
five-minute subprocess timeout, disables bytecode writes and limits numerical
library threads to one. It returns the test process's status; timeout returns
124 without a retry. These tests use synthetic fixtures and do not launch a
live research batch.

The compatibility command `python3 -B tools/check.py --suite smoke` remains
supported. From a different working directory, pass the absolute path to
`tools/check.py`, or explicitly set `PYTHONPATH` to this checkout when using
the module command.

## Inspect the native launch interface

```sh
python3 -B -m market_rsi price --help
```

The price command requires `--batch-config` and `--initial-feedback`, and
accepts `--preflight`. It delegates to the existing native entry with the
current interpreter and the original project working directory. Caller-relative
input paths become absolute before delegation; the wrapper adds no defaults,
retries, permissions or accounting.

A launch needs its own exact authorization, configuration, source and feedback
bindings. Test success does not create those bindings. The wrapper has mocked
launch coverage; live execution through the wrapper needs separate evidence.
Consult the bound launch configuration and
[research instructions](../research/market_rsi/AGENTS.md) before operational work.

## Keep source identities stable

Production imports, literal paths, scorers and source-hashed manifests still
refer to the existing implementation locations. Keep them unchanged during a
documentation or tracking cleanup. A future source move needs a caller/import
inventory, new prospective bindings and success/failure/restart replay checks;
a directory alias does not preserve that contract.

The developer package forwards legacy helper attributes to the existing
`research/market_rsi/market_rsi.py` implementation. Preserve that source identity
when changing the package namespace. Root tests check this compatibility.

## Publish source separately from private research

The active Supervisor checkpoint branch retains private research history.
Prepare a public change from published main with an explicit source/doc write
set; do not push private checkpoint ancestry with it. CandidateAuthor's immutable
`author_receipt.json` records may be necessary in local source bindings even
though public ignore rules exclude new receipts and logs.

Before committing, inspect the entire staged diff. Keep raw data, credentials,
runtimes, live ledgers and generated run records local. Existing tracked files
remain tracked after an ignore rule is added, so a tracking cleanup requires
its own reviewed inventory and recoverable local archive. Apply it at an idle
checkpoint while preserving original bytes and literal paths.

[History](HISTORY.md) explains where research state and archives belong.
Repository guidance is in [AGENTS.md](../AGENTS.md); task-specific research
instructions remain under [research/market_rsi/AGENTS.md](../research/market_rsi/AGENTS.md).
