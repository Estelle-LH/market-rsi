"""Opened-Train label stratification, separate from label-blind event sampling.

Exploratory follow-up to the state-thinning diagnostic. Held-out rows are never
removed. Reuses the exact source, model, target and time split of that diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from market_rsi import digest, file_hash, fresh_json
from run_training_sampling_diagnostic import features, fit_predict, metrics, MODEL_FEATURES
from time_series_split_policy import train_cv_split


def label_selection(rows, *, role, fit_cutoff_ms, flat_probability, weighting, seed=23):
    if role != "opened_train":
        raise ValueError("label sampling is opened_train only")
    if (type(fit_cutoff_ms) is not int or isinstance(flat_probability, bool)
            or not isinstance(flat_probability, (int, float))
            or not math.isfinite(flat_probability) or not 0 < flat_probability <= 1
            or weighting not in {"inverse_probability", "unweighted"}
            or type(seed) is not int):
        raise ValueError("invalid sampling specification")
    result, ids = [], set()
    for ordinal, row in enumerate(rows):
        if row["row_id"] in ids:
            raise ValueError("duplicate identity")
        ids.add(row["row_id"])
        if (type(row.get("label_available_ms")) is not int
                or row["label_available_ms"] >= fit_cutoff_ms):
            raise ValueError("Train label was not available before fit cutoff")
        target, mid = row["target"], row["features"]["mid"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) or not 0 <= v <= 1 for v in (target, mid)):
            raise ValueError("finite probability target and midpoint required")
        flat = abs(target - mid) <= 1e-12
        p = flat_probability if flat else 1.0
        key = hashlib.sha256(f'{seed}\0{row["row_id"]}'.encode()).digest()
        keep = int.from_bytes(key[:8], "big") < int(p * 2**64)
        result.append({"row_id": row["row_id"], "original_ordinal": ordinal,
                       "state": "known_train_zero_target" if flat else "known_train_moving_target",
                       "keep": keep, "inclusion_probability": p,
                       "loss_weight": (1 / p if weighting == "inverse_probability" else 1.)
                       if keep else 0.})
    return result


def run(prior_run: Path, output: Path):
    if output.exists():
        raise FileExistsError(output)
    prior = json.loads((prior_run / "pre-fit-spec.json").read_bytes())
    original_result = json.loads((prior_run / "result.json").read_bytes())
    source_path = Path(prior["source"])
    source_hash = file_hash(source_path)
    if source_hash != prior["source_file_sha256"]:
        raise ValueError("source changed since reference diagnostic")
    source = json.loads(source_path.read_bytes())
    if source.get("split") != "train" or source.get("schema") != "market_permitted_rows_v1":
        raise ValueError("opened permitted Train required")
    rows = sorted(source["rows"], key=lambda r: r["decision_ms"])
    fit, cv, split = train_cv_split(rows, label_delay_bounds_ms=(330000, 330000))
    if split != prior["split"]:
        raise ValueError("split changed")
    if digest([r["row_id"] for r in cv]) != prior["common"]["raw_data"]["cv_ids"]:
        raise ValueError("evaluation row membership changed")
    variants = [{"name": "full_population", "p": 1., "weighting": "inverse_probability"}]
    variants += [{"name": f"zero_target_{int(p * 100)}pct_{w}", "p": p, "weighting": w}
                 for p in (.1, .25, .5) for w in ("inverse_probability", "unweighted")]
    spec = {
        "schema": "opened_train_label_sampling_pre_fit_v1", "prior_spec_sha256": digest(prior),
        "prior_results_inspected": True, "use": "post_hoc_method_diagnostic_not_fresh_test",
        "source_file_sha256": source_hash, "split": split, "common": prior["common"],
        "code_sha256": file_hash(Path(__file__)),
        "model_helper_sha256": file_hash(Path(__file__).with_name("run_training_sampling_diagnostic.py")),
        "seed": 23, "alpha": prior["alpha"], "variants": variants,
        "fit_cutoff_ms": split["boundary_ms"], "zero_target_tolerance": 1e-12,
        "label_aware_sampling_scope": "opened_Train_labels_available_before_fit_cutoff_only",
        "cv_membership_unchanged": True, "promotion_eligible": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / "pre-fit-spec.json", spec)
    x, cv_x = features(fit), features(cv)
    mean, std = x.mean(axis=0), x.std(axis=0)
    std[std < 1e-12] = 1.
    x = np.column_stack([np.ones(len(fit)), (x - mean) / std])
    cv_x = np.column_stack([np.ones(len(cv)), (cv_x - mean) / std])
    y = np.array([r["target"] - r["features"]["mid"] for r in fit])
    cv_mid = np.array([r["features"]["mid"] for r in cv])
    expected_mse = original_result["results"][0]["score"]["equal_game_mse_probability_squared"]
    results = []
    for variant in variants:
        masks = label_selection(fit, role="opened_train", fit_cutoff_ms=split["boundary_ms"],
                                flat_probability=variant["p"], weighting=variant["weighting"])
        fresh_json(output / (variant["name"] + "-selection.json"), {"rows": masks})
        delta, beta = fit_predict(x, y, cv_x, masks, population_rows=len(fit),
                                 inverse_probability=variant["weighting"] == "inverse_probability",
                                 alpha=prior["alpha"])
        prediction = np.clip(cv_mid + delta, 0., 1.)
        score = metrics(cv, prediction)
        if variant["name"] == "full_population" and score["equal_game_mse_probability_squared"] != expected_mse:
            raise ValueError("full-fit reference did not reproduce exactly")
        fresh_json(output / (variant["name"] + "-model.json"), {
            "features": MODEL_FEATURES, "normalizer_mean": mean.tolist(),
            "normalizer_std": std.tolist(), "coefficients": beta.tolist(), "alpha": prior["alpha"]})
        fresh_json(output / (variant["name"] + "-predictions.json"), {
            "row_ids": [r["row_id"] for r in cv], "predictions": prediction.tolist()})
        per_day = {}
        for day in sorted({r["decision_ms"] // 86400000 for r in cv}):
            indices = [i for i, r in enumerate(cv) if r["decision_ms"] // 86400000 == day]
            per_day[str(day)] = metrics([cv[i] for i in indices], prediction[indices])
        kept = sum(m["keep"] for m in masks)
        moving_kept = sum(m["keep"] and m["state"] == "known_train_moving_target" for m in masks)
        results.append({**variant, "fit_rows": len(fit), "fit_kept": kept,
                        "moving_train_rows_kept": moving_kept, "moving_kept_fraction": moving_kept / kept,
                        "score": score, "per_utc_day": per_day,
                        "mse_change_vs_full_fit_pct": 100 * (
                            score["equal_game_mse_probability_squared"] / expected_mse - 1)})
    if file_hash(source_path) != source_hash:
        raise ValueError("source mutated")
    body = {"schema": "opened_train_label_sampling_result_v1", "pre_fit_spec_sha256": digest(spec),
            "results": results, "selected_variant": None, "promotion_eligible": False,
            "baseline_reproduced_exactly": True, "raw_rows_deleted": 0,
            "new_dev_or_final_scored": False, "paid_provider_cost_usd": 0.0}
    fresh_json(output / "result.json", {**body, "report_sha256": digest(body)})
    return body


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.prior_run, args.output)
    print(json.dumps({"report": str(args.output / "result.json"), "variants": [
        {"name": r["name"], "fit_kept": r["fit_kept"], "moving_kept_fraction": r["moving_kept_fraction"],
         "rmse_bps": r["score"]["equal_game_rmse_probability_bps"],
         "mse_change_vs_full_fit_pct": r["mse_change_vs_full_fit_pct"]} for r in result["results"]]}, indent=2))
