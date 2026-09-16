"""One-time, authorization-bound engineering probe of two selected archives.

No automatic retries, bulk transfer, market rows, model calls, or Test access.
Run under an independent parent timeout. Existing ingest lock is held throughout.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/historical-selected-prefix-preflight-20260910-01"
AUTH = ROOT / "artifacts/historical-acquisition-authorization-20260910-01/authorization.json"
MODULE = ROOT / "audit_tools/pinned_archive_prefix.py"
MODULE_SHA = "1790ec71a6fa514c1304ac32530ce89ba7173cb47480ea163ec5e8e5f9af47f5"
TEST_SHA = "685e6742c00f30e3c7416761f33a9bcc25f8aeeb38366486ec69ef82106804fb"


def read(path, expected=None):
    path = Path(path)
    if path.resolve(strict=True) != path:
        raise ValueError("symlink or noncanonical input")
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_flags & 0x40000000:
        raise ValueError("input not resident regular file")
    if s.st_size > 4_000_000:
        raise ValueError("unexpected input size")
    value = path.read_bytes()
    after = path.lstat()
    if (s.st_ino, s.st_size, s.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("input changed during read")
    digest = hashlib.sha256(value).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError("input commitment mismatch: " + path.name)
    return value, digest


def write_once(name, obj):
    with (OUTPUT / name).open("x") as f:
        json.dump(obj, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    (OUTPUT / name).chmod(0o444)


def main():
    auth_bytes, auth_sha = read(AUTH)
    auth = json.loads(auth_bytes)
    if auth["cumulative_download_cap_bytes"] != 15_000_000_000 or auth["experiment_cap_usd"] != "200":
        raise ValueError("unexpected authorization cap")
    if auth["prior_accounted_payload_bytes"] != 5_008_484_297:
        raise ValueError("prior transfer accounting changed")
    for prefix in ("prior_accounting", "controller_decision", "controller_proposal"):
        read(ROOT / auth[prefix + "_path"], auth[prefix + "_file_sha256"])
    read(MODULE, MODULE_SHA)
    read(ROOT / "audit_tools/test_pinned_archive_prefix.py", TEST_SHA)
    module = runpy.run_path(str(MODULE))
    for obj in auth["selected_objects"]:
        if obj["dataset"] != module["DATASET"] or obj["revision"] != module["REVISION"]:
            raise ValueError("source identity mismatch")
        expected = module["ARCHIVES"][obj["filename"]]
        if any(obj[k] != expected[k] for k in ("bytes", "sha256")):
            raise ValueError("object commitment mismatch")
    if len(auth["selected_objects"]) != 2:
        raise ValueError("expected exactly two selected objects")
    verified = json.loads(read(ROOT / "artifacts/historical-local-hydration-20260910-01/verification.json")[0])
    frozen_rows = [x for x in verified["files"] if x.get("expected_sha256")]
    if len(frozen_rows) != 367 or any(x["status"] != "hash_verified" for x in frozen_rows):
        raise ValueError("frozen content verification missing")
    for row in frozen_rows:
        read(row["path"], row["expected_sha256"])

    fd = os.open(ROOT / "artifacts/historical-ingest-download.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
            raise ValueError("invalid global acquisition lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        OUTPUT.mkdir(mode=0o700, exist_ok=False)
        write_once("execution.json", {
            "schema": "authorized_prefix_execution_v1",
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(), "authorization_sha256": auth_sha,
            "module_sha256": MODULE_SHA, "tests_sha256": TEST_SHA,
            "driver_sha256": read(Path(__file__))[1], "offline_tests_passed": 24,
            "prior_payload_bytes": auth["prior_accounted_payload_bytes"],
            "maximum_reserved_body_bytes": 2 * 5 * 65536,
            "cap_bytes": 15_000_000_000, "objects": auth["selected_objects"],
            "global_lock": "artifacts/historical-ingest-download.lock",
            "only_prefix_and_100_byte_header": True, "bulk_admitted": False,
            "scientific_admission": False, "automatic_retry": False,
        })
        cumulative = auth["prior_accounted_payload_bytes"]
        results = []
        for index, obj in enumerate(auth["selected_objects"]):
            result = module["probe"](obj["filename"], OUTPUT / f"object-{index + 1}",
                prior_cumulative_bytes=cumulative, max_seconds=25)
            cumulative = result["cumulative_actual_response_body_bytes"]
            results.append(result)
            print(json.dumps({"object": index + 1, "passed": True, "header": result["header"]}), flush=True)
        write_once("accounting.json", {
            "passed": True, "previous_payload_bytes": auth["prior_accounted_payload_bytes"],
            "new_payload_bytes": cumulative - auth["prior_accounted_payload_bytes"],
            "cumulative_payload_bytes": cumulative,
            "remaining_payload_cap_bytes": 15_000_000_000 - cumulative,
            "accounting_scope": "Application-consumed raw response bodies, not full wire traffic.",
            "unresolved_request_body_reservations": 0,
            "full_object_hash_verified": False, "bulk_admitted": False,
            "outputs": [r["prefix_file"] for r in results],
        })
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
