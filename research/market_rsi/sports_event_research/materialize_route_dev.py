"""Materialize the frozen 50-game Route-Dev cohort without scoring it.

The cohort and reward must already be frozen.  This runner fetches every trade
tape, binds the corresponding play-by-play file, and writes aligned panels.
It does not summarize labels, fit a model, calculate MSE, or exclude a game.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from sports_event_research.build_play_trade_canary import align, home_trade_series, plays, sha
from sports_event_research.fetch_polymarket_trade_canary import fetch


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def load_frozen_selections(selection_dir: Path) -> list[tuple[Path, dict]]:
    selection_dir = Path(selection_dir).resolve()
    manifest = json.loads((selection_dir / "manifest.json").read_text())
    paths = sorted(selection_dir.glob("*.selection.json"))
    selections = [(path, json.loads(path.read_text())) for path in paths]
    if (manifest.get("schema") != "polymarket_nfl_route_dev_selection_manifest_v1"
            or manifest.get("selection_count") != 50 or len(selections) != 50
            or any(value.get("split_role") != "route_dev" for _, value in selections)
            or len({value.get("nflverse_game_id") for _, value in selections}) != 50
            or manifest.get("trades_opened") is not False
            or manifest.get("labels_opened") is not False
            or manifest.get("scored") is not False):
        raise ValueError("exact unopened 50-game Route-Dev selection required")
    expected = {row["game_id"]: row["sha256"] for row in manifest["selection_receipts"]}
    observed = {value["nflverse_game_id"]: sha(path) for path, value in selections}
    if observed != expected:
        raise ValueError("Route-Dev selection files changed after cohort freeze")
    return selections


def find_pbp(root: Path, sportradar_game_id: str) -> Path:
    matches = sorted(Path(root).resolve().glob(f"*/pbp/{sportradar_game_id}.json.gz"))
    if len(matches) != 1:
        raise ValueError("exactly one frozen play-by-play object required per Route-Dev game")
    return matches[0]


def run(selection_dir: Path, game_master: Path, pbp_root: Path, output: Path,
        timeout: float = 45.0) -> dict:
    selection_dir, game_master, pbp_root = map(lambda path: Path(path).resolve(),
                                               (selection_dir, game_master, pbp_root))
    selections = load_frozen_selections(selection_dir)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    started = {
        "schema": "route_dev_materialization_start_v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "selection_manifest_sha256": sha(selection_dir / "manifest.json"),
        "selection_count": len(selections),
        "scored": False, "labels_summarized": False, "automatic_retries": 0,
    }
    write_json(output / "start.json", started)
    receipts = []
    for index, (selection_path, selection) in enumerate(selections, start=1):
        game = selection["nflverse_game_id"]
        game_root = output / game; trade_root = game_root / "trades"
        try:
            trade = fetch(selection_path, game_master, trade_root, timeout,
                          expected_split_role="route_dev")
            if trade["possibly_truncated_at_20000"]:
                raise ValueError("trade tape reached the frozen 20,000-row bound")
            pbp = find_pbp(pbp_root, selection["sportradar_game_id"])
            play_rows = plays(pbp)
            times, prices = home_trade_series(trade_root / "trade_window.csv", selection)
            rows = align(play_rows, times, prices)
            if not rows:
                raise ValueError("Route-Dev game produced no aligned play rows")
            panel = game_root / "play_trade_alignment.csv"
            with panel.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
            game_manifest = {
                "schema": "route_dev_materialized_game_v1",
                "game_id": game, "selection_sha256": sha(selection_path),
                "pbp_sha256": sha(pbp), "trade_manifest_sha256": sha(trade_root / "manifest.json"),
                "panel_sha256": sha(panel), "play_rows": len(rows),
                "labels_summarized": False, "scored": False,
            }
            write_json(game_root / "materialization.json", game_manifest)
            receipts.append({"index": index, "game_id": game,
                "materialization_sha256": sha(game_root / "materialization.json"),
                "panel_sha256": sha(panel), "play_rows": len(rows)})
            write_json(output / "progress.json", {
                "schema": "route_dev_materialization_progress_v1",
                "selection_count": 50, "materialized_count": len(receipts),
                "receipts": receipts, "labels_summarized": False, "scored": False,
            })
        except Exception as error:
            write_json(output / "failure.json", {
                "schema": "route_dev_materialization_failure_v1",
                "failed_utc": datetime.now(timezone.utc).isoformat(),
                "failed_game": game, "materialized_count": len(receipts),
                "error_type": type(error).__name__, "error": str(error),
                "automatic_retry": False, "labels_summarized": False, "scored": False,
            })
            raise
    result = {
        "schema": "route_dev_materialization_manifest_v1",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "eligible_data_sha256": sha(selection_dir / "manifest.json"),
        "selection_count": 50, "materialized_count": len(receipts), "excluded_count": 0,
        "receipts": receipts, "source_manifest_sha256": sha(game_master),
        "labels_summarized": False, "scored": False, "automatic_retries": 0,
        "route_dev_opened": True, "sealed_final_opened": False,
    }
    write_json(output / "manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-dir", type=Path, required=True)
    parser.add_argument("--game-master", type=Path, required=True)
    parser.add_argument("--pbp-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    result = run(args.selection_dir, args.game_master, args.pbp_root, args.output, args.timeout)
    print(json.dumps({key: result[key] for key in (
        "selection_count", "materialized_count", "excluded_count", "labels_summarized", "scored"
    )}, indent=2))


if __name__ == "__main__":
    main()
