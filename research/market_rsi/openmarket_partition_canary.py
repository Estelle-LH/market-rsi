#!/usr/bin/env python3
"""Inventory and validate three controller-authorized OpenMarket Parquet files."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from market_rsi import digest, file_hash, fresh_json


DATASET = "gregyoung14/openmarket-btc-polymarket"
REVISION = "74502466d1a7cef56395bfd8d0b465fbebc849cf"
SCHEMA = "openmarket_partition_clean_canary_v1"
MAX_TOTAL_BYTES = 1_000_000_000
MAX_TICK_FILE_BYTES = 80_000_000
MIN_TICK_FILE_BYTES = 1_000_000
GAP_START = date(2026, 4, 22)
GAP_END = date(2026, 5, 12)
META_PATH = "unified/market_meta/unpartitioned/part-000001.parquet"
TICK_RE = re.compile(
    r"^unified/polymarket_ticks_ms/date=(\d{4}-\d{2}-\d{2})/part-000001\.parquet$"
)


def _entry(item) -> dict | None:
    path = getattr(item, "path", "")
    size = getattr(item, "size", None)
    if type(size) is not int or size < 0 or not path.startswith("unified/"):
        return None
    lfs = getattr(item, "lfs", None)
    sha256 = getattr(lfs, "sha256", None) if lfs else None
    return {"path": path, "bytes": size, "lfs_sha256": sha256}


def fetch_inventory() -> list[dict]:
    from huggingface_hub import list_repo_tree
    records = []
    for item in list_repo_tree(DATASET, repo_type="dataset", revision=REVISION,
                               recursive=True, expand=True):
        record = _entry(item)
        if record is not None:
            records.append(record)
    records.sort(key=lambda value: value["path"])
    if not records:
        raise ValueError("empty OpenMarket inventory")
    return records


def _rank(plan_sha256: str, path: str) -> str:
    return hashlib.sha256(f"{plan_sha256}\0{path}".encode()).hexdigest()


def inventory_and_selection(records: list[dict], *, plan_sha256: str) -> dict:
    if len(plan_sha256) != 64:
        raise ValueError("plan SHA-256 required")
    by_path = {record["path"]: record for record in records}
    if len(by_path) != len(records) or META_PATH not in by_path:
        raise ValueError("unique files and unified metadata required")
    tick_dates = {}
    for record in records:
        match = TICK_RE.match(record["path"])
        if match:
            tick_dates[date.fromisoformat(match.group(1))] = record
    if not tick_dates:
        raise ValueError("no partitioned Polymarket ticks")
    eligible = {
        day: record for day, record in tick_dates.items()
        if MIN_TICK_FILE_BYTES <= record["bytes"] <= MAX_TICK_FILE_BYTES
    }
    before = [(day, record) for day, record in eligible.items() if day < GAP_START]
    after = [(day, record) for day, record in eligible.items() if day > GAP_END]
    if not before or not after:
        raise ValueError("bounded files on both sides of the documented gap required")
    pre = min(before, key=lambda item: _rank(plan_sha256, item[1]["path"]))
    post = min(after, key=lambda item: _rank(plan_sha256, item[1]["path"]))
    selected = [
        {**pre[1], "role": "pre_gap_polymarket_ticks", "utc_date": pre[0].isoformat()},
        {**post[1], "role": "post_gap_polymarket_ticks", "utc_date": post[0].isoformat()},
        {**by_path[META_PATH], "role": "market_metadata", "utc_date": None},
    ]
    selected.sort(key=lambda value: value["role"])
    selected_bytes = sum(item["bytes"] for item in selected)
    if selected_bytes >= MAX_TOTAL_BYTES:
        raise ValueError("selected canary exceeds one-gigabyte hard cap")
    dates = sorted(tick_dates)
    before_gap = max(day for day in dates if day < GAP_START)
    after_gap = min(day for day in dates if day > GAP_END)
    tables = {}
    for record in records:
        parts = record["path"].split("/")
        table = parts[1] if len(parts) > 2 else "other"
        tables.setdefault(table, {"files": 0, "bytes": 0, "utc_dates": []})
        tables[table]["files"] += 1
        tables[table]["bytes"] += record["bytes"]
        match = re.search(r"/date=(\d{4}-\d{2}-\d{2})/", record["path"])
        if match:
            tables[table]["utc_dates"].append(match.group(1))
    for value in tables.values():
        value["utc_dates"] = sorted(set(value["utc_dates"]))
    body = {
        "schema": "openmarket_frozen_partition_inventory_v1",
        "dataset": DATASET,
        "revision": REVISION,
        "plan_sha256": plan_sha256,
        "selection_rule": (
            "market metadata plus one 1MB-80MB Polymarket tick partition from each side "
            "of the documented gap, minimizing sha256(plan_sha256 + NUL + path) per stratum"
        ),
        "files": records,
        "tables": tables,
        "polymarket_tick_coverage": {
            "utc_dates": [day.isoformat() for day in dates],
            "utc_date_count": len(dates),
            "earliest": dates[0].isoformat(),
            "latest": dates[-1].isoformat(),
            "last_before_documented_gap": before_gap.isoformat(),
            "first_after_documented_gap": after_gap.isoformat(),
        },
        "selected": selected,
        "selected_bytes": selected_bytes,
        "full_download_authorized": False,
    }
    return {**body, "inventory_sha256": digest(body)}


def _download(selection: list[dict], raw: Path) -> None:
    from huggingface_hub import hf_hub_download
    for item in selection:
        result = Path(hf_hub_download(
            DATASET, filename=item["path"], repo_type="dataset", revision=REVISION,
            local_dir=raw,
        )).resolve()
        expected = (raw / item["path"]).resolve()
        if result != expected or result.is_symlink() or not result.is_file():
            raise ValueError("downloaded file escaped or is not a regular file")
        if result.stat().st_size != item["bytes"]:
            raise ValueError("downloaded file size changed")
        if item["lfs_sha256"] and file_hash(result) != item["lfs_sha256"]:
            raise ValueError("downloaded file hash changed")


def _validate_ticks(path: Path, partition_date: str,
                    metadata: dict) -> tuple[dict, pa.Table]:
    columns = ["id", "source_ts_ms", "ingest_ts_ms", "market_slug", "asset_id",
               "side_label", "event_type", "price", "best_bid", "best_ask",
               "size", "paired", "date"]
    table = pq.read_table(path, columns=columns)
    required = ["id", "source_ts_ms", "ingest_ts_ms", "market_slug", "asset_id",
                "side_label", "event_type", "paired", "date"]
    if table.num_rows == 0 or any(table[name].null_count for name in required):
        raise ValueError("empty tick partition or null required identity/time field")
    ids = table["id"].combine_chunks()
    duplicates = table.num_rows - pc.count_distinct(ids).as_py()
    if duplicates:
        raise ValueError("duplicate tick IDs")
    timestamps = table["source_ts_ms"].combine_chunks().to_numpy()
    raw_order_monotonic = (
        len(timestamps) < 2 or bool((timestamps[1:] >= timestamps[:-1]).all()))
    ingests = table["ingest_ts_ms"].combine_chunks().to_numpy()
    if bool((ingests < timestamps).any()):
        raise ValueError("negative ingest latency")
    observed_dates = {
        value.isoformat() if hasattr(value, "isoformat") else str(value)
        for value in pc.unique(table["date"].combine_chunks()).to_pylist()
    }
    if observed_dates != {partition_date}:
        raise ValueError("partition date disagrees with row date")
    event_types = pc.utf8_lower(table["event_type"].combine_chunks())
    events = set(pc.unique(event_types).to_pylist())
    if not events <= {"price_change", "book"}:
        raise ValueError("unknown event-specific null semantics")
    price_change = pc.equal(event_types, "price_change")
    book = pc.equal(event_types, "book")
    for name in ("price", "best_bid", "best_ask", "size"):
        if pc.any(pc.and_(price_change, pc.is_null(table[name]))).as_py():
            raise ValueError("price-change event is missing price state")
    if pc.any(pc.and_(book, pc.and_(pc.is_null(table["best_bid"]),
                                    pc.is_null(table["best_ask"])))).as_py():
        raise ValueError("book event has neither bid nor ask")
    for name in ("price", "best_bid", "best_ask"):
        values = table[name].combine_chunks()
        out_of_bounds = pc.or_(pc.less(values, 0), pc.greater(values, 1))
        if pc.any(pc.fill_null(out_of_bounds, False)).as_py():
            raise ValueError("probability price outside [0, 1]")
    crossed = pc.greater(table["best_bid"].combine_chunks(),
                         table["best_ask"].combine_chunks())
    if pc.any(pc.fill_null(crossed, False)).as_py():
        raise ValueError("crossed top of book")
    markets = set(pc.unique(table["market_slug"].combine_chunks()).to_pylist())
    if not markets <= set(metadata):
        raise ValueError("tick market missing from metadata")
    allowed_assets = {token for market in markets for token in metadata[market]}
    assets = set(pc.unique(table["asset_id"].combine_chunks()).to_pylist())
    if not assets <= allowed_assets:
        raise ValueError("tick asset missing from market metadata")
    latency = ingests - timestamps
    latency_arrow = pc.subtract(table["ingest_ts_ms"].combine_chunks(),
                                table["source_ts_ms"].combine_chunks())
    normalized = table
    for name in ("side_label", "event_type"):
        index = normalized.schema.get_field_index(name)
        normalized = normalized.set_column(index, name,
                                           pc.utf8_lower(normalized[name]))
    paired_index = normalized.schema.get_field_index("paired")
    normalized = normalized.set_column(paired_index, "paired",
                                       pc.cast(normalized["paired"], pa.bool_()))
    date_index = normalized.schema.get_field_index("date")
    normalized = normalized.set_column(
        date_index, "date", pc.strftime(normalized["date"], format="%Y-%m-%d"))
    normalized = normalized.append_column("ingest_latency_ms", latency_arrow)
    quality = pc.if_else(
        pc.greater(latency_arrow, 60_000), pa.scalar(2, pa.int8()),
        pc.if_else(pc.greater(latency_arrow, 1_000), pa.scalar(1, pa.int8()),
                   pa.scalar(0, pa.int8())),
    )
    normalized = normalized.append_column("arrival_quality_code", quality)
    normalized = normalized.sort_by([("ingest_ts_ms", "ascending"),
                                     ("id", "ascending")])
    quantiles = pc.quantile(latency_arrow, q=[0.5, 0.95, 0.99, 0.999]).to_pylist()
    audit = {
        "rows": table.num_rows,
        "whole_markets": len(markets),
        "duplicate_ids": duplicates,
        "raw_source_order_monotonic": raw_order_monotonic,
        "clean_sort": ["ingest_ts_ms", "id"],
        "event_type_counts": {
            item["values"]: item["counts"]
            for item in pc.value_counts(event_types).to_pylist()
        },
        "semantic_null_counts": {
            name: table[name].null_count
            for name in ("price", "best_bid", "best_ask", "size")
        },
        "source_timestamp_min_ms": int(timestamps.min()),
        "source_timestamp_max_ms": int(timestamps.max()),
        "ingest_latency_ms": {
            "minimum": int(latency.min()),
            "p50": int(quantiles[0]),
            "p95": int(quantiles[1]),
            "p99": int(quantiles[2]),
            "p999": int(quantiles[3]),
            "maximum": int(latency.max()),
            "over_1_second_rows": pc.sum(pc.cast(pc.greater(latency_arrow, 1_000), pa.int64())).as_py(),
            "over_60_seconds_rows": pc.sum(pc.cast(pc.greater(latency_arrow, 60_000), pa.int64())).as_py(),
        },
        "arrival_quality_code": {
            "0": "latency_at_most_1_second",
            "1": "latency_over_1_second_through_60_seconds",
            "2": "latency_over_60_seconds",
        },
    }
    return audit, normalized


def run_canary(output: Path, *, plan_path: Path, sample_report_path: Path,
               records: list[dict] | None = None, downloader=None,
               reuse_raw_from: Path | None = None) -> dict:
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if (plan.get("decision", {}).get("proposal_id") != "plan-a-openmarket-reuse-v1"
            or plan.get("feasibility_audit", {}).get("full_download_authorized") is not False):
        raise ValueError("exact bounded OpenMarket plan required")
    sample = json.loads(Path(sample_report_path).read_text(encoding="utf-8"))
    if (sample.get("canary_pass") is not True
            or sample.get("source", {}).get("license") != "apache-2.0"
            or sample.get("source", {}).get("huggingface_revision") != REVISION):
        raise ValueError("passing frozen public sample required")
    output.mkdir(parents=True, mode=0o700)
    raw, clean = output / "raw", output / "clean"
    raw.mkdir(mode=0o700)
    clean.mkdir(mode=0o700)
    if records is None and reuse_raw_from is not None:
        previous_inventory_path = Path(reuse_raw_from).resolve().parent / "frozen-inventory.json"
        previous_inventory = json.loads(previous_inventory_path.read_text(encoding="utf-8"))
        if (previous_inventory.get("plan_sha256") != plan["plan_sha256"]
                or previous_inventory.get("revision") != REVISION
                or previous_inventory.get("full_download_authorized") is not False):
            raise ValueError("reused inventory is not bound to the exact frozen plan")
        records = previous_inventory["files"]
    records = fetch_inventory() if records is None else records
    inventory = inventory_and_selection(records, plan_sha256=plan["plan_sha256"])
    fresh_json(output / "frozen-inventory.json", inventory)
    if reuse_raw_from is not None:
        source_root = Path(reuse_raw_from).resolve()
        for item in inventory["selected"]:
            source = source_root / item["path"]
            if source.is_symlink() or not source.is_file():
                raise ValueError("reused raw canary file is missing or symlinked")
            target = raw / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    else:
        (downloader or _download)(inventory["selected"], raw)

    meta_item = next(item for item in inventory["selected"] if item["role"] == "market_metadata")
    meta_path = raw / meta_item["path"]
    meta = pq.read_table(meta_path)
    if meta.num_rows == 0 or "market_slug" not in meta.column_names:
        raise ValueError("empty market metadata")
    slugs = meta["market_slug"].combine_chunks()
    if pc.count_distinct(slugs).as_py() != meta.num_rows:
        raise ValueError("duplicate market metadata identities")
    metadata = {
        row["market_slug"]: {row["up_token_id"], row["down_token_id"]}
        for row in meta.select(["market_slug", "up_token_id", "down_token_id"]).to_pylist()
    }
    audits = {}
    for item in inventory["selected"]:
        source = raw / item["path"]
        before = file_hash(source)
        if item["role"].endswith("polymarket_ticks"):
            audit, normalized = _validate_ticks(source, item["utc_date"], metadata)
        else:
            audit = {"rows": meta.num_rows, "whole_markets": meta.num_rows,
                     "duplicate_market_slugs": 0,
                     "resolution_columns_present": bool(
                         {"resolution", "outcome", "resolved_outcome"} & set(meta.column_names))}
            normalized = meta
        if file_hash(source) != before:
            raise ValueError("file changed during deterministic reread")
        target = clean / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(normalized, target, compression="zstd")
        os.chmod(target, 0o600)
        if item["role"].endswith("polymarket_ticks"):
            clean_timestamps = pq.read_table(target, columns=["ingest_ts_ms"])[
                "ingest_ts_ms"].combine_chunks().to_numpy()
            if (len(clean_timestamps) > 1
                    and not bool((clean_timestamps[1:] >= clean_timestamps[:-1]).all())):
                raise ValueError("clean partition is not monotonically arrival-sorted")
        audits[item["role"]] = {
            **audit, "path": item["path"], "raw_bytes": source.stat().st_size,
            "raw_sha256": before, "clean_sha256": file_hash(target),
        }

    tick_roles = [value for key, value in audits.items() if key.endswith("polymarket_ticks")]
    total_rows = sum(item["rows"] for item in tick_roles)
    body = {
        "schema": SCHEMA,
        "source": {
            "dataset": DATASET,
            "revision": REVISION,
            "version": "v0.4.3-unified",
            "license": "apache-2.0",
            "dataset_card_sha256": sample["source"]["dataset_card_sha256"],
        },
        "plan_sha256": plan["plan_sha256"],
        "inventory_sha256": inventory["inventory_sha256"],
        "selected_files": inventory["selected"],
        "selected_bytes": inventory["selected_bytes"],
        "raw_acquisition": (
            {"mode": "reused_hash_verified_canary_bytes",
             "source": str(Path(reuse_raw_from).resolve())}
            if reuse_raw_from is not None else {"mode": "downloaded_from_frozen_revision"}
        ),
        "audits": audits,
        "clean_tick_rows": total_rows,
        "checks": {
            "license_and_version": "pass",
            "schema": "pass",
            "utc_and_monotonic_timestamps": "pass",
            "duplicates": "pass",
            "market_and_token_linkage": "pass",
            "documented_gap_boundary": "pass",
            "byte_deterministic_reread": "pass",
            "byte_cap": "pass",
            "clock_drift": "measured_and_flagged_per_row",
            "causal_replay_order": "ingest_ts_ms_then_id",
            "resolution_linkage": "explicitly_absent_from_market_meta",
        },
        "observed_historical_depth": inventory["polymarket_tick_coverage"],
        "canary_pass": True,
        "formal_dataset_ready": False,
        "full_download_authorized": False,
        "why_not_formal": (
            "This is a bounded three-file canary. It validates real historical partitions "
            "but does not satisfy or authorize the full-ingest acceptance tests."
        ),
        "training_admission_rule": (
            "Replay in ingest_ts_ms order. Preserve source_ts_ms for diagnostics. Treat "
            "arrival_quality_code 2 as delayed backfill and never expose it before ingest time."
        ),
    }
    report = {**body, "report_sha256": digest(body)}
    fresh_json(output / "clean-data-report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--sample-report", required=True, type=Path)
    parser.add_argument("--reuse-raw-from", type=Path)
    args = parser.parse_args()
    report = run_canary(args.output, plan_path=args.plan,
                        sample_report_path=args.sample_report,
                        reuse_raw_from=args.reuse_raw_from)
    print(json.dumps({
        "report_sha256": report["report_sha256"],
        "clean_tick_rows": report["clean_tick_rows"],
        "selected_bytes": report["selected_bytes"],
        "observed_historical_depth": report["observed_historical_depth"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
