"""Build a non-outcome NFL game master from immutable historical sources.

The output intentionally excludes scores and play contents.  It binds games,
providers, chronology and whole-game split roles without exposing Final labels
to a controller.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import gzip
import hashlib
import json
from pathlib import Path
from typing import Iterable


TEAM = {"JAX": "JAC", "LA": "LAR", "WSH": "WAS"}
TYPE = {"REG": "REG", "POST": "PST", "PST": "PST"}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def normalized_team(value: str) -> str:
    value = value.strip().upper()
    return TEAM.get(value, value)


def read_nflverse(paths: Iterable[Path]) -> tuple[list[dict], dict[str, str]]:
    games: dict[str, dict] = {}
    sources: dict[str, str] = {}
    required = {"game_id", "home_team", "away_team", "season_type", "week", "game_date"}
    for path in sorted(map(Path, paths)):
        sources[str(path.resolve())] = sha256(path)
        with gzip.open(path, "rt", newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError(f"missing nflverse fields in {path}")
            for row in reader:
                game_id = row["game_id"].strip()
                if not game_id:
                    raise ValueError(f"empty game_id in {path}")
                identity = {
                    "season": int(game_id[:4]),
                    "nflverse_game_id": game_id,
                    "game_date": row["game_date"],
                    "season_type": row["season_type"],
                    "week": int(float(row["week"])),
                    "home_team": normalized_team(row["home_team"]),
                    "away_team": normalized_team(row["away_team"]),
                }
                current = games.get(game_id)
                if current is None:
                    games[game_id] = {**identity, "nflverse_play_rows": 1}
                else:
                    if any(current[key] != value for key, value in identity.items()):
                        raise ValueError(f"inconsistent game identity for {game_id}")
                    current["nflverse_play_rows"] += 1
    result = sorted(games.values(), key=lambda row: (row["game_date"], row["nflverse_game_id"]))
    if len(result) != len({row["nflverse_game_id"] for row in result}):
        raise ValueError("duplicate nflverse games")
    return result, sources


def read_sportradar(root: Path) -> tuple[list[dict], dict[str, str]]:
    games, sources = [], {}
    for path in sorted(Path(root).glob("*/schedule.json.gz")):
        sources[str(path.resolve())] = sha256(path)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            schedule = json.load(stream)
        schedule_type = path.parent.name
        for week in schedule.get("weeks", []):
            for game in week.get("games", []):
                games.append({
                    "sportradar_game_id": game["id"],
                    "sportradar_sr_id": game.get("sr_id") or "",
                    "scheduled_utc": game["scheduled"],
                    "game_date_utc": game["scheduled"][:10],
                    "season_type": schedule_type,
                    "week": int(week["sequence"]),
                    "home_team": normalized_team(game["home"]["alias"]),
                    "away_team": normalized_team(game["away"]["alias"]),
                    "status": game.get("status") or "",
                })
    if len(games) != len({row["sportradar_game_id"] for row in games}):
        raise ValueError("duplicate Sportradar game IDs")
    return games, sources


def days_between(left: str, right: str) -> int:
    return abs((date.fromisoformat(left) - date.fromisoformat(right)).days)


def bind_sportradar(games: list[dict], sportradar: list[dict], season: int) -> dict:
    index: dict[tuple[str, str, str], list[dict]] = {}
    for row in sportradar:
        index.setdefault((row["home_team"], row["away_team"], row["season_type"]), []).append(row)
    matched, unmatched, used = 0, [], set()
    for game in games:
        game["sportradar_game_id"] = ""
        game["sportradar_sr_id"] = ""
        game["scheduled_utc"] = ""
        if game["season"] != season:
            continue
        key = (game["home_team"], game["away_team"], TYPE.get(game["season_type"], game["season_type"]))
        candidates = [row for row in index.get(key, []) if days_between(game["game_date"], row["game_date_utc"]) <= 1]
        candidates.sort(key=lambda row: (days_between(game["game_date"], row["game_date_utc"]), row["scheduled_utc"]))
        if len(candidates) != 1 or candidates[0]["sportradar_game_id"] in used:
            unmatched.append(game["nflverse_game_id"])
            continue
        row = candidates[0]
        used.add(row["sportradar_game_id"])
        game.update({key: row[key] for key in ("sportradar_game_id", "sportradar_sr_id", "scheduled_utc")})
        matched += 1
    target = sum(row["season"] == season for row in games)
    return {"season": season, "target_games": target, "matched_games": matched,
            "unmatched_games": unmatched, "match_rate": matched / target if target else 0.0}


def assign_splits(games: list[dict], season: int, dev_games: int, final_games: int) -> dict[str, int]:
    target = [row for row in games if row["season"] == season]
    if len(target) <= dev_games + final_games:
        raise ValueError("not enough games for positive Train plus requested Dev/Final")
    train_end = len(target) - dev_games - final_games
    dev_end = len(target) - final_games
    target_ids = {row["nflverse_game_id"]: index for index, row in enumerate(target)}
    counts: dict[str, int] = {}
    for row in games:
        if row["season"] < season:
            role = "state_history"
        elif row["season"] == season:
            index = target_ids[row["nflverse_game_id"]]
            role = "market_train" if index < train_end else "route_dev" if index < dev_end else "sealed_final"
        else:
            role = "future_unassigned"
        row["split_role"] = role
        counts[role] = counts.get(role, 0) + 1
    return counts


def write_json(path: Path, value: dict) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def build(nflverse_paths: Iterable[Path], sportradar_root: Path, output: Path,
          split_season: int = 2025, dev_games: int = 50, final_games: int = 40) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    games, nfl_sources = read_nflverse(nflverse_paths)
    sportradar, sr_sources = read_sportradar(sportradar_root)
    binding = bind_sportradar(games, sportradar, split_season)
    splits = assign_splits(games, split_season, dev_games, final_games)
    fields = ["season", "nflverse_game_id", "sportradar_game_id", "sportradar_sr_id",
              "game_date", "scheduled_utc", "season_type", "week", "home_team", "away_team",
              "nflverse_play_rows", "split_role"]
    master = output / "game_master.csv"
    with master.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in games)
    seasons: dict[str, dict] = {}
    for season in sorted({row["season"] for row in games}):
        rows = [row for row in games if row["season"] == season]
        seasons[str(season)] = {"games": len(rows), "play_rows": sum(row["nflverse_play_rows"] for row in rows)}
    result = {
        "schema": "nfl_game_master_manifest_v1",
        "generated_utc": datetime.now().astimezone().isoformat(),
        "outcomes_or_scores_in_master": False,
        "split_unit": "whole_game",
        "chronological_split": True,
        "split_season": split_season,
        "split_counts": splits,
        "season_counts": seasons,
        "sportradar_binding": binding,
        "source_sha256": {**nfl_sources, **sr_sources},
        "game_master_path": str(master),
        "game_master_sha256": sha256(master),
        "controller_may_read_sealed_final_rows": False,
        "scientific_claim": False,
    }
    write_json(output / "manifest.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nflverse", type=Path, nargs="+", required=True)
    parser.add_argument("--sportradar-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split-season", type=int, default=2025)
    parser.add_argument("--dev-games", type=int, default=50)
    parser.add_argument("--final-games", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps(build(args.nflverse, args.sportradar_root, args.output,
                           args.split_season, args.dev_games, args.final_games), indent=2))


if __name__ == "__main__":
    main()
