#!/usr/bin/env python3
"""Materialize dense Train-only objective candidates from closed archives."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from market_rsi import fresh_json
from materialize_polymarket_archives import canonical, jsonl, load_days
from polymarket_data import build_event_catalog
from polymarket_objective_data import (
    DISCOVERY_TARGET_SPECS,
    materialize_objective_books,
)


def materialize(data_root: Path, dates: list[str]) -> dict:
    if not dates or dates != sorted(set(dates)):
        raise ValueError("unique chronological dates required")
    days = load_days(data_root, dates)
    source = {
        "schema": "polymarket_closed_archive_bundle_v1",
        "data_root_role": "existing_read_only_collector_archive",
        "dates": days,
    }
    source_sha256 = sha256(canonical(source).encode()).hexdigest()
    event_paths = [data_root / date / "event_changes.jsonl.gz" for date in dates]
    book_paths = [data_root / date / "book_observations.jsonl.gz" for date in dates]
    catalog, event_counts = build_event_catalog(jsonl(event_paths))
    result = materialize_objective_books(
        jsonl(book_paths), catalog, source_sha256,
        target_specs=DISCOVERY_TARGET_SPECS,
    )
    result.update({
        "source_bundle": source,
        "source_bundle_sha256": source_sha256,
        "event_catalog_counts": event_counts,
        "event_catalog_games": len(catalog),
        "evidence_class": "opened_train_objective_discovery",
        "scientific_admission": False,
        "dev_labels_used": False,
        "future_test_used": False,
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--dates", required=True, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = materialize(args.data_root, args.dates)
    fresh_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "source_bundle_sha256": result["source_bundle_sha256"],
        "event_catalog_games": result["event_catalog_games"],
        "rows": len(result["rows"]),
        "counts": result["counts"],
    }, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
