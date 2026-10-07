"""Frozen 300-second trade-VWAP task; no executable-price or live-availability claim."""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
import csv
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import tempfile

from experiments.nfl_ingame_trade_price_feasibility_audit import SOURCE_ROOT, market_tokens, sha

MANIFEST_SHA = "429a0ef100ade70f7e7b7f5862c39f42adffd7dcdaaddf35c73c88b60f80074f"
COHORT_SHA = "ba07b5535917f6ccfd4ddb5eadb53f6428b02bcc238595adac42894643d37885"
FEATURE_NAMES = ("p30", "p30_minus_vwap300", "p30_minus_vwap900",
                 "log_count30", "log_count300", "log_count900",
                 "log_size30", "log_size300", "log_size900",
                 "signed_size_fraction300", "signed_size_fraction900",
                 "latest_trade_age_seconds", "elapsed_seconds")


def _root(source_root, allow_test_paths):
    root = Path(source_root).resolve()
    fixture = root != SOURCE_ROOT.resolve()
    if fixture:
        temporary = Path(tempfile.gettempdir()).resolve()
        if not allow_test_paths or not root.is_relative_to(temporary) or root == temporary:
            raise ValueError("Only opened Train root or explicitly authorized temporary fixtures")
    return root, fixture


def _load_game(root, game):
    gid = game["game_id"]
    if not gid or "/" in gid or ".." in gid:
        raise ValueError("Invalid game identity")
    catalog_path = root / "catalog" / f"{gid}.json"
    trade_manifest = root / "trades" / gid / "manifest.json"
    catalog = json.loads(catalog_path.read_text())
    receipt = json.loads(trade_manifest.read_text())
    trade_file = trade_manifest.parent / "trade_window.csv"
    raw_file = catalog_path.with_suffix(".raw.json.gz")
    if sha(trade_file) != receipt["trade_window_sha256"] or sha(raw_file) != catalog["stored_sha256"]:
        raise ValueError(f"Source hash failure: {gid}")
    raw_bytes = gzip.decompress(raw_file.read_bytes())
    if hashlib.sha256(raw_bytes).hexdigest() != catalog["raw_sha256"]:
        raise ValueError(f"Raw catalog hash failure: {gid}")
    tokens = market_tokens(json.loads(raw_bytes), catalog)
    if (set(tokens) != set(receipt["tokens"]) or receipt["condition_id"] != catalog["condition_id"]
            or receipt["game_id"] != gid or catalog["game_id"] != gid
            or catalog["game_date"] != game["game_date"] or not receipt["complete"]
            or receipt.get("dev_final_opened", False)):
        raise ValueError(f"Receipt identity failure: {gid}")
    start_time = datetime.fromisoformat(catalog["event_start_utc"])
    if start_time.tzinfo is None or start_time.timestamp() != int(start_time.timestamp()):
        raise ValueError("Scheduled start requires integer timezone-aware seconds")
    selected, seen, count = [], set(), 0
    with trade_file.open() as stream:
        for trade in csv.DictReader(stream):
            count += 1
            identity = tuple(trade.items())
            timestamp, price, size = (float(trade[k]) for k in ("timestamp", "price", "size"))
            if (identity in seen or not all(math.isfinite(x) for x in (timestamp, price, size))
                    or timestamp != int(timestamp) or not 0 <= price <= 1 or size <= 0
                    or trade["side"] not in ("BUY", "SELL") or trade["token_id"] not in tokens
                    or trade["condition_id"] != catalog["condition_id"]
                    or trade["event_slug"] != game["event_slug"]
                    or int(trade["outcome_index"]) != tokens.index(trade["token_id"])
                    or not receipt["window_start"] <= timestamp <= receipt["window_end"]):
                raise ValueError(f"Invalid/duplicate trade or identity: {gid}")
            seen.add(identity)
            if trade["token_id"] == tokens[0]:
                selected.append((int(timestamp), price, size, 1 if trade["side"] == "BUY" else -1))
    if count != receipt["window_trade_rows"]:
        raise ValueError(f"Trade count failure: {gid}")
    selected.sort()
    sources = {"catalog_receipt_sha256": sha(catalog_path), "trade_receipt_sha256": sha(trade_manifest),
               "trade_sha256": sha(trade_file), "raw_catalog_stored_sha256": sha(raw_file),
               "raw_catalog_sha256": catalog["raw_sha256"], "token0": tokens[0]}
    return int(start_time.timestamp()), selected, sources


def _vwap(trades):
    return math.fsum(p * s for _, p, s, _ in trades) / math.fsum(s for _, _, s, _ in trades)


def anchor_row(game, start, trades, anchor):
    """Pure constructor. Equal-second trades are commutative; endpoint trades excluded."""
    times = [trade[0] for trade in trades]
    window = lambda end, width: trades[bisect_left(times, end - width):bisect_left(times, end)]
    past = window(anchor, 900)
    current = window(anchor, 30)
    future = window(anchor + 300, 30)
    elapsed = anchor - start
    row = {"row_id": f"{game['game_id']}:{anchor}", "game_id": game["game_id"],
           "game_date": game["game_date"], "game_week": game["game_id"].split("_")[1],
           "anchor_s": anchor, "elapsed_seconds": elapsed, "p_current": None, "label": None,
           "forecastable": bool(current), "reason": "NO_CURRENT_WINDOW_TRADE" if not current else None,
           "features": (), "history": tuple((ts - anchor, p, s, side) for ts, p, s, side in past)}
    if current:
        windows = [current, window(anchor, 300), past]
        sizes = [math.fsum(trade[2] for trade in w) for w in windows]
        p = _vwap(current)
        row["p_current"] = p
        row["features"] = (p, p - _vwap(windows[1]), p - _vwap(past),
                           *(math.log1p(len(w)) for w in windows), *(math.log1p(s) for s in sizes),
                           *(math.fsum(s * side for _, _, s, side in windows[i]) / sizes[i] for i in (1, 2)),
                           anchor - current[-1][0], elapsed)
        row["label"] = _vwap(future) - p if future else None
        row["reason"] = None if future else "NO_FUTURE_WINDOW_LABEL"
    return row


def chronological_folds(rows):
    dates = sorted({row["game_date"] for row in rows})
    if len(dates) != 42 or len({row["row_id"] for row in rows}) != len(rows):
        raise ValueError("Protocol requires 42 unique dates and unique row IDs")
    folds = []
    for first in range(22, 42, 5):
        block = [r for r in rows if r["game_date"] in dates[first:first + 5]]
        cutoff = min(r["anchor_s"] for r in block)
        fit = [r for r in rows if r["game_date"] in dates[:first] and r["label"] is not None
               and r["forecastable"] and r["anchor_s"] + 300 < cutoff]
        check = [r for r in block if r["forecastable"]]
        if not fit or not check:
            raise ValueError("Empty fit/check fold is a protocol failure")
        folds.append((fit, check))
    return folds


def fit_weights(rows):
    counts = Counter(r["game_id"] for r in rows)
    if not rows:
        raise ValueError("Empty fit rows")
    scale = len(rows) / len(counts)
    return [scale / counts[r["game_id"]] for r in rows]


def materialize(source_root=SOURCE_ROOT, *, allow_test_paths=False):
    root, fixture = _root(source_root, allow_test_paths)
    manifest = json.loads((root / "manifest.json").read_text())
    if (not fixture and (sha(root / "manifest.json") != MANIFEST_SHA or sha(root / "cohort.csv") != COHORT_SHA)
            or not manifest["complete"] or manifest["dev_final_opened"]):
        raise ValueError("Opened Train manifest boundary failure")
    if sha(root / "audit/per_game.json") != manifest["per_game_sha256"]:
        raise ValueError("Per-game source audit hash failure")
    with (root / "cohort.csv").open() as stream:
        cohort = list(csv.DictReader(stream))
    if (len({g["game_id"] for g in cohort}) != len(cohort) or not cohort
            or not fixture and (len(cohort) != 195 or len({g["game_date"] for g in cohort}) != 42)):
        raise ValueError("Cohort population failure")
    rows, sources, coverage = [], {}, []
    for game in cohort:
        start, trades, sources[game["game_id"]] = _load_game(root, game)
        anchors = [anchor_row(game, start, trades, start + offset) for offset in range(600, 7201, 300)]
        rows.extend(anchors)
        coverage.append({"game_id": game["game_id"], "game_date": game["game_date"],
                         "game_week": game["game_id"].split("_")[1], "anchors": len(anchors),
                         "forecastable": sum(r["forecastable"] for r in anchors),
                         "scorable": sum(r["label"] is not None for r in anchors)})
    rows.sort(key=lambda r: (r["game_date"], r["game_id"], r["anchor_s"]))
    metadata = {"schema": "market_trade_vwap300_materialization_v1", "test_fixture": fixture,
                "task_id": "MarketTradeVWAPChange300sTrainDiagnostic-v1", "population": len(cohort),
                "source_root": str(root), "manifest_sha256": sha(root / "manifest.json"),
                "cohort_sha256": sha(root / "cohort.csv"), "source_receipts": sources, "coverage": coverage,
                "anchors": len(rows), "forecastable": sum(r["forecastable"] for r in rows),
                "scorable": sum(r["label"] is not None for r in rows), "feature_names": FEATURE_NAMES,
                "reasons": dict(Counter(r["reason"] for r in rows if r["reason"])),
                "claim": "Historical filtered trade-price diagnostic; event time is not receipt availability"}
    if not fixture:
        folds = chronological_folds(rows)
        observed = (len(rows), metadata["forecastable"], metadata["scorable"], len(folds[0][0]),
                    sum(len(c) for _, c in folds), sum(r["label"] is not None for _, c in folds for r in c))
        if observed != (4485, 2721, 1848, 857, 1356, 991):
            raise ValueError(f"Frozen availability mask changed: {observed}")
    return rows, metadata
