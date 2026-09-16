"""Offline only. Tiny fixture commitments and injected transport never make HTTP calls."""
from collections import namedtuple
from contextlib import ExitStack
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest import mock

import pinned_vantage_download as worker


Space = namedtuple("Space", "total used free")
PAYLOAD = b"a tiny opaque archive fixture; never decoded"
PLAN_HASH = "a" * 64


def full_headers(status=206):
    result = [("Content-Length", str(len(PAYLOAD)))]
    if status == 206:
        result.append(("Content-Range", f"bytes 0-{len(PAYLOAD)-1}/{len(PAYLOAD)}"))
    return result


class Response:
    def __init__(self, body=PAYLOAD, status=206, headers=None, read_error=None, delay=0):
        self.status = status
        self.headers = full_headers(status) if headers is None else headers
        self.body, self.offset, self.read_error, self.delay = body, 0, read_error, delay
        self.reads, self.closed = [], False

    def read1(self, amount, timeout):
        self.reads.append((amount, timeout))
        if self.read_error is not None and self.offset >= 8:
            raise self.read_error
        if self.delay:
            time.sleep(self.delay)
        result = self.body[self.offset:self.offset + amount]
        self.offset += len(result)
        return result

    def close(self):
        self.closed = True


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(temp).resolve()
        self.output = self.root / "job"
        for name, value in {
            "OBJECT_BYTES": len(PAYLOAD), "OBJECT_SHA256": hashlib.sha256(PAYLOAD).hexdigest(),
            "CHUNK_BYTES": 8,
        }.items():
            self.stack.enter_context(mock.patch.object(worker, name, value))
        # A mistakenly omitted injection is a hard failure, never a network attempt.
        self.stack.enter_context(mock.patch.object(worker.prefix.http.client, "HTTPSConnection",
                                                  side_effect=AssertionError("network prohibited")))
        self.disk_calls = []

    def disk(self, output):
        self.disk_calls.append(output)
        return Space(10**12, 0, 10**12)

    def run_download(self, response=None, **kwargs):
        self.response = response or Response()
        self.transport = kwargs.pop("transport", Transport(self.response))
        return worker.download(
            self.output, plan_sha256=kwargs.pop("plan_sha256", PLAN_HASH),
            prior_cumulative_bytes=kwargs.pop("prior_cumulative_bytes", worker.PRIOR_BYTES_FLOOR),
            transport=self.transport, disk_usage=kwargs.pop("disk_usage", self.disk), **kwargs)

    def read_json(self, name):
        return json.loads((self.output / name).read_text())

    def journal(self):
        return [json.loads(line) for line in (self.output / "body-receipts.jsonl").read_text().splitlines()]

    def assert_failed(self, error, response=None, **kwargs):
        with self.assertRaises(error):
            self.run_download(response, **kwargs)
        self.assertFalse((self.output / "result.json").exists())
        return self.read_json("failure.json")

    def test_complete_206_exact_no_extra_read_readonly_full_hash(self):
        result = self.run_download()
        self.assertTrue(result["persisted_full_object_sha256_verified"])
        self.assertFalse(result["scientific_admission"])
        self.assertFalse(result["decode_performed"])
        self.assertFalse(result["transport_is_real_https"])
        self.assertEqual(result["object_bytes"], len(PAYLOAD))
        self.assertEqual(result["cumulative_actual_response_body_bytes"], worker.PRIOR_BYTES_FLOOR + len(PAYLOAD))
        final = self.output / worker.FILENAME
        partial = self.output / "compressed.partial.zst"
        self.assertEqual(final.read_bytes(), PAYLOAD)
        self.assertFalse(partial.exists())
        self.assertEqual(final.stat().st_nlink, 1)
        self.assertTrue(result["staging_link_removed_without_raw_byte_deletion"])
        self.assertEqual(final.stat().st_mode & 0o222, 0)
        self.assertEqual(sum(size for size, _ in self.response.reads), len(PAYLOAD))
        self.assertTrue(all(0 < size <= 8 and 0 < timeout <= 20 for size, timeout in self.response.reads))
        self.assertTrue(self.response.closed)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertLessEqual(self.transport.calls[0][2], 20)
        headers = self.transport.calls[0][1]
        self.assertEqual(headers["Range"], f"bytes=0-{len(PAYLOAD)-1}")
        self.assertEqual(set(headers), {"Range", "Accept-Encoding", "Connection", "User-Agent"})
        self.assertEqual(self.read_json("status.json")["state"], "complete")
        self.assertFalse(list(self.output.glob("*.tmp")))
        self.assertGreaterEqual(len(self.disk_calls), 2 * len(self.response.reads) + 1)
        starts = [item for item in self.journal() if item["event"] == "body_read_started"]
        for index, item in enumerate(starts):
            self.assertEqual(item["required_free_bytes"], len(PAYLOAD) - index * 8 +
                             worker.DECODED_BYTES + worker.QA_BYTES + worker.RESERVE_BYTES)

    def test_complete_full_200(self):
        self.assertTrue(self.run_download(Response(status=200))["passed"])

    def test_bad_headers_never_read_body(self):
        variants = [
            (206, []),
            (206, full_headers() + [("content-length", str(len(PAYLOAD)))]),
            (206, [("Content-Length", "1"), full_headers()[1]]),
            (206, [full_headers()[0], ("Content-Range", "bytes 1-2/3")]),
            (206, full_headers() + [("Content-Encoding", "gzip")]),
            (206, full_headers() + [("Transfer-Encoding", "chunked")]),
            (200, full_headers()),
            (403, full_headers()),
        ]
        for index, (status, headers) in enumerate(variants):
            with self.subTest(index=index):
                self.output = self.root / f"bad-{index}"
                response = Response(status=status, headers=headers)
                failure = self.assert_failed(ValueError, response)
                self.assertEqual(response.reads, [])
                self.assertTrue(response.closed)
                self.assertEqual(failure["new_actual_response_body_bytes"], 0)
                self.assertEqual(len(self.transport.calls), 1)

    def test_allowlisted_redirect_settled_before_next_request(self):
        redirect = Response(status=302, headers=[("Location", "https://us.aws.cdn.hf.co/data?sig=hidden")])
        final = Response()
        transport = Transport(redirect, final)
        result = self.run_download(transport=transport)
        self.assertEqual(result["requests_started"], 2)
        self.assertEqual(redirect.reads, [])
        self.assertTrue(redirect.closed)
        journal = self.journal()
        self.assertEqual([item["event"] for item in journal[:3]],
                         ["request_started", "request_closed", "request_started"])
        self.assertTrue(journal[1]["request_reservation_settled"])
        self.assertNotIn("hidden", (self.output / "body-receipts.jsonl").read_text())

    def test_forbidden_redirects_no_second_request(self):
        for index, url in enumerate([
            "http://huggingface.co/data", "https://huggingface.co.attacker.test/data",
            "https://user:password@huggingface.co/data", "https://huggingface.co:444/data",
            "https://unknown.xethub.hf.co/data", "https://huggingface.co/data#fragment",
        ]):
            with self.subTest(url=url):
                self.output = self.root / f"redirect-{index}"
                response = Response(status=302, headers=[("Location", url)])
                self.assert_failed(ValueError, response)
                self.assertEqual(len(self.transport.calls), 1)
                self.assertEqual(response.reads, [])

    def test_redirect_limit_no_retry(self):
        responses = [Response(status=302, headers=[("Location", "/next")]) for _ in range(worker.MAX_REDIRECTS + 1)]
        transport = Transport(*responses)
        self.assert_failed(ValueError, transport=transport)
        self.assertEqual(len(transport.calls), worker.MAX_REDIRECTS + 1)
        self.assertTrue(all(item.closed and not item.reads for item in responses))

    def test_disconnect_preserves_partial_unresolved_reservation_and_sanitizes(self):
        failure = self.assert_failed(ConnectionResetError, Response(read_error=ConnectionResetError("secret-query-token")))
        self.assertEqual((self.output / "compressed.partial.zst").read_bytes(), PAYLOAD[:8])
        self.assertEqual(failure["new_actual_response_body_bytes"], 8)
        self.assertTrue(failure["body_read_receipt_unresolved"])
        self.assertTrue(failure["request_reservation_remains_unresolved"])
        self.assertEqual(failure["unresolved_request_reservation_bytes"], len(PAYLOAD) - 8)
        self.assertEqual(failure["unresolved_read_upper_bytes"], 8)
        self.assertEqual(failure["per_request_reservation_bytes"], len(PAYLOAD))
        self.assertEqual(self.journal()[0]["reserved_body_bytes"], len(PAYLOAD))
        self.assertEqual(self.journal()[-2]["event"], "body_read_started")
        self.assertNotIn("secret-query-token", (self.output / "failure.json").read_text())
        self.assertEqual(len(self.transport.calls), 1)

    def test_connection_error_reservation_survives(self):
        failure = self.assert_failed(TimeoutError, transport=Transport(TimeoutError("hidden")))
        self.assertEqual(failure["requests_started"], 1)
        self.assertEqual(self.journal()[0]["event"], "request_started")
        self.assertTrue(failure["reconciliation_required_before_next_request"])

    def test_early_eof_and_wrong_hash_preserve_partial(self):
        for index, body in enumerate([PAYLOAD[:11], b"x" * len(PAYLOAD)]):
            with self.subTest(index=index):
                self.output = self.root / f"payload-{index}"
                failure = self.assert_failed(EOFError if index == 0 else ValueError, Response(body=body))
                self.assertEqual((self.output / "compressed.partial.zst").read_bytes(), body)
                self.assertFalse(failure["full_object_sha256_verified"])
                self.assertFalse((self.output / worker.FILENAME).exists())

    def test_initial_capacity_fails_before_request(self):
        failure = self.assert_failed(OSError, disk_usage=lambda path: Space(0, 0, 0))
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(failure["requests_started"], 0)

    def test_capacity_drop_before_next_chunk_preserves_downloaded_bytes(self):
        calls = 0
        def disk(path):
            nonlocal calls
            calls += 1
            return Space(10**12, 0, 10**12 if calls <= 3 else 0)
        failure = self.assert_failed(OSError, disk_usage=disk)
        self.assertEqual(failure["stored_partial_bytes"], 8)
        self.assertEqual(len(self.response.reads), 1)
        self.assertFalse(failure["body_read_receipt_unresolved"])

    def test_capacity_drop_after_read_accounts_returned_unstored_bytes(self):
        calls = 0
        def disk(path):
            nonlocal calls
            calls += 1
            return Space(10**12, 0, 10**12 if calls <= 2 else 0)
        failure = self.assert_failed(OSError, disk_usage=disk)
        self.assertEqual(failure["new_actual_response_body_bytes"], 8)
        self.assertEqual(failure["stored_partial_bytes"], 0)

    def test_hard_deadline_stops_trickle_and_restores_alarm(self):
        old_handler = signal.getsignal(signal.SIGALRM)
        started = time.monotonic()
        failure = self.assert_failed(TimeoutError, Response(delay=0.1), max_seconds=0.02)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(signal.getsignal(signal.SIGALRM), old_handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertTrue(failure["body_read_receipt_unresolved"])

    def test_existing_output_and_symlinks_refused_without_changes(self):
        self.output.mkdir()
        marker = self.output / "do-not-change"
        marker.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            self.run_download()
        self.assertEqual(marker.read_bytes(), b"existing")
        link = self.root / "link"
        link.symlink_to(self.output, target_is_directory=True)
        self.output = link
        with self.assertRaises((FileExistsError, ValueError)):
            self.run_download()
        self.output = link / "new-job"
        with self.assertRaises(ValueError):
            self.run_download()

    def test_failure_output_never_resumed(self):
        self.assert_failed(EOFError, Response(body=PAYLOAD[:8]))
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        with self.assertRaises(FileExistsError):
            self.run_download()
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_plan_budget_deadline_arguments_fail_before_creation(self):
        for kwargs in [
            {"plan_sha256": ""}, {"plan_sha256": "A" * 64}, {"plan_sha256": True},
            {"prior_cumulative_bytes": worker.PRIOR_BYTES_FLOOR - 1},
            {"prior_cumulative_bytes": True}, {"prior_cumulative_bytes": worker.CAP_BYTES},
            {"max_seconds": 1801}, {"max_seconds": float("inf")}, {"max_seconds": True},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.run_download(**kwargs)
            self.assertFalse(self.output.exists())

    def test_monitor_optional(self):
        self.assertTrue(self.run_download(monitor_status=False)["passed"])
        self.assertFalse((self.output / "status.json").exists())

    def test_transport_overread_is_counted_not_saved(self):
        response = Response()
        response.read1 = lambda amount, timeout: PAYLOAD
        failure = self.assert_failed(ValueError, response)
        self.assertEqual(failure["new_actual_response_body_bytes"], len(PAYLOAD))
        self.assertEqual(failure["stored_partial_bytes"], 0)
        self.assertTrue(any(row.get("read_bound_exceeded") for row in self.journal()))

    def test_persisted_hash_detects_local_corruption(self):
        original = worker._verify_stored
        def corrupt(output_fd, target, *args):
            os.pwrite(target.fileno(), b"X", 0)
            os.fsync(target.fileno())
            return original(output_fd, target, *args)
        with mock.patch.object(worker, "_verify_stored", side_effect=corrupt):
            failure = self.assert_failed(ValueError)
        self.assertEqual(failure["phase"], "stored_hash")
        self.assertFalse((self.output / worker.FILENAME).exists())

    def test_publication_refuses_foreign_file_without_overwrite(self):
        original = worker._verify_stored
        def place_existing(output_fd, target, *args):
            result = original(output_fd, target, *args)
            (self.output / worker.FILENAME).write_bytes(b"preserve this file")
            return result
        with mock.patch.object(worker, "_verify_stored", side_effect=place_existing):
            self.assert_failed(FileExistsError)
        self.assertEqual((self.output / worker.FILENAME).read_bytes(), b"preserve this file")

    def test_bulk_transport_uses_bounded_read_not_tls_read1(self):
        response = worker.HTTPSResponse.__new__(worker.HTTPSResponse)
        response.connection = mock.Mock()
        response.response = mock.Mock()
        response.response.read.return_value = b"12345678"
        self.assertEqual(response.read1(8, 12), b"12345678")
        response.response.read.assert_called_once_with(8)
        response.response.read1.assert_not_called()
        response.connection.sock.settimeout.assert_called_once_with(12)
        for amount, timeout in [(0, 10), (9, 10), (True, 10), (8, 21), (8, 0), (8, float("inf"))]:
            with self.subTest(amount=amount, timeout=timeout), self.assertRaises(ValueError):
                response.read1(amount, timeout)
        self.assertEqual(response.response.read.call_count, 1)

    def test_bulk_transport_preserves_actual_http_eof_bytes(self):
        class FakeSocket:
            def makefile(self, mode):
                return io.BytesIO(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nabc")
        underlying = http.client.HTTPResponse(FakeSocket())
        underlying.begin()
        response = worker.HTTPSResponse.__new__(worker.HTTPSResponse)
        response.connection = mock.Mock()
        response.response = underlying
        self.assertEqual(response.read1(8, 10), b"abc")
        self.assertEqual(response.read1(8, 10), b"")

    def test_bulk_transport_timeout_leaves_one_read_reservation(self):
        response = worker.HTTPSResponse.__new__(worker.HTTPSResponse)
        response.connection = mock.Mock()
        response.response = mock.Mock()
        response.status, response.headers = 206, full_headers()
        response.response.read.side_effect = [PAYLOAD[:8], TimeoutError("secret-buffer-state")]
        failure = self.assert_failed(TimeoutError, response)
        self.assertEqual(response.response.read.call_args_list, [mock.call(8), mock.call(8)])
        response.response.read1.assert_not_called()
        self.assertEqual(failure["new_actual_response_body_bytes"], 8)
        self.assertEqual(failure["stored_partial_bytes"], 8)
        self.assertEqual(failure["unresolved_read_upper_bytes"], 8)
        self.assertTrue(failure["request_reservation_remains_unresolved"])

    def test_all_bulk_artifacts_and_receipts_have_utc_timestamps(self):
        timestamp = "2026-09-10T16:00:00.123456Z"
        with mock.patch.object(worker, "_utc_now", return_value=timestamp):
            result = self.run_download()
        self.assertEqual(result["recorded_at_utc"], timestamp)
        for name in ("claim.json", "status.json", "result.json"):
            self.assertEqual(self.read_json(name)["recorded_at_utc"], timestamp)
        self.assertTrue(all(row["recorded_at_utc"] == timestamp for row in self.journal()))
        self.output = self.root / "timestamped-failure"
        with mock.patch.object(worker, "_utc_now", return_value=timestamp):
            self.assert_failed(EOFError, Response(body=PAYLOAD[:8]))
        self.assertEqual(self.read_json("failure.json")["recorded_at_utc"], timestamp)
        self.assertEqual(self.read_json("status.json")["recorded_at_utc"], timestamp)
        self.assertTrue(all(row["recorded_at_utc"] == timestamp for row in self.journal()))


if __name__ == "__main__":
    unittest.main()
