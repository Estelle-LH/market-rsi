#!/usr/bin/env python3
"""Validate and normalize the bounded OpenMarket public sample.

The output is a source canary, not a formal Train/Dev dataset.  It proves that
we can acquire, verify, join and replay the published schema before considering
selected full-history partitions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from market_rsi import digest, file_hash, fresh_json


SCHEMA = "openmarket_public_sample_clean_canary_v1"
EXPECTED = {
    "binance_candles_15m.parquet": ("candle_start", 5),
    "binance_candles_1h.parquet": ("candle_start", 2),
    "binance_candles_1m.parquet": ("candle_start", 104),
    "binance_candles_1s.parquet": ("candle_start", 9),
    "binance_candles_5m.parquet": ("candle_start", 23),
    "binance_candles_5s.parquet": ("candle_start", 1),
    "binance_ticks_ms.parquet": ("id", 1044),
    "binance_trades.parquet": ("trade_id", 4249),
    "crossover_alerts.parquet": (None, 0),
    "lag_pairs_ms.parquet": ("id", 1769),
    "market_meta.parquet": ("market_slug", 146),
    "polymarket_ticks_ms.parquet": ("id", 2000),
}
TIMESTAMP = {
    "binance_candles_15m.parquet": "candle_start",
    "binance_candles_1h.parquet": "candle_start",
    "binance_candles_1m.parquet": "candle_start",
    "binance_candles_1s.parquet": "candle_start",
    "binance_candles_5m.parquet": "candle_start",
    "binance_candles_5s.parquet": "candle_start",
    "binance_ticks_ms.parquet": "source_ts_ms",
    "binance_trades.parquet": "trade_time",
    "lag_pairs_ms.parquet": "paired_at_ms",
    "polymarket_ticks_ms.parquet": "source_ts_ms",
}


def _revision(raw: Path) -> str:
    revisions = set()
    metadata = raw / ".cache" / "huggingface" / "download"
    for name in ["README.md", *EXPECTED]:
        path = metadata / f"{name}.metadata"
        if path.is_symlink() or not path.is_file():
            raise ValueError("Hugging Face revision metadata is missing")
        revision = path.read_text(encoding="utf-8").splitlines()[0].strip()
        if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            raise ValueError("invalid Hugging Face revision")
        revisions.add(revision)
    if len(revisions) != 1:
        raise ValueError("sample files came from different dataset revisions")
    return revisions.pop()


def _rows(table: pa.Table) -> list[dict]:
    return table.to_pylist()


def _utc_date(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date().isoformat()


def _finite_numeric(table: pa.Table) -> None:
    for field in table.schema:
        if pa.types.is_floating(field.type):
            for value in table[field.name].to_pylist():
                if value is not None and not math.isfinite(value):
                    raise ValueError(f"nonfinite value in {field.name}")


def _validate_table(name: str, table: pa.Table) -> dict:
    key, expected_rows = EXPECTED[name]
    if table.num_rows != expected_rows:
        raise ValueError(f"published sample row count changed for {name}")
    nulls = sum(column.null_count for column in table.columns)
    if nulls:
        raise ValueError(f"null values in {name}")
    _finite_numeric(table)
    rows = _rows(table)
    duplicates = 0
    if key is not None:
        values = [row[key] for row in rows]
        duplicates = len(values) - len(set(values))
        if duplicates:
            raise ValueError(f"duplicate primary keys in {name}")
    timestamp = TIMESTAMP.get(name)
    dates = sorted({_utc_date(row[timestamp]) for row in rows}) if rows and timestamp else []
    if timestamp:
        for row in rows:
            if row["date"] != _utc_date(row[timestamp]):
                raise ValueError(f"partition date does not match source timestamp in {name}")
    return {"rows": len(rows), "columns": table.column_names, "null_values": nulls,
            "duplicate_primary_keys": duplicates, "utc_dates": dates}


def _normalize(name: str, table: pa.Table) -> pa.Table:
    if name == "binance_trades.parquet":
        index = table.schema.get_field_index("is_buyer_maker")
        table = table.set_column(index, "is_buyer_maker",
                                 pa.array([bool(value) for value in table[index].to_pylist()]))
    if name == "polymarket_ticks_ms.parquet":
        index = table.schema.get_field_index("paired")
        table = table.set_column(index, "paired",
                                 pa.array([bool(value) for value in table[index].to_pylist()]))
        for column in ("side_label", "event_type"):
            index = table.schema.get_field_index(column)
            table = table.set_column(index, column,
                                     pa.array([str(value).lower() for value in table[index].to_pylist()]))
    if name == "lag_pairs_ms.parquet":
        index = table.schema.get_field_index("side_label")
        table = table.set_column(index, "side_label",
                                 pa.array([str(value).lower() for value in table[index].to_pylist()]))
    key = EXPECTED[name][0]
    return table.sort_by([(key, "ascending")]) if key and table.num_rows else table


def clean(raw: Path, output: Path) -> dict:
    raw, output = Path(raw).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError("real downloaded sample directory required")
    readme = raw / "README.md"
    if readme.is_symlink() or not readme.is_file():
        raise ValueError("dataset card required")
    text = readme.read_text(encoding="utf-8")
    if "license: apache-2.0" not in text or "Version v0.4.3-unified" not in text:
        raise ValueError("expected license and dataset version are not frozen")
    revision = _revision(raw)
    tables, audits = {}, {}
    for name in EXPECTED:
        path = raw / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing sample table {name}")
        table = pq.read_table(path)
        audits[name] = {**_validate_table(name, table), "raw_sha256": file_hash(path),
                        "raw_bytes": path.stat().st_size}
        tables[name] = table

    polymarket = _rows(tables["polymarket_ticks_ms.parquet"])
    binance = _rows(tables["binance_ticks_ms.parquet"])
    lags = _rows(tables["lag_pairs_ms.parquet"])
    metadata = _rows(tables["market_meta.parquet"])
    meta_by_market = {row["market_slug"]: row for row in metadata}
    if any(row["best_bid"] > row["best_ask"] or not 0 <= row["price"] <= 1
           or not 0 <= row["best_bid"] <= 1 or not 0 <= row["best_ask"] <= 1
           for row in polymarket):
        raise ValueError("invalid Polymarket price or crossed quote")
    if any(row["ingest_ts_ms"] < row["source_ts_ms"] for row in polymarket + binance):
        raise ValueError("negative ingest latency in sample")
    if any(abs(row["up_price"] + row["down_price"] - 1) > 1e-9 for row in metadata):
        raise ValueError("market metadata probabilities do not complement")
    if any(row["market_slug"] not in meta_by_market for row in polymarket + lags):
        raise ValueError("tick references unknown market metadata")
    for row in polymarket:
        meta = meta_by_market[row["market_slug"]]
        if row["asset_id"] not in {meta["up_token_id"], meta["down_token_id"]}:
            raise ValueError("tick asset does not match market metadata")
    binance_ids = {row["id"] for row in binance}
    polymarket_ids = {row["id"] for row in polymarket}
    if any(row["binance_tick_id"] not in binance_ids
           or row["polymarket_tick_id"] not in polymarket_ids
           or row["polymarket_source_ts_ms"] - row["binance_source_ts_ms"] != row["lead_lag_ms"]
           for row in lags):
        raise ValueError("lag-pair linkage or formula failed")

    output.mkdir(parents=True, mode=0o700)
    clean_dir = output / "clean"
    clean_dir.mkdir(mode=0o700)
    for name, table in tables.items():
        normalized = _normalize(name, table)
        target = clean_dir / name
        pq.write_table(normalized, target, compression="zstd")
        os.chmod(target, 0o600)
        audits[name]["clean_sha256"] = file_hash(target)
        audits[name]["clean_bytes"] = target.stat().st_size

    dates = sorted({_utc_date(row["source_ts_ms"]) for row in polymarket})
    active_markets = sorted({row["market_slug"] for row in polymarket})
    latency = sorted(row["ingest_ts_ms"] - row["source_ts_ms"] for row in polymarket)
    body = {
        "schema": SCHEMA,
        "source": {"dataset": "gregyoung14/openmarket-btc-polymarket",
                   "huggingface_revision": revision, "sample_split": "v0.1-sample",
                   "full_dataset_version_documented": "v0.4.3-unified",
                   "license": "apache-2.0", "dataset_card_sha256": file_hash(readme)},
        "tables": audits,
        "total_rows": sum(item["rows"] for item in audits.values()),
        "checks": {"nulls": "pass", "primary_key_duplicates": "pass",
                   "timestamp_partition_dates": "pass", "quote_bounds_and_order": "pass",
                   "market_and_token_linkage": "pass", "lag_pair_linkage": "pass",
                   "ingest_clock_nonnegative": "pass", "metadata_complements": "pass"},
        "sample_evidence": {"utc_dates": dates, "active_polymarket_markets": len(active_markets),
                            "polymarket_ticks": len(polymarket), "binance_ticks": len(binance),
                            "binance_trades": len(_rows(tables["binance_trades.parquet"])),
                            "ingest_latency_ms": {"minimum": latency[0],
                                                  "median": latency[len(latency) // 2],
                                                  "maximum": latency[-1]}},
        "canary_pass": True,
        "formal_dataset_ready": False,
        "why_not_formal": (
            "The public sample contains one UTC date and four active Polymarket markets. "
            "It verifies the data path but is not enough independent history for Train/Dev/Test."
        ),
        "full_download_authorized": False,
        "next_gate": "controller_selects_bounded_full-history_date partitions after comparing sources",
    }
    report = {**body, "report_sha256": digest(body)}
    fresh_json(output / "clean-data-report.json", report)
    os.chmod(output / "clean-data-report.json", 0o600)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(clean(args.raw, args.output), sort_keys=True))


if __name__ == "__main__":
    main()

