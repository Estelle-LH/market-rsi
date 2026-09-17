"""Reconstruct only the historical 2025 role/date boundary from a hashed schedule.

No market prices, trades, score fields, outcomes, labels, or predictions are
accessed. Role assignment is not proof of which rows past actors actually saw.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from supervisor_harness.screen_2023_archive_catalog import SCHEDULE_SHA256, encoded, sha


def assign_roles(games: list[tuple[str, str]], dev_games: int, final_games: int) -> dict:
    if len(games) <= dev_games + final_games or len(set(games)) != len(games):
        raise ValueError("invalid split size or duplicate game/date pair")
    if len({game_id for _, game_id in games}) != len(games):
        raise ValueError("duplicate game ID")
    ordered = sorted(games)
    train_end = len(ordered) - dev_games - final_games
    dev_end = len(ordered) - final_games
    sections = {"market_train": ordered[:train_end],
                "route_dev": ordered[train_end:dev_end],
                "sealed_final": ordered[dev_end:]}
    dates = {name: {day for day, _ in rows} for name, rows in sections.items()}
    overlaps = {f"{a}__{b}": sorted(dates[a] & dates[b])
                for a, b in (("market_train", "route_dev"),
                             ("route_dev", "sealed_final"),
                             ("market_train", "sealed_final"))}
    return {"role_game_counts": {key: len(rows) for key, rows in sections.items()},
            "role_distinct_date_counts": {key: len(value) for key, value in dates.items()},
            "role_date_ranges": {key: [min(value), max(value)] for key, value in dates.items()},
            "cross_role_same_dates": overlaps}


def schedule_games(raw: bytes) -> list[tuple[str, str]]:
    if sha(raw) != SCHEDULE_SHA256:
        raise ValueError("nflverse schedule hash differs from prior source")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"game_id", "season", "gameday"}.issubset(reader.fieldnames or ()):
        raise ValueError("schedule identity fields missing")
    rows = [(row["gameday"], row["game_id"]) for row in reader if row["season"] == "2025"]
    if len(rows) != 285:
        raise ValueError("2025 schedule must contain exactly 285 games")
    return rows


def audit(schedule: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    raw = schedule.read_bytes()
    result = assign_roles(schedule_games(raw), dev_games=50, final_games=40)
    if result["role_game_counts"] != {"market_train": 195, "route_dev": 50,
                                       "sealed_final": 40}:
        raise ValueError("historical role counts differ")
    report = {"schema": "market_p0_2025_schedule_role_date_audit_v1",
              "source_schedule_sha256_verified": sha(raw),
              "split_rule": "date, game_id ascending; 195 Train, next 50 Dev, last 40 Final",
              **result,
              "opened_train_games_from_prior_documentation_not_reaudited": 163,
              "old_dev_scored_games_from_prior_documentation_not_reaudited": 50,
              "actual_access_history_complete": False,
              "untouched_final_admitted": False,
              "market_prices_outcomes_scores_labels_or_predictions_read": False,
              "provider_cost_usd": "0"}
    raw_report = encoded(report)
    output.mkdir(parents=True, exist_ok=False)
    (output / "date-audit.json").write_bytes(raw_report)
    return {**report, "report_sha256": hashlib.sha256(raw_report).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.schedule, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
