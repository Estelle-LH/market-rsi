"""Estimate Train-only descriptive market responses at fixed horizons.

This is a Jorda-style horizon-by-horizon regression, but it is deliberately
not given a causal interpretation: scoring plays are not exogenous shocks.
All horizons use the same complete-case play population and equal-game WLS.
Uncertainty is clustered by NFL game.  Route-Dev and Final are never read.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t


HORIZONS = (30, 60, 300)
SCORE_FEATURES = ("home_score_change", "away_score_change")
CONTROL_FEATURES = (
    "home_price_pre",
    "regulation_seconds_remaining",
    "home_score_diff_pre",
    "possession_is_home",
    "down",
    "yards_to_first_down",
    "yards_to_goal",
    "is_no_play",
)
FEATURES = SCORE_FEATURES + CONTROL_FEATURES
SOURCES = (
    {
        "id": "jorda-2005-local-projections",
        "url": "https://doi.org/10.1257/0002828053828518",
        "used_for": "estimate a separate direct regression at each fixed response horizon",
    },
    {
        "id": "goncalves-herrera-kilian-pesavento-2024-state-dependent-lp",
        "url": "https://doi.org/10.1016/j.jeconom.2024.105702",
        "used_for": "limit interpretation when the event and state are endogenous",
    },
)


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


def equal_game_weights(games: list[str]) -> np.ndarray:
    counts = Counter(games)
    if not counts:
        raise ValueError("cannot weight an empty population")
    return np.asarray([len(counts) / counts[game] for game in games], dtype=float)


def fit_clustered_wls(
    design: np.ndarray,
    outcome: np.ndarray,
    weights: np.ndarray,
    groups: list[str],
    names: list[str],
) -> dict:
    design = np.asarray(design, dtype=float)
    outcome = np.asarray(outcome, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if design.ndim != 2 or outcome.ndim != 1 or weights.ndim != 1:
        raise ValueError("invalid WLS array shape")
    if len(outcome) != len(design) or len(weights) != len(design) or len(groups) != len(design):
        raise ValueError("WLS inputs have different row counts")
    if design.shape[1] != len(names):
        raise ValueError("design columns do not match names")
    if not np.isfinite(design).all() or not np.isfinite(outcome).all():
        raise ValueError("WLS input contains a non-finite value")
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("WLS weights must be finite and positive")
    rows, columns = design.shape
    clusters = sorted(set(groups))
    if rows <= columns or len(clusters) <= 1:
        raise ValueError("not enough rows or game clusters")
    root_weight = np.sqrt(weights)
    weighted_design = design * root_weight[:, None]
    weighted_outcome = outcome * root_weight
    rank = int(np.linalg.matrix_rank(weighted_design))
    if rank != columns:
        raise ValueError(f"rank-deficient design: rank={rank}, columns={columns}")
    bread = np.linalg.inv(weighted_design.T @ weighted_design)
    coefficient = bread @ weighted_design.T @ weighted_outcome
    residual = outcome - design @ coefficient
    meat = np.zeros((columns, columns), dtype=float)
    group_array = np.asarray(groups, dtype=object)
    for group in clusters:
        positions = np.flatnonzero(group_array == group)
        score = design[positions].T @ (weights[positions] * residual[positions])
        meat += np.outer(score, score)
    correction = (len(clusters) / (len(clusters) - 1)) * ((rows - 1) / (rows - columns))
    covariance = correction * bread @ meat @ bread
    standard_error = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    degrees = len(clusters) - 1
    critical = float(student_t.ppf(0.975, degrees))
    estimates = []
    for index, name in enumerate(names):
        beta = float(coefficient[index])
        se = float(standard_error[index])
        statistic = beta / se if se > 0 else None
        p_value = float(2 * student_t.sf(abs(statistic), degrees)) if statistic is not None else None
        estimates.append({
            "feature": name,
            "coefficient": beta,
            "cluster_standard_error": se,
            "ci_95_lower": beta - critical * se,
            "ci_95_upper": beta + critical * se,
            "t_statistic": statistic,
            "p_value": p_value,
        })
    weighted_mse = float(np.sum(weights * np.square(residual)) / np.sum(weights))
    return {
        "rows": rows,
        "columns": columns,
        "rank": rank,
        "game_clusters": len(clusters),
        "cluster_df": degrees,
        "equal_game_weighted_mse": weighted_mse,
        "estimates": estimates,
    }


def load_common_support(panel_root: Path, selection_root: Path) -> tuple[list[dict], list[dict]]:
    selections = []
    for path in sorted(Path(selection_root).glob("*.selection.json")):
        selection = json.loads(path.read_text())
        if selection.get("split_role") != "market_train":
            raise ValueError("local projection received a non-Train selection")
        if selection.get("price_history_opened") is not False or selection.get("trades_opened") is not False:
            raise ValueError("selection receipt was modified after split freeze")
        selection["path"] = path.resolve()
        selection["sha256"] = sha256(path)
        selections.append(selection)
    selections.sort(key=lambda row: (row["scheduled_utc"], row["nflverse_game_id"]))
    if len(selections) != 163 or len({row["nflverse_game_id"] for row in selections}) != 163:
        raise ValueError("expected exact 163-game market_train population")

    rows, receipts = [], []
    targets = tuple(f"home_change_{horizon}s" for horizon in HORIZONS)
    required = set(FEATURES + targets + ("play_id",))
    for selection in selections:
        game = selection["nflverse_game_id"]
        panel = Path(panel_root) / game / "play_trade_alignment.csv"
        manifest = Path(panel_root) / game / "manifest.json"
        if not panel.is_file() or not manifest.is_file():
            raise ValueError(f"missing panel or manifest for {game}")
        alignment = json.loads(manifest.read_text())
        if alignment.get("scientific_score") is not False:
            raise ValueError("alignment manifest unexpectedly contains a scientific score")
        if alignment.get("selection_sha256") != selection["sha256"]:
            raise ValueError(f"selection binding mismatch for {game}")
        common, any_target, total = 0, {str(horizon): 0 for horizon in HORIZONS}, 0
        with panel.open(newline="") as stream:
            reader = csv.DictReader(stream)
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError(f"panel lacks frozen fields for {game}")
            for raw in reader:
                total += 1
                for horizon, target in zip(HORIZONS, targets):
                    if raw[target] != "":
                        any_target[str(horizon)] += 1
                if any(raw[target] == "" for target in targets):
                    continue
                if any(raw[feature] == "" for feature in FEATURES):
                    raise ValueError(f"common-support row has missing feature in {game}")
                feature_values = [float(raw[feature]) for feature in FEATURES]
                outcomes = {str(horizon): float(raw[target]) for horizon, target in zip(HORIZONS, targets)}
                if not np.isfinite(feature_values).all() or not np.isfinite(list(outcomes.values())).all():
                    raise ValueError(f"non-finite value in {game}")
                rows.append({
                    "game": game,
                    "scheduled_utc": selection["scheduled_utc"],
                    "play_id": raw["play_id"],
                    "features": feature_values,
                    "outcomes": outcomes,
                })
                common += 1
        receipts.append({
            "game": game,
            "scheduled_utc": selection["scheduled_utc"],
            "selection_sha256": selection["sha256"],
            "panel_sha256": sha256(panel),
            "alignment_manifest_sha256": sha256(manifest),
            "total_play_rows": total,
            "eligible_rows_by_horizon": any_target,
            "common_support_rows": common,
        })
    if len({(row["game"], row["play_id"]) for row in rows}) != len(rows):
        raise ValueError("duplicate game/play row")
    if set(row["game"] for row in rows) != set(row["nflverse_game_id"] for row in selections):
        raise ValueError("at least one Train game lacks common horizon support")
    return rows, receipts


def standardized_design(rows: list[dict]) -> tuple[np.ndarray, list[str], dict]:
    raw = np.asarray([row["features"] for row in rows], dtype=float)
    score = raw[:, :len(SCORE_FEATURES)]
    controls = raw[:, len(SCORE_FEATURES):]
    mean = controls.mean(axis=0)
    scale = controls.std(axis=0)
    constant = [CONTROL_FEATURES[index] for index, value in enumerate(scale) if value == 0]
    if constant:
        raise ValueError(f"constant frozen controls: {', '.join(constant)}")
    design = np.column_stack((np.ones(len(rows)), score, (controls - mean) / scale))
    names = ["intercept", *SCORE_FEATURES, *CONTROL_FEATURES]
    return design, names, {
        "score_features_unscaled": list(SCORE_FEATURES),
        "control_features_standardized": list(CONTROL_FEATURES),
        "control_mean": mean.tolist(),
        "control_scale": scale.tolist(),
        "design_condition_number": float(np.linalg.cond(design)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel-root", type=Path, required=True)
    parser.add_argument("--selection-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output.exists():
        raise ValueError("output already exists")
    args.output.mkdir(parents=True)
    source_path = Path(__file__).resolve()
    lock = {
        "schema": "nfl_train_local_projection_lock_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "problem": "descriptive home moneyline response after an observed NFL play",
        "horizons_seconds": list(HORIZONS),
        "response": "home_price_horizon_minus_pre_play_home_price",
        "exposures": list(SCORE_FEATURES),
        "controls": list(CONTROL_FEATURES),
        "sample": "same market_train plays with nonmissing 30s, 60s and 300s outcomes",
        "weighting": "equal total weight per NFL game",
        "inference": "WLS CR1 covariance clustered by NFL game; t reference with G-1 df",
        "interpretation": "descriptive adjusted association, not a causal shock or trading return",
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "controller_self_evolution": False,
        "formal_promotion": False,
        "source_code_sha256": sha256(source_path),
        "research_sources": list(SOURCES),
    }
    lock_path = args.output / "pre_score_lock.json"
    write_json(lock_path, lock)

    rows, receipts = load_common_support(args.panel_root, args.selection_root)
    games = [row["game"] for row in rows]
    design, names, preprocessing = standardized_design(rows)
    weights = equal_game_weights(games)
    results = {}
    for horizon in HORIZONS:
        outcome = np.asarray([row["outcomes"][str(horizon)] for row in rows], dtype=float)
        results[str(horizon)] = fit_clustered_wls(design, outcome, weights, games, names)
    result = {
        "schema": "nfl_train_local_projection_result_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pre_score_lock_sha256": sha256(lock_path),
        "games": len(set(games)),
        "common_support_rows": len(rows),
        "preprocessing": preprocessing,
        "horizons": results,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "scientific_score": False,
        "interpretation_boundary": (
            "Score changes and game states are endogenous. Coefficients are descriptive conditional "
            "responses on historical trade prints, not causal effects, executable alpha, or PnL."
        ),
    }
    receipt_path = args.output / "input_receipts.json"
    write_json(receipt_path, {"schema": "nfl_train_local_projection_inputs_v1", "games": receipts})
    result["input_receipts_sha256"] = sha256(receipt_path)
    result_path = args.output / "result.json"
    write_json(result_path, result)
    manifest = {
        "schema": "nfl_train_local_projection_manifest_v1",
        "complete": True,
        "pre_score_lock_sha256": sha256(lock_path),
        "input_receipts_sha256": sha256(receipt_path),
        "result_sha256": sha256(result_path),
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "scientific_score": False,
    }
    write_json(args.output / "manifest.json", manifest)
    summary = {}
    for horizon, values in results.items():
        wanted = {row["feature"]: row for row in values["estimates"]}
        summary[horizon] = {
            "home_score_change": wanted["home_score_change"],
            "away_score_change": wanted["away_score_change"],
            "equal_game_weighted_mse": values["equal_game_weighted_mse"],
        }
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
