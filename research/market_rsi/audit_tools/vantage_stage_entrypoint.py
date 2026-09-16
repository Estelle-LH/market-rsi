"""Execute one precommitted remote acquisition/decode; no research admission.

Caller separately verifies deployment and runs this in a bounded systemd cgroup.
The permanent claim survives SSH/app loss. A failure never triggers a retry.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types
from datetime import datetime, timezone

CODE_FILES = frozenset({
    "pinned_archive_prefix.py", "pinned_vantage_download.py",
    "guarded_sqlite_decode.py", "canary_sqlite_observations.py",
    "canary_activity_observations.py", "canary_sqlite_fixture.py",
    "remote_decode_canary.py", "vantage_stage_entrypoint.py",
})
CANARY_FILES = frozenset({
    "guarded_sqlite_decode.py", "canary_sqlite_observations.py",
    "canary_activity_observations.py", "canary_sqlite_fixture.py",
    "remote_decode_canary.py",
})


def now():
    return datetime.now(timezone.utc).isoformat()


def frozen_bytes(path, expected):
    if path.resolve(strict=True) != path:
        raise ValueError("noncanonical input")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o222 or before.st_nlink != 1:
        raise ValueError("non-frozen input")
    raw = path.read_bytes()
    after = path.lstat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("input changed while reading")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("input SHA mismatch")
    return raw


def write_once(path, value):
    with path.open("x") as f:
        json.dump(value, f, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    path.chmod(0o444)


def run(plan_path, expected_plan_sha):
    plan = json.loads(frozen_bytes(plan_path, expected_plan_sha))
    root = plan_path.parent
    if str(root) != "/opt/market-rsi-historical-20260910-01":
        raise ValueError("unexpected deployment root")
    if plan["prior_cumulative_bytes"] != 5_008_615_369 or plan["cap_bytes"] != 15_000_000_000:
        raise ValueError("unexpected cumulative accounting")
    if plan["decoded_upper_bound_bytes"] != 39_315_099_648 or plan["decode_reserve_bytes"] != 5_637_144_576:
        raise ValueError("unexpected storage commitment")
    if set(plan["code_hashes"]) != CODE_FILES:
        raise ValueError("complete exact import closure required")
    source_bytes = {}
    for name, digest in plan["code_hashes"].items():
        if Path(name).name != name:
            raise ValueError("flat code manifest required")
        source_bytes[name] = frozen_bytes(root / "code" / name, digest)
    decoder = Path("/usr/bin/zstd")
    if hashlib.sha256(decoder.read_bytes()).hexdigest() != plan["decoder_sha256"]:
        raise ValueError("native decoder changed")
    canary_path = root / "canary" / "result.json"
    canary = json.loads(frozen_bytes(canary_path, plan["canary_result_sha256"]))
    if canary.get("passed") is not True:
        raise ValueError("remote decoder canary did not pass")
    if canary.get("decoder_sha256") != plan["decoder_sha256"] or \
            canary.get("decoder_version") != plan["decoder_version"] or \
            canary.get("code_sha256") != {name: plan["code_hashes"][name] for name in CANARY_FILES}:
        raise ValueError("canary is not bound to this exact decoder and code closure")
    # Execute exactly the bytes just hashed: do not search the directory or read
    # stale .pyc files (Python -B only disables writes, not reads).
    loaded = {}
    for name in ("pinned_archive_prefix.py", "canary_activity_observations.py",
                 "canary_sqlite_observations.py", "guarded_sqlite_decode.py",
                 "pinned_vantage_download.py"):
        module_name = Path(name).stem
        if module_name in sys.modules:
            raise ValueError("unexpected previously loaded worker dependency")
        module = types.ModuleType(module_name)
        module.__file__ = str(root / "code" / name)
        sys.modules[module_name] = module
        exec(compile(source_bytes[name], module.__file__, "exec"), module.__dict__)
        loaded[module_name] = module
    pinned_vantage_download = loaded["pinned_vantage_download"]
    guarded_sqlite_decode = loaded["guarded_sqlite_decode"]
    lock = os.open(root / ".acquisition.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
            raise ValueError("invalid remote acquisition lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write_once(root / "execution-claim.json", {
            "started_at_utc": now(), "pid": os.getpid(), "plan_sha256": expected_plan_sha,
            "prior_cumulative_bytes": plan["prior_cumulative_bytes"],
            "new_body_reservation_bytes": 3_164_694_656,
            "reserved_cumulative_ceiling_bytes": 8_173_310_025,
            "automatic_retry": False, "paid_model_process": False,
            "primary_object_still_selected": True,
        })
        try:
            acquisition = pinned_vantage_download.download(
                root / "acquisition", plan_sha256=expected_plan_sha,
                prior_cumulative_bytes=plan["prior_cumulative_bytes"], max_seconds=1800)
            archive = root / "acquisition" / "polymarket-recorder-tape-vantage-b-20260603-20260701.db.zst"
            write_once(root / "decode-stage-start.json", {
                "started_at_utc": now(), "acquisition_result": "acquisition/result.json",
                "archive_bytes": archive.stat().st_size, "new_download_bytes": 0,
            })
            decoded = guarded_sqlite_decode.decode(
                archive, root / "decode",
                expected_sha256="9915c881cd5a598b831652664a1b761629c2c9303997332c9beef2af835d64a4",
                expected_bytes=3_164_694_656, decoder=decoder,
                expected_decoder_sha256=plan["decoder_sha256"],
                decoded_upper_bound_bytes=plan["decoded_upper_bound_bytes"],
                reserve_bytes=plan["decode_reserve_bytes"], max_seconds=1800)
            if decoded["decoded_bytes"] != plan["decoded_upper_bound_bytes"]:
                raise ValueError("decoded byte count differs from header commitment")
            write_once(root / "result.json", {
                "passed": True, "completed_at_utc": now(), "plan_sha256": expected_plan_sha,
                "acquisition_result": acquisition, "decode_result": decoded,
                "fresh_validation_admitted": False, "clean_data_proven": False,
                "scientific_source_choice_changed": False, "primary_pending": True,
                "paid_model_calls": 0, "automatic_retry": False,
                "claim_limit": "One selected object acquired and staged, not two-source completion or data QA.",
            })
        except BaseException as exc:
            write_once(root / "failure.json", {
                "failed_at_utc": now(), "error_type": type(exc).__name__,
                "automatic_retry": False, "reconciliation_required": True,
                "preserve_all_receipts_and_partials": True,
            })
            raise
    finally:
        os.close(lock)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    run(args.plan, args.plan_sha256)
