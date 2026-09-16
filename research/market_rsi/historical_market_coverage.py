#!/usr/bin/env python3
"""Measure PM observation coverage without future labels or price-change filters.

Per-second event presence is NOT continuous/executable quote coverage. Nominal
15-minute windows are parsed from the source slug as a diagnostic hypothesis,
not certified settlement times or a rule selecting a research universe.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from bounded_historical_ingest import verify_file
from historical_ingest_controller import _signed
from market_rsi import canonical, file_hash, fresh_json, load_json


WINDOW_SECONDS = 900
MAX_MARKETS = 20_000


class Coverage:
    def __init__(self, metadata):
        if not metadata or len(metadata) > MAX_MARKETS:
            raise ValueError("metadata exceeds bounded market count")
        self.rows = metadata
        self.names = pa.array([r["market_slug"] for r in metadata])
        if len(set(self.names.to_pylist())) != len(metadata):
            raise ValueError("duplicate metadata market slug")
        self.up = pa.array([r["up_token_id"] for r in metadata])
        self.down = pa.array([r["down_token_id"] for r in metadata])
        self.starts = np.array([int(m.group(1)) if (m := re.fullmatch(
            r"btc-updown-15m-(\d{10})", r["market_slug"])) else -1 for r in metadata], dtype=np.int64)
        n = len(metadata)
        self.token_events = np.zeros((n, 2, WINDOW_SECONDS), dtype=bool)
        self.token_quotes = np.zeros_like(self.token_events)
        self.counts = {k: np.zeros(n, dtype=np.int64) for k in
            ("rows", "identity_mismatch_rows", "before_nominal_window_rows", "after_nominal_window_rows",
             "two_sided_non_crossed_rows", "crossed_rows")}
        self.min_ingest = np.full(n, np.iinfo(np.int64).max, dtype=np.int64)
        self.max_ingest = np.full(n, -1, dtype=np.int64)
        self.minutes = set()
        self.unknown_market_rows = 0
        self.total = 0

    def consume(self, batch):
        table = pa.Table.from_batches([batch]) if isinstance(batch, pa.RecordBatch) else batch
        needed = {"market_slug", "asset_id", "ingest_ts_ms", "best_bid", "best_ask"}
        if not needed <= set(table.column_names):
            raise ValueError("required quote coverage fields missing")
        for name in ("market_slug", "asset_id", "ingest_ts_ms"):
            if table[name].null_count:
                raise ValueError("null identity/clock for coverage")
        mapped = pc.index_in(table["market_slug"], value_set=self.names)
        idx = pc.fill_null(mapped, -1).to_numpy().astype(np.int64)
        known = idx >= 0
        self.unknown_market_rows += int(np.sum(~known))
        self.total += table.num_rows
        clock = table["ingest_ts_ms"].to_numpy()
        if not np.issubdtype(clock.dtype, np.integer) or np.any((clock < 946684800000) | (clock >= 4102444800000)):
            raise ValueError("coverage requires sane integer epoch-ms receipt clocks")
        self.minutes.update(int(v) for v in np.unique(clock // 60_000))
        up = pc.fill_null(pc.equal(table["asset_id"], pc.take(self.up, mapped)), False).to_numpy()
        down = pc.fill_null(pc.equal(table["asset_id"], pc.take(self.down, mapped)), False).to_numpy()
        token_ok = (up | down) & known
        bid = table["best_bid"].to_numpy()
        ask = table["best_ask"].to_numpy()
        two_sided = np.isfinite(bid) & np.isfinite(ask) & (bid >= 0) & (ask <= 1) & (bid <= ask)
        crossed = np.isfinite(bid) & np.isfinite(ask) & (bid > ask)
        safe = np.maximum(idx, 0)
        starts = self.starts[safe]
        offset = clock // 1000 - starts
        scheduled = known & (starts >= 0)
        inside = scheduled & (offset >= 0) & (offset < WINDOW_SECONDS)
        masks = {"rows": known, "identity_mismatch_rows": known & ~token_ok,
                 "before_nominal_window_rows": scheduled & (offset < 0),
                 "after_nominal_window_rows": scheduled & (offset >= WINDOW_SECONDS),
                 "two_sided_non_crossed_rows": known & token_ok & two_sided,
                 "crossed_rows": known & crossed}
        for name, mask in masks.items():
            self.counts[name] += np.bincount(idx[mask], minlength=len(self.rows))
        np.minimum.at(self.min_ingest, idx[known], clock[known])
        np.maximum.at(self.max_ingest, idx[known], clock[known])
        for side, side_mask in enumerate((up, down)):
            present = inside & side_mask
            good = present & two_sided
            self.token_events[idx[present], side, offset[present]] = True
            self.token_quotes[idx[good], side, offset[good]] = True

    def result(self):
        markets = []
        for i, row in enumerate(self.rows):
            if not self.counts["rows"][i]:
                continue
            markets.append({"market_slug": row["market_slug"],
                **{k: int(v[i]) for k, v in self.counts.items()},
                "nominal_start_from_slug_s": int(self.starts[i]),
                "min_ingest_ms": int(self.min_ingest[i]), "max_ingest_ms": int(self.max_ingest[i]),
                "up_seconds_with_event": int(self.token_events[i, 0].sum()),
                "down_seconds_with_event": int(self.token_events[i, 1].sum()),
                "up_seconds_with_two_sided_quote": int(self.token_quotes[i, 0].sum()),
                "down_seconds_with_two_sided_quote": int(self.token_quotes[i, 1].sum()),
                "seconds_with_two_sided_quotes_for_both_tokens": int(np.sum(self.token_quotes[i, 0] & self.token_quotes[i, 1]))})
        days = Counter(datetime.fromtimestamp(m * 60, timezone.utc).date().isoformat() for m in self.minutes)
        return {"rows": self.total, "unknown_market_rows": self.unknown_market_rows,
                "observed_markets": len(markets), "markets": markets,
                "actual_utc_receipt_day_event_bins": [{"utc_date": day, "minutes_with_events": count,
                    "possible_minutes": 1440} for day, count in sorted(days.items())],
                "full_utc_days_with_an_event_in_every_minute": sum(n == 1440 for n in days.values()),
                "clock_used": "recorded_ingest_ts_ms_not_filename",
                "nominal_window_rule": "slug_epoch_plus_900s_diagnostic_only_not_settlement_verified",
                "continuous_executable_quote_coverage_proven": False,
                "per_second_presence_is_not_independent_sample_count": True,
                "quiet_records_preserved": True, "future_label_filter": False,
                "raw_unchanged": True, "training_admitted": False}


def run(ingest, output):
    plan = load_json(ingest / "frozen-plan.json")
    _signed(plan, "plan_sha256")
    complete = load_json(ingest / "completion.json")
    if not complete["raw_acquisition_complete"] or complete["source_plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("completed matching source required")
    items = [i for i in plan["audit"]["selected_files"] if i["path"].split("/")[1] == "polymarket_ticks_ms"]
    meta = next(i for i in plan["audit"]["selected_files"] if i["path"].split("/")[1] == "market_meta")
    meta_path = ingest / "raw" / meta["path"]
    verify_file(meta_path, meta)
    rows = pq.ParquetFile(meta_path).read(columns=["market_slug", "up_token_id", "down_token_id"]).to_pylist()
    coverage = Coverage(rows)
    output.mkdir(exist_ok=False)
    fresh_json(output / "claim.json", {"source_plan_sha256": plan["plan_sha256"],
        "code_sha256": file_hash(__file__), "files": items, "metadata": meta,
        "max_markets": MAX_MARKETS, "batch_rows": 100_000,
        "coverage_boolean_array_bytes": coverage.token_events.nbytes + coverage.token_quotes.nbytes,
        "no_paid_calls": True, "no_training_selection": True})
    for i, item in enumerate(items):
        path = ingest / "raw" / item["path"]
        verify_file(path, item)
        pf = pq.ParquetFile(path)
        before = coverage.total
        for batch in pf.iter_batches(batch_size=100_000, columns=["market_slug", "asset_id", "ingest_ts_ms", "best_bid", "best_ask"]):
            coverage.consume(batch)
        if coverage.total - before != pf.metadata.num_rows:
            raise ValueError("coverage row conservation failure")
        verify_file(path, item)
        print(canonical({"files": i+1, "total_files": len(items), "rows": coverage.total}), flush=True)
    if coverage.total != complete["pm_tick_rows"]:
        raise ValueError("PM source row total changed")
    result = coverage.result()
    fresh_json(output / "result.json", result)
    print(canonical({"rows": result["rows"], "observed_markets": result["observed_markets"],
                     "training_admitted": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingest-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.ingest_root, args.output)
