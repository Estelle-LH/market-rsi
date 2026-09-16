"""Opened-Train chronological robustness A/B for frozen NFL RF versus HGB.

This expands chronological check coverage from the last 63 to the last 100
games by using a 63-game initial prefix and five 20-game rolling blocks.  Both
models use identical rows and representations in every fold.  Route-Dev and
Final stay closed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

from data_scientist_harness.paired_evidence import build_paired_evidence
from data_scientist_harness.target_discovery_contract import (
    verify_frozen_target_discovery_spec,
)
from experiments.nfl_representation_ablation import (
    DERIVED,
    TARGET,
    derived_without_state,
    matrices,
)
from experiments.nfl_representation_trainer_ablation import (
    HGB_PARAMETERS,
)
from experiments.nfl_target_grid_screen import current_commit, load_rows, load_target_map
from experiments.nfl_target_same_support import TARGETS, common_indices
from market_rsi import digest, file_hash, fresh_json, load_json
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
)


INITIAL_GAMES = 63
BLOCK_GAMES = 20
BLOCKS = 5
MINIMUM_DATE_FRACTION = 0.60
MINIMUM_DATES = 8
MAXIMUM_TOP_DATE_ABSOLUTE_SHARE = 0.50
PAIRED_SPEC = {
    "kind": "paired_grouped_loss_v1",
    "unit": "UTC_date",
    "block": "UTC_date",
    "loss": "equal_game_mse",
    "delta": "candidate_minus_baseline",
    "reward_direction": "minimize",
    "persist_unit_records_runner_private": True,
    "public_visibility": "aggregate_only",
    "bootstrap_draws": 10000,
    "bootstrap_seed": SEED,
    "top_k_units": [1, 5],
}


def verify_release(path: Path) -> dict:
    release = load_json(path)
    unsigned = {key: value for key, value in release.items() if key != "release_sha256"}
    if (release.get("harness_version") != "data-scientist-harness-v1.6.4"
            or release.get("publication", {}).get("tag") != "dsh-v1.6.4"
            or release.get("release_sha256") != digest(unsigned)):
        raise ValueError("published dsh-v1.6.4 release required")
    return release


def verify_prior_trainer(root: Path) -> tuple[dict, dict, dict]:
    root = Path(root).resolve()
    manifest = load_json(root / "manifest.json")
    result = load_json(root / "result.json")
    diagnostics = load_json(root / "diagnostics.json")
    receipts = load_json(root / "input_receipts.json")
    if (manifest.get("schema") != "nfl_representation_trainer_ablation_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("provider_cost_usd") != "0"):
        raise ValueError("completed opened-Train trainer artifact required")
    for name in ("result", "diagnostics", "input_receipts"):
        if manifest.get(f"{name}_sha256") != file_hash(root / f"{name}.json"):
            raise ValueError(f"prior trainer {name} hash mismatch")
    if (result.get("schema") != "nfl_representation_trainer_ablation_result_v1"
            or result.get("route_dev_opened") is not False
            or result.get("sealed_final_opened") is not False
            or receipts.get("schema") != "nfl_representation_trainer_ablation_inputs_v1"):
        raise ValueError("exact completed trainer result required")
    return result, diagnostics, receipts


def robustness_folds(games: list[str]) -> list[dict]:
    if len(games) != INITIAL_GAMES + BLOCK_GAMES * BLOCKS:
        raise ValueError("exact 163-game chronological population required")
    if len(games) != len(set(games)):
        raise ValueError("duplicate game in chronological population")
    folds = []
    for index in range(BLOCKS):
        boundary = INITIAL_GAMES + index * BLOCK_GAMES
        folds.append({
            "fold": index + 1,
            "fit_games": games[:boundary],
            "check_games": games[boundary:boundary + BLOCK_GAMES],
        })
    return folds


def date_records(rows: list[dict], indices: np.ndarray, parent_prediction: np.ndarray,
                 candidate_prediction: np.ndarray) -> list[dict]:
    by_date_game: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    target = np.asarray([rows[index]["target"] for index in indices], dtype=float)
    for position, index in enumerate(indices):
        by_date_game[rows[index]["game_date"]][rows[index]["game"]].append(position)
    records = []
    for date in sorted(by_date_game):
        parent_losses, candidate_losses, date_rows = [], [], 0
        for positions in by_date_game[date].values():
            local = np.asarray(positions, dtype=int)
            parent_losses.append(float(np.mean(np.square(
                target[local] - parent_prediction[local]
            ))))
            candidate_losses.append(float(np.mean(np.square(
                target[local] - candidate_prediction[local]
            ))))
            date_rows += len(local)
        records.append({
            "unit_id": date,
            "block_id": date,
            "rows": date_rows,
            "baseline_loss": float(np.mean(parent_losses)),
            "candidate_loss": float(np.mean(candidate_losses)),
        })
    return records


def support_conditions(public: dict) -> dict:
    interval = public["equal_block_bootstrap_interval"]
    return {
        "minimum_date_count": public["unit_count"] >= MINIMUM_DATES,
        "candidate_better_date_fraction_at_least": (
            public["candidate_better_unit_fraction"] >= MINIMUM_DATE_FRACTION
        ),
        "paired_bootstrap_upper_strictly_below_zero": interval["upper"] < 0,
        "top_date_absolute_share_at_most": (
            public["top_1_absolute_delta_share"] <= MAXIMUM_TOP_DATE_ABSOLUTE_SHARE
        ),
    }


def supported(conditions: dict) -> bool:
    return all(conditions.values())


def run(spec_path: Path, target_materialization: Path, panel_root: Path,
        selection_root: Path, release_path: Path, prior_trainer: Path,
        nflverse_history: list[Path], repo_root: Path, output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        release = verify_release(release_path)
        prior_result, _, prior_receipts = verify_prior_trainer(prior_trainer)
        frozen = verify_frozen_target_discovery_spec(load_json(spec_path))
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
            "schema": "nfl_chronological_robustness_inputs_v1",
            **expected_input_hashes,
            "prior_trainer_manifest_sha256": file_hash(Path(prior_trainer) / "manifest.json"),
            "prior_trainer_result_sha256": file_hash(Path(prior_trainer) / "result.json"),
            "panel_receipts": panel_receipts,
            "history_receipts": history_receipts,
            "same_event_availability_receipts": availability_receipts,
        }
        fresh_json(output / "input_receipts.json", input_receipts)

        folds = robustness_folds(ordered_games)
        lock = {
            "schema": "nfl_chronological_robustness_lock_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "question": "Does frozen full_k4 HGB beat frozen full_k4 RF under wider past-to-future opened-Train coverage?",
            "hypothesis": "HGB clears all four canonical paired-date support conditions.",
            "changed_stage": "chronological_evaluation_coverage_only",
            "target": TARGET,
            "same_support_full_rows": len(rows),
            "rolling_design": {"initial_games": INITIAL_GAMES,
                               "block_games": BLOCK_GAMES, "blocks": BLOCKS},
            "fit_order": "strict chronological game prefix only",
            "leave_one_date_out_forbidden": True,
            "frozen_derived_features": list(DERIVED),
            "parent": {"trainer": "random_forest", "parameters": METHODS["random_forest"]},
            "candidate": {"trainer": "hist_gradient_boosting",
                          "parameters": HGB_PARAMETERS},
            "paired_evidence_spec": PAIRED_SPEC,
            "support_rule": {
                "candidate_better_date_fraction_at_least": MINIMUM_DATE_FRACTION,
                "paired_bootstrap_upper_strictly_below_zero": True,
                "minimum_dates": MINIMUM_DATES,
                "maximum_top_date_absolute_delta_share": MAXIMUM_TOP_DATE_ABSOLUTE_SHARE,
            },
            "second_moment_crosscheck": "mean_candidate_minus_parent_delta + sqrt(population_variance/date_count)",
            "adaptive_opened_train_robustness_not_independent_confirmation": True,
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
            "research_record": "NFL_CHRONOLOGICAL_ROBUSTNESS_RESEARCH_2026-09-16.md",
        }
        fresh_json(output / "pre_score_lock.json", lock)

        diagnostic = state_model_diagnostic(state_x, state_y, state_games)
        prior_state = load_json(
            Path(prior_trainer).parent
            / "nfl-open-train-representation-ablation-20260916-01"
            / "state_model_diagnostic.json"
        )
        if diagnostic != prior_state:
            raise ValueError("historical state model diagnostic did not reproduce")
        state_scaler, state_model = fit_state_model(state_x, state_y, state_games)
        state_wp_pre = state_model.predict_proba(state_scaler.transform(
            np.asarray([market_state(row) for row in rows], dtype=float)
        ))[:, 1]
        state_wp_post = state_model.predict_proba(state_scaler.transform(post_states))[:, 1]
        derived = derived_without_state(rows)
        derived["state_wp_delta"] = state_wp_post - state_wp_pre

        game_to_indices: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            game_to_indices[row["game"]].append(index)
        parent_predictions, candidate_predictions, check_order = [], [], []
        fold_details = []
        for fold in folds:
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
            parent_model = RandomForestRegressor(
                **METHODS["random_forest"], random_state=SEED, n_jobs=1
            ).fit(x_fit, y_fit, sample_weight=weights)
            candidate_model = HistGradientBoostingRegressor(
                **HGB_PARAMETERS, random_state=SEED, early_stopping=False
            ).fit(x_fit, y_fit, sample_weight=weights)
            parent_prediction = np.asarray(parent_model.predict(x_check), dtype=float)
            candidate_prediction = np.asarray(candidate_model.predict(x_check), dtype=float)
            parent_report = metrics(rows, check_indices, parent_prediction)
            candidate_report = metrics(rows, check_indices, candidate_prediction)
            parent_predictions.extend(parent_prediction.tolist())
            candidate_predictions.extend(candidate_prediction.tolist())
            check_order.extend(check_indices.tolist())
            fold_details.append({
                "fold": fold["fold"], "fit_rows": len(fit_indices),
                "check_rows": len(check_indices), "feature_names": feature_names,
                "preprocessing": preprocessing,
                "parent": {key: value for key, value in parent_report.items() if key != "by_game"},
                "candidate": {key: value for key, value in candidate_report.items() if key != "by_game"},
            })

        check_indices = np.asarray(check_order, dtype=int)
        parent_prediction = np.asarray(parent_predictions, dtype=float)
        candidate_prediction = np.asarray(candidate_predictions, dtype=float)
        records = date_records(rows, check_indices, parent_prediction, candidate_prediction)
        private_paired, public_paired = build_paired_evidence(records, PAIRED_SPEC)
        conditions = support_conditions(public_paired)
        deltas = np.asarray([
            row["candidate_loss"] - row["baseline_loss"] for row in records
        ], dtype=float)
        second_moment_upper = float(np.mean(deltas) + math.sqrt(
            float(np.var(deltas)) / len(deltas)
        ))
        parent_report = metrics(rows, check_indices, parent_prediction)
        candidate_report = metrics(rows, check_indices, candidate_prediction)
        result = {
            "schema": "nfl_chronological_robustness_result_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "rolling_check_rows": len(check_indices),
            "rolling_check_games": BLOCK_GAMES * BLOCKS,
            "parent": {key: value for key, value in parent_report.items() if key != "by_game"},
            "candidate": {key: value for key, value in candidate_report.items() if key != "by_game"},
            "paired_date_evidence": public_paired,
            "second_moment_upper_crosscheck": second_moment_upper,
            "support_conditions": conditions,
            "support_rule_satisfied": supported(conditions),
            "conclusion_status": (
                "opened_train_chronological_robustness_supported"
                if supported(conditions)
                else "opened_train_chronological_robustness_not_supported"
            ),
            "adaptive_opened_train_robustness_not_independent_confirmation": True,
            "provider_cost_usd": "0",
            "route_dev_opened": False,
            "sealed_final_opened": False,
        }
        diagnostics = {
            "schema": "nfl_chronological_robustness_diagnostics_v1",
            "folds": fold_details,
            "runner_private_paired_date_evidence": private_paired,
            "parent_by_game": parent_report["by_game"],
            "candidate_by_game": candidate_report["by_game"],
        }
        fresh_json(output / "result.json", result)
        fresh_json(output / "diagnostics.json", diagnostics)
        manifest = {
            "schema": "nfl_chronological_robustness_manifest_v1",
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
            "schema": "nfl_chronological_robustness_failure_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(error).__name__, "error": str(error),
            "provider_cost_usd": "0", "route_dev_opened": False,
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
    parser.add_argument("--prior-trainer", type=Path, required=True)
    parser.add_argument("--nflverse-history", type=Path, nargs="+", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.spec, args.target_materialization, args.panel_root,
        args.selection_root, args.release, args.prior_trainer,
        args.nflverse_history, args.repo_root, args.output,
    )
    print({key: result[key] for key in (
        "support_rule_satisfied", "conclusion_status", "rolling_check_games",
        "route_dev_opened", "sealed_final_opened",
    )})


if __name__ == "__main__":
    main()
