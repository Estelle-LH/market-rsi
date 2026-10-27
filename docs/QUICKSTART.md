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

The smoke check and two-round example below use only the standard library. No
credential, Docker or resident-data opt-in is needed. An independent Linux
check found a hidden private-file dependency in the original two-round fixture;
use the version containing the [portability repair](DEVIN_VERIFICATION.md), not
the earlier `153b6b2` snapshot. Broader numerical/legacy
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

Expected: the repaired snapshot passes all 17 tests. Their temporary records are removed by the
test fixtures. No real LLM generates a scientific candidate here, and passing
does not demonstrate autonomous learning or financial prediction improvement.

## 4. Run wider public tests when needed

```sh
PYTHONPATH=tools:tests:research/market_rsi python -B -m unittest discover -s tests -v
```

This is the wider root developer/earnings suite, outside the minimal portable
quickstart. It is **known to fail in a public-only Linux clone**: many cases
bind the private empirical scorer, original data or host-specific runtimes.
Installing the numerical dependencies does not supply those materials. See the
[independent test record](DEVIN_VERIFICATION.md) and
[Development](DEVELOPMENT.md); the standard-library demonstration above does
not validate this whole suite.
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

The original Mac check used a clean standard-library Python 3.12.3 venv, but
still had access to the host filesystem. Its 69/16/27 passing selections did
not establish portability. At `153b6b2`, Devin's fresh Ubuntu/Python 3.12.16
environment passed smoke (69) and focused developer checks (27), but the
two-round selection ran 16 tests with nine errors from an absolute private
macOS scorer path. The repaired fixture passes 17 tests locally and in Devin's
independent fresh GitHub clone at `7a66ea0`; smoke (69) and focused developer
checks (27) also pass there, with zero skips. A regression guard now forbids
that private loader in the
generic sum/count fixture; real earnings fixtures keep their original loader.
These are separate selections, not a count of distinct tests.

The initial broader root discovery failed on Linux, rather than timing out:
643 tests, 199 errors and 11 skips. It remains outside the passing portable
path. [The verification record](DEVIN_VERIFICATION.md) preserves the failure,
repair scope and retest evidence. No financial result, autonomous learning,
live experiment, provider call or private ledger write is established by these
checks.

Next read [Architecture](ARCHITECTURE.md), the
[reproduction boundary](REPRODUCIBILITY.md), and the
[two experiment tracks](experiments/README.md).
