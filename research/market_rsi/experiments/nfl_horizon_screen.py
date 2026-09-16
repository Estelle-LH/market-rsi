"""Opened-Train screen of available NFL price-change horizons.

This is a discovery experiment, not a formal confirmation.  It compares
already-materialized 30, 60 and 300 second targets on exactly the same plays,
games, rolling folds, features and two fixed trainers.  Route-Dev and Final are
never read.  The available trio is a first executable screen, not a global
horizon library or permission to select a future Dev result post hoc.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from market_rsi import digest, file_hash, fresh_json
from sports_event_research.run_train_local_projection import (
    CONTROL_FEATURES,
    HORIZONS,
    SCORE_FEATURES,
    load_common_support,
)
from sports_event_research.run_train_method_screen import (
    SEED,
    block_interval,
    equal_game_weights,
    metrics,
    rolling_folds,
)


METHODS = {
    "ridge": {"alpha": 1.0, "fit_intercept": True, "solver": "svd"},
    "random_forest": {
        "n_estimators": 200,
        "max_depth": 8,
        "min_samples_leaf": 50,
        "max_features": 0.7,
        "random_state": SEED,
        "n_jobs": 1,
    },
}


def current_commit(root: Path) -> str:
    value = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("full experiment source commit required")
    return value


def matrices(rows: list[dict], fit_indices: np.ndarray, check_indices: np.ndarray):
    raw = np.asarray([row["features"] for row in rows], dtype=float)
    scaler = StandardScaler().fit(raw[fit_indices])
    return scaler.transform(raw[fit_indices]), scaler.transform(raw[check_indices]), {
        "feature_names": list(SCORE_FEATURES + CONTROL_FEATURES),
        "fit_mean": scaler.mean_.tolist(),
        "fit_scale": scaler.scale_.tolist(),
    }


def rows_for_metric(rows: list[dict], horizon: int) -> list[dict]:
    return [{
        "game": row["game"],
        "game_date": row["scheduled_utc"][:10],
        "target": row["outcomes"][str(horizon)],
    } for row in rows]


def target_profile(rows: list[dict], indices: np.ndarray, horizon: int) -> dict:
    values = np.asarray([rows[index]["outcomes"][str(horizon)] for index in indices], dtype=float)
    games: dict[str, list[float]] = defaultdict(list)
    for index in indices:
        games[rows[index]["game"]].append(rows[index]["outcomes"][str(horizon)])
    return {
        "rows": len(values),
        "games": len(games),
        "mean": float(np.mean(values)),
        "standard_deviation": float(np.std(values)),
        "mean_absolute_change": float(np.mean(np.abs(values))),
        "exact_zero_fraction": float(np.mean(values == 0)),
        "equal_game_zero_change_mse": float(np.mean([
            np.mean(np.square(np.asarray(game_values, dtype=float)))
            for game_values in games.values()
        ])),
    }


def fit_method(method: str, x_fit: np.ndarray, y_fit: np.ndarray, weights: np.ndarray):
    if method == "ridge":
        return Ridge(**METHODS[method]).fit(x_fit, y_fit, sample_weight=weights)
    return RandomForestRegressor(**METHODS[method]).fit(x_fit, y_fit, sample_weight=weights)


def run(panel_root: Path, selection_root: Path, release_path: Path,
        repo_root: Path, output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        release = json.loads(Path(release_path).read_text())
        if (release.get("harness_version") != "data-scientist-harness-v1.6.1"
                or release.get("publication", {}).get("tag") != "dsh-v1.6.1"
                or release.get("release_sha256") != digest({
                    key: value for key, value in release.items() if key != "release_sha256"
                })):
            raise ValueError("published dsh-v1.6.1 release required")
        source = Path(__file__).resolve()
        commit = current_commit(repo_root)
        lock = {
            "schema": "nfl_open_train_horizon_screen_lock_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "question": "Does the existing evidence support keeping 60 seconds over other already-materialized horizons?",
            "discovery_only": True,
            "candidate_horizons_seconds": list(HORIZONS),
            "candidate_set_is_exhaustive": False,
            "same_common_support_required": True,
            "train_games": 163,
            "rolling_design": {"initial_games": 100, "block_games": 21, "blocks": 3},
            "features": list(SCORE_FEATURES + CONTROL_FEATURES),
            "methods": METHODS,
            "baseline": "zero price change",
            "primary_discovery_view": "relative equal-game MSE skill versus zero change",
            "selection_status": "no formal horizon selection from opened Train",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "seed": SEED,
            "harness_release_sha256": release["release_sha256"],
            "harness_commit": release["publication"]["commit"],
            "experiment_source_commit": commit,
            "experiment_source_sha256": file_hash(source),
            "research_sources": [
                "https://doi.org/10.1257/0002828053828518",
                "https://doi.org/10.1111/1468-0262.00152",
                "https://doi.org/10.1198/073500105000000063",
            ],
        }
        fresh_json(output / "pre_score_lock.json", lock)

        rows, receipts = load_common_support(panel_root, selection_root)
        ordered_games = [row["game"] for row in receipts]
        folds = rolling_folds(ordered_games)
        game_to_indices: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            game_to_indices[row["game"]].append(index)
        all_check_indices = np.asarray([
            index for fold in folds for game in fold["check_games"]
            for index in game_to_indices[game]
        ], dtype=int)
        if len(all_check_indices) != len(set(all_check_indices.tolist())):
            raise ValueError("rolling check rows overlap")

        results = {}
        for horizon in HORIZONS:
            metric_rows = rows_for_metric(rows, horizon)
            predictions = {method: [] for method in METHODS}
            prediction_indices = []
            fold_results = []
            for fold in folds:
                fit_indices = np.asarray([
                    index for game in fold["fit_games"] for index in game_to_indices[game]
                ], dtype=int)
                check_indices = np.asarray([
                    index for game in fold["check_games"] for index in game_to_indices[game]
                ], dtype=int)
                x_fit, x_check, preprocessing = matrices(rows, fit_indices, check_indices)
                y_fit = np.asarray([
                    rows[index]["outcomes"][str(horizon)] for index in fit_indices
                ], dtype=float)
                weights = equal_game_weights(metric_rows, fit_indices)
                report = {"fold": fold["fold"], "fit_games": len(fold["fit_games"]),
                          "check_games": len(fold["check_games"]), "methods": {}}
                for method in METHODS:
                    model = fit_method(method, x_fit, y_fit, weights)
                    prediction = np.asarray(model.predict(x_check), dtype=float)
                    predictions[method].extend(prediction.tolist())
                    report["methods"][method] = metrics(metric_rows, check_indices, prediction)
                report["preprocessing"] = preprocessing
                prediction_indices.extend(check_indices.tolist())
                fold_results.append(report)
            check_indices = np.asarray(prediction_indices, dtype=int)
            results[str(horizon)] = {
                "target_profile_on_rolling_checks": target_profile(rows, check_indices, horizon),
                "methods": {
                    method: metrics(metric_rows, check_indices, np.asarray(values, dtype=float))
                    for method, values in predictions.items()
                },
                "folds": fold_results,
            }

        public_summary = {}
        for horizon, row in results.items():
            public_summary[horizon] = {
                "target_profile": row["target_profile_on_rolling_checks"],
                "methods": {method: {
                    key: report[key] for key in (
                        "equal_game_baseline_mse", "equal_game_candidate_mse",
                        "relative_mse_improvement", "positive_game_fraction",
                        "positive_date_fraction", "equal_game_pearson_ic",
                        "equal_game_rank_ic", "candidate_minus_baseline_date_block_interval",
                    )
                } for method, report in row["methods"].items()},
            }
        result = {
            "schema": "nfl_open_train_horizon_screen_result_v1",
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "games": len(ordered_games),
            "common_support_rows": len(rows),
            "rolling_check_rows": len(all_check_indices),
            "horizons": results,
            "public_summary": public_summary,
            "conclusion_status": "opened_train_discovery_not_formal_selection",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        fresh_json(output / "input_receipts.json", {
            "schema": "nfl_open_train_horizon_screen_inputs_v1", "games": receipts,
        })
        result["input_receipts_sha256"] = file_hash(output / "input_receipts.json")
        fresh_json(output / "result.json", result)
        manifest = {
            "schema": "nfl_open_train_horizon_screen_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "result_sha256": file_hash(output / "result.json"),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        fresh_json(output / "manifest.json", manifest)
        return public_summary
    except Exception as error:
        fresh_json(output / "failure.json", {
            "error_type": type(error).__name__, "error": str(error)[:2000],
            "automatic_retry": False, "route_dev_opened": False,
            "sealed_final_opened": False, "provider_cost_usd": "0",
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.panel_root, args.selection_root, args.release,
                         args.repo_root, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
