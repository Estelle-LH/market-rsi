"""Offline, previously opened Train comparison; no formal promotion or payment."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

import numpy as np

from causal_training_sampler import sampling_contract, select_training_rows
from market_rsi import digest, file_hash, fresh_json
from time_series_split_policy import train_cv_split


MODEL_FEATURES = ["mid", "spread", "imbalance", "log1p_bid_size", "log1p_ask_size"]
QUIET_FEATURES = sorted(["bid", "ask", "mid", "spread", "bid_size", "ask_size", "imbalance"])
STAGES = ("raw_data", "raw_indicator_signal", "prediction", "objective", "pnl")


def features(rows):
    values = []
    for row in rows:
        f = row["features"]
        if f["bid_size"] < 0 or f["ask_size"] < 0:
            raise ValueError("negative displayed size")
        values.append([f["mid"], f["spread"], f["imbalance"],
                       math.log1p(f["bid_size"]), math.log1p(f["ask_size"])])
    result = np.asarray(values, dtype=float)
    if not np.isfinite(result).all():
        raise ValueError("nonfinite model features")
    return result


def fit_predict(x, y, test_x, masks, *, population_rows, inverse_probability, alpha):
    keep = np.asarray([m["keep"] for m in masks])
    weights = np.asarray([m["loss_weight"] for m in masks])[keep]
    if not keep.any() or not np.isfinite(weights).all():
        raise ValueError("empty or invalid weighted fit")
    selected_x, selected_y = x[keep], y[keep]
    denominator = population_rows if inverse_probability else int(keep.sum())
    penalty = np.eye(x.shape[1]) * alpha
    penalty[0, 0] = 0.0
    lhs = (selected_x.T * weights) @ selected_x / denominator + penalty
    rhs = selected_x.T @ (weights * selected_y) / denominator
    beta = np.linalg.solve(lhs, rhs)
    return test_x @ beta, beta


def metrics(rows, predictions):
    y = np.asarray([row["target"] for row in rows])
    mids = np.asarray([row["features"]["mid"] for row in rows])
    errors = (predictions - y) ** 2
    persistence = (mids - y) ** 2
    by_game = defaultdict(list)
    for i, row in enumerate(rows):
        by_game[row["game_id"]].append(i)
    mse = float(np.mean([errors[indices].mean() for indices in by_game.values()]))
    baseline_mse = float(np.mean([persistence[indices].mean() for indices in by_game.values()]))
    flat = np.abs(y - mids) <= 1e-12
    diagnostics = {}
    for name, mask in (("flat_future", flat), ("moving_future", ~flat)):
        diagnostics[name] = {"rows": int(mask.sum()),
                             "row_rmse_probability_bps": float(np.sqrt(errors[mask].mean()) * 1e4)
                             if mask.any() else None}
    return {
        "rows": len(rows), "games": len(by_game),
        "equal_game_mse_probability_squared": mse,
        "equal_game_rmse_probability_bps": math.sqrt(mse) * 1e4,
        "persistence_equal_game_rmse_probability_bps": math.sqrt(baseline_mse) * 1e4,
        "mse_improvement_over_persistence_pct": 100 * (1 - mse / baseline_mse)
        if baseline_mse else None,
        "row_rmse_probability_bps": float(np.sqrt(errors.mean()) * 1e4),
        "future_activity_diagnostics_only": diagnostics,
    }


def run(source_path: Path, output: Path):
    if output.exists():
        raise FileExistsError(output)
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    if source.get("schema") != "market_permitted_rows_v1" or source.get("split") != "train":
        raise ValueError("explicit previously-open permitted Train block required")
    rows = source["rows"]
    rows.sort(key=lambda row: row["decision_ms"])
    if any(not math.isfinite(row["target"]) or not 0 <= row["target"] <= 1 for row in rows):
        raise ValueError("invalid target")
    dates = sorted({datetime.fromtimestamp(row["decision_ms"] / 1000, timezone.utc)
                    .date().isoformat() for row in rows})
    if dates != ["2026-08-29", "2026-08-30", "2026-08-31", "2026-09-01",
                 "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]:
        raise ValueError("this diagnostic is scoped to the already-open eight-day block")
    fit, cv, split = train_cv_split(rows, label_delay_bounds_ms=(330_000, 330_000))
    variants = [{"name": "full_population", "p": 1.0, "weighting": "inverse_probability"}]
    variants += [{"name": f"quiet_{int(p * 100)}pct_{weighting}", "p": p,
                  "weighting": weighting} for p in (0.10, 0.25, 0.50)
                 for weighting in ("inverse_probability", "unweighted")]
    alpha = 0.01
    common = {
        "raw_data": {"source_sha256": digest(source), "fit_ids": digest([r["row_id"] for r in fit]),
                     "cv_ids": digest([r["row_id"] for r in cv])},
        "raw_indicator_signal": {"features": MODEL_FEATURES,
                                 "normalizer": "same_full_fit_history_mean_std_all_variants"},
        "objective": {"id": "future-midpoint-window-mean-270-330s-v1",
                      "target": "unchanged_source_target", "fit_target": "target_minus_current_mid",
                      "score": "unweighted_equal_game_MSE_on_all_identical_CV_rows"},
        "pnl": {"executed": False, "cost_model": "not_applicable_prediction_only_diagnostic"},
    }
    baseline_prediction = {"model": "fixed_ridge", "alpha": alpha, "variant": variants[0]}
    baseline_ids = {stage: digest(baseline_prediction if stage == "prediction" else common[stage])
                    for stage in STAGES}
    contract = {
        "schema": "training_sampling_pre_fit_spec_v1", "source": str(source_path.resolve()),
        "source_file_sha256": file_hash(source_path), "code_sha256": file_hash(Path(__file__)),
        "sampler_code_sha256": file_hash(Path(__file__).with_name("causal_training_sampler.py")),
        "source_scope": "existing selected opened Train, not the full raw market population",
        "evidence_class": "post_hoc_open_train_diagnostic", "development_dates": dates,
        "final_test_dates": [], "final_test_sessions": 0,
        "promotion_eligible": False, "formal_validation_status": "insufficient_fresh_final_sessions",
        "imputation_policy": "forbidden", "expected_sign": None,
        "declared_changed_stage": "prediction", "baseline_component_ids": baseline_ids,
        "common": common, "split": split, "seed": 23, "alpha": alpha, "variants": variants,
        "sampling_semantics": {
            "inverse_probability": "weights 1/p, loss denominator full_fit_count; same expected row risk",
            "unweighted": "deliberately changes training emphasis; loss denominator retained_count",
        },
        "quiet_is_not_zero_future_target": True,
        "limitations": ["only eight previously inspected dates", "one origin, three-day CV",
                        "source had legacy upstream selection; no full-population claim",
                        "no verified trading PnL", "no model is auto-promoted"],
    }
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / "pre-fit-spec.json", contract)
    x, cv_x = features(fit), features(cv)
    mean, std = x.mean(axis=0), x.std(axis=0)
    std[std < 1e-12] = 1.0
    x = np.column_stack([np.ones(len(fit)), (x - mean) / std])
    cv_x = np.column_stack([np.ones(len(cv)), (cv_x - mean) / std])
    y = np.asarray([r["target"] - r["features"]["mid"] for r in fit])
    cv_mid = np.asarray([r["features"]["mid"] for r in cv])
    results, baseline_mse = [], None
    for variant in variants:
        policy = sampling_contract(feature_names=QUIET_FEATURES,
                                   quiet_keep_probability=variant["p"],
                                   weighting=variant["weighting"], seed=23)
        masks = select_training_rows(fit, contract=policy, role="opened_train")
        fresh_json(output / (variant["name"] + "-selection.json"), {"policy": policy, "rows": masks})
        started = time.monotonic()
        delta, beta = fit_predict(x, y, cv_x, masks, population_rows=len(fit),
                                 inverse_probability=variant["weighting"] == "inverse_probability",
                                 alpha=alpha)
        predictions = np.clip(cv_mid + delta, 0.0, 1.0)
        fit_seconds = time.monotonic() - started
        fresh_json(output / (variant["name"] + "-model.json"), {
            "features": MODEL_FEATURES, "normalizer_mean": mean.tolist(),
            "normalizer_std": std.tolist(), "coefficients": beta.tolist(), "alpha": alpha})
        fresh_json(output / (variant["name"] + "-predictions.json"), {
            "row_ids": [r["row_id"] for r in cv], "predictions": predictions.tolist()})
        score = metrics(cv, predictions)
        baseline_mse = score["equal_game_mse_probability_squared"] if baseline_mse is None else baseline_mse
        per_day = {}
        for day in sorted({r["decision_ms"] // 86_400_000 for r in cv}):
            indices = [i for i, r in enumerate(cv) if r["decision_ms"] // 86_400_000 == day]
            day_name = datetime.fromtimestamp(day * 86400, timezone.utc).date().isoformat()
            per_day[day_name] = metrics([cv[i] for i in indices], predictions[indices])
        kept = sum(m["keep"] for m in masks)
        quiet = sum(m["state"] == "repeated" for m in masks)
        quiet_kept = sum(m["state"] == "repeated" and m["keep"] for m in masks)
        candidate_ids = {**baseline_ids, "prediction": digest(
            {"model": "fixed_ridge", "alpha": alpha, "variant": variant})}
        results.append({
            **variant, "fit_rows": len(fit), "fit_kept": kept,
            "repeated_observed_states": quiet, "repeated_states_kept": quiet_kept,
            "kept_fraction": kept / len(fit), "fit_seconds_diagnostic_only": fit_seconds,
            "changed_states_dropped": sum(not m["keep"] and m["state"] != "repeated" for m in masks),
            "score": score, "per_day": per_day,
            "mse_improvement_over_full_fit_pct": 100 * (1 - score["equal_game_mse_probability_squared"] /
                                                      baseline_mse) if baseline_mse else None,
            "candidate_component_ids": candidate_ids,
        })
    if file_hash(source_path) != contract["source_file_sha256"]:
        raise ValueError("source changed during diagnostic")
    body = {"schema": "training_sampling_diagnostic_result_v1", "pre_fit_spec_sha256": digest(contract),
            "results": results, "selected_variant": None, "promotion_eligible": False,
            "source_unchanged": True, "paid_provider_cost_usd": 0.0,
            "new_dev_or_final_scored": False, "original_rows_deleted": 0}
    fresh_json(output / "result.json", {**body, "report_sha256": digest(body)})
    return body


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.train, args.output)
    print(json.dumps({"report": str(args.output / "result.json"),
                      "variants": [{"name": r["name"], "fit_kept": r["fit_kept"],
                                    "fit_rows": r["fit_rows"], "score": r["score"],
                                    "mse_improvement_over_full_fit_pct":
                                    r["mse_improvement_over_full_fit_pct"]}
                                   for r in report["results"]]}, indent=2))
