#!/usr/bin/env python3
"""Verify local-only paths and hashes without printing secrets or paths."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def absolute_regular(path):
    path = Path(path)
    return path.is_absolute() and path.resolve() == path and path.is_file() and not path.is_symlink()


def absolute_executable(path):
    """Accept a pinned interpreter symlink when its resolved target is a real file."""
    path = Path(path)
    resolved = path.resolve()
    return path.is_absolute() and path.is_file() and resolved.is_file() and not resolved.is_symlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--require-idle", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "round17_local_artifact_manifest_v1":
        raise ValueError("Unsupported manifest schema")

    checks = {}
    source = Path(manifest["source"]["path"])
    checks["source_absolute_directory"] = source.is_absolute() and source.is_dir()
    if checks["source_absolute_directory"]:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, check=True,
                              capture_output=True, text=True).stdout.strip()
        checks["source_commit"] = head == manifest["source"]["commit"]
        checks["source_tracked_clean"] = (
            subprocess.run(["git", "diff", "--quiet"], cwd=source).returncode == 0
            and subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=source).returncode == 0
        )

    python = Path(manifest["python"]["path"])
    checks["python"] = absolute_executable(python) and sha256(python) == manifest["python"]["sha256"]

    credential = Path(manifest["credential"]["path"])
    checks["credential_regular"] = absolute_regular(credential)
    checks["credential_owner_only"] = False
    checks["credential_shape"] = False
    if checks["credential_regular"]:
        info = credential.stat()
        checks["credential_owner_only"] = info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
        entries = [line.split("=", 1)[1].strip() for line in credential.read_text().splitlines()
                   if line.startswith("OPENAI_API_KEY=")]
        checks["credential_shape"] = len(entries) == 1 and bool(entries[0]) and not any(c.isspace() for c in entries[0])

    artifacts = manifest.get("artifacts", [])
    checks["artifact_names_unique"] = len({x["name"] for x in artifacts}) == len(artifacts)
    artifact_matches = 0
    for item in artifacts:
        path = Path(item["path"])
        if absolute_regular(path) and sha256(path) == item["sha256"]:
            artifact_matches += 1
    checks["artifact_hashes"] = artifact_matches == len(artifacts) and bool(artifacts)

    ledger = Path(manifest["ledger"]["path"])
    checks["ledger_regular"] = absolute_regular(ledger)
    pending = None
    if checks["ledger_regular"]:
        with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            checks["ledger_schema"] = {"config", "requests", "concurrent_request_owners"} <= tables
            if checks["ledger_schema"]:
                pending = db.execute(
                    "SELECT COUNT(*) FROM requests WHERE status NOT IN ('settled','settled_upper_bound')"
                ).fetchone()[0]
                checks["ledger_idle"] = pending == 0 if args.require_idle else True

    report = {
        "schema": "round17_local_manifest_verification_v1",
        "checks": checks,
        "artifacts_verified": artifact_matches,
        "artifacts_declared": len(artifacts),
        "pending_requests": pending,
        "pass": bool(checks) and all(checks.values()),
    }
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
