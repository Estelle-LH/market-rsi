"""Opened-Train trainer-only A/B on the frozen NFL full_k4 representation.

The target, row population, rolling whole-game folds, features, preprocessing,
weights and metrics are frozen to the completed representation ablation.  The
only changed component is Random Forest versus one preregistered
HistGradientBoostingRegressor.  Route-Dev and Final stay closed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from data_scientist_harness.target_discovery_contract import (
    verify_frozen_target_discovery_spec,
)
from experiments.nfl_representation_ablation import (
    CALIBRATION_RANGE,
    DERIVED,
    MINIMUM_POSITIVE_GAME_FRACTION,
    PRIMARY,
    TARGET,
    derived_without_state,
    matrices,
    paired_against_parent,
    verify_release,
)
from experiments.nfl_target_grid_screen import (
    current_commit,
    load_rows,
    load_target_map,
)
from experiments.nfl_target_same_support import TARGETS, common_indices
from market_rsi import file_hash, fresh_json, load_json
from sports_event_research.materialize_controller_targets import target_names
from sports_event_research.run_state_surprise_discovery import (
    fit_state_model,
    load_state_history,
    market_state,
    same_event_post_states,
    state_model_diagnostic,
)
from sports_event_research.run_train_method_screen import (
    METHODS,
    SEED,
    equal_game_weights,
    metrics,
    rolling_folds,
)


CANDIDATE = "hist_gradient_boosting"
HGB_PARAMETERS = dict(METHODS[CANDIDATE])


def verify_prior(root: Path) -> tuple[dict, dict, dict]:
    root = Path(root).resolve()
    manifest = load_json(root / "manifest.json")
    result = load_json(root / "result.json")
    diagnostics = load_json(root / "diagnostics.json")
    receipts = load_json(root / "input_receipts.json")
    if (manifest.get("schema") != "nfl_representation_ablation_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("provider_cost_usd") != "0"):
        raise ValueError("completed opened-Train representation artifact required")
    for name in ("result", "diagnostics", "input_receipts"):
        if manifest.get(f"{name}_sha256") != file_hash(root / f"{name}.json"):
            raise ValueError(f"prior {name} hash mismatch")
    if (result.get("schema") != "nfl_representation_ablation_result_v1"
            or result.get("parent_reproduced") is not True
            or result.get("primary_candidate") != PRIMARY
            or result.get("route_dev_opened") is not False
            or result.get("sealed_final_opened") is not False):
        raise ValueError("exact completed full_k4 representation result required")
    if (diagnostics.get("schema") != "nfl_representation_ablation_diagnostics_v1"
            or receipts.get("schema") != "nfl_representation_ablation_inputs_v1"):
        raise ValueError("prior representation diagnostics/receipts are invalid")
    return result, diagnostics, receipts


def parent_report(result: dict, diagnostics: dict) -> dict:
    summary = result["summary"][PRIMARY]
    by_game = diagnostics["aggregate_by_game"][PRIMARY]
    report = dict(summary)
    report["by_game"] = by_game
    if len(by_game) != summary["games"]:
        raise ValueError("prior parent by-game population mismatch")
    return report


def support_conditions(candidate: dict, candidate_folds: list[dict],
                       parent_folds: list[dict], paired: dict) -> dict:
    if len(candidate_folds) != 3 or len(parent_folds) != 3:
        raise ValueError("exact three-fold comparison required")
    fold_wins = [
        candidate_fold["equal_game_candidate_mse"]
        < parent_fold["equal_game_candidate_mse"]
        for candidate_fold, parent_fold in zip(candidate_folds, parent_folds)
    ]
    slope = candidate["equal_game_calibration_slope"]
    interval = paired["candidate_minus_parent_date_block_interval"]
    return {
        "candidate_mse_below_parent_in_every_fold": all(fold_wins),
        "fold_wins": fold_wins,
        "paired_date_block_interval_upper_below_zero": (
            interval["upper"] is not None and interval["upper"] < 0
        ),
        "calibration_slope_in_range": (
            slope is not None and CALIBRATION_RANGE[0] <= slope <= CALIBRATION_RANGE[1]
        ),
        "positive_game_fraction_at_least_threshold": (
            candidate["positive_game_fraction"] >= MINIMUM_POSITIVE_GAME_FRACTION
        ),
    }


def supported(conditions: dict) -> bool:
    return all(
        value if isinstance(value, bool) else all(value)
        for value in conditions.values()
    )


def run(spec_path: Path, target_materialization: Path, panel_root: Path,
        selection_root: Path, release_path: Path, prior_representation: Path,
        nflverse_history: list[Path], repo_root: Path, output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        release = verify_release(release_path)
        prior_result, prior_diagnostics, prior_receipts = verify_prior(prior_representation)
        frozen_record = load_json(spec_path)
        frozen = verify_frozen_target_discovery_spec(frozen_record)
        names = [name for name, _, _ in target_names(frozen)]
        if not set(TARGETS).issubset(names) or TARGET not in names:
            raise ValueError("frozen target materialization lacks same-support neighborhood")

        materialization = Path(target_materialization).resolve()
        materialization_manifest = load_json(materialization / "manifest.json")
        if (materialization_manifest.get("complete") is not True
                or materialization_manifest.get("route_dev_opened") is not False
                or materialization_manifest.get("sealed_final_opened") is not False
                or materialization_manifest.get("target_panel_sha256")
                != file_hash(materialization / "target_panel.csv")):
            raise ValueError("target materialization receipt is invalid")
        expected_input_hashes = {
            "target_spec_sha256": file_hash(spec_path),
            "target_materialization_manifest_sha256": file_hash(
                materialization / "manifest.json"
            ),
            "target_panel_sha256": file_hash(materialization / "target_panel.csv"),
        }
        for key, value in expected_input_hashes.items():
            if prior_receipts.get(key) != value:
                raise ValueError(f"current input no longer matches prior {key}")

        target_map, _ = load_target_map(materialization / "target_panel.csv", names)
        all_rows, panel_receipts = load_rows(
            Path(panel_root), Path(selection_root), target_map, names
        )
        ordered_games = [receipt["game"] for receipt in panel_receipts]
        indices = common_indices(all_rows, ordered_games)
        rows = []
        for index in indices:
            row = dict(all_rows[index])
            row["target"] = float(row["targets"][TARGET])
            rows.append(row)
        if len(rows) != prior_result["same_support_full_rows"] or len(rows) != 16632:
            raise ValueError("exact prior 16,632-play population required")

        market_receipts = []
        for receipt in panel_receipts:
            value = dict(receipt)
            value["panel_path"] = str(
                (Path(panel_root) / receipt["game"] / "play_trade_alignment.csv").resolve()
            )
            market_receipts.append(value)
        state_x, state_y, state_games, history_receipts = load_state_history(nflverse_history)
        post_states, availability_receipts = same_event_post_states(rows, market_receipts)
        input_receipts = {
            "schema": "nfl_representation_trainer_ablation_inputs_v1",
            **expected_input_hashes,
            "prior_representation_manifest_sha256": file_hash(
                Path(prior_representation) / "manifest.json"
            ),
            "prior_representation_result_sha256": file_hash(
                Path(prior_representation) / "result.json"
            ),
            "prior_representation_diagnostics_sha256": file_hash(
                Path(prior_representation) / "diagnostics.json"
            ),
            "panel_receipts": panel_receipts,
            "history_receipts": history_receipts,
            "same_event_availability_receipts": availability_receipts,
        }
        fresh_json(output / "input_receipts.json", input_receipts)

        folds = rolling_folds(ordered_games)
        parent_folds = [
            fold["variants"][PRIMARY]["metrics"]
            for fold in prior_diagnostics["folds"]
        ]
        if [fold["fold"] for fold in folds] != [fold["fold"] for fold in prior_diagnostics["folds"]]:
            raise ValueError("rolling fold identity changed")
        lock = {
            "schema": "nfl_representation_trainer_ablation_lock_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "question": "Does fixed HistGradientBoosting beat the exact full_k4 Random Forest parent while clearing calibration and breadth gates?",
            "hypothesis": "The candidate clears all four preregistered opened-Train support conditions.",
            "changed_stage": "prediction_trainer_only",
            "target": TARGET,
            "same_support_targets": list(TARGETS),
            "same_support_full_rows": len(rows),
            "rolling_design": {"initial_games": 100, "block_games": 21, "blocks": 3},
            "frozen_derived_features": list(DERIVED),
            "frozen_preprocessing": "fold-fit StandardScaler numeric plus fold-fit one-hot play_type",
            "frozen_train_weighting": "equal_game",
            "parent": {
                "trainer": "random_forest",
                "parameters": METHODS["random_forest"],
                "equal_game_candidate_mse": prior_result["summary"][PRIMARY]["equal_game_candidate_mse"],
                "fold_equal_game_candidate_mse": [
                    fold["equal_game_candidate_mse"] for fold in parent_folds
                ],
            },
            "candidate": {
                "trainer": CANDIDATE,
                "parameters": HGB_PARAMETERS,
                "random_state": SEED,
                "early_stopping": False,
            },
            "support_rule": {
                "candidate_mse_strictly_below_parent_in_every_fold": True,
                "candidate_minus_parent_date_block_interval_upper_strictly_below_zero": True,
                "equal_game_calibration_slope_inclusive": list(CALIBRATION_RANGE),
                "positive_game_fraction_at_least": MINIMUM_POSITIVE_GAME_FRACTION,
            },
            "refutation_rule": "Missing any support condition refutes this fixed trainer candidate; no parameter search or substitute winner.",
            "opened_train_discovery_only": True,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "seed": SEED,
            "folds": folds,
            "harness_release_sha256": release["release_sha256"],
            "harness_commit": release["publication"]["commit"],
            "experiment_source_commit": current_commit(repo_root),
            "experiment_source_sha256": file_hash(Path(__file__).resolve()),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "research_record": "NFL_REPRESENTATION_TRAINER_ABLATION_RESEARCH_2026-09-16.md",
        }
        fresh_json(output / "pre_score_lock.json", lock)

        diagnostic = state_model_diagnostic(state_x, state_y, state_games)
        prior_diagnostic = load_json(Path(prior_representation) / "state_model_diagnostic.json")
        if diagnostic != prior_diagnostic:
            raise ValueError("historical state model diagnostic did not reproduce")
        state_scaler, state_model = fit_state_model(state_x, state_y, state_games)
        pre_states = np.asarray([market_state(row) for row in rows], dtype=float)
        state_wp_pre = state_model.predict_proba(state_scaler.transform(pre_states))[:, 1]
        state_wp_post = state_model.predict_proba(state_scaler.transform(post_states))[:, 1]
        derived = derived_without_state(rows)
        derived["state_wp_delta"] = state_wp_post - state_wp_pre
        if any(values.shape != (len(rows),) or not np.isfinite(values).all()
               for values in derived.values()):
            raise ValueError("frozen derived representation is incomplete or non-finite")

        game_to_indices: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            game_to_indices[row["game"]].append(index)
        predictions: list[float] = []
        check_order: list[int] = []
        candidate_folds = []
        fold_details = []
        for fold, parent_fold in zip(folds, parent_folds):
            fit_indices = np.asarray([
                index for game in fold["fit_games"] for index in game_to_indices[game]
            ], dtype=int)
            check_indices = np.asarray([
                index for game in fold["check_games"] for index in game_to_indices[game]
            ], dtype=int)
            x_fit, x_check, feature_names, preprocessing = matrices(
                rows, fit_indices, check_indices, derived, DERIVED
            )
            y_fit = np.asarray([rows[index]["target"] for index in fit_indices], dtype=float)
            weights = equal_game_weights(rows, fit_indices)
            model = HistGradientBoostingRegressor(
                **HGB_PARAMETERS, random_state=SEED, early_stopping=False
            ).fit(x_fit, y_fit, sample_weight=weights)
            prediction = np.asarray(model.predict(x_check), dtype=float)
            report = metrics(rows, check_indices, prediction)
            predictions.extend(prediction.tolist())
            check_order.extend(check_indices.tolist())
            candidate_folds.append(report)
            fold_details.append({
                "fold": fold["fold"],
                "fit_rows": len(fit_indices),
                "check_rows": len(check_indices),
                "feature_names": feature_names,
                "preprocessing": preprocessing,
                "parent_metrics": parent_fold,
                "candidate_metrics": {key: value for key, value in report.items() if key != "by_game"},
            })

        check_indices = np.asarray(check_order, dtype=int)
        if len(check_indices) != prior_result["rolling_check_rows"]:
            raise ValueError("rolling check population changed")
        candidate = metrics(rows, check_indices, np.asarray(predictions, dtype=float))
        parent = parent_report(prior_result, prior_diagnostics)
        paired = paired_against_parent(parent, candidate)
        conditions = support_conditions(candidate, candidate_folds, parent_folds, paired)
        support = supported(conditions)
        result = {
            "schema": "nfl_representation_trainer_ablation_result_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "same_support_full_rows": len(rows),
            "rolling_check_rows": len(check_indices),
            "parent": {
                key: value for key, value in parent.items()
                if key != "by_game"
            },
            "candidate": {
                **{key: value for key, value in candidate.items() if key != "by_game"},
                "fold_equal_game_candidate_mse": [
                    fold["equal_game_candidate_mse"] for fold in candidate_folds
                ],
            },
            "paired_against_parent": {
                key: value for key, value in paired.items() if key != "by_game"
            },
            "support_conditions": conditions,
            "support_rule_satisfied": support,
            "conclusion_status": (
                "opened_train_trainer_supported" if support
                else "opened_train_trainer_not_supported"
            ),
            "interpretation_boundary": (
                "Opened-Train trainer-only A/B. Historical provider event time is not live receive time; "
                "prediction skill is not executable PnL."
            ),
            "provider_cost_usd": "0",
            "route_dev_opened": False,
            "sealed_final_opened": False,
        }
        diagnostics = {
            "schema": "nfl_representation_trainer_ablation_diagnostics_v1",
            "folds": fold_details,
            "candidate_by_game": candidate["by_game"],
            "paired_against_parent": paired,
        }
        fresh_json(output / "result.json", result)
        fresh_json(output / "diagnostics.json", diagnostics)
        manifest = {
            "schema": "nfl_representation_trainer_ablation_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "result_sha256": file_hash(output / "result.json"),
            "diagnostics_sha256": file_hash(output / "diagnostics.json"),
            "provider_cost_usd": "0",
            "route_dev_opened": False,
            "sealed_final_opened": False,
        }
        fresh_json(output / "manifest.json", manifest)
        return result
    except Exception as error:
        fresh_json(output / "failure.json", {
            "schema": "nfl_representation_trainer_ablation_failure_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(error).__name__,
            "error": str(error),
            "provider_cost_usd": "0",
            "route_dev_opened": False,
            "sealed_final_opened": False,
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--target-materialization", type=Path, required=True)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--prior-representation", type=Path, required=True)
    parser.add_argument("--nflverse-history", type=Path, nargs="+", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.spec, args.target_materialization, args.panel_root,
        args.selection_root, args.release, args.prior_representation,
        args.nflverse_history, args.repo_root, args.output,
    )
    print({key: result[key] for key in (
        "support_rule_satisfied", "conclusion_status",
        "route_dev_opened", "sealed_final_opened",
    )})


if __name__ == "__main__":
    main()
