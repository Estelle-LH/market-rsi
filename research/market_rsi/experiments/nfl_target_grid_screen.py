"""Screen a frozen NFL target grid on opened Train with rolling whole-game folds.

Each target is evaluated against its own zero-change baseline.  Different
target scales and eligible populations are never compared by raw MSE.  This is
opened-Train discovery, not formal target selection or sealed evidence.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

from data_scientist_harness.target_discovery_contract import (
    verify_frozen_target_discovery_spec,
)
from market_rsi import digest, file_hash, fresh_json, load_json
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


def verify_release(path: Path) -> dict:
    release = load_json(path)
    unsigned = {key: value for key, value in release.items() if key != "release_sha256"}
    if (release.get("harness_version") != "data-scientist-harness-v1.6.2"
            or release.get("publication", {}).get("tag") != "dsh-v1.6.2"
            or release.get("release_sha256") != digest(unsigned)):
        raise ValueError("published dsh-v1.6.2 release required")
    return release


def load_target_map(path: Path, names: list[str]) -> tuple[dict[tuple[str, str], dict], list[str]]:
    targets: dict[tuple[str, str], dict] = {}
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"game", "scheduled_utc", "play_id", "eligible_for_common_comparison", *names}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("target panel lacks frozen fields")
        for raw in reader:
            key = (raw["game"], raw["play_id"])
            if key in targets:
                raise ValueError("duplicate game/play in target panel")
            values = {name: (None if raw[name] == "" else float(raw[name])) for name in names}
            observed = [value for value in values.values() if value is not None]
            if not np.isfinite(observed).all():
                raise ValueError("non-finite target value")
            common = raw["eligible_for_common_comparison"] == "1"
            if common != all(value is not None for value in values.values()):
                raise ValueError("common-support marker is inconsistent")
            targets[key] = {
                "scheduled_utc": raw["scheduled_utc"],
                "targets": values,
                "common": common,
            }
    if not targets:
        raise ValueError("empty target panel")
    return targets, names


def feature_values(raw: dict, target: dict) -> tuple[list[float], list[str]] | None:
    missing = [name for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES if raw[name] == ""]
    if missing:
        if any(value is not None for value in target["targets"].values()):
            raise ValueError("row with an observed target has a missing frozen feature")
        return None
    numeric = [float(raw[name]) for name in NUMERIC_FEATURES]
    if not np.isfinite(numeric).all():
        raise ValueError("non-finite feature value")
    return numeric, [raw[name] for name in CATEGORICAL_FEATURES]


def load_rows(panel_root: Path, selection_root: Path, target_map: dict,
              target_names_list: list[str]) -> tuple[list[dict], list[dict]]:
    selections = []
    for path in sorted(Path(selection_root).glob("*.selection.json")):
        selection = load_json(path)
        if selection.get("split_role") != "market_train":
            raise ValueError("target screen received a non-Train selection")
        if selection.get("price_history_opened") is not False or selection.get("trades_opened") is not False:
            raise ValueError("selection receipt was modified after split freeze")
        selection["path"] = path.resolve()
        selection["sha256"] = file_hash(path)
        selections.append(selection)
    selections.sort(key=lambda row: (row["scheduled_utc"], row["nflverse_game_id"]))
    if len(selections) != 163 or len({row["nflverse_game_id"] for row in selections}) != 163:
        raise ValueError("expected exact 163-game market_train population")

    rows, receipts, consumed = [], [], set()
    required = set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + ("play_id",))
    for selection in selections:
        game = selection["nflverse_game_id"]
        panel = Path(panel_root) / game / "play_trade_alignment.csv"
        manifest = Path(panel_root) / game / "manifest.json"
        if not panel.is_file() or not manifest.is_file():
            raise ValueError(f"missing panel or manifest for {game}")
        alignment = load_json(manifest)
        if alignment.get("scientific_score") is not False:
            raise ValueError("alignment manifest unexpectedly contains a scientific score")
        if alignment.get("selection_sha256") != selection["sha256"]:
            raise ValueError(f"selection binding mismatch for {game}")
        eligible = {name: 0 for name in target_names_list}
        total = feature_ineligible_no_target = 0
        with panel.open(newline="") as stream:
            reader = csv.DictReader(stream)
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError(f"feature panel lacks frozen fields for {game}")
            for ordinal, raw in enumerate(reader):
                total += 1
                key = (game, raw["play_id"])
                target = target_map.get(key)
                if target is None:
                    raise ValueError(f"target panel lacks feature row {game}/{raw['play_id']}")
                if target["scheduled_utc"] != selection["scheduled_utc"]:
                    raise ValueError("target and selection schedule mismatch")
                for name, value in target["targets"].items():
                    eligible[name] += int(value is not None)
                consumed.add(key)
                values = feature_values(raw, target)
                if values is None:
                    feature_ineligible_no_target += 1
                    continue
                numeric, categorical = values
                rows.append({
                    "game": game,
                    "game_date": selection["scheduled_utc"][:10],
                    "scheduled_utc": selection["scheduled_utc"],
                    "play_id": raw["play_id"],
                    "ordinal": ordinal,
                    "numeric": numeric,
                    "categorical": categorical,
                    "targets": target["targets"],
                    "common": target["common"],
                })
        receipts.append({
            "game": game,
            "scheduled_utc": selection["scheduled_utc"],
            "selection_sha256": selection["sha256"],
            "feature_panel_sha256": file_hash(panel),
            "alignment_manifest_sha256": file_hash(manifest),
            "total_play_rows": total,
            "feature_ineligible_no_target_rows": feature_ineligible_no_target,
            "eligible_rows_by_target": eligible,
        })
    if consumed != set(target_map):
        raise ValueError("target panel contains rows outside the frozen feature population")
    if len({(row["game"], row["play_id"]) for row in rows}) != len(rows):
        raise ValueError("duplicate merged game/play row")
    return rows, receipts


def estimator(method: str):
    if method == "ridge":
        return Ridge(**METHODS[method])
    return RandomForestRegressor(**METHODS[method])


def target_view(rows: list[dict], name: str) -> list[dict]:
    return [{
        "game": row["game"],
        "game_date": row["game_date"],
        "target": row["targets"][name],
    } for row in rows]


def target_profile(view: list[dict], indices: np.ndarray, total_rows: int) -> dict:
    by_game: dict[str, list[float]] = defaultdict(list)
    values = []
    for index in indices:
        value = float(view[index]["target"])
        values.append(value)
        by_game[view[index]["game"]].append(value)
    array = np.asarray(values, dtype=float)
    return {
        "rolling_check_rows": len(array),
        "rolling_check_games": len(by_game),
        "full_population_coverage": sum(row["target"] is not None for row in view) / total_rows,
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array)),
        "mean_absolute_change": float(np.mean(np.abs(array))),
        "exact_zero_fraction": float(np.mean(array == 0)),
        "equal_game_zero_change_mse": float(np.mean([
            np.mean(np.square(np.asarray(game_values, dtype=float)))
            for game_values in by_game.values()
        ])),
    }


def shortlist(results: dict) -> list[dict]:
    candidates = []
    for name, target in results.items():
        for method, report in target["methods"].items():
            fold_skills = [fold["methods"][method]["relative_mse_improvement"]
                           for fold in target["folds"]]
            interval = report["candidate_minus_baseline_date_block_interval"]
            if (all(value is not None and value > 0 for value in fold_skills)
                    and report["relative_mse_improvement"] > 0
                    and report["positive_game_fraction"] > 0.5
                    and interval["upper"] is not None and interval["upper"] < 0
                    and target["profile"]["full_population_coverage"] >= 0.5):
                candidates.append({
                    "target": name,
                    "method": method,
                    "minimum_fold_relative_improvement": min(fold_skills),
                    "aggregate_relative_improvement": report["relative_mse_improvement"],
                    "coverage": target["profile"]["full_population_coverage"],
                    "status": "opened_train_shortlist_only",
                })
    candidates.sort(key=lambda row: (
        -row["minimum_fold_relative_improvement"],
        -row["aggregate_relative_improvement"],
        -row["coverage"], row["target"], row["method"],
    ))
    chosen, seen = [], set()
    for candidate in candidates:
        if candidate["target"] in seen:
            continue
        chosen.append(candidate)
        seen.add(candidate["target"])
        if len(chosen) == 3:
            break
    return chosen


def run(spec_path: Path, target_materialization: Path, panel_root: Path,
        selection_root: Path, release_path: Path, repo_root: Path,
        output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        release = verify_release(release_path)
        frozen = load_json(spec_path)
        spec = verify_frozen_target_discovery_spec(frozen)
        names = [name for name, _, _ in target_names(spec)]
        materialization = Path(target_materialization)
        manifest = load_json(materialization / "manifest.json")
        if (manifest.get("complete") is not True
                or manifest.get("route_dev_opened") is not False
                or manifest.get("sealed_final_opened") is not False
                or manifest.get("frozen_target_spec_sha256") != frozen["record_sha256"]
                or manifest.get("target_spec_file_sha256") != file_hash(spec_path)
                or manifest.get("target_panel_sha256") != file_hash(materialization / "target_panel.csv")
                or manifest.get("summary_sha256") != file_hash(materialization / "summary.json")):
            raise ValueError("target materialization receipt is invalid")
        source = Path(__file__).resolve()
        lock = {
            "schema": "nfl_open_train_target_grid_screen_lock_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "question": "Which clock-time or event-time targets show stable predictive skill on opened Train?",
            "hypothesis": "At least one target has positive skill beyond zero change across every rolling fold without date-block concentration.",
            "support_rule": {
                "all_three_fold_relative_mse_improvements_positive": True,
                "aggregate_relative_mse_improvement_positive": True,
                "positive_game_fraction_strictly_above": 0.5,
                "candidate_minus_baseline_date_block_interval_upper_strictly_below": 0,
                "minimum_full_population_coverage": 0.5,
            },
            "refutation_rule": "No target-method pair meets every support condition.",
            "shortlist_rule": "Rank qualifying pairs by minimum fold skill, aggregate skill, then coverage; retain at most three unique targets.",
            "target_comparison_warning": "Raw MSE is never compared across target definitions; each target uses its own zero-change baseline and eligible rows.",
            "discovery_only": True,
            "rolling_design": {"initial_games": 100, "block_games": 21, "blocks": 3},
            "numeric_features": list(NUMERIC_FEATURES),
            "categorical_features": list(CATEGORICAL_FEATURES),
            "methods": METHODS,
            "seed": SEED,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "frozen_target_spec_sha256": frozen["record_sha256"],
            "target_materialization_manifest_sha256": file_hash(materialization / "manifest.json"),
            "harness_release_sha256": release["release_sha256"],
            "harness_commit": release["publication"]["commit"],
            "experiment_source_commit": current_commit(repo_root),
            "experiment_source_sha256": file_hash(source),
            "research_sources": [
                "https://doi.org/10.1016/j.ijforecast.2004.08.004",
                "https://doi.org/10.1080/07350015.2019.1620074",
                "https://doi.org/10.1145/3534678.3539462",
                "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=423921",
            ],
        }
        fresh_json(output / "pre_score_lock.json", lock)

        target_map, _ = load_target_map(materialization / "target_panel.csv", names)
        rows, receipts = load_rows(panel_root, selection_root, target_map, names)
        ordered_games = [receipt["game"] for receipt in receipts]
        folds = rolling_folds(ordered_games)
        game_to_indices: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            game_to_indices[row["game"]].append(index)

        results = {}
        for name in names:
            view = target_view(rows, name)
            predictions = {method: [] for method in METHODS}
            prediction_indices, fold_results = [], []
            for fold in folds:
                fit_indices = np.asarray([
                    index for game in fold["fit_games"] for index in game_to_indices[game]
                    if view[index]["target"] is not None
                ], dtype=int)
                check_indices = np.asarray([
                    index for game in fold["check_games"] for index in game_to_indices[game]
                    if view[index]["target"] is not None
                ], dtype=int)
                if not len(fit_indices) or not len(check_indices):
                    raise ValueError(f"empty rolling support for {name}")
                x_fit, x_check, feature_names, preprocessing = matrices(
                    rows, fit_indices, check_indices
                )
                y_fit = np.asarray([view[index]["target"] for index in fit_indices], dtype=float)
                weights = equal_game_weights(rows, fit_indices)
                fold_report = {
                    "fold": fold["fold"],
                    "fit_games": len(set(rows[index]["game"] for index in fit_indices)),
                    "fit_rows": len(fit_indices),
                    "check_games": len(set(rows[index]["game"] for index in check_indices)),
                    "check_rows": len(check_indices),
                    "methods": {},
                    "feature_names": feature_names,
                    "preprocessing": preprocessing,
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
                    method: metrics(view, check_indices, np.asarray(values, dtype=float))
                    for method, values in predictions.items()
                },
                "folds": fold_results,
            }

        opened_train_shortlist = shortlist(results)
        public_summary = {
            name: {
                "profile": result["profile"],
                "methods": {method: {
                    key: report[key] for key in (
                        "equal_game_baseline_mse", "equal_game_candidate_mse",
                        "relative_mse_improvement", "positive_game_fraction",
                        "positive_date_fraction", "equal_game_pearson_ic",
                        "equal_game_rank_ic", "equal_game_calibration_slope",
                        "candidate_minus_baseline_date_block_interval",
                    )
                } for method, report in result["methods"].items()},
                "fold_relative_mse_improvements": {
                    method: [fold["methods"][method]["relative_mse_improvement"]
                             for fold in result["folds"]]
                    for method in METHODS
                },
            }
            for name, result in results.items()
        }
        fresh_json(output / "input_receipts.json", {
            "schema": "nfl_open_train_target_grid_screen_inputs_v1",
            "target_materialization_manifest_sha256": file_hash(materialization / "manifest.json"),
            "games": receipts,
        })
        result = {
            "schema": "nfl_open_train_target_grid_screen_result_v1",
            "games": len(ordered_games),
            "plays": len(rows),
            "targets": results,
            "public_summary": public_summary,
            "opened_train_shortlist": opened_train_shortlist,
            "support_rule_satisfied": bool(opened_train_shortlist),
            "conclusion_status": "opened_train_discovery_not_formal_selection",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
        }
        fresh_json(output / "result.json", result)
        fresh_json(output / "manifest.json", {
            "schema": "nfl_open_train_target_grid_screen_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "result_sha256": file_hash(output / "result.json"),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        })
        return {"public_summary": public_summary, "opened_train_shortlist": opened_train_shortlist}
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
