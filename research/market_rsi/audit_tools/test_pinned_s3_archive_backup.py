"""Offline fixtures only. No AWS calls, credentials, or real signed URLs."""
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import pinned_s3_archive_backup as module


PLAN_SHA = "a" * 64
SECRET_MARKER = "FAKE_SECRET_ONLY_FOR_OFFLINE_LEAK_TEST"


def signed_url(**changes):
    values = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": "FAKEKEY/20260910/us-east-1/s3/aws4_request",
        "X-Amz-Date": "20260910T170000Z", "X-Amz-Expires": "1800",
        "X-Amz-SignedHeaders": ";".join(sorted(module.SIGNED_HEADERS)),
        "X-Amz-Signature": "b" * 64,
        "X-Amz-Security-Token": SECRET_MARKER,
    }
    values.update(changes)
    return "https://lh-research.s3.us-east-1.amazonaws.com/" + module.KEY + "?" + urlencode(values)


def envelope(url=None, plan_sha=PLAN_SHA):
    return io.BytesIO((json.dumps({"url": signed_url() if url is None else url,
                                 "plan_sha256": plan_sha}) + "\n").encode())


class FakeUpload:
    def __init__(self, digest, *, status=200, body=b"", fail_send=False, delay=0, checksum=True):
        self.status = status
        self.body = body
        self.offset = 0
        self.headers = [("Content-Length", str(len(body)))]
        if checksum:
            self.headers.append(("x-amz-checksum-sha256", base64.b64encode(bytes.fromhex(digest)).decode()))
        self.fail_send = fail_send
        self.delay = delay
        self.chunks = []
        self.reads = []
        self.closed = False

    def send(self, chunk, timeout):
        if self.delay:
            time.sleep(self.delay)
        if self.fail_send:
            raise OSError(SECRET_MARKER)
        self.chunks.append(chunk)

    def getresponse(self, timeout):
        return self.status, self.headers

    def read1(self, amount, timeout):
        self.reads.append(amount)
        chunk = self.body[self.offset:self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "synthetic-only.zst"
        self.data = b"SYNTHETIC_NOT_MARKET_DATA" * 97
        self.source.write_bytes(self.data)
        self.source.chmod(0o444)
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.fake = FakeUpload(self.digest)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def factory(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        return self.fake

    def backup(self, name="run", **options):
        arguments = dict(source=self.source, output=self.root / name,
                         expected_bytes=len(self.data), expected_sha256=self.digest,
                         expected_plan_sha256=PLAN_SHA, stdin=envelope(),
                         transport_factory=self.factory)
        arguments.update(options)
        return module._backup(**arguments)

    def failure(self, name="run"):
        return json.loads((self.root / name / "failure.json").read_text())

    def events(self):
        return [json.loads(line) for line in (self.root / "run/upload-receipts.jsonl").read_text().splitlines()]

    def no_secret_artifacts(self):
        for path in self.root.rglob("*.json*"):
            data = path.read_text()
            self.assertNotIn(SECRET_MARKER, data)
            self.assertNotIn("X-Amz-", data)
            self.assertNotIn("https://", data)

    def test_success_provisional_only_source_preserved_and_exact_headers(self):
        result = self.backup()
        self.assertTrue(result["provisional_put_success"])
        self.assertFalse(result["backup_accepted"])
        self.assertTrue(result["independent_head_required"])
        self.assertTrue(result["source_precheck_passed"])
        self.assertTrue(result["source_postcheck_passed"])
        self.assertEqual(b"".join(self.fake.chunks), self.data)
        self.assertEqual(self.source.read_bytes(), self.data)
        self.assertTrue(self.fake.closed)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1], {
            "Content-Length": str(len(self.data)), "Content-Type": "application/zstd",
            "If-None-Match": "*", "x-amz-checksum-sha256": base64.b64encode(bytes.fromhex(self.digest)).decode(),
        })
        self.assertEqual(result["cumulative_raw_bytes_including_backup"], module.PRIOR_CUMULATIVE_BYTES + len(self.data))
        self.assertEqual([e["event"] for e in self.events()],
                         ["put_started", "chunk_started", "chunk_completed", "put_provisionally_completed"])
        self.assertEqual((self.root / "run/claim.json").stat().st_mode & 0o222, 0)
        self.assertEqual((self.root / "run/upload-receipts.jsonl").stat().st_mode & 0o222, 0)
        self.no_secret_artifacts()

    def test_full_hash_mismatch_before_network(self):
        with self.assertRaises(module.GuardError):
            self.backup(expected_sha256="0" * 64)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.failure()["source_precheck_passed"])

    def test_claim_and_journal_directory_entries_synced_before_network(self):
        barriers = []
        original = module._fsync_directory
        def track(path):
            barriers.append(path)
            return original(path)
        def checked_factory(url, headers, timeout):
            self.assertEqual(barriers[:3], [self.root, self.root / "run", self.root / "run"])
            self.assertEqual(self.events()[0]["event"], "put_started")
            return self.factory(url, headers, timeout)
        with patch.object(module, "_fsync_directory", track):
            self.backup(transport_factory=checked_factory)

    def test_journal_directory_sync_failure_prevents_network(self):
        original = module._fsync_directory
        calls = []
        def fail_third(path):
            calls.append(path)
            if len(calls) == 3:
                raise OSError(SECRET_MARKER)
            return original(path)
        with patch.object(module, "_fsync_directory", fail_third), self.assertRaises(module.GuardError):
            self.backup()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.failure()["error_code"], "IO_FAILURE")
        self.no_secret_artifacts()

    def test_writable_hardlinked_symlinked_and_size_mismatch_sources_refused(self):
        self.source.chmod(0o644)
        with self.assertRaises(module.GuardError):
            self.backup(name="writable")
        self.source.chmod(0o444)
        os.link(self.source, self.root / "hardlink")
        with self.assertRaises(module.GuardError):
            self.backup(name="hardlinked")
        (self.root / "hardlink").unlink()
        link = self.root / "symlink"
        link.symlink_to(self.source)
        with self.assertRaises(module.GuardError):
            self.backup(name="symlinked", source=link)
        with self.assertRaises(module.GuardError):
            self.backup(name="size", expected_bytes=len(self.data) + 1)
        self.assertFalse(self.calls)

    def test_body_send_failure_has_pending_bound_and_no_retry_or_secret(self):
        self.fake.fail_send = True
        with self.assertRaises(module.GuardError) as caught:
            self.backup()
        failure = self.failure()
        self.assertEqual(failure["durably_completed_backup_body_bytes"], 0)
        self.assertEqual(failure["pending_chunk_max_bytes"], len(self.data))
        self.assertTrue(failure["reservation_reconciliation_required"])
        self.assertFalse(failure["automatic_retry"])
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn(SECRET_MARKER, str(caught.exception))
        self.assertTrue(self.fake.closed)
        self.no_secret_artifacts()

    def test_stream_chunks_never_exceed_one_mib(self):
        self.source.chmod(0o644)
        self.data = b"Z" * (module.CHUNK_BYTES + 17)
        self.source.write_bytes(self.data)
        self.source.chmod(0o444)
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.fake = FakeUpload(self.digest)
        self.backup()
        self.assertEqual([len(chunk) for chunk in self.fake.chunks], [module.CHUNK_BYTES, 17])

    def test_redirect_not_followed_or_body_read(self):
        self.fake.status = 307
        self.fake.headers.append(("Location", "https://example.invalid/" + SECRET_MARKER))
        with self.assertRaises(module.GuardError):
            self.backup()
        self.assertEqual(self.failure()["http_status"], 307)
        self.assertEqual(self.fake.reads, [])
        self.assertEqual(len(self.calls), 1)
        self.no_secret_artifacts()

    def test_conditional_conflict_is_not_success(self):
        self.fake = FakeUpload(self.digest, status=412, body=SECRET_MARKER.encode())
        with self.assertRaises(module.GuardError):
            self.backup()
        self.assertEqual(self.failure()["http_status"], 412)
        self.assertTrue(self.failure()["source_postcheck_passed"])
        self.assertEqual(self.failure()["durably_completed_backup_body_bytes"], len(self.data))
        self.no_secret_artifacts()

    def test_absent_or_wrong_s3_checksum_refused(self):
        for name, fake in (("absent", FakeUpload(self.digest, checksum=False)),
                           ("wrong", FakeUpload("0" * 64))):
            self.fake = fake
            with self.assertRaises(module.GuardError):
                self.backup(name=name)
            self.assertFalse(self.failure(name)["response_checksum_matches"])

    def test_response_body_length_above_cap_not_read(self):
        self.fake.headers[0] = ("Content-Length", "65537")
        with self.assertRaises(module.GuardError):
            self.backup()
        self.assertFalse(self.fake.reads)
        self.assertEqual(self.failure()["response_body_bytes"], 0)

    def test_transfer_encoding_with_content_length_refused_without_body_read(self):
        self.fake.headers.append(("Transfer-Encoding", "chunked"))
        self.fake.body = SECRET_MARKER.encode()
        with self.assertRaises(module.GuardError):
            self.backup()
        self.assertEqual(self.failure()["error_code"], "RESPONSE_TRANSFER_ENCODING_FORBIDDEN")
        self.assertFalse(self.fake.reads)
        self.assertFalse((self.root / "run/provisional-result.json").exists())
        self.no_secret_artifacts()

    def test_response_body_exact_cap_allowed_when_declared(self):
        self.fake = FakeUpload(self.digest, body=b"x" * module.MAX_RESPONSE_BYTES)
        result = self.backup()
        self.assertEqual(result["response_body_bytes"], module.MAX_RESPONSE_BYTES)
        self.assertEqual(sum(self.fake.reads), module.MAX_RESPONSE_BYTES)

    def test_undeclared_body_stops_at_cap_without_extra_byte(self):
        self.fake = FakeUpload(self.digest, body=b"x" * (module.MAX_RESPONSE_BYTES + 1))
        self.fake.headers = self.fake.headers[1:]
        with self.assertRaises(module.GuardError):
            self.backup()
        self.assertEqual(self.fake.offset, module.MAX_RESPONSE_BYTES)

    def test_source_change_during_send_blocks_acceptance(self):
        original_send = self.fake.send
        def change(chunk, timeout):
            original_send(chunk, timeout)
            self.source.chmod(0o644)
            self.source.write_bytes(b"Q" * len(self.data))
            self.source.chmod(0o444)
        self.fake.send = change
        with self.assertRaises(module.GuardError):
            self.backup()
        self.assertFalse(self.failure()["source_postcheck_passed"])

    def test_plan_mismatch_before_source_or_network(self):
        with self.assertRaises(module.GuardError):
            self.backup(stdin=envelope(plan_sha="0" * 64))
        self.assertEqual(self.calls, [])

    def test_duplicate_output_never_reused(self):
        self.backup()
        before = (self.root / "run/provisional-result.json").read_bytes()
        with self.assertRaises(module.GuardError):
            self.backup()
        self.assertEqual(before, (self.root / "run/provisional-result.json").read_bytes())
        self.assertEqual(len(self.calls), 1)

    def test_wall_deadline_interrupts_send_and_restores_alarm(self):
        self.fake.delay = 0.2
        with self.assertRaises(module.GuardError):
            self.backup(deadline_seconds=0.03)
        self.assertEqual(self.failure()["error_code"], "WALL_DEADLINE")
        self.assertGreater(self.failure()["pending_chunk_max_bytes"], 0)
        self.assertTrue(self.fake.closed)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_cumulative_cap_cannot_reset_for_backup(self):
        with self.assertRaises(module.GuardError):
            self.backup(expected_bytes=module.CAP_BYTES - module.PRIOR_CUMULATIVE_BYTES + 1)
        self.assertFalse((self.root / "run").exists())
        self.assertEqual(module.PRIOR_CUMULATIVE_BYTES + module.EXPECTED_BYTES, 11_338_004_681)

    def test_cli_cannot_accept_url_or_target_override_and_never_echoes(self):
        text = io.StringIO()
        with redirect_stdout(text):
            code = module.main(["--url", signed_url()])
        self.assertEqual(code, 2)
        self.assertNotIn(SECRET_MARKER, text.getvalue())
        self.assertNotIn("https://", text.getvalue())

    def test_production_constructor_is_fixed(self):
        with patch.object(module, "_backup", return_value={}) as implementation:
            supplied = envelope()
            module.run(PLAN_SHA, supplied)
        implementation.assert_called_once_with(
            module.SOURCE, module.OUTPUT, 3_164_694_656, module.EXPECTED_SHA256, PLAN_SHA, supplied)


class URLTests(unittest.TestCase):
    def test_native_https_request_is_put_and_sends_only_fixed_headers(self):
        class Connection:
            def __init__(self, host, **options):
                self.host, self.options, self.headers = host, options, {}
                self.sock = None
            def set_debuglevel(self, level):
                self.debuglevel = level
            def putrequest(self, method, target, **options):
                self.method, self.target, self.request_options = method, target, options
            def putheader(self, key, value):
                self.headers[key] = value
            def endheaders(self):
                self.ended = True
            def send(self, data):
                self.sent = data
            def close(self):
                self.closed = True
        headers = {"Content-Length": "3", "Content-Type": "application/zstd",
                   "If-None-Match": "*", "x-amz-checksum-sha256": "fixture-checksum"}
        with patch.object(module.http.client, "HTTPSConnection", Connection):
            upload = module._HTTPSUpload(signed_url(), headers, 20)
            upload.send(b"abc", 20)
            upload.close()
        connection = upload.connection
        self.assertEqual(connection.method, "PUT")
        self.assertEqual(connection.debuglevel, 0)
        self.assertEqual(connection.request_options, {"skip_host": True, "skip_accept_encoding": True})
        self.assertEqual(connection.headers, {**headers, "Host": "lh-research.s3.us-east-1.amazonaws.com",
                                             "Connection": "close"})
        self.assertEqual(connection.sent, b"abc")
        self.assertTrue(connection.closed)

    def test_both_exact_virtual_hosts_allowed(self):
        url = signed_url()
        self.assertEqual(module._validate_url(url)[0], "lh-research.s3.us-east-1.amazonaws.com")
        alternate = url.replace("lh-research.s3.us-east-1.amazonaws.com", "lh-research.s3.amazonaws.com")
        self.assertEqual(module._validate_url(alternate)[0], "lh-research.s3.amazonaws.com")

    def test_host_scheme_path_credentials_and_port_refused(self):
        url = signed_url()
        cases = [url.replace("https:", "http:"), url.replace("lh-research.s3.", "evil.s3."),
                 url.replace(module.KEY, "unrelated-key"), url.replace("https://", "https://user@"),
                 url.replace("amazonaws.com/", "amazonaws.com:443/"), url + "#fragment"]
        for candidate in cases:
            with self.subTest(), self.assertRaises(module.GuardError):
                module._validate_url(candidate)

    def test_signature_region_signed_headers_and_duplicates_refused(self):
        cases = [signed_url(**{"X-Amz-Credential": "FAKEKEY/20260910/eu-west-1/s3/aws4_request"}),
                 signed_url(**{"X-Amz-SignedHeaders": "host"}),
                 signed_url(**{"X-Amz-Expires": "3601"}),
                 signed_url(**{"X-Amz-Algorithm": "not-sigv4"}),
                 signed_url() + "&X-Amz-Expires=1"]
        for candidate in cases:
            with self.subTest(), self.assertRaises(module.GuardError):
                module._validate_url(candidate)

    def test_input_bound_duplicate_fields_and_extra_fields_refused(self):
        cases = [b"x" * (module.MAX_INPUT_BYTES + 1),
                 b'{"url":"first","url":"second","plan_sha256":"' + PLAN_SHA.encode() + b'"}\n',
                 b'{"url":"first","plan_sha256":"' + PLAN_SHA.encode() + b'","credentials":"never"}\n']
        for data in cases:
            with self.subTest(), self.assertRaises(module.GuardError):
                module._read_envelope(io.BytesIO(data), PLAN_SHA)


if __name__ == "__main__":
    unittest.main()
