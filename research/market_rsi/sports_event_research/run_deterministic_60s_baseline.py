"""Opened-Train, trainer-only screen on the frozen 60-second NFL state-delta task.

This does not touch Route-Dev or Final. It selects no scientific winner on an
independent cohort; it only prepares a stronger deterministic benchmark slate.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from sports_event_research.run_state_surprise_discovery import (
    add_representation,
    fit_state_model,
    load_state_history,
)
from sports_event_research.run_train_method_screen import (
    CATEGORICAL_FEATURES,
    METHODS,
    NUMERIC_FEATURES,
    SEED,
    TARGET,
    equal_game_weights,
    estimator,
    load_rows,
    metrics,
    rolling_folds,
    sha256,
    write_json,
)


METHOD_ORDER = ("ridge", "random_forest", "hist_gradient_boosting")
EXPECTED_PARENT_TRAIN_MSE = 0.0016700963
EXPECTED_SUMMARY_SHA256 = "cdcb9fc20ea700eaf195d3a6d3a9d5818087778ee29523afb7db43f3e1d9b29d"


def preflight(summary_manifest: Path) -> dict:
    summary = json.loads(Path(summary_manifest).read_text())
    if (summary.get("games") != 163 or summary.get("split_role") != "market_train"
            or summary.get("route_dev_opened") is not False
            or summary.get("sealed_final_opened") is not False):
        raise ValueError("exact 163-game opened Train manifest required")
    return summary


def fold_matrices(rows: list[dict], fit_indices: np.ndarray, check_indices: np.ndarray,
                  state_delta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if state_delta.shape != (len(rows),) or not np.isfinite(state_delta).all():
        raise ValueError("one finite same-event state delta per row required")
    numeric = np.asarray([row["numeric"] for row in rows], dtype=float)
    if numeric.shape != (len(rows), len(NUMERIC_FEATURES)) or not np.isfinite(numeric).all():
        raise ValueError("frozen numeric feature population required")
    numeric = np.column_stack((numeric, state_delta))
    categorical = np.asarray([row["categorical"] for row in rows], dtype=object)
    if categorical.shape != (len(rows), len(CATEGORICAL_FEATURES)):
        raise ValueError("frozen categorical feature population required")
    scaler = StandardScaler().fit(numeric[fit_indices])
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=float).fit(
        categorical[fit_indices]
    )
    fit = np.column_stack((scaler.transform(numeric[fit_indices]),
                           encoder.transform(categorical[fit_indices])))
    check = np.column_stack((scaler.transform(numeric[check_indices]),
                             encoder.transform(categorical[check_indices])))
    return fit, check


def fit_predict_fold(rows: list[dict], fit_indices: np.ndarray, check_indices: np.ndarray,
                     state_delta: np.ndarray) -> dict[str, np.ndarray]:
    x_fit, x_check = fold_matrices(rows, fit_indices, check_indices, state_delta)
    target = np.asarray([rows[index]["target"] for index in fit_indices], dtype=float)
    if not np.isfinite(target).all():
        raise ValueError("non-finite Train target")
    weights = equal_game_weights(rows, fit_indices)
    result = {}
    for method in METHOD_ORDER:
        model = estimator(method)
        model.fit(x_fit, target, sample_weight=weights)
        prediction = np.asarray(model.predict(x_check), dtype=float)
        if prediction.shape != (len(check_indices),) or not np.isfinite(prediction).all():
            raise ValueError(f"{method} returned invalid predictions")
        result[method] = prediction
    return result


def select_train_only(summary: dict[str, dict]) -> str:
    """Fixed minimum-MSE rule; this never promotes on Route-Dev or Final."""
    if set(summary) != set(METHOD_ORDER):
        raise ValueError("all preregistered methods must complete")
    return min(METHOD_ORDER, key=lambda method: (
        summary[method]["equal_game_candidate_mse"], METHOD_ORDER.index(method)))


def run(panel_root: Path, selection_root: Path, summary_manifest: Path,
        nflverse_history: list[Path], output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        preflight(summary_manifest)
        if sha256(summary_manifest) != EXPECTED_SUMMARY_SHA256:
            raise ValueError("opened Train source manifest changed from the parent")
        rows, market_receipts = load_rows(panel_root, selection_root)
        state_x, state_y, state_games, history_receipts = load_state_history(nflverse_history)
        state_scaler, state_model = fit_state_model(state_x, state_y, state_games)
        representation, availability = add_representation(
            rows, market_receipts, state_scaler, state_model)
        delta = np.asarray(representation, dtype=float)[:, 1]
        games = [receipt["game"] for receipt in market_receipts]
        folds = rolling_folds(games)
        game_indices = defaultdict(list)
        for index, row in enumerate(rows):
            game_indices[row["game"]].append(index)
        if (len(games) != 163 or len(rows) != 23709 or len(folds) != 3
                or len({row["game"] for row in rows}) != 163):
            raise ValueError("the old 60-second Train population changed")
        lock = {
            "schema": "nfl_deterministic_60s_baseline_lock_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "question": "Can fixed deterministic trainers beat the existing state-delta Ridge on identical opened-Train folds?",
            "changed_stage": "trainer_only",
            "target": TARGET, "horizon_seconds": 60,
            "fixed_features": {"numeric": list(NUMERIC_FEATURES) + ["state_wp_delta"],
                               "categorical": list(CATEGORICAL_FEATURES)},
            "state_fit_seasons": [2021, 2022, 2023, 2024],
            "state_available_time": "historical same-event end_situation, not verified live receive time",
            "train_population": {"games": 163, "eligible_rows": 23709},
            "folds": folds, "seed": SEED, "train_weighting": "equal_game",
            "preprocessing": "fit-only StandardScaler and fit-only OneHotEncoder, identical for all trainers",
            "methods": {method: METHODS[method] for method in METHOD_ORDER},
            "selection_rule": "minimum aggregate equal-game MSE on opened Train; tie uses METHOD_ORDER",
            "expected_parent_equal_game_mse": EXPECTED_PARENT_TRAIN_MSE,
            "source_sha256": sha256(Path(__file__)),
            "summary_manifest_sha256": sha256(summary_manifest),
            "history_receipts": history_receipts,
            "market_receipts": market_receipts,
            "same_event_availability": availability,
            "route_dev_opened": False, "sealed_final_opened": False,
            "formal_claim": False, "provider_cost_usd": "0",
        }
        write_json(output / "pre_score_lock.json", lock)

        predictions = {method: [] for method in METHOD_ORDER}
        check_order: list[int] = []
        fold_reports = []
        for fold in folds:
            fit = np.asarray([index for game in fold["fit_games"] for index in game_indices[game]],
                             dtype=int)
            check = np.asarray([index for game in fold["check_games"] for index in game_indices[game]],
                               dtype=int)
            predicted = fit_predict_fold(rows, fit, check, delta)
            reports = {method: metrics(rows, check, value) for method, value in predicted.items()}
            fold_reports.append({"fold": fold["fold"], "fit_games": len(fold["fit_games"]),
                                 "check_games": len(fold["check_games"]),
                                 "method_mse": {method: report["equal_game_candidate_mse"]
                                                for method, report in reports.items()}})
            for method in METHOD_ORDER:
                predictions[method].extend(predicted[method].tolist())
            check_order.extend(check.tolist())
        check = np.asarray(check_order, dtype=int)
        summaries = {method: metrics(rows, check, np.asarray(predictions[method], dtype=float))
                     for method in METHOD_ORDER}
        ridge_mse = summaries["ridge"]["equal_game_candidate_mse"]
        if abs(ridge_mse - EXPECTED_PARENT_TRAIN_MSE) > 1e-8:
            raise ValueError("existing state-delta Ridge parent did not reproduce")
        selected = select_train_only(summaries)
        result = {
            "schema": "nfl_deterministic_60s_baseline_result_v1",
            "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "folds": fold_reports,
            "methods": {method: {key: value for key, value in report.items() if key != "by_game"}
                        for method, report in summaries.items()},
            "train_only_selected_method": selected,
            "relative_mse_improvement_vs_ridge": (
                ridge_mse - summaries[selected]["equal_game_candidate_mse"]
            ) / ridge_mse,
            "interpretation_boundary": "Opened-Train deterministic screen; not a locked strong benchmark or new independent test.",
            "route_dev_opened": False, "sealed_final_opened": False,
            "formal_claim": False, "provider_cost_usd": "0",
        }
        write_json(output / "result.json", result)
        write_json(output / "manifest.json", {
            "schema": "nfl_deterministic_60s_baseline_manifest_v1",
            "complete": True, "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "result_sha256": sha256(output / "result.json"),
            "route_dev_opened": False, "sealed_final_opened": False,
            "formal_claim": False,
        })
        return result
    except Exception as error:
        write_json(output / "failure.json", {
            "schema": "nfl_deterministic_60s_baseline_failure_v1",
            "error_type": type(error).__name__, "error": str(error),
            "route_dev_opened": False, "sealed_final_opened": False,
            "formal_claim": False,
        })
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
    print(json.dumps({"train_only_selected_method": result["train_only_selected_method"],
                      "relative_mse_improvement_vs_ridge": result["relative_mse_improvement_vs_ridge"],
                      "route_dev_opened": False, "sealed_final_opened": False}, indent=2))


if __name__ == "__main__":
    main()
