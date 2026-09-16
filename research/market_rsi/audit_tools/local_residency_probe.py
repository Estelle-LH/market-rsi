"""Metadata-only preflight: never hydrate, import, or hash research inputs.

Run this with Python -I -B before any repository imports on a cloud-backed Mac.
Passing is only a point-in-time residency observation, not an integrity check.
Content reads still require a timeout because residency can change afterwards.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import stat


DATALESS_FLAG = getattr(stat, "SF_DATALESS", 0x40000000)


def inspect_path(path: Path) -> dict:
    path = Path(path)
    row = {"path": str(path)}
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {**row, "status": "missing"}
    except OSError as error:
        return {**row, "status": "stat_error", "errno": error.errno}
    row.update(bytes=metadata.st_size, mtime_ns=metadata.st_mtime_ns)
    if stat.S_ISLNK(metadata.st_mode):
        return {**row, "status": "symlink_not_followed"}
    if not stat.S_ISREG(metadata.st_mode):
        return {**row, "status": "not_regular"}
    flags = getattr(metadata, "st_flags", None)
    if flags is None:
        return {**row, "status": "residency_flag_unavailable"}
    return {
        **row,
        "status": "dataless" if flags & DATALESS_FLAG else "resident_at_stat",
        "flags": flags,
    }


def make_report(paths) -> dict:
    # Do not resolve symlinks. Preserve the identity that the caller provided.
    rows = [inspect_path(Path(p)) for p in sorted({str(p) for p in paths})]
    counts = dict(sorted(Counter(row["status"] for row in rows).items()))
    return {
        "schema": "market-rsi-local-residency-v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(rows),
        "counts": counts,
        "preflight_clear_at_stat": bool(rows)
        and all(row["status"] == "resident_at_stat" for row in rows),
        "content_bytes_read": 0,
        "scientific_hashes_verified": False,
        "budget_reconciled": False,
        "raw_download_authorized": False,
        "limitations": [
            "File flags can change immediately after this observation.",
            "No bytes, source hashes, ledger arithmetic, or data quality checked.",
            "Dataless does not establish loss or corruption of the remote copy.",
            "Later content reads need an independent timeout and hash check.",
        ],
        "files": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--directory", action="append", default=[], type=Path,
                        help="Inspect immediate children only; never their content.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = list(args.paths)
    for directory in args.directory:
        # Explicit caller-owned directories only; no recursive traversal.
        if directory.is_symlink() or not directory.is_dir():
            parser.error("directory must be a real existing directory")
        paths.extend(directory.iterdir())
    report = make_report(paths)
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    output = args.output_dir / "residency.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"artifact": str(output), "file_count": report["file_count"],
                      "counts": report["counts"],
                      "preflight_clear_at_stat": report["preflight_clear_at_stat"]}))
    return 0 if report["preflight_clear_at_stat"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
