# Developing Market RSI

This guide covers the environment, developer checks and command behavior.
[Architecture](ARCHITECTURE.md) owns the current system explanation and code map;
[History](HISTORY.md) routes older designs and research records.

New readers should begin with the repaired standard-library Python 3.12 path
in [Quickstart](QUICKSTART.md). Read the
[independent Linux verification record](DEVIN_VERIFICATION.md) for the original
hidden-file failure and repair. See [Reproducibility](REPRODUCIBILITY.md) before
interpreting offline checks as reproduction of an experiment result.

## Use the existing runtime

Use Python 3.12. The quickstart smoke and synthetic two-round demonstration
need no third-party packages. Broader numerical or legacy work uses the CPU
environment described by
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
PYTHONPATH=tools:tests:research/market_rsi python3 -B -m unittest discover -s tests -v
python3 -B -m market_rsi check --suite smoke
python3 -B -m market_rsi check --suite price --list
python3 -B -m market_rsi check --suite price
```

The root suite is broader and is known to fail in a public-only Linux clone:
it includes cases bound to a private empirical scorer, data and host runtimes,
plus unresolved portability/numerical-test failures. Numerical package
installation alone does not make it runnable. It is not required for the first
quickstart; preserve these failures instead of weakening the scientific tests.
Run navigation checks alone with
`PYTHONPATH=tools:tests:research/market_rsi python3 -B -m unittest test_public_docs -v`.
They validate public reading entrypoints and local link paths without importing
the research runtime.

- **Root developer tests:** command delegation, layout/API compatibility and
  nested test-fixture cleanup, plus the published earnings contracts. Their
  explicit import path includes the source-bound tools, test fixtures and
  legacy implementation root; no package installation is required.
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

## Inspect the legacy price launch interface

```sh
python3 -B -m market_rsi price --help
```

The legacy price command requires `--batch-config` and `--initial-feedback`, and
accepts `--preflight`. It delegates to the existing native entry with the
current interpreter and the original project working directory. Caller-relative
input paths become absolute before delegation; the wrapper adds no defaults,
retries, permissions or accounting.

A launch needs its own exact authorization, configuration, source and feedback
bindings. Test success does not create those bindings. The wrapper has mocked
launch coverage; live execution through the wrapper needs separate evidence.
New research work should follow the [earnings scenario boundary](../benchmarks/earnings/README.md),
not extend the legacy price command. Consult the bound launch configuration and
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
