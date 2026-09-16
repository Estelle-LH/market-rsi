"""Freeze a chronological, Train-only NFL moneyline trade-tape pilot.

Selection uses game time and frozen split membership only.  It never reads
prices, trades, outcomes, scores, or event volume, so coverage decisions cannot
be conditioned on a favorable market response.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sports_event_research.fetch_polymarket_catalog import parse_list


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def even_indices(population: int, requested: int) -> list[int]:
    if population <= 0 or requested <= 0 or requested > population:
        raise ValueError("requested games must be between 1 and the Train population")
    if requested == 1:
        return [0]
    indices = [round(index * (population - 1) / (requested - 1)) for index in range(requested)]
    if len(set(indices)) != requested:
        raise ValueError("chronological stratification produced duplicate indices")
    return indices


def select(mapping_path: Path, catalog_path: Path, requested: int) -> list[dict]:
    with Path(mapping_path).open(newline="") as stream:
        mapping = [row for row in csv.DictReader(stream) if row["split_role"] == "market_train"]
    events = {str(event["id"]): event for event in json.loads(Path(catalog_path).read_text())}
    candidates = []
    for game in mapping:
        event = events.get(str(game["polymarket_event_id"]))
        if event is None:
            raise ValueError(f"mapped event missing from catalog: {game['polymarket_event_id']}")
        moneylines = []
        for market in event.get("markets") or []:
            outcomes = parse_list(market.get("outcomes"))
            tokens = parse_list(market.get("clobTokenIds"))
            if (market.get("sportsMarketType") == "moneyline" and market.get("conditionId")
                    and len(outcomes) == 2 and len(tokens) == 2 and all(tokens)):
                moneylines.append((str(market.get("id")), market, outcomes, tokens))
        if len(moneylines) != 1:
            raise ValueError(f"expected one usable moneyline for event {event['id']}, got {len(moneylines)}")
        _, market, outcomes, tokens = moneylines[0]
        candidates.append((game["scheduled_utc"], game["nflverse_game_id"], game, event,
                           market, outcomes, tokens))
    candidates.sort(key=lambda row: row[:2])
    chosen = []
    for position in even_indices(len(candidates), requested):
        _, _, game, event, market, outcomes, tokens = candidates[position]
        chosen.append({
            "schema": "polymarket_nfl_trade_pilot_selection_v1",
            "selection_rule": (
                f"{requested} evenly spaced chronological market_train games from the frozen mapping; "
                "one unique two-outcome moneyline per game; no price, trade, result, score, or volume consulted"
            ),
            "selection_position": position,
            "train_population": len(candidates),
            "nflverse_game_id": game["nflverse_game_id"],
            "sportradar_game_id": game["sportradar_game_id"],
            "split_role": game["split_role"],
            "scheduled_utc": game["scheduled_utc"],
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "event_id": event["id"],
            "game_id": event["gameId"],
            "event_slug": event.get("slug"),
            "event_title": event.get("title"),
            "event_start_utc": event.get("eventStartTime") or event.get("startTime"),
            "market_id": market["id"],
            "market_slug": market.get("slug"),
            "market_question": market.get("question"),
            "condition_id": market["conditionId"],
            "outcomes": outcomes,
            "clob_token_ids": tokens,
            "price_history_opened": False,
            "trades_opened": False,
            "scientific_score": False,
        })
    return chosen


def build(mapping: Path, catalog: Path, output: Path, requested: int) -> dict:
    mapping, catalog, output = Path(mapping).resolve(), Path(catalog).resolve(), Path(output).resolve()
    selections = select(mapping, catalog, requested)
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    for selection in selections:
        path = output / f"{selection['nflverse_game_id']}.selection.json"
        path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")
        receipts.append({"game_id": selection["nflverse_game_id"], "path": path.name,
                         "sha256": sha(path), "scheduled_utc": selection["scheduled_utc"]})
    result = {
        "schema": "polymarket_nfl_trade_pilot_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mapping_sha256": sha(mapping),
        "catalog_sha256": sha(catalog),
        "requested_games": requested,
        "selected_games": len(receipts),
        "split_role": "market_train",
        "selection_receipts": receipts,
        "selection_used_price_trade_result_score_or_volume": False,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "trades_opened": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--games", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(build(args.mapping, args.catalog, args.output, args.games), indent=2))


if __name__ == "__main__":
    main()
