"""Run a Train-only, whole-game rolling trainer screen for NFL market response.

This is a human-directed harness diagnostic, not controller self-evolution or
formal promotion evidence.  It never reads Route-Dev or sealed Final market
data.  Every candidate uses the same rows, features, 60-second target, rolling
game folds, sample weights and primary equal-game MSE.  Only the trainer and
its preregistered hyperparameters change.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler


SEED = 23
TARGET = "home_change_60s"
NUMERIC_FEATURES = (
    "home_price_pre",
    "regulation_seconds_remaining",
    "period",
    "home_score_diff_pre",
    "possession_is_home",
    "down",
    "yards_to_first_down",
    "yards_to_goal",
    "official",
    "is_no_play",
    "is_scoring_play",
    "home_score_change",
    "away_score_change",
)
CATEGORICAL_FEATURES = ("play_type",)
METHODS = {
    "ridge": {"alpha": 1.0, "fit_intercept": True},
    "elastic_net": {"alpha": 0.0001, "l1_ratio": 0.5, "fit_intercept": True,
                    "max_iter": 20000, "tol": 1e-6},
    "random_forest": {"n_estimators": 200, "max_depth": 8,
                      "min_samples_leaf": 50, "max_features": 0.7},
    "hist_gradient_boosting": {"max_iter": 150, "learning_rate": 0.05,
                               "max_leaf_nodes": 31, "min_samples_leaf": 50,
                               "l2_regularization": 1.0},
}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def rolling_folds(games: list[str], initial_games: int = 100,
                  block_games: int = 21, blocks: int = 3) -> list[dict]:
    if len(games) != initial_games + block_games * blocks:
        raise ValueError("game population does not match frozen rolling design")
    if len(games) != len(set(games)):
        raise ValueError("duplicate game in rolling population")
    result = []
    for index in range(blocks):
        boundary = initial_games + index * block_games
        result.append({
            "fold": index + 1,
            "fit_games": games[:boundary],
            "check_games": games[boundary:boundary + block_games],
        })
    return result


def load_rows(panel_root: Path, selection_root: Path) -> tuple[list[dict], list[dict]]:
    selections = []
    for path in sorted(Path(selection_root).glob("*.selection.json")):
        row = json.loads(path.read_text())
        if row.get("split_role") != "market_train":
            raise ValueError("method screen selection contains non-Train game")
        if row.get("price_history_opened") is not False or row.get("trades_opened") is not False:
            raise ValueError("selection receipt was modified after split freeze")
        row["selection_path"] = str(path.resolve())
        row["selection_sha256"] = sha256(path)
        selections.append(row)
    selections.sort(key=lambda row: (row["scheduled_utc"], row["nflverse_game_id"]))
    if len(selections) != 163:
        raise ValueError("expected exact 163-game market_train population")
    if len({row["nflverse_game_id"] for row in selections}) != len(selections):
        raise ValueError("duplicate game selection")

    rows, receipts = [], []
    for selection in selections:
        game = selection["nflverse_game_id"]
        panel = Path(panel_root) / game / "play_trade_alignment.csv"
        manifest = Path(panel_root) / game / "manifest.json"
        if not panel.is_file() or not manifest.is_file():
            raise ValueError(f"missing panel or manifest for {game}")
        panel_manifest = json.loads(manifest.read_text())
        if panel_manifest.get("scientific_score") is not False:
            raise ValueError("alignment manifest unexpectedly contains a scientific score")
        if panel_manifest.get("selection_sha256") != selection["selection_sha256"]:
            raise ValueError(f"selection binding mismatch for {game}")
        loaded, missing_target = 0, 0
        with panel.open(newline="") as stream:
            reader = csv.DictReader(stream)
            required = set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + (TARGET, "play_id"))
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError(f"panel lacks frozen fields for {game}")
            for ordinal, raw in enumerate(reader):
                if raw[TARGET] == "":
                    missing_target += 1
                    continue
                if any(raw[name] == "" for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES):
                    raise ValueError(f"eligible target row has missing frozen feature in {game}")
                values = [float(raw[name]) for name in NUMERIC_FEATURES]
                target = float(raw[TARGET])
                if not np.isfinite(values).all() or not np.isfinite(target):
                    raise ValueError(f"non-finite feature or target in {game}")
                rows.append({
                    "game": game,
                    "game_date": selection["scheduled_utc"][:10],
                    "scheduled_utc": selection["scheduled_utc"],
                    "play_id": raw["play_id"],
                    "ordinal": ordinal,
                    "numeric": values,
                    "categorical": [raw[name] for name in CATEGORICAL_FEATURES],
                    "target": target,
                })
                loaded += 1
        receipts.append({
            "game": game,
            "scheduled_utc": selection["scheduled_utc"],
            "selection_path": selection["selection_path"],
            "selection_sha256": selection["selection_sha256"],
            "panel_path": str(panel.resolve()),
            "panel_sha256": sha256(panel),
            "alignment_manifest_sha256": sha256(manifest),
            "eligible_rows": loaded,
            "missing_60s_target_rows": missing_target,
        })
    if len({(row["game"], row["play_id"]) for row in rows}) != len(rows):
        raise ValueError("duplicate game/play row")
    return rows, receipts


def matrices(rows: list[dict], fit_indices: np.ndarray, check_indices: np.ndarray):
    numeric = np.asarray([row["numeric"] for row in rows], dtype=float)
    categorical = np.asarray([row["categorical"] for row in rows], dtype=object)
    scaler = StandardScaler().fit(numeric[fit_indices])
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=float).fit(
        categorical[fit_indices]
    )
    transformed = np.column_stack((scaler.transform(numeric), encoder.transform(categorical)))
    names = list(NUMERIC_FEATURES) + list(encoder.get_feature_names_out(CATEGORICAL_FEATURES))
    return transformed[fit_indices], transformed[check_indices], names, {
        "numeric_mean": scaler.mean_.tolist(),
        "numeric_scale": scaler.scale_.tolist(),
        "categorical_levels": [list(map(str, levels)) for levels in encoder.categories_],
    }


def equal_game_weights(rows: list[dict], indices: np.ndarray) -> np.ndarray:
    counts = Counter(rows[index]["game"] for index in indices)
    games = len(counts)
    return np.asarray([games / counts[rows[index]["game"]] for index in indices], dtype=float)


def estimator(method: str):
    parameters = METHODS[method]
    if method == "ridge":
        return Ridge(**parameters, solver="svd")
    if method == "elastic_net":
        return ElasticNet(**parameters, random_state=SEED, selection="cyclic")
    if method == "random_forest":
        return RandomForestRegressor(**parameters, random_state=SEED, n_jobs=1)
    return HistGradientBoostingRegressor(**parameters, random_state=SEED, early_stopping=False)


def correlation(left: np.ndarray, right: np.ndarray, rank: bool = False) -> float | None:
    if len(left) < 3 or np.std(left) == 0 or np.std(right) == 0:
        return None
    value = spearmanr(left, right).statistic if rank else np.corrcoef(left, right)[0, 1]
    return None if not np.isfinite(value) else float(value)


def block_interval(values: dict[str, list[float]], draws: int = 10000) -> dict:
    dates = sorted(values)
    if len(dates) < 2:
        return {"dates": len(dates), "lower": None, "upper": None, "draws": 0}
    date_values = np.asarray([float(np.mean(values[date])) for date in dates])
    rng = np.random.default_rng(SEED)
    samples = date_values[rng.integers(0, len(date_values), size=(draws, len(date_values)))].mean(axis=1)
    lower, upper = np.quantile(samples, [0.025, 0.975])
    return {"dates": len(dates), "lower": float(lower), "upper": float(upper), "draws": draws,
            "unit": "UTC_date_equal_weight"}


def metrics(rows: list[dict], indices: np.ndarray, prediction: np.ndarray) -> dict:
    target = np.asarray([rows[index]["target"] for index in indices], dtype=float)
    if prediction.shape != target.shape or not np.isfinite(prediction).all():
        raise ValueError("prediction is missing or non-finite")
    by_game, by_date = defaultdict(list), defaultdict(list)
    for position, index in enumerate(indices):
        by_game[rows[index]["game"]].append(position)
    games = []
    for game in sorted(by_game):
        local = np.asarray(by_game[game], dtype=int)
        baseline_mse = float(np.mean(np.square(target[local])))
        candidate_mse = float(np.mean(np.square(target[local] - prediction[local])))
        delta = candidate_mse - baseline_mse
        date = rows[indices[local[0]]]["game_date"]
        by_date[date].append(delta)
        games.append({
            "game": game,
            "date": date,
            "rows": len(local),
            "baseline_mse": baseline_mse,
            "candidate_mse": candidate_mse,
            "candidate_minus_baseline_mse": delta,
            "pearson_ic": correlation(prediction[local], target[local]),
            "rank_ic": correlation(prediction[local], target[local], rank=True),
        })
    baseline = float(np.mean([row["baseline_mse"] for row in games]))
    candidate = float(np.mean([row["candidate_mse"] for row in games]))
    slopes, intercepts = [], []
    for game, positions in by_game.items():
        local = np.asarray(positions, dtype=int)
        if len(local) >= 3 and np.std(prediction[local]) > 0:
            slope, intercept = np.polyfit(prediction[local], target[local], 1)
            slopes.append(float(slope)); intercepts.append(float(intercept))
    pearson = [row["pearson_ic"] for row in games if row["pearson_ic"] is not None]
    rank = [row["rank_ic"] for row in games if row["rank_ic"] is not None]
    return {
        "rows": len(indices),
        "games": len(games),
        "dates": len(by_date),
        "equal_game_baseline_mse": baseline,
        "equal_game_candidate_mse": candidate,
        "relative_mse_improvement": (baseline - candidate) / baseline if baseline else None,
        "row_weighted_baseline_mse": float(np.mean(np.square(target))),
        "row_weighted_candidate_mse": float(np.mean(np.square(target - prediction))),
        "positive_game_fraction": float(np.mean([row["candidate_mse"] < row["baseline_mse"] for row in games])),
        "positive_date_fraction": float(np.mean([np.mean(value) < 0 for value in by_date.values()])),
        "equal_game_pearson_ic": float(np.mean(pearson)) if pearson else None,
        "equal_game_rank_ic": float(np.mean(rank)) if rank else None,
        "equal_game_calibration_slope": float(np.mean(slopes)) if slopes else None,
        "equal_game_calibration_intercept": float(np.mean(intercepts)) if intercepts else None,
        "candidate_minus_baseline_date_block_interval": block_interval(by_date),
        "by_game": games,
    }


def raw_signal_diagnostics(rows: list[dict], indices: np.ndarray) -> dict:
    target = np.asarray([rows[index]["target"] for index in indices], dtype=float)
    features = np.asarray([rows[index]["numeric"] for index in indices], dtype=float)
    scaled = StandardScaler().fit_transform(features)
    standard_deviation = np.std(scaled, axis=0)
    active = np.flatnonzero(standard_deviation > 0)
    constant = [NUMERIC_FEATURES[index] for index in range(len(NUMERIC_FEATURES))
                if index not in set(active.tolist())]
    pairwise: list[list[float | None]] = [
        [None for _ in NUMERIC_FEATURES] for _ in NUMERIC_FEATURES
    ]
    if len(active):
        active_pairwise = np.atleast_2d(np.corrcoef(scaled[:, active], rowvar=False))
        for left_position, left in enumerate(active):
            for right_position, right in enumerate(active):
                pairwise[int(left)][int(right)] = float(active_pairwise[left_position, right_position])
    condition_value = float(np.linalg.cond(scaled[:, active])) if len(active) else None
    condition = condition_value if condition_value is None or np.isfinite(condition_value) else None
    output = {}
    for column, name in enumerate(NUMERIC_FEATURES):
        output[name] = {
            "pearson_ic": correlation(features[:, column], target),
            "rank_ic": correlation(features[:, column], target, rank=True),
        }
    return {
        "scope": "initial_100_market_train_games_only",
        "rows": len(indices),
        "numeric_features": output,
        "numeric_pairwise_correlation": pairwise,
        "numeric_condition_number_after_standardization": condition,
        "numeric_condition_number_finite": bool(condition_value is not None and np.isfinite(condition_value)),
        "numeric_matrix_rank": int(np.linalg.matrix_rank(scaled[:, active])) if len(active) else 0,
        "constant_numeric_features": constant,
        "automatic_feature_selection": False,
        "target_used_to_change_feature_set": False,
    }


def run(panel_root: Path, selection_root: Path, summary_manifest: Path, output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        summary = json.loads(Path(summary_manifest).read_text())
        if (summary.get("games") != 163 or summary.get("split_role") != "market_train"
                or summary.get("route_dev_opened") is not False
                or summary.get("sealed_final_opened") is not False
                or summary.get("scientific_score") is not False):
            raise ValueError("summary manifest does not prove sealed 163-game Train-only input")
        rows, receipts = load_rows(panel_root, selection_root)
        games = [row["game"] for row in receipts]
        folds = rolling_folds(games)
        game_to_indices = defaultdict(list)
        for index, row in enumerate(rows):
            game_to_indices[row["game"]].append(index)
        if any(not game_to_indices[game] for game in games):
            raise ValueError("game lacks an eligible 60-second label")

        spec = {
            "schema": "nfl_train_only_method_screen_spec_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "problem": "Does trainer choice improve 60-second post-play home-price-delta prediction on identical Train-only rows?",
            "changed_stage": "prediction_trainer_only",
            "target": TARGET,
            "horizon_seconds": 60,
            "features": {"numeric": list(NUMERIC_FEATURES), "categorical": list(CATEGORICAL_FEATURES)},
            "feature_observation": "pre-play state plus event result observable at the historical play timestamp",
            "excluded_feature": "free-text description",
            "methods": {"zero_change": {"prediction": 0.0}, **METHODS},
            "normalizer": "fold-fit StandardScaler on numeric fields; fold-fit one-hot play_type; no target fit",
            "train_weighting": "equal_game",
            "primary_metric": "equal_game_mse",
            "secondary_metrics": ["row_weighted_mse", "pearson_ic", "rank_ic", "calibration_slope",
                                  "positive_game_fraction", "UTC_date_block_interval"],
            "folds": folds,
            "selection_rule": "descriptive screen only; no winner is promoted and no hyperparameter is changed from this result",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "profitability_measured": False,
            "formal_promotion": False,
            "controller_self_evolution": False,
            "human_harness_diagnostic": True,
            "seed": SEED,
            "summary_manifest": str(Path(summary_manifest).resolve()),
            "summary_manifest_sha256": sha256(summary_manifest),
            "source_code_sha256": sha256(Path(__file__)),
            "input_receipts": receipts,
        }
        write_json(output / "pre_score_lock.json", spec)

        initial_indices = np.asarray([index for game in folds[0]["fit_games"]
                                      for index in game_to_indices[game]], dtype=int)
        raw = raw_signal_diagnostics(rows, initial_indices)
        write_json(output / "raw_signal_diagnostics.json", raw)

        predictions = {method: [] for method in METHODS}
        prediction_indices = []
        fold_reports = []
        for fold in folds:
            fit_indices = np.asarray([index for game in fold["fit_games"]
                                      for index in game_to_indices[game]], dtype=int)
            check_indices = np.asarray([index for game in fold["check_games"]
                                        for index in game_to_indices[game]], dtype=int)
            x_fit, x_check, feature_names, preprocessing = matrices(rows, fit_indices, check_indices)
            y_fit = np.asarray([rows[index]["target"] for index in fit_indices], dtype=float)
            weights = equal_game_weights(rows, fit_indices)
            report = {
                "fold": fold["fold"],
                "fit_games": len(fold["fit_games"]),
                "fit_rows": len(fit_indices),
                "check_games": len(fold["check_games"]),
                "check_rows": len(check_indices),
                "check_start": rows[check_indices[0]]["scheduled_utc"],
                "check_end": rows[check_indices[-1]]["scheduled_utc"],
                "feature_names": feature_names,
                "preprocessing": preprocessing,
                "methods": {},
            }
            for method in METHODS:
                model = estimator(method)
                model.fit(x_fit, y_fit, sample_weight=weights)
                prediction = np.asarray(model.predict(x_check), dtype=float)
                predictions[method].extend(prediction.tolist())
                report["methods"][method] = {
                    "parameters": model.get_params(deep=False),
                    "metrics": metrics(rows, check_indices, prediction),
                    "coefficients": model.coef_.tolist() if hasattr(model, "coef_") else None,
                    "feature_importances": (model.feature_importances_.tolist()
                                            if hasattr(model, "feature_importances_") else None),
                }
            prediction_indices.extend(check_indices.tolist())
            fold_reports.append(report)

        check_indices = np.asarray(prediction_indices, dtype=int)
        if len(check_indices) != len(set(check_indices.tolist())):
            raise ValueError("rolling check rows overlap")
        aggregate = {
            "zero_change": metrics(rows, check_indices, np.zeros(len(check_indices))),
            **{method: metrics(rows, check_indices, np.asarray(value, dtype=float))
               for method, value in predictions.items()},
        }
        result = {
            "schema": "nfl_train_only_method_screen_result_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "raw_signal_diagnostics_sha256": sha256(output / "raw_signal_diagnostics.json"),
            "folds": fold_reports,
            "aggregate": aggregate,
            "interpretation_boundary": "Train-only rolling diagnostic; no Route-Dev/Final, promotion, PnL or controller-learning claim",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "scientific_score": False,
        }
        write_json(output / "result.json", result)
        manifest = {
            "schema": "nfl_train_only_method_screen_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "raw_signal_diagnostics_sha256": sha256(output / "raw_signal_diagnostics.json"),
            "result_sha256": sha256(output / "result.json"),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "scientific_score": False,
        }
        write_json(output / "manifest.json", manifest)
        return result
    except Exception as error:
        write_json(output / "failure.json", {
            "schema": "nfl_train_only_method_screen_failure_v1",
            "error_type": type(error).__name__,
            "error": str(error),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "scientific_score": False,
        })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--summary-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.panel_root, args.selection_root, args.summary_manifest, args.output)
    compact = {method: {key: value for key, value in metrics.items() if key != "by_game"}
               for method, metrics in result["aggregate"].items()}
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
