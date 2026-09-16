"""Twelve-game, time-spread 2024 NFL trade availability screen; no model score.

The entire sample is frozen from mapping metadata before any trade request.
The previously opened earliest-game canary is excluded. Failure stops the
batch without retry and preserves completed receipts.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from sports_event_research.fetch_polymarket_2024_trade_canary import (
    fetch_selected, selection_from_row,
)


SAMPLE_SIZE = 12
SELECTION_RULE = (
    "exclude earliest opened canary; sort remaining mapped 2024 games by event start "
    "and event ID; take midpoint of each of 12 equal index bins before reading trades"
)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def choose_sample(mapping: Path) -> list[dict]:
    with Path(mapping).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: (row["event_start_utc"], row["polymarket_event_id"]))
    eligible = rows[1:]
    if len(eligible) < SAMPLE_SIZE:
        raise ValueError("fewer than 12 unopened mapped games")
    selected = [eligible[((2 * index + 1) * len(eligible)) // (2 * SAMPLE_SIZE)]
                for index in range(SAMPLE_SIZE)]
    if len({row["nflverse_game_id"] for row in selected}) != SAMPLE_SIZE:
        raise ValueError("duplicate selected game")
    return [selection_from_row(row, SELECTION_RULE) for row in selected]


def run(mapping: Path, output: Path, timeout: float = 30.0,
        request_pause_seconds: float = 0.5) -> dict:
    if request_pause_seconds < 0:
        raise ValueError("request pause cannot be negative")
    mapping = Path(mapping).resolve()
    selections = choose_sample(mapping)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    selection_path = output / "selection_manifest.json"
    write_json(selection_path, {
        "schema": "polymarket_2024_nfl_trade_screen_selection_v1",
        "created_utc": started,
        "mapping_sha256": sha(mapping),
        "selection_rule": SELECTION_RULE,
        "planned_games": SAMPLE_SIZE,
        "selections": selections,
        "trade_data_seen_before_selection": False,
        "scientific_score": False,
    })
    receipts: list[dict] = []
    for index, selection in enumerate(selections, start=1):
        game_id = selection["nflverse_game_id"]
        if index > 1:
            time.sleep(request_pause_seconds)
        try:
            result = fetch_selected(selection, mapping, output / game_id, timeout)
        except Exception as error:
            write_json(output / "failure.json", {
                "schema": "polymarket_2024_nfl_trade_screen_failure_v1",
                "failed_utc": datetime.now(timezone.utc).isoformat(),
                "completed_games": len(receipts),
                "failed_game": game_id,
                "error_type": type(error).__name__,
                "error": str(error),
                "automatic_retry": False,
                "scientific_score": False,
            })
            raise
        receipt = {"index": index, "game_id": game_id,
                   "manifest_sha256": sha(output / game_id / "manifest.json"),
                   "trades": result["frozen_window"]["trades"],
                   "distinct_prices": result["frozen_window"]["distinct_prices"]}
        receipts.append(receipt)
        write_json(output / "progress.json", {
            "schema": "polymarket_2024_nfl_trade_screen_progress_v1",
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "completed_games": len(receipts),
            "receipts": receipts,
            "scientific_score": False,
        })
    manifest = {
        "schema": "polymarket_2024_nfl_trade_screen_manifest_v1",
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "mapping_sha256": sha(mapping),
        "selection_manifest_sha256": sha(selection_path),
        "planned_games": SAMPLE_SIZE,
        "completed_games": len(receipts),
        "games_with_trades": sum(row["trades"] > 0 for row in receipts),
        "total_window_trades": sum(row["trades"] for row in receipts),
        "receipts": receipts,
        "automatic_retries": 0,
        "protected_data_opened": False,
        "train_admitted": False,
        "scientific_score": False,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    print(json.dumps(run(args.mapping, args.output, args.timeout), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
