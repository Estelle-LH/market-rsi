#!/usr/bin/env python3
"""Build a fresh, unopened continuation schedule after a source repair.

The parent learning-data root stays immutable.  Earlier scored Dev blocks are
folded into the first continuation Train input, while only the parent's still
unopened Dev blocks remain evaluation blocks.  This creates a new H0 study; it
does not pretend a source-changing repair belongs to the old fixed-H0 lineage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_archive_formal_data import (FEATURES, MAX_RUNNER_REQUEST_BYTES,
                                       ROW_FIELDS, SCHEMA as PARENT_SCHEMA)
from market_rsi import digest, file_hash, fresh_json, identifier


SCHEMA = "market_archive_repair_continuation_data_v1"
DAY_MS = 86_400_000


def _json(path: Path, maximum: int = 16 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized continuation input")
    return json.loads(path.read_bytes())


def _artifact(path: Path, *, experiment_id: str, task_id: str,
              split: str, rows: list[dict]) -> dict:
    if (split not in {"train", "dev"} or not rows
            or any(not isinstance(row, dict) or set(row) != set(ROW_FIELDS)
                   for row in rows)):
        raise ValueError("invalid continuation rows")
    value = {"schema": "market_permitted_rows_v1", "experiment_id": experiment_id,
             "task_id": task_id, "split": split, "feature_names": FEATURES,
             "rows": rows}
    fresh_json(path, value)
    return {"path": str(path.resolve()), "sha256": file_hash(path),
            "bytes": path.stat().st_size, "rows": len(rows),
            "games": len({row["game_id"] for row in rows})}


def _validate_parent(root: Path) -> dict:
    root = Path(root).resolve()
    receipt = _json(root / "receipt.json")
    rounds = _json(root / "lifecycle-rounds.json")
    inputs = _json(root / "round-inputs.json")
    policy = _json(root / "transfer-policy.json")
    from build_archive_formal_data import __file__ as parent_builder
    if (receipt.get("schema") != PARENT_SCHEMA
            or receipt.get("builder_source_sha256") != file_hash(parent_builder)
            or receipt.get("lifecycle_rounds_sha256") != digest(rounds)
            or receipt.get("round_inputs_sha256") != digest(inputs)
            or receipt.get("transfer_policy_sha256") != digest(policy)
            or receipt.get("transfer_materialized") is not False
            or receipt.get("future_test_used") is not False
            or len(rounds) != len(inputs)):
        raise ValueError("parent formal data root changed")
    for source in receipt.get("source_materializations", []):
        if file_hash(Path(source["path"])) != source["sha256"]:
            raise ValueError("parent source materialization changed")
    return {"root": root, "receipt": receipt, "rounds": rounds,
            "inputs": inputs, "policy": policy}


def _strict_prior_games(rows: list[dict], dev_rows: list[dict]) -> tuple[list[dict], dict]:
    """Keep whole games whose last label is on a date before Dev starts."""
    dev_day = min(row["feature_available_ms"] for row in dev_rows) // DAY_MS
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["game_id"], []).append(row)
    kept_games = {game_id for game_id, game_rows in grouped.items()
                  if max(row["label_available_ms"] for row in game_rows) // DAY_MS < dev_day}
    kept = [row for row in rows if row["game_id"] in kept_games]
    if not kept:
        raise ValueError("strict-date continuation Train is empty")
    return kept, {"source_rows": len(rows), "kept_rows": len(kept),
                  "omitted_rows": len(rows) - len(kept),
                  "source_games": len(grouped), "kept_games": len(kept_games),
                  "omitted_games": len(grouped) - len(kept_games),
                  "dev_start_utc_day": dev_day}


def build(parent_root: Path, output: Path, starting_round_id: str) -> dict:
    identifier(starting_round_id)
    parent = _validate_parent(parent_root)
    parent_ids = [item["round_id"] for item in parent["rounds"]]
    if starting_round_id not in parent_ids or parent_ids.index(starting_round_id) == 0:
        raise ValueError("continuation must begin after at least one parent round")
    start = parent_ids.index(starting_round_id)
    remaining_rounds = parent["rounds"][start:]
    remaining_inputs = parent["inputs"][start:]
    experiment_id = parent["receipt"]["experiment_id"]

    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    blocks = output / "blocks"
    blocks.mkdir(mode=0o700)
    component_rows: dict[str, list[dict]] = {}
    component_receipts: dict[str, dict] = {}
    lifecycle_rounds, round_inputs, round_reports = [], [], []
    available_ids: list[str] = []

    for offset, (parent_round, parent_input) in enumerate(zip(
            remaining_rounds, remaining_inputs)):
        round_id = parent_round["round_id"]
        task_id = "archive-formal-" + round_id
        if offset == 0:
            train_id = round_id + "-continuation-train"
            source_train = _json(Path(parent_input["train"]["path"]))
            if (file_hash(Path(parent_input["train"]["path"]))
                    != parent_input["train"]["sha256"]):
                raise ValueError("parent cumulative Train changed")
            source_train_rows = source_train["rows"]
        else:
            train_id = round_id + "-new-train"
            parent_train_id = parent_round["train_datasets"][0]["dataset_id"]
            parent_train_path = parent["root"] / "blocks" / f"{parent_train_id}.json"
            if file_hash(parent_train_path) != parent_round["train_datasets"][0]["content_sha256"]:
                raise ValueError("parent new-Train component changed")
            source_train_rows = _json(parent_train_path)["rows"]
        dev_id = round_id + "-dev"
        parent_dev_id = parent_round["dev_datasets"][0]["dataset_id"]
        parent_dev_path = parent["root"] / "blocks" / f"{parent_dev_id}.json"
        if file_hash(parent_dev_path) != parent_round["dev_datasets"][0]["content_sha256"]:
            raise ValueError("parent Dev component changed")
        dev_rows = _json(parent_dev_path)["rows"]
        new_train_rows, date_filter = _strict_prior_games(source_train_rows, dev_rows)

        component_rows[train_id] = new_train_rows
        component_rows[dev_id] = dev_rows
        component_receipts[train_id] = _artifact(
            blocks / f"{train_id}.json", experiment_id=experiment_id,
            task_id=train_id, split="train", rows=new_train_rows)
        component_receipts[dev_id] = _artifact(
            blocks / f"{dev_id}.json", experiment_id=experiment_id,
            task_id=dev_id, split="dev", rows=dev_rows)

        cumulative_ids = available_ids + [train_id]
        cumulative_map = {}
        for dataset_id in cumulative_ids:
            for row in component_rows[dataset_id]:
                if row["row_id"] in cumulative_map:
                    raise ValueError("row repeated in continuation Train")
                cumulative_map[row["row_id"]] = row
        cumulative = sorted(cumulative_map.values(), key=lambda row: (
            row["decision_ms"], row["row_id"]))
        if max(row["label_available_ms"] for row in cumulative) >= min(
                row["feature_available_ms"] for row in dev_rows):
            raise ValueError("continuation Train overlaps unopened Dev")
        if max(row["label_available_ms"] for row in cumulative) // DAY_MS >= min(
                row["feature_available_ms"] for row in dev_rows) // DAY_MS:
            raise ValueError("continuation Train is not on an earlier UTC date")
        train_receipt = _artifact(
            blocks / f"{round_id}-cumulative-train.json",
            experiment_id=experiment_id, task_id=task_id,
            split="train", rows=cumulative)
        dev_receipt = _artifact(
            blocks / f"{round_id}-sealed-dev.json",
            experiment_id=experiment_id, task_id=task_id,
            split="dev", rows=dev_rows)
        if train_receipt["bytes"] > MAX_RUNNER_REQUEST_BYTES:
            raise ValueError("continuation Train exceeds runner request cap")

        lifecycle_rounds.append({"round_id": round_id,
            "train_datasets": [{"dataset_id": train_id,
                                "content_sha256": component_receipts[train_id]["sha256"]}],
            "dev_datasets": [{"dataset_id": dev_id,
                              "content_sha256": component_receipts[dev_id]["sha256"]}]})
        round_inputs.append({"round_id": round_id, "task_id": task_id,
            "train_dataset_ids": cumulative_ids, "train": train_receipt,
            "dev_dataset_ids": [dev_id], "dev": dev_receipt,
            "materialization_sha256": digest({
                "round_id": round_id,
                "components": [{"dataset_id": dataset_id,
                    "content_sha256": component_receipts[dataset_id]["sha256"]}
                    for dataset_id in cumulative_ids],
                "cumulative_train_sha256": train_receipt["sha256"],
                "dev_sha256": dev_receipt["sha256"],
            })})
        round_reports.append({"round_id": round_id,
                              "cumulative_train_rows": len(cumulative),
                              "dev_rows": len(dev_rows),
                              "strict_date_filter": date_filter,
                              "source_parent_round": round_id})
        available_ids = cumulative_ids + [dev_id]

    transfer_policy = dict(parent["policy"])
    transfer_policy["opening"] = "once after every continuation submission is frozen"
    fresh_json(output / "transfer-policy.json", transfer_policy)
    fresh_json(output / "lifecycle-rounds.json", lifecycle_rounds)
    fresh_json(output / "round-inputs.json", round_inputs)
    receipt = {
        "schema": SCHEMA, "experiment_id": experiment_id,
        "builder_source_sha256": file_hash(__file__),
        "parent_data_root": str(parent["root"]),
        "parent_data_receipt_sha256": digest(parent["receipt"]),
        "starting_round_id": starting_round_id,
        "source_materializations": parent["receipt"]["source_materializations"],
        "sampling": parent["receipt"]["sampling"], "rounds": round_reports,
        "lifecycle_rounds_sha256": digest(lifecycle_rounds),
        "round_inputs_sha256": digest(round_inputs),
        "transfer_policy_sha256": digest(transfer_policy),
        "transfer_materialized": False, "formal_lineage_ready": False,
        "future_test_used": False,
    }
    for key in ("objective_id", "objective_contract_sha256"):
        if key in parent["receipt"]:
            receipt[key] = parent["receipt"][key]
    fresh_json(output / "receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--starting-round-id", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.parent_root, args.output, args.starting_round_id),
                     sort_keys=True, separators=(",", ":")))
