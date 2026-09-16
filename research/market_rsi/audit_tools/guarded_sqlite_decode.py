"""Bounded local zstd -> SQLite staging; no download or research admission.

The caller must separately prove the compressed artifact's acquisition authority.
This utility accepts existing, frozen bytes only. It uses a hash-pinned native
decoder, pipes stdout, checks its exit status, preserves failures and never uses
--force, --rm or publisher-supplied commands. A successful decode is NOT database
integrity, data quality, model training or fresh-test admission.
"""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import time

from canary_sqlite_observations import _check_path, _deadline, _hash_fd, _identity


CHUNK_BYTES = 65536
SQLITE_MAGIC = b"SQLite format 3\x00"


def _json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def storage_plan(*, free_bytes, decoded_upper_bound_bytes, reserve_bytes,
                 compressed_bytes_not_yet_present=0, additional_working_bytes=0):
    values = (free_bytes, decoded_upper_bound_bytes, reserve_bytes,
              compressed_bytes_not_yet_present, additional_working_bytes)
    if any(type(v) is not int or v < 0 for v in values) or decoded_upper_bound_bytes == 0:
        raise ValueError("nonnegative integer space terms and positive decode bound required")
    required = decoded_upper_bound_bytes + reserve_bytes + compressed_bytes_not_yet_present + additional_working_bytes
    return {"free_bytes": free_bytes, "required_free_bytes": required,
            "fits": free_bytes >= required,
            "compressed_bytes_already_on_disk_counted_again": False,
            "new_authority_granted": False}


def _stop_exact(process):
    if process is None:
        return None
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    return process.returncode


def decode(archive, output, *, expected_sha256, expected_bytes, decoder,
           expected_decoder_sha256, decoded_upper_bound_bytes, reserve_bytes,
           max_seconds=3600, free_bytes_at=None):
    """Create a permanent per-run directory; never retry or reuse its name.

    Disk-space checks are conservative cooperative safeguards, not an OS quota.
    Another process can consume disk after a check; write errors remain failures.
    Jobs sharing this output parent/device are serialized. The final name appears
    only after decoder exit 0, hash checks, fsync and a SQLite magic check.
    """
    archive, output, decoder = Path(archive), Path(output), Path(decoder)
    for value in (expected_sha256, expected_decoder_sha256):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("exact compressed and decoder SHA256 commitments required")
    if type(expected_bytes) is not int or expected_bytes <= 0:
        raise ValueError("positive compressed size required")
    storage_plan(free_bytes=0, decoded_upper_bound_bytes=decoded_upper_bound_bytes, reserve_bytes=reserve_bytes)
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("positive finite wall deadline required")
    if not output.is_absolute() or output.parent != output.parent.resolve(strict=True):
        raise ValueError("canonical existing output parent required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("permanent decode ID already claimed")
    source_identity = _check_path(archive)
    if source_identity[2] != expected_bytes:
        raise ValueError("compressed size mismatch")
    if not decoder.is_absolute() or decoder != decoder.resolve(strict=True) or not decoder.is_file():
        raise ValueError("canonical decoder binary required")
    decoder_hash = hashlib.sha256(decoder.read_bytes()).hexdigest()
    if decoder_hash != expected_decoder_sha256:
        raise ValueError("decoder hash mismatch")
    free_bytes_at = free_bytes_at or (lambda path: shutil.disk_usage(path).free)
    end = time.monotonic() + max_seconds
    output.mkdir(mode=0o700, exist_ok=False)
    _json(output / "claim.json", {
        "schema": "local_sqlite_decode_claim_v1", "archive": str(archive),
        "compressed_sha256": expected_sha256, "compressed_bytes": expected_bytes,
        "decoder": str(decoder), "decoder_sha256": decoder_hash,
        "decoded_upper_bound_bytes": decoded_upper_bound_bytes, "reserve_bytes": reserve_bytes,
        "max_seconds": max_seconds, "new_download_bytes": 0, "automatic_retry": False,
        "acquisition_authority_added": False,
    })
    process = None
    source_fd = lock_fd = None
    partial = output / "payload.partial"
    selector = selectors.DefaultSelector()
    written = 0
    decoded_hash = hashlib.sha256()
    stderr_hash, stderr_bytes = hashlib.sha256(), 0
    initial_magic = b""
    source_verified = False
    try:
        # Cooperative lock is a metadata file, never a decoded-data reservation.
        lock = output.parent / f".sqlite-decode-device-{output.parent.stat().st_dev}.lock"
        lock_fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        lock_stat = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1:
            raise ValueError("invalid cooperative lock file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source_fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW)
        if _identity(os.fstat(source_fd)) != source_identity or _hash_fd(source_fd, end) != expected_sha256:
            raise ValueError("compressed source hash/identity mismatch")
        source_verified = True
        plan = storage_plan(free_bytes=free_bytes_at(output),
                            decoded_upper_bound_bytes=decoded_upper_bound_bytes, reserve_bytes=reserve_bytes)
        _json(output / "storage-check.json", plan)
        if not plan["fits"]:
            raise ValueError("insufficient free space before decode; decoder not started")
        # Literal flags were checked against this installed decoder's help.
        command = [str(decoder), "-d", "-c", "-q", "--no-progress", "--no-pass-through", "-M128MB", "--", str(archive)]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env={"LANG": "C", "LC_ALL": "C"})
        _json(output / "process.json", {"pid": process.pid, "argv": command, "paid_process": False})
        selector.register(process.stdout, selectors.EVENT_READ, "payload")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        with partial.open("xb", buffering=0) as target:
            while selector.get_map():
                _deadline(end)
                for key, _ in selector.select(timeout=min(0.2, max(0, end - time.monotonic()))):
                    chunk = os.read(key.fd, CHUNK_BYTES)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if key.data == "stderr":
                        stderr_hash.update(chunk)
                        stderr_bytes += len(chunk)
                        continue
                    if written + len(chunk) > decoded_upper_bound_bytes:
                        raise ValueError("decoded output would exceed explicit byte bound")
                    if free_bytes_at(output) < reserve_bytes + len(chunk):
                        raise ValueError("free-space reserve reached during decode")
                    initial_magic = (initial_magic + chunk)[:len(SQLITE_MAGIC)]
                    if len(initial_magic) == len(SQLITE_MAGIC) and initial_magic != SQLITE_MAGIC:
                        raise ValueError("decoded artifact is not a SQLite file")
                    offset = 0
                    while offset < len(chunk):
                        n = target.write(chunk[offset:])
                        if not n:
                            raise OSError("short decoded-file write")
                        decoded_hash.update(chunk[offset:offset + n])
                        written += n
                        offset += n
            _deadline(end)
            code = process.wait(timeout=max(0.001, end - time.monotonic()))
            if code != 0:
                raise ValueError(f"decoder failed with exit status {code}; no complete artifact")
            if initial_magic != SQLITE_MAGIC:
                raise ValueError("decoded artifact lacks complete SQLite magic")
            target.flush()
            os.fsync(target.fileno())
        if _check_path(archive) != source_identity or _identity(os.fstat(source_fd)) != source_identity \
                or _hash_fd(source_fd, end) != expected_sha256:
            raise ValueError("compressed archive changed during decode")
        if hashlib.sha256(decoder.read_bytes()).hexdigest() != expected_decoder_sha256:
            raise ValueError("decoder changed during run")
        partial.chmod(0o444)
        completed = output / "payload.sqlite"
        # link() refuses an existing destination; removing this staging name
        # removes no bytes because the verified final hard link retains them.
        os.link(partial, completed)
        partial.unlink()
        result = {
            "schema": "local_sqlite_decode_result_v1", "passed": True,
            "compressed_sha256": expected_sha256, "compressed_bytes": expected_bytes,
            "decoded_sha256": decoded_hash.hexdigest(), "decoded_bytes": written,
            "decoded_file": str(completed), "source_unchanged": True,
            "decoder_pid": process.pid, "decoder_exit_code": code, "process_reaped": True,
            "decoder_sha256": decoder_hash, "stderr_bytes": stderr_bytes,
            "stderr_sha256": stderr_hash.hexdigest(), "new_download_bytes": 0,
            "acquisition_admitted": False, "database_integrity_checked": False,
            "clean_session_admitted": False, "fresh_validation_admitted": False,
            "claim_limit": "Lossless local staging only; no data QA or research outcome.",
        }
        _json(output / "result.json", result)
        return result
    except Exception as exc:
        code = _stop_exact(process)
        if partial.exists():
            partial.chmod(0o444)
        _json(output / "failure.json", {
            "passed": False, "error_type": type(exc).__name__, "reason": str(exc),
            "decoder_pid": process.pid if process else None, "decoder_exit_code": code,
            "process_reaped": process is None or process.poll() is not None,
            "compressed_verified_before_decode": source_verified,
            "prefix_bytes_written": written, "prefix_sha256": decoded_hash.hexdigest(),
            "stderr_bytes_drained": stderr_bytes, "stderr_sha256": stderr_hash.hexdigest(),
            "automatic_retry": False, "new_download_bytes": 0,
            "complete_result_available": False,
        })
        raise
    finally:
        selector.close()
        if process is not None:
            _stop_exact(process)
            for pipe in (process.stdout, process.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
        if source_fd is not None:
            os.close(source_fd)
        if lock_fd is not None:
            os.close(lock_fd)
