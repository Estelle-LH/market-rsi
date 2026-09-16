"""A single bounded prefix of either already-selected Canary object; never bulk ingest.

No CLI dispatch and no authorization inference: the caller must bind the actual
controller proposal/user approval, reconcile prior cumulative acquisition bytes,
and hold its global acquisition lock before calling probe(). This module's local
lock only serializes jobs sharing its output parent. No automatic retries.

Accounting means response-body bytes delivered to this reader, NOT total wire
traffic/TLS buffers. Rejected/redirect bodies are not consumed. An interrupted
request's reservation remains unresolved; never infer zero transfer from a missing
receipt. Prefix hashes do not verify the committed full-object SHA256.

Host source: https://huggingface.co/docs/hub/main/datasets-downloading (2026-09-10).
Only explicit current hosts are allowed; an unfamiliar/legacy redirect fails closed.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import io
import json
import math
import os
from pathlib import Path
import signal
import ssl
import stat
import threading
import time
from urllib.parse import urljoin, urlsplit


DATASET = "oraclemangle/polymarket-canary-tape"
REVISION = "0f09fdb48f703d672a648c562e3f6398f45eb168"
CAP_BYTES = 15_000_000_000
PREFIX_BYTES = 65_536
MAX_REDIRECTS = 4
READ_BYTES = 8192
MAX_WINDOW_BYTES = 128 * 1024 * 1024
ZSTANDARD_VERSION = "0.25.0"
ARCHIVES = {
    "polymarket-canary-tape-20260513-20260705.db.zst": {
        "bytes": 5_986_672_592,
        "sha256": "920d905ab7e786aeb5bc4d3f6904a03e26a9b87e9f450905345eed8c372ba176",
    },
    "polymarket-recorder-tape-vantage-b-20260603-20260701.db.zst": {
        "bytes": 3_164_694_656,
        "sha256": "9915c881cd5a598b831652664a1b761629c2c9303997332c9beef2af835d64a4",
    },
}
ALLOWED_HOSTS = frozenset({
    "huggingface.co", "cas-server.xethub.hf.co", "cas-server.xethub-eu.hf.co",
    "transfer.xethub.hf.co", "transfer.xethub-eu.hf.co", "us.aws.cdn.hf.co",
    "us.gcp.cdn.hf.co", "cdn-lfs-us-1.hf.co", "cdn-lfs-eu-1.hf.co",
})
REQUEST_HEADERS = {
    "Range": "bytes=0-65535", "Accept-Encoding": "identity",
    "User-Agent": "pinned-canary-prefix-preflight/1", "Connection": "close",
}


def _json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


def _append(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def checked_url(url):
    """Never follow credentials, ports, HTTP, broad suffixes, or arbitrary hosts."""
    if not isinstance(url, str) or len(url) > 16384 or any(ord(c) < 32 for c in url):
        raise ValueError("invalid redirect URL")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS \
            or parsed.username is not None or parsed.password is not None \
            or parsed.port not in (None, 443) or parsed.fragment:
        raise ValueError("HTTPS exact-host redirect policy refused URL")
    return parsed


@contextmanager
def _hard_deadline(seconds):
    # Socket timeouts alone cannot bound trickled response headers or DNS. Refuse
    # callers whose alarm/thread context cannot support the independent timer.
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("probe requires main thread for hard wall deadline")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ValueError("existing real-time alarm must not be replaced")
    previous = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise TimeoutError("prefix request/body/header wall deadline exceeded")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield time.monotonic() + seconds
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("prefix request/body/header wall deadline exceeded")
    return remaining


class HTTPSResponse:
    """No proxy, cookie jar, netrc, keys, automatic redirects, or retry client."""
    def __init__(self, url, headers, timeout):
        parsed = checked_url(url)
        self.connection = http.client.HTTPSConnection(
            parsed.hostname, port=443, timeout=timeout,
            context=ssl.create_default_context())
        try:
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            self.connection.request("GET", target, headers=headers)
            self.response = self.connection.getresponse()
            self.status = self.response.status
            self.headers = self.response.getheaders()
        except BaseException:
            self.connection.close()
            raise

    def read1(self, amount, timeout):
        if self.connection.sock is not None:
            self.connection.sock.settimeout(timeout)
        return self.response.read1(amount)

    def close(self):
        self.response.close()
        self.connection.close()


def _one_header(headers, name, required=True):
    values = [str(value).strip() for key, value in headers if key.lower() == name.lower()]
    if len(values) != 1:
        if not required and not values:
            return None
        raise ValueError("missing or duplicate " + name)
    return values[0]


def validate_response_headers(response, full_size):
    if response.status != 206:
        raise ValueError("expected HTTP 206; response body not consumed")
    expected = f"bytes 0-{PREFIX_BYTES - 1}/{full_size}"
    if _one_header(response.headers, "Content-Range") != expected:
        raise ValueError("Content-Range does not match pinned full size and exact prefix")
    if _one_header(response.headers, "Content-Length") != str(PREFIX_BYTES):
        raise ValueError("Content-Length must equal exact prefix bound")
    if _one_header(response.headers, "Content-Encoding", False) not in (None, "identity"):
        raise ValueError("encoded response is forbidden")
    if _one_header(response.headers, "Transfer-Encoding", False) is not None:
        raise ValueError("transfer-encoded response is forbidden")


def inspect_prefix(prefix):
    """Materialize only 100 decoded bytes, never rows or a SQLite connection.

    The zstd implementation necessarily maintains its bounded window internally.
    The inspected frame need not end within the prefix; no checksum/completeness
    or concatenated-frame total is claimed.
    """
    if type(prefix) is not bytes or not 0 < len(prefix) <= PREFIX_BYTES:
        raise ValueError("expected bounded nonempty prefix bytes")
    import zstandard
    if zstandard.__version__ != ZSTANDARD_VERSION:
        raise ValueError("unreviewed zstandard package version")
    if prefix[:4] != b"\x28\xb5\x2f\xfd":
        raise ValueError("expected an ordinary initial zstd frame, not a skippable frame")
    parameters = zstandard.get_frame_parameters(prefix)
    if parameters.window_size > MAX_WINDOW_BYTES:
        raise ValueError("zstd frame window exceeds 128 MiB")
    if parameters.dict_id:
        raise ValueError("external zstd dictionaries are not allowed")
    content_size = parameters.content_size
    if content_size in (zstandard.CONTENTSIZE_UNKNOWN, zstandard.CONTENTSIZE_ERROR):
        content_size = None
    # Installed 0.25.0 backend_c takes BYTES here despite its current docs saying
    # KiB. An offline 1 MiB-frame regression binds that observed behavior. The
    # independent frame-header byte ceiling above remains mandatory regardless.
    context = zstandard.ZstdDecompressor(max_window_size=MAX_WINDOW_BYTES)
    with context.stream_reader(io.BytesIO(prefix), read_size=PREFIX_BYTES,
                               read_across_frames=False) as reader:
        header = reader.read(100)
    if len(header) != 100 or header[:16] != b"SQLite format 3\x00":
        raise ValueError("prefix does not yield the complete 100-byte SQLite header")
    encoded_page_size = int.from_bytes(header[16:18], "big")
    page_size = 65536 if encoded_page_size == 1 else encoded_page_size
    if page_size < 512 or page_size > 65536 or page_size & (page_size - 1):
        raise ValueError("invalid SQLite page size")
    page_count = int.from_bytes(header[28:32], "big")
    change_counter = int.from_bytes(header[24:28], "big")
    version_valid_for = int.from_bytes(header[92:96], "big")
    counters_match = change_counter == version_valid_for
    valid_size = page_count != 0 and counters_match
    candidate = page_size * page_count if valid_size else None
    return {
        "zstandard_version": zstandard.__version__,
        "first_frame_content_size_bytes": content_size,
        "first_frame_window_bytes": parameters.window_size,
        "first_frame_checksum_present": parameters.has_checksum,
        "first_frame_checksum_verified": False,
        "all_frames_inspected": False, "decoded_bytes_materialized": 100,
        "sqlite_page_size": page_size, "sqlite_page_count": page_count,
        "sqlite_change_counter": change_counter,
        "sqlite_version_valid_for": version_valid_for,
        "sqlite_counters_match": counters_match,
        "sqlite_in_header_size_valid": valid_size,
        "sqlite_expected_candidate_bytes": candidate,
        "first_frame_size_matches_sqlite_candidate": (
            content_size == candidate if content_size is not None and candidate is not None else None),
        "exact_decoded_file_size_verified": False, "database_integrity_checked": False,
        "market_rows_emitted": 0,
        "claim_limit": "Header candidate only; not total-frame size, integrity, coverage, or admission.",
    }


def probe(filename, output, *, prior_cumulative_bytes, cap_bytes=CAP_BYTES,
          max_seconds=30, transport=HTTPSResponse):
    """Fetch exactly one prefix; injected transports are for offline tests only.

    Request+body+inspection have a <=30 second hard deadline. Durable per-read
    started/finished events expose interrupted accounting. Any existing output
    name is permanently used, including failures. This is not a global budget
    ledger or an approval/proposal validator; caller integration remains required.
    """
    if filename not in ARCHIVES:
        raise ValueError("object is not one of the two selected pinned archives")
    if type(prior_cumulative_bytes) is not int or prior_cumulative_bytes < 0 \
            or type(cap_bytes) is not int or cap_bytes != CAP_BYTES:
        raise ValueError("explicit nonnegative prior bytes and exact 15 GB cap required")
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) \
            or not 0 < max_seconds <= 30:
        raise ValueError("hard wall deadline must be positive and at most 30 seconds")
    maximum_reserved = (MAX_REDIRECTS + 1) * PREFIX_BYTES
    if prior_cumulative_bytes + maximum_reserved > cap_bytes:
        raise ValueError("insufficient cumulative headroom for per-request reservations")
    output = Path(output)
    if not output.is_absolute() or output.parent != output.parent.resolve(strict=True):
        raise ValueError("canonical absolute output with existing parent required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("permanent prefix output ID already claimed")
    lock_fd = os.open(output.parent / ".pinned-prefix-acquisition.lock",
                      os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        lock_stat = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1:
            raise ValueError("invalid prefix acquisition lock")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run_probe(filename, output, prior_cumulative_bytes, cap_bytes,
                          max_seconds, maximum_reserved, transport)
    finally:
        os.close(lock_fd)


def _run_probe(filename, output, prior, cap, max_seconds, maximum_reserved, transport):
    commitment = ARCHIVES[filename]
    url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{filename}"
    output.mkdir(mode=0o700, exist_ok=False)
    _json(output / "claim.json", {
        "schema": "pinned_archive_prefix_claim_v1", "dataset": DATASET,
        "revision": REVISION, "filename": filename, "url": url,
        "full_object_bytes_commitment": commitment["bytes"],
        "full_object_sha256_commitment": commitment["sha256"],
        "prior_cumulative_bytes": prior, "cap_bytes": cap,
        "prefix_bytes": PREFIX_BYTES, "per_request_reserved_bytes": PREFIX_BYTES,
        "maximum_request_reservations_bytes": maximum_reserved,
        "max_redirects": MAX_REDIRECTS, "max_seconds": max_seconds,
        "automatic_retry": False, "new_authority_granted": False,
        "prior_budget_and_authorization_validated_by_this_module": False,
        "transport_is_real_https": transport is HTTPSResponse,
        "accounting_scope": "Response-body bytes delivered to reader; not total wire traffic.",
    })
    partial = output / "prefix.partial.zst"
    journal = output / "body-receipts.jsonl"
    actual = 0
    digest = hashlib.sha256()
    response = None
    request_index = -1
    read_pending = False
    try:
        with journal.open("x") as receipts, partial.open("xb", buffering=0) as target:
            with _hard_deadline(max_seconds) as deadline:
                for request_index in range(MAX_REDIRECTS + 1):
                    parsed = checked_url(url)
                    _append(receipts, {
                        "event": "request_started", "request_index": request_index,
                        "host": parsed.hostname, "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
                        "reserved_body_bytes": PREFIX_BYTES,
                        "prior_plus_actual_bytes": prior + actual,
                    })
                    response = transport(url, dict(REQUEST_HEADERS), _remaining(deadline))
                    _remaining(deadline)
                    if response.status in (301, 302, 303, 307, 308):
                        location = _one_header(response.headers, "Location")
                        _append(receipts, {
                            "event": "response_closed", "request_index": request_index,
                            "status": response.status, "actual_body_bytes": 0,
                            "body_consumed": False,
                        })
                        response.close()
                        response = None
                        if request_index == MAX_REDIRECTS:
                            raise ValueError("redirect count bound exceeded")
                        url = urljoin(url, location)
                        checked_url(url)
                        continue
                    validate_response_headers(response, commitment["bytes"])
                    _append(receipts, {"event": "headers_admitted", "request_index": request_index,
                                      "status": 206, "expected_body_bytes": PREFIX_BYTES})
                    while actual < PREFIX_BYTES:
                        amount = min(READ_BYTES, PREFIX_BYTES - actual)
                        _append(receipts, {"event": "body_read_started", "request_index": request_index,
                                          "maximum_body_bytes": amount})
                        read_pending = True
                        chunk = response.read1(amount, _remaining(deadline))
                        if type(chunk) is not bytes:
                            raise ValueError("transport violated byte-reader type contract")
                        actual += len(chunk)
                        digest.update(chunk)
                        _append(receipts, {"event": "body_read_finished", "request_index": request_index,
                                          "actual_body_bytes": len(chunk), "total_actual_body_bytes": actual,
                                          "read_bound_exceeded": len(chunk) > amount})
                        read_pending = False
                        if len(chunk) > amount:
                            raise ValueError("transport violated bounded byte-reader contract")
                        if not chunk:
                            raise ValueError("truncated prefix response")
                        written = target.write(chunk)
                        if written != len(chunk):
                            raise OSError("short prefix artifact write")
                        _remaining(deadline)
                    response.close()
                    response = None
                    _append(receipts, {"event": "response_closed", "request_index": request_index,
                                      "status": 206, "actual_body_bytes": actual,
                                      "body_consumed": True})
                    # Never probe one extra byte beyond the exact prefix bound.
                    target.flush()
                    os.fsync(target.fileno())
                    header = inspect_prefix(partial.read_bytes())
                    _remaining(deadline)
                    break
                else:
                    raise ValueError("no admitted prefix response")
        partial.chmod(0o444)
        journal.chmod(0o444)
        result = {
            "schema": "pinned_archive_prefix_result_v1", "passed": True,
            "filename": filename, "prefix_file": str(partial),
            "prefix_bytes": actual, "prefix_sha256": digest.hexdigest(),
            "full_object_sha256_commitment": commitment["sha256"],
            "full_object_sha256_verified": False,
            "new_actual_response_body_bytes": actual,
            "cumulative_actual_response_body_bytes": prior + actual,
            "accounting_scope": "Application response bodies, not total wire traffic.",
            "transport_is_real_https": transport is HTTPSResponse,
            "requests_started": request_index + 1,
            "header": header, "acquisition_admitted": False,
            "fresh_validation_admitted": False, "automatic_retry": False,
        }
        _json(output / "result.json", result)
        return result
    except BaseException as exc:
        close_failed = False
        if response is not None:
            try:
                response.close()
            except Exception:
                close_failed = True
        failure_receipt_written = False
        if journal.exists():
            try:
                with journal.open("a") as receipts:
                    _append(receipts, {
                        "event": "request_failed", "request_index": request_index,
                        "error_type": type(exc).__name__,
                        "total_actual_body_bytes": actual,
                        "body_read_receipt_unresolved": read_pending,
                        "response_close_failed": close_failed,
                    })
                failure_receipt_written = True
            except OSError:
                # A filesystem failure cannot turn into a claim of zero bytes.
                # The original durable request reservation remains unresolved.
                pass
        for path in (partial, journal):
            if path.exists():
                path.chmod(0o444)
        _json(output / "failure.json", {
            "passed": False, "error_type": type(exc).__name__,
            "reason": str(exc), "new_actual_response_body_bytes": actual,
            "cumulative_actual_response_body_bytes": prior + actual,
            "prefix_sha256_of_bytes_returned_to_reader": digest.hexdigest(),
            "body_read_receipt_unresolved": read_pending,
            "append_only_failure_receipt_written": failure_receipt_written,
            "response_close_failed": close_failed,
            "requests_started": request_index + 1,
            "request_reservation_bytes": PREFIX_BYTES,
            "reconciliation_required_before_next_request": True,
            "full_object_sha256_verified": False, "automatic_retry": False,
            "transport_is_real_https": transport is HTTPSResponse,
            "complete_result_available": False,
        })
        raise
