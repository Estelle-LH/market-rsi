"""Fetch the public Polymarket 2025 NFL event/market catalog once.

This is metadata discovery, not price-history admission, L2 reconstruction or
an executable-PnL claim.  Raw targeted responses and request parameters are
preserved so a later runner can verify the catalog exactly.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GAMMA = "https://gamma-api.polymarket.com"
SERIES_SLUG = "nfl-2025"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def get(path: str, params: dict, timeout: float) -> tuple[bytes, str]:
    url = GAMMA + path + "?" + urlencode(params, doseq=True)
    request = Request(url, headers={"User-Agent": "market-rsi-research/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Polymarket returned HTTP {response.status}")
        return response.read(), url


def parse_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def market_rows(events: list[dict]) -> list[dict]:
    rows = []
    for event in events:
        for market in event.get("markets") or []:
            outcomes = parse_list(market.get("outcomes"))
            tokens = parse_list(market.get("clobTokenIds"))
            rows.append({
                "event_id": event.get("id") or "",
                "game_id": event.get("gameId") or "",
                "event_slug": event.get("slug") or "",
                "event_title": event.get("title") or "",
                "event_start_utc": event.get("eventStartTime") or event.get("startTime") or "",
                "event_end_utc": event.get("endDate") or "",
                "event_volume": event.get("volume") or "",
                "market_id": market.get("id") or "",
                "market_slug": market.get("slug") or "",
                "market_question": market.get("question") or "",
                "sports_market_type": market.get("sportsMarketType") or "",
                "condition_id": market.get("conditionId") or "",
                "outcomes_json": json.dumps(outcomes, separators=(",", ":")),
                "clob_token_ids_json": json.dumps(tokens, separators=(",", ":")),
                "closed": market.get("closed"),
                "accepting_orders": market.get("acceptingOrders"),
            })
    return rows


def choose_canary(events: list[dict]) -> dict:
    candidates = []
    for event in events:
        start = event.get("eventStartTime") or event.get("startTime") or ""
        for market in event.get("markets") or []:
            outcomes = parse_list(market.get("outcomes"))
            tokens = parse_list(market.get("clobTokenIds"))
            if (event.get("gameId") and start and market.get("sportsMarketType") == "moneyline"
                    and len(outcomes) == 2 and len(tokens) == 2 and all(tokens)):
                candidates.append((start, str(event.get("id")), str(market.get("id")), event, market,
                                   outcomes, tokens))
    if not candidates:
        raise ValueError("no two-outcome moneyline canary candidate")
    start, _, _, event, market, outcomes, tokens = sorted(candidates, key=lambda row: row[:3])[0]
    return {
        "schema": "polymarket_nfl_catalog_canary_selection_v1",
        "selection_rule": "earliest chronological closed nfl-2025 game with one two-outcome moneyline and two CLOB token IDs; no score or price history consulted",
        "event_id": event["id"],
        "game_id": event["gameId"],
        "event_slug": event.get("slug"),
        "event_title": event.get("title"),
        "event_start_utc": start,
        "market_id": market["id"],
        "market_slug": market.get("slug"),
        "market_question": market.get("question"),
        "condition_id": market.get("conditionId"),
        "outcomes": outcomes,
        "clob_token_ids": tokens,
        "price_history_opened": False,
        "scientific_score": False,
    }


def write_raw(path: Path, value: bytes) -> str:
    path.write_bytes(value)
    return digest_bytes(value)


def fetch(output: Path, timeout: float = 30.0) -> dict:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    series_raw, series_url = get("/series", {"slug": SERIES_SLUG, "limit": 10}, timeout)
    series_path = output / "series.raw.json"
    series_sha = write_raw(series_path, series_raw)
    series = json.loads(series_raw)
    exact = [row for row in series if row.get("slug") == SERIES_SLUG]
    if len(exact) != 1:
        raise ValueError("expected exactly one nfl-2025 series")
    series_id = exact[0]["id"]

    events, page_receipts, cursor, page = [], [], None, 0
    while True:
        params = {"series_id": series_id, "closed": "true", "limit": 100}
        if cursor:
            params["after_cursor"] = cursor
        raw, url = get("/events/keyset", params, timeout)
        path = output / f"events-page-{page:03d}.raw.json"
        page_receipts.append({"page": page, "url": url, "sha256": write_raw(path, raw), "bytes": len(raw)})
        payload = json.loads(raw)
        batch = payload.get("events")
        if not isinstance(batch, list):
            raise ValueError("keyset response lacks events")
        events.extend(batch)
        next_cursor = payload.get("next_cursor") or (payload.get("pagination") or {}).get("next_cursor")
        if not next_cursor or not batch:
            break
        if next_cursor == cursor:
            raise ValueError("Polymarket repeated keyset cursor")
        cursor, page = next_cursor, page + 1
        if page >= 20:
            raise ValueError("unexpectedly large nfl-2025 catalog")

    unique = {str(event.get("id")): event for event in events}
    if len(unique) != len(events):
        raise ValueError("duplicate event IDs across keyset pages")
    events = sorted(events, key=lambda row: ((row.get("eventStartTime") or row.get("startTime") or ""),
                                             str(row.get("id") or "")))
    if not events or any(row.get("seriesSlug") not in {None, SERIES_SLUG} for row in events):
        raise ValueError("series-filtered catalog is empty or contains another series")
    catalog_path = output / "events.catalog.json"
    catalog_path.write_text(json.dumps(events, indent=2, sort_keys=True) + "\n")
    rows = market_rows(events)
    if not rows:
        raise ValueError("catalog contains no markets")
    index_path = output / "event_market_index.csv"
    with index_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    canary = choose_canary(events)
    canary_path = output / "canary-selection.json"
    canary_path.write_text(json.dumps(canary, indent=2, sort_keys=True) + "\n")
    result = {
        "schema": "polymarket_nfl_2025_catalog_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_kind": "public_metadata_api",
        "research_access_basis": "Polymarket documentation and Institute describe public unauthenticated APIs for researchers; no trading or user data used",
        "series_request": {"url": series_url, "sha256": series_sha, "bytes": len(series_raw)},
        "series_id": series_id,
        "series_slug": SERIES_SLUG,
        "page_receipts": page_receipts,
        "events": len(events),
        "games_with_game_id": len({row.get("gameId") for row in events if row.get("gameId")}),
        "markets": len(rows),
        "catalog_sha256": digest_file(catalog_path),
        "index_sha256": digest_file(index_path),
        "canary_selection_sha256": digest_file(canary_path),
        "price_history_opened": False,
        "trades_opened": False,
        "historical_l2_claim": False,
        "scientific_claim": False,
    }
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    print(json.dumps(fetch(args.output, args.timeout), indent=2))


if __name__ == "__main__":
    main()
