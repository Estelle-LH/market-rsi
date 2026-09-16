#!/usr/bin/env python3
"""Materialize one target-blind, chronological Train/Dev research block.

The schedule is frozen before candidate execution.  Membership uses only row
identity, availability timestamps, UTC dates, and whole-game identity.  Target
values are copied into runner-owned artifacts only after membership is fixed;
they are never used to choose a date, game, or row.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, identifier
from objective_contract import validate_objective_contract
from time_series_split_policy import (FORECAST_HORIZON_MS,
                                      MAXIMUM_LABEL_LATENESS_MS, POLICY,
                                      policy_contract, train_cv_split,
                                      validate_outer_dev)


SCHEDULE_SCHEMA = "market_time_series_selection_schedule_v1"
SCHEMA = "market_prospective_time_series_materialization_v1"
FEATURES = ["bid", "ask", "mid", "spread", "bid_size", "ask_size", "imbalance"]
ROW_FIELDS = (
    "row_id", "game_id", "market_id", "decision_ms", "feature_available_ms",
    "features", "target", "label_available_ms",
)
SELECTION_FIELDS = (
    "row_id", "game_id", "market_id", "decision_ms", "feature_available_ms",
    "label_available_ms",
)
MIN_ROWS_PER_GAME = 20
MAX_ROWS_PER_GAME = 300
MAX_JSON_BYTES = 256 * 1024 * 1024


def _json(path: Path, maximum: int = MAX_JSON_BYTES) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized materializer input")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("materializer JSON root must be an object")
    return value


def _sha(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError("lowercase SHA-256 commitment required")
    return value


def _date(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date().isoformat()


def _dates(values: list[str], *, minimum: int, name: str) -> list[str]:
    if (not isinstance(values, list) or len(values) < minimum
            or values != sorted(set(values))):
        raise ValueError(f"{name} must contain at least {minimum} unique chronological dates")
    for value in values:
        if datetime.strptime(value, "%Y-%m-%d").date().isoformat() != value:
            raise ValueError(f"invalid {name} UTC date")
    return list(values)


def freeze_schedule(
    path: Path,
    *,
    experiment_id: str,
    objective_contract_path: Path,
    train_utc_dates: list[str],
    dev_utc_dates: list[str],
    reserved_game_ids: list[str],
    reservation_commitment_sha256: str,
    evidence_class: str,
) -> dict:
    """Write the one-time split decision before any candidate is scored."""
    identifier(experiment_id)
    objective_path = Path(objective_contract_path).resolve()
    objective = validate_objective_contract(
        _json(objective_path), experiment_id=experiment_id
    )
    if evidence_class not in {"diagnostic", "formal_learning"}:
        raise ValueError("schedule evidence class must be diagnostic or formal_learning")
    train_dates = _dates(
        train_utc_dates, minimum=POLICY.formal_minimum_train_utc_days,
        name="Train",
    )
    dev_dates = _dates(
        dev_utc_dates, minimum=POLICY.outer_dev_minimum_utc_days, name="Dev"
    )
    if train_dates[-1] >= dev_dates[0]:
        raise ValueError("Train dates must be strictly earlier than Dev dates")
    if (not isinstance(reserved_game_ids, list)
            or reserved_game_ids != sorted(set(reserved_game_ids))):
        raise ValueError("reserved game IDs must be a sorted unique list")
    for game_id in reserved_game_ids:
        if not isinstance(game_id, str) or not game_id:
            raise ValueError("reserved game ID must be a nonempty string")
    schedule = {
        "schema": SCHEDULE_SCHEMA,
        "experiment_id": experiment_id,
        "evidence_class": evidence_class,
        "objective": {
            "contract_path": str(objective_path),
            "contract_file_sha256": file_hash(objective_path),
            "objective_contract_sha256": objective["objective_contract_sha256"],
            "objective_id": objective["objective_id"],
            "frozen_before_schedule": True,
        },
        "time_series_policy": policy_contract(),
        "train_utc_dates": train_dates,
        "dev_utc_dates": dev_dates,
        "selection": {
            "game_rule": "all_eligible_whole_games_on_predeclared_dates",
            "row_rule": "uniform_chronological_without_target",
            "minimum_rows_per_game": MIN_ROWS_PER_GAME,
            "maximum_rows_per_game": MAX_ROWS_PER_GAME,
            "membership_fields": list(SELECTION_FIELDS),
            "target_fields_used": [],
            "candidate_scores_used": False,
        },
        "exclusions": {
            "reserved_game_ids": reserved_game_ids,
            "reservation_commitment_sha256": _sha(
                reservation_commitment_sha256
            ),
        },
        "openings": {"dev": 1, "future_test": 0},
    }
    fresh_json(path, schedule)
    return schedule


def _validate_schedule(value: dict) -> dict:
    if (value.get("schema") != SCHEDULE_SCHEMA
            or value.get("time_series_policy") != policy_contract()
            or value.get("openings") != {"dev": 1, "future_test": 0}):
        raise ValueError("selection schedule or frozen time-series policy changed")
    identifier(value.get("experiment_id"))
    objective_receipt = value.get("objective")
    if (not isinstance(objective_receipt, dict) or set(objective_receipt) != {
            "contract_path", "contract_file_sha256", "objective_contract_sha256",
            "objective_id", "frozen_before_schedule",
    } or objective_receipt["frozen_before_schedule"] is not True):
        raise ValueError("objective was not frozen before the Dev schedule")
    objective_path = Path(objective_receipt["contract_path"]).resolve()
    if file_hash(objective_path) != objective_receipt["contract_file_sha256"]:
        raise ValueError("frozen objective contract file changed")
    objective = validate_objective_contract(
        _json(objective_path), experiment_id=value["experiment_id"]
    )
    if (objective["objective_contract_sha256"]
            != objective_receipt["objective_contract_sha256"]
            or objective["objective_id"] != objective_receipt["objective_id"]):
        raise ValueError("selection schedule is bound to a different objective")
    if (value.get("evidence_class") == "formal_learning"
            and objective["selection"]["evidence_class"] != "formal_learning"):
        raise ValueError("formal Dev schedule requires a formal objective selection")
    # This builder copies the historical 60-second point label. Other target
    # contracts require their own independently tested label materializer.
    if objective["objective_id"] != "future-midpoint-point-60s-v1":
        raise ValueError("selected objective requires a matching label materializer")
    if value.get("evidence_class") not in {"diagnostic", "formal_learning"}:
        raise ValueError("invalid schedule evidence class")
    train_dates = _dates(
        value.get("train_utc_dates"), minimum=POLICY.formal_minimum_train_utc_days,
        name="Train",
    )
    dev_dates = _dates(
        value.get("dev_utc_dates"), minimum=POLICY.outer_dev_minimum_utc_days,
        name="Dev",
    )
    expected_selection = {
        "game_rule": "all_eligible_whole_games_on_predeclared_dates",
        "row_rule": "uniform_chronological_without_target",
        "minimum_rows_per_game": MIN_ROWS_PER_GAME,
        "maximum_rows_per_game": MAX_ROWS_PER_GAME,
        "membership_fields": list(SELECTION_FIELDS),
        "target_fields_used": [],
        "candidate_scores_used": False,
    }
    exclusions = value.get("exclusions")
    if (train_dates[-1] >= dev_dates[0]
            or value.get("selection") != expected_selection
            or not isinstance(exclusions, dict)
            or set(exclusions) != {
                "reserved_game_ids", "reservation_commitment_sha256"
            }
            or exclusions["reserved_game_ids"]
            != sorted(set(exclusions["reserved_game_ids"]))):
        raise ValueError("invalid target-blind selection schedule")
    _sha(exclusions["reservation_commitment_sha256"])
    return value


def _validate_source(value: dict) -> None:
    if (value.get("schema") != "polymarket_midpoint_labels_v1"
            or value.get("evidence_class") != "historical_diagnostic"
            or value.get("scientific_admission") is not False
            or value.get("test_opened") is not False
            or not isinstance(value.get("rows"), list)
            or not value["rows"]):
        raise ValueError("exact unopened closed-day materialization required")
    _sha(value.get("source_bundle_sha256"))


def _validate_row(row: dict) -> None:
    required = set(ROW_FIELDS) | {"game_start_ms"}
    if not isinstance(row, dict) or not required <= set(row):
        raise ValueError("source row lacks required time-series fields")
    for key in ("row_id", "game_id", "market_id"):
        if not isinstance(row[key], str) or not row[key]:
            raise ValueError("invalid time-series row identity")
    for key in ("decision_ms", "feature_available_ms", "label_available_ms",
                "game_start_ms"):
        if type(row[key]) is not int:
            raise ValueError("integer time-series timestamps required")
    label_delay = row["label_available_ms"] - row["decision_ms"]
    if (row["feature_available_ms"] > row["decision_ms"]
            or not (FORECAST_HORIZON_MS <= label_delay
                    <= FORECAST_HORIZON_MS + MAXIMUM_LABEL_LATENESS_MS)
            or row["label_available_ms"] >= row["game_start_ms"]):
        raise ValueError("noncausal time-series source row")
    if (set(row["features"]) != set(FEATURES)
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in row["features"].values())
            or isinstance(row["target"], bool)
            or not isinstance(row["target"], (int, float))
            or not math.isfinite(row["target"])):
        raise ValueError("invalid time-series feature or target")


def _uniform(rows: list[dict], maximum: int) -> list[dict]:
    ordered = sorted(rows, key=lambda row: (row["decision_ms"], row["row_id"]))
    if len(ordered) <= maximum:
        return ordered
    indices = [index * (len(ordered) - 1) // (maximum - 1)
               for index in range(maximum)]
    return [ordered[index] for index in indices]


def _permitted(row: dict) -> dict:
    return {key: row[key] for key in ROW_FIELDS}


def _source_rows(sources: list[tuple[Path, dict]]) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    receipts: list[dict] = []
    seen_rows: set[str] = set()
    market_games: dict[str, str] = {}
    for path, value in sources:
        _validate_source(value)
        for row in value["rows"]:
            _validate_row(row)
            if row["row_id"] in seen_rows:
                raise ValueError("duplicate row across source materializations")
            seen_rows.add(row["row_id"])
            previous_game = market_games.setdefault(row["market_id"], row["game_id"])
            if previous_game != row["game_id"]:
                raise ValueError("market identity moved between games")
            rows.append(row)
        receipts.append({
            "path": str(Path(path).resolve()),
            "sha256": file_hash(path),
            "source_bundle_sha256": value["source_bundle_sha256"],
            "rows": len(value["rows"]),
        })
    if not rows:
        raise ValueError("nonempty source rows required")
    return sorted(rows, key=lambda row: (row["decision_ms"], row["row_id"])), receipts


def _select(schedule: dict, rows: list[dict]) -> dict:
    train_dates = set(schedule["train_utc_dates"])
    dev_dates = set(schedule["dev_utc_dates"])
    reserved = set(schedule["exclusions"]["reserved_game_ids"])
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["game_id"]].append(row)

    selected = {"train": [], "dev": []}
    games = {"train": [], "dev": []}
    omitted = defaultdict(int)
    for game_id, game_rows in sorted(
        grouped.items(),
        key=lambda item: (min(row["decision_ms"] for row in item[1]), item[0]),
    ):
        if game_id in reserved:
            omitted["reserved_games"] += 1
            continue
        row_dates = {_date(row["decision_ms"]) for row in game_rows}
        role = ("train" if row_dates <= train_dates else
                "dev" if row_dates <= dev_dates else None)
        if role is None:
            if row_dates & train_dates and row_dates & dev_dates:
                omitted["cross_boundary_games"] += 1
            else:
                omitted["outside_schedule_games"] += 1
            continue
        if len(game_rows) < MIN_ROWS_PER_GAME:
            omitted[f"short_{role}_games"] += 1
            continue
        sample = _uniform(game_rows, MAX_ROWS_PER_GAME)
        games[role].append(game_id)
        selected[role].extend(_permitted(row) for row in sample)

    for role in selected:
        selected[role].sort(key=lambda row: (row["decision_ms"], row["row_id"]))
    if not selected["train"] or not selected["dev"]:
        raise ValueError("target-blind schedule produced an empty Train or Dev")
    split_evidence_class = (
        "formal_prospective_learning"
        if schedule["evidence_class"] == "formal_learning"
        else "prospective_diagnostic"
    )
    train_cv_fit, train_cv_holdout, train_cv_audit = train_cv_split(
        selected["train"], evidence_class=split_evidence_class)
    outer_audit = validate_outer_dev(
        selected["train"], selected["dev"],
        evidence_class=split_evidence_class,
    )
    descriptors = [
        {key: row[key] for key in SELECTION_FIELDS}
        for row in rows
    ]
    return {
        "train": selected["train"],
        "dev": selected["dev"],
        "train_games": games["train"],
        "dev_games": games["dev"],
        "omitted": dict(sorted(omitted.items())),
        "target_blind_source_manifest_sha256": digest(descriptors),
        "train_membership_sha256": digest(
            [row["row_id"] for row in selected["train"]]
        ),
        "dev_membership_sha256": digest(
            [row["row_id"] for row in selected["dev"]]
        ),
        "train_cv_fit_rows": len(train_cv_fit),
        "train_cv_holdout_rows": len(train_cv_holdout),
        "train_cv_audit": train_cv_audit,
        "outer_dev_audit": outer_audit,
    }


def _artifact(path: Path, *, experiment_id: str, split: str,
              rows: list[dict]) -> dict:
    value = {
        "schema": "market_permitted_rows_v1",
        "experiment_id": experiment_id,
        "task_id": "prospective-time-series-round-01",
        "split": split,
        "feature_names": FEATURES,
        "rows": rows,
    }
    fresh_json(path, value)
    return {
        "path": str(path.resolve()),
        "sha256": file_hash(path),
        "bytes": path.stat().st_size,
        "rows": len(rows),
        "games": len({row["game_id"] for row in rows}),
        "utc_dates": sorted({_date(row["decision_ms"]) for row in rows}),
    }


def build(schedule_path: Path, sources: list[tuple[Path, dict]], output: Path) -> dict:
    schedule_path = Path(schedule_path).resolve()
    schedule = _validate_schedule(_json(schedule_path))
    rows, source_receipts = _source_rows(sources)
    selection = _select(schedule, rows)

    output = Path(output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    train = _artifact(
        output / "train.json", experiment_id=schedule["experiment_id"],
        split="train", rows=selection["train"],
    )
    dev = _artifact(
        output / "sealed-dev.json", experiment_id=schedule["experiment_id"],
        split="dev", rows=selection["dev"],
    )
    selection_receipt = {
        "schema": "market_target_blind_selection_receipt_v1",
        "schedule_sha256": file_hash(schedule_path),
        "policy_sha256": policy_contract()["policy_sha256"],
        "membership_fields": list(SELECTION_FIELDS),
        "target_fields_used": [],
        "candidate_scores_used": False,
        "target_blind_source_manifest_sha256": selection[
            "target_blind_source_manifest_sha256"
        ],
        "train_game_ids": selection["train_games"],
        "dev_game_ids": selection["dev_games"],
        "train_membership_sha256": selection["train_membership_sha256"],
        "dev_membership_sha256": selection["dev_membership_sha256"],
        "omitted": selection["omitted"],
        "train_cv_fit_rows": selection["train_cv_fit_rows"],
        "train_cv_holdout_rows": selection["train_cv_holdout_rows"],
        "train_cv_audit": selection["train_cv_audit"],
        "outer_dev_audit": selection["outer_dev_audit"],
    }
    fresh_json(output / "selection-receipt.json", selection_receipt)
    receipt = {
        "schema": SCHEMA,
        "experiment_id": schedule["experiment_id"],
        "evidence_class": schedule["evidence_class"],
        "builder_source_sha256": file_hash(__file__),
        "schedule_path": str(schedule_path),
        "schedule_sha256": file_hash(schedule_path),
        "objective": schedule["objective"],
        "source_materializations": source_receipts,
        "selection_receipt_sha256": file_hash(output / "selection-receipt.json"),
        "train": train,
        "sealed_dev": dev,
        "dev_opened": False,
        "future_test_used": False,
        "formal_lineage_ready": schedule["evidence_class"] == "formal_learning",
    }
    fresh_json(output / "receipt.json", receipt)
    return receipt


def validate_output(output: Path) -> dict:
    output = Path(output).resolve()
    receipt = _json(output / "receipt.json")
    if (receipt.get("schema") != SCHEMA
            or receipt.get("builder_source_sha256") != file_hash(__file__)
            or receipt.get("dev_opened") is not False
            or receipt.get("future_test_used") is not False
            or receipt.get("evidence_class") not in {"diagnostic", "formal_learning"}
            or receipt.get("formal_lineage_ready")
            is not (receipt.get("evidence_class") == "formal_learning")):
        raise ValueError("prospective materialization receipt changed")
    schedule_path = Path(receipt.get("schedule_path", "")).resolve()
    if file_hash(schedule_path) != receipt.get("schedule_sha256"):
        raise ValueError("selection schedule changed")
    schedule = _validate_schedule(_json(schedule_path))
    if receipt.get("objective") != schedule["objective"]:
        raise ValueError("materialization objective receipt changed")
    sources = []
    for source in receipt.get("source_materializations", []):
        if (not isinstance(source, dict) or set(source) != {
                "path", "sha256", "source_bundle_sha256", "rows"
        }):
            raise ValueError("source receipt changed")
        path = Path(source["path"])
        if file_hash(path) != source["sha256"]:
            raise ValueError("source materialization changed")
        value = _json(path)
        if (value.get("source_bundle_sha256") != source["source_bundle_sha256"]
                or len(value.get("rows", [])) != source["rows"]):
            raise ValueError("source materialization identity changed")
        sources.append((path, value))
    rows, rebuilt_source_receipts = _source_rows(sources)
    if rebuilt_source_receipts != receipt["source_materializations"]:
        raise ValueError("source materialization receipts changed")
    selection = _select(schedule, rows)
    selection_receipt = _json(output / "selection-receipt.json")
    if file_hash(output / "selection-receipt.json") != receipt.get(
            "selection_receipt_sha256"):
        raise ValueError("selection receipt hash changed")
    expected_selection = {
        "schema": "market_target_blind_selection_receipt_v1",
        "schedule_sha256": receipt["schedule_sha256"],
        "policy_sha256": policy_contract()["policy_sha256"],
        "membership_fields": list(SELECTION_FIELDS),
        "target_fields_used": [],
        "candidate_scores_used": False,
        "target_blind_source_manifest_sha256": selection[
            "target_blind_source_manifest_sha256"
        ],
        "train_game_ids": selection["train_games"],
        "dev_game_ids": selection["dev_games"],
        "train_membership_sha256": selection["train_membership_sha256"],
        "dev_membership_sha256": selection["dev_membership_sha256"],
        "omitted": selection["omitted"],
        "train_cv_fit_rows": selection["train_cv_fit_rows"],
        "train_cv_holdout_rows": selection["train_cv_holdout_rows"],
        "train_cv_audit": selection["train_cv_audit"],
        "outer_dev_audit": selection["outer_dev_audit"],
    }
    if selection_receipt != expected_selection:
        raise ValueError("target-blind selection receipt changed")
    for key, filename, split, expected_rows in (
        ("train", "train.json", "train", selection["train"]),
        ("sealed_dev", "sealed-dev.json", "dev", selection["dev"]),
    ):
        artifact_path = output / filename
        artifact = _json(artifact_path)
        item = receipt[key]
        if (file_hash(artifact_path) != item.get("sha256")
                or artifact.get("schema") != "market_permitted_rows_v1"
                or artifact.get("experiment_id") != schedule["experiment_id"]
                or artifact.get("split") != split
                or artifact.get("feature_names") != FEATURES
                or artifact.get("rows") != expected_rows
                or item.get("path") != str(artifact_path)
                or item.get("bytes") != artifact_path.stat().st_size
                or item.get("rows") != len(expected_rows)
                or item.get("games") != len({row["game_id"] for row in expected_rows})
                or item.get("utc_dates") != sorted(
                    {_date(row["decision_ms"]) for row in expected_rows}
                )):
            raise ValueError("materialized Train or Dev artifact changed")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze-schedule")
    freeze.add_argument("--output", required=True, type=Path)
    freeze.add_argument("--experiment-id", required=True)
    freeze.add_argument("--objective-contract", required=True, type=Path)
    freeze.add_argument("--train-date", action="append", required=True)
    freeze.add_argument("--dev-date", action="append", required=True)
    freeze.add_argument("--reserved-game-id", action="append", default=[])
    freeze.add_argument("--reservation-commitment-sha256", required=True)
    freeze.add_argument(
        "--evidence-class", required=True,
        choices=("diagnostic", "formal_learning"),
    )
    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("--schedule", required=True, type=Path)
    materialize.add_argument("--input", action="append", required=True, type=Path)
    materialize.add_argument("--output", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "freeze-schedule":
        value = freeze_schedule(
            args.output, experiment_id=args.experiment_id,
            objective_contract_path=args.objective_contract,
            train_utc_dates=args.train_date, dev_utc_dates=args.dev_date,
            reserved_game_ids=sorted(args.reserved_game_id),
            reservation_commitment_sha256=args.reservation_commitment_sha256,
            evidence_class=args.evidence_class,
        )
    elif args.command == "materialize":
        sources = [(path, _json(path)) for path in args.input]
        value = build(args.schedule, sources, args.output)
    else:
        value = validate_output(args.output)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
