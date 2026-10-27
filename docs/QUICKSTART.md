# Offline quickstart

This path lets a new reader run the public code without model credentials or
the private EDGAR dataset. It checks execution/feedback mechanics, not the
reported financial forecast scores. Use a separate checkout, never a live
Supervisor worktree.

## 1. Clone and create a clean environment

Prerequisites: Git and Python 3.12. The commands below use a POSIX shell.

```sh
git clone https://github.com/Estelle-LH/market-rsi.git
cd market-rsi
git rev-parse HEAD
python3.12 -m venv .venv
. .venv/bin/activate
python --version
```

The smoke check and two-round example below use only the standard library. They were checked
on macOS with Python 3.12.3 in a new venv without third-party packages. No
credential, Docker or resident-data opt-in is needed. Broader numerical/legacy
work can require the pinned CPU dependencies described in
[Development](DEVELOPMENT.md); it is not part of this first path.

## 2. Confirm the public interface and smoke checks

```sh
python -B -m market_rsi --help
python -B -m market_rsi check --suite smoke
```

Expected: CLI help, then a successful unittest summary. The checked snapshot ran
69 smoke tests. Counts can change; the success condition is exit status 0 with
no failures or errors. The CLI exposes checks and a legacy price delegate; it
does not expose a one-command authorized earnings experiment.

## 3. Observe a small two-round feedback/R/H example

```sh
PYTHONPATH=tools:tests:research/market_rsi python -B -m unittest test_capacity_feedback_engine test_earnings_capacity_adapter -v
```

These are deterministic, human-authored synthetic fixtures. The
[common-engine tests](../tests/test_capacity_feedback_engine.py) run sum/count
tasks, score the actual calculation, pass the result to the next round, check
that retained state is consumed and restore a completed run without executing
it again. The
[R/H adapter tests](../tests/test_earnings_capacity_adapter.py) check selected
research instructions, tool bounds, rejected changes and rollback.

Expected: the checked snapshot passes all 16 tests. Their temporary records are removed by the
test fixtures. No real LLM generates a scientific candidate here, and passing
does not demonstrate autonomous learning or financial prediction improvement.

## 4. Run wider public tests when needed

```sh
PYTHONPATH=tools:tests:research/market_rsi python -B -m unittest discover -s tests -v
```

This is the wider root developer/earnings suite, outside the minimal portable
quickstart; it can take substantially longer. Follow the environment requirements
in [Development](DEVELOPMENT.md) rather than treating the whole suite as validated
by the standard-library demonstration above.
Docker and original-resident-data cases have explicit opt-ins and are skipped
by default. Keep them off for this quickstart; a skipped case is not a pass of
that external execution boundary. See [Earnings development](EARNINGS_DEVELOPMENT.md)
for smaller source-contract groups.

For navigation checks alone:

```sh
PYTHONPATH=tools:tests:research/market_rsi python -B -m unittest test_public_docs -v
```

## If something fails

- Run from the repository root. The root test command needs all three explicit
  PYTHONPATH entries shown above.
- Use Python 3.12 and preserve the error and commit identity; do not install
  arbitrary newer dependencies or relax a source/data check to force a pass.
- The broader legacy `price` suite has host/runtime and process-inspection
  requirements. It is not the first portable earnings check.
- Never enable Docker, resident-data tests, paid execution or heldout access
  just to remove a skip or make a fresh clone look complete.

## Verification scope of this documentation cleanup

In a clean standard-library Python 3.12.3 venv, the smoke suite passed 69 tests,
the two-round/adapter example passed 16, and the navigation/layout/CLI/check-runner
group passed 27. These are separate selections, not a count of distinct tests.

The broader root discovery was also attempted and stopped manually before
completion because it was substantially more expensive than the targeted
checks. No full-root-suite pass is claimed for this cleanup. No live experiment,
provider call or private ledger was involved in these test runs.

Next read [Architecture](ARCHITECTURE.md), the
[reproduction boundary](REPRODUCIBILITY.md), and the
[two experiment tracks](experiments/README.md).
