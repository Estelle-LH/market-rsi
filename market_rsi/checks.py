"""Run explicit synthetic development suites; never launch a research batch."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CHECKOUT_ROOT / "research" / "market_rsi"
TIMEOUT_SECONDS = 300
SUITES = {name: tuple(modules) for name, modules in
          json.loads((CHECKOUT_ROOT / "configs" / "checks.json").read_text()).items()}


def test_environment():
    """Bound test threads without changing the parent process environment."""
    environment = os.environ.copy()
    environment.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    })
    return environment


def run_suite(suite, *, verbose=False):
    command = [sys.executable, "-B", "-m", "unittest",
               "-v" if verbose else "-q", *SUITES[suite]]
    try:
        result = subprocess.run(
            command, cwd=PROJECT_ROOT, env=test_environment(),
            timeout=TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"Suite {suite!r} exceeded {TIMEOUT_SECONDS}s; no retry.", file=sys.stderr)
        return 124
    return result.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=tuple(SUITES), default="smoke")
    parser.add_argument("--list", action="store_true", help="List modules without running tests.")
    parser.add_argument("--verbose", action="store_true", help="Show individual test results.")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(SUITES[args.suite]))
        return 0
    return run_suite(args.suite, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
