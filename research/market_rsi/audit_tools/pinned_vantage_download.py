"""One-shot, stdlib-only acquisition of the second pinned Vantage archive.

Copy this file AND the reviewed pinned_archive_prefix.py to the same remote
directory. No repository imports, decoding, subprocesses, credentials, retries,
resume, or scientific admission. The caller owns approval/context binding,
global locks, prior-transfer reconciliation, and remote deployment. A syntactically
valid plan hash is recorded, never treated as evidence of authorization.

Receipts count response-body bytes returned to this reader, not wire/TLS traffic.
An interrupted read leaves its durable request reservation unresolved. Every
output ID, including a failed one, is permanently consumed. Failed partials stay.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import sys
from urllib.parse import urljoin

import pinned_archive_prefix as prefix


FILENAME = "polymarket-recorder-tape-vantage-b-20260603-20260701.db.zst"
DATASET = "oraclemangle/polymarket-canary-tape"
REVISION = "0f09fdb48f703d672a648c562e3f6398f45eb168"
OBJECT_BYTES = 3_164_694_656
OBJECT_SHA256 = "9915c881cd5a598b831652664a1b761629c2c9303997332c9beef2af835d64a4"
PRIOR_BYTES_FLOOR = 5_008_615_369
CAP_BYTES = 15_000_000_000
DECODED_BYTES = 39_315_099_648
QA_BYTES = 256 * 1024 * 1024
RESERVE_BYTES = 5 * 1024 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SOCKET_SECONDS = 20
MAX_SECONDS = 1800
MAX_REDIRECTS = prefix.MAX_REDIRECTS
REQUEST_HEADERS = {
    "Range": f"bytes=0-{OBJECT_BYTES - 1}",
    "Accept-Encoding": "identity", "Connection": "close",
    "User-Agent": "pinned-vantage-one-shot-acquisition/1",
}


class HTTPSResponse(prefix.HTTPSResponse):
    """Reuse the reviewed exact-host connection, but fill one bounded bulk read.

    The inherited protocol method name is read1; unlike the prefix probe, its
    implementation deliberately uses HTTPResponse.read(amount). This avoids
    fsyncing every short TLS record. One durable outstanding read reservation
    remains at most 1 MiB. A timeout may consume buffered bytes without returning
    them, so the caller preserves that reservation as unresolved and never retries.
    Explicit-amount read returns available bytes on EOF; those bytes are retained.
    """
    @staticmethod
    def _timeout(timeout):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) \
                or not 0 < timeout <= SOCKET_SECONDS:
            raise ValueError("bulk socket timeout must be positive and at most 20 seconds")
        return timeout

    def __init__(self, url, headers, timeout):
        super().__init__(url, headers, self._timeout(timeout))

    def read1(self, amount, timeout):
        if type(amount) is not int or not 0 < amount <= CHUNK_BYTES:
            raise ValueError("bulk read must be positive and at most 1 MiB")
        timeout = self._timeout(timeout)
        if self.connection.sock is not None:
            self.connection.sock.settimeout(timeout)
        return self.response.read(amount)


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _append(stream, value):
    """Own timestamped durable receipt writer; the frozen prefix helper is unchanged."""
    record = {**value, "recorded_at_utc": _utc_now()}
    stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
    return record


def _exclusive(output_fd, name, mode="w"):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=output_fd)
    return os.fdopen(fd, mode, buffering=0 if "b" in mode else -1)


def _json(output_fd, name, value):
    with _exclusive(output_fd, name) as stream:
        record = _append(stream, value)
        os.fchmod(stream.fileno(), 0o444)
    os.fsync(output_fd)
    return record


class _Status:
    """Optional atomic status owned by this job; never replace a foreign inode."""
    def __init__(self, output_fd, enabled):
        self.fd, self.enabled, self.sequence, self.previous = output_fd, enabled, 0, None

    def update(self, **value):
        if not self.enabled:
            return
        if self.previous is None:
            try:
                os.stat("status.json", dir_fd=self.fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("foreign monitor status exists")
        else:
            current = os.stat("status.json", dir_fd=self.fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != self.previous \
                    or not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                raise ValueError("monitor status ownership changed")
        name = f"status-{self.sequence:08d}.tmp"
        self.sequence += 1
        _json(self.fd, name, {"schema": "pinned_vantage_status_v1", **value})
        os.replace(name, "status.json", src_dir_fd=self.fd, dst_dir_fd=self.fd)
        current = os.stat("status.json", dir_fd=self.fd, follow_symlinks=False)
        self.previous = current.st_dev, current.st_ino
        os.fsync(self.fd)


def validate_headers(response):
    """Admit a full 200, or the exact full-object 206 range we requested."""
    if response.status not in (200, 206):
        raise ValueError("expected full HTTP 200 or exact full-range 206")
    header = prefix._one_header
    if header(response.headers, "Content-Length") != str(OBJECT_BYTES):
        raise ValueError("Content-Length differs from the full pinned byte commitment")
    content_range = header(response.headers, "Content-Range", False)
    if response.status == 206:
        if content_range != f"bytes 0-{OBJECT_BYTES - 1}/{OBJECT_BYTES}":
            raise ValueError("Content-Range differs from the requested complete range")
    elif content_range is not None:
        raise ValueError("HTTP 200 must not contain Content-Range")
    if header(response.headers, "Content-Encoding", False) not in (None, "identity"):
        raise ValueError("content encoding is forbidden")
    if header(response.headers, "Transfer-Encoding", False) is not None:
        raise ValueError("transfer encoding is forbidden")


def _capacity(output, stored_bytes, disk_usage):
    required = OBJECT_BYTES - stored_bytes + DECODED_BYTES + QA_BYTES + RESERVE_BYTES
    free = disk_usage(output).free
    if type(free) is not int or free < required:
        raise OSError("capacity cannot preserve remaining compressed, decoded, QA and reserve bytes")
    return {"free_bytes": free, "required_free_bytes": required,
            "remaining_compressed_bytes": OBJECT_BYTES - stored_bytes}


def _verify_stored(output_fd, target, deadline, output, disk_usage):
    """Independently hash the persisted full file; no archive parsing or decoding."""
    fd = os.open("compressed.partial.zst", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=output_fd)
    try:
        current, original = os.fstat(fd), os.fstat(target.fileno())
        if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1 \
                or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino) \
                or current.st_size != OBJECT_BYTES:
            raise ValueError("stored artifact identity or full size changed")
        digest, remaining = hashlib.sha256(), OBJECT_BYTES
        while remaining:
            prefix._remaining(deadline)
            _capacity(output, OBJECT_BYTES, disk_usage)
            chunk = os.read(fd, min(CHUNK_BYTES, remaining))
            if not chunk:
                raise EOFError("persisted artifact is incomplete")
            digest.update(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != \
                (current.st_size, current.st_mtime_ns, current.st_ctime_ns):
            raise ValueError("stored artifact mutated during hashing")
        if digest.hexdigest() != OBJECT_SHA256:
            raise ValueError("persisted full-object SHA256 mismatch")
        prefix._remaining(deadline)
        return digest.hexdigest()
    finally:
        os.close(fd)


def download(output, *, plan_sha256, prior_cumulative_bytes,
             max_seconds=MAX_SECONDS, monitor_status=True,
             transport=HTTPSResponse, disk_usage=shutil.disk_usage):
    """Acquire only the fixed archive. Injected transport/disk functions are test-only.

    No local lock substitutes for the caller's global acquisition lock. The output
    parent must already exist, be canonical, and be controlled by the caller.
    The claim explicitly records that this helper cannot verify actual authority.
    """
    if type(plan_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", plan_sha256) is None:
        raise ValueError("a typed lowercase SHA256 plan/context binding is required")
    if type(prior_cumulative_bytes) is not int or prior_cumulative_bytes < PRIOR_BYTES_FLOOR:
        raise ValueError("explicit reconciled prior bytes at or above the known floor required")
    if prior_cumulative_bytes + OBJECT_BYTES > CAP_BYTES:
        raise ValueError("full-object reservation exceeds the 15 GB cumulative cap")
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) \
            or not 0 < max_seconds <= MAX_SECONDS:
        raise ValueError("hard job deadline must be positive and at most 1800 seconds")
    if type(monitor_status) is not bool:
        raise ValueError("monitor_status must be bool")
    output = Path(output)
    if not output.is_absolute() or output.parent != output.parent.resolve(strict=True) \
            or output.name in ("", ".", ".."):
        raise ValueError("canonical absolute fresh output with an existing parent required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("output ID already used; no retry or resume is allowed")
    parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    output_fd = None
    try:
        os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
        output_fd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent_fd)
        return _run(output, output_fd, plan_sha256, prior_cumulative_bytes,
                    max_seconds, monitor_status, transport, disk_usage)
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(parent_fd)


def _run(output, output_fd, plan_hash, prior, seconds, monitor_status, transport, disk_usage):
    url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{FILENAME}"
    claim = {
        "schema": "pinned_vantage_download_claim_v1", "dataset": DATASET,
        "revision": REVISION, "filename": FILENAME, "source_url": url,
        "object_bytes": OBJECT_BYTES, "object_sha256": OBJECT_SHA256,
        "plan_sha256": plan_hash, "prior_cumulative_bytes": prior, "cap_bytes": CAP_BYTES,
        "per_request_body_reservation_bytes": OBJECT_BYTES, "max_seconds": seconds,
        "socket_timeout_ceiling_seconds": SOCKET_SECONDS, "chunk_limit_bytes": CHUNK_BYTES,
        "decoded_capacity_reserved_bytes": DECODED_BYTES, "qa_capacity_bytes": QA_BYTES,
        "free_reserve_bytes": RESERVE_BYTES, "automatic_retry": False, "resume": False,
        "authorization_verified_by_this_helper": False, "global_lock_held_by_this_helper": False,
        "caller_must_bind_actual_approval_and_context": True,
        "transport_is_real_https": transport is HTTPSResponse,
        "accounting_scope": "Response-body bytes returned to reader, not wire/TLS traffic.",
        "decode_performed": False, "scientific_admission": False,
    }
    _json(output_fd, "claim.json", claim)
    status = _Status(output_fd, monitor_status)
    response = None
    request_index, actual, stored, read_pending = -1, 0, 0, False
    request_open, pending_read_maximum = False, 0
    digest = hashlib.sha256()
    phase = "initial_capacity"
    # All job operations after the claim, not just the socket, share one alarm.
    try:
        with prefix._hard_deadline(seconds) as deadline:
            with _exclusive(output_fd, "body-receipts.jsonl") as receipts, \
                    _exclusive(output_fd, "compressed.partial.zst", "wb") as target:
                capacity = _capacity(output, stored, disk_usage)
                status.update(state="running", bytes_read=0, bytes_stored=0, **capacity)
                for request_index in range(MAX_REDIRECTS + 1):
                    phase = "request"
                    parsed = prefix.checked_url(url)
                    # Every predecessor redirect was closed and durably settled at
                    # zero consumed body bytes before this reservation is created.
                    if prior + actual + OBJECT_BYTES > CAP_BYTES:
                        raise ValueError("new request reservation exceeds cumulative cap")
                    _append(receipts, {
                        "event": "request_started", "request_index": request_index,
                        "host": parsed.hostname, "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
                        "reserved_body_bytes": OBJECT_BYTES, "prior_plus_actual_bytes": prior + actual,
                    })
                    request_open = True
                    headers = dict(REQUEST_HEADERS)
                    headers["Range"] = f"bytes=0-{OBJECT_BYTES - 1}"
                    response = transport(url, headers, min(SOCKET_SECONDS, prefix._remaining(deadline)))
                    prefix._remaining(deadline)
                    if response.status in (301, 302, 303, 307, 308):
                        location = prefix._one_header(response.headers, "Location")
                        redirect_status = response.status
                        response.close()
                        response = None
                        _append(receipts, {
                            "event": "request_closed", "request_index": request_index,
                            "status": redirect_status, "body_consumed": False,
                            "actual_body_bytes": 0, "request_reservation_settled": True,
                        })
                        request_open = False
                        if request_index == MAX_REDIRECTS:
                            raise ValueError("redirect count bound exceeded")
                        url = urljoin(url, location)
                        prefix.checked_url(url)
                        continue
                    phase = "headers"
                    validate_headers(response)
                    accepted_status = response.status
                    _append(receipts, {"event": "headers_admitted", "request_index": request_index,
                                              "status": accepted_status, "body_bytes": OBJECT_BYTES})
                    while actual < OBJECT_BYTES:
                        phase = "body"
                        capacity = _capacity(output, stored, disk_usage)
                        amount = min(CHUNK_BYTES, OBJECT_BYTES - actual)
                        _append(receipts, {
                            "event": "body_read_started", "request_index": request_index,
                            "maximum_body_bytes": amount, "total_actual_body_bytes": actual,
                            **capacity,
                        })
                        read_pending = True
                        pending_read_maximum = amount
                        chunk = response.read1(amount, min(SOCKET_SECONDS, prefix._remaining(deadline)))
                        if type(chunk) is not bytes:
                            raise ValueError("transport violated bytes-only reader contract")
                        actual += len(chunk)
                        digest.update(chunk)
                        _append(receipts, {
                            "event": "body_read_finished", "request_index": request_index,
                            "actual_body_bytes": len(chunk), "total_actual_body_bytes": actual,
                            "read_bound_exceeded": len(chunk) > amount,
                        })
                        read_pending = False
                        if len(chunk) > amount:
                            raise ValueError("transport exceeded the requested read bound")
                        if not chunk:
                            raise EOFError("response ended before the pinned full size")
                        prefix._remaining(deadline)
                        # Also protect against another local process consuming space
                        # during the network read. Already returned bytes stay accounted.
                        _capacity(output, stored, disk_usage)
                        written = target.write(chunk)
                        stored += written or 0
                        if written != len(chunk):
                            raise OSError("short compressed artifact write")
                        os.fsync(target.fileno())
                        _append(receipts, {"event": "body_bytes_persisted",
                                                  "total_stored_bytes": stored})
                        status.update(state="running", bytes_read=actual, bytes_stored=stored)
                        prefix._remaining(deadline)
                    # Exactly OBJECT_BYTES have been read. No extra-byte EOF probe.
                    response.close()
                    response = None
                    _append(receipts, {
                        "event": "request_closed", "request_index": request_index,
                        "status": accepted_status, "body_consumed": True,
                        "actual_body_bytes": actual, "request_reservation_settled": True,
                    })
                    request_open = False
                    phase = "full_hash"
                    if actual != OBJECT_BYTES or stored != OBJECT_BYTES or digest.hexdigest() != OBJECT_SHA256:
                        raise ValueError("complete-object byte count or SHA256 mismatch")
                    phase = "stored_hash"
                    stored_sha256 = _verify_stored(output_fd, target, deadline, output, disk_usage)
                    _capacity(output, stored, disk_usage)
                    os.fchmod(target.fileno(), 0o444)
                    os.fchmod(receipts.fileno(), 0o444)
                    prefix._remaining(deadline)
                    break
                else:
                    raise ValueError("no admitted complete-object response")
            phase = "publish"
            # Atomic no-overwrite publication. Remove ONLY the identical staging
            # link after checking both identities; the verified raw bytes remain
            # under the final name with nlink==1 for the separate decoder gate.
            before = os.stat("compressed.partial.zst", dir_fd=output_fd, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("partial artifact identity changed before publication")
            os.link("compressed.partial.zst", FILENAME, src_dir_fd=output_fd,
                    dst_dir_fd=output_fd, follow_symlinks=False)
            final = os.stat(FILENAME, dir_fd=output_fd, follow_symlinks=False)
            staged = os.stat("compressed.partial.zst", dir_fd=output_fd, follow_symlinks=False)
            expected_identity = before.st_dev, before.st_ino
            if (final.st_dev, final.st_ino) != expected_identity \
                    or (staged.st_dev, staged.st_ino) != expected_identity \
                    or final.st_nlink != 2 or staged.st_nlink != 2:
                raise ValueError("publication or staging identity changed")
            os.unlink("compressed.partial.zst", dir_fd=output_fd)
            if os.stat(FILENAME, dir_fd=output_fd, follow_symlinks=False).st_nlink != 1:
                raise ValueError("published artifact must have one link")
            os.fsync(output_fd)
            result = {
                "schema": "pinned_vantage_download_result_v1", "passed": True,
                "dataset": DATASET, "revision": REVISION, "filename": FILENAME,
                "compressed_file": str(output / FILENAME), "plan_sha256": plan_hash,
                "object_bytes": stored, "object_sha256": stored_sha256,
                "persisted_full_object_sha256_verified": True,
                "full_object_sha256_verified": True, "new_actual_response_body_bytes": actual,
                "cumulative_actual_response_body_bytes": prior + actual,
                "requests_started": request_index + 1, "body_read_receipt_unresolved": False,
                "transport_is_real_https": transport is HTTPSResponse,
                "staging_link_removed_without_raw_byte_deletion": True,
                "published_artifact_link_count": 1, "decode_performed": False,
                "scientific_admission": False, "fresh_validation_admitted": False,
                "automatic_retry": False, "resume": False,
                "accounting_scope": "Response-body bytes returned to reader, not wire/TLS traffic.",
            }
            status.update(state="complete", bytes_read=actual, bytes_stored=stored,
                          full_object_sha256_verified=True)
            prefix._remaining(deadline)
            return _json(output_fd, "result.json", result)
    except BaseException as exc:
        close_failed = False
        if response is not None:
            try:
                response.close()
            except BaseException:
                close_failed = True
        failure = {
            "schema": "pinned_vantage_download_failure_v1", "passed": False,
            "phase": phase, "error_type": type(exc).__name__, "plan_sha256": plan_hash,
            "new_actual_response_body_bytes": actual, "stored_partial_bytes": stored,
            "cumulative_actual_response_body_bytes": prior + actual,
            "sha256_of_bytes_returned_to_reader": digest.hexdigest(),
            "body_read_receipt_unresolved": read_pending, "response_close_failed": close_failed,
            "unresolved_read_upper_bytes": pending_read_maximum if read_pending else 0,
            "request_reservation_remains_unresolved": request_open,
            "unresolved_request_reservation_bytes": max(0, OBJECT_BYTES - actual) if request_open else 0,
            "requests_started": request_index + 1, "per_request_reservation_bytes": OBJECT_BYTES,
            "reconciliation_required_before_next_request": True,
            "partial_or_verified_published_bytes_preserved": True,
            "full_object_sha256_verified": False, "complete_result_available": False,
            "transport_is_real_https": transport is HTTPSResponse,
            "automatic_retry": False, "resume": False, "decode_performed": False,
            "scientific_admission": False,
        }
        # No exception strings or signed redirect URLs are persisted. Failure to
        # write receipts never cancels the preceding durable reservation.
        try:
            fd = os.open("body-receipts.jsonl", os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW,
                         dir_fd=output_fd)
            with os.fdopen(fd, "w") as receipts:
                _append(receipts, {"event": "request_failed", **failure})
                os.fchmod(receipts.fileno(), 0o444)
        except OSError:
            pass
        try:
            fd = os.open("compressed.partial.zst", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=output_fd)
            try:
                os.fsync(fd)
                os.fchmod(fd, 0o444)
            finally:
                os.close(fd)
        except OSError:
            pass
        try:
            status.update(state="failed", **failure)
        except (OSError, ValueError):
            pass
        try:
            _json(output_fd, "failure.json", failure)
        except OSError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--prior-cumulative-bytes", type=int, required=True)
    parser.add_argument("--max-seconds", type=float, default=MAX_SECONDS)
    parser.add_argument("--no-monitor-status", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = download(args.output, plan_sha256=args.plan_sha256,
                          prior_cumulative_bytes=args.prior_cumulative_bytes,
                          max_seconds=args.max_seconds, monitor_status=not args.no_monitor_status)
    except BaseException as exc:
        print(json.dumps({"passed": False, "error_type": type(exc).__name__,
                          "detail": "Inspect preserved claim/receipts/failure; do not retry."}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
