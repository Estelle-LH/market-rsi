"""Offline synthetic bytes and injected transports only; no network calls."""
import hashlib
import json
from pathlib import Path
import signal
import tempfile
import time
import unittest

import zstandard

import pinned_archive_prefix as module


NAME = next(iter(module.ARCHIVES))
FULL_SIZE = module.ARCHIVES[NAME]["bytes"]
PRIOR = 5_008_484_297


def sqlite_header(*, page_size=4096, page_count=42, counter=9, valid_for=9):
    data = bytearray(100)
    data[:16] = b"SQLite format 3\x00"
    data[16:18] = (1 if page_size == 65536 else page_size).to_bytes(2, "big")
    data[24:28] = counter.to_bytes(4, "big")
    data[28:32] = page_count.to_bytes(4, "big")
    data[92:96] = valid_for.to_bytes(4, "big")
    return bytes(data)


def prefix_body(header=None):
    # A complete synthetic first frame plus trailing padding makes a full-size
    # HTTP fixture; it intentionally cannot prove whole-file validity.
    frame = zstandard.ZstdCompressor(write_checksum=True).compress(header or sqlite_header())
    return frame + bytes(module.PREFIX_BYTES - len(frame))


class FakeResponse:
    def __init__(self, *, status=206, headers=None, body=None, fail_after=None, delay=0):
        self.status = status
        self.headers = headers if headers is not None else [
            ("Content-Length", str(module.PREFIX_BYTES)),
            ("Content-Range", f"bytes 0-65535/{FULL_SIZE}"),
        ]
        self.body = prefix_body() if body is None else body
        self.offset = 0
        self.reads = []
        self.closed = False
        self.fail_after = fail_after
        self.delay = delay

    def read1(self, amount, timeout):
        self.reads.append(amount)
        if self.delay:
            time.sleep(self.delay)
        if self.fail_after is not None and self.offset >= self.fail_after:
            raise OSError("synthetic disconnect")
        chunk = self.body[self.offset:self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class HeaderTests(unittest.TestCase):
    def test_only_header_is_materialized_and_not_full_verification(self):
        result = module.inspect_prefix(prefix_body())
        self.assertEqual(result["decoded_bytes_materialized"], 100)
        self.assertEqual(result["sqlite_expected_candidate_bytes"], 4096 * 42)
        self.assertFalse(result["exact_decoded_file_size_verified"])
        self.assertFalse(result["all_frames_inspected"])
        self.assertFalse(result["first_frame_size_matches_sqlite_candidate"])

    def test_unknown_content_size(self):
        data = zstandard.ZstdCompressor(write_content_size=False).compress(sqlite_header())
        self.assertIsNone(module.inspect_prefix(data)["first_frame_content_size_bytes"])

    def test_installed_window_limit_units_allow_one_mib_frame(self):
        raw = sqlite_header() + bytes(1024 * 1024 - 100)
        data = zstandard.ZstdCompressor().compress(raw)
        result = module.inspect_prefix(data)
        self.assertEqual(result["first_frame_window_bytes"], 1024 * 1024)
        self.assertEqual(result["decoded_bytes_materialized"], 100)

    def test_large_sqlite_page_size_encoding(self):
        result = module.inspect_prefix(prefix_body(sqlite_header(page_size=65536)))
        self.assertEqual(result["sqlite_page_size"], 65536)

    def test_inconsistent_counter_or_zero_pages_has_no_candidate(self):
        for options in ({"valid_for": 8}, {"page_count": 0}):
            result = module.inspect_prefix(prefix_body(sqlite_header(**options)))
            self.assertIsNone(result["sqlite_expected_candidate_bytes"])
            self.assertFalse(result["sqlite_in_header_size_valid"])

    def test_bad_page_size_magic_and_short_data_refused(self):
        for data in (sqlite_header(page_size=513), b"bad" * 34, b"SQLite format 3\x00"):
            with self.subTest(data=data[:16]), self.assertRaises(ValueError):
                module.inspect_prefix(zstandard.ZstdCompressor().compress(data))

    def test_window_above_128_mib_rejected_before_decompressor(self):
        # Non-single-segment frame, no FCS, window descriptor exponent18 ->256MiB.
        frame = b"\x28\xb5\x2f\xfd\x00\x90\x01\x00\x00"
        with self.assertRaisesRegex(ValueError, "window"):
            module.inspect_prefix(frame)

    def test_skippable_frame_and_oversized_input_refused(self):
        for data in (b"\x50\x2a\x4d\x18" + b"\x00" * 8,
                     b"x" * (module.PREFIX_BYTES + 1)):
            with self.assertRaises(ValueError):
                module.inspect_prefix(data)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.responses = []
        self.requests = []

    def tearDown(self):
        self.temp.cleanup()

    def transport(self, url, headers, timeout):
        self.requests.append((url, headers, timeout))
        return self.responses.pop(0)

    def run_probe(self, name="probe", **options):
        kwargs = dict(prior_cumulative_bytes=PRIOR, transport=self.transport)
        kwargs.update(options)
        return module.probe(NAME, self.root / name, **kwargs)

    def failure(self):
        return json.loads((self.root / "probe/failure.json").read_text())

    def events(self):
        return [json.loads(line) for line in (self.root / "probe/body-receipts.jsonl").read_text().splitlines()]

    def test_exact_range_preserved_no_extra_read(self):
        response = FakeResponse()
        self.responses = [response]
        result = self.run_probe()
        self.assertEqual(result["prefix_sha256"], hashlib.sha256(response.body).hexdigest())
        self.assertEqual(result["cumulative_actual_response_body_bytes"], PRIOR + 65536)
        self.assertFalse(result["full_object_sha256_verified"])
        self.assertFalse(result["transport_is_real_https"])
        self.assertEqual(sum(response.reads), 65536)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][1], module.REQUEST_HEADERS)
        self.assertTrue(response.closed)
        self.assertEqual(sum(e["actual_body_bytes"] for e in self.events()
                             if e["event"] == "body_read_finished"), 65536)
        self.assertEqual((self.root / "probe/claim.json").stat().st_mode & 0o222, 0)
        self.assertEqual((self.root / "probe/prefix.partial.zst").stat().st_mode & 0o222, 0)

    def test_unknown_source_and_bad_budget_refused_before_output(self):
        cases = [dict(prior_cumulative_bytes=-1), dict(prior_cumulative_bytes=True),
                 dict(prior_cumulative_bytes=module.CAP_BYTES - 65536),
                 dict(cap_bytes=module.CAP_BYTES + 1), dict(max_seconds=31)]
        for options in cases:
            with self.assertRaises(ValueError):
                self.run_probe(**options)
        with self.assertRaises(ValueError):
            module.probe("not-selected", self.root / "probe", prior_cumulative_bytes=PRIOR)
        self.assertFalse((self.root / "probe").exists())
        self.assertFalse(self.requests)

    def test_second_pinned_object_uses_its_size_and_carried_cumulative_bytes(self):
        self.responses = [FakeResponse()]
        first = self.run_probe()
        second_name = list(module.ARCHIVES)[1]
        second_size = module.ARCHIVES[second_name]["bytes"]
        self.responses = [FakeResponse(headers=[
            ("Content-Length", "65536"),
            ("Content-Range", f"bytes 0-65535/{second_size}"),
        ])]
        second = module.probe(
            second_name, self.root / "second",
            prior_cumulative_bytes=first["cumulative_actual_response_body_bytes"],
            transport=self.transport)
        self.assertEqual(second["cumulative_actual_response_body_bytes"], PRIOR + 2 * 65536)
        self.assertEqual(second["full_object_sha256_commitment"], module.ARCHIVES[second_name]["sha256"])

    def test_duplicate_run_id_never_reused(self):
        self.responses = [FakeResponse()]
        self.run_probe()
        before = (self.root / "probe/result.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_probe()
        self.assertEqual(before, (self.root / "probe/result.json").read_bytes())
        self.assertEqual(len(self.requests), 1)

    def test_200_rejected_without_consuming_body(self):
        response = FakeResponse(status=200)
        self.responses = [response]
        with self.assertRaisesRegex(ValueError, "206"):
            self.run_probe()
        self.assertEqual(response.reads, [])
        self.assertEqual(self.failure()["new_actual_response_body_bytes"], 0)
        self.assertTrue(response.closed)
        self.assertEqual(self.events()[-1]["event"], "request_failed")
        self.assertEqual(self.events()[-1]["total_actual_body_bytes"], 0)

    def test_wrong_or_duplicate_headers_rejected_without_body(self):
        fixtures = [
            [("Content-Length", "65536"), ("Content-Range", "bytes 0-65535/7")],
            [("Content-Length", "65535"), ("Content-Range", f"bytes 0-65535/{FULL_SIZE}")],
            [("Content-Length", "65536"), ("Content-Length", "65536"),
             ("Content-Range", f"bytes 0-65535/{FULL_SIZE}")],
            [("Content-Length", "65536"), ("Content-Range", f"bytes 0-65535/{FULL_SIZE}"),
             ("Content-Encoding", "gzip")],
            [("Content-Length", "65536"), ("Content-Range", f"bytes 0-65535/{FULL_SIZE}"),
             ("Transfer-Encoding", "chunked")],
        ]
        for index, headers in enumerate(fixtures):
            response = FakeResponse(headers=headers)
            self.responses = [response]
            with self.assertRaises(ValueError):
                self.run_probe(name=f"bad-{index}")
            self.assertEqual(response.reads, [])

    def test_redirect_is_manual_and_carries_no_cookie(self):
        redirect = FakeResponse(status=302, headers=[
            ("Location", "https://cdn-lfs-us-1.hf.co/path?signed=value"),
            ("Set-Cookie", "forbidden=secret")])
        final = FakeResponse()
        self.responses = [redirect, final]
        self.run_probe()
        self.assertFalse(redirect.reads)
        self.assertTrue(redirect.closed)
        self.assertEqual(len(self.requests), 2)
        self.assertNotIn("Cookie", self.requests[1][1])
        self.assertNotIn("Authorization", self.requests[1][1])
        self.assertNotIn("signed=value", (self.root / "probe/body-receipts.jsonl").read_text())

    def test_redirect_host_scheme_credentials_and_port_policy(self):
        for url in ("http://huggingface.co/x", "https://evil.test/x",
                    "https://huggingface.co.evil.test/x", "https://user@huggingface.co/x",
                    "https://huggingface.co:8443/x", "https://huggingface.co/x#secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                module.checked_url(url)

    def test_unapproved_redirect_fails_before_second_request(self):
        self.responses = [FakeResponse(status=302, headers=[("Location", "https://evil.test/x")])]
        with self.assertRaises(ValueError):
            self.run_probe()
        self.assertEqual(len(self.requests), 1)

    def test_redirect_loop_bounded_no_retries(self):
        self.responses = [FakeResponse(status=302, headers=[("Location", "/again")])
                          for _ in range(module.MAX_REDIRECTS + 1)]
        with self.assertRaisesRegex(ValueError, "redirect count"):
            self.run_probe()
        self.assertEqual(len(self.requests), module.MAX_REDIRECTS + 1)
        self.assertEqual(self.failure()["new_actual_response_body_bytes"], 0)

    def test_partial_disconnect_bytes_survive_and_are_accounted(self):
        response = FakeResponse(fail_after=8192)
        self.responses = [response]
        with self.assertRaises(OSError):
            self.run_probe()
        failure = self.failure()
        self.assertEqual(failure["new_actual_response_body_bytes"], 8192)
        self.assertTrue(failure["body_read_receipt_unresolved"])
        self.assertEqual((self.root / "probe/prefix.partial.zst").stat().st_size, 8192)
        self.assertFalse((self.root / "probe/result.json").exists())
        self.assertEqual(len(self.requests), 1)

    def test_truncated_response_counts_every_returned_byte(self):
        self.responses = [FakeResponse(body=b"synthetic-prefix")]
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.run_probe()
        self.assertEqual(self.failure()["new_actual_response_body_bytes"], 16)
        self.assertFalse(self.failure()["body_read_receipt_unresolved"])

    def test_header_failure_still_counts_complete_acquisition(self):
        self.responses = [FakeResponse(body=b"x" * 65536)]
        with self.assertRaises(ValueError):
            self.run_probe()
        self.assertEqual(self.failure()["new_actual_response_body_bytes"], 65536)
        self.assertEqual((self.root / "probe/prefix.partial.zst").stat().st_size, 65536)

    def test_broken_transport_bound_still_accounts_returned_bytes(self):
        response = FakeResponse()
        response.read1 = lambda amount, timeout: b"x" * (amount + 1)
        self.responses = [response]
        with self.assertRaisesRegex(ValueError, "bounded byte-reader"):
            self.run_probe()
        self.assertEqual(self.failure()["new_actual_response_body_bytes"], module.READ_BYTES + 1)
        self.assertTrue(response.closed)

    def test_body_deadline_is_wall_clock_and_closes_response(self):
        response = FakeResponse(delay=0.2)
        self.responses = [response]
        with self.assertRaises(TimeoutError):
            self.run_probe(max_seconds=0.03)
        self.assertTrue(response.closed)
        self.assertTrue(self.failure()["body_read_receipt_unresolved"])
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_request_deadline_applies_before_headers(self):
        def slow_transport(*_args):
            time.sleep(0.2)
            raise AssertionError("hard deadline failed")
        with self.assertRaises(TimeoutError):
            self.run_probe(max_seconds=0.03, transport=slow_transport)
        self.assertEqual(self.failure()["requests_started"], 1)
        self.assertEqual(self.failure()["new_actual_response_body_bytes"], 0)
        self.assertTrue(self.failure()["reconciliation_required_before_next_request"])


if __name__ == "__main__":
    unittest.main()
