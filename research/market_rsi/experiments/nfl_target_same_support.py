"""Check the 15--60 second target neighborhood on identical opened-Train rows."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from data_scientist_harness.target_discovery_contract import (
    verify_frozen_target_discovery_spec,
)
from experiments.nfl_target_grid_screen import (
    METHODS,
    current_commit,
    estimator,
    load_rows,
    load_target_map,
    target_profile,
    target_view,
    verify_release,
)
from market_rsi import file_hash, fresh_json, load_json
from sports_event_research.materialize_controller_targets import target_names
from sports_event_research.run_train_method_screen import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    SEED,
    equal_game_weights,
    matrices,
    metrics,
    rolling_folds,
)


TARGETS = (
    "elapsed_15s_delta",
    "elapsed_20s_delta",
    "elapsed_30s_delta",
    "elapsed_45s_delta",
    "elapsed_60s_delta",
)


def common_indices(rows: list[dict], games: list[str]) -> np.ndarray:
    game_set = set(games)
    return np.asarray([
        index for index, row in enumerate(rows)
        if row["game"] in game_set
        and all(row["targets"][name] is not None for name in TARGETS)
    ], dtype=int)


def ranking(results: dict, method: str) -> list[dict]:
    ranked = [{
        "target": name,
        "relative_mse_improvement": result["methods"][method]["relative_mse_improvement"],
        "minimum_fold_relative_improvement": min(
            fold["methods"][method]["relative_mse_improvement"] for fold in result["folds"]
        ),
    } for name, result in results.items()]
    ranked.sort(key=lambda row: (
        -row["minimum_fold_relative_improvement"],
        -row["relative_mse_improvement"],
        row["target"],
    ))
    return ranked


def run(spec_path: Path, target_materialization: Path, panel_root: Path,
        selection_root: Path, release_path: Path, repo_root: Path,
        output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        release = verify_release(release_path)
        frozen = load_json(spec_path)
        spec = verify_frozen_target_discovery_spec(frozen)
        expected = {f"elapsed_{value}s_delta" for value in spec["elapsed_horizons_seconds"]}
        if not set(TARGETS).issubset(expected) or spec["target_transform"] != "price_delta":
            raise ValueError("frozen spec lacks the same-support target neighborhood")
        materialization = Path(target_materialization)
        manifest = load_json(materialization / "manifest.json")
        if (manifest.get("complete") is not True
                or manifest.get("route_dev_opened") is not False
                or manifest.get("sealed_final_opened") is not False
                or manifest.get("frozen_target_spec_sha256") != frozen["record_sha256"]
                or manifest.get("target_panel_sha256") != file_hash(materialization / "target_panel.csv")):
            raise ValueError("target materialization receipt is invalid")

        lock = {
            "schema": "nfl_open_train_target_same_support_lock_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "question": "Does the apparent 30--45 second peak persist when 15--60 second targets use identical plays?",
            "hypothesis": "A 30 or 45 second target ranks in the top two by minimum-fold skill for both fixed methods.",
            "support_rule": "30s or 45s must appear in each method's top two when ranked by minimum fold relative MSE skill.",
            "refutation_rule": "Neither 30s nor 45s appears in the top two for at least one fixed method.",
            "ranking_tie_break": "minimum fold skill, aggregate skill, target name",
            "targets": list(TARGETS),
            "same_rows_for_every_target": True,
            "rolling_design": {"initial_games": 100, "block_games": 21, "blocks": 3},
            "numeric_features": list(NUMERIC_FEATURES),
            "categorical_features": list(CATEGORICAL_FEATURES),
            "methods": METHODS,
            "seed": SEED,
            "discovery_only": True,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "frozen_target_spec_sha256": frozen["record_sha256"],
            "target_materialization_manifest_sha256": file_hash(materialization / "manifest.json"),
            "harness_release_sha256": release["release_sha256"],
            "harness_commit": release["publication"]["commit"],
            "experiment_source_commit": current_commit(repo_root),
            "experiment_source_sha256": file_hash(Path(__file__)),
            "research_sources": [
                "https://doi.org/10.1016/j.ijforecast.2004.08.004",
                "https://doi.org/10.1080/07350015.2019.1620074",
            ],
        }
        fresh_json(output / "pre_score_lock.json", lock)

        all_target_names = [name for name, _, _ in target_names(spec)]
        target_map, _ = load_target_map(materialization / "target_panel.csv", all_target_names)
        rows, receipts = load_rows(panel_root, selection_root, target_map, all_target_names)
        ordered_games = [receipt["game"] for receipt in receipts]
        folds = rolling_folds(ordered_games)
        results = {}
        for name in TARGETS:
            view = target_view(rows, name)
            predictions = {method: [] for method in METHODS}
            prediction_indices, fold_results = [], []
            for fold in folds:
                fit_indices = common_indices(rows, fold["fit_games"])
                check_indices = common_indices(rows, fold["check_games"])
                if not len(fit_indices) or not len(check_indices):
                    raise ValueError("empty same-support rolling block")
                x_fit, x_check, feature_names, preprocessing = matrices(
                    rows, fit_indices, check_indices
                )
                y_fit = np.asarray([view[index]["target"] for index in fit_indices], dtype=float)
                weights = equal_game_weights(rows, fit_indices)
                fold_report = {
                    "fold": fold["fold"],
                    "fit_rows": len(fit_indices),
                    "check_rows": len(check_indices),
                    "fit_games": len(set(rows[index]["game"] for index in fit_indices)),
                    "check_games": len(set(rows[index]["game"] for index in check_indices)),
                    "feature_names": feature_names,
                    "preprocessing": preprocessing,
                    "methods": {},
                }
                for method in METHODS:
                    model = estimator(method).fit(x_fit, y_fit, sample_weight=weights)
                    prediction = np.asarray(model.predict(x_check), dtype=float)
                    predictions[method].extend(prediction.tolist())
                    fold_report["methods"][method] = metrics(view, check_indices, prediction)
                prediction_indices.extend(check_indices.tolist())
                fold_results.append(fold_report)
            check_indices = np.asarray(prediction_indices, dtype=int)
            results[name] = {
                "profile": target_profile(view, check_indices, len(target_map)),
                "methods": {
                    method: metrics(view, check_indices, np.asarray(prediction, dtype=float))
                    for method, prediction in predictions.items()
                },
                "folds": fold_results,
            }

        rankings = {method: ranking(results, method) for method in METHODS}
        top_two = {method: {row["target"] for row in values[:2]}
                   for method, values in rankings.items()}
        support = all(
            bool({"elapsed_30s_delta", "elapsed_45s_delta"} & values)
            for values in top_two.values()
        )
        public_summary = {
            name: {
                "profile": result["profile"],
                "methods": {method: {
                    "relative_mse_improvement": report["relative_mse_improvement"],
                    "positive_game_fraction": report["positive_game_fraction"],
                    "equal_game_pearson_ic": report["equal_game_pearson_ic"],
                    "equal_game_calibration_slope": report["equal_game_calibration_slope"],
                    "candidate_minus_baseline_date_block_interval": report[
                        "candidate_minus_baseline_date_block_interval"
                    ],
                    "fold_relative_mse_improvements": [
                        fold["methods"][method]["relative_mse_improvement"]
                        for fold in result["folds"]
                    ],
                } for method, report in result["methods"].items()},
            } for name, result in results.items()
        }
        fresh_json(output / "input_receipts.json", {
            "schema": "nfl_open_train_target_same_support_inputs_v1",
            "target_materialization_manifest_sha256": file_hash(materialization / "manifest.json"),
            "games": receipts,
        })
        result = {
            "schema": "nfl_open_train_target_same_support_result_v1",
            "games": len(ordered_games),
            "source_plays": len(target_map),
            "design_matrix_rows": len(rows),
            "same_support_full_rows": len(common_indices(rows, ordered_games)),
            "public_summary": public_summary,
            "rankings": rankings,
            "support_rule_satisfied": support,
            "conclusion_status": "opened_train_sensitivity_not_formal_selection",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
        }
        fresh_json(output / "result.json", result)
        fresh_json(output / "manifest.json", {
            "schema": "nfl_open_train_target_same_support_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "result_sha256": file_hash(output / "result.json"),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        })
        return {"support_rule_satisfied": support, "rankings": rankings,
                "public_summary": public_summary}
    except Exception as error:
        fresh_json(output / "failure.json", {
            "error_type": type(error).__name__,
            "error": str(error)[:2000],
            "automatic_retry": False,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--target-materialization", type=Path, required=True)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.target_materialization, args.panel_root,
                 args.selection_root, args.release, args.repo_root, args.output)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
