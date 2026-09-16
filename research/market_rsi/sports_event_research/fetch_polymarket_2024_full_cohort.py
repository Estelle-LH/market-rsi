"""Freeze all mapped 2024 NFL Train candidates, then fetch fixed-size trade batches.

No volume, price, score, model outcome, Dev or Final input selects a game. A
failed batch stays partial and is never silently skipped or automatically retried.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

from data_scientist_harness import VERSION
from data_scientist_harness.release import source_hashes, verify_git_publication
from market_rsi import digest
from sports_event_research.fetch_polymarket_2024_trade_canary import (
    fetch_selected, selection_from_row,
)
EXPECTED_MAPPING = "a8621f15ed703f01add64aaf4869b2ef262b4762d7bd241ba3168d040942008b"
EXPECTED_MAPPING_MANIFEST = "adc6f4244d5e3709d462ea210b19fc22d1bd4ba7a28aee579bcc741ce6a1c61a"
EXPECTED_V15_COHORT_PLAN = "e06e112f057d5b1f1749f668c2a9f2ceabcee662464da521335e1b8aba1987c2"
EXPECTED_GAMES = 284
BATCH_SIZE = 24
SELECTION_RULE = "all uniquely mapped 2024 NFL moneyline games in event-start/event-ID order; no price, volume or outcome filtering"


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


def frozen_selections(mapping: Path) -> list[dict]:
    mapping = Path(mapping).resolve()
    if sha256(mapping) != EXPECTED_MAPPING or sha256(mapping.parent / "manifest.json") != EXPECTED_MAPPING_MANIFEST:
        raise ValueError("frozen 2024 mapping changed")
    manifest = json.loads((mapping.parent / "manifest.json").read_text())
    if (manifest.get("mapped_unique_games") != EXPECTED_GAMES
            or manifest.get("mapping_sha256") != EXPECTED_MAPPING
            or manifest.get("train_admitted") is not False
            or manifest.get("protected_data_opened") is not False):
        raise ValueError("2024 mapping is not the frozen Train-source candidate set")
    with mapping.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: (row["event_start_utc"], row["polymarket_event_id"]))
    if (len(rows) != EXPECTED_GAMES
            or len({row["nflverse_game_id"] for row in rows}) != EXPECTED_GAMES
            or len({row["condition_id"] for row in rows}) != EXPECTED_GAMES):
        raise ValueError("mapped games or markets are missing or duplicate")
    return [selection_from_row(row, SELECTION_RULE) for row in rows]


def verify_release(receipt: Path) -> dict:
    receipt = Path(receipt).resolve()
    value = json.loads(receipt.read_text())
    publication = value.get("publication") or {}
    sources = source_hashes()
    if (value.get("schema") != "data_scientist_release_v1"
            or value.get("harness_version") != VERSION
            or value.get("release_sha256") != digest({k: v for k, v in value.items() if k != "release_sha256"})
            or value.get("source_hashes") != sources
            or publication.get("tag") != "dsh-v1.6.16"):
        raise ValueError("exact v1.6.16 release receipt required")
    proof = verify_git_publication(sources, commit=publication.get("commit"))
    if any(proof[key] != publication[key] for key in ("tag", "commit", "tag_object", "tree")):
        raise ValueError("release publication proof changed")
    return {"path": str(receipt), "file_sha256": sha256(receipt),
            "release_sha256": value["release_sha256"],
            "commit": publication["commit"], "tag": publication["tag"]}


def batch_slice(selections: list[dict], index: int) -> list[dict]:
    if index < 0 or index * BATCH_SIZE >= len(selections):
        raise ValueError("batch index outside frozen cohort")
    return selections[index * BATCH_SIZE:(index + 1) * BATCH_SIZE]


def freeze(mapping: Path, release: Path, output: Path) -> dict:
    selections = frozen_selections(mapping)
    proof = verify_release(release)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("cohort plan exists; never rewrite it")
    value = {"schema": "polymarket_2024_full_train_source_plan_v1",
             "generated_utc": datetime.now(timezone.utc).isoformat(),
             "mapping_sha256": EXPECTED_MAPPING,
             "mapping_manifest_sha256": EXPECTED_MAPPING_MANIFEST,
             "release": proof,
             "selection_rule": SELECTION_RULE,
             "planned_games": EXPECTED_GAMES, "batch_size": BATCH_SIZE,
             "batch_count": (EXPECTED_GAMES + BATCH_SIZE - 1) // BATCH_SIZE,
             "selections": selections,
             "train_admitted": False, "route_dev_opened": False,
             "sealed_final_opened": False, "scientific_score": False,
             "provider_cost_usd": "0"}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "cohort_plan.json", value)
    write_json(output / "manifest.json", {
        "schema": "polymarket_2024_full_train_source_plan_manifest_v1",
        "cohort_plan_sha256": sha256(output / "cohort_plan.json"),
        "planned_games": EXPECTED_GAMES, "batch_count": value["batch_count"],
        "trade_data_opened": False, "train_admitted": False,
        "route_dev_opened": False, "sealed_final_opened": False,
        "provider_cost_usd": "0", "scientific_score": False})
    return value


def fetch_batch(mapping: Path, plan_path: Path, release: Path, index: int,
                output: Path, timeout: float = 30.0,
                pause_seconds: float = 0.5) -> dict:
    if pause_seconds < 0 or timeout <= 0:
        raise ValueError("invalid request timing")
    selections = frozen_selections(mapping)
    proof = verify_release(release)
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text())
    # Preserve the sole pre-fetch v1.6.15 plan after a startup-only v1.6.16
    # repair. The exact plan hash binds its earlier release and all 284 choices.
    plan_release_valid = (plan.get("release") == proof
                          or sha256(plan_path) == EXPECTED_V15_COHORT_PLAN)
    if (plan.get("schema") != "polymarket_2024_full_train_source_plan_v1"
            or plan.get("mapping_sha256") != EXPECTED_MAPPING
            or plan.get("planned_games") != EXPECTED_GAMES
            or plan.get("batch_size") != BATCH_SIZE
            or plan.get("batch_count") != (EXPECTED_GAMES + BATCH_SIZE - 1) // BATCH_SIZE
            or plan.get("selections") != selections
            or not plan_release_valid
            or plan.get("train_admitted") is not False
            or plan.get("route_dev_opened") is not False
            or plan.get("sealed_final_opened") is not False):
        raise ValueError("batch does not match the immutable full-cohort plan")
    selected = batch_slice(selections, index)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("batch output exists; never reuse an attempt ID")
    free = shutil.disk_usage(output.parent).free
    if free < 5 * 1024**3:
        raise RuntimeError("less than 5 GiB local free; no new data fetch")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "pre_fetch_lock.json", {
        "schema": "polymarket_2024_full_train_source_batch_lock_v1",
        "cohort_plan_sha256": sha256(plan_path), "release": proof,
        "batch_index": index, "planned_games": [row["nflverse_game_id"] for row in selected],
        "selection_rule": SELECTION_RULE,
        "route_dev_opened": False, "sealed_final_opened": False,
        "train_admitted": False, "scientific_score": False,
        "provider_cost_usd": "0"})
    receipts = []
    for ordinal, selection in enumerate(selected, start=1):
        game = selection["nflverse_game_id"]
        if ordinal > 1:
            time.sleep(pause_seconds)
        try:
            result = fetch_selected(selection, mapping, output / game, timeout)
            receipt = {"ordinal": ordinal, "game_id": game,
                       "manifest_sha256": sha256(output / game / "manifest.json"),
                       "trade_rows": result["frozen_window"]["trades"]}
            receipts.append(receipt)
            write_json(output / "progress.json", {
                "schema": "polymarket_2024_full_train_source_batch_progress_v1",
                "batch_index": index, "completed_games": len(receipts),
                "planned_games": len(selected), "receipts": receipts,
                "route_dev_opened": False, "sealed_final_opened": False,
                "provider_cost_usd": "0", "scientific_score": False})
        except Exception as error:
            write_json(output / "failure.json", {
                "schema": "polymarket_2024_full_train_source_batch_failure_v1",
                "batch_index": index, "completed_games": len(receipts),
                "failed_game": game, "error_type": type(error).__name__,
                "error": str(error)[:1200], "automatic_retry": False,
                "route_dev_opened": False, "sealed_final_opened": False,
                "provider_cost_usd": "0", "scientific_score": False})
            raise
    manifest = {"schema": "polymarket_2024_full_train_source_batch_manifest_v1",
                "complete": True, "batch_index": index,
                "pre_fetch_lock_sha256": sha256(output / "pre_fetch_lock.json"),
                "cohort_plan_sha256": sha256(plan_path),
                "planned_games": len(selected), "completed_games": len(receipts),
                "games_with_trades": sum(row["trade_rows"] > 0 for row in receipts),
                "trade_rows": sum(row["trade_rows"] for row in receipts),
                "receipts": receipts, "automatic_retries": 0,
                "train_admitted": False, "route_dev_opened": False,
                "sealed_final_opened": False, "provider_cost_usd": "0",
                "scientific_score": False}
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--batch-index", type=int)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if (args.plan is None) != (args.batch_index is None):
        parser.error("--plan and --batch-index must be given together")
    result = (freeze(args.mapping, args.release, args.output) if args.plan is None else
              fetch_batch(args.mapping, args.plan, args.release, args.batch_index,
                          args.output, args.timeout))
    print(json.dumps({"schema": result["schema"],
                      "planned_games": result["planned_games"],
                      "completed_games": result.get("completed_games", 0),
                      "provider_cost_usd": "0", "scientific_score": False}, indent=2))


if __name__ == "__main__":
    main()
