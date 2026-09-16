"""Archive a bounded public 2024-season NFL metadata catalog for Train discovery.

This does not fetch trades, prices, results, or protected evaluation cohorts.
The older events have no reliable gameId, so no game mapping is inferred here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from sports_event_research.fetch_polymarket_catalog import get


SERIES_SLUG = "nfl"
START_MIN = "2024-09-01T00:00:00Z"
START_MAX = "2025-02-15T00:00:00Z"
GAME_SLUG = re.compile(r"^nfl-[a-z0-9]+-[a-z0-9]+-202[45]-\d{2}-\d{2}$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def event_start(event: dict) -> str:
    return str(event.get("eventStartTime") or event.get("startTime") or "")


def fetch(output: Path, timeout: float = 30.0, max_pages: int = 10) -> dict:
    """Fetch metadata once into a new directory; fail closed on pagination drift."""
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)

    series_raw, series_url = get("/series", {"slug": SERIES_SLUG, "limit": 10}, timeout)
    (output / "series.raw.json").write_bytes(series_raw)
    series = json.loads(series_raw)
    exact = [item for item in series if item.get("slug") == SERIES_SLUG]
    if len(exact) != 1:
        raise ValueError("expected exactly one NFL series")
    series_id = exact[0]["id"]

    events: list[dict] = []
    receipts: list[dict] = []
    cursor = None
    seen_cursors: set[str] = set()
    for page in range(max_pages):
        params = {
            "series_id": series_id,
            "closed": "true",
            "start_date_min": START_MIN,
            "start_date_max": START_MAX,
            "limit": 100,
        }
        if cursor:
            params["after_cursor"] = cursor
        raw, url = get("/events/keyset", params, timeout)
        (output / f"events-page-{page:03d}.raw.json").write_bytes(raw)
        payload = json.loads(raw)
        batch = payload.get("events")
        if not isinstance(batch, list):
            raise ValueError("keyset response lacks events")
        receipts.append({"page": page, "url": url, "sha256": sha256(raw), "bytes": len(raw),
                         "events": len(batch)})
        events.extend(batch)
        next_cursor = payload.get("next_cursor") or (payload.get("pagination") or {}).get("next_cursor")
        if not next_cursor:
            break
        if not batch or next_cursor in seen_cursors:
            raise ValueError("empty page or repeated keyset cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    else:
        raise ValueError("catalog exceeded max_pages; partial catalog cannot be admitted")

    ids = [str(event.get("id") or "") for event in events]
    if not ids or any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("empty, missing-ID, or duplicated event catalog")
    for event in events:
        start = event_start(event)
        if not (START_MIN <= start < START_MAX):
            raise ValueError("event outside frozen 2024-season window or missing start")
        if event.get("seriesSlug") not in (None, SERIES_SLUG):
            raise ValueError("event belongs to another series")

    events.sort(key=lambda event: (event_start(event), str(event["id"])))
    catalog_bytes = (json.dumps(events, indent=2, sort_keys=True) + "\n").encode()
    (output / "events.catalog.json").write_bytes(catalog_bytes)
    candidates = [event for event in events if GAME_SLUG.fullmatch(str(event.get("slug") or ""))]
    two_outcome_moneyline = 0
    for event in candidates:
        for market in event.get("markets") or []:
            outcomes = market.get("outcomes") or []
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except json.JSONDecodeError:
                    outcomes = []
            if market.get("sportsMarketType") == "moneyline" and len(outcomes) == 2:
                two_outcome_moneyline += 1

    manifest = {
        "schema": "polymarket_2024_nfl_train_catalog_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_kind": "public_metadata_api",
        "season_start_min": START_MIN,
        "season_start_max_exclusive": START_MAX,
        "series_request": {"url": series_url, "sha256": sha256(series_raw),
                           "bytes": len(series_raw)},
        "series_id": series_id,
        "series_slug": SERIES_SLUG,
        "page_receipts": receipts,
        "events": len(events),
        "game_slug_candidates_not_mapped": len(candidates),
        "two_outcome_moneyline_markets_on_candidates": two_outcome_moneyline,
        "events_with_game_id": sum(bool(event.get("gameId")) for event in events),
        "catalog_sha256": sha256(catalog_bytes),
        "trades_opened": False,
        "prices_opened": False,
        "results_opened_by_runner": False,
        "game_mapping_verified": False,
        "train_admitted": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    print(json.dumps(fetch(args.output, args.timeout), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
