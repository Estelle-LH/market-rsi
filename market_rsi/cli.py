"""Source-checkout commands; existing native admission and accounting apply."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from market_rsi import checks


PRICE_ENTRY = "supervisor_harness.run_price_discovery"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Run synthetic developer regressions.")
    check.add_argument("--suite", choices=tuple(checks.SUITES), default="smoke")
    check.add_argument("--list", action="store_true")
    check.add_argument("--verbose", action="store_true")
    price = commands.add_parser("price", help="Delegate an explicitly authorized native batch.")
    price.add_argument("--batch-config", required=True)
    price.add_argument("--initial-feedback", required=True)
    price.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "check":
        forwarded = ["--suite", args.suite]
        if args.list:
            forwarded.append("--list")
        if args.verbose:
            forwarded.append("--verbose")
        return checks.main(forwarded)

    # Resolve caller-relative names before changing the child's cwd. Do not
    # resolve symlinks or alter bindings; native admission validates them.
    command = [sys.executable, "-B", "-m", PRICE_ENTRY,
               "--batch-config", str(Path(args.batch_config).absolute()),
               "--initial-feedback", str(Path(args.initial_feedback).absolute())]
    if args.preflight:
        command.append("--preflight")
    result = subprocess.run(command, cwd=checks.PROJECT_ROOT, check=False)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode
