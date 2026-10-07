#!/usr/bin/env python3
"""Matched residual HGB with exactly nine additional frozen causal fields."""
from __future__ import annotations

import argparse
from pathlib import Path

from experiments import nfl_ingame_market_residual_hgb as shared


TASK_ID = "InGameMarketStateResidualHGB-v1"
ARM_CANDIDATE = "market_state_residual_hgb"
SOURCE_ROOT, V0_ARTIFACT_ROOT = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT
MODEL_FITS = 4


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    return shared.run_recipe(source_root, output, candidate_id=TASK_ID, arm=ARM_CANDIDATE,
        include_state=True, runner_file=Path(__file__), allow_test_paths=allow_test_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(shared.common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
