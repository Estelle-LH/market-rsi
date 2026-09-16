"""Freeze every mapped Route-Dev NFL moneyline before opening trade data.

Selection uses only the already-frozen whole-game split, event identity and
market schema.  It does not inspect prices, trades, play outcomes or labels.
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


def select(mapping_path: Path, catalog_path: Path) -> list[dict]:
    with Path(mapping_path).open(newline="") as stream:
        mapping = [row for row in csv.DictReader(stream) if row["split_role"] == "route_dev"]
    if len(mapping) != 50:
        raise ValueError("the preregistered Route-Dev cohort must contain exactly 50 games")
    events = {str(event["id"]): event for event in json.loads(Path(catalog_path).read_text())}
    chosen = []
    for game in sorted(mapping, key=lambda row: (row["scheduled_utc"], row["nflverse_game_id"])):
        event = events.get(str(game["polymarket_event_id"]))
        if event is None:
            raise ValueError("mapped Route-Dev event missing from frozen catalog")
        moneylines = []
        for market in event.get("markets") or []:
            outcomes = parse_list(market.get("outcomes")); tokens = parse_list(market.get("clobTokenIds"))
            if (market.get("sportsMarketType") == "moneyline" and market.get("conditionId")
                    and len(outcomes) == 2 and len(tokens) == 2 and all(tokens)):
                moneylines.append((market, outcomes, tokens))
        if len(moneylines) != 1:
            raise ValueError("each Route-Dev game requires exactly one usable moneyline")
        market, outcomes, tokens = moneylines[0]
        chosen.append({
            "schema": "polymarket_nfl_route_dev_selection_v1",
            "selection_rule": "all 50 chronologically frozen route_dev games; unique two-outcome moneyline; no price, trade, result, score, volume or model output consulted",
            "nflverse_game_id": game["nflverse_game_id"],
            "sportradar_game_id": game["sportradar_game_id"],
            "split_role": "route_dev",
            "scheduled_utc": game["scheduled_utc"],
            "home_team": game["home_team"], "away_team": game["away_team"],
            "event_id": event["id"], "game_id": event["gameId"],
            "event_slug": event.get("slug"), "event_title": event.get("title"),
            "event_start_utc": event.get("eventStartTime") or event.get("startTime"),
            "market_id": market["id"], "market_slug": market.get("slug"),
            "market_question": market.get("question"), "condition_id": market["conditionId"],
            "outcomes": outcomes, "clob_token_ids": tokens,
            "price_history_opened": False, "trades_opened": False,
            "labels_opened": False, "scientific_score": False,
        })
    return chosen


def build(mapping: Path, catalog: Path, output: Path) -> dict:
    mapping, catalog, output = map(lambda path: Path(path).resolve(), (mapping, catalog, output))
    selections = select(mapping, catalog)
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    for index, selection in enumerate(selections):
        path = output / f"{selection['nflverse_game_id']}.selection.json"
        path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")
        receipts.append({"index": index, "game_id": selection["nflverse_game_id"],
                         "scheduled_utc": selection["scheduled_utc"], "sha256": sha(path)})
    manifest = {
        "schema": "polymarket_nfl_route_dev_selection_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mapping_sha256": sha(mapping), "catalog_sha256": sha(catalog),
        "split_role": "route_dev", "selection_count": len(receipts),
        "selection_receipts": receipts,
        "selection_used_price_trade_result_score_volume_or_model_output": False,
        "trades_opened": False, "labels_opened": False, "scored": False,
        "sealed_final_opened": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.mapping, args.catalog, args.output), indent=2))


if __name__ == "__main__":
    main()
