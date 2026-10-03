#!/usr/bin/env python3
"""Frozen prior-play volume ratio with the archived parent's NLL offset trainer."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from experiments import nfl_ingame_identity_blended_isotonic as sibling
from experiments import nfl_ingame_prior_play_success_market_uncertainty_audit as uncertainty


common = sibling.common
TASK_ID = "InGamePriorPlayVolumeOffset-v1"
ARM_CANDIDATE = "prior_play_volume_offset"
ARM_RESEARCH_PARENT = sibling.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = sibling.ARM_RAW, sibling.ARM_ORDINARY, sibling.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = sibling.SOURCE_ROOT, sibling.V0_ARTIFACT_ROOT
MODEL_FITS = 4
CONTRACT, CONTRACT_SHA256 = sibling.CONTRACT, sibling.CONTRACT_SHA256
SIBLING_SOURCE_SHA256 = "489d8268bd5243d94df9396f6dd5d616acfeab2d23f29d0e9e5903b7f156cce5"
UNCERTAINTY_SOURCE_SHA256 = "e51f85ed368c53545369dfdd7505dcee3331917cba115ebacb5194290808e745"
EXTRA_DEPENDENCIES = {sibling.__name__: SIBLING_SOURCE_SHA256, uncertainty.__name__: UNCERTAINTY_SOURCE_SHA256}
FORMULA = "(home_eligible_plays-away_eligible_plays)/(home_eligible_plays+away_eligible_plays)"


def volume_ratio(indicator: dict) -> float:
    try:
        home, away = indicator["home_eligible_plays"], indicator["away_eligible_plays"]
    except (KeyError, TypeError) as error:
        raise ValueError("both strictly-prior eligible-play counts are required") from error
    if type(home) is not int or type(away) is not int or home <= 0 or away <= 0:
        raise ValueError("strictly-prior eligible-play counts must be positive integers")
    ratio = (home - away) / (home + away)
    if not math.isfinite(ratio) or not -1 < ratio < 1:
        raise ValueError("prior-play volume ratio is outside its finite physical range")
    return ratio


def validate_features(indicators: dict, rows: list) -> dict:
    if set(indicators) != {row.game_id for row in rows}:
        raise ValueError("prior-play volume feature coverage differs from all materialized games")
    return {game_id: volume_ratio(indicator) for game_id, indicator in indicators.items()}


def load_features(source_root: Path, frozen: dict, recipe: dict, rows: list) -> tuple[dict, dict]:
    for module, digest in ((sibling, SIBLING_SOURCE_SHA256), (uncertainty, UNCERTAINTY_SOURCE_SHA256)):
        path = Path(module.__file__)
        if not path.is_file() or path.is_symlink() or common._sha256(path) != digest:
            raise ValueError("frozen prior-play volume sibling/validator source changed")
    evidence = recipe["feature_artifact"]
    root = Path(evidence["root"])
    artifact = uncertainty._validate_parent_artifact(root, expected_hashes=evidence["hashes"])
    if artifact["hashes"] != evidence["hashes"]:
        raise ValueError("frozen prior-play volume feature artifact changed")
    source_receipts = common.frozen_v0._validate_source_and_receipts(source_root, frozen)
    original = common.settlement._strict_json(root / "input_receipts.json")
    if any(original.get(key) != value for key, value in source_receipts.items()):
        raise ValueError("prior-play feature artifact does not bind current source/cohort/PBP receipts")
    indicators = common.frozen_v0._load_indicators(root / "prior_play_success.csv", frozen)
    values = validate_features(indicators, rows)
    return values, {"feature_artifact_hashes": artifact["hashes"], "source_receipts": source_receipts,
        "all_materialized_rows_validated": len(values), "source_feature_rows": 195,
        "predictive_fields": ["home_eligible_plays", "away_eligible_plays"], "formula": FORMULA,
        "feature_values_sha256": common._digest(values), "extractor_rerun": False,
        "x_min": min(values.values()), "x_max": max(values.values())}


def replay_offset(state: dict, rows: list, features: dict) -> list[float]:
    if (state["formula"] != FORMULA or state["market_coefficient"] != 1 or state["intercept"] is not False
            or state["standardization"] != "none" or state["penalty"] != 16
            or not math.isfinite(state["beta"])):
        raise ValueError("prior-play offset numeric state/recipe changed")
    raw = sibling.raw_probabilities(rows)
    x = common._vector([features[row.game_id] for row in rows], "check volume ratios")
    if np.any(x <= -1) or np.any(x >= 1):
        raise ValueError("check volume ratio physical bounds changed")
    return common.candidate_probabilities(state["beta"], x, [row.market_features[0] for row in rows], raw_probabilities=raw)


def fit_offset(fit: list, check: list, features: dict) -> tuple[list[float], dict]:
    sibling.raw_probabilities(fit)
    x = common._vector([features[row.game_id] for row in fit], "fit volume ratios")
    if np.any(x <= -1) or np.any(x >= 1):
        raise ValueError("fit volume ratio physical bounds changed")
    labels = [row.trusted["outcome"] for row in fit]
    offsets = [row.market_features[0] for row in fit]
    beta, optimizer = common.fit_single_offset(x, labels, offsets)
    objective, gradient, _ = common.objective_gradient_hessian(beta, x, labels, offsets)
    if (not optimizer["converged"] or not math.isfinite(beta) or not math.isfinite(objective)
            or abs(gradient) > 1e-8 or optimizer["penalty"] != 16
            or optimizer["unused_zero_column_coefficient"] != 0):
        raise ValueError("prior-play volume offset failed exact frozen convergence")
    state = {"schema": "prior_play_volume_single_offset_numeric_state_v1", "formula": FORMULA,
        "beta": beta, "market_coefficient": 1, "intercept": False, "standardization": "none",
        "penalty": 16, "fit_events": len(fit), "fit_feature_sha256": common._digest(x.tolist())}
    values = replay_offset(state, check, features)
    return values, {"optimizer": optimizer, "model_fits": 1, "fit_events": len(fit), "input_columns": 1,
        "fit_only": True, "analytic_objective": objective, "analytic_gradient_absolute": abs(gradient),
        "predictor_state_sha256": common._digest(state), "primitive_prediction_state": state,
        "bounding": {"clipped_rows": 0, "rows_removed": 0, "epsilon": sibling.EPSILON}}


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    return sibling.run_recipe(source_root, output, candidate_id=TASK_ID, arm=ARM_CANDIDATE,
        runner_file=Path(__file__), fit_predict=fit_offset, feature_loader=load_features,
        extra_dependency_hashes=EXTRA_DEPENDENCIES, allow_test_paths=allow_test_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
