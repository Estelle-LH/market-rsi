#!/usr/bin/env python3
"""Build deterministic dense-quote opened-Train data for the discovery canary."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path

from market_rsi import fresh_json
from polymarket_data import NS, build_event_catalog
from polymarket_objective_data import (
    ObjectiveMaterializationPolicy,
    materialize_objective_books,
)


def _iso(ns: int) -> str:
    return datetime.fromtimestamp(ns / NS, timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def build() -> dict:
    rows = []
    all_counts = {}
    for day in range(1, 5):
        base = int(datetime(2026, 9, day, 12, tzinfo=timezone.utc).timestamp()) * NS
        game_start = base + 2 * 60 * 60 * NS
        slug = f"objective-canary-game-{day}"
        event = {
            "observed_at": _iso(base - 600 * NS + 1_000_000),
            "request_start_ns": base - 600 * NS - 2_000_000,
            "receive_ns": base - 600 * NS,
            "event_id": slug,
            "slug": slug,
            "start_time": _iso(game_start),
            "game_id": f"venue-{slug}",
            "league": "mlb",
        }
        catalog, _ = build_event_catalog([event])
        books = []
        for second in range(0, 601, 2):
            # Stable local movement plus occasional real jumps; the controller
            # is not told which objective should handle this best.
            level = (0.42 + day * 0.02 + 0.00004 * second
                     + 0.003 * math.sin(second / 37)
                     + (0.012 if second >= 310 else 0.0))
            available = base + second * NS
            books.append({
                "observed_at": _iso(available + 1_000_000),
                "request_start_ns": available - 2_000_000,
                "receive_ns": available,
                "event_id": slug,
                "event_slug": slug,
                "market_slug": f"{slug}-moneyline",
                "http_status": 200,
                "state": "MARKET_STATE_OPEN",
                "qa_flags": [],
                "best_bid": max(0.01, level - 0.01),
                "best_ask": min(0.99, level + 0.01),
                "bid_qty_l1": 12 + (second % 11),
                "ask_qty_l1": 15 + ((second + day) % 13),
            })
        day_result = materialize_objective_books(
            books,
            catalog,
            f"{day}" * 64,
            ObjectiveMaterializationPolicy(max_pregame_lead_ns=3 * 60 * 60 * NS),
        )
        rows.extend(day_result["rows"])
        all_counts[str(day)] = day_result["counts"]
    return {
        "schema": "polymarket_objective_labels_v1",
        "rows": sorted(rows, key=lambda row: (row["decision_ns"], row["row_id"])),
        "raw_quote_cadence": {"seconds": 2, "deterministic_canary": True},
        "trade_stream_provenance": {"verified": False, "reason": "not supplied"},
        "resolution_stream_provenance": {"verified": False, "reason": "not supplied"},
        "canary_generation_counts": all_counts,
        "scientific_result": False,
        "dev_labels_used": False,
        "future_test_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build()
    fresh_json(args.output, result)
    print({"rows": len(result["rows"]), "output": str(args.output)})


if __name__ == "__main__":
    main()
