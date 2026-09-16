#!/usr/bin/env python3
"""Run one post-session Dev score under the prospective Transfer lifecycle."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from market_rsi import canonical
from prospective_data_lifecycle import ProspectiveDataLifecycle
from sealed_dev_runner import _run_once


OUTCOME_SCHEMA = "market_controller_prospective_sealed_dev_outcome_v2"


async def run_once(workspace: Path, config_path: Path, output: Path) -> dict:
    return await _run_once(workspace, config_path, output,
                           lifecycle_class=ProspectiveDataLifecycle,
                           outcome_schema=OUTCOME_SCHEMA)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(canonical(asyncio.run(run_once(args.workspace, args.config, args.output))))
