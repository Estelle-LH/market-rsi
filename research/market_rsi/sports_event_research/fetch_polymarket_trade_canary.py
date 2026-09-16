"""Fetch a bounded public trade tape for the frozen non-Final NFL canary."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sports_event_research.fetch_polymarket_price_canary import bind_game, read_selection


URL = "https://data-api.polymarket.com/trades"
SAFE_FIELDS = ("side", "asset", "conditionId", "size", "price", "timestamp",
               "eventSlug", "outcome", "outcomeIndex")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fetch_page(condition: str, offset: int, start: int, end: int,
               timeout: float) -> tuple[bytes, str]:
    url = URL + "?" + urlencode({"market": condition, "limit": 10000,
                                  "offset": offset, "start": start, "end": end,
                                  "takerOnly": "true"})
    request = Request(url, headers={"User-Agent": "market-rsi-research/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Polymarket returned HTTP {response.status}")
        return response.read(), url


def validate(trades: list[dict], selection: dict) -> dict:
    timestamps, prices, sizes = [], [], []
    for trade in trades:
        if trade.get("conditionId") != selection["condition_id"]:
            raise ValueError("trade from another condition")
        timestamp, price, size = int(trade["timestamp"]), float(trade["price"]), float(trade["size"])
        if not 0 <= price <= 1 or size < 0:
            raise ValueError("invalid trade price or size")
        if str(trade.get("asset")) not in set(selection["clob_token_ids"]):
            raise ValueError("trade asset is not a selected outcome token")
        timestamps.append(timestamp); prices.append(price); sizes.append(size)
    return {
        "trades": len(trades),
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "distinct_timestamps": len(set(timestamps)),
        "distinct_prices": len(set(prices)),
        "reported_token_notional": sum(size * price for size, price in zip(sizes, prices)),
    }


def fetch(selection_path: Path, game_master: Path, output: Path, timeout: float = 30.0,
          expected_split_role: str = "market_train") -> dict:
    selection_path, game_master = Path(selection_path).resolve(), Path(game_master).resolve()
    selection = read_selection(selection_path, expected_split_role)
    game = bind_game(selection, game_master, expected_split_role)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    event_start = datetime.fromisoformat(selection["event_start_utc"].replace("Z", "+00:00"))
    lower, upper = int((event_start - timedelta(days=7)).timestamp()), int((event_start + timedelta(days=1)).timestamp())
    trades, receipts, possibly_truncated = [], [], False
    for page, offset in enumerate((0, 10000)):
        raw, url = fetch_page(selection["condition_id"], offset, lower, upper, timeout)
        path = output / f"trades-page-{page}.raw.json"; path.write_bytes(raw)
        batch = json.loads(raw)
        if not isinstance(batch, list):
            raise ValueError("trade endpoint did not return a list")
        receipts.append({"url": url, "sha256": sha(raw), "bytes": len(raw), "rows": len(batch)})
        trades.extend(batch)
        if len(batch) < 10000:
            break
        if offset == 10000:
            possibly_truncated = True
    identities = {(row.get("transactionHash"), row.get("asset"), row.get("timestamp"),
                   row.get("price"), row.get("size"), row.get("side")) for row in trades}
    if len(identities) != len(trades):
        raise ValueError("duplicate trade rows across pages")
    summary = validate(trades, selection)
    window = [row for row in trades if lower <= int(row["timestamp"]) <= upper]
    window_summary = validate(window, selection)
    safe = sorted(({key: row.get(key) for key in SAFE_FIELDS} for row in window),
                  key=lambda row: (int(row["timestamp"]), str(row["asset"]), str(row["side"])))
    safe_path = output / "trade_window.csv"
    with safe_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SAFE_FIELDS); writer.writeheader(); writer.writerows(safe)
    result = {
        "schema": "polymarket_nfl_trade_canary_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": URL,
        "canonical_game": {key: game[key] for key in (
            "nflverse_game_id", "sportradar_game_id", "game_date", "scheduled_utc",
            "home_team", "away_team", "split_role")},
        "selection_sha256": sha(selection_path.read_bytes()),
        "game_master_sha256": sha(game_master.read_bytes()),
        "page_receipts": receipts,
        "retrieved_query_summary": summary,
        "frozen_window": {"start_timestamp": lower, "end_timestamp": upper, **window_summary},
        "safe_trade_window_sha256": sha(safe_path.read_bytes()),
        "possibly_truncated_at_20000": possibly_truncated,
        "query_uses_frozen_start_end_window": True,
        "taker_only": True,
        "wallet_fields_in_safe_output": False,
        "is_historical_l2": False,
        "is_order_or_fill_evidence_for_us": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--game-master", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    print(json.dumps(fetch(args.selection, args.game_master, args.output, args.timeout), indent=2))


if __name__ == "__main__":
    main()
