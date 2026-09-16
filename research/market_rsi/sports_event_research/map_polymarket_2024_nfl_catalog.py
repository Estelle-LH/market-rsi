"""Map 2024 public NFL metadata to nflverse games without prices or outcomes.

The 2024 Polymarket event records lack gameId, and their team order can vary.
Only a unique same/adjacent-date nflverse game can establish slug orientation.
A mapped row is a Train candidate, not an admitted play/trade panel.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

from sports_event_research.build_game_master import read_nflverse
from sports_event_research.build_polymarket_game_mapping import canonical_team
from sports_event_research.fetch_polymarket_2024_nfl_catalog import (
    START_MAX, START_MIN, event_start,
)


GAME_SLUG = re.compile(r"^nfl-([a-z0-9]+)-([a-z0-9]+)-(202[45]-\d{2}-\d{2})$")
FIELDS = ("polymarket_event_id", "event_slug", "event_start_utc", "nflverse_game_id",
          "nflverse_game_date", "away_team", "home_team", "slug_order", "date_resolution",
          "moneyline_market_id", "condition_id", "outcomes_json", "tokens_json")
OLDER_TEAM_ALIASES = {"LAS": "LV", "WSH": "WAS"}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_list(value) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def map_events(events: list[dict], games: list[dict]) -> tuple[list[dict], list[dict]]:
    candidates = [game for game in games if game["season"] == 2024]
    index: dict[tuple[str, str, str], list[dict]] = {}
    for game in candidates:
        key = (game["game_date"], game["away_team"], game["home_team"])
        index.setdefault(key, []).append(game)
    mapped: list[dict] = []
    failures: list[dict] = []
    used_games: set[str] = set()
    for event in events:
        event_id = str(event.get("id") or "")
        slug = str(event.get("slug") or "")
        if not (START_MIN <= event_start(event) < START_MAX):
            raise ValueError("event outside frozen 2024-season window")
        match = GAME_SLUG.fullmatch(slug)
        if not match:
            failures.append({"event_id": event_id, "slug": slug, "reason": "slug_shape"})
            continue
        first, second = (OLDER_TEAM_ALIASES.get(team.upper(), canonical_team(team.upper()))
                         for team in match.group(1, 2))
        slug_date = date.fromisoformat(match.group(3))
        orders = (("away_home", first, second), ("home_away", second, first))
        resolved = []
        for offset in (0,):
            match_date = (slug_date + timedelta(days=offset)).isoformat()
            for slug_order, away, home in orders:
                for game in index.get((match_date, away, home), []):
                    resolved.append((game, slug_order, "exact"))
        if not resolved:
            for offset in (-1, 1):
                match_date = (slug_date + timedelta(days=offset)).isoformat()
                for slug_order, away, home in orders:
                    for game in index.get((match_date, away, home), []):
                        resolved.append((game, slug_order, "adjacent"))
        if len(resolved) != 1:
            failures.append({"event_id": event_id, "slug": slug,
                             "reason": "game_ambiguous_or_missing"})
            continue
        game, slug_order, date_resolution = resolved[0]
        away, home = game["away_team"], game["home_team"]
        if game["nflverse_game_id"] in used_games:
            failures.append({"event_id": event_id, "slug": slug,
                             "reason": "duplicate_event_for_game"})
            continue
        moneylines = []
        for market in event.get("markets") or []:
            outcomes = parse_list(market.get("outcomes"))
            tokens = parse_list(market.get("clobTokenIds"))
            if (market.get("sportsMarketType") == "moneyline" and len(outcomes) == 2
                    and len(tokens) == 2 and all(tokens) and market.get("conditionId")):
                moneylines.append((market, outcomes, tokens))
        if len(moneylines) != 1:
            failures.append({"event_id": event_id, "slug": slug,
                             "reason": "moneyline_missing_or_ambiguous"})
            continue
        market, outcomes, tokens = moneylines[0]
        used_games.add(game["nflverse_game_id"])
        mapped.append({
            "polymarket_event_id": event_id,
            "event_slug": slug,
            "event_start_utc": event_start(event),
            "nflverse_game_id": game["nflverse_game_id"],
            "nflverse_game_date": game["game_date"],
            "away_team": away,
            "home_team": home,
            "slug_order": slug_order,
            "date_resolution": date_resolution,
            "moneyline_market_id": str(market["id"]),
            "condition_id": str(market["conditionId"]),
            "outcomes_json": json.dumps(outcomes, separators=(",", ":")),
            "tokens_json": json.dumps(tokens, separators=(",", ":")),
        })
    mapped.sort(key=lambda row: (row["nflverse_game_date"], row["nflverse_game_id"]))
    return mapped, failures


def build(nflverse: Path, catalog: Path, output: Path) -> dict:
    nflverse, catalog = Path(nflverse).resolve(), Path(catalog).resolve()
    games, source_hashes = read_nflverse([nflverse])
    events = json.loads(catalog.read_text())
    if not isinstance(events, list) or not events:
        raise ValueError("empty event catalog")
    mapped, failures = map_events(events, games)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    mapping_path = output / "candidate_mapping.csv"
    with mapping_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(mapped)
    failure_path = output / "mapping_failures.json"
    failure_path.write_text(json.dumps(failures, indent=2, sort_keys=True) + "\n")
    counts: dict[str, int] = {}
    for failure in failures:
        counts[failure["reason"]] = counts.get(failure["reason"], 0) + 1
    manifest = {
        "schema": "polymarket_2024_nfl_train_candidate_mapping_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "nflverse_sha256": source_hashes[str(nflverse)],
        "catalog_sha256": sha(catalog),
        "catalog_events": len(events),
        "nflverse_2024_games": sum(game["season"] == 2024 for game in games),
        "mapped_unique_games": len(mapped),
        "unmapped_events": len(failures),
        "failure_reasons": counts,
        "adjacent_date_matches": sum(row["date_resolution"] == "adjacent" for row in mapped),
        "slug_order_counts": {
            order: sum(row["slug_order"] == order for row in mapped)
            for order in ("away_home", "home_away")
        },
        "mapping_sha256": sha(mapping_path),
        "failures_sha256": sha(failure_path),
        "outcome_orientation_verified": False,
        "trade_coverage_verified": False,
        "train_admitted": False,
        "protected_data_opened": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nflverse", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.nflverse, args.catalog, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
