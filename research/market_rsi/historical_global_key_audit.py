#!/usr/bin/env python3
"""Bounded exact source-key audit; does NOT deduplicate raw observations.

Hash-partition int64 source keys to disk, then sort one bounded shard at a time.
A repeated source key is not proof of an identical row. Preserve original bytes
and retain (dataset revision, source path/hash, row ordinal) for physical identity.
No price labels, targets, models, downloads or train/eval selection.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from bounded_historical_ingest import verify_file
from historical_ingest_controller import _signed
from market_rsi import canonical, file_hash, fresh_json, load_json


KEYS = {"polymarket_ticks_ms": "id", "binance_ticks_ms": "id", "binance_trades": "trade_id",
        **{f"binance_candles_{v}": "candle_start" for v in ("1s", "5s", "1m", "5m", "15m", "1h")}}
SHARDS = 128
BATCH_ROWS = 250_000
MAX_SHARD_ROWS = 8_000_000  # 64 MB key array; scratch arrays are separately bounded.
MAX_KEY_BYTES = 8_000_000_000
FREE_DISK_MARGIN = 8_000_000_000


def shard_numbers(values: np.ndarray, shards=SHARDS) -> np.ndarray:
    if shards < 1 or shards > 1024 or shards & (shards - 1):
        raise ValueError("power-of-two shard count required")
    x = values.astype(np.uint64, copy=True)
    x ^= x >> np.uint64(30)
    x *= np.uint64(0xBF58476D1CE4E5B9)
    x ^= x >> np.uint64(27)
    x *= np.uint64(0x94D049BB133111EB)
    x ^= x >> np.uint64(31)
    return (x & np.uint64(shards - 1)).astype(np.int16)


def summarize_shard(path: Path, expected_rows: int, *, max_rows=MAX_SHARD_ROWS) -> dict:
    if expected_rows > max_rows:
        raise ValueError("source-key shard exceeds RAM bound; no unbounded sort")
    if path.is_symlink() or path.stat().st_size != expected_rows * 8:
        raise ValueError("shard size/count mismatch")
    values = np.fromfile(path, dtype="<i8")
    values.sort(kind="quicksort")
    equal = values[1:] == values[:-1]
    excess = int(np.count_nonzero(equal))
    starts = np.flatnonzero(equal & ~np.r_[False, equal[:-1]]) if len(equal) else np.array([], dtype=int)
    examples = []
    for pos in starts[:12]:
        key = values[pos]
        count = int(np.searchsorted(values, key, side="right") - np.searchsorted(values, key, side="left"))
        examples.append({"source_key": int(key), "occurrences": count})
    return {"rows": len(values), "unique_keys": len(values) - excess,
            "excess_occurrences": excess, "repeated_distinct_keys": len(starts),
            "examples": examples, "shard_sha256": file_hash(path)}


def audit_stream(ingest: Path, items: list[dict], output: Path, *, shards=SHARDS,
                 batch_rows=BATCH_ROWS, max_shard_rows=MAX_SHARD_ROWS) -> dict:
    streams = {i["path"].split("/")[1] for i in items}
    if len(streams) != 1 or not streams <= set(KEYS):
        raise ValueError("one supported source stream required")
    stream = next(iter(streams))
    output.mkdir(exist_ok=False)
    paths = [output / f"keys-{i:03d}.i64" for i in range(shards)]
    counts = np.zeros(shards, dtype=np.int64)
    input_rows, files = 0, []
    with ExitStack() as stack:
        handles = [stack.enter_context(p.open("xb")) for p in paths]
        for item in items:
            path = ingest / "raw" / item["path"]
            verify_file(path, item)
            parquet = pq.ParquetFile(path)
            key = KEYS[stream]
            if key not in parquet.schema_arrow.names or not pa.types.is_integer(parquet.schema_arrow.field(key).type):
                raise ValueError("required integer source key missing")
            before = input_rows
            for batch in parquet.iter_batches(batch_size=batch_rows, columns=[key]):
                col = batch.column(0)
                if col.null_count:
                    raise ValueError("null source key; no synthetic replacement")
                if pa.types.is_unsigned_integer(col.type) and pc.max(col).as_py() > np.iinfo(np.int64).max:
                    raise ValueError("unsigned source key exceeds signed storage range")
                values = col.to_numpy(zero_copy_only=False).astype("<i8", copy=False)
                slots = shard_numbers(values, shards)
                order = np.argsort(slots, kind="stable")
                arranged = values[order]
                sizes = np.bincount(slots, minlength=shards)
                counts += sizes
                if int(counts.max()) > max_shard_rows:
                    raise ValueError("source-key shard would exceed RAM bound")
                begin = 0
                for handle, n in zip(handles, sizes):
                    end = begin + int(n)
                    if end != begin:
                        handle.write(arranged[begin:end].tobytes())
                    begin = end
                input_rows += batch.num_rows
            if input_rows - before != parquet.metadata.num_rows:
                raise ValueError("decoded input row count changed")
            verify_file(path, item)
            files.append({"path": item["path"], "sha256": item["lfs_sha256"],
                          "rows": input_rows - before})
            print(canonical({"stage": "source_keys_partitioned", "stream": stream,
                             "files": len(files), "rows": input_rows}), flush=True)
        for handle in handles:
            handle.flush()
            os.fsync(handle.fileno())
    shard_results = [summarize_shard(path, int(n), max_rows=max_shard_rows) for path, n in zip(paths, counts)]
    if sum(r["rows"] for r in shard_results) != input_rows:
        raise ValueError("shards lost or duplicated rows")
    result = {"stream": stream, "key": KEYS[stream], "rows": input_rows,
              "unique_keys": sum(r["unique_keys"] for r in shard_results),
              "excess_occurrences": sum(r["excess_occurrences"] for r in shard_results),
              "repeated_distinct_keys": sum(r["repeated_distinct_keys"] for r in shard_results),
              "examples": [e for r in shard_results for e in r["examples"]][:24],
              "files": files, "shards": shard_results,
              "largest_shard_rows": int(counts.max()), "max_shard_rows": max_shard_rows,
              "exact_source_key_count": True, "identical_observation_dedup_proven": False,
              "raw_unchanged": True, "training_admitted": False}
    fresh_json(output / "result.json", result)
    return result


def prepare(ingest: Path, output: Path) -> dict:
    if not load_json(ingest / "completion.json").get("raw_acquisition_complete"):
        raise ValueError("complete raw acquisition required")
    plan = load_json(ingest / "frozen-plan.json")
    _signed(plan, "plan_sha256")
    if load_json(ingest / "claim.json")["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("ingest claim differs from manifest")
    items, expected_rows = [], 0
    for item in plan["audit"]["selected_files"]:
        if item["path"].split("/")[1] not in KEYS:
            continue
        if Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts:
            raise ValueError("unsafe selected path")
        qa_path = ingest / "qa" / (item["path"].replace("/", "__") + ".json")
        qa = load_json(qa_path)
        if qa["sha256"] != item["lfs_sha256"]:
            raise ValueError("QA source hash differs")
        raw = ingest / "raw" / item["path"]
        if (type(qa.get("rows")) is not int or qa["rows"] <= 0
                or pq.ParquetFile(raw).metadata.num_rows != qa["rows"]):
            raise ValueError("QA/header row count differs; cannot bound disk")
        expected_rows += qa["rows"]
        items.append(item)
    key_bytes = expected_rows * 8
    if not items or key_bytes > MAX_KEY_BYTES:
        raise ValueError("source-key artifact disk cap exceeded")
    if shutil.disk_usage(output.parent).free < key_bytes + FREE_DISK_MARGIN:
        raise ValueError("insufficient free disk reserve")
    output.mkdir(exist_ok=False, mode=0o700)
    spec = {"ingest": str(ingest.absolute()), "source_plan_sha256": plan["plan_sha256"],
            "files": items, "code_sha256": file_hash(__file__), "expected_rows": expected_rows,
            "key_bytes_upper": key_bytes, "shards": SHARDS, "max_shard_rows": MAX_SHARD_ROWS,
            "physical_row_identity": ["dataset_revision", "relative_path", "sha256", "raw_row_ordinal"],
            "source_key_scope": "separate_per_stream", "no_new_downloads": True,
            "no_paid_calls": True, "training_admitted": False}
    fresh_json(output / "claim.json", spec)
    return spec


def execute(ingest: Path, output: Path):
    lock = (output.parent / "historical-global-keys.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fresh_json(output / "process.json", {"pid": os.getpid(), "started_unix_ns": time.time_ns()})
    try:
        spec = load_json(output / "claim.json")
        if spec["code_sha256"] != file_hash(__file__) or spec["ingest"] != str(ingest.absolute()):
            raise ValueError("frozen source-key audit changed")
        outputs = []
        for stream in sorted(KEYS):
            items = [i for i in spec["files"] if i["path"].split("/")[1] == stream]
            if items:
                outputs.append(audit_stream(ingest, items, output / stream))
        rows = sum(r["rows"] for r in outputs)
        if rows != spec["expected_rows"]:
            raise ValueError("global row conservation failed")
        result = {"source_plan_sha256": spec["source_plan_sha256"], "rows": rows,
            "streams": [{k: r[k] for k in ("stream", "key", "rows", "unique_keys",
                        "excess_occurrences", "repeated_distinct_keys", "largest_shard_rows")}
                        for r in outputs], "raw_unchanged": True, "formal_readiness": False,
            "identical_observation_dedup_proven": False, "no_new_downloads": True, "no_paid_calls": True}
        fresh_json(output / "result.json", result)
        return result
    except Exception as exc:
        fresh_json(output / "failure.json", {"error": str(exc), "raw_unchanged": True,
                                              "automatic_retry": False})
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingest-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--execute-prepared", action="store_true")
    args = parser.parse_args()
    ingest, output = args.ingest_root.absolute(), args.output.absolute()
    if not args.execute_prepared:
        prepare(ingest, output)
    if args.detach:
        if args.execute_prepared:
            raise ValueError("do not dispatch an already prepared claim twice")
        command = [sys.executable, str(Path(__file__).absolute()), "--ingest-root", str(ingest),
                   "--output", str(output), "--execute-prepared"]
        with (output / "runner.log").open("x") as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(canonical({"pid": child.pid, "output": str(output), "no_paid_calls": True}))
    else:
        print(canonical(execute(ingest, output)))
