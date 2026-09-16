"""Audit historical 2024 NFL play/trade timing support on the frozen 12 games.

`time_of_day` is a historical play clock, not provider publish or local receive
time. This reports potential 30/60/300-second label availability only, not a
model score, live lead, or executable result.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


HORIZONS = (30, 60, 300)
MAX_PRE_AGE = 300


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("play timestamp has no timezone")
    return int(parsed.timestamp())


def support(trade_times: list[int], play_time: int) -> dict[int, bool]:
    if not trade_times:
        return {horizon: False for horizon in HORIZONS}
    prior_index = bisect_right(trade_times, play_time) - 1
    if prior_index < 0 or play_time - trade_times[prior_index] > MAX_PRE_AGE:
        return {horizon: False for horizon in HORIZONS}
    future_index = bisect_right(trade_times, play_time)
    return {horizon: future_index < len(trade_times)
            and trade_times[future_index] <= play_time + horizon for horizon in HORIZONS}


def audit(nflverse: Path, screen: Path, output: Path) -> dict:
    nflverse, screen = Path(nflverse).resolve(), Path(screen).resolve()
    selection_path = screen / "selection_manifest.json"
    screen_manifest_path = screen / "manifest.json"
    selections = json.loads(selection_path.read_text())["selections"]
    screen_manifest = json.loads(screen_manifest_path.read_text())
    if (len(selections) != 12 or screen_manifest.get("completed_games") != 12
            or screen_manifest.get("selection_manifest_sha256") != sha(selection_path)):
        raise ValueError("12-game screen or frozen selection is incomplete")
    selected = {row["nflverse_game_id"] for row in selections}
    if len(selected) != 12:
        raise ValueError("duplicate selected games")
    receipts = screen_manifest.get("receipts") or []
    receipt_by_game = {row["game_id"]: row for row in receipts}
    if len(receipts) != 12 or set(receipt_by_game) != selected:
        raise ValueError("screen receipts do not match frozen games")
    by_game: dict[str, dict] = {game_id: {"pbp_rows": 0, "typed_play_rows": 0,
                                        "timed_typed_play_rows": 0, "times": [],
                                        "play_ids": set()}
                                for game_id in selected}
    with gzip.open(nflverse, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"game_id", "play_id", "play_type", "time_of_day"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("nflverse file lacks play time fields")
        for row in reader:
            game_id = row["game_id"]
            if game_id not in by_game:
                continue
            state = by_game[game_id]
            state["pbp_rows"] += 1
            if not row["play_type"]:
                continue
            state["typed_play_rows"] += 1
            play_id = row["play_id"]
            if not play_id or play_id in state["play_ids"]:
                raise ValueError("missing or repeated typed play ID")
            state["play_ids"].add(play_id)
            if row["time_of_day"]:
                state["times"].append(timestamp(row["time_of_day"]))
                state["timed_typed_play_rows"] += 1

    rows = []
    for game_id in sorted(selected):
        state = by_game[game_id]
        if not state["typed_play_rows"]:
            raise ValueError(f"selected game has no typed plays: {game_id}")
        game_dir = screen / game_id
        trade_manifest_path = game_dir / "manifest.json"
        if sha(trade_manifest_path) != receipt_by_game[game_id]["manifest_sha256"]:
            raise ValueError("trade receipt hash changed")
        trade_manifest = json.loads(trade_manifest_path.read_text())
        selection = json.loads((game_dir / "selection.json").read_text())
        if selection["nflverse_game_id"] != game_id:
            raise ValueError("trade directory game mismatch")
        scheduled = timestamp(selection["event_start_utc"])
        trade_path = game_dir / "trade_window.csv"
        if sha(trade_path) != trade_manifest["safe_trade_window_sha256"]:
            raise ValueError("safe trade window hash changed")
        trade_times = []
        with trade_path.open(newline="") as handle:
            for trade in csv.DictReader(handle):
                if trade["asset"] not in selection["clob_token_ids"]:
                    raise ValueError("trade token is not part of selected moneyline")
                trade_times.append(int(trade["timestamp"]))
        trade_times.sort()
        counts = {horizon: 0 for horizon in HORIZONS}
        for play_time in state["times"]:
            for horizon, available in support(trade_times, play_time).items():
                counts[horizon] += available
        rows.append({
            "game_id": game_id,
            "pbp_rows": state["pbp_rows"],
            "typed_play_rows": state["typed_play_rows"],
            "timed_typed_play_rows": state["timed_typed_play_rows"],
            "first_play_minus_scheduled_seconds": (
                min(state["times"]) - scheduled if state["times"] else None),
            "last_play_minus_scheduled_seconds": (
                max(state["times"]) - scheduled if state["times"] else None),
            "trade_rows": len(trade_times),
            "covered_30s": counts[30],
            "covered_60s": counts[60],
            "covered_300s": counts[300],
            "trade_window_sha256": sha(trade_path),
        })
    totals = {key: sum(row[key] for row in rows) for key in (
        "pbp_rows", "typed_play_rows", "timed_typed_play_rows", "trade_rows",
        "covered_30s", "covered_60s", "covered_300s")}
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    per_game_path = output / "per_game.json"
    per_game_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema": "nfl_2024_pbp_trade_timing_support_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "nflverse_sha256": sha(nflverse),
        "screen_manifest_sha256": sha(screen_manifest_path),
        "selection_manifest_sha256": sha(selection_path),
        "per_game_sha256": sha(per_game_path),
        "games": len(rows),
        "totals": totals,
        "coverage_denominator": "typed nflverse plays with parseable time_of_day",
        "historical_event_clock_only": True,
        "provider_publish_or_local_receive_proven": False,
        "outcome_orientation_verified": False,
        "train_admitted": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nflverse", type=Path, required=True)
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.nflverse, args.screen, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
