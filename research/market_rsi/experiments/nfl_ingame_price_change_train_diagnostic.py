"""Bounded opened-Train trade-price diagnostic; not execution or profitability.

The existing native worker invokes this sibling with --source-root and --output.
The Supervisor supplies a hash-bound, immutable per-attempt operation beside runs/.
No account client, network access, retries, protected data or old scorer changes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from experiments import nfl_ingame_price_data as data
from experiments import nfl_ingame_price_score as scoring
from supervisor_harness.opened_train_discovery_worker import save, sha

TASK = "MarketTradeVWAPChange300sTrainDiagnostic-v1"
SEED = 314159
ORDINARY = "B1-FixedHGBRegressor"
ZERO = "B0-NoPriceChange"
RECIPE = dict(loss="squared_error", max_iter=150, learning_rate=.05,
              max_leaf_nodes=15, min_samples_leaf=20, l2_regularization=10,
              early_stopping=False, random_state=SEED)
STORE = Path("/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/artifacts")
REPO = Path(__file__).resolve().parents[3]


def binding(value):
    path = Path(value["path"])
    if set(value) != {"path", "sha256"} or not path.is_absolute() or path.resolve() != path or sha(path) != value["sha256"]:
        raise ValueError("file binding drift")
    return path


def matrices(fit, check):
    """Candidate sees past-only arrays/history, never labels/missingness/IDs at check."""
    x = np.asarray([r["features"] for r in fit], dtype=np.float64)
    y = np.asarray([r["label"] for r in fit], dtype=np.float64)
    xc = np.asarray([r["features"] for r in check], dtype=np.float64)
    counts = Counter(r["game_id"] for r in fit)
    weights = np.asarray([1 / counts[r["game_id"]] for r in fit])
    weights /= weights.mean()
    histories = [[tuple(trade) for trade in r["history"]] for r in fit]
    check_histories = [[tuple(trade) for trade in r["history"]] for r in check]
    if x.shape != (len(fit), 13) or xc.shape != (len(check), 13) or not all(np.isfinite(v).all() for v in (x, y, xc, weights)):
        raise ValueError("invalid past-only fit/check matrices")
    return x, y, weights, xc, histories, check_histories


def annotate_folds(rows):
    dates = sorted({r["game_date"] for r in rows})
    if len(dates) != 42:
        raise ValueError("frozen42date population required")
    for row in rows:
        index = dates.index(row["game_date"])
        row["fold"] = "initial_fit" if index < 22 else f"check_{1 + (index - 22) // 5}"


def _progress(output, entered, completed):
    temporary = output / ".fit-progress-pending.json"
    save(temporary, {"fit_calls_entered": entered, "fit_calls_completed": completed})
    os.replace(temporary, output / "fit_progress.json")


def operation_commitment(op):
    """Bind every operation field except the outer review binding; no hash cycle."""
    core = {k: v for k, v in op.items() if k != "review"}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def reference_predictions(reference_path, check_rows, receipts):
    reference = json.loads(reference_path.read_text())
    if reference.get("task_id") != TASK or reference.get("complete") is not True or reference.get("model_fits") != 4:
        raise ValueError("ordinary reference manifest changed")
    receipt_path, csv_path = reference_path.parent / "input_receipts.json", reference_path.parent / "predictions.csv"
    if sha(csv_path) != reference["predictions_sha256"] or sha(receipt_path) != reference["input_receipts_sha256"] or json.loads(receipt_path.read_text()) != json.loads(json.dumps(receipts)):
        raise ValueError("ordinary source or predictions changed")
    with csv_path.open() as stream:
        baseline_rows = list(csv.DictReader(stream))
    by_id = {r["row_id"]: r for r in baseline_rows}
    if len(by_id) != len(baseline_rows) or set(by_id) != {r["row_id"] for r in check_rows}:
        raise ValueError("ordinary common forecast mask changed")
    for row in check_rows:
        old = by_id[row["row_id"]]
        label = None if old["label"] == "" else float(old["label"])
        if label != row["label"] or float(old["p_current"]) != row["p_current"] or any(old[k] != str(row[k]) for k in ("game_id", "game_date", "game_week", "fold", "anchor_s")):
            raise ValueError("ordinary common price/label/identity changed")
    return {key: float(row[ORDINARY]) for key, row in by_id.items()}


def _operation(output):
    path = output.parent.parent / f"{output.name}.price_operation.json"
    op = json.loads(path.read_text())
    if set(op) != {"schema", "task_id", "attempt_id", "candidate_id", "mode", "source_commit", "plan", "review", "deadline_utc", "candidate", "ordinary_reference"}:
        raise ValueError("exact price operation fields required")
    if op["schema"] != "market_trade_price_operation_v1" or op["task_id"] != TASK or op["mode"] not in {"ordinary", "candidate"}:
        raise ValueError("frozen price task/operation required")
    plan = json.loads(binding(op["plan"]).read_text())
    if plan["task_id"] != TASK or plan["horizon_choice"]["seconds"] != 300:
        raise ValueError("price plan changed")
    review = json.loads(binding(op["review"]).read_text())
    if review.get("passed") is not True or review.get("operation_core_sha256") != operation_commitment(op):
        raise ValueError("exact independent operation review required")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip() != op["source_commit"]:
        raise ValueError("source checkpoint changed")
    if datetime.now(timezone.utc) >= datetime.fromisoformat(op["deadline_utc"].replace("Z", "+00:00")):
        raise ValueError("pilot deadline reached")
    if output.name != op["attempt_id"]:
        raise ValueError("attempt/output identity mismatch")
    return op


def run(source_root, output):
    output = Path(output)
    if output.resolve() != output or not output.is_relative_to(STORE) or output.exists():
        raise ValueError("fresh permanent output required")
    op = _operation(output)
    output.mkdir()
    _progress(output, 0, 0)
    rows, receipts = data.materialize(Path(source_root))
    annotate_folds(rows)
    folds = data.chronological_folds(rows)
    if len(rows) != 4485 or len(folds) != 4 or sum(len(c) for _, c in folds) != 1356:
        raise ValueError("frozen price population/check geometry changed")
    check_rows = [r for _, check in folds for r in check]
    if sum(r["label"] is not None for r in check_rows) != 991:
        raise ValueError("frozen common label mask changed")
    candidate = None
    predictions = {ZERO: {r["row_id"]: 0. for r in check_rows}}
    if op["mode"] == "candidate":
        candidate_path = binding(op["candidate"])
        spec = importlib.util.spec_from_file_location("reviewed_price_candidate", candidate_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        candidate = module.fit_predict
        predictions[ORDINARY] = reference_predictions(binding(op["ordinary_reference"]), check_rows, receipts)
    elif op["candidate"] is not None or op["ordinary_reference"] is not None:
        raise ValueError("ordinary run cannot import candidate/reference")
    name = ORDINARY if candidate is None else op["candidate_id"]
    lock = {"task_id": TASK, "operation": op, "operation_sha256": sha(output.parent.parent / f"{output.name}.price_operation.json"),
            "features": list(data.FEATURE_NAMES), "ordinary_recipe": RECIPE, "seed": SEED,
            "check_ids": [r["row_id"] for r in check_rows], "label_ids": [r["row_id"] for r in check_rows if r["label"] is not None],
            "fit_ids": [[r["row_id"] for r in fit] for fit, _ in folds],
            "interpretation": "historical opened-Train Discovery, not untouched OOS or executable profit"}
    save(output / "input_receipts.json", receipts)
    save(output / "pre_score_lock.json", lock)
    save(output / "exclusions.json", [{k: r[k] for k in ("row_id", "game_id", "game_date", "reason")} for r in rows if r["reason"]])
    predicted = {}
    entered = completed = 0
    for fit, check in folds:
        if datetime.now(timezone.utc) >= datetime.fromisoformat(op["deadline_utc"].replace("Z", "+00:00")):
            raise ValueError("deadline before next fit")
        x, y, weights, xc, history, check_history = matrices(fit, check)
        entered += 1
        _progress(output, entered, completed)
        if candidate is None:
            values = HistGradientBoostingRegressor(**RECIPE).fit(x, y, sample_weight=weights).predict(xc)
        else:
            values = candidate(x, y, weights, xc, history, check_history, seed=SEED)
        values = np.asarray(values, dtype=float)
        if values.shape != (len(check),) or not np.isfinite(values).all():
            raise ValueError("candidate predictions missing/nonfinite/wrong shape")
        predicted.update({r["row_id"]: float(p) for r, p in zip(check, values)})
        completed += 1
        _progress(output, entered, completed)
    predictions[name] = predicted
    card = scoring.score(rows, predictions, draws=2000, seed=SEED)
    card.update(task_id=TASK, candidate_id=op["candidate_id"], source_commit=op["source_commit"],
                model_fits=4, historical_event_clock_only=True, provider_cost_usd="0",
                external_fetch=False, paid_provider=False, route_dev_opened=False, sealed_final_opened=False,
                promotion_authorized=False, prices_executable=False)
    fields = ["row_id", "game_id", "game_date", "game_week", "fold", "anchor_s", "p_current", "label", *predictions]
    with (output / "predictions.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{**{k: r[k] for k in fields if k not in predictions},
                           **{model: values[r["row_id"]] for model, values in predictions.items()}} for r in check_rows])
    save(output / "scorecard.json", card)
    manifest = {"schema": "market_trade_price_manifest_v1", "task_id": TASK, "complete": True, "model_fits": 4,
                "mode": op["mode"], "source_commit": op["source_commit"], "population_games": 195,
                "historical_train_discovery_only": True, "provider_cost_usd": "0"}
    for key in ("pre_score_lock", "input_receipts", "exclusions", "predictions", "scorecard"):
        manifest[key + "_sha256"] = sha(output / (key + (".csv" if key == "predictions" else ".json")))
    save(output / "manifest.json", manifest)
    return card


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source_root, args.output), sort_keys=True, allow_nan=False))
