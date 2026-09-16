"""Run a small, auditable Train-only RSI trajectory for NFL market response.

This is an unpaid development canary.  It deliberately reuses the already-open
2025 market_train rolling check rows to prove that the propose -> execute ->
measure -> retain loop works.  It is not Route-Dev evidence, formal promotion,
or a claim that repeated Train-check improvement will generalize.

The target, rows, features, folds, weighting and metric remain frozen.  Each
round changes only the prediction trainer or one Random Forest parameter.  The
branching policy is locked before the first score, and every round writes its
intent before fitting, followed by a machine result and a result-bound
reflection in a SHA256-linked ledger.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge

from sports_event_research.run_train_method_screen import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    SEED,
    TARGET,
    equal_game_weights,
    load_rows,
    matrices,
    metrics,
    rolling_folds,
    sha256,
    write_json,
)


BASE_RF = {
    "n_estimators": 200,
    "max_depth": 8,
    "min_samples_leaf": 50,
    "max_features": 0.7,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def changed_parameters(parent: dict, candidate: dict) -> list[str]:
    keys = sorted(set(parent) | set(candidate))
    return [key for key in keys if parent.get(key) != candidate.get(key)]


def build_estimator(plan: dict):
    family = plan["family"]
    parameters = dict(plan["parameters"])
    if family == "ridge":
        return Ridge(**parameters, solver="svd")
    if family == "elastic_net":
        return ElasticNet(**parameters, random_state=SEED, selection="cyclic")
    if family == "random_forest":
        return RandomForestRegressor(**parameters, random_state=SEED, n_jobs=1)
    raise ValueError(f"unsupported family: {family}")


def initial_plans() -> list[dict]:
    return [
        {
            "round": 1,
            "candidate_id": "ridge-alpha1",
            "parent_id": "zero-change",
            "family": "ridge",
            "parameters": {"alpha": 1.0, "fit_intercept": True},
            "changed_stage": "prediction_trainer",
            "question": "Can a regularized linear model beat predicting no 60-second change?",
            "hypothesis": "The frozen play-state features contain a small linear response signal.",
        },
        {
            "round": 2,
            "candidate_id": "elastic-net-a0001-l1r05",
            "parent_id": "zero-change",
            "family": "elastic_net",
            "parameters": {
                "alpha": 0.0001,
                "l1_ratio": 0.5,
                "fit_intercept": True,
                "max_iter": 20000,
                "tol": 1e-6,
            },
            "changed_stage": "prediction_trainer",
            "question": "Does sparse linear regularization improve on the zero-change parent?",
            "hypothesis": "Some frozen features are weak enough that mixed L1/L2 shrinkage helps.",
        },
        {
            "round": 3,
            "candidate_id": "random-forest-base",
            "parent_id": "zero-change",
            "family": "random_forest",
            "parameters": dict(BASE_RF),
            "changed_stage": "prediction_trainer",
            "question": "Do nonlinear feature interactions beat the zero-change parent?",
            "hypothesis": "Play effects depend nonlinearly on score, clock, field position and play type.",
        },
    ]


def next_rf_plan(round_number: int, evaluated: dict[str, dict]) -> dict:
    rf_rows = [row for row in evaluated.values() if row["plan"]["family"] == "random_forest"]
    if not rf_rows:
        raise ValueError("Random Forest parent is unavailable")
    parent = min(rf_rows, key=lambda row: row["mse"])
    parameters = dict(parent["plan"]["parameters"])
    if round_number == 4:
        parameters["max_depth"] = 12
        suffix = "depth12"
        question = "Does allowing deeper interactions improve the best available Random Forest?"
        hypothesis = "Depth 8 may underfit rare, high-impact play states."
    elif round_number == 5:
        parameters["min_samples_leaf"] = 25
        suffix = "leaf25"
        question = "Does a smaller leaf improve the best available Random Forest?"
        hypothesis = "Leaf size 50 may smooth away useful but less common play states."
    elif round_number == 6:
        parameters["max_features"] = 1.0
        suffix = "features100"
        question = "Does exposing every feature at each split improve the best available Random Forest?"
        hypothesis = "The small frozen feature set may not need feature subsampling."
    elif round_number == 7:
        parameters["n_estimators"] = 400
        suffix = "trees400"
        question = "Does lowering ensemble Monte Carlo variance improve the best available Random Forest?"
        hypothesis = "Four hundred trees may stabilize predictions without changing model capacity."
    else:
        raise ValueError(f"unsupported adaptive round: {round_number}")
    changed = changed_parameters(parent["plan"]["parameters"], parameters)
    if len(changed) != 1:
        raise ValueError(f"adaptive candidate must change exactly one parameter, got {changed}")
    return {
        "round": round_number,
        "candidate_id": f"random-forest-{suffix}-from-{parent['plan']['candidate_id']}",
        "parent_id": parent["plan"]["candidate_id"],
        "family": "random_forest",
        "parameters": parameters,
        "changed_stage": f"prediction_trainer_parameter:{changed[0]}",
        "question": question,
        "hypothesis": hypothesis,
    }


def choose_champion(evaluated: dict[str, dict]) -> str:
    return min(evaluated, key=lambda candidate_id: evaluated[candidate_id]["mse"])


def validate_summary(summary_manifest: Path) -> dict:
    summary = json.loads(Path(summary_manifest).read_text())
    if (
        summary.get("games") != 163
        or summary.get("split_role") != "market_train"
        or summary.get("route_dev_opened") is not False
        or summary.get("sealed_final_opened") is not False
        or summary.get("scientific_score") is not False
    ):
        raise ValueError("summary manifest does not prove sealed 163-game Train-only input")
    return summary


def prepare_folds(rows: list[dict], receipts: list[dict]) -> tuple[list[dict], np.ndarray]:
    games = [row["game"] for row in receipts]
    folds = rolling_folds(games)
    game_to_indices: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        game_to_indices[row["game"]].append(index)
    prepared = []
    all_check_indices: list[int] = []
    for fold in folds:
        fit_indices = np.asarray(
            [index for game in fold["fit_games"] for index in game_to_indices[game]], dtype=int
        )
        check_indices = np.asarray(
            [index for game in fold["check_games"] for index in game_to_indices[game]], dtype=int
        )
        x_fit, x_check, feature_names, preprocessing = matrices(rows, fit_indices, check_indices)
        prepared.append(
            {
                "fold": fold["fold"],
                "fit_indices": fit_indices,
                "check_indices": check_indices,
                "x_fit": x_fit,
                "x_check": x_check,
                "y_fit": np.asarray([rows[index]["target"] for index in fit_indices], dtype=float),
                "weights": equal_game_weights(rows, fit_indices),
                "feature_names": feature_names,
                "preprocessing": preprocessing,
            }
        )
        all_check_indices.extend(check_indices.tolist())
    if len(all_check_indices) != len(set(all_check_indices)):
        raise ValueError("rolling check rows overlap")
    return prepared, np.asarray(all_check_indices, dtype=int)


def score_plan(plan: dict, rows: list[dict], prepared: list[dict]) -> tuple[np.ndarray, list[dict]]:
    predictions: list[float] = []
    reports = []
    for fold in prepared:
        model = build_estimator(plan)
        model.fit(fold["x_fit"], fold["y_fit"], sample_weight=fold["weights"])
        prediction = np.asarray(model.predict(fold["x_check"]), dtype=float)
        if not np.isfinite(prediction).all():
            raise ValueError(f"non-finite predictions for {plan['candidate_id']}")
        predictions.extend(prediction.tolist())
        reports.append(
            {
                "fold": fold["fold"],
                "fit_rows": len(fold["fit_indices"]),
                "check_rows": len(fold["check_indices"]),
                "metrics": metrics(rows, fold["check_indices"], prediction),
                "model_parameters": model.get_params(deep=False),
                "feature_names": fold["feature_names"],
                "preprocessing": fold["preprocessing"],
                "coefficients": model.coef_.tolist() if hasattr(model, "coef_") else None,
                "feature_importances": (
                    model.feature_importances_.tolist()
                    if hasattr(model, "feature_importances_")
                    else None
                ),
            }
        )
    return np.asarray(predictions, dtype=float), reports


def write_predictions(
    path: Path, rows: list[dict], check_indices: np.ndarray, predictions: dict[str, np.ndarray]
) -> None:
    fields = ["game", "game_date", "scheduled_utc", "play_id", "target", *predictions]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for position, index in enumerate(check_indices):
            source = rows[index]
            record = {name: source[name] for name in fields[:5]}
            for candidate_id, values in predictions.items():
                record[candidate_id] = float(values[position])
            writer.writerow(record)
    temporary.replace(path)


def run(panel_root: Path, selection_root: Path, summary_manifest: Path, output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        validate_summary(summary_manifest)
        rows, receipts = load_rows(panel_root, selection_root)
        prepared, check_indices = prepare_folds(rows, receipts)
        zero_prediction = np.zeros(len(check_indices), dtype=float)
        zero_metrics = metrics(rows, check_indices, zero_prediction)
        policy = {
            "schema": "nfl_train_only_rsi_trajectory_lock_v1",
            "generated_utc": utc_now(),
            "purpose": "development canary for the propose-execute-measure-retain trajectory",
            "research_reuse": {
                "record": "NFL_TRAIN_METHOD_SCREEN_2026-09-15.md",
                "reason": "same frozen target, features, trainers, folds and data; no new method claim",
                "applicability_confirmed": True,
                "new_live_search_claimed": False,
            },
            "target": TARGET,
            "horizon_seconds": 60,
            "features": {"numeric": list(NUMERIC_FEATURES), "categorical": list(CATEGORICAL_FEATURES)},
            "folds": [
                {
                    "fold": fold["fold"],
                    "fit_rows": len(fold["fit_indices"]),
                    "check_rows": len(fold["check_indices"]),
                }
                for fold in prepared
            ],
            "primary_metric": "equal_game_mse",
            "selection_rule": "retain the lowest opened-Train rolling-check MSE seen so far",
            "support_rule": "candidate equal-game MSE is lower than its declared parent",
            "initial_rounds": initial_plans(),
            "adaptive_rounds": {
                "4": "best evaluated Random Forest; max_depth -> 12",
                "5": "best evaluated Random Forest; min_samples_leaf -> 25",
                "6": "best evaluated Random Forest; max_features -> 1.0",
                "7": "best evaluated Random Forest; n_estimators -> 400",
            },
            "one_change_rule": "rounds 4-7 change exactly one parameter from their declared parent",
            "seed": SEED,
            "summary_manifest": str(Path(summary_manifest).resolve()),
            "summary_manifest_sha256": sha256(summary_manifest),
            "source_code_sha256": sha256(Path(__file__)),
            "input_receipts": receipts,
            "paid_provider_calls": 0,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "formal_promotion": False,
            "scientific_score": False,
            "controller_model": "deterministic_locked_development_policy",
            "controller_self_evolution_claim": False,
        }
        write_json(output / "pre_score_lock.json", policy)

        evaluated: dict[str, dict] = {
            "zero-change": {
                "plan": {
                    "round": 0,
                    "candidate_id": "zero-change",
                    "parent_id": None,
                    "family": "zero_change",
                    "parameters": {"prediction": 0.0},
                },
                "mse": zero_metrics["equal_game_candidate_mse"],
                "metrics": zero_metrics,
            }
        }
        all_predictions = {"zero-change": zero_prediction}
        ledger = []
        previous_sha = sha256(output / "pre_score_lock.json")
        plans = initial_plans()
        for round_number in range(1, 8):
            plan = plans[round_number - 1] if round_number <= 3 else next_rf_plan(round_number, evaluated)
            parent = evaluated[plan["parent_id"]]
            intent = {
                "schema": "nfl_train_only_rsi_round_intent_v1",
                "generated_utc": utc_now(),
                "previous_record_sha256": previous_sha,
                **plan,
                "parent_mse_known_before_run": parent["mse"],
                "support_criterion": "candidate equal-game MSE < declared-parent equal-game MSE",
                "refutation_criterion": "candidate equal-game MSE >= declared-parent equal-game MSE",
                "next_step_if_supported": "retain if it is also the lowest MSE seen; continue locked search",
                "next_step_if_refuted": "archive candidate; retain prior champion; continue locked search",
                "route_dev_opened": False,
                "sealed_final_opened": False,
            }
            intent_path = output / f"round-{round_number:02d}-intent.json"
            write_json(intent_path, intent)
            intent_sha = sha256(intent_path)

            prediction, fold_reports = score_plan(plan, rows, prepared)
            aggregate = metrics(rows, check_indices, prediction)
            result = {
                "schema": "nfl_train_only_rsi_round_result_v1",
                "generated_utc": utc_now(),
                "intent_sha256": intent_sha,
                "candidate_id": plan["candidate_id"],
                "aggregate": aggregate,
                "folds": fold_reports,
                "route_dev_opened": False,
                "sealed_final_opened": False,
                "scientific_score": False,
            }
            result_path = output / f"round-{round_number:02d}-result.json"
            write_json(result_path, result)
            result_sha = sha256(result_path)
            evaluated[plan["candidate_id"]] = {
                "plan": plan,
                "mse": aggregate["equal_game_candidate_mse"],
                "metrics": aggregate,
            }
            all_predictions[plan["candidate_id"]] = prediction
            champion = choose_champion(evaluated)
            delta = aggregate["equal_game_candidate_mse"] - parent["mse"]
            supported = delta < 0.0
            reflection = {
                "schema": "nfl_train_only_rsi_round_reflection_v1",
                "generated_utc": utc_now(),
                "result_sha256": result_sha,
                "candidate_id": plan["candidate_id"],
                "parent_id": plan["parent_id"],
                "parent_mse": parent["mse"],
                "candidate_mse": aggregate["equal_game_candidate_mse"],
                "candidate_minus_parent_mse": delta,
                "relative_change_vs_parent": delta / parent["mse"] if parent["mse"] else None,
                "hypothesis_supported_on_opened_train_check": supported,
                "champion_after_round": champion,
                "champion_mse_after_round": evaluated[champion]["mse"],
                "decision": "retain_as_champion" if champion == plan["candidate_id"] else "archive_candidate",
                "interpretation_boundary": (
                    "Result is adaptive reuse of opened Train check rows. It tests loop mechanics and "
                    "generates a hypothesis, but it is not independent evidence of generalization."
                ),
            }
            reflection_path = output / f"round-{round_number:02d}-reflection.json"
            write_json(reflection_path, reflection)
            reflection_sha = sha256(reflection_path)
            ledger.append(
                {
                    "round": round_number,
                    "candidate_id": plan["candidate_id"],
                    "parent_id": plan["parent_id"],
                    "changed_stage": plan["changed_stage"],
                    "candidate_mse": aggregate["equal_game_candidate_mse"],
                    "parent_mse": parent["mse"],
                    "supported": supported,
                    "decision": reflection["decision"],
                    "champion": champion,
                    "champion_mse": evaluated[champion]["mse"],
                    "intent_sha256": intent_sha,
                    "result_sha256": result_sha,
                    "reflection_sha256": reflection_sha,
                }
            )
            previous_sha = reflection_sha

        write_predictions(output / "predictions.csv", rows, check_indices, all_predictions)
        champion = choose_champion(evaluated)
        summary = {
            "schema": "nfl_train_only_rsi_trajectory_result_v1",
            "generated_utc": utc_now(),
            "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "rounds_completed": len(ledger),
            "baseline_id": "zero-change",
            "baseline_mse": evaluated["zero-change"]["mse"],
            "champion_id": champion,
            "champion_mse": evaluated[champion]["mse"],
            "champion_relative_improvement_vs_zero": (
                evaluated["zero-change"]["mse"] - evaluated[champion]["mse"]
            ) / evaluated["zero-change"]["mse"],
            "trajectory": ledger,
            "predictions_sha256": sha256(output / "predictions.csv"),
            "paid_provider_calls": 0,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "scientific_score": False,
            "formal_promotion": False,
            "interpretation_boundary": (
                "Opened-Train adaptive development trajectory only. The best-so-far curve is expected "
                "to be monotone by retention and must be tested once on untouched Route-Dev later."
            ),
        }
        write_json(output / "trajectory.json", summary)
        manifest = {
            "schema": "nfl_train_only_rsi_trajectory_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": sha256(output / "pre_score_lock.json"),
            "trajectory_sha256": sha256(output / "trajectory.json"),
            "predictions_sha256": sha256(output / "predictions.csv"),
            "final_chain_sha256": previous_sha,
            "rounds_completed": len(ledger),
            "paid_provider_calls": 0,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "scientific_score": False,
        }
        write_json(output / "manifest.json", manifest)
        return summary
    except Exception as error:
        write_json(
            output / "failure.json",
            {
                "schema": "nfl_train_only_rsi_trajectory_failure_v1",
                "generated_utc": utc_now(),
                "error_type": type(error).__name__,
                "error": str(error),
                "paid_provider_calls": 0,
                "route_dev_opened": False,
                "sealed_final_opened": False,
                "scientific_score": False,
            },
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--summary-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.panel_root, args.selection_root, args.summary_manifest, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
