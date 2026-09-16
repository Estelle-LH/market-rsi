#!/usr/bin/env python3
"""Download, minimize, validate, and freeze a bounded Polymarket history canary.

This is source qualification, not Train/Dev construction.  It deliberately
samples five resolved game markets across three widely separated UTC dates so
we can test historical retention before authorizing a larger acquisition.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq

from market_rsi import canonical, digest, fresh_json


SCHEMA = "polymarket_official_historical_source_canary_v1"
DEFAULT_DATES = ("2026-06-15", "2026-07-15", "2026-08-21")
ALLOWED_HOSTS = frozenset({
    "gamma-api.polymarket.com",
    "data-api.polymarket.com",
    "clob.polymarket.com",
})
MAX_MARKETS = 5
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 200 * 1024 * 1024
CONDITION = re.compile(r"^0x[0-9a-fA-F]{64}$")

MARKET_SCHEMA = pa.schema([
    ("event_id", pa.string()), ("event_slug", pa.string()),
    ("event_title", pa.string()), ("event_end_ts_s", pa.int64()),
    ("market_id", pa.string()), ("market_slug", pa.string()),
    ("condition_id", pa.string()), ("game_start_ts_s", pa.int64()),
    ("outcome_0", pa.string()), ("outcome_1", pa.string()),
    ("final_price_0", pa.float64()), ("final_price_1", pa.float64()),
    ("token_0", pa.string()), ("token_1", pa.string()),
])
TRADE_SCHEMA = pa.schema([
    ("source_record_sha256", pa.string()), ("condition_id", pa.string()),
    ("asset_id", pa.string()), ("side", pa.string()),
    ("size", pa.float64()), ("price", pa.float64()),
    ("timestamp_s", pa.int64()), ("timestamp_utc", pa.string()),
    ("outcome", pa.string()), ("outcome_index", pa.int64()),
    ("transaction_hash", pa.string()),
])
PRICE_SCHEMA = pa.schema([
    ("condition_id", pa.string()), ("asset_id", pa.string()),
    ("outcome_index", pa.int64()), ("timestamp_s", pa.int64()),
    ("timestamp_utc", pa.string()), ("price", pa.float64()),
])


def _iso_timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return int(parsed.astimezone(timezone.utc).timestamp())


def _utc(timestamp_s: int) -> str:
    return datetime.fromtimestamp(timestamp_s, timezone.utc).isoformat()


def _json_array(value, field: str) -> list:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or len(parsed) != 2:
        raise ValueError(f"{field} must be a binary two-item array")
    return parsed


class PublicJsonClient:
    """GET-only client with a small allowlist and byte accounting."""

    def __init__(self):
        self.requests = []
        self.total_bytes = 0

    def get(self, endpoint: str, url: str, params: dict) -> object:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError("endpoint is outside the public source allowlist")
        query = urlencode(sorted(params.items()))
        request = Request(f"{url}?{query}", headers={
            "Accept": "application/json",
            "User-Agent": "market-rsi-source-canary/1",
        })
        with urlopen(request, timeout=45) as response:
            if response.status != 200:
                raise ValueError(f"{endpoint} returned HTTP {response.status}")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError(f"{endpoint} exceeded the per-response canary cap")
        self.total_bytes += len(raw)
        if self.total_bytes > MAX_TOTAL_BYTES:
            raise ValueError("source canary exceeded the total byte cap")
        result = json.loads(raw)
        self.requests.append({
            "endpoint": endpoint, "host": parsed.hostname, "path": parsed.path,
            "query": dict(sorted(params.items())), "http_status": 200,
            "response_bytes": len(raw),
            "response_sha256": hashlib.sha256(raw).hexdigest(),
        })
        return result


def _event_candidates(events: object, requested_date: str) -> list[dict]:
    if not isinstance(events, list):
        raise ValueError("Gamma events response is not a list")
    candidates = []
    for event in events:
        tags = {item.get("slug") for item in event.get("tags", [])
                if isinstance(item, dict)}
        if event.get("closed") is not True or "games" not in tags:
            continue
        exact = [market for market in event.get("markets", [])
                 if market.get("closed") is True
                 and market.get("gameStartTime")
                 and market.get("slug") == event.get("slug")]
        if not exact:
            continue
        market = min(exact, key=lambda item: int(item["id"]))
        condition = market.get("conditionId", "")
        outcomes = _json_array(market.get("outcomes"), "outcomes")
        prices = [float(item) for item in _json_array(market.get("outcomePrices"),
                                                       "outcomePrices")]
        tokens = [str(item) for item in _json_array(market.get("clobTokenIds"),
                                                     "clobTokenIds")]
        if not CONDITION.fullmatch(condition) or any(not item.isdigit() for item in tokens):
            raise ValueError("invalid market or token identity")
        if any(not 0 <= item <= 1 for item in prices):
            raise ValueError("invalid resolved outcome price")
        event_end = _iso_timestamp(event["endDate"])
        if datetime.fromtimestamp(event_end, timezone.utc).date().isoformat() != requested_date:
            # Gamma's end_date_max boundary is inclusive.  Keep the local UTC
            # partition strict instead of accepting the next day's midnight.
            continue
        candidates.append({
            "event_id": str(event["id"]), "event_slug": str(event["slug"]),
            "event_title": str(event["title"]), "event_end_ts_s": event_end,
            "market_id": str(market["id"]), "market_slug": str(market["slug"]),
            "condition_id": condition.lower(),
            "game_start_ts_s": _iso_timestamp(market["gameStartTime"]),
            "outcome_0": str(outcomes[0]), "outcome_1": str(outcomes[1]),
            "final_price_0": prices[0], "final_price_1": prices[1],
            "token_0": tokens[0], "token_1": tokens[1],
        })
    return sorted(candidates, key=lambda item: (item["event_end_ts_s"], item["event_id"]))


def _select_markets(by_date: dict[str, list[dict]]) -> list[dict]:
    if any(not rows for rows in by_date.values()):
        missing = sorted(day for day, rows in by_date.items() if not rows)
        raise ValueError(f"no resolved game market for requested dates: {missing}")
    selected = [by_date[day][0] for day in sorted(by_date)]
    remaining = [row for day in sorted(by_date) for row in by_date[day][1:]]
    selected.extend(remaining[:MAX_MARKETS - len(selected)])
    return sorted(selected, key=lambda item: (item["event_end_ts_s"], item["event_id"]))


def _clean_trades(raw_rows: object, market: dict) -> tuple[list[dict], int]:
    if not isinstance(raw_rows, list):
        raise ValueError("trades response is not a list")
    allowed_assets = {market["token_0"], market["token_1"]}
    cleaned = {}
    for raw in raw_rows:
        if str(raw.get("conditionId", "")).lower() != market["condition_id"]:
            raise ValueError("trade condition does not join to selected market")
        asset = str(raw.get("asset", ""))
        side = str(raw.get("side", "")).upper()
        price, size, timestamp = float(raw["price"]), float(raw["size"]), int(raw["timestamp"])
        if asset not in allowed_assets or side not in {"BUY", "SELL"}:
            raise ValueError("invalid trade asset or side")
        if not 0 <= price <= 1 or size <= 0 or timestamp <= 0:
            raise ValueError("invalid trade price, size, or timestamp")
        identity = digest(raw)
        cleaned[identity] = {
            "source_record_sha256": identity,
            "condition_id": market["condition_id"], "asset_id": asset,
            "side": side, "size": size, "price": price,
            "timestamp_s": timestamp, "timestamp_utc": _utc(timestamp),
            "outcome": str(raw.get("outcome", "")),
            "outcome_index": int(raw.get("outcomeIndex", -1)),
            "transaction_hash": str(raw.get("transactionHash", "")),
        }
    rows = sorted(cleaned.values(), key=lambda item: (
        item["timestamp_s"], item["transaction_hash"], item["source_record_sha256"]))
    return rows, len(raw_rows) - len(rows)


def _clean_prices(raw: object, market: dict, asset: str, outcome_index: int) -> tuple[list[dict], int]:
    history = raw.get("history") if isinstance(raw, dict) else None
    if not isinstance(history, list):
        raise ValueError("price-history response has no history list")
    unique = {}
    for point in history:
        timestamp, price = int(point["t"]), float(point["p"])
        if timestamp <= 0 or not 0 <= price <= 1:
            raise ValueError("invalid price-history point")
        key = (timestamp, price)
        unique[key] = {
            "condition_id": market["condition_id"], "asset_id": asset,
            "outcome_index": outcome_index, "timestamp_s": timestamp,
            "timestamp_utc": _utc(timestamp), "price": price,
        }
    rows = sorted(unique.values(), key=lambda item: (item["timestamp_s"], item["price"]))
    return rows, len(history) - len(rows)


def _maximum_gap(rows: list[dict]) -> int | None:
    timestamps = sorted({row["timestamp_s"] for row in rows})
    return max((later - earlier for earlier, later in zip(timestamps, timestamps[1:])),
               default=None)


def controller_evidence(report: dict) -> dict:
    """Return aggregate-only evidence safe for the isolated controller."""
    body = {
        "schema": "market_source_canary_controller_evidence_v1",
        "provider": report["source"]["provider"],
        "canary_status": report["canary_status"],
        "requested_utc_dates": report["scope"]["requested_utc_dates"],
        "whole_markets": report["scope"]["whole_markets"],
        "response_bytes": report["scope"]["response_bytes"],
        "tables": report["tables"],
        "historical_depth_observed": report["historical_depth_observed"],
        "checks": report["checks"],
        "rejection_reasons": report["rejection_reasons"],
        "formal_dataset_ready": report["formal_dataset_ready"],
        "full_download_authorized": report["full_download_authorized"],
        "source_report_sha256": report["report_sha256"],
    }
    return {**body, "evidence_sha256": digest(body)}


def run_canary(output: Path, client=None, utc_dates=DEFAULT_DATES) -> dict:
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    parsed_dates = [date.fromisoformat(item) for item in utc_dates]
    if len(parsed_dates) != 3 or len(set(parsed_dates)) != 3:
        raise ValueError("exactly three distinct UTC dates are required")
    client = client or PublicJsonClient()
    by_date = {}
    for requested in parsed_dates:
        next_day = requested + timedelta(days=1)
        payload = client.get("gamma_events", "https://gamma-api.polymarket.com/events", {
            "closed": "true", "end_date_max": f"{next_day.isoformat()}T00:00:00Z",
            "end_date_min": f"{requested.isoformat()}T00:00:00Z",
            "limit": "100", "tag_slug": "sports",
        })
        by_date[requested.isoformat()] = _event_candidates(payload, requested.isoformat())
    markets = _select_markets(by_date)

    all_trades, all_prices = [], []
    per_market = []
    for market in markets:
        raw_trades = []
        first = client.get("data_api_trades", "https://data-api.polymarket.com/trades", {
            "limit": "10000", "market": market["condition_id"], "offset": "0",
        })
        raw_trades.extend(first)
        trade_truncated = False
        if len(first) == 10000:
            second = client.get("data_api_trades", "https://data-api.polymarket.com/trades", {
                "limit": "10000", "market": market["condition_id"], "offset": "10000",
            })
            raw_trades.extend(second)
            trade_truncated = len(second) == 10000
        trades, duplicate_trades = _clean_trades(raw_trades, market)
        all_trades.extend(trades)

        market_prices = []
        duplicate_prices = 0
        for outcome_index, asset in enumerate((market["token_0"], market["token_1"])):
            raw_prices = client.get("clob_price_history",
                                    "https://clob.polymarket.com/prices-history", {
                                        "fidelity": "5", "interval": "max", "market": asset,
                                    })
            prices, duplicates = _clean_prices(raw_prices, market, asset, outcome_index)
            market_prices.extend(prices)
            duplicate_prices += duplicates
        all_prices.extend(market_prices)
        per_market.append({
            "event_id": market["event_id"], "market_id": market["market_id"],
            "condition_id": market["condition_id"],
            "trade_rows": len(trades), "trade_duplicates_removed": duplicate_trades,
            "trade_history_truncated_at_20000": trade_truncated,
            "price_rows": len(market_prices), "price_duplicates_removed": duplicate_prices,
            "maximum_price_history_gap_seconds": _maximum_gap(market_prices),
            "deterministic_trade_replay_sha256": digest(trades),
            "deterministic_price_replay_sha256": digest(market_prices),
        })

    trade_markets_nonempty = sum(item["trade_rows"] > 0 for item in per_market)
    price_markets_nonempty = sum(item["price_rows"] > 0 for item in per_market)
    trade_majority_nonempty = trade_markets_nonempty > len(per_market) / 2
    price_majority_nonempty = price_markets_nonempty > len(per_market) / 2
    rejection_reasons = []
    if not trade_majority_nonempty:
        rejection_reasons.append("historical trades are empty for a majority of canary markets")
    if not price_majority_nonempty:
        rejection_reasons.append("price history is empty for a majority of canary markets")

    output.mkdir(parents=True, mode=0o700)
    clean = output / "clean"
    clean.mkdir(mode=0o700)
    pq.write_table(pa.Table.from_pylist(markets, schema=MARKET_SCHEMA),
                   clean / "markets.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist(all_trades, schema=TRADE_SCHEMA),
                   clean / "trades.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist(all_prices, schema=PRICE_SCHEMA),
                   clean / "price_history.parquet", compression="zstd")
    for path in clean.iterdir():
        os.chmod(path, 0o600)

    stream_timestamps = [row["timestamp_s"] for row in all_trades + all_prices]
    market_dates = sorted({_utc(item["event_end_ts_s"])[:10] for item in markets})
    body = {
        "schema": SCHEMA,
        "source": {
            "provider": "Polymarket official public APIs",
            "event_endpoint": "https://gamma-api.polymarket.com/events",
            "trade_endpoint": "https://data-api.polymarket.com/trades",
            "price_history_endpoint": "https://clob.polymarket.com/prices-history",
            "authentication_used": False,
            "documentation_checked_at_utc": "2026-09-09",
            "terms_or_bulk_reuse_review": "pending_before_full_ingest",
        },
        "scope": {
            "requested_utc_dates": sorted(utc_dates), "selected_market_dates": market_dates,
            "whole_markets": len(markets), "maximum_markets": MAX_MARKETS,
            "response_bytes": client.total_bytes, "response_byte_cap": MAX_TOTAL_BYTES,
        },
        "requests": client.requests,
        "tables": {
            "markets": len(markets), "trades": len(all_trades),
            "price_history": len(all_prices),
        },
        "per_market": per_market,
        "historical_depth_observed": {
            "oldest_selected_market_date": min(market_dates),
            "newest_selected_market_date": max(market_dates),
            "calendar_span_days": (max(date.fromisoformat(item) for item in market_dates)
                                   - min(date.fromisoformat(item) for item in market_dates)).days + 1,
            "oldest_retained_stream_timestamp_utc": (_utc(min(stream_timestamps))
                                                       if stream_timestamps else None),
            "newest_retained_stream_timestamp_utc": (_utc(max(stream_timestamps))
                                                       if stream_timestamps else None),
        },
        "checks": {
            "public_access_without_credentials": "pass",
            "three_spread_utc_dates": "pass" if len(market_dates) == 3 else "fail",
            "trade_history_nonempty_for_majority": ("pass" if trade_majority_nonempty else "fail"),
            "price_history_nonempty_for_majority": ("pass" if price_majority_nonempty else "fail"),
            "binary_market_and_resolution_linkage": "pass",
            "timestamps_parse_as_utc": "pass",
            "price_and_size_bounds": "pass",
            "exact_duplicates_removed_and_counted": "pass",
            "deterministic_sorted_replay": "pass",
            "byte_caps": "pass",
            "terms_or_bulk_reuse_review": "pending",
        },
        "canary_status": ("data_path_pass_terms_review_pending"
                          if not rejection_reasons else "rejected_by_frozen_plan"),
        "rejection_reasons": rejection_reasons,
        "formal_dataset_ready": False,
        "why_not_formal": (
            "This is only five whole markets across three dates. It proves historical "
            "retention and the cleaning path, not the required 60 days and 150 markets."
        ),
        "full_download_authorized": False,
        "next_gate": (
            "Complete terms/bulk-reuse review, then inventory the entire proposed date "
            "range before authorizing selected full-history partitions."
        ),
    }
    report = {**body, "report_sha256": digest(body)}
    fresh_json(output / "clean-data-report.json", report)
    os.chmod(output / "clean-data-report.json", 0o600)
    fresh_json(output / "controller-evidence.json", controller_evidence(report))
    os.chmod(output / "controller-evidence.json", 0o600)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--utc-date", action="append", dest="utc_dates")
    args = parser.parse_args()
    print(canonical(run_canary(args.output, utc_dates=tuple(args.utc_dates or DEFAULT_DATES))))


if __name__ == "__main__":
    main()
