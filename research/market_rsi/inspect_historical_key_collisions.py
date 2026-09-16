#!/usr/bin/env python3
"""Trace bounded repeated-key examples to immutable raw row locations."""
import argparse
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from bounded_historical_ingest import verify_file
from historical_global_key_audit import KEYS
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def inspect_stream(ingest: Path, files: list[dict], *, stream: str, examples: list[dict],
                   max_hits=512) -> dict:
    if not examples or len(examples) > 24:
        raise ValueError("bounded repeated-key examples required")
    wanted = {e["source_key"]: e["occurrences"] for e in examples}
    if len(wanted) != len(examples) or sum(wanted.values()) > max_hits:
        raise ValueError("example hit count exceeds bound")
    key = KEYS[stream]
    keys = pa.array(sorted(wanted), type=pa.int64())
    hits = defaultdict(list)
    for item in files:
        path = ingest / "raw" / item["path"]
        verify_file(path, item)
        parquet = pq.ParquetFile(path)
        ordinal = 0
        for batch in parquet.iter_batches(batch_size=100_000):
            mask = pc.is_in(batch.column(key), value_set=keys)
            indices = np.flatnonzero(mask.to_numpy(zero_copy_only=False))
            if len(indices):
                for index, row in zip(indices, pa.Table.from_batches([batch]).filter(mask).to_pylist()):
                    row = {k: v.isoformat() if isinstance(v, (date, datetime)) else v for k, v in row.items()}
                    # Distinguish local ID reuse from repeated event payload; collector
                    # receipt/partition fields are not exchange event identifiers.
                    payload = {k: v for k, v in row.items() if k not in {
                        "id", "date", "ingest_ts_ms", "received_at", "created_at"}}
                    hits[row[key]].append({"relative_path": item["path"],
                        "source_sha256": item["lfs_sha256"], "raw_row_ordinal": ordinal + int(index),
                        "row": row, "event_payload_sha256": digest(payload)})
                    if sum(len(v) for v in hits.values()) > max_hits:
                        raise ValueError("actual example hits exceed frozen bound")
            ordinal += batch.num_rows
        verify_file(path, item)
    if {k: len(v) for k, v in hits.items()} != wanted:
        raise ValueError("collision samples do not reconcile to exact global key counts")
    results = [{"source_key": key, "occurrences": len(rows),
                "distinct_event_payloads": len({r["event_payload_sha256"] for r in rows}),
                "hits": rows} for key, rows in sorted(hits.items())]
    return {"stream": stream, "examples": results, "sample_only": True,
            "keys_with_multiple_event_payloads": sum(r["distinct_event_payloads"] > 1 for r in results),
            "raw_unchanged": True, "automatic_deduplication": False, "training_admitted": False}


def run(ingest: Path, key_audit: Path, output: Path):
    source = load_json(key_audit / "result.json")
    plan = load_json(ingest / "frozen-plan.json")
    if source["source_plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("source plans differ")
    output.mkdir(exist_ok=False)
    fresh_json(output / "claim.json", {"source_key_audit_sha256": file_hash(key_audit / "result.json"),
        "source_plan_sha256": plan["plan_sha256"], "code_sha256": file_hash(__file__),
        "selection": "first_12_reported_repeated_keys_each_affected_stream", "no_paid_calls": True})
    reports = []
    for summary in source["streams"]:
        if not summary["repeated_distinct_keys"]:
            continue
        stream = summary["stream"]
        detailed = load_json(key_audit / stream / "result.json")
        items = [i for i in plan["audit"]["selected_files"] if i["path"].split("/")[1] == stream]
        report = inspect_stream(ingest, items, stream=stream, examples=detailed["examples"][:12])
        fresh_json(output / (stream + ".json"), report)
        reports.append({k: report[k] for k in ["stream", "keys_with_multiple_event_payloads", "sample_only"]})
        print(canonical(reports[-1]), flush=True)
    fresh_json(output / "result.json", {"streams": reports, "raw_unchanged": True,
                                        "training_admitted": False, "no_paid_calls": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ingest-root", "key-audit", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    run(args.ingest_root, args.key_audit, args.output)
