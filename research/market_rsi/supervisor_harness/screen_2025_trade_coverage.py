"""Bounded, source-only 2025 NFL moneyline trade-coverage screen.

This follows the already researched public Polymarket trade endpoint used by
``screen_2025_trade_canary``. It reads only the corrected, complete 285-game
identity mapping and catalog. The fixed 12-hour pre-game to 5-hour post-start
window is a coverage diagnostic, not a label, prediction or formal admission.
Only counts, timestamps and SHA-256 page receipts are saved: no raw trades,
prices, sizes, wallets, outcomes, scores, or protected Dev/Final data.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from supervisor_harness.screen_2025_schedule import load_events


TRADES_URL = "https://data-api.polymarket.com/trades"
GAME_COUNT = 285
PAGE_LIMIT = 10_000
MAX_PAGES_PER_GAME = 2
MAX_REQUESTS = GAME_COUNT * MAX_PAGES_PER_GAME
MAX_PAGE_BYTES = 16_000_000
MAX_TOTAL_BYTES = 300_000_000
PRE_GAME_HOURS = 12
POST_START_HOURS = 5


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("game start missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("game start lacks timezone")
    return parsed.astimezone(timezone.utc)


def selections(mapping_dir: Path, catalog: Path) -> tuple[list[dict], dict]:
    """Bind all mapped games to hashed catalog metadata without reading scores."""
    mapping_dir, catalog = Path(mapping_dir).resolve(), Path(catalog).resolve()
    report = json.loads((mapping_dir / "manifest.json").read_text())
    if (report.get("schema") != "market_p0_2025_schedule_screen_v1"
            or report.get("formal_data_admitted") is not False
            or report.get("trade_coverage_verified") is not False
            or report.get("mapped_unique_games") != GAME_COUNT
            or report.get("schedule_games") != GAME_COUNT):
        raise ValueError("expected corrected, unadmitted 285-game mapping")
    mapping_raw = (mapping_dir / "mapping.json").read_bytes()
    if sha(mapping_raw) != report.get("mapping_sha256"):
        raise ValueError("mapping hash changed")
    mapping = json.loads(mapping_raw)
    if not isinstance(mapping, list) or len(mapping) != GAME_COUNT:
        raise ValueError("mapping must contain exactly 285 games")
    events, pages = load_events(catalog)
    if len(events) != report.get("catalog_events"):
        raise ValueError("mapping and catalog event counts differ")
    by_event: dict[str, list[dict]] = {}
    for event in events:
        by_event.setdefault(str(event.get("id")), []).append(event)

    bound: list[dict] = []
    seen: dict[str, set[str]] = {key: set() for key in
                                 ("game_id", "event_id", "market_id", "condition_id")}
    for row in mapping:
        if not isinstance(row, dict):
            raise ValueError("mapping row is not an object")
        selected = {}
        for key in ("game_id", "event_id", "market_id", "condition_id", "game_date"):
            value = row.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"mapping lacks {key}")
            selected[key] = value
        for key in seen:
            if selected[key] in seen[key]:
                raise ValueError(f"duplicate mapped {key}")
            seen[key].add(selected[key])
        matches = by_event.get(selected["event_id"], [])
        if len(matches) != 1:
            raise ValueError("mapped event missing or duplicated in catalog")
        event = matches[0]
        markets = [market for market in event.get("markets") or []
                   if str(market.get("id")) == selected["market_id"]
                   and str(market.get("conditionId")) == selected["condition_id"]
                   and market.get("sportsMarketType") == "moneyline"]
        if len(markets) != 1:
            raise ValueError("mapped moneyline missing or duplicated in catalog")
        tokens = markets[0].get("clobTokenIds")
        if isinstance(tokens, str):
            tokens = json.loads(tokens)
        if (not isinstance(tokens, list) or len(tokens) != 2
                or len({str(token) for token in tokens}) != 2 or not all(tokens)):
            raise ValueError("mapped moneyline needs two distinct outcome tokens")
        start = parse_utc(event.get("eventStartTime") or event.get("startTime"))
        start_ts = int(start.timestamp())
        selected["game_start_timestamp"] = start_ts
        selected["start_timestamp"] = int((start - timedelta(hours=PRE_GAME_HOURS)).timestamp())
        selected["end_timestamp"] = int((start + timedelta(hours=POST_START_HOURS)).timestamp())
        selected["_tokens"] = frozenset(str(token) for token in tokens)
        bound.append(selected)
    bound.sort(key=lambda row: (row["game_date"], row["game_id"], row["event_id"]))
    provenance = {"mapping_sha256": sha(mapping_raw),
                  "catalog_page_sha256": [page["sha256"] for page in pages],
                  "catalog_events": len(events)}
    return bound, provenance


def fetch_page(condition_id: str, offset: int, lower: int, upper: int,
               timeout: float, byte_cap: int) -> tuple[bytes, str]:
    """Read at most byte_cap + 1 bytes so oversized responses fail closed."""
    url = TRADES_URL + "?" + urlencode({"market": condition_id, "limit": PAGE_LIMIT,
                                        "offset": offset, "start": lower, "end": upper,
                                        "takerOnly": "true"})
    request = Request(url, headers={"User-Agent": "market-rsi-p0-coverage/1.0",
                                    "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"trade source HTTP {response.status}")
        raw = response.read(byte_cap + 1)
    if len(raw) > byte_cap:
        raise ValueError("trade page exceeded byte cap; no completeness claim")
    return raw, url


def screen_game(selection: dict, *, timeout: float, request_budget: int,
                byte_budget: int, page_byte_cap: int) -> tuple[dict, int, int]:
    """Summarize one game; a full final page is explicitly incomplete."""
    if request_budget < 1 or byte_budget < 1:
        raise ValueError("global request or byte budget exhausted")
    receipts: list[dict] = []
    previous_pages: set[str] = set()
    timestamps: set[int] = set()
    count = pre_game = post_start = used_bytes = 0
    for page in range(MAX_PAGES_PER_GAME):
        if page >= request_budget:
            raise ValueError("global request budget exhausted before pagination completed")
        remaining = byte_budget - used_bytes
        if remaining < 1:
            raise ValueError("global byte budget exhausted before pagination completed")
        raw, url = fetch_page(selection["condition_id"], page * PAGE_LIMIT,
                              selection["start_timestamp"], selection["end_timestamp"],
                              timeout, min(page_byte_cap, remaining))
        if len(raw) > min(page_byte_cap, remaining):
            raise ValueError("trade page exceeded byte budget")
        used_bytes += len(raw)
        batch = json.loads(raw)
        if not isinstance(batch, list) or len(batch) > PAGE_LIMIT:
            raise ValueError("trade endpoint returned an invalid page")
        this_page: set[str] = set()
        for trade in batch:
            if not isinstance(trade, dict):
                raise ValueError("trade row is not an object")
            if trade.get("conditionId") != selection["condition_id"]:
                raise ValueError("trade belongs to another condition")
            if str(trade.get("asset")) not in selection["_tokens"]:
                raise ValueError("trade asset is not a selected token")
            timestamp = int(trade["timestamp"])
            if not selection["start_timestamp"] <= timestamp <= selection["end_timestamp"]:
                raise ValueError("trade endpoint ignored fixed time bounds")
            signature = sha(json.dumps(trade, sort_keys=True, separators=(",", ":")).encode())
            if signature in previous_pages:
                raise ValueError("overlapping trade pages; pagination incomplete")
            this_page.add(signature)
            timestamps.add(timestamp)
            count += 1
            if timestamp < selection["game_start_timestamp"]:
                pre_game += 1
            else:
                post_start += 1
        previous_pages.update(this_page)
        receipts.append({"url": url, "sha256": sha(raw), "bytes": len(raw),
                         "rows": len(batch), "offset": page * PAGE_LIMIT})
        if len(batch) < PAGE_LIMIT:
            break
    else:
        raise ValueError("last allowed trade page was full; pagination incomplete")
    public = {key: selection[key] for key in
              ("game_id", "event_id", "market_id", "condition_id", "game_date",
               "start_timestamp", "game_start_timestamp", "end_timestamp")}
    public.update({"trades": count, "pre_game_trades": pre_game,
                   "game_to_plus_five_hours_trades": post_start,
                   "first_timestamp": min(timestamps) if timestamps else None,
                   "last_timestamp": max(timestamps) if timestamps else None,
                   "distinct_timestamps": len(timestamps), "page_receipts": receipts})
    return public, len(receipts), used_bytes


def screen(mapping_dir: Path, catalog: Path, output: Path, *, timeout: float = 30.0,
           max_requests: int = MAX_REQUESTS, max_total_bytes: int = MAX_TOTAL_BYTES,
           max_page_bytes: int = MAX_PAGE_BYTES) -> dict:
    """Run a source-only screen; preserve incomplete checkpoints on failure."""
    if timeout <= 0 or timeout > 30:
        raise ValueError("timeout must be in (0, 30] seconds")
    if not GAME_COUNT <= max_requests <= MAX_REQUESTS:
        raise ValueError("request cap must be between 285 and 570")
    if not 1 <= max_total_bytes <= MAX_TOTAL_BYTES:
        raise ValueError("total byte cap exceeds hard bound")
    if not 1 <= max_page_bytes <= MAX_PAGE_BYTES:
        raise ValueError("page byte cap exceeds hard bound")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    chosen, provenance = selections(mapping_dir, catalog)
    output.mkdir(parents=True, exist_ok=False)
    results: list[dict] = []
    requests_used = bytes_used = 0

    def checkpoint(status: str, failed_game_id: str | None = None,
                   failure_type: str | None = None) -> None:
        partial_raw = encoded(results)
        partial = {"schema": "market_p0_2025_trade_coverage_partial_v1",
                   "status": status, "expected_games": GAME_COUNT,
                   "completed_games": len(results),
                   "last_completed_game_id": results[-1]["game_id"] if results else None,
                   "failed_game_id": failed_game_id, "failure_type": failure_type,
                   "completed_game_requests": requests_used,
                   "completed_game_bytes": bytes_used,
                   "coverage_partial_sha256": sha(partial_raw),
                   "mapping_and_catalog": provenance,
                   "complete_within_bounded_windows": False,
                   "event_aligned_labels_verified": False,
                   "historical_quote_coverage_verified": False,
                   "formal_data_admitted": False, "provider_cost_usd": "0"}
        (output / "coverage.partial.json").write_bytes(partial_raw)
        (output / "manifest.partial.json").write_bytes(encoded(partial))

    checkpoint("in_progress")
    for selection in chosen:
        try:
            result, game_requests, game_bytes = screen_game(
                selection, timeout=timeout, request_budget=max_requests - requests_used,
                byte_budget=max_total_bytes - bytes_used, page_byte_cap=max_page_bytes)
        except Exception as error:
            checkpoint("failed", selection["game_id"], type(error).__name__)
            raise
        results.append(result)
        requests_used += game_requests
        bytes_used += game_bytes
        checkpoint("in_progress")
    coverage_raw = encoded(results)
    report = {"schema": "market_p0_2025_trade_coverage_v1",
              "source": TRADES_URL, "mapping_and_catalog": provenance,
              "window_rule": {"pre_game_hours": PRE_GAME_HOURS,
                              "post_start_hours": POST_START_HOURS,
                              "taker_only": True, "page_limit": PAGE_LIMIT},
              "hard_caps": {"max_pages_per_game": MAX_PAGES_PER_GAME,
                            "max_requests": max_requests,
                            "max_total_bytes": max_total_bytes,
                            "max_page_bytes": max_page_bytes,
                            "timeout_seconds": timeout},
              "games_screened": len(results), "games_with_trades": sum(row["trades"] > 0 for row in results),
              "games_with_post_start_trades": sum(row["game_to_plus_five_hours_trades"] > 0 for row in results),
              "total_trades": sum(row["trades"] for row in results),
              "requests_used": requests_used, "bytes_read": bytes_used,
              "coverage_sha256": sha(coverage_raw),
              "complete_within_bounded_windows": True,
              "event_aligned_labels_verified": False,
              "historical_quote_coverage_verified": False,
              "formal_data_admitted": False, "provider_cost_usd": "0"}
    (output / "coverage.json").write_bytes(coverage_raw)
    (output / "manifest.json").write_bytes(encoded(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    parser.add_argument("--max-total-bytes", type=int, default=MAX_TOTAL_BYTES)
    parser.add_argument("--max-page-bytes", type=int, default=MAX_PAGE_BYTES)
    parser.add_argument("--execute-public-requests", action="store_true",
                        help="explicitly authorize the bounded 285-game public API screen")
    args = parser.parse_args()
    if not args.execute_public_requests:
        parser.error("refusing network screen without --execute-public-requests")
    print(json.dumps(screen(args.mapping, args.catalog, args.output, timeout=args.timeout,
                            max_requests=args.max_requests, max_total_bytes=args.max_total_bytes,
                            max_page_bytes=args.max_page_bytes), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
