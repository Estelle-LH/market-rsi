"""Map the frozen Polymarket NFL catalog to canonical whole-game rows."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re


SLUG = re.compile(r"^nfl-([a-z]+)-([a-z]+)-(\d{4}-\d{2}-\d{2})$")

# Provider vocabulary only.  These are explicit, audited aliases rather than
# fuzzy matching: Polymarket uses LA/JAX while nflverse uses LAR/JAC.
POLYMARKET_TO_NFLVERSE = {"LA": "LAR", "JAX": "JAC"}


def canonical_team(team: str) -> str:
    return POLYMARKET_TO_NFLVERSE.get(team, team)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def map_catalog(master_path: Path, catalog_path: Path) -> tuple[list[dict], list[dict]]:
    with Path(master_path).open(newline="") as stream:
        master = list(csv.DictReader(stream))
    index = {(row["game_date"], row["away_team"], row["home_team"]): row for row in master}
    events = json.loads(Path(catalog_path).read_text())
    mapped, failures = [], []
    for event in events:
        if not event.get("gameId"):
            continue
        match = SLUG.fullmatch(event.get("slug") or "")
        if not match:
            failures.append({"event_id": event.get("id"), "slug": event.get("slug"), "reason": "slug_shape"})
            continue
        raw_away, raw_home, game_date = match.group(1).upper(), match.group(2).upper(), match.group(3)
        away, home = canonical_team(raw_away), canonical_team(raw_home)
        game = index.get((game_date, away, home))
        date_resolution = "exact_slug_date"
        if game is None:
            # A small number of Polymarket slugs use the following UTC date for
            # Saturday games.  Resolve only an otherwise-exact team pair on an
            # adjacent date, and only when that candidate is unique.
            center = date.fromisoformat(game_date)
            candidates = [
                index[key]
                for key in (
                    ((center - timedelta(days=1)).isoformat(), away, home),
                    ((center + timedelta(days=1)).isoformat(), away, home),
                )
                if key in index
            ]
            if len(candidates) == 1:
                game = candidates[0]
                date_resolution = "exact_teams_adjacent_date"
        if game is None:
            failures.append({"event_id": event.get("id"), "slug": event.get("slug"), "reason": "canonical_game_missing"})
            continue
        markets = event.get("markets") or []
        mapped.append({
            "nflverse_game_id": game["nflverse_game_id"],
            "sportradar_game_id": game["sportradar_game_id"],
            "split_role": game["split_role"],
            "game_date": game_date,
            "scheduled_utc": game["scheduled_utc"],
            "away_team": away,
            "home_team": home,
            "polymarket_away_team": raw_away,
            "polymarket_home_team": raw_home,
            "date_resolution": date_resolution,
            "polymarket_event_id": event["id"],
            "polymarket_game_id": event["gameId"],
            "event_slug": event["slug"],
            "market_count": len(markets),
            "market_types": ";".join(sorted({market.get("sportsMarketType") or "unknown" for market in markets})),
            "event_volume": event.get("volume") or "",
        })
    if len(mapped) != len({row["polymarket_event_id"] for row in mapped}):
        raise ValueError("duplicate mapped event IDs")
    return sorted(mapped, key=lambda row: (row["game_date"], row["nflverse_game_id"])), failures


def build(master: Path, catalog: Path, output: Path) -> dict:
    master, catalog = Path(master).resolve(), Path(catalog).resolve()
    rows, failures = map_catalog(master, catalog)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    mapping = output / "polymarket_game_mapping.csv"
    with mapping.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    failure_path = output / "mapping_failures.json"
    failure_path.write_text(json.dumps(failures, indent=2, sort_keys=True) + "\n")
    splits, market_types = {}, {}
    for row in rows:
        splits[row["split_role"]] = splits.get(row["split_role"], 0) + 1
        for market_type in row["market_types"].split(";"):
            market_types[market_type] = market_types.get(market_type, 0) + 1
    result = {
        "schema": "polymarket_nfl_game_mapping_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "game_master_sha256": sha(master), "catalog_sha256": sha(catalog),
        "mapped_game_events": len(rows), "mapping_failures": len(failures),
        "split_coverage": splits, "events_by_market_type_presence": market_types,
        "mapping_sha256": sha(mapping), "failure_sha256": sha(failure_path),
        "sealed_final_price_or_outcome_opened": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-master", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.game_master, args.catalog, args.output), indent=2))


if __name__ == "__main__":
    main()
