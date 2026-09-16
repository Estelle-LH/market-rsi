#!/usr/bin/env python3
"""Freeze three chronological multi-game learning rounds for Archive RSI.

This builder uses only pre-boundary historical materializations.  It creates
new-Train blocks, one sealed multi-game Dev block per round, and the exact
cumulative Train artifact that the controller may read in that round.  It does
not create the final data lifecycle or open/materialize Transfer data.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier


SCHEMA = "market_archive_formal_learning_data_v1"
FEATURES = ["bid", "ask", "mid", "spread", "bid_size", "ask_size", "imbalance"]
SEED = 23
DAY_MS = 86_400_000
MIN_ROWS_PER_GAME = 20
MIN_DEV_GAMES = 5
MAX_DEV_ROWS_PER_GAME = 300
MAX_RUNNER_REQUEST_BYTES = 8 * 1024 * 1024
TRANSFER_BOUNDARY = "2026-09-07T16:08:41Z"
TRANSFER_GAMES = 20
ROUND_SPECS = (
    {"round_id": "round-01", "new_train_dates": ("2026-08-27", "2026-09-01"),
     "max_new_train_rows": 6000, "dev_date": "2026-09-02"},
    {"round_id": "round-02", "new_train_dates": ("2026-09-03", "2026-09-03"),
     "max_new_train_rows": 2500, "dev_date": "2026-09-04"},
    {"round_id": "round-03", "new_train_dates": ("2026-09-05", "2026-09-05"),
     "max_new_train_rows": 2500, "dev_date": "2026-09-06"},
)
ROW_FIELDS = (
    "row_id", "game_id", "market_id", "decision_ms", "feature_available_ms",
    "features", "target", "label_available_ms",
)


def _date(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date().isoformat()


def _rank(row_id: str, namespace: str) -> str:
    return hashlib.sha256(f"{SEED}:{namespace}:{row_id}".encode()).hexdigest()


def _sample(rows: list[dict], maximum: int, namespace: str) -> list[dict]:
    selected = sorted(rows, key=lambda row: (_rank(row["row_id"], namespace), row["row_id"]))[:maximum]
    return sorted(selected, key=lambda row: (row["decision_ms"], row["row_id"]))


def _uniform(rows: list[dict], maximum: int) -> list[dict]:
    ordered = sorted(rows, key=lambda row: (row["decision_ms"], row["row_id"]))
    if len(ordered) <= maximum:
        return ordered
    indices = [index * (len(ordered) - 1) // (maximum - 1) for index in range(maximum)]
    return [ordered[index] for index in indices]


def _permitted(row: dict) -> dict:
    return {key: row[key] for key in ROW_FIELDS}


def _artifact(path: Path, *, experiment_id: str, task_id: str,
              split: str, rows: list[dict]) -> dict:
    value = {"schema": "market_permitted_rows_v1", "experiment_id": experiment_id,
             "task_id": task_id, "split": split, "feature_names": FEATURES,
             "rows": rows}
    fresh_json(path, value)
    return {"path": str(path.resolve()), "sha256": file_hash(path),
            "bytes": path.stat().st_size, "rows": len(rows),
            "games": len({row["game_id"] for row in rows})}


def _validate_source(value: dict) -> None:
    if (not isinstance(value, dict)
            or value.get("schema") != "polymarket_midpoint_labels_v1"
            or value.get("evidence_class") != "historical_diagnostic"
            or value.get("scientific_admission") is not False
            or value.get("test_opened") is not False
            or not isinstance(value.get("rows"), list) or not value["rows"]):
        raise ValueError("exact unopened historical materialization required")


def _eligible_dev(rows: list[dict], date: str) -> tuple[list[dict], list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["game_id"]].append(row)
    games, selected = [], []
    for game_id, values in sorted(grouped.items(), key=lambda item: (
            min(row["game_start_ms"] for row in item[1]), item[0])):
        # The outer boundary is about when predictions and labels exist, not a
        # game's nominal start date.  Admit only whole games whose complete row
        # population lies inside the predeclared Dev UTC date.  A game spanning
        # midnight is omitted instead of being split across time blocks.
        if {_date(row["decision_ms"]) for row in values} != {date}:
            continue
        if len(values) < MIN_ROWS_PER_GAME:
            continue
        sample = _uniform(values, MAX_DEV_ROWS_PER_GAME)
        # This is calculated only after target-blind membership is fixed.  It
        # is a difficulty diagnostic, never an eligibility rule.
        mse = sum((row["target"] - row["features"]["mid"]) ** 2
                  for row in sample) / len(sample)
        games.append({"game_id": game_id, "source_rows": len(values),
                      "selected_rows": len(sample), "persistence_mse": mse})
        selected.extend(sample)
    if len(games) < MIN_DEV_GAMES:
        raise ValueError(f"only {len(games)} eligible Dev games on {date}; need {MIN_DEV_GAMES}")
    return sorted(selected, key=lambda row: (row["decision_ms"], row["row_id"])), games


def build(sources: list[tuple[Path, dict]], output: Path, experiment_id: str) -> dict:
    identifier(experiment_id)
    if not sources:
        raise ValueError("at least one historical materialization required")
    rows, source_receipts, seen = [], [], set()
    objective_bindings: set[tuple[str, str]] = set()
    for path, value in sources:
        _validate_source(value)
        objective_id = value.get("objective_id")
        objective_contract_sha256 = value.get("objective_contract_sha256")
        if (objective_id is None) != (objective_contract_sha256 is None):
            raise ValueError("objective identity and contract hash must appear together")
        if objective_id is not None:
            identifier(objective_id)
            if (not isinstance(objective_contract_sha256, str)
                    or len(objective_contract_sha256) != 64
                    or any(character not in "0123456789abcdef"
                           for character in objective_contract_sha256)):
                raise ValueError("lowercase objective contract SHA-256 required")
            objective_bindings.add((objective_id, objective_contract_sha256))
        for row in value["rows"]:
            if row["row_id"] in seen:
                raise ValueError("duplicate row across materializations")
            seen.add(row["row_id"])
            rows.append(row)
        source_receipts.append({"path": str(Path(path).resolve()),
                                "sha256": file_hash(path),
                                "source_bundle_sha256": value["source_bundle_sha256"],
                                "rows": len(value["rows"])})
    if len(objective_bindings) > 1:
        raise ValueError("historical materializations use different objectives")
    if objective_bindings and len(objective_bindings) != 1:
        raise ValueError("exactly one objective binding required")

    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    blocks = output / "blocks"
    blocks.mkdir(mode=0o700)
    component_rows: dict[str, list[dict]] = {}
    component_receipts: dict[str, dict] = {}
    lifecycle_rounds, round_inputs, round_reports = [], [], []
    available_dataset_ids: list[str] = []

    for spec in ROUND_SPECS:
        round_id = spec["round_id"]
        task_id = "archive-formal-" + round_id
        dev, dev_games = _eligible_dev(rows, spec["dev_date"])
        dev_start = min(row["feature_available_ms"] for row in dev)
        # Games are catalogued by their scheduled start date, but their market
        # observations can begin on the previous UTC date.  The frozen outer
        # split requires Train labels to end on an earlier UTC date than the
        # first Dev feature, not merely at an earlier millisecond.  Purge to
        # the actual Dev feature-day boundary so the builder and runner enforce
        # the same chronological contract before any candidate is evaluated.
        dev_feature_day_start = (dev_start // DAY_MS) * DAY_MS
        lower, upper = spec["new_train_dates"]
        dated_pool = [row for row in rows if lower <= _date(row["game_start_ms"]) <= upper]
        existing_row_ids = {
            row["row_id"]
            for dataset_id in available_dataset_ids
            for row in component_rows[dataset_id]
        }
        chronological_pool = [
            row for row in dated_pool
            if row["label_available_ms"] < dev_feature_day_start
        ]
        pool = [
            row for row in chronological_pool
            if row["row_id"] not in existing_row_ids
        ]
        new_train = _sample(pool, spec["max_new_train_rows"], round_id + "-new-train")
        if not new_train:
            raise ValueError(f"empty new Train block for {round_id}")
        train_id, dev_id = round_id + "-new-train", round_id + "-dev"
        component_rows[train_id] = [_permitted(row) for row in new_train]
        component_rows[dev_id] = [_permitted(row) for row in dev]
        component_receipts[train_id] = _artifact(
            blocks / f"{train_id}.json", experiment_id=experiment_id,
            task_id=train_id, split="train", rows=component_rows[train_id])
        component_receipts[dev_id] = _artifact(
            blocks / f"{dev_id}.json", experiment_id=experiment_id,
            task_id=dev_id, split="dev", rows=component_rows[dev_id])

        # Match DataLifecycle.controller_view exactly: each round's new Train,
        # followed by that round's Dev only after it has been scored/promoted.
        cumulative_ids = available_dataset_ids + [train_id]
        cumulative_map = {}
        for dataset_id in cumulative_ids:
            for row in component_rows[dataset_id]:
                if row["row_id"] in cumulative_map:
                    raise ValueError("row repeated in cumulative Train")
                cumulative_map[row["row_id"]] = row
        cumulative = sorted(cumulative_map.values(), key=lambda row: (
            row["decision_ms"], row["row_id"]))
        if max(row["label_available_ms"] for row in cumulative) >= min(
                row["feature_available_ms"] for row in component_rows[dev_id]):
            raise ValueError(f"Train labels overlap sealed Dev in {round_id}")
        cumulative_receipt = _artifact(
            blocks / f"{round_id}-cumulative-train.json", experiment_id=experiment_id,
            task_id=task_id, split="train", rows=cumulative)
        dev_round_receipt = _artifact(
            blocks / f"{round_id}-sealed-dev.json", experiment_id=experiment_id,
            task_id=task_id, split="dev", rows=component_rows[dev_id])
        if cumulative_receipt["bytes"] > MAX_RUNNER_REQUEST_BYTES:
            raise ValueError(f"cumulative Train exceeds runner request cap in {round_id}")

        lifecycle_rounds.append({"round_id": round_id,
            "train_datasets": [{"dataset_id": train_id,
                                "content_sha256": component_receipts[train_id]["sha256"]}],
            "dev_datasets": [{"dataset_id": dev_id,
                              "content_sha256": component_receipts[dev_id]["sha256"]}]})
        round_inputs.append({"round_id": round_id, "task_id": task_id,
            "train_dataset_ids": cumulative_ids,
            "train": cumulative_receipt,
            "dev_dataset_ids": [dev_id], "dev": dev_round_receipt,
            "materialization_sha256": digest({
                "round_id": round_id,
                "components": [{"dataset_id": dataset_id,
                    "content_sha256": component_receipts[dataset_id]["sha256"]}
                    for dataset_id in cumulative_ids],
                "cumulative_train_sha256": cumulative_receipt["sha256"],
                "dev_sha256": dev_round_receipt["sha256"],
            })})
        round_reports.append({"round_id": round_id,
            "new_train_dates": list(spec["new_train_dates"]),
            "new_train_pool_rows_before_time_purge": len(dated_pool),
            "new_train_rows_purged_at_dev_boundary": (
                len(dated_pool) - len(chronological_pool)
            ),
            "new_train_rows_already_in_cumulative_history": (
                len(chronological_pool) - len(pool)
            ),
            "dev_first_feature_ms": dev_start,
            "dev_feature_utc_day_start_ms": dev_feature_day_start,
            "new_train_pool_rows": len(pool), "new_train_selected_rows": len(new_train),
            "cumulative_train_rows": len(cumulative), "dev_date": spec["dev_date"],
            "dev_games": dev_games, "dev_rows": len(dev)})
        available_dataset_ids = cumulative_ids + [dev_id]

    transfer_policy = {
        "schema": "market_prospective_transfer_policy_v1",
        "source_boundary_utc": TRANSFER_BOUNDARY,
        "minimum_distinct_complete_games": TRANSFER_GAMES,
        "selection": "first chronological eligible whole games after boundary",
        "eligibility": {"minimum_rows_per_game": MIN_ROWS_PER_GAME,
                        "future_target_based_filtering": False},
        "rows_per_game": {"method": "uniform chronological", "maximum": MAX_DEV_ROWS_PER_GAME},
        "opening": "once after every A0-A3 submission is frozen",
    }
    fresh_json(output / "transfer-policy.json", transfer_policy)
    fresh_json(output / "lifecycle-rounds.json", lifecycle_rounds)
    fresh_json(output / "round-inputs.json", round_inputs)
    receipt = {
        "schema": SCHEMA, "experiment_id": experiment_id,
        "builder_source_sha256": file_hash(__file__),
        "source_materializations": source_receipts,
        "sampling": {"seed": SEED, "label_independent_train_sampling": True,
                     "dev_game_gate_predeclared": True,
                     "dev_date_clock": "decision_ms_utc",
                     "dev_whole_game_date_rule": "all_rows_on_predeclared_utc_date",
                     "minimum_rows_per_game": MIN_ROWS_PER_GAME,
                     "minimum_dev_games": MIN_DEV_GAMES,
                     "dev_membership_target_blind": True,
                     "persistence_mse_computed_after_membership": True,
                     "maximum_dev_rows_per_game": MAX_DEV_ROWS_PER_GAME},
        "rounds": round_reports,
        "lifecycle_rounds_sha256": digest(lifecycle_rounds),
        "round_inputs_sha256": digest(round_inputs),
        "transfer_policy_sha256": digest(transfer_policy),
        "transfer_materialized": False,
        "formal_lineage_ready": False,
        "future_test_used": False,
    }
    if objective_bindings:
        objective_id, objective_contract_sha256 = next(iter(objective_bindings))
        receipt["objective_id"] = objective_id
        receipt["objective_contract_sha256"] = objective_contract_sha256
    fresh_json(output / "receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    sources = [(path, json.loads(path.read_bytes())) for path in args.input]
    try:
        print(canonical(build(sources, args.output, args.experiment_id)))
    except Exception as error:
        if args.output.exists() and not (args.output / "failure.json").exists():
            fresh_json(args.output / "failure.json", {
                "error_type": type(error).__name__, "message": str(error),
                "automatic_retry": False, "paid_work": False,
                "formal_lineage_started": False,
            })
        raise


if __name__ == "__main__":
    main()
