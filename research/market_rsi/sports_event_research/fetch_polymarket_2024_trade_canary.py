"""Fetch one deterministic 2024 NFL Train-candidate trade tape canary.

Selection is earliest mapped game by start time and event ID, never volume or
outcome. This checks source availability only; it does not admit training data.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from sports_event_research.fetch_polymarket_trade_canary import (
    SAFE_FIELDS, fetch_page, validate,
)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def choose(mapping: Path) -> dict:
    with Path(mapping).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("no mapped 2024 games")
    row = min(rows, key=lambda item: (item["event_start_utc"], item["polymarket_event_id"]))
    return selection_from_row(row, "earliest mapped 2024 NFL game by event start and event ID; no price, volume, outcome, or score consulted")


def selection_from_row(row: dict, rule: str) -> dict:
    tokens = json.loads(row["tokens_json"])
    if len(tokens) != 2 or not all(tokens) or not row["condition_id"]:
        raise ValueError("selected moneyline has no two outcome tokens")
    return {
        "selection_rule": rule,
        "event_id": row["polymarket_event_id"],
        "event_slug": row["event_slug"],
        "event_start_utc": row["event_start_utc"],
        "nflverse_game_id": row["nflverse_game_id"],
        "condition_id": row["condition_id"],
        "clob_token_ids": tokens,
        "slug_order": row["slug_order"],
    }


def fetch_selected(selection: dict, mapping: Path, output: Path,
                   timeout: float = 30.0) -> dict:
    mapping = Path(mapping).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "selection.json").write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")
    start = datetime.fromisoformat(selection["event_start_utc"].replace("Z", "+00:00"))
    lower = int((start - timedelta(days=7)).timestamp())
    upper = int((start + timedelta(days=1)).timestamp())
    trades: list[dict] = []
    receipts: list[dict] = []
    for page, offset in enumerate((0, 10000)):
        raw, url = fetch_page(selection["condition_id"], offset, lower, upper, timeout)
        raw_path = output / f"trades-page-{page}.raw.json"
        raw_path.write_bytes(raw)
        batch = json.loads(raw)
        if not isinstance(batch, list):
            raise ValueError("trade endpoint did not return a list")
        receipts.append({"url": url, "sha256": sha(raw_path), "bytes": len(raw),
                         "rows": len(batch)})
        trades.extend(batch)
        if len(batch) < 10000:
            break
    else:
        raise ValueError("trade canary reached 20000-row cap; no coverage claim")
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
    with safe_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAFE_FIELDS)
        writer.writeheader()
        writer.writerows(safe)
    manifest = {
        "schema": "polymarket_2024_nfl_trade_canary_manifest_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mapping_sha256": sha(mapping),
        "selection_sha256": sha(output / "selection.json"),
        "page_receipts": receipts,
        "retrieved_query_summary": summary,
        "frozen_window": {"start_timestamp": lower, "end_timestamp": upper, **window_summary},
        "safe_trade_window_sha256": sha(safe_path),
        "taker_only": True,
        "wallet_fields_in_safe_output": False,
        "trade_coverage_verified_for_season": False,
        "train_admitted": False,
        "scientific_score": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def fetch(mapping: Path, output: Path, timeout: float = 30.0) -> dict:
    """Run the one-game earliest-by-time canary."""
    mapping = Path(mapping).resolve()
    return fetch_selected(choose(mapping), mapping, output, timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    print(json.dumps(fetch(args.mapping, args.output, args.timeout), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
