"""Opened-Train ablation of controller-proposed NFL state representations.

The target, common row population, rolling whole-game folds, Random Forest and
zero-change baseline are frozen to the prior 30-second same-support screen.
Only derived feature representation changes.  Route-Dev and Final stay closed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from experiments.nfl_target_grid_screen import (
    METHODS,
    current_commit,
    estimator,
    load_rows,
    load_target_map,
)
from experiments.nfl_target_same_support import TARGETS, common_indices
from data_scientist_harness.target_discovery_contract import (
    verify_frozen_target_discovery_spec,
)
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
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    SEED,
    block_interval,
    equal_game_weights,
    metrics,
    rolling_folds,
)


TARGET = "elapsed_30s_delta"
PRIMARY = "full_k4"
PARENT_MINIMUM_FOLD_SKILL = 0.0587082927399335
CALIBRATION_RANGE = (0.9, 1.1)
MINIMUM_POSITIVE_GAME_FRACTION = 0.75
DERIVED = (
    "score_time_ratio_k4",
    "possession_field_position_interaction",
    "state_wp_delta",
)
VARIANTS = {
    "parent_raw_state": (),
    PRIMARY: DERIVED,
    "without_score_time": DERIVED[1:],
    "without_possession_field": (DERIVED[0], DERIVED[2]),
    "without_state_wp_delta": DERIVED[:2],
    "score_time_k4_only": (DERIVED[0],),
    "possession_field_only": (DERIVED[1],),
    "state_wp_delta_only": (DERIVED[2],),
    "full_k2_sensitivity": (
        "score_time_ratio_k2",
        "possession_field_position_interaction",
        "state_wp_delta",
    ),
}


def verify_release(path: Path) -> dict:
    release = load_json(path)
    unsigned = {key: value for key, value in release.items() if key != "release_sha256"}
    if (release.get("harness_version") != "data-scientist-harness-v1.6.3"
            or release.get("publication", {}).get("tag") != "dsh-v1.6.3"
            or release.get("release_sha256") != digest(unsigned)):
        raise ValueError("published dsh-v1.6.3 release required")
    return release


def score_time_ratio(score_diff: float, seconds_remaining: float, k: float) -> float:
    seconds = min(3600.0, max(0.0, float(seconds_remaining)))
    elapsed_fraction = 1.0 - seconds / 3600.0
    return float(score_diff) * math.exp(float(k) * elapsed_fraction)


def possession_field_interaction(possession_is_home: float, yards_to_goal: float) -> float:
    home_possession = bool(float(possession_is_home))
    yards = min(100.0, max(0.0, float(yards_to_goal)))
    home_field_position = 100.0 - yards if home_possession else yards
    possession_sign = 1.0 if home_possession else -1.0
    return possession_sign * ((home_field_position - 50.0) / 50.0)


def derived_without_state(rows: list[dict]) -> dict[str, np.ndarray]:
    locations = {name: NUMERIC_FEATURES.index(name) for name in (
        "regulation_seconds_remaining", "home_score_diff_pre",
        "possession_is_home", "yards_to_goal",
    )}
    output = defaultdict(list)
    for row in rows:
        numeric = row["numeric"]
        seconds = numeric[locations["regulation_seconds_remaining"]]
        score = numeric[locations["home_score_diff_pre"]]
        possession = numeric[locations["possession_is_home"]]
        yards = numeric[locations["yards_to_goal"]]
        output["score_time_ratio_k2"].append(score_time_ratio(score, seconds, 2.0))
        output["score_time_ratio_k4"].append(score_time_ratio(score, seconds, 4.0))
        output["possession_field_position_interaction"].append(
            possession_field_interaction(possession, yards)
        )
    return {name: np.asarray(values, dtype=float) for name, values in output.items()}


def matrices(rows: list[dict], fit_indices: np.ndarray, check_indices: np.ndarray,
             derived: dict[str, np.ndarray], columns: tuple[str, ...]):
    numeric = np.asarray([row["numeric"] for row in rows], dtype=float)
    if columns:
        numeric = np.column_stack((numeric, *(derived[name] for name in columns)))
    categorical = np.asarray([row["categorical"] for row in rows], dtype=object)
    scaler = StandardScaler().fit(numeric[fit_indices])
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=float).fit(
        categorical[fit_indices]
    )
    transformed = np.column_stack((scaler.transform(numeric), encoder.transform(categorical)))
    names = list(NUMERIC_FEATURES) + list(columns) + list(
        encoder.get_feature_names_out(CATEGORICAL_FEATURES)
    )
    return transformed[fit_indices], transformed[check_indices], names, {
        "numeric_mean": scaler.mean_.tolist(),
        "numeric_scale": scaler.scale_.tolist(),
        "categorical_levels": [list(map(str, levels)) for levels in encoder.categories_],
    }


def paired_against_parent(parent: dict, candidate: dict) -> dict:
    parent_games = {row["game"]: row for row in parent["by_game"]}
    candidate_games = {row["game"]: row for row in candidate["by_game"]}
    if set(parent_games) != set(candidate_games):
        raise ValueError("candidate and parent game support differ")
    by_date: dict[str, list[float]] = defaultdict(list)
    by_game = []
    for game in sorted(parent_games):
        parent_row, candidate_row = parent_games[game], candidate_games[game]
        if (parent_row["rows"] != candidate_row["rows"]
                or parent_row["date"] != candidate_row["date"]):
            raise ValueError("candidate and parent row support differ")
        delta = candidate_row["candidate_mse"] - parent_row["candidate_mse"]
        by_date[parent_row["date"]].append(delta)
        by_game.append({
            "game": game,
            "date": parent_row["date"],
            "rows": parent_row["rows"],
            "candidate_minus_parent_mse": delta,
        })
    parent_mse = parent["equal_game_candidate_mse"]
    candidate_mse = candidate["equal_game_candidate_mse"]
    return {
        "equal_game_parent_mse": parent_mse,
        "equal_game_candidate_mse": candidate_mse,
        "candidate_minus_parent_equal_game_mse": candidate_mse - parent_mse,
        "relative_mse_improvement_vs_parent": (
            (parent_mse - candidate_mse) / parent_mse if parent_mse else None
        ),
        "positive_game_fraction_vs_parent": float(np.mean([
            row["candidate_minus_parent_mse"] < 0 for row in by_game
        ])),
        "candidate_minus_parent_date_block_interval": block_interval(by_date),
        "by_game": by_game,
    }


def supported(report: dict, fold_reports: list[dict]) -> bool:
    weakest = min(fold["relative_mse_improvement"] for fold in fold_reports)
    slope = report["equal_game_calibration_slope"]
    return bool(
        weakest > PARENT_MINIMUM_FOLD_SKILL
        and slope is not None
        and CALIBRATION_RANGE[0] <= slope <= CALIBRATION_RANGE[1]
        and report["positive_game_fraction"] >= MINIMUM_POSITIVE_GAME_FRACTION
    )


def assert_parent_reproduction(prior: dict, report: dict, folds: list[dict],
                               full_rows: int, check_rows: int) -> None:
    if prior.get("same_support_full_rows") != full_rows:
        raise ValueError("same-support full row count did not reproduce")
    expected = prior["public_summary"][TARGET]
    if expected["profile"]["rolling_check_rows"] != check_rows:
        raise ValueError("same-support rolling check row count did not reproduce")
    expected_method = expected["methods"]["random_forest"]
    checks = (
        (report["relative_mse_improvement"], expected_method["relative_mse_improvement"]),
        (report["positive_game_fraction"], expected_method["positive_game_fraction"]),
        (report["equal_game_calibration_slope"], expected_method["equal_game_calibration_slope"]),
        (report["equal_game_baseline_mse"], expected["profile"]["equal_game_zero_change_mse"]),
    )
    for observed, expected_value in checks:
        if not math.isclose(observed, expected_value, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("frozen parent metric did not reproduce")
    observed_folds = [fold["relative_mse_improvement"] for fold in folds]
    expected_folds = expected_method["fold_relative_mse_improvements"]
    if len(observed_folds) != len(expected_folds) or any(
        not math.isclose(observed, expected_value, rel_tol=0.0, abs_tol=1e-12)
        for observed, expected_value in zip(observed_folds, expected_folds)
    ):
        raise ValueError("frozen parent fold metrics did not reproduce")


def run(spec_path: Path, target_materialization: Path, panel_root: Path,
        selection_root: Path, release_path: Path, prior_same_support: Path,
        nflverse_history: list[Path], repo_root: Path, output: Path) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        release = verify_release(release_path)
        frozen_record = load_json(spec_path)
        frozen = verify_frozen_target_discovery_spec(frozen_record)
        names = [name for name, _, _ in target_names(frozen)]
        if not set(TARGETS).issubset(names) or TARGET not in names:
            raise ValueError("frozen target materialization lacks the same-support neighborhood")
        materialization = Path(target_materialization).resolve()
        materialization_manifest = load_json(materialization / "manifest.json")
        if (materialization_manifest.get("complete") is not True
                or materialization_manifest.get("route_dev_opened") is not False
                or materialization_manifest.get("sealed_final_opened") is not False
                or materialization_manifest.get("target_panel_sha256")
                != file_hash(materialization / "target_panel.csv")):
            raise ValueError("target materialization receipt is invalid")
        prior = load_json(prior_same_support)
        if (prior.get("schema") != "nfl_open_train_target_same_support_result_v1"
                or prior.get("route_dev_opened") is not False
                or prior.get("sealed_final_opened") is not False
                or prior.get("support_rule_satisfied") is not True):
            raise ValueError("completed same-support parent result required")

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
        if len(rows) != 16632:
            raise ValueError("exact 16,632-play same-support population required")
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
            "schema": "nfl_representation_ablation_inputs_v1",
            "target_spec_sha256": file_hash(spec_path),
            "target_materialization_manifest_sha256": file_hash(materialization / "manifest.json"),
            "target_panel_sha256": file_hash(materialization / "target_panel.csv"),
            "prior_same_support_result_sha256": file_hash(prior_same_support),
            "panel_receipts": panel_receipts,
            "history_receipts": history_receipts,
            "same_event_availability_receipts": availability_receipts,
        }
        fresh_json(output / "input_receipts.json", input_receipts)

        folds = rolling_folds(ordered_games)
        lock = {
            "schema": "nfl_representation_ablation_lock_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "question": "Do controller-proposed state representations improve the exact frozen 30-second Random Forest parent?",
            "hypothesis": "The predeclared full_k4 representation clears all three opened-Train support conditions.",
            "changed_stage": "feature_representation_only",
            "target": TARGET,
            "same_support_targets": list(TARGETS),
            "same_support_full_rows": len(rows),
            "rolling_design": {"initial_games": 100, "block_games": 21, "blocks": 3},
            "parent_numeric_features": list(NUMERIC_FEATURES),
            "parent_categorical_features": list(CATEGORICAL_FEATURES),
            "parent_method": METHODS["random_forest"],
            "derived_feature_formulas": {
                "score_time_ratio_k4": "home_score_diff_pre * exp(4 * (1 - clipped_regulation_seconds_remaining/3600))",
                "score_time_ratio_k2": "home_score_diff_pre * exp(2 * (1 - clipped_regulation_seconds_remaining/3600))",
                "possession_field_position_interaction": "possession_sign * ((home_field_position - 50)/50)",
                "state_wp_delta": "historical_public_PBP_state_model(end_of_same_event) - state_model(start_of_same_event)",
            },
            "variants": {name: list(columns) for name, columns in VARIANTS.items()},
            "primary_candidate": PRIMARY,
            "support_rule": {
                "minimum_fold_relative_mse_improvement_strictly_above_parent": PARENT_MINIMUM_FOLD_SKILL,
                "equal_game_calibration_slope_inclusive": list(CALIBRATION_RANGE),
                "positive_game_fraction_at_least": MINIMUM_POSITIVE_GAME_FRACTION,
            },
            "refutation_rule": "The primary candidate misses any support condition; ablations remain diagnostics, not substitute winners.",
            "parent_reproduction_required": True,
            "historical_clock_boundary": "same-event historical provider time only; live receive latency is unobserved",
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
            "research_record": "NFL_REPRESENTATION_ABLATION_RESEARCH_2026-09-16.md",
            "research_sources": [
                "https://arxiv.org/abs/1802.00998",
                "https://arxiv.org/abs/1704.00197",
                "https://opensourcefootball.com/posts/2020-09-28-nflfastr-ep-wp-and-cp-models/",
            ],
        }
        fresh_json(output / "pre_score_lock.json", lock)

        diagnostic = state_model_diagnostic(state_x, state_y, state_games)
        state_scaler, state_model = fit_state_model(state_x, state_y, state_games)
        pre_states = np.asarray([market_state(row) for row in rows], dtype=float)
        state_wp_pre = state_model.predict_proba(state_scaler.transform(pre_states))[:, 1]
        state_wp_post = state_model.predict_proba(state_scaler.transform(post_states))[:, 1]
        derived = derived_without_state(rows)
        derived["state_wp_delta"] = state_wp_post - state_wp_pre
        if any(values.shape != (len(rows),) or not np.isfinite(values).all()
               for values in derived.values()):
            raise ValueError("derived representation is incomplete or non-finite")
        fresh_json(output / "state_model_diagnostic.json", diagnostic)

        game_to_indices: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            game_to_indices[row["game"]].append(index)
        predictions = {name: [] for name in VARIANTS}
        check_order: list[int] = []
        fold_details = []
        fold_metrics_by_variant = {name: [] for name in VARIANTS}
        for fold in folds:
            fit_indices = np.asarray([
                index for game in fold["fit_games"] for index in game_to_indices[game]
            ], dtype=int)
            check_indices = np.asarray([
                index for game in fold["check_games"] for index in game_to_indices[game]
            ], dtype=int)
            weights = equal_game_weights(rows, fit_indices)
            y_fit = np.asarray([rows[index]["target"] for index in fit_indices], dtype=float)
            local = {"fold": fold["fold"], "fit_rows": len(fit_indices),
                     "check_rows": len(check_indices), "variants": {}}
            for name, columns in VARIANTS.items():
                x_fit, x_check, feature_names, preprocessing = matrices(
                    rows, fit_indices, check_indices, derived, columns
                )
                model = estimator("random_forest").fit(x_fit, y_fit, sample_weight=weights)
                prediction = np.asarray(model.predict(x_check), dtype=float)
                report = metrics(rows, check_indices, prediction)
                predictions[name].extend(prediction.tolist())
                fold_metrics_by_variant[name].append(report)
                local["variants"][name] = {
                    "feature_names": feature_names,
                    "preprocessing": preprocessing,
                    "metrics": {key: value for key, value in report.items() if key != "by_game"},
                }
            check_order.extend(check_indices.tolist())
            fold_details.append(local)

        check_indices = np.asarray(check_order, dtype=int)
        aggregate = {
            name: metrics(rows, check_indices, np.asarray(values, dtype=float))
            for name, values in predictions.items()
        }
        parent = aggregate["parent_raw_state"]
        assert_parent_reproduction(
            prior, parent, fold_metrics_by_variant["parent_raw_state"],
            len(rows), len(check_indices),
        )
        paired = {
            name: paired_against_parent(parent, report)
            for name, report in aggregate.items() if name != "parent_raw_state"
        }
        primary_fold_reports = [
            {key: value for key, value in report.items() if key != "by_game"}
            for report in fold_metrics_by_variant[PRIMARY]
        ]
        primary_supported = supported(aggregate[PRIMARY], primary_fold_reports)
        summary = {}
        for name, report in aggregate.items():
            summary[name] = {
                **{key: value for key, value in report.items() if key != "by_game"},
                "fold_relative_mse_improvements": [
                    fold["relative_mse_improvement"] for fold in fold_metrics_by_variant[name]
                ],
                "minimum_fold_relative_mse_improvement": min(
                    fold["relative_mse_improvement"] for fold in fold_metrics_by_variant[name]
                ),
            }
            if name in paired:
                summary[name]["paired_against_parent"] = {
                    key: value for key, value in paired[name].items() if key != "by_game"
                }
        result = {
            "schema": "nfl_representation_ablation_result_v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "state_model_diagnostic_sha256": file_hash(output / "state_model_diagnostic.json"),
            "parent_reproduced": True,
            "same_support_full_rows": len(rows),
            "rolling_check_rows": len(check_indices),
            "primary_candidate": PRIMARY,
            "primary_support_rule_satisfied": primary_supported,
            "conclusion_status": (
                "opened_train_representation_supported" if primary_supported
                else "opened_train_representation_not_supported"
            ),
            "summary": summary,
            "interpretation_boundary": (
                "Opened-Train representation ablation only. Historical provider event time is not live receive time; "
                "prediction skill is not executable PnL."
            ),
            "provider_cost_usd": "0",
            "route_dev_opened": False,
            "sealed_final_opened": False,
        }
        diagnostics = {
            "schema": "nfl_representation_ablation_diagnostics_v1",
            "folds": fold_details,
            "aggregate_by_game": {name: report["by_game"] for name, report in aggregate.items()},
            "paired_against_parent": paired,
        }
        fresh_json(output / "result.json", result)
        fresh_json(output / "diagnostics.json", diagnostics)
        manifest = {
            "schema": "nfl_representation_ablation_manifest_v1",
            "complete": True,
            "pre_score_lock_sha256": file_hash(output / "pre_score_lock.json"),
            "input_receipts_sha256": file_hash(output / "input_receipts.json"),
            "state_model_diagnostic_sha256": file_hash(output / "state_model_diagnostic.json"),
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
            "schema": "nfl_representation_ablation_failure_v1",
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
    parser.add_argument("--prior-same-support", type=Path, required=True)
    parser.add_argument("--nflverse-history", type=Path, nargs="+", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.spec, args.target_materialization, args.panel_root,
        args.selection_root, args.release, args.prior_same_support,
        args.nflverse_history, args.repo_root, args.output,
    )
    print({key: result[key] for key in (
        "primary_candidate", "primary_support_rule_satisfied",
        "conclusion_status", "route_dev_opened", "sealed_final_opened",
    )})


if __name__ == "__main__":
    main()
