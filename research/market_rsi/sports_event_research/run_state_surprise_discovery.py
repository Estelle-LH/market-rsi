"""Train-only discovery: represent an NFL play by its estimated win-probability surprise.

The state model learns final home-win probability from 2021-2024 public
play-by-play only.  It never reads market prices.  On the already-open 2025
market Train split, this script compares the same fixed Ridge trainer with and
without three representation features: state win probability before the play,
its play-to-play change, and the gap between state probability and market
price.  Target, rows, rolling folds, weighting and score stay unchanged.

This is adaptive discovery on opened Train, not Route-Dev evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import log_loss
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from sports_event_research.run_train_method_screen import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    SEED,
    TARGET,
    equal_game_weights,
    load_rows,
    metrics,
    rolling_folds,
    sha256,
    write_json,
)
from sports_event_research.build_play_trade_canary import clock_seconds, field_yards_to_goal


STATE_FEATURES = (
    "time_fraction",
    "home_score_diff",
    "score_urgency",
    "period",
    "possession_is_home",
    "down",
    "yards_to_first_down",
    "yards_to_goal",
    "field_position_for_home",
)
REPRESENTATION_FEATURES = ("state_wp_pre", "state_wp_delta", "state_market_gap")


def number(value, default=0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if math.isfinite(parsed) else float(default)


def state_vector(*, seconds: float, score_diff: float, period: float,
                 possession_is_home: float, down: float, yards_to_first: float,
                 yards_to_goal: float) -> list[float]:
    seconds = min(3600.0, max(0.0, seconds))
    possession_is_home = 1.0 if possession_is_home else 0.0
    yards_to_goal = min(100.0, max(0.0, yards_to_goal))
    home_field_position = 100.0 - yards_to_goal if possession_is_home else yards_to_goal
    return [
        seconds / 3600.0,
        score_diff,
        score_diff / math.sqrt(seconds + 60.0),
        min(5.0, max(1.0, period)),
        possession_is_home,
        min(4.0, max(0.0, down)),
        min(100.0, max(0.0, yards_to_first)),
        yards_to_goal,
        home_field_position,
    ]


def nflverse_state(row: dict) -> list[float]:
    possession_home = bool(row.get("posteam")) and row.get("posteam") == row.get("home_team")
    return state_vector(
        seconds=number(row.get("game_seconds_remaining")),
        score_diff=number(row.get("total_home_score")) - number(row.get("total_away_score")),
        period=number(row.get("qtr"), 1),
        possession_is_home=possession_home,
        down=number(row.get("down")),
        yards_to_first=number(row.get("ydstogo")),
        yards_to_goal=number(row.get("yardline_100"), 50),
    )


def market_state(row: dict) -> list[float]:
    values = dict(zip(NUMERIC_FEATURES, row["numeric"]))
    return state_vector(
        seconds=values["regulation_seconds_remaining"],
        score_diff=values["home_score_diff_pre"],
        period=values["period"],
        possession_is_home=values["possession_is_home"],
        down=values["down"],
        yards_to_first=values["yards_to_first_down"],
        yards_to_goal=values["yards_to_goal"],
    )


def load_state_history(paths: list[Path]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    features, labels, games, receipts = [], [], [], []
    for path in sorted(map(Path, paths)):
        if not path.is_file() or path.is_symlink():
            raise ValueError("canonical nflverse history file required")
        season_counts = Counter()
        with gzip.open(path, "rt", newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required = {"game_id", "home_team", "posteam", "game_seconds_remaining", "qtr",
                        "down", "ydstogo", "yardline_100", "total_home_score",
                        "total_away_score", "result"}
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError("nflverse history lacks frozen state fields")
            for row in reader:
                result = number(row.get("result"), float("nan"))
                game = row.get("game_id", "")
                if not game or not math.isfinite(result) or result == 0:
                    continue
                features.append(nflverse_state(row))
                labels.append(1 if result > 0 else 0)
                games.append(game)
                season_counts[game[:4]] += 1
        receipts.append({"path": str(path.resolve()), "sha256": sha256(path),
                         "usable_rows_by_season": dict(sorted(season_counts.items()))})
    if not features or len(set(games)) < 100:
        raise ValueError("insufficient historical whole-game breadth")
    return np.asarray(features), np.asarray(labels), np.asarray(games), receipts


def game_equal_weights(games: np.ndarray) -> np.ndarray:
    counts = Counter(games.tolist())
    return np.asarray([1.0 / counts[game] for game in games], dtype=float)


def fit_state_model(x: np.ndarray, y: np.ndarray, games: np.ndarray):
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500, random_state=SEED)
    model.fit(scaler.transform(x), y, sample_weight=game_equal_weights(games))
    return scaler, model


def state_model_diagnostic(x: np.ndarray, y: np.ndarray, games: np.ndarray) -> dict:
    train = np.asarray([not game.startswith("2024_") for game in games])
    check = ~train
    if len(set(games[train])) < 100 or len(set(games[check])) < 100:
        raise ValueError("2021-2023 fit and 2024 check breadth required")
    scaler, model = fit_state_model(x[train], y[train], games[train])
    prediction = model.predict_proba(scaler.transform(x[check]))[:, 1]
    weights = game_equal_weights(games[check]); weights /= weights.sum()
    brier = float(np.sum(weights * np.square(y[check] - prediction)))
    base = float(np.sum(weights * np.square(y[check] - np.average(y[train],
        weights=game_equal_weights(games[train])))))
    return {
        "fit_games": len(set(games[train])),
        "check_games": len(set(games[check])),
        "check_rows": int(check.sum()),
        "equal_game_brier": brier,
        "equal_game_constant_base_brier": base,
        "relative_brier_improvement": (base - brier) / base,
        "weighted_log_loss": float(log_loss(y[check], prediction, sample_weight=weights,
                                              labels=[0, 1])),
        "mean_prediction": float(np.sum(weights * prediction)),
        "mean_outcome": float(np.sum(weights * y[check])),
        "formal_promotion": False,
    }


def same_event_post_states(rows: list[dict], market_receipts: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """Build post-play states from the same PBP event, never a later row."""
    if rows and all("post_state" in row for row in rows):
        values = np.asarray([row["post_state"] for row in rows], dtype=float)
        if values.shape != (len(rows), len(STATE_FEATURES)) or not np.isfinite(values).all():
            raise ValueError("materialized same-event post-state is invalid")
        counts = Counter(row["game"] for row in rows)
        return values, [{"game": game, "eligible_same_event_rows": counts[game],
                         "source": "gate_committed_panel"} for game in sorted(counts)]
    by_game = defaultdict(list)
    for index, row in enumerate(rows):
        by_game[row["game"]].append((index, row))
    output = np.empty((len(rows), len(STATE_FEATURES)), dtype=float)
    receipts = []
    for receipt in market_receipts:
        game = receipt["game"]
        manifest_path = Path(receipt["panel_path"]).with_name("manifest.json")
        manifest = json.loads(manifest_path.read_text())
        pbp = Path(manifest["pbp_path"]).resolve()
        if (not pbp.is_file() or pbp.is_symlink() or sha256(pbp) != manifest["pbp_sha256"]
                or sha256(manifest_path) != receipt["alignment_manifest_sha256"]):
            raise ValueError("same-event representation PBP binding changed")
        with gzip.open(pbp, "rt", encoding="utf-8") as stream:
            source = json.load(stream)
        home = ((source.get("summary") or {}).get("home") or {}).get("alias")
        away = ((source.get("summary") or {}).get("away") or {}).get("alias")
        events = {}
        for period in source.get("periods") or []:
            period_number = int(period.get("number"))
            for item in period.get("pbp") or []:
                values = item.get("events") if item.get("type") == "drive" else [item]
                for event in values or []:
                    if event.get("type") == "play" and event.get("wall_clock"):
                        if event.get("id") in events:
                            raise ValueError("duplicate event ID in bound PBP")
                        events[event["id"]] = (period_number, event)
        for index, row in by_game[game]:
            if row["play_id"] not in events:
                raise ValueError("eligible market row has no same-event PBP record")
            period_number, event = events[row["play_id"]]
            end = event.get("end_situation") or {}
            possession = (end.get("possession") or {}).get("alias")
            location = end.get("location") or {}
            clock = end.get("clock")
            needed = (clock, end.get("down"), end.get("yfd"), possession,
                      location.get("alias"), location.get("yardline"),
                      event.get("home_points"), event.get("away_points"))
            if (not home or not away or any(value is None or value == "" for value in needed)
                    or possession not in {home, away}):
                raise ValueError("same-event end_situation is incomplete")
            seconds = ((4 - period_number) * 900 + clock_seconds(clock)
                       if period_number <= 4 else 0)
            yards = field_yards_to_goal(possession, location)
            if yards is None:
                raise ValueError("same-event field position is unavailable")
            output[index] = state_vector(
                seconds=seconds,
                score_diff=float(event["home_points"]) - float(event["away_points"]),
                period=period_number,
                possession_is_home=possession == home,
                down=float(end["down"]),
                yards_to_first=float(end["yfd"]),
                yards_to_goal=float(yards),
            )
        receipts.append({"game": game, "pbp_sha256": manifest["pbp_sha256"],
                         "eligible_same_event_rows": len(by_game[game])})
    if set(by_game) != {row["game"] for row in receipts} or not np.isfinite(output).all():
        raise ValueError("same-event representation did not cover the exact Train population")
    return output, receipts


def add_representation(rows: list[dict], market_receipts: list[dict], scaler, model
                       ) -> tuple[list[list[float]], list[dict]]:
    states = np.asarray([market_state(row) for row in rows], dtype=float)
    post_states, receipts = same_event_post_states(rows, market_receipts)
    wp = model.predict_proba(scaler.transform(states))[:, 1]
    post_wp = model.predict_proba(scaler.transform(post_states))[:, 1]
    delta = post_wp - wp
    home_price = np.asarray([row["numeric"][NUMERIC_FEATURES.index("home_price_pre")]
                             for row in rows], dtype=float)
    return np.column_stack((wp, delta, wp - home_price)).tolist(), receipts


def design(rows: list[dict], indices: np.ndarray, extra: list[list[float]] | None):
    numeric = np.asarray([rows[index]["numeric"] for index in indices], dtype=float)
    if extra is not None:
        numeric = np.column_stack((numeric, np.asarray([extra[index] for index in indices])))
    categorical = np.asarray([rows[index]["categorical"] for index in indices], dtype=object)
    return numeric, categorical


def fit_predict(rows: list[dict], fit_indices: np.ndarray, check_indices: np.ndarray,
                extra: list[list[float]] | None) -> np.ndarray:
    fit_numeric, fit_categorical = design(rows, fit_indices, extra)
    check_numeric, check_categorical = design(rows, check_indices, extra)
    scaler = StandardScaler().fit(fit_numeric)
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=float).fit(fit_categorical)
    x_fit = np.column_stack((scaler.transform(fit_numeric), encoder.transform(fit_categorical)))
    x_check = np.column_stack((scaler.transform(check_numeric), encoder.transform(check_categorical)))
    y_fit = np.asarray([rows[index]["target"] for index in fit_indices], dtype=float)
    model = Ridge(alpha=1.0, fit_intercept=True, solver="svd")
    model.fit(x_fit, y_fit, sample_weight=equal_game_weights(rows, fit_indices))
    return np.asarray(model.predict(x_check), dtype=float)


def run(panel_root: Path, selection_root: Path, summary_manifest: Path,
        nflverse_history: list[Path], output: Path) -> dict:
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    try:
        summary = json.loads(Path(summary_manifest).read_text())
        if (summary.get("games") != 163 or summary.get("split_role") != "market_train"
                or summary.get("route_dev_opened") is not False
                or summary.get("sealed_final_opened") is not False):
            raise ValueError("sealed 163-game opened Train manifest required")
        rows, market_receipts = load_rows(panel_root, selection_root)
        state_x, state_y, state_games, history_receipts = load_state_history(nflverse_history)
        diagnostic = state_model_diagnostic(state_x, state_y, state_games)
        state_scaler, state_model = fit_state_model(state_x, state_y, state_games)
        extra, availability_receipts = add_representation(
            rows, market_receipts, state_scaler, state_model)
        games = [row["game"] for row in market_receipts]
        folds = rolling_folds(games)
        game_indices = defaultdict(list)
        for index, row in enumerate(rows): game_indices[row["game"]].append(index)

        variants = {
            "baseline_raw_state": None,
            "state_wp_pre_only": [0],
            "state_wp_delta_only": [1],
            "state_market_gap_only": [2],
            "state_surprise_all": [0, 1, 2],
        }
        variant_extra = {
            name: (None if columns is None else [[row[column] for column in columns] for row in extra])
            for name, columns in variants.items()
        }
        lock = {
            "schema": "nfl_state_surprise_train_discovery_spec_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "problem": "Does a history-trained game-state surprise representation improve identical opened-Train rolling prediction?",
            "changed_stage": "representation_learning_only",
            "baseline_features": {"numeric": list(NUMERIC_FEATURES),
                                  "categorical": list(CATEGORICAL_FEATURES)},
            "candidate_added_features": list(REPRESENTATION_FEATURES),
            "representation_availability": (
                "Each state_wp_delta uses only pre-state and end_situation from the same PBP event; "
                "a later play row is never read."
            ),
            "frozen_ablation_variants": {
                name: ([] if columns is None else [REPRESENTATION_FEATURES[index] for index in columns])
                for name, columns in variants.items()
            },
            "state_features": list(STATE_FEATURES),
            "state_fit_seasons": [2021, 2022, 2023, 2024],
            "state_label": "final_home_win; ties excluded",
            "state_weighting": "each game total weight 1",
            "market_target": TARGET,
            "market_horizon_seconds": 60,
            "downstream_trainer": {"family": "ridge", "alpha": 1.0,
                                   "fit_intercept": True, "solver": "svd"},
            "market_weighting": "equal_game",
            "primary_metric": "candidate_minus_baseline_equal_game_mse",
            "reward_direction": "minimize",
            "secondary_metrics": ["positive_game_fraction", "pearson_ic", "rank_ic",
                                  "calibration_slope", "UTC_date_block_interval"],
            "folds": folds,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "formal_claim": False,
            "history_receipts": history_receipts,
            "market_receipts": market_receipts,
            "same_event_availability_receipts": availability_receipts,
            "summary_manifest_sha256": sha256(summary_manifest),
            "source_code_sha256": sha256(Path(__file__)),
        }
        write_json(output / "pre_score_lock.json", lock)
        write_json(output / "state_model_diagnostic.json", diagnostic)

        predictions = {name: [] for name in variants}
        check_order = []
        fold_results = []
        for fold in folds:
            fit = np.asarray([i for game in fold["fit_games"] for i in game_indices[game]], dtype=int)
            check = np.asarray([i for game in fold["check_games"] for i in game_indices[game]], dtype=int)
            fold_predictions = {
                name: fit_predict(rows, fit, check, variant_extra[name]) for name in variants
            }
            fold_metrics = {name: metrics(rows, check, prediction)
                            for name, prediction in fold_predictions.items()}
            baseline_mse = fold_metrics["baseline_raw_state"]["equal_game_candidate_mse"]
            fold_results.append({
                "fold": fold["fold"], "fit_games": len(fold["fit_games"]),
                "check_games": len(fold["check_games"]),
                "baseline_mse": baseline_mse,
                "variants": {name: {
                    "mse": report["equal_game_candidate_mse"],
                    "minus_baseline_mse": report["equal_game_candidate_mse"] - baseline_mse,
                } for name, report in fold_metrics.items()},
            })
            for name, prediction in fold_predictions.items():
                predictions[name].extend(prediction.tolist())
            check_order.extend(check.tolist())
        check = np.asarray(check_order, dtype=int)
        aggregate = {name: metrics(rows, check, np.asarray(prediction))
                     for name, prediction in predictions.items()}
        baseline_metrics = aggregate["baseline_raw_state"]
        candidate_metrics = aggregate["state_surprise_all"]
        delta = candidate_metrics["equal_game_candidate_mse"] - baseline_metrics["equal_game_candidate_mse"]
        result = {
            "schema": "nfl_state_surprise_train_discovery_result_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "state_model_diagnostic_sha256": sha256(output / "state_model_diagnostic.json"),
            "state_model_diagnostic": diagnostic,
            "folds": fold_results,
            "ablations": {name: {**{key: value for key, value in report.items() if key != "by_game"},
                "minus_baseline_equal_game_mse": report["equal_game_candidate_mse"]
                    - baseline_metrics["equal_game_candidate_mse"],
                "relative_mse_improvement_vs_same_ridge": (
                    baseline_metrics["equal_game_candidate_mse"] - report["equal_game_candidate_mse"]
                ) / baseline_metrics["equal_game_candidate_mse"]}
                for name, report in aggregate.items()},
            "baseline": {key: value for key, value in baseline_metrics.items() if key != "by_game"},
            "candidate": {key: value for key, value in candidate_metrics.items() if key != "by_game"},
            "candidate_minus_baseline_equal_game_mse": delta,
            "relative_mse_improvement_vs_same_ridge": -delta / baseline_metrics["equal_game_candidate_mse"],
            "supported_on_opened_train": delta < 0,
            "interpretation_boundary": "Opened-Train representation discovery only; no Route-Dev or Final was opened.",
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "formal_claim": False,
            "paid_provider_calls": 0,
        }
        write_json(output / "result.json", result)
        write_json(output / "manifest.json", {
            "schema": "nfl_state_surprise_train_discovery_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "state_model_diagnostic_sha256": sha256(output / "state_model_diagnostic.json"),
            "result_sha256": sha256(output / "result.json"),
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "formal_claim": False,
        })
        return result
    except Exception as error:
        write_json(output / "failure.json", {"schema": "nfl_state_surprise_discovery_failure_v1",
            "error_type": type(error).__name__, "error": str(error),
            "route_dev_opened": False, "sealed_final_opened": False,
            "formal_claim": False})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--summary-manifest", type=Path, required=True)
    parser.add_argument("--nflverse-history", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.panel_root, args.selection_root, args.summary_manifest,
                 args.nflverse_history, args.output)
    print(json.dumps({key: result[key] for key in (
        "candidate_minus_baseline_equal_game_mse",
        "relative_mse_improvement_vs_same_ridge",
        "supported_on_opened_train",
        "route_dev_opened",
    )}, indent=2))


if __name__ == "__main__":
    main()
