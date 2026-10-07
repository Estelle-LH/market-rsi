"""Read-only, zero-fit feasibility audit of the already-opened 195-game Train source.

No labels, price changes, forecast errors, provider calls or new data acquisition.
Print aggregate evidence to stdout; never modify the source or any runtime ledger.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SOURCE_ROOT = Path("/Users/estelle/Library/Application Support/MarketRSI/"
                   "self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_window(times: list[int], endpoint: int, width: int = 30) -> int:
    """Strictly before the endpoint, including the left boundary."""
    return bisect_left(times, endpoint) - bisect_left(times, endpoint - width)


def market_tokens(raw: dict, receipt: dict) -> list[str]:
    markets = [m for m in raw["markets"] if str(m.get("id")) == receipt["market_id"]]
    if len(markets) != 1 or markets[0]["conditionId"] != receipt["condition_id"]:
        raise ValueError("selected market identity mismatch")
    tokens = markets[0]["clobTokenIds"]
    tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
    # Receipts can reorder token sets; outcome orientation comes from raw market order.
    if len(tokens) != 2 or len(set(tokens)) != 2 or set(tokens) != set(receipt["tokens"]):
        raise ValueError("selected market token-set mismatch")
    return tokens


def quantiles(values: list[int]) -> dict | None:
    return {str(q): float(np.quantile(values, q)) for q in (.5, .9, .99)} if values else None


def audit() -> dict:
    root = SOURCE_ROOT
    manifest = json.loads((root / "manifest.json").read_text())
    with (root / "cohort.csv").open() as stream:
        cohort = list(csv.DictReader(stream))
    if len(cohort) != 195 or len({g["game_date"] for g in cohort}) != 42:
        raise ValueError("opened cohort changed")
    if sha(root / "audit/per_game.json") != manifest["per_game_sha256"]:
        raise ValueError("per-game source audit hash mismatch")
    counts = Counter()
    filters = Counter()
    fields, receipt_fields, catalog_fields = set(), set(), set()
    ages, gaps, window_counts = [], [], []
    first_timestamp, last_timestamp = None, None
    play_fields, sides = set(), Counter()
    coverage = {h: {"anchors": 0, "forecastable": 0, "scorable": 0,
                    "missing_current": 0, "missing_future_after_current": 0,
                    "games": set(), "dates": set(), "weeks": set(), "per_game": []}
                for h in (60, 300)}
    for game in cohort:
        gid = game["game_id"]
        catalog = json.loads((root / "catalog" / f"{gid}.json").read_text())
        trade_receipt = json.loads((root / "trades" / gid / "manifest.json").read_text())
        trade_file = root / "trades" / gid / "trade_window.csv"
        raw_file = root / "catalog" / f"{gid}.raw.json.gz"
        if sha(trade_file) != trade_receipt["trade_window_sha256"] or sha(raw_file) != catalog["stored_sha256"]:
            raise ValueError(f"source hash mismatch: {gid}")
        raw_bytes = gzip.decompress(raw_file.read_bytes())
        if hashlib.sha256(raw_bytes).hexdigest() != catalog["raw_sha256"]:
            raise ValueError(f"raw catalog hash mismatch: {gid}")
        raw = json.loads(raw_bytes)
        tokens = market_tokens(raw, catalog)
        if set(tokens) != set(trade_receipt["tokens"]) or catalog["condition_id"] != trade_receipt["condition_id"]:
            raise ValueError(f"trade/catalog identity mismatch: {gid}")
        counts["receipt_token_order_differs_from_raw_market"] += int(tokens != catalog["tokens"])
        catalog_fields.update(k for m in raw["markets"] for k in m)
        receipt_fields.update(catalog)
        receipt_fields.update(json.loads((root / "pbp" / f"{gid}.json").read_text()))
        with (root / "plays" / f"{gid}.csv").open() as stream:
            plays = csv.DictReader(stream)
            play_fields.update(plays.fieldnames or [])
            for play in plays:
                counts["timed_play_rows"] += 1
                parsed = datetime.fromisoformat(play["time_utc"].replace("Z", "+00:00"))
                counts["play_time_without_timezone"] += int(parsed.tzinfo is None)
        for page in trade_receipt["raw_pages"]:
            filters["pages"] += 1
            filters["taker_only_true"] += int("taker_only=true" in page["url"])
            filters["filter_amount_0.01"] += int("filter_amount=0.01" in page["url"])
        start = int(datetime.fromisoformat(catalog["event_start_utc"]).timestamp())
        with trade_file.open() as stream:
            rows = list(csv.DictReader(stream))
        counts["rows"] += len(rows)
        fields.update(rows[0] if rows else [])
        seen, times, all_times = set(), [], []
        for row in rows:
            full = tuple(row.items())
            counts["exact_duplicate_rows"] += int(full in seen)
            seen.add(full)
            price, size, timestamp = float(row["price"]), float(row["size"]), float(row["timestamp"])
            time = int(timestamp)
            first_timestamp = time if first_timestamp is None else min(first_timestamp, time)
            last_timestamp = time if last_timestamp is None else max(last_timestamp, time)
            sides[row["side"]] += 1
            counts["outside_recorded_capture_window"] += int(not trade_receipt["window_start"] <= time <= trade_receipt["window_end"])
            counts["invalid_price"] += int(not math.isfinite(price) or not 0 <= price <= 1)
            counts["invalid_size"] += int(not math.isfinite(size) or size <= 0)
            counts["non_integer_timestamp"] += int(timestamp != time)
            counts["endpoint_price_0_or_1"] += int(price in (0, 1))
            counts["condition_mismatch"] += int(row["condition_id"] != catalog["condition_id"])
            counts["token_mismatch"] += int(row["token_id"] not in tokens)
            index = tokens.index(row["token_id"])
            counts["outcome_index_mismatch"] += int(int(row["outcome_index"]) != index)
            all_times.append(time)
            if index == 0:
                times.append(time)
        counts["files_ascending"] += int(all(a <= b for a, b in zip(all_times, all_times[1:])))
        counts["files_descending"] += int(all(a >= b for a, b in zip(all_times, all_times[1:])))
        times.sort()
        counts["token0_rows"] += len(times)
        tied = Counter(times)
        counts["token0_same_second_excess_rows"] += sum(n - 1 for n in tied.values())
        counts["token0_tied_seconds"] += sum(n > 1 for n in tied.values())
        in_game = sorted(set(t for t in times if start <= t < start + 7500))
        gaps.extend(b - a for a, b in zip(in_game, in_game[1:]))
        counts["token0_first_125min_trades"] += sum(start <= t < start + 7500 for t in times)
        for horizon, item in coverage.items():
            forecastable = scorable = 0
            for offset in range(600, 7201, 300):
                time = start + offset
                current, future = count_window(times, time), count_window(times, time + horizon)
                item["anchors"] += 1
                if not current:
                    item["missing_current"] += 1
                    continue
                forecastable += 1
                item["forecastable"] += 1
                if horizon == 300:
                    ages.append(time - times[bisect_left(times, time) - 1])
                    window_counts.append(current)
                if not future:
                    item["missing_future_after_current"] += 1
                    continue
                scorable += 1
                item["scorable"] += 1
                item["games"].add(gid)
                item["dates"].add(game["game_date"])
                item["weeks"].add(gid.split("_")[1])
            item["per_game"].append({"game_id": gid, "forecastable": forecastable, "scorable": scorable})
    dates = sorted({g["game_date"] for g in cohort})
    game_dates = {g["game_id"]: g["game_date"] for g in cohort}
    for item in coverage.values():
        item["chronological_blocks"] = []
        for index, selected_dates in enumerate([dates[:22]] + [dates[i:i + 5] for i in range(22, 42, 5)]):
            games = [g for g in item["per_game"] if game_dates[g["game_id"]] in selected_dates]
            item["chronological_blocks"].append({
                "block": "initial_fit" if index == 0 else f"check_{index}",
                "dates": selected_dates, "population_games": len(games),
                "forecastable": sum(g["forecastable"] for g in games),
                "scorable": sum(g["scorable"] for g in games),
                "scorable_games": sum(g["scorable"] > 0 for g in games),
            })
        for label in ("games", "dates", "weeks"):
            item["scorable_" + ("nfl_weeks" if label == "weeks" else label)] = len(item.pop(label))
        for label in ("forecastable", "scorable"):
            item["zero_" + label + "_games"] = [g["game_id"] for g in item["per_game"] if g[label] == 0]
            item[label + "_per_game_quantiles"] = quantiles([g[label] for g in item["per_game"]])
        del item["per_game"]
    return {"schema": "market_trade_price_feasibility_zero_fit_v1",
            "dataset_id": manifest["dataset_id"], "manifest_sha256": sha(root / "manifest.json"),
            "cohort_sha256": sha(root / "cohort.csv"), "population": len(cohort), "dates": 42,
            "nfl_weeks": len({g["game_id"].split("_")[1] for g in cohort}),
            "nfl_week_population_counts": dict(sorted(Counter(g["game_id"].split("_")[1]
                                                               for g in cohort).items())),
            "check_nfl_week_population_counts": dict(sorted(Counter(g["game_id"].split("_")[1]
                      for g in cohort if g["game_date"] in dates[22:]).items())),
            "date_list": dates, "trade_columns": sorted(fields),
            "catalog_market_columns": sorted(catalog_fields), "catalog_pbp_receipt_columns": sorted(receipt_fields),
            "page_filters": dict(filters), "quality_counts": dict(counts),
            "trade_side_counts": dict(sides), "play_columns": sorted(play_fields),
            "trade_timestamp_range_utc": [datetime.fromtimestamp(t, timezone.utc).isoformat()
                                          for t in (first_timestamp, last_timestamp)],
            "token0_unique_timestamp_gap_seconds_first_125min": quantiles(gaps),
            "latest_token0_trade_age_seconds_at_forecastable_anchor": quantiles(ages),
            "token0_trades_per_30s_current_window": quantiles(window_counts),
            "audited_window": {"anchor_offsets_seconds": [600, 7200], "stride_seconds": 300,
                               "price_window_seconds": 30, "same_token": "raw selected market clobTokenIds[0]",
                               "endpoint_rule": "[endpoint-30, endpoint)"},
            "coverage": {str(h): item for h, item in coverage.items()},
            "model_fits": 0, "forecast_metrics_computed": False, "source_modified": False}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
