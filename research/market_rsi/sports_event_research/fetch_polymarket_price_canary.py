"""Fetch one frozen, non-Final Polymarket NFL price-history canary."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen


URL = "https://clob.polymarket.com/batch-prices-history"
SLUG = re.compile(r"^nfl-([a-z]+)-([a-z]+)-(\d{4}-\d{2}-\d{2})$")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


SELECTION_SCHEMAS = {
    "polymarket_nfl_catalog_canary_selection_v1": None,
    "polymarket_nfl_trade_pilot_selection_v1": "market_train",
    "polymarket_nfl_route_dev_selection_v1": "route_dev",
}


def read_selection(path: Path, expected_split_role: str = "market_train") -> dict:
    value = json.loads(Path(path).read_text())
    if expected_split_role == "sealed_final" or value.get("split_role") == "sealed_final":
        raise ValueError("sealed Final cannot be opened by this fetcher")
    schema_role = SELECTION_SCHEMAS.get(value.get("schema"))
    if (value.get("schema") not in SELECTION_SCHEMAS
            or value.get("price_history_opened") is not False
            or len(value.get("clob_token_ids") or []) != 2):
        raise ValueError("invalid or already-open canary selection")
    if schema_role is not None and (schema_role != expected_split_role
            or value.get("split_role") != expected_split_role
            or value.get("trades_opened") is not False):
        raise ValueError(f"selection is not unopened {expected_split_role}")
    return value


def bind_game(selection: dict, master: Path, expected_split_role: str = "market_train") -> dict:
    if expected_split_role == "sealed_final":
        raise ValueError("sealed Final cannot be opened by this fetcher")
    if selection.get("nflverse_game_id"):
        with Path(master).open(newline="") as stream:
            rows = [row for row in csv.DictReader(stream)
                    if row.get("nflverse_game_id") == selection["nflverse_game_id"]]
        if len(rows) != 1:
            raise ValueError("selection does not bind to exactly one canonical game ID")
        if (rows[0]["split_role"] != expected_split_role
                or selection.get("split_role") != expected_split_role):
            raise ValueError(f"selection is not bound to {expected_split_role}")
        for key in ("sportradar_game_id", "home_team", "away_team", "scheduled_utc"):
            if selection.get(key) != rows[0].get(key):
                raise ValueError(f"pilot selection disagrees with canonical {key}")
        return rows[0]
    match = SLUG.fullmatch(selection.get("event_slug") or "")
    if not match:
        raise ValueError("canary event slug does not encode away/home/date")
    away, home, game_date = (match.group(1).upper(), match.group(2).upper(), match.group(3))
    with Path(master).open(newline="") as stream:
        rows = [row for row in csv.DictReader(stream)
                if row["game_date"] == game_date and row["away_team"] == away and row["home_team"] == home]
    if len(rows) != 1:
        raise ValueError("canary does not map to exactly one canonical game")
    if rows[0]["split_role"] == "sealed_final":
        raise ValueError("canary selection would open sealed Final")
    if rows[0]["split_role"] != expected_split_role:
        raise ValueError(f"canary selection is not bound to {expected_split_role}")
    return rows[0]


def validate_history(raw: bytes, tokens: list[str]) -> dict:
    payload = json.loads(raw)
    history = payload.get("history")
    if not isinstance(history, dict):
        raise ValueError("price response lacks history map")
    result = {}
    for token in tokens:
        points = history.get(token)
        if not isinstance(points, list):
            raise ValueError(f"price response lacks selected token {token}")
        timestamps, prices = [], []
        for point in points:
            timestamp, price = int(point["t"]), float(point["p"])
            if not 0 <= price <= 1:
                raise ValueError("price outside [0,1]")
            timestamps.append(timestamp); prices.append(price)
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("price timestamps are duplicated or not monotonic")
        changes = sum(left != right for left, right in zip(prices, prices[1:]))
        result[token] = {
            "points": len(points),
            "first_timestamp": timestamps[0] if timestamps else None,
            "last_timestamp": timestamps[-1] if timestamps else None,
            "distinct_prices": len(set(prices)),
            "change_fraction": changes / (len(prices) - 1) if len(prices) > 1 else 0.0,
        }
    return result


def fetch(selection_path: Path, game_master: Path, output: Path, timeout: float = 30.0,
          expected_split_role: str = "market_train") -> dict:
    selection_path, game_master = Path(selection_path).resolve(), Path(game_master).resolve()
    selection = read_selection(selection_path, expected_split_role)
    game = bind_game(selection, game_master, expected_split_role)
    event_start = datetime.fromisoformat(selection["event_start_utc"].replace("Z", "+00:00"))
    start, end = event_start - timedelta(days=7), event_start + timedelta(days=1)
    request_body = {
        "markets": selection["clob_token_ids"],
        "start_ts": int(start.timestamp()),
        "end_ts": int(end.timestamp()),
        "interval": "all",
        "fidelity": 1,
    }
    encoded = json.dumps(request_body, separators=(",", ":")).encode()
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    (output / "request.json").write_bytes(encoded + b"\n")
    request = Request(URL, data=encoded, method="POST", headers={
        "User-Agent": "market-rsi-research/1.0", "Accept": "application/json",
        "Content-Type": "application/json",
    })
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        if response.status != 200:
            raise RuntimeError(f"Polymarket returned HTTP {response.status}")
    raw_path = output / "response.raw.json"; raw_path.write_bytes(raw)
    quality = validate_history(raw, selection["clob_token_ids"])
    result = {
        "schema": "polymarket_nfl_price_canary_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": URL,
        "selection_path": str(selection_path),
        "selection_sha256": sha(selection_path.read_bytes()),
        "game_master_path": str(game_master),
        "game_master_sha256": sha(game_master.read_bytes()),
        "canonical_game": {key: game[key] for key in (
            "nflverse_game_id", "sportradar_game_id", "game_date", "scheduled_utc",
            "home_team", "away_team", "split_role")},
        "request_sha256": sha(encoded),
        "response_sha256": sha(raw),
        "response_bytes": len(raw),
        "token_quality": quality,
        "source_kind": "historical indicative price series",
        "is_trade_tape": False,
        "is_historical_l2": False,
        "is_fill_evidence": False,
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
