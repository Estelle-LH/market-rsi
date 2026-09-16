"""Offline diagnostics: unchanged best quotes are not duplicate market events.

Reads already-open OpenMarket canaries only. Does not select training rows,
read labels, alter source data, or authorize a new experiment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from market_rsi import digest, file_hash, fresh_json


COLUMNS = ["id", "market_slug", "asset_id", "ingest_ts_ms", "source_ts_ms",
           "event_type", "side_label", "price", "size", "best_bid", "best_ask"]


def _adjacent_equal(column):
    left, right = column.slice(0, len(column) - 1), column.slice(1)
    return pc.or_(pc.fill_null(pc.equal(left, right), False),
                  pc.and_(pc.is_null(left), pc.is_null(right))).to_numpy(
                      zero_copy_only=False)


def audit_activity(table: pa.Table) -> dict:
    table = table.select(COLUMNS).combine_chunks()
    if table.num_rows == 0:
        raise ValueError("empty input")
    for name in ("id", "market_slug", "asset_id", "ingest_ts_ms", "source_ts_ms"):
        if table[name].null_count:
            raise ValueError("missing identity or timestamp")
    repeated_ids = table.num_rows - pc.count_distinct(table["id"]).as_py()
    if repeated_ids:
        raise ValueError("repeated row IDs require a separate identity/conflict audit")
    for name in ("price", "size", "best_bid", "best_ask"):
        if pc.any(pc.invert(pc.fill_null(pc.is_finite(table[name]), True))).as_py():
            raise ValueError("non-finite numeric value")
    # Preserve file position for ties; a tie is reported, not claimed resolved.
    table = table.append_column("file_ordinal", pa.array(np.arange(table.num_rows)))
    table = table.sort_by([("market_slug", "ascending"), ("asset_id", "ascending"),
                           ("ingest_ts_ms", "ascending"), ("file_ordinal", "ascending")])
    columns = {name: table[name].combine_chunks() for name in COLUMNS}
    same_stream = (_adjacent_equal(columns["market_slug"])
                   & _adjacent_equal(columns["asset_id"]))
    comparable = same_stream.copy()
    for name in ("best_bid", "best_ask"):
        valid = pc.is_valid(columns[name]).to_numpy(zero_copy_only=False)
        comparable &= valid[:-1] & valid[1:]
    unchanged = (comparable & _adjacent_equal(columns["best_bid"])
                 & _adjacent_equal(columns["best_ask"]))
    same_payload = np.ones(table.num_rows - 1, dtype=bool)
    for name in ("event_type", "side_label", "price", "size"):
        same_payload &= _adjacent_equal(columns[name])
    payload_changed = unchanged & ~same_payload
    repeat_visible = unchanged & same_payload
    counts = {
        "rows": table.num_rows,
        "streams": int((~same_stream).sum()) + 1,
        "within_stream_transitions": int(same_stream.sum()),
        "comparable_quote_transitions": int(comparable.sum()),
        "incomplete_quote_transitions": int((same_stream & ~comparable).sum()),
        "best_quote_changed": int((comparable & ~unchanged).sum()),
        "best_quote_unchanged": int(unchanged.sum()),
        "unchanged_quote_but_other_payload_changed": int(payload_changed.sum()),
        "unchanged_quote_and_visible_payload": int(repeat_visible.sum()),
        "same_receive_timestamp_transitions": int((same_stream & _adjacent_equal(
            columns["ingest_ts_ms"])).sum()),
        "repeated_row_ids": repeated_ids,
        "rows_removed": 0,
    }
    counts["unchanged_best_quote_fraction"] = (
        counts["best_quote_unchanged"] / counts["comparable_quote_transitions"]
        if counts["comparable_quote_transitions"] else None)
    return counts


def run(canary_root: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    source_report_path = canary_root / "clean-data-report.json"
    source_report = json.loads(source_report_path.read_bytes())
    audits = []
    for item in source_report["selected_files"]:
        if not item["role"].endswith("polymarket_ticks"):
            continue
        path = canary_root / "raw" / item["path"]
        expected = source_report["audits"][item["role"]]["raw_sha256"]
        if file_hash(path) != expected:
            raise ValueError("source bytes differ from the existing canary receipt")
        table = pq.ParquetFile(path).read(columns=COLUMNS)
        counts = audit_activity(table)
        if file_hash(path) != expected:
            raise ValueError("source mutated during audit")
        audits.append({"path": str(path), "sha256": expected,
                       "utc_date": item["utc_date"], **counts})
    if not audits:
        raise ValueError("no tick partitions")
    body = {
        "schema": "quote_activity_diagnostic_v1",
        "source_report_sha256": file_hash(source_report_path),
        "audit_code_sha256": file_hash(Path(__file__)),
        "fields_read": COLUMNS, "partitions": audits,
        "use": "already-open data diagnostics only; no labels or Dev opened",
        "rows_removed": 0, "training_mask_created": False,
        "limitations": [
            "Unchanged quote means equal best_bid and best_ask within one market/token.",
            "price_change price/size are order updates, not verified trade executions.",
            "Equal visible payload with a different event ID is not a proven duplicate.",
            "Full depth, trade tape and collection heartbeats are not in this source.",
            "Message fractions are not elapsed-time fractions or independent samples.",
            "Same receive-time order uses file ordinal; true sequence is not proven.",
        ],
    }
    report = {**body, "report_sha256": digest(body)}
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / "activity-report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.canary_root, args.output), indent=2))
