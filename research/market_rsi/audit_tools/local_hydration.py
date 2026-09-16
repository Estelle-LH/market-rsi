"""Explicit, byte-capped iCloud hydration requests; never edit selected originals.

Use Python -I -B. Preparation reads only a resident frozen manifest in a bounded
stdlib subprocess. Plans include originals AND source snapshots. Requests run in
one independently timed Foundation subprocess per batch. Acceptance is not file
residency, content integrity, budget reconciliation, or paid-work authorization.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


DATALESS_FLAG = getattr(stat, "SF_DATALESS", 0x40000000)
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
MAX_BATCH_SIZE = 32
MAX_SELECTED_FILES = 2048


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def checked_path(root, value, *, directory=False, lstat=None):
    """Validate lexical containment and every component without resolving links."""
    lstat = lstat or Path.lstat
    root = Path(root)
    raw = os.fspath(value)
    if not root.is_absolute() or not raw or any(ord(c) < 32 for c in raw):
        raise ValueError("root must be absolute; paths must be nonempty and printable")
    if ".." in Path(raw).parts or ".." in root.parts:
        raise ValueError("parent traversal is forbidden")
    path = Path(raw) if Path(raw).is_absolute() else root / raw
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ValueError("path is outside research root") from None
    # Include root and its ancestors, so a symlinked research root cannot escape.
    components = list(reversed(path.parents)) + [path]
    for component in components:
        metadata = lstat(component)
        final = component == path
        expected = stat.S_ISDIR if not final or directory else stat.S_ISREG
        if stat.S_ISLNK(metadata.st_mode) or not expected(metadata.st_mode):
            raise ValueError("symlink or unexpected file type: " + str(component))
    if not directory and not relative.parts:
        raise ValueError("research root is not a file")
    return path, metadata


def inspect(root, path, *, lstat=None):
    path, metadata = checked_path(root, path, lstat=lstat)
    flags = getattr(metadata, "st_flags", None)
    if flags is None:
        raise ValueError("residency flags unavailable: " + str(path))
    return {"path": str(path), "bytes": metadata.st_size,
            "mtime_ns": metadata.st_mtime_ns, "device": metadata.st_dev,
            "inode": metadata.st_ino, "flags": flags,
            "status": "dataless" if flags & DATALESS_FLAG else "resident_at_stat"}


_READ_RESIDENT = r"""
import hashlib, json, os, stat, sys
p, limit, identity = sys.argv[1], int(sys.argv[2]), json.loads(sys.argv[3])
fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
 s = os.fstat(fd)
 assert stat.S_ISREG(s.st_mode) and hasattr(s, 'st_flags')
 assert not s.st_flags & getattr(stat, 'SF_DATALESS', 0x40000000)
 assert [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns] == identity
 assert s.st_size <= limit
 with os.fdopen(fd, 'rb', closefd=False) as f: data = f.read(limit + 1)
 assert len(data) == s.st_size and len(data) <= limit
 t = os.fstat(fd)
 assert [t.st_dev, t.st_ino, t.st_size, t.st_mtime_ns] == identity
 print(json.dumps({'text': data.decode('utf-8'), 'sha256': hashlib.sha256(data).hexdigest()}))
finally:
 os.close(fd)
"""


def read_resident(row, limit, *, timeout_seconds=20):
    if not 0 < timeout_seconds <= 20 or row["status"] != "resident_at_stat":
        raise ValueError("bounded resident read required")
    identity = [row[k] for k in ("device", "inode", "bytes", "mtime_ns")]
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _READ_RESIDENT, row["path"],
         str(limit), json.dumps(identity)], capture_output=True, text=True,
        timeout=timeout_seconds, check=False)
    if result.returncode:
        raise ValueError("resident read failed; no child stderr retained")
    return json.loads(result.stdout)


def write_once(path, value):
    """Exclusive creation and read-only mode; never overwrite an audit artifact."""
    with Path(path).open("xb") as stream:
        stream.write(canonical(value) + b"\n")
    Path(path).chmod(0o444)


def prepare(root, manifest, output_dir, *, files=(), directories=(),
            max_bytes=DEFAULT_MAX_BYTES, lstat=None, manifest_reader=None):
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    root, _ = checked_path(root, root, directory=True, lstat=lstat)
    manifest_row = inspect(root, manifest, lstat=lstat)
    if manifest_row["bytes"] > max_bytes or manifest_row["status"] != "resident_at_stat":
        raise ValueError("manifest must be resident and within the cumulative cap")
    loaded = (manifest_reader or read_resident)(manifest_row, max_bytes)
    document = json.loads(loaded["text"])
    hashes = document.get("source_hashes") if isinstance(document, dict) else None
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("manifest must contain nonempty source_hashes")
    selections = {manifest_row["path"]: (loaded["sha256"], "manifest")}

    def select(path, expected_hash=None, role="additional"):
        path, _ = checked_path(root, path, lstat=lstat)
        existing = selections.get(str(path))
        if existing and existing[0] and expected_hash and existing[0] != expected_hash:
            raise ValueError("conflicting expected hashes")
        selections[str(path)] = existing or (expected_hash, role)
        if len(selections) > MAX_SELECTED_FILES:
            raise ValueError("too many selected files for a bounded local recovery")

    snapshot_root = Path(manifest_row["path"]).parent / "source-snapshot"
    for name, expected_hash in hashes.items():
        if not isinstance(name, str) or Path(name).is_absolute():
            raise ValueError("source names must be research-root relative")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError("invalid source sha256")
        select(root / name, expected_hash, "source")
        select(snapshot_root / name, expected_hash, "snapshot")
    for path in files:
        select(path)
    for directory in directories:
        directory, _ = checked_path(root, directory, directory=True, lstat=lstat)
        # Only explicitly selected directories, immediate children, no recursion.
        for path in directory.iterdir():
            select(path)
    rows = []
    total = 0
    for path, (expected_hash, role) in sorted(selections.items()):
        row = inspect(root, path, lstat=lstat)
        if path == manifest_row["path"] and any(
                row[k] != manifest_row[k] for k in ("bytes", "device", "inode", "mtime_ns")):
            raise ValueError("manifest metadata changed during preparation")
        total += row["bytes"]
        if total > max_bytes:
            raise ValueError("cumulative selected bytes exceed cap")
        rows.append({**row, "expected_sha256": expected_hash, "role": role})
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    checked_path(root, output_dir.parent, directory=True, lstat=lstat)
    if output_dir.name in ("", ".", "..") or ".." in output_dir.parts:
        raise ValueError("invalid output directory")
    plan = {"schema": "market-rsi-local-hydration-v1", "root": str(root),
            "output_dir": str(output_dir), "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest_sha256": loaded["sha256"], "max_bytes": max_bytes,
            "total_selected_bytes": total, "files": rows,
            "scientific_hashes_verified": False, "budget_reconciled": False,
            "paid_work_authorized": False, "raw_download_authorized": False}
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    write_once(output_dir / "claim.json", {"plan_sha256": digest(plan),
               "purpose": "Explicit local file hydration only; no paid calls or original writes"})
    write_once(output_dir / "plan.json", plan)
    return plan


def foundation_requester(paths, *, timeout_seconds=20):
    if not 0 < timeout_seconds <= 20 or not 0 < len(paths) <= MAX_BATCH_SIZE:
        raise ValueError("request must have 1-32 paths and a timeout no greater than 20s")
    # JSON literals prevent paths from becoming executable JavaScript.
    script = ("ObjC.import('Foundation'); var paths=" + json.dumps(paths) + ";"
              "JSON.stringify(paths.map(function(p){var err=Ref();"
              "var ok=$.NSFileManager.defaultManager.startDownloadingUbiquitousItemAtURLError("
              "$.NSURL.fileURLWithPath(p),err);"
              "return {path:p,requestAccepted:Boolean(ok),errorPresent:!Boolean(ok)};}));")
    try:
        result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                                capture_output=True, text=True, timeout=timeout_seconds,
                                check=False)
    except subprocess.TimeoutExpired:
        return [{"path": p, "requestAccepted": None, "outcome": "timeout_unknown"} for p in paths]
    if result.returncode:
        return [{"path": p, "requestAccepted": None, "outcome": "process_error_unknown"} for p in paths]
    try:
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or len(rows) != len(paths):
            raise ValueError("unexpected response count")
        for row, path in zip(rows, paths):
            if row.get("path") != path or not isinstance(row.get("requestAccepted"), bool):
                raise ValueError("unexpected response")
        return [{"path": r["path"], "requestAccepted": r["requestAccepted"],
                 "outcome": "accepted" if r["requestAccepted"] else "rejected"} for r in rows]
    except (ValueError, TypeError, AttributeError):
        return [{"path": p, "requestAccepted": None, "outcome": "invalid_response_unknown"} for p in paths]


def poll(plan, *, lstat=None):
    rows = []
    for before in plan["files"]:
        try:
            after = inspect(plan["root"], before["path"], lstat=lstat)
            if any(after[k] != before[k] for k in ("bytes", "device", "inode", "mtime_ns")):
                after["status"] = "identity_or_size_changed"
        except (OSError, ValueError):
            after = {"path": before["path"], "status": "metadata_rejected"}
        rows.append(after)
    return {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "files": rows,
            "all_resident_at_stat": bool(rows) and all(r["status"] == "resident_at_stat" for r in rows),
            "content_bytes_read": 0, "scientific_hashes_verified": False,
            "budget_reconciled": False, "paid_work_authorized": False}


def request_batch(plan, output_dir, *, batch_index=0, batch_size=16,
                  timeout_seconds=20, requester=None, lstat=None, claim_reader=None):
    if (type(batch_index) is not int or batch_index < 0 or type(batch_size) is not int
            or not 1 <= batch_size <= MAX_BATCH_SIZE):
        raise ValueError("invalid bounded batch selection")
    if not 0 < timeout_seconds <= 20:
        raise ValueError("timeout must be no greater than 20 seconds")
    output_dir, _ = checked_path(plan["root"], output_dir, directory=True, lstat=lstat)
    if str(output_dir) != plan["output_dir"]:
        raise ValueError("output directory differs from prepared plan")
    # Verify the in-memory plan against its immutable preparation claim.
    claim_row = inspect(plan["root"], output_dir / "claim.json", lstat=lstat)
    claim = json.loads((claim_reader or read_resident)(claim_row, 4096)["text"])
    if claim.get("plan_sha256") != digest(plan):
        raise ValueError("prepared plan changed")
    candidates = [r for r in plan["files"] if r["status"] == "dataless"]
    selected = candidates[batch_index * batch_size:(batch_index + 1) * batch_size]
    if not selected:
        raise ValueError("batch has no planned dataless files")
    current = poll({**plan, "files": selected}, lstat=lstat)["files"]
    if any(r["status"] not in ("dataless", "resident_at_stat") for r in current):
        raise ValueError("planned input metadata changed; prepare a fresh audited run")
    paths = [r["path"] for r in current if r["status"] == "dataless"]
    # One claim per plan path: changing batch size cannot accidentally retry it.
    for row in selected:
        claim_path = output_dir / ("requested-" + hashlib.sha256(row["path"].encode()).hexdigest() + ".json")
        if claim_path.exists() or claim_path.is_symlink():
            raise FileExistsError("path already claimed; never retry automatically")
    write_once(output_dir / ("batch-" + str(batch_index).zfill(4) + "-claim.json"),
               {"batch_index": batch_index, "paths": paths, "plan_sha256": digest(plan)})
    for row in selected:
        write_once(output_dir / ("requested-" + hashlib.sha256(row["path"].encode()).hexdigest() + ".json"),
                   {"path": row["path"], "batch_index": batch_index, "plan_sha256": digest(plan)})
    responses = (requester or foundation_requester)(paths, timeout_seconds=timeout_seconds) if paths else []
    observation = poll({**plan, "files": selected}, lstat=lstat)
    report = {"batch_index": batch_index, "requests": responses, "observation": observation,
              "acceptance_is_residency_or_integrity": False, "automatic_retry": False}
    write_once(output_dir / ("batch-" + str(batch_index).zfill(4) + ".json"), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--file", action="append", default=[], type=Path)
    parser.add_argument("--directory", action="append", default=[], type=Path)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--request", action="store_true", help="Request one batch after preparation")
    parser.add_argument("--batch-index", type=int, default=0)
    args = parser.parse_args()
    plan = prepare(args.root, args.manifest, args.output_dir, files=args.file,
                   directories=args.directory, max_bytes=args.max_bytes)
    summary = {"plan": str(Path(plan["output_dir"]) / "plan.json"),
               "selected_bytes": plan["total_selected_bytes"], "files": len(plan["files"])}
    if args.request:
        summary["batch"] = request_batch(plan, plan["output_dir"], batch_index=args.batch_index)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
