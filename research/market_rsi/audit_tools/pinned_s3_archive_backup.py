"""One fixed archive backup, directly from Linode to private S3.

No AWS credentials, signed URLs on argv/disk/logs, redirects, retries, deletion,
or whole-Linode-backup claim. CLI: --plan-sha256 PUBLIC_SHA256. Stdin: one JSON
line containing only url and matching plan_sha256. Use a fresh isolated process
and an outer watchdog in addition to the internal 1800-second wall timer.

A PUT response is provisional: independent S3 HEAD size/checksum verification
must be performed by the caller before accepting the backup. Per-chunk sendall
completion is not proof of S3 receipt; failed pending chunks remain uncertain.
"""
import base64
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import sys
import threading
import time
from urllib.parse import parse_qsl, unquote, urlsplit


FILENAME = "polymarket-recorder-tape-vantage-b-20260603-20260701.db.zst"
SOURCE = Path("/opt/market-rsi-historical-20260910-01/acquisition") / FILENAME
OUTPUT = Path("/opt/market-rsi-historical-20260910-01/s3-backup-01")
EXPECTED_BYTES = 3_164_694_656
EXPECTED_SHA256 = "9915c881cd5a598b831652664a1b761629c2c9303997332c9beef2af835d64a4"
BUCKET = "lh-research"
REGION = "us-east-1"
KEY = "self-evolving/market-rsi/backups/20260910-linode-173-255-231-4-01/" + FILENAME
ALLOWED_HOSTS = frozenset({"lh-research.s3.amazonaws.com", "lh-research.s3.us-east-1.amazonaws.com"})
PRIOR_CUMULATIVE_BYTES = 8_173_310_025
CAP_BYTES = 15_000_000_000
CHUNK_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 32768
MAX_RESPONSE_BYTES = 65536
WALL_SECONDS = 1800
SOCKET_SECONDS = 20
SIGNED_HEADERS = frozenset({"content-length", "content-type", "host", "if-none-match", "x-amz-checksum-sha256"})


class GuardError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _error_code(error):
    if isinstance(error, GuardError):
        return error.code
    if isinstance(error, TimeoutError):
        return "DEADLINE_OR_SOCKET_TIMEOUT"
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return "INTERRUPTED"
    if isinstance(error, OSError):
        return "IO_FAILURE"
    if isinstance(error, http.client.HTTPException):
        return "HTTP_PROTOCOL_FAILURE"
    return "UNEXPECTED_FAILURE"


def _json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fchmod(stream.fileno(), 0o444)
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append(stream, value):
    stream.write(json.dumps({"recorded_unix_ns": time.time_ns(), **value},
                            sort_keys=True, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _remaining(end):
    left = end - time.monotonic()
    if left <= 0:
        raise GuardError("WALL_DEADLINE")
    return min(SOCKET_SECONDS, left)


@contextmanager
def _wall_deadline(seconds):
    if threading.current_thread() is not threading.main_thread() \
            or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise GuardError("UNSAFE_DEADLINE_CONTEXT")
    previous = signal.getsignal(signal.SIGALRM)

    def expire(_number, _frame):
        raise GuardError("WALL_DEADLINE")

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield time.monotonic() + seconds
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GuardError("DUPLICATE_INPUT_FIELD")
        result[key] = value
    return result


def _read_envelope(stream, expected_plan_sha256):
    line = stream.readline(MAX_INPUT_BYTES + 1)
    if type(line) is not bytes or not line.endswith(b"\n") or len(line) > MAX_INPUT_BYTES:
        raise GuardError("INVALID_BOUNDED_STDIN")
    try:
        value = json.loads(line, object_pairs_hook=_pairs_unique)
    except (ValueError, UnicodeError, RecursionError):
        raise GuardError("INVALID_STDIN_JSON") from None
    if type(value) is not dict or set(value) != {"url", "plan_sha256"} \
            or value["plan_sha256"] != expected_plan_sha256:
        raise GuardError("PLAN_ENVELOPE_MISMATCH")
    return value["url"]


def _validate_url(url):
    # No exceptions or parsed URL fields are ever emitted. Credential IDs and
    # session tokens remain part of the in-memory bearer URL only.
    try:
        if type(url) is not str or len(url) > 16384 or any(ord(c) < 33 or ord(c) > 126 for c in url):
            raise GuardError("INVALID_SIGNED_URL")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS \
                or parsed.netloc != parsed.hostname or parsed.fragment \
                or unquote(parsed.path, errors="strict") != "/" + KEY:
            raise GuardError("SIGNED_URL_DESTINATION_MISMATCH")
        query = _pairs_unique(parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True))
        required = {"X-Amz-Algorithm", "X-Amz-Credential", "X-Amz-Date", "X-Amz-Expires",
                    "X-Amz-SignedHeaders", "X-Amz-Signature"}
        if not required <= set(query) or set(query) - required - {"X-Amz-Security-Token"}:
            raise GuardError("UNSUPPORTED_SIGNATURE_QUERY")
        scope = query["X-Amz-Credential"].split("/")
        signed = query["X-Amz-SignedHeaders"].split(";")
        if query["X-Amz-Algorithm"] != "AWS4-HMAC-SHA256" \
                or len(scope) != 5 or not scope[0] or scope[2:] != [REGION, "s3", "aws4_request"] \
                or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", query["X-Amz-Date"]) \
                or scope[1] != query["X-Amz-Date"][:8] \
                or not query["X-Amz-Expires"].isdigit() or not 0 < int(query["X-Amz-Expires"]) <= 3600 \
                or set(signed) != SIGNED_HEADERS or len(signed) != len(SIGNED_HEADERS) \
                or not re.fullmatch(r"[0-9a-f]{64}", query["X-Amz-Signature"]):
            raise GuardError("SIGNATURE_SCOPE_OR_HEADERS_MISMATCH")
        return parsed.hostname, parsed.path + "?" + parsed.query
    except GuardError:
        raise
    except Exception:
        raise GuardError("INVALID_SIGNED_URL") from None


class _HTTPSUpload:
    def __init__(self, url, headers, timeout):
        host, target = _validate_url(url)
        self.connection = http.client.HTTPSConnection(host, timeout=timeout, context=ssl.create_default_context())
        self.connection.set_debuglevel(0)
        self.response = None
        try:
            self.connection.putrequest("PUT", target, skip_host=True, skip_accept_encoding=True)
            self.connection.putheader("Host", host)
            for name, value in headers.items():
                self.connection.putheader(name, value)
            self.connection.putheader("Connection", "close")
            self.connection.endheaders()
        except BaseException:
            self.connection.close()
            raise

    def send(self, chunk, timeout):
        if self.connection.sock is not None:
            self.connection.sock.settimeout(timeout)
        self.connection.send(chunk)

    def getresponse(self, timeout):
        if self.connection.sock is not None:
            self.connection.sock.settimeout(timeout)
        self.response = self.connection.getresponse()
        return self.response.status, self.response.getheaders()

    def read1(self, amount, timeout):
        if self.connection.sock is not None:
            self.connection.sock.settimeout(timeout)
        return self.response.read1(amount)

    def close(self):
        if self.response is not None:
            self.response.close()
        self.connection.close()


def _identity(value):
    return tuple(getattr(value, name) for name in (
        "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_nlink"))


def _check_source(source, expected_bytes):
    if not source.is_absolute() or source != source.resolve(strict=True):
        raise GuardError("SOURCE_PATH_NOT_CANONICAL")
    value = source.lstat()
    if not stat.S_ISREG(value.st_mode) or value.st_mode & 0o222 or value.st_nlink != 1 \
            or getattr(value, "st_flags", 0) & 0x40000000 or value.st_size != expected_bytes:
        raise GuardError("SOURCE_METADATA_MISMATCH")
    return _identity(value)


def _hash_fd(fd, expected_bytes, end):
    os.lseek(fd, 0, os.SEEK_SET)
    total, digest = 0, hashlib.sha256()
    while True:
        _remaining(end)
        chunk = os.read(fd, min(CHUNK_BYTES, expected_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > expected_bytes:
            raise GuardError("SOURCE_HASH_READ_SIZE_MISMATCH")
        digest.update(chunk)
    if total != expected_bytes:
        raise GuardError("SOURCE_HASH_READ_SIZE_MISMATCH")
    return digest.hexdigest()


def _one_header(headers, wanted, required=False):
    values = [value.strip() for name, value in headers if name.lower() == wanted.lower()]
    if len(values) > 1 or (required and not values):
        raise GuardError("RESPONSE_HEADER_AMBIGUOUS")
    return values[0] if values else None


def _response(transport, end, expected_checksum, metadata):
    status, headers = transport.getresponse(_remaining(end))
    if type(status) is not int or not 100 <= status <= 599:
        raise GuardError("INVALID_HTTP_STATUS")
    metadata["http_status"] = status
    if 300 <= status <= 399:
        raise GuardError("REDIRECT_FORBIDDEN")
    if _one_header(headers, "Transfer-Encoding") is not None:
        raise GuardError("RESPONSE_TRANSFER_ENCODING_FORBIDDEN")
    length = _one_header(headers, "Content-Length")
    if length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE_BYTES):
        raise GuardError("RESPONSE_BODY_BOUND")
    digest, received = hashlib.sha256(), 0
    while received < MAX_RESPONSE_BYTES:
        if length is not None and received == int(length):
            break
        amount = min(8192, MAX_RESPONSE_BYTES - received)
        if length is not None:
            amount = min(amount, int(length) - received)
        chunk = transport.read1(amount, _remaining(end))
        if type(chunk) is not bytes or len(chunk) > amount:
            raise GuardError("RESPONSE_READER_CONTRACT")
        if not chunk:
            break
        digest.update(chunk)
        received += len(chunk)
        metadata["response_body_bytes"] = received
        metadata["response_body_sha256"] = digest.hexdigest()
    if (length is not None and received != int(length)) or (length is None and received == MAX_RESPONSE_BYTES):
        raise GuardError("RESPONSE_BODY_BOUND_OR_TRUNCATION")
    metadata["response_body_bytes"] = received
    metadata["response_body_sha256"] = digest.hexdigest()
    metadata["response_checksum_matches"] = _one_header(headers, "x-amz-checksum-sha256") == expected_checksum


def _backup(source, output, expected_bytes, expected_sha256, expected_plan_sha256, stdin,
            *, transport_factory=_HTTPSUpload, deadline_seconds=WALL_SECONDS):
    """Private test seam; production run() supplies every target/limit constant."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise GuardError("INVALID_PLAN_SHA256")
    if PRIOR_CUMULATIVE_BYTES + expected_bytes > CAP_BYTES:
        raise GuardError("CUMULATIVE_CAP_EXCEEDED")
    if not output.is_absolute() or output.parent != output.parent.resolve(strict=True):
        raise GuardError("OUTPUT_PARENT_NOT_CANONICAL")
    if output.exists() or output.is_symlink():
        raise GuardError("OUTPUT_ALREADY_CLAIMED")
    output.mkdir(mode=0o700, exist_ok=False)
    _fsync_directory(output.parent)
    _json(output / "claim.json", {
        "schema": "pinned_s3_archive_backup_claim_v1", "plan_sha256": expected_plan_sha256,
        "source": str(source), "source_bytes": expected_bytes, "source_sha256": expected_sha256,
        "bucket": BUCKET, "region": REGION, "key": KEY,
        "prior_cumulative_raw_bytes": PRIOR_CUMULATIVE_BYTES,
        "reserved_backup_body_bytes": expected_bytes, "cumulative_cap_bytes": CAP_BYTES,
        "reserved_cumulative_raw_bytes": PRIOR_CUMULATIVE_BYTES + expected_bytes,
        "whole_deadline_seconds": deadline_seconds, "socket_timeout_seconds": SOCKET_SECONDS,
        "maximum_chunk_bytes": CHUNK_BYTES, "maximum_response_bytes": MAX_RESPONSE_BYTES,
        "automatic_retry": False, "overwrite_allowed": False,
        "backup_scope": "selected_compressed_historical_archive_only",
        "independent_head_required": True, "backup_accepted": False,
    })
    completed = send_returned = pending = 0
    source_fd = None
    transport = None
    stream_sha = hashlib.sha256()
    journal_path = output / "upload-receipts.jsonl"
    metadata = {"http_status": None, "response_body_bytes": 0,
                "response_body_sha256": hashlib.sha256(b"").hexdigest(),
                "response_checksum_matches": False, "source_precheck_passed": False,
                "source_postcheck_passed": False}
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | os.O_NOFOLLOW
        with os.fdopen(os.open(journal_path, flags, 0o600), "w") as journal:
            _fsync_directory(output)
            with _wall_deadline(deadline_seconds) as end:
                url = _read_envelope(stdin, expected_plan_sha256)
                _validate_url(url)
                identity = _check_source(source, expected_bytes)
                source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
                if _identity(os.fstat(source_fd)) != identity or _hash_fd(source_fd, expected_bytes, end) != expected_sha256 \
                        or _check_source(source, expected_bytes) != identity:
                    raise GuardError("SOURCE_PRECHECK_FAILED")
                metadata["source_precheck_passed"] = True
                checksum = base64.b64encode(bytes.fromhex(expected_sha256)).decode("ascii")
                headers = {"Content-Length": str(expected_bytes), "Content-Type": "application/zstd",
                           "If-None-Match": "*", "x-amz-checksum-sha256": checksum}
                _append(journal, {"event": "put_started", "reserved_body_bytes": expected_bytes})
                transport = transport_factory(url, headers, _remaining(end))
                url = None
                os.lseek(source_fd, 0, os.SEEK_SET)
                while completed < expected_bytes:
                    _remaining(end)
                    chunk = os.read(source_fd, min(CHUNK_BYTES, expected_bytes - completed))
                    if not chunk:
                        raise GuardError("SOURCE_TRUNCATED_DURING_UPLOAD")
                    _append(journal, {"event": "chunk_started", "offset": completed,
                                      "maximum_body_bytes": len(chunk)})
                    pending = len(chunk)
                    transport.send(chunk, _remaining(end))
                    send_returned += len(chunk)
                    stream_sha.update(chunk)
                    _append(journal, {"event": "chunk_completed", "body_bytes": len(chunk),
                                      "completed_body_bytes": send_returned})
                    completed = send_returned
                    pending = 0
                _response(transport, end, checksum, metadata)
                if stream_sha.hexdigest() != expected_sha256 \
                        or _check_source(source, expected_bytes) != identity \
                        or _identity(os.fstat(source_fd)) != identity \
                        or _hash_fd(source_fd, expected_bytes, end) != expected_sha256 \
                        or _check_source(source, expected_bytes) != identity:
                    raise GuardError("SOURCE_POSTCHECK_FAILED")
                metadata["source_postcheck_passed"] = True
                if metadata["http_status"] != 200:
                    raise GuardError("HTTP_PUT_NOT_200")
                if not metadata["response_checksum_matches"]:
                    raise GuardError("S3_RESPONSE_CHECKSUM_MISMATCH")
                _append(journal, {"event": "put_provisionally_completed", "http_status": 200,
                                  "completed_body_bytes": completed, "source_sha256": expected_sha256})
                _remaining(end)
        result = {
            "schema": "pinned_s3_archive_backup_provisional_v1", "worker_completed": True,
            "provisional_put_success": True, "backup_accepted": False,
            "independent_head_required": True, "plan_sha256": expected_plan_sha256,
            "source_sha256": expected_sha256, "expected_head_content_length": expected_bytes,
            "expected_head_checksum_sha256": expected_sha256,
            "new_backup_body_bytes": completed,
            "cumulative_raw_bytes_including_backup": PRIOR_CUMULATIVE_BYTES + completed,
            "remaining_cumulative_raw_cap_bytes": CAP_BYTES - PRIOR_CUMULATIVE_BYTES - completed,
            "pending_chunk_max_bytes": 0, "automatic_retry": False,
            "backup_scope": "selected_compressed_historical_archive_only", **metadata,
        }
        _json(output / "provisional-result.json", result)
        return result
    except BaseException as error:
        failure = {
            "worker_completed": False, "error_code": _error_code(error), "backup_accepted": False,
            "plan_sha256": expected_plan_sha256, "durably_completed_backup_body_bytes": completed,
            "send_calls_returned_body_bytes": send_returned, "pending_chunk_max_bytes": pending,
            "cumulative_raw_upper_bound_from_observed_chunks": PRIOR_CUMULATIVE_BYTES + completed + pending,
            "full_backup_body_reservation_bytes": expected_bytes,
            "reservation_reconciliation_required": True, "automatic_retry": False,
            "independent_head_required": True, **metadata,
        }
        if journal_path.exists():
            try:
                with journal_path.open("a") as journal:
                    _append(journal, {"event": "put_failed", **failure})
            except OSError:
                pass
        _json(output / "failure.json", failure)
        raise GuardError(_error_code(error)) from None
    finally:
        if transport is not None:
            try:
                transport.close()
            except BaseException:
                pass
        if source_fd is not None:
            os.close(source_fd)
        if journal_path.exists():
            journal_path.chmod(0o444)


def run(expected_plan_sha256, stdin):
    # No caller-provided source, destination, size, byte cap, timeout, or URL argv.
    return _backup(SOURCE, OUTPUT, EXPECTED_BYTES, EXPECTED_SHA256, expected_plan_sha256, stdin)


def main(argv=None, stdin=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "--plan-sha256" or not re.fullmatch(r"[0-9a-f]{64}", argv[1]):
        print(json.dumps({"worker_completed": False, "error_code": "INVALID_CLI", "backup_accepted": False}))
        return 2
    try:
        result = run(argv[1], sys.stdin.buffer if stdin is None else stdin)
        print(json.dumps({key: result[key] for key in (
            "worker_completed", "provisional_put_success", "backup_accepted",
            "independent_head_required", "new_backup_body_bytes")}))
        return 0
    except BaseException as error:
        print(json.dumps({"worker_completed": False, "error_code": _error_code(error), "backup_accepted": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
