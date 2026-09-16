"""Inventory public NFL event metadata by season; never admit it for training.

This is a P0 source-discovery screen. It does not fetch trades, outcomes,
quotes, scores, or protected evaluation data. Every API page is preserved so
that a later reviewer can reproduce counts and inspect classification errors.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://gamma-api.polymarket.com"
GAME_SLUG = re.compile(r"^nfl-[a-z0-9]+-[a-z0-9]+-(20\d\d-\d\d-\d\d)$")
SEASONS = (2021, 2022, 2023, 2024, 2025)
SERIES_SLUGS = {2021: "nfl", 2022: "nfl", 2023: "nfl", 2024: "nfl",
                2025: "nfl-2025"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get(path: str, params: dict, timeout: float) -> tuple[bytes, str]:
    url = API + path + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "market-rsi-p0-inventory/1.0",
                                    "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"public API returned HTTP {response.status}")
        raw = response.read(20_000_001)
    if len(raw) > 20_000_000:
        raise ValueError("public API response exceeded 20 MB safety limit")
    return raw, url


def parse_list(value: object) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def classify(events: list[dict], season: int) -> dict:
    """Screen slug/market types only; these are not schedule-matched games."""
    kind_counts: dict[str, int] = {}
    game_slugs = moneyline_events = strict_moneyline_events = 0
    moneyline_market_ids: set[str] = set()
    for event in events:
        match = GAME_SLUG.fullmatch(str(event.get("slug") or ""))
        if match and int(match.group(1)[:4]) in (season, season + 1):
            game_slugs += 1
            eligible = []
            for market in event.get("markets") or []:
                kind = str(market.get("sportsMarketType") or "missing")
                kind_counts[kind] = kind_counts.get(kind, 0) + 1
                if kind != "moneyline":
                    continue
                outcomes = parse_list(market.get("outcomes"))
                tokens = parse_list(market.get("clobTokenIds"))
                if len(outcomes) == 2:
                    eligible.append(market)
                    if len(tokens) == 2 and all(tokens) and market.get("conditionId"):
                        moneyline_market_ids.add(str(market.get("id") or ""))
            if eligible:
                moneyline_events += 1
            if len(eligible) == 1 and str(eligible[0].get("id") or "") in moneyline_market_ids:
                strict_moneyline_events += 1
    return {"events": len(events), "game_slug_candidates_not_schedule_matched": game_slugs,
            "events_with_two_outcome_moneyline": moneyline_events,
            "events_with_one_tokenized_moneyline": strict_moneyline_events,
            "unique_tokenized_moneyline_market_ids": len(moneyline_market_ids),
            "market_type_counts_on_game_slugs": kind_counts}


def fetch(output: Path, seasons: tuple[int, ...] = SEASONS, timeout: float = 30,
          max_pages_per_season: int = 100) -> dict:
    if not seasons or any(year not in SEASONS for year in seasons):
        raise ValueError("seasons must be a nonempty subset of 2021–2025")
    if timeout <= 0 or max_pages_per_season <= 0:
        raise ValueError("invalid request bounds")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "market_p0_polymarket_season_metadata_inventory_v1",
              "generated_utc": datetime.now(timezone.utc).isoformat(),
              "source": "public_gamma_api",
              "seasons": {}, "trades_opened": False, "scores_opened": False,
              "schedule_matched": False, "formal_data_admitted": False,
              "provider_cost_usd": "0"}
    for season in seasons:
        series_slug = SERIES_SLUGS[season]
        raw, series_url = get("/series", {"slug": series_slug, "limit": 10}, timeout)
        (output / f"{season}-series.raw.json").write_bytes(raw)
        exact = [row for row in json.loads(raw) if row.get("slug") == series_slug]
        if len(exact) != 1:
            raise ValueError(f"expected exactly one {series_slug} series")
        series_id = exact[0]["id"]
        start = f"{season}-09-01T00:00:00Z"
        end = f"{season + 1}-03-01T00:00:00Z"
        cursor = None
        seen_cursors: set[str] = set()
        events: list[dict] = []
        receipts: list[dict] = []
        for page in range(max_pages_per_season):
            params = {"series_id": series_id, "closed": "true",
                      "start_date_min": start, "start_date_max": end, "limit": 100}
            if cursor:
                params["after_cursor"] = cursor
            page_raw, url = get("/events/keyset", params, timeout)
            (output / f"{season}-page-{page:03d}.raw.json").write_bytes(page_raw)
            payload = json.loads(page_raw)
            batch = payload.get("events")
            if not isinstance(batch, list):
                raise ValueError("keyset page lacks events")
            receipts.append({"page": page, "url": url, "sha256": digest(page_raw),
                             "bytes": len(page_raw), "events": len(batch)})
            events.extend(batch)
            next_cursor = payload.get("next_cursor") or (payload.get("pagination") or {}).get("next_cursor")
            if not next_cursor:
                break
            if not batch or next_cursor in seen_cursors:
                raise ValueError("empty page or repeated cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise ValueError(f"season {season} exceeded max_pages_per_season; partial inventory")
        ids = [str(row.get("id") or "") for row in events]
        if any(not row for row in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"season {season} has missing or duplicate event IDs")
        report["seasons"][str(season)] = {"window": [start, end],
                                          "series_slug": series_slug,
                                          "series_id": series_id,
                                          "series_receipt": {"url": series_url,
                                                             "sha256": digest(raw)},
                                          "pages": receipts, **classify(events, season),
                                          "complete_keyset_pagination": True,
                                          "trade_coverage_verified": False,
                                          "schedule_matched": False}
        (output / "manifest.partial.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=list(SEASONS))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--max-pages-per-season", type=int, default=100)
    args = parser.parse_args()
    result = fetch(args.output, tuple(args.seasons), args.timeout, args.max_pages_per_season)
    print(json.dumps({"output": str(args.output), "seasons": result["seasons"],
                      "formal_data_admitted": False}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
