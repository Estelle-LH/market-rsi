#!/usr/bin/env python3
"""Materialize committed Polymarket archive days without touching the collector.

This utility is intentionally provider-free. It verifies each selected gzip
archive against its closed-day manifest, streams the original observations
through :mod:`polymarket_data`, and creates one exclusive result file.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from polymarket_data import build_event_catalog, materialize_books


REQUIRED = ("event_changes.jsonl.gz", "book_observations.jsonl.gz")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_days(data_root, dates):
    days = []
    for date in dates:
        directory = data_root / date
        manifest_path = directory / "archive_manifest.json"
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        if (manifest.get("schema") != "ez-capture-archive.v1"
                or manifest.get("date") != date or not isinstance(manifest.get("files"), list)):
            raise ValueError(f"invalid closed-day manifest for {date}")
        entries = {item.get("archive"): item for item in manifest["files"]}
        selected = []
        for name in REQUIRED:
            entry = entries.get(name)
            path = directory / name
            if (not isinstance(entry, dict) or not path.is_file()
                    or file_sha256(path) != entry.get("archive_sha256")):
                raise ValueError(f"archive hash mismatch: {date}/{name}")
            selected.append({
                "name": name,
                "archive_sha256": entry["archive_sha256"],
                "content_sha256": entry["content_sha256"],
                "original_bytes": entry["original_bytes"],
                "compressed_bytes": entry["compressed_bytes"],
            })
        days.append({
            "date": date,
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "selected_files": selected,
        })
    return days


def jsonl(paths):
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSONL at {path.name}:{line_number}") from error
                yield value


def materialize(data_root, dates):
    if not dates or len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError("unique chronological dates required")
    days = load_days(data_root, dates)
    source = {
        "schema": "polymarket_closed_archive_bundle_v1",
        "data_root_role": "existing_read_only_collector_archive",
        "dates": days,
    }
    source_sha256 = hashlib.sha256(canonical(source).encode()).hexdigest()
    event_paths = [data_root / date / "event_changes.jsonl.gz" for date in dates]
    book_paths = [data_root / date / "book_observations.jsonl.gz" for date in dates]
    catalog, event_counts = build_event_catalog(jsonl(event_paths))
    result = materialize_books(jsonl(book_paths), catalog, source_sha256)
    result.update({
        "source_bundle": source,
        "source_bundle_sha256": source_sha256,
        "event_catalog_counts": event_counts,
        "event_catalog_games": len(catalog),
        "evidence_class": "historical_diagnostic",
        "scientific_admission": False,
        "test_opened": False,
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--dates", required=True, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = materialize(args.data_root, args.dates)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    print(canonical({
        "output": str(args.output),
        "source_bundle_sha256": result["source_bundle_sha256"],
        "event_catalog_games": result["event_catalog_games"],
        "rows": len(result["rows"]),
        "counts": result["counts"],
    }))


if __name__ == "__main__":
    main()
