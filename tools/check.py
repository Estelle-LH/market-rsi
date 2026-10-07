"""Run explicit synthetic development suites; never launch a research batch."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CHECKOUT_ROOT / "research" / "market_rsi"
TIMEOUT_SECONDS = 300
SUITES = {
    "smoke": (
        "supervisor_harness.test_feedback_linked_loop",
        "supervisor_harness.test_coevo_pilot_configuration",
        "supervisor_harness.test_research_capacity_identity",
        "supervisor_harness.test_research_capacity_activation",
        "data_scientist_harness.test_micro_evolution",
    ),
    "price": (
        "supervisor_harness.test_run_price_discovery",
        "supervisor_harness.test_price_capacity_loop",
        "supervisor_harness.test_price_capacity_trial",
        "supervisor_harness.test_price_capacity_replay",
        "supervisor_harness.test_price_capacity_review",
        "supervisor_harness.test_price_capacity_services",
        "supervisor_harness.test_price_capacity_source",
        "supervisor_harness.test_price_loop_services",
        "supervisor_harness.test_price_loop_handoff",
        "supervisor_harness.test_price_candidate_author",
        "supervisor_harness.test_price_independent_review",
        "supervisor_harness.test_price_account_roles",
        "supervisor_harness.test_feedback_loop_runtime",
        "supervisor_harness.test_feedback_linked_loop",
        "supervisor_harness.test_coevo_pilot_transaction",
        "supervisor_harness.test_coevo_pilot_configuration",
        "supervisor_harness.test_research_capacity_identity",
        "supervisor_harness.test_research_capacity_activation",
        "supervisor_harness.test_continuous_discovery_batch",
        "supervisor_harness.test_opened_train_discovery_worker",
        "experiments.test_nfl_ingame_price_change_train_diagnostic",
        "experiments.test_nfl_ingame_price_score",
        "experiments.test_nfl_ingame_price_data",
        "data_scientist_harness.test_micro_evolution",
    ),
}


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
