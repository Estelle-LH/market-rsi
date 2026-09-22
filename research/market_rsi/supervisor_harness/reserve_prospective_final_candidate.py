"""Commit a schedule-only future-date candidate; never read market outcomes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def run(source: Path, output: Path, *, after_date: str = "2026-09-18") -> dict:
    if output.exists():
        raise FileExistsError("fresh candidate output required")
    if source.is_symlink() or not source.is_file():
        raise ValueError("regular pinned schedule source required")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"game_id", "season", "game_type", "gameday"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("schedule fields missing")
        games = [{"game_id": row["game_id"], "game_date": row["gameday"]}
                 for row in reader if row["season"] == "2026"
                 and row["game_type"] == "REG" and row["gameday"] > after_date]
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError("schedule changed during selection")
    dates = sorted({game["game_date"] for game in games})[:20]
    selected = sorted((game for game in games if game["game_date"] in dates),
                      key=lambda game: (game["game_date"], game["game_id"]))
    if len(dates) != 20 or len({g["game_id"] for g in selected}) != len(selected):
        raise ValueError("exactly 20 distinct future dates and unique games required")
    result = {"schema": "market_p0_schedule_only_final_candidate_v1",
              "selection_rule": "first 20 distinct 2026 REG game dates strictly after 2026-09-18; all scheduled games on them",
              "source_path": str(source.resolve()), "source_sha256": before,
              "dates": dates, "games": selected, "date_count": len(dates),
              "game_count": len(selected), "scope": "candidate reservation only",
              "formal_final_admitted": False, "market_rights_verified": False,
              "same_mechanism_market_coverage_verified": False,
              "access_history_complete": False, "labels_read": False,
              "provider_cost_usd": "0"}
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return {"date_count": len(dates), "game_count": len(selected),
            "first_date": dates[0], "last_date": dates[-1],
            "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source.resolve(), args.output.resolve()), sort_keys=True))
