#!/usr/bin/env python3
"""Read-only clock/coverage audit of hash-verified historical source files.

No labels, model fitting, row removal, relabeling or admission decisions. A
calendar partition is not a full session, and a finalized candle is not known
at its start. Reports describe recorded clocks; they do not certify that a
publisher timestamp represents actual exchange/collector availability.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from bounded_historical_ingest import verify_file
from historical_ingest_controller import _signed
from market_rsi import canonical, file_hash, fresh_json, load_json


DAY_MS = 86_400_000
MIN_CLOCK_MS = 946_684_800_000  # 2000-01-01: detect seconds/us mistaken for ms.
MAX_CLOCK_MS = 4_102_444_800_000  # 2100-01-01; not a train/eval cutoff.
CANDLES = {f"binance_candles_{k}": v for k, v in
           {"1s": 1000, "5s": 5000, "1m": 60_000, "5m": 300_000,
            "15m": 900_000, "1h": 3_600_000}.items()}
STREAMS = {"polymarket_ticks_ms": ("source_ts_ms", "ingest_ts_ms"),
           "binance_ticks_ms": ("source_ts_ms", "ingest_ts_ms"),
           "binance_trades": ("trade_time", "received_at")}


def partition(item):
    path = PurePosixPath(item["path"])
    if (path.is_absolute() or ".." in path.parts or len(path.parts) != 4
            or path.parts[0] != "unified" or not path.parts[2].startswith("date=")):
        raise ValueError("unsupported partition path")
    day = date.fromisoformat(path.parts[2][5:])
    start = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp() * 1000)
    return path.parts[1], day, start


def coverage(bins: set[int], *, day_start: int, width_ms: int) -> dict:
    first, n = day_start // width_ms, DAY_MS // width_ms
    mask = np.zeros(n, dtype=bool)
    inside = [v - first for v in bins if first <= v < first + n]
    mask[inside] = True
    ranges, longest, gap = [], 0, 0
    begin = None
    for i, occupied in enumerate([*mask, False]):
        if occupied:
            gap = 0
            if begin is None:
                begin = i
        else:
            if i < n:
                gap += 1
                longest = max(longest, gap)
            if begin is not None:
                ranges.append([day_start + begin * width_ms, day_start + i * width_ms])
                begin = None
    return {"bin_width_ms": width_ms, "occupied_bins": int(mask.sum()),
            "possible_bins_in_partition_day": n, "occupied_fraction": float(mask.mean()),
            "longest_empty_run_ms_including_day_edges": longest * width_ms,
            "occupied_ranges_ms_half_open": ranges,
            "observed_bins_outside_partition_day": len(bins) - len(inside),
            "continuous_quote_or_full_session_coverage_proven": False}


def audit_file(path: Path, item: dict, *, batch_size=100_000) -> dict:
    stream, day, day_start = partition(item)
    candle = stream in CANDLES
    if not candle and stream not in STREAMS:
        raise ValueError("stream has no clock audit contract")
    verify_file(path, item)
    parquet = pq.ParquetFile(path)
    event, receipt = ("candle_start", "created_at") if candle else STREAMS[stream]
    clocks = [event, receipt] + (["candle_end"] if candle else [])
    if stream == "binance_ticks_ms":
        clocks.append("trade_time_ms")
    if not set(clocks) <= set(parquet.schema_arrow.names):
        raise ValueError("required clock columns missing")
    inline_date = "date" in parquet.schema_arrow.names
    for name in clocks:
        if not pa.types.is_integer(parquet.schema_arrow.field(name).type):
            raise ValueError("clock must be integer epoch milliseconds: " + name)
    if inline_date and not pa.types.is_date32(parquet.schema_arrow.field("date").type):
        raise ValueError("partition date must be date32")
    # Candles are binned at their native interval. Event streams at one minute.
    width = CANDLES[stream] if candle else 60_000
    bins = {name: set() for name in (event, receipt)}
    counts = Counter()
    stats = {name: {"min_ms": None, "max_ms": None,
                    "raw_order_reversals": 0, "adjacent_equal_timestamps": 0}
             for name in clocks}
    previous, observed_dates = {}, set()
    lag_min = lag_max = None
    # Competing metadata hypotheses, not a silently chosen partition timezone.
    # New York explains observed 05:00 winter / 04:00 summer UTC boundaries.
    # Some files may still be UTC; count every row under both conventions.
    ny = ZoneInfo("America/New_York")
    ny_start = int(datetime.combine(day, datetime.min.time(), ny).timestamp() * 1000)
    ny_end = int(datetime.combine(day + timedelta(days=1), datetime.min.time(), ny).timestamp() * 1000)
    for batch in parquet.iter_batches(batch_size=batch_size, columns=clocks + (["date"] if inline_date else [])):
        counts["rows"] += batch.num_rows
        arrays = {}
        for name in clocks:
            column = batch.column(name)
            if column.null_count:
                raise ValueError("null clock field: " + name)
            values = column.to_numpy(zero_copy_only=False)
            if np.any((values < MIN_CLOCK_MS) | (values >= MAX_CLOCK_MS)):
                raise ValueError("clock outside epoch-ms sanity range: " + name)
            arrays[name] = values
            s = stats[name]
            lo, hi = int(values.min()), int(values.max())
            s["min_ms"] = lo if s["min_ms"] is None else min(s["min_ms"], lo)
            s["max_ms"] = hi if s["max_ms"] is None else max(s["max_ms"], hi)
            s["raw_order_reversals"] += int(np.sum(values[1:] < values[:-1]))
            s["adjacent_equal_timestamps"] += int(np.sum(values[1:] == values[:-1]))
            if name in previous:
                s["raw_order_reversals"] += int(values[0] < previous[name])
                s["adjacent_equal_timestamps"] += int(values[0] == previous[name])
            previous[name] = values[-1]
            if name in bins:
                bins[name].update(int(v) for v in np.unique(values // width))
        if inline_date:
            day_array = batch.column("date")
            if day_array.null_count:
                raise ValueError("null partition date")
            observed_dates.update(str(v) for v in pc.unique(day_array).to_pylist())
        e, r = arrays[event], arrays[receipt]
        counts["event_time_outside_partition_day_rows"] += int(np.sum(
            (e < day_start) | (e >= day_start + DAY_MS)))
        counts["event_time_outside_new_york_partition_hypothesis_rows"] += int(np.sum(
            (e < ny_start) | (e >= ny_end)))
        # created_at is often a historical backfill time, NOT necessarily
        # a trustworthy first-available timestamp. Describe, never overwrite.
        lag = r - (arrays["candle_end"] + 1 if candle else e)
        lag_min = int(lag.min()) if lag_min is None else min(lag_min, int(lag.min()))
        lag_max = int(lag.max()) if lag_max is None else max(lag_max, int(lag.max()))
        counts["receipt_before_event_or_candle_close_rows"] += int(np.sum(lag < 0))
        for threshold, label in [(1000, "1s"), (60_000, "1m"),
                                 (3_600_000, "1h"), (DAY_MS, "1d")]:
            counts["receipt_lag_over_" + label + "_rows"] += int(np.sum(lag > threshold))
        if candle:
            counts["candle_duration_mismatch_rows"] += int(np.sum(
                arrays["candle_end"] - e + 1 != CANDLES[stream]))
            counts["candle_start_not_interval_aligned_rows"] += int(np.sum(e % width != 0))
        elif stream == "binance_ticks_ms":
            counts["trade_time_differs_from_source_time_rows"] += int(np.sum(
                arrays["trade_time_ms"] != e))
    if not counts["rows"] or counts["rows"] != parquet.metadata.num_rows:
        raise ValueError("empty or inconsistent decoded row count")
    verify_file(path, item)
    flags = []
    if (inline_date and observed_dates != {day.isoformat()}) or counts["event_time_outside_partition_day_rows"]:
        flags.append("partition_clock_mismatch")
    if not inline_date:
        flags.append("partition_date_only_in_path_not_inline")
    if counts["receipt_before_event_or_candle_close_rows"]:
        flags.append("receipt_precedes_event_or_final_candle_close")
    if counts["candle_duration_mismatch_rows"] or counts["candle_start_not_interval_aligned_rows"]:
        flags.append("candle_interval_mismatch")
    if counts["receipt_lag_over_1d_rows"]:
        flags.append("recorded_receipt_over_one_day_late")
    if stats[receipt]["raw_order_reversals"]:
        flags.append("raw_file_not_in_recorded_receipt_order")
    return {"schema": "historical_stream_clock_qa_v1", "path": item["path"],
            "sha256": item["lfs_sha256"], "stream": stream, "day": day.isoformat(),
            "counts": dict(counts), "clock_fields": stats, "flags": flags,
            "lag_reference": "candle_end_plus_1ms" if candle else event,
            "recorded_receipt_minus_reference_ms": {"min": lag_min, "max": lag_max},
            "coverage": {name: coverage(values, day_start=day_start, width_ms=width)
                         for name, values in bins.items()},
            "clock_semantics": "publisher_fields_only_deployment_provenance_unverified",
            "partition_clock_hypotheses": {
                "UTC": [day_start, day_start + DAY_MS], "America/New_York": [ny_start, ny_end],
                "timezone_selected": False, "existing_coverage_assumption": "UTC",
                "date_column_present": inline_date},
            "candle_policy": "never_use_final_ohlcv_at_candle_start" if candle else None,
            "row_order": "raw_ordinal_preserved_no_sort_or_dedup_applied",
            "label_values_opened": False, "train_dev_selected": False,
            "raw_unchanged": True, "training_admitted": False,
            "remaining": ["source_clock_provenance", "global_key_uniqueness",
                          "per_market_quote_state_coverage", "numeric_stream_semantics",
                          "controller_objective_and_prospective_split"]}


def run(ingest_root: Path, output: Path, *, tables=None) -> dict:
    """Freeze completed QA receipts at invocation; ignore unfinished files."""
    allowed = set(CANDLES) | set(STREAMS)
    selected_tables = set(tables or allowed)
    if not selected_tables or not selected_tables <= allowed:
        raise ValueError("unsupported tables")
    plan = load_json(ingest_root / "frozen-plan.json")
    _signed(plan, "plan_sha256")
    if load_json(ingest_root / "claim.json")["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("ingest claim does not match frozen plan")
    ready = []
    for item in plan["audit"]["selected_files"]:
        if item["path"].split("/")[1] not in selected_tables:
            continue
        partition(item)
        receipt = ingest_root / "qa" / (item["path"].replace("/", "__") + ".json")
        if not receipt.is_file():
            continue
        qa = load_json(receipt)
        if qa["sha256"] != item["lfs_sha256"]:
            raise ValueError("completed QA receipt hash mismatch")
        ready.append({"item": item, "initial_qa_sha256": file_hash(receipt),
                      "initial_quarantine_required": qa.get("quarantine_required", False)})
    if not ready:
        raise ValueError("no completed files available")
    output.mkdir(exist_ok=False, parents=True)
    fresh_json(output / "snapshot.json", {"plan_sha256": plan["plan_sha256"],
        "code_sha256": file_hash(__file__), "ingest_root": str(ingest_root.absolute()),
        "tables": sorted(selected_tables), "files": ready,
        "no_future_or_label_selection": True})
    (output / "files").mkdir()
    summaries, failures = [], []
    for entry in ready:
        item = entry["item"]
        try:
            report = audit_file(ingest_root / "raw" / item["path"], item)
            report["initial_quarantine_required"] = entry["initial_quarantine_required"]
            fresh_json(output / "files" / (item["path"].replace("/", "__") + ".json"), report)
            event_field = "candle_start" if report["stream"] in CANDLES else STREAMS[report["stream"]][0]
            summaries.append({"path": item["path"], "counts": report["counts"],
                "flags": report["flags"], "initial_quarantine_required": report["initial_quarantine_required"],
                "event_occupied_fraction": report["coverage"][event_field]["occupied_fraction"]})
        except (ValueError, OSError, pa.ArrowException) as exc:
            failure = {"path": item["path"], "error": str(exc), "training_admitted": False}
            fresh_json(output / "files" / (item["path"].replace("/", "__") + ".failure.json"), failure)
            failures.append(failure)
        print(canonical({"audited_files": len(summaries), "failures": len(failures),
                         "snapshot_files": len(ready)}), flush=True)
    result = {"schema": "historical_stream_readiness_snapshot_v1",
              "source_plan_sha256": plan["plan_sha256"],
              "files": summaries, "failures": failures, "snapshot_files": len(ready),
              "raw_unchanged": True, "training_admitted": False,
              "formal_readiness": False, "full_session_count_verified": False,
              "no_paid_calls": True, "no_new_downloads": True}
    fresh_json(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingest-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tables", nargs="*")
    args = parser.parse_args()
    result = run(args.ingest_root, args.output, tables=args.tables)
    print(canonical({"snapshot_files": result["snapshot_files"],
                     "failures": len(result["failures"]), "formal_readiness": False}))
