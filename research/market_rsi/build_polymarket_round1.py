#!/usr/bin/env python3
"""Freeze nine real historical tasks for the first Reset/Archive/Learn pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json
from polymarket_round1_protocol import build_protocol
from prediction_stream import encoded


FEATURES = ["bid", "ask", "mid", "spread", "bid_size", "ask_size", "imbalance"]
# August 26 is the collector's first partial day, so it is an explicit warm-up
# exclusion rather than silently treating incomplete coverage as a full day.
TRAIN_DATES = ("2026-08-27", "2026-09-01")
ROUTE_DATES = ("2026-09-02", "2026-09-03")
AUDIT_DATES = ("2026-09-04", "2026-09-05")
SEED = 23
MAX_TRAIN_ROWS = 6000
MAX_DEV_ROWS = 300
MIN_DEV_ROWS = 20
MIN_PERSISTENCE_MSE = 0.0000005


def _date(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat()


def _rank(row_id, namespace):
    return hashlib.sha256(f"{SEED}:{namespace}:{row_id}".encode()).hexdigest()


def _sample(rows, maximum, namespace):
    """A frozen identity-only sample; labels never affect inclusion."""
    selected = sorted(rows, key=lambda row: (_rank(row["row_id"], namespace), row["row_id"]))[:maximum]
    return sorted(selected, key=lambda row: (row["decision_ms"], row["row_id"]))


def _sample_dev(rows, maximum):
    """Uniform chronological coverage of a whole game, independent of labels."""
    ordered = sorted(rows, key=lambda row: (row["decision_ms"], row["row_id"]))
    if len(ordered) <= maximum:
        return ordered
    indices = [index * (len(ordered) - 1) // (maximum - 1) for index in range(maximum)]
    return [ordered[index] for index in indices]


def _permitted(row):
    return {key: row[key] for key in (
        "row_id", "game_id", "market_id", "decision_ms", "feature_available_ms",
        "features", "target", "label_available_ms")}


def _range(date, bounds):
    return bounds[0] <= date <= bounds[1]


def _eligible_games(rows, bounds):
    grouped = defaultdict(list)
    for row in rows:
        if _range(_date(row["game_start_ms"]), bounds):
            grouped[row["game_id"]].append(row)
    result = {}
    for game, values in grouped.items():
        if len(values) < MIN_DEV_ROWS:
            continue
        mse = sum((row["target"] - row["features"]["mid"]) ** 2 for row in values) / len(values)
        if mse >= MIN_PERSISTENCE_MSE:
            result[game] = values
    return result


def _choose_games(grouped, count, namespace):
    if len(grouped) < count:
        raise ValueError(f"only {len(grouped)} eligible {namespace} games; need {count}")
    chosen = sorted(grouped, key=lambda game: (_rank(game, namespace), game))[:count]
    return sorted(chosen, key=lambda game: (grouped[game][0]["game_start_ms"], game))


def build(materialized, output, experiment_id):
    if (materialized.get("schema") != "polymarket_midpoint_labels_v1"
            or materialized.get("evidence_class") != "historical_diagnostic"
            or materialized.get("scientific_admission") is not False
            or not isinstance(materialized.get("rows"), list)):
        raise ValueError("exact historical Polymarket materialization required")
    rows = materialized["rows"]
    train_pool = [row for row in rows if _range(_date(row["game_start_ms"]), TRAIN_DATES)]
    if not train_pool:
        raise ValueError("nonempty historical Train pool required")
    train = _sample(train_pool, MAX_TRAIN_ROWS, "train")
    route = _eligible_games(rows, ROUTE_DATES)
    audit = _eligible_games(rows, AUDIT_DATES)
    task_games = [(game, "learning") for game in _choose_games(route, 6, "learning")]
    task_games += [(game, "transfer") for game in _choose_games(audit, 3, "transfer")]

    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    data_dir = output / "task-data"
    data_dir.mkdir(mode=0o700)
    nonce = secrets.token_hex(32)
    test_policy = {
        "schema": "polymarket_prospective_test_policy_v1",
        "source_boundary_utc": "2026-09-07T16:08:41Z",
        "minimum_distinct_complete_games": 20,
        "selection": "first chronological eligible whole games after boundary",
        "opening": "once after all transfer submissions freeze",
        "nonce": nonce,
    }
    opaque_test_commitment = digest(test_policy)
    tasks, task_data, baselines, split_tasks = [], {}, {}, []
    limits = {"max_input_tokens": 48000, "max_output_tokens": 4096,
              "max_wall_seconds": 300}
    for index, (game, phase) in enumerate(task_games):
        task_id = f"pm-r1-task-{index:02d}"
        train_rows = [_permitted(row) for row in train]
        dev_private = _sample_dev(route[game] if phase == "learning" else audit[game],
                                  MAX_DEV_ROWS)
        dev_rows = [_permitted(row) for row in dev_private]
        if max(row["label_available_ms"] for row in train_rows) >= min(
                row["feature_available_ms"] for row in dev_rows):
            raise ValueError("Train labels overlap a later task")
        files = {}
        for split, values in (("train", train_rows), ("dev", dev_rows)):
            artifact = {"schema": "market_permitted_rows_v1", "experiment_id": experiment_id,
                        "task_id": task_id, "split": split, "feature_names": FEATURES,
                        "rows": values}
            raw = encoded(artifact)
            path = data_dir / f"{task_id}-{split}.json"
            with path.open("xb") as stream:
                stream.write(raw)
            files[split] = {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
                            "bytes": len(raw), "rows": len(values)}
        if files["train"]["bytes"] + files["dev"]["bytes"] > 16 * 1024 * 1024:
            raise ValueError("task artifacts exceed runner safety cap")
        task = {"schema": "market_research_task_v1", "experiment_id": experiment_id,
            "task_id": task_id, "task_index": index, "phase": phase,
            "objective": "Predict the first admitted Polymarket midpoint 60 seconds after each decision; compare MSE with persistence on the same rows.",
            "data_catalog": [
                {"artifact_id": task_id + "-train", "split": "train",
                 "sha256": files["train"]["sha256"],
                 "description": f"Frozen historical Train rows ({len(train_rows)} rows); labels available before Dev."},
                {"artifact_id": task_id + "-dev", "split": "dev",
                 "sha256": files["dev"]["sha256"],
                 "description": f"One later complete game mask ({len(dev_rows)} rows); labels scorer-owned."},
            ],
            "evaluation_contract": {"primary_metric": "mse", "target": "future_midpoint",
                                    "baseline_rule": "persistence"},
            "resource_limits": limits,
            "opaque_test_commitment": opaque_test_commitment}
        tasks.append(task)
        task_data[task_id] = {"train_id": task_id + "-train", "train_path": files["train"]["path"],
                              "dev_id": task_id + "-dev", "dev_path": files["dev"]["path"]}
        baseline = {row["row_id"]: row["features"]["mid"] for row in dev_rows}
        baselines[task_id] = digest(baseline)
        split_tasks.append({"task_id": task_id, "phase": phase, "game_id": game,
                            "game_start_date": _date(dev_private[0]["game_start_ms"]),
                            "train_rows": len(train_rows), "dev_rows": len(dev_rows),
                            "dev_sampling": f"uniform chronological coverage, maximum {MAX_DEV_ROWS}"})

    protocol = build_protocol(experiment_id=experiment_id,
        task_ids=[task["task_id"] for task in tasks],
        opaque_test_commitment=opaque_test_commitment)
    private = output / "test-policy-private.json"
    fresh_json(private, test_policy)
    os.chmod(private, 0o600)
    fresh_json(output / "protocol.json", protocol)
    fresh_json(output / "tasks.json", tasks)
    fresh_json(output / "task-data.json", task_data)
    fresh_json(output / "baseline-source-hashes.json", baselines)
    receipt = {
        "schema": "polymarket_round1_materialization_receipt_v1",
        "experiment_id": experiment_id,
        "source_bundle_sha256": materialized["source_bundle_sha256"],
        "materializer_source_sha256": file_hash(Path(__file__).with_name("polymarket_data.py")),
        "builder_source_sha256": file_hash(__file__),
        "target": "future_midpoint_at_60_seconds",
        "baseline": "current_midpoint_persistence",
        "feature_names": FEATURES,
        "sampling": {"seed": SEED, "row_sampling_label_independent": True,
                     "game_eligibility_uses_predeclared_persistence_difficulty": True,
                     "max_train_rows": MAX_TRAIN_ROWS, "max_dev_rows_per_task": MAX_DEV_ROWS,
                     "dev_row_sampling": "uniform_chronological",
                     "minimum_dev_rows_per_game": MIN_DEV_ROWS,
                     "minimum_full_game_persistence_mse": MIN_PERSISTENCE_MSE,
                     "difficulty_gate_set_before_any_candidate_or_model_call": True},
        "date_blocks": {"train": TRAIN_DATES, "learning": ROUTE_DATES, "transfer": AUDIT_DATES},
        "train_pool": {"eligible_rows": len(train_pool), "selected_rows": len(train)},
        "tasks": split_tasks,
        "opaque_prospective_test_commitment": opaque_test_commitment,
        "protocol_sha256": digest(protocol),
        "scientific_admission": False,
        "test_opened": False,
    }
    fresh_json(output / "materialization-receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    receipt = build(json.loads(args.input.read_text()), args.output, args.experiment_id)
    print(canonical(receipt))


if __name__ == "__main__":
    main()
