#!/usr/bin/env python3
"""Frozen pre-play possession-pressure offset; no future-play inputs."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from experiments import nfl_ingame_market_freshness_interaction_offset as common


TASK_ID = "InGameCausalPossessionPressureOffset-v1"
ARM_CANDIDATE = "causal_possession_pressure_offset"
ARM_RAW, ARM_ORDINARY, ARM_PARENT = common.ARM_RAW, common.ARM_ORDINARY, common.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = common.SOURCE_ROOT, common.V0_ARTIFACT_ROOT
MODEL_FITS = 4


def possession_pressure(state: dict) -> float:
    try:
        possession, down, distance, field = [float(state[name]) for name in (
            "possession_is_home", "down", "yards_to_go", "yards_to_opponent_goal")]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("causal possession state is incomplete") from error
    if (not all(math.isfinite(value) for value in (possession, down, distance, field))
            or possession not in (0, 1) or down not in (1, 2, 3, 4)
            or not 0 <= distance <= 100 or not 0 <= field <= 100):
        raise ValueError("causal possession state is outside frozen physical bounds")
    return (2 * possession - 1) * (1 - field / 100) / (down + distance / 10)


def pressure_features(fit_rows: list, check_rows: list, *, states: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    if not {row.game_id for row in [*fit_rows, *check_rows]} <= set(states):
        raise ValueError("causal possession state is missing a materialized game")
    # Only four explicitly named pre-play state fields enter this basis.
    return (np.asarray([possession_pressure(states[row.game_id]) for row in fit_rows]),
        np.asarray([possession_pressure(states[row.game_id]) for row in check_rows]),
        {"scaling": "none", "fixed_physical_bounds": True, "future_play_fields_used": False})


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    return common.run_recipe(source_root, output, candidate_id=TASK_ID, arm=ARM_CANDIDATE,
        runner_file=Path(__file__), feature_builder=pressure_features, allow_test_paths=allow_test_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
