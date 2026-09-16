#!/usr/bin/env python3
"""Acquire a completed controller's exact manifest and run bounded streaming QA.

Preserves every raw byte. This is not a feature materializer or a formal-data
admission gate; no Train/Dev/target is constructed. Verified complete files are
resumable, but partial transfers never silently restart and double the byte cap.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import shutil
import time
from urllib.parse import quote
from urllib.request import urlopen

from controller_activity_log import append_activity, read_activity_events
from historical_ingest_controller import (DATASET, REVISION, MAX_BYTES,
                                          _signed, assess_activity, load, select_files)
from market_rsi import canonical, file_hash, fresh_json


def verify_file(path: Path, item: dict) -> None:
    if (path.is_symlink() or not path.is_file() or path.stat().st_size != item["bytes"]
            or file_hash(path) != item["lfs_sha256"]):
        raise ValueError("downloaded file size/hash mismatch: " + item["path"])


def download_file(item: dict, target: Path) -> int:
    url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{quote(item['path'], safe='/')}"
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        raise ValueError("partial transfer retained; no automatic restart or hidden re-download")
    target.parent.mkdir(parents=True, exist_ok=True)
    received = 0
    with urlopen(url, timeout=60) as response, partial.open("xb") as handle:
        if response.status != 200:
            raise ValueError("expected complete public object response")
        length = response.headers.get("content-length")
        if length is not None and int(length) != item["bytes"]:
            raise ValueError("remote content length differs from frozen inventory")
        while True:
            chunk = response.read(min(1024 * 1024, item["bytes"] - received + 1))
            if not chunk:
                break
            received += len(chunk)
            if received > item["bytes"]:
                raise ValueError("response exceeds frozen object byte bound")
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    verify_file(partial, item)
    os.replace(partial, target)
    return received


def audit_parquet(path: Path, item: dict, metadata: dict | None, *,
                  identity_policy: str = "reject", quote_policy: str = "reject") -> dict:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    if identity_policy not in {"reject", "preserve_and_flag_no_training_admission"}:
        raise ValueError("unsupported identity policy")
    if quote_policy not in {"reject", "preserve_and_flag_no_training_admission"}:
        raise ValueError("unsupported quote policy")
    parquet = pq.ParquetFile(path)
    stream = item["path"].split("/")[1]
    report = {"table": stream, "rows": parquet.metadata.num_rows,
              "schema": str(parquet.schema_arrow), "row_groups": parquet.num_row_groups,
              "raw_bytes": item["bytes"], "sha256": item["lfs_sha256"],
              "raw_unchanged": True, "full_day_coverage_verified": False,
              "training_admitted": False}
    if not parquet.metadata.num_rows:
        raise ValueError("empty selected parquet")
    if stream != "polymarket_ticks_ms":
        # Other streams need their own later semantic/clock canary before feature use.
        count = sum(batch.num_rows for batch in parquet.iter_batches(batch_size=100_000))
        if count != report["rows"]:
            raise ValueError("parquet decoded row count changed")
        report.update(decoded_rows=count, semantic_validation="pending_stream_specific_canary")
        return report
    columns = ["id", "source_ts_ms", "ingest_ts_ms", "market_slug", "asset_id",
               "event_type", "price", "best_bid", "best_ask", "size", "date"]
    if metadata is None or not set(columns) <= set(parquet.schema_arrow.names):
        raise ValueError("PM schema or market metadata missing")
    counts, events, markets = Counter(), Counter(), set()
    mismatch_pairs = Counter()
    crossed_examples = []
    observed_row_dates = set()
    minimum_source = minimum_ingest = None
    maximum_source = maximum_ingest = None
    previous_ingest = None
    for batch in parquet.iter_batches(batch_size=100_000, columns=columns):
        table = pa.Table.from_batches([batch])
        counts["decoded_rows"] += table.num_rows
        for name in ("id", "source_ts_ms", "ingest_ts_ms", "market_slug", "asset_id", "event_type", "date"):
            if table[name].null_count:
                raise ValueError("null PM identity/clock field: " + name)
        source, ingest = table["source_ts_ms"], table["ingest_ts_ms"]
        latency = pc.subtract(ingest, source)
        if pc.any(pc.less(latency, 0)).as_py():
            raise ValueError("negative ingest latency")
        counts["delayed_over_1s_rows"] += pc.sum(pc.cast(pc.greater(latency, 1000), pa.int64())).as_py()
        counts["delayed_over_60s_rows"] += pc.sum(pc.cast(pc.greater(latency, 60000), pa.int64())).as_py()
        smin, smax = pc.min(source).as_py(), pc.max(source).as_py()
        imin, imax = pc.min(ingest).as_py(), pc.max(ingest).as_py()
        minimum_source = min(minimum_source, smin) if minimum_source is not None else smin
        maximum_source = max(maximum_source, smax) if maximum_source is not None else smax
        minimum_ingest = min(minimum_ingest, imin) if minimum_ingest is not None else imin
        maximum_ingest = max(maximum_ingest, imax) if maximum_ingest is not None else imax
        ingests = ingest.combine_chunks().to_numpy()
        counts["arrival_order_reversals"] += int((ingests[1:] < ingests[:-1]).sum())
        if previous_ingest is not None and ingests[0] < previous_ingest:
            counts["arrival_order_reversals"] += 1
        previous_ingest = ingests[-1]
        observed_row_dates.update(str(v) for v in pc.unique(table["date"]).to_pylist())
        event_types = pc.utf8_lower(table["event_type"])
        events.update({v["values"]: v["counts"] for v in pc.value_counts(event_types).to_pylist()})
        if not set(events) <= {"book", "price_change"}:
            raise ValueError("unknown PM event semantics")
        changes = pc.equal(event_types, "price_change")
        for name in ("price", "best_bid", "best_ask", "size"):
            counts["null_" + name] += table[name].null_count
            if pc.any(pc.and_(changes, pc.is_null(table[name]))).as_py():
                raise ValueError("price-change missing required price state")
            if pc.any(pc.fill_null(pc.invert(pc.is_finite(table[name])), False)).as_py():
                raise ValueError("nonfinite price/size")
            if pc.any(pc.fill_null(pc.less(table[name], 0), False)).as_py():
                raise ValueError("negative price/size")
            if name != "size" and pc.any(pc.fill_null(pc.greater(table[name], 1), False)).as_py():
                raise ValueError("probability price outside [0,1]")
        crossed = pc.fill_null(pc.greater(table["best_bid"], table["best_ask"]), False)
        crossed_count = pc.sum(pc.cast(crossed, pa.int64())).as_py()
        counts["crossed_quote_rows"] += crossed_count
        if crossed_count:
            if quote_policy == "reject":
                raise ValueError("crossed PM quote")
            if len(crossed_examples) < 5:
                crossed_examples.extend(table.filter(crossed).select(
                    ["id", "market_slug", "asset_id", "source_ts_ms", "ingest_ts_ms",
                     "best_bid", "best_ask"]).slice(0, 5 - len(crossed_examples)).to_pylist())
        if pc.any(pc.and_(pc.is_null(table["best_bid"]), pc.is_null(table["best_ask"]))).as_py():
            raise ValueError("PM event has neither side of quote")
        pairs = table.select(["market_slug", "asset_id", "id"]).group_by(["market_slug", "asset_id"]).aggregate([("id", "count")])
        for pair in pairs.to_pylist():
            market = pair["market_slug"]
            if market not in metadata or pair["asset_id"] not in metadata[market]:
                if identity_policy == "reject":
                    raise ValueError("token does not belong to its row's market")
                counts["identity_mismatch_rows"] += pair["id_count"]
                mismatch_pairs[(market, pair["asset_id"])] += pair["id_count"]
            markets.add(market)
        counts["within_batch_duplicate_ids"] += table.num_rows - pc.count_distinct(table["id"]).as_py()
    if counts["decoded_rows"] != report["rows"] or counts["within_batch_duplicate_ids"]:
        raise ValueError("row count mismatch or within-batch duplicate IDs")
    partition_day = item["path"].split("date=")[1].split("/")[0]
    if observed_row_dates != {partition_day}:
        raise ValueError("declared row date differs from file partition")
    report.update(dict(counts), event_counts=dict(events), market_count=len(markets),
                  source_min_ms=minimum_source, source_max_ms=maximum_source,
                  ingest_min_ms=minimum_ingest, ingest_max_ms=maximum_ingest,
                  global_id_uniqueness="not_yet_verified_across_batches_and_files",
                  true_exchange_tie_order="unavailable",
                  source_file_ordinal="preserved_in_unchanged_raw_parquet",
                  chronological_materialization="pending_ingest_time_sort_with_raw_ordinal",
                  pm_trade_tape="unavailable_not_zero_trades",
                  identity_policy=identity_policy,
                  quote_policy=quote_policy,
                  crossed_quote_examples=crossed_examples,
                  identity_mismatch_pairs=[{"market_slug": m, "asset_id": a, "rows": n}
                                           for (m, a), n in sorted(mismatch_pairs.items())],
                  quarantine_required=bool(mismatch_pairs) or bool(counts["crossed_quote_rows"]),
                  initial_streaming_qa_pass=not (bool(mismatch_pairs) or bool(counts["crossed_quote_rows"])))
    return report


def read_controller_plan(session_root: Path) -> dict:
    assessment = load(session_root / "session" / "assessment.json")
    if assessment.get("valid") is not True or assessment.get("controller_stage") != "ingest":
        raise ValueError("completed valid ingest controller required before downloading")
    workspace = session_root / "workspace"
    if assess_activity(workspace)["action"] != "select":
        raise ValueError("controller deferred; no download authorized")
    frozen = load(workspace / "frozen-ingest-plan.json")
    _signed(frozen, "plan_sha256")
    if (frozen.get("dataset") != DATASET or frozen.get("revision") != REVISION
            or frozen.get("max_compressed_bytes") != MAX_BYTES
            or frozen["audit"] != select_files(load(workspace / "inventory.json"), frozen["proposal"])):
        raise ValueError("frozen selection changed")
    return frozen


def run(session_root: Path, output: Path, reuse_raw: Path, *, resume=False,
        quote_policy="reject", adaptation: dict | None = None) -> dict:
    import pyarrow.parquet as pq

    plan = read_controller_plan(session_root)
    if quote_policy != "reject":
        if (quote_policy != "preserve_and_flag_no_training_admission" or not resume
                or not adaptation or adaptation.get("training_admitted") is not False
                or adaptation.get("source_plan_sha256") != plan["plan_sha256"]):
            raise ValueError("quote QA adaptation requires explicit raw-only resume provenance")
    output = output.absolute()
    lock = (output.parent / "historical-ingest-download.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        if not resume:
            output.mkdir(mode=0o700, exist_ok=False)
            fresh_json(output / "claim.json", {"plan_sha256": plan["plan_sha256"],
                                                "source_session": str(session_root.absolute())})
            fresh_json(output / "frozen-plan.json", plan)
        elif load(output / "claim.json")["plan_sha256"] != plan["plan_sha256"]:
            raise ValueError("cannot resume a different manifest")
        if (output / "completion.json").exists():
            raise ValueError("ingest already completed; never rerun completed work")
        if list(output.rglob("*.partial")):
            raise ValueError("partial transfer needs explicit causal diagnosis before continuation")
        if shutil.disk_usage(output).free < plan["audit"]["selected_bytes"] + 10_000_000_000:
            raise ValueError("insufficient disk reserve for bounded acquisition")
        append_activity(output / "progress.jsonl", {
            "event": "process_started", "pid": os.getpid(), "unix_ns": time.time_ns(),
            "resume": resume, "plan_sha256": plan["plan_sha256"],
            "quote_policy": quote_policy, "source_adaptation": adaptation})
        selected = sorted(plan["audit"]["selected_files"],
                          key=lambda r: (r["path"].split("/")[1] != "market_meta", r["path"]))
        metadata, reports = None, []
        for index, item in enumerate(selected):
            target = output / "raw" / item["path"]
            if target.exists():
                verify_file(target, item)
            else:
                cached = reuse_raw / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if cached.is_file() and not cached.is_symlink():
                    verify_file(cached, item)
                    shutil.copyfile(cached, target)
                    mode, received = "copied_hash_verified_cache", 0
                else:
                    append_activity(output / "progress.jsonl", {
                        "event": "download_started", "path": item["path"], "bytes": item["bytes"]})
                    received = download_file(item, target)
                    mode = "downloaded_public_frozen_object"
                verify_file(target, item)
                append_activity(output / "progress.jsonl", {
                    "event": "file_acquired", "path": item["path"], "mode": mode,
                    "new_payload_bytes": received, "sha256": item["lfs_sha256"]})
            if item["path"].split("/")[1] == "market_meta":
                rows = pq.ParquetFile(target).read(columns=["market_slug", "up_token_id", "down_token_id"]).to_pylist()
                metadata = {r["market_slug"]: {r["up_token_id"], r["down_token_id"]} for r in rows}
                if len(metadata) != len(rows) or None in metadata:
                    raise ValueError("invalid or duplicate metadata identities")
            report_path = output / "qa" / (item["path"].replace("/", "__") + ".json")
            if report_path.exists():
                report = load(report_path)
                if report.get("sha256") != item["lfs_sha256"]:
                    raise ValueError("QA receipt changed")
            else:
                report = audit_parquet(target, item, metadata,
                                       identity_policy=plan.get("identity_policy", "reject"),
                                       quote_policy=quote_policy)
                verify_file(target, item)
                report_path.parent.mkdir(exist_ok=True)
                fresh_json(report_path, report)
            reports.append(report)
            append_activity(output / "progress.jsonl", {
                "event": "file_qa_complete", "path": item["path"], "rows": report["rows"],
                "completed_files": index + 1, "total_files": len(selected)})
            print(canonical({"completed_files": index + 1, "total_files": len(selected),
                             "path": item["path"], "rows": report["rows"]}), flush=True)
        events = read_activity_events(output / "progress.jsonl")
        result = {"raw_acquisition_complete": True, "selected_files": len(selected),
                  "tick_dates": plan["audit"]["tick_dates"], "source_plan_sha256": plan["plan_sha256"],
                  "new_payload_bytes": sum(e.get("new_payload_bytes", 0) for e in events),
                  "raw_bytes": plan["audit"]["selected_bytes"],
                  "pm_tick_rows": sum(r["rows"] for r in reports if r["table"] == "polymarket_ticks_ms"),
                  "identity_mismatch_rows": sum(r.get("identity_mismatch_rows", 0) for r in reports),
                  "crossed_quote_rows": sum(r.get("crossed_quote_rows", 0) for r in reports),
                  "quarantine_required": any(r.get("quarantine_required", False) for r in reports),
                  "formal_dataset_ready": False, "dev_created": False, "objective_selected": False,
                  "remaining": ["global_duplicate_check", "causal_clock_materialization",
                                "per_market_coverage_gaps", "side_stream_semantic_canaries",
                                "controller_objective_research", "prospective_split_freeze"]}
        fresh_json(output / "completion.json", result)
        return result
    except Exception as exc:
        if output.is_dir():
            append_activity(output / "progress.jsonl", {
                "event": "process_failed", "pid": os.getpid(), "error": str(exc),
                "automatic_retry": False, "raw_preserved": True})
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reuse-raw", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(canonical(run(args.session_root, args.output, args.reuse_raw, resume=args.resume)))
