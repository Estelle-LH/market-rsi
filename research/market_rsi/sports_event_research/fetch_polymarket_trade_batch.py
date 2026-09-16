"""Fetch one frozen Train-only batch of public NFL trade tapes.

There is no automatic retry and no score.  Each completed game is journaled so
a failure leaves an auditable partial artifact rather than silently skipping a
hard market.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sports_event_research.fetch_polymarket_trade_canary import fetch


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(selection_dir: Path, game_master: Path, output: Path, timeout: float = 45.0) -> dict:
    selection_dir, game_master = Path(selection_dir).resolve(), Path(game_master).resolve()
    selection_paths = sorted(selection_dir.glob("*.selection.json"))
    if not selection_paths:
        raise ValueError("selection directory contains no selections")
    selections = [json.loads(path.read_text()) for path in selection_paths]
    if any(value.get("split_role") != "market_train" for value in selections):
        raise ValueError("batch contains a non-Train selection")
    if len({value.get("nflverse_game_id") for value in selections}) != len(selections):
        raise ValueError("duplicate canonical game in batch")
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    receipts = []
    started = datetime.now(timezone.utc).isoformat()
    for index, (path, selection) in enumerate(zip(selection_paths, selections), start=1):
        game_id = selection["nflverse_game_id"]
        try:
            result = fetch(path, game_master, output / game_id, timeout)
        except Exception as error:
            failure = {
                "schema": "polymarket_nfl_trade_batch_failure_v1",
                "failed_utc": datetime.now(timezone.utc).isoformat(),
                "started_utc": started,
                "completed_games": len(receipts),
                "failed_game": game_id,
                "selection_sha256": sha(path),
                "error_type": type(error).__name__,
                "error": str(error),
                "automatic_retry": False,
                "scientific_score": False,
            }
            write_json(output / "failure.json", failure)
            raise
        manifest = output / game_id / "manifest.json"
        receipts.append({
            "index": index,
            "game_id": game_id,
            "selection_sha256": sha(path),
            "manifest_sha256": sha(manifest),
            "trades": result["frozen_window"]["trades"],
            "possibly_truncated_at_20000": result["possibly_truncated_at_20000"],
        })
        write_json(output / "progress.json", {
            "schema": "polymarket_nfl_trade_batch_progress_v1",
            "started_utc": started,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "planned_games": len(selections),
            "completed_games": len(receipts),
            "last_game": game_id,
            "receipts": receipts,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "scientific_score": False,
        })
    result = {
        "schema": "polymarket_nfl_trade_batch_manifest_v1",
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "selection_manifest_sha256": sha(selection_dir / "manifest.json"),
        "game_master_sha256": sha(game_master),
        "planned_games": len(selections),
        "completed_games": len(receipts),
        "window_trades": sum(row["trades"] for row in receipts),
        "possibly_truncated_games": sum(row["possibly_truncated_at_20000"] for row in receipts),
        "receipts": receipts,
        "automatic_retries": 0,
        "split_role": "market_train",
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "scientific_score": False,
    }
    write_json(output / "manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-dir", type=Path, required=True)
    parser.add_argument("--game-master", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    print(json.dumps(run(args.selection_dir, args.game_master, args.output, args.timeout), indent=2))


if __name__ == "__main__":
    main()
