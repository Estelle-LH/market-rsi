"""One-shot Route-Dev evaluator for the frozen state-WP-delta candidate."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from data_scientist_harness.sealed_dev_gate import SealedDevGate
from sports_event_research.run_state_surprise_discovery import (
    add_representation,
    fit_state_model,
    load_state_history,
    state_vector,
)
from sports_event_research.run_train_method_screen import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    equal_game_weights,
    load_rows,
    metrics,
    sha256,
    write_json,
)


def load_route_dev_rows(dev_files: dict[str, str], selection_root: Path) -> tuple[list[dict], list[dict]]:
    selections = {}
    for path in sorted(Path(selection_root).glob("*.selection.json")):
        value = json.loads(path.read_text())
        if (value.get("split_role") != "route_dev" or value.get("price_history_opened") is not False
                or value.get("trades_opened") is not False or value.get("labels_opened") is not False):
            raise ValueError("frozen unopened Route-Dev selection required")
        value["selection_path"] = str(path.resolve()); value["selection_sha256"] = sha256(path)
        selections[value["nflverse_game_id"]] = value
    if len(selections) != 50 or set(dev_files) != set(selections):
        raise ValueError("claimed Dev panels must match all 50 selected games")
    rows, receipts = [], []
    for game, selection in sorted(selections.items(), key=lambda item: (
            item[1]["scheduled_utc"], item[0])):
        panel = Path(dev_files[game]).resolve()
        if not panel.is_file() or panel.is_symlink():
            raise ValueError("canonical claimed Dev panel required")
        loaded = missing = 0
        with panel.open(newline="") as stream:
            reader = csv.DictReader(stream)
            post_names = ("post_regulation_seconds_remaining", "post_period",
                          "post_home_score_diff", "post_possession_is_home", "post_down",
                          "post_yards_to_first_down", "post_yards_to_goal")
            required = set(NUMERIC_FEATURES + CATEGORICAL_FEATURES + (TARGET, "play_id")
                           + post_names)
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError("Dev panel lacks frozen evaluator fields")
            for ordinal, raw in enumerate(reader):
                if raw[TARGET] == "":
                    missing += 1; continue
                if any(raw[name] == "" for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES + post_names):
                    raise ValueError("eligible Dev target row has a missing frozen feature")
                numeric = [float(raw[name]) for name in NUMERIC_FEATURES]
                target = float(raw[TARGET])
                if not np.isfinite(numeric).all() or not np.isfinite(target):
                    raise ValueError("non-finite Dev feature or target")
                post_state = state_vector(
                    seconds=float(raw["post_regulation_seconds_remaining"]),
                    score_diff=float(raw["post_home_score_diff"]),
                    period=float(raw["post_period"]),
                    possession_is_home=float(raw["post_possession_is_home"]),
                    down=float(raw["post_down"]),
                    yards_to_first=float(raw["post_yards_to_first_down"]),
                    yards_to_goal=float(raw["post_yards_to_goal"]),
                )
                rows.append({"game": game, "game_date": selection["scheduled_utc"][:10],
                    "scheduled_utc": selection["scheduled_utc"], "play_id": raw["play_id"],
                    "ordinal": ordinal, "numeric": numeric,
                    "categorical": [raw[name] for name in CATEGORICAL_FEATURES], "target": target,
                    "post_state": post_state})
                loaded += 1
        receipts.append({"game": game, "panel_sha256": sha256(panel),
                         "eligible_rows": loaded, "missing_target_rows": missing})
    if not rows or len({(row["game"], row["play_id"]) for row in rows}) != len(rows):
        raise ValueError("empty or duplicate Route-Dev row population")
    return rows, receipts


def matrices(train: list[dict], dev: list[dict], train_extra=None, dev_extra=None):
    train_numeric = np.asarray([row["numeric"] for row in train], dtype=float)
    dev_numeric = np.asarray([row["numeric"] for row in dev], dtype=float)
    if train_extra is not None:
        train_numeric = np.column_stack((train_numeric, train_extra))
        dev_numeric = np.column_stack((dev_numeric, dev_extra))
    train_cat = np.asarray([row["categorical"] for row in train], dtype=object)
    dev_cat = np.asarray([row["categorical"] for row in dev], dtype=object)
    scaler = StandardScaler().fit(train_numeric)
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=float).fit(train_cat)
    return (
        np.column_stack((scaler.transform(train_numeric), encoder.transform(train_cat))),
        np.column_stack((scaler.transform(dev_numeric), encoder.transform(dev_cat))),
    )


def ridge_predict(train: list[dict], dev: list[dict], train_extra=None, dev_extra=None) -> np.ndarray:
    x_train, x_dev = matrices(train, dev, train_extra, dev_extra)
    y_train = np.asarray([row["target"] for row in train], dtype=float)
    indices = np.arange(len(train), dtype=int)
    model = Ridge(alpha=1.0, fit_intercept=True, solver="svd")
    model.fit(x_train, y_train, sample_weight=equal_game_weights(train, indices))
    return np.asarray(model.predict(x_dev), dtype=float)


def run(gate_root: Path, train_panel_root: Path, train_selection_root: Path,
        dev_selection_root: Path, nflverse_history: list[Path], output: Path,
        evaluation_id: str = "state-wp-delta-route-dev-01") -> dict:
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh evaluator output required")
    gate = SealedDevGate(gate_root)
    claim = gate.claim_once(evaluation_id)  # allowance is consumed before any Dev label is read
    output.mkdir(parents=True)
    try:
        train_rows, train_receipts = load_rows(train_panel_root, train_selection_root)
        dev_rows, dev_receipts = load_route_dev_rows(claim["dev_files"], dev_selection_root)
        state_x, state_y, state_games, history_receipts = load_state_history(nflverse_history)
        state_scaler, state_model = fit_state_model(state_x, state_y, state_games)
        train_representation, train_availability = add_representation(
            train_rows, train_receipts, state_scaler, state_model)
        dev_representation, dev_availability = add_representation(
            dev_rows, dev_receipts, state_scaler, state_model)
        train_representation = np.asarray(train_representation)[:, [1]]
        dev_representation = np.asarray(dev_representation)[:, [1]]

        baseline_prediction = ridge_predict(train_rows, dev_rows)
        candidate_prediction = ridge_predict(train_rows, dev_rows,
                                             train_representation, dev_representation)
        indices = np.arange(len(dev_rows), dtype=int)
        baseline = metrics(dev_rows, indices, baseline_prediction)
        candidate = metrics(dev_rows, indices, candidate_prediction)
        delta = candidate["equal_game_candidate_mse"] - baseline["equal_game_candidate_mse"]
        result = {
            "schema": "state_wp_delta_route_dev_result_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_id": evaluation_id,
            "confirmation_sha256": claim["confirmation"]["record_sha256"],
            "primary_metric": "candidate_minus_baseline_equal_game_mse",
            "reward_direction": "minimize",
            "candidate_minus_baseline_equal_game_mse": delta,
            "relative_mse_improvement_vs_baseline": -delta / baseline["equal_game_candidate_mse"],
            "supported_on_route_dev": delta < 0,
            "baseline": {key: value for key, value in baseline.items() if key != "by_game"},
            "candidate": {key: value for key, value in candidate.items() if key != "by_game"},
            "train_games": len(train_receipts), "route_dev_games": len(dev_receipts),
            "history_source_hashes": [row["sha256"] for row in history_receipts],
            "train_panel_hashes": {row["game"]: row["panel_sha256"] for row in train_receipts},
            "route_dev_panel_hashes": {row["game"]: row["panel_sha256"] for row in dev_receipts},
            "same_event_availability": {
                "train_games": len(train_availability),
                "route_dev_games": len(dev_availability),
                "later_play_rows_used": 0,
            },
            "evaluation_uses": 1, "sealed_final_opened": False,
            "claim_boundary": "One-shot Route-Dev transfer result; not profitability or sealed Final evidence.",
        }
        write_json(output / "result.json", result)
        receipt = gate.record_result(evaluation_id, result)
        write_json(output / "complete.json", {"schema": "state_wp_delta_route_dev_complete_v1",
            "result_sha256": sha256(output / "result.json"),
            "gate_receipt_sha256": receipt["result_sha256"], "evaluation_uses": 1,
            "sealed_final_opened": False})
        return result
    except Exception as error:
        failure = {"schema": "state_wp_delta_route_dev_failure_v1",
            "evaluation_id": evaluation_id, "error_type": type(error).__name__,
            "error": str(error), "evaluation_uses": 1, "sealed_final_opened": False}
        write_json(output / "failure.json", failure)
        gate.record_result(evaluation_id, failure)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-root", type=Path, required=True)
    parser.add_argument("--train-panel-root", type=Path, required=True)
    parser.add_argument("--train-selection-root", type=Path, required=True)
    parser.add_argument("--dev-selection-root", type=Path, required=True)
    parser.add_argument("--nflverse-history", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.gate_root, args.train_panel_root, args.train_selection_root,
                 args.dev_selection_root, args.nflverse_history, args.output)
    print(json.dumps({key: result[key] for key in (
        "candidate_minus_baseline_equal_game_mse", "relative_mse_improvement_vs_baseline",
        "supported_on_route_dev", "route_dev_games", "evaluation_uses")}, indent=2))


if __name__ == "__main__":
    main()
