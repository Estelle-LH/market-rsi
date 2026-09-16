"""Fake cloud receipts plus one actual closed-admission local child; no E2B API."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import development_harbor
import harbor_process as worker
from market_rsi import canonical, digest, file_hash, fresh_json
from sandbox_receipts import read_sandbox_receipts
from worker_receipts import Receipts
import test_dev_evidence as fixtures


class HarborProcessTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.EvidenceTests()
        self.fx.setUp()
        self.args = self.fx.pipeline()
        self.root = self.fx.devroot
        self.budget = self.fx.fixture.budget

    def tearDown(self):
        self.fx.tearDown()

    def context(self, deadline="2099-01-01T00:00:00+00:00"):
        return {"root": str(self.root), "budget_path": str(self.budget.root), "deadline_utc": deadline,
            "claim_sha256": digest(development_harbor.verify_job(self.root)[0]), "source_hashes": worker.source_hashes(),
            "local_wall_seconds": worker.WALL_SECONDS, "sdk_connection_retries": 0}

    def receipts(self, *, deadline="2099-01-01T00:00:00+00:00", exit_code=0):
        context = self.context(deadline)
        directory = self.root / "harbor-process"
        directory.mkdir()
        blobs = {"input": canonical(context).encode(), "stdout": b"", "stderr": b""}
        hashes = {}
        for name, raw in blobs.items():
            (directory / (name + ".bin")).write_bytes(raw)
            hashes[name] = hashlib.sha256(raw).hexdigest()
        here = Path(worker.__file__).parent
        fresh_json(directory / "claim.json", {"command_sha256": digest([sys.executable, "-I", str(here / "harbor_process_worker.py")]),
            "input_sha256": hashes["input"], "environment_names": sorted(["PATH", "LANG", "E2B_CONNECTION_RETRIES", "RSI_E2B_API_KEY"]),
            "wall_seconds": 270, "reap_seconds": 2, "max_stdout_bytes": 16*1024*1024, "max_stderr_bytes": 256*1024,
            "supervisor_source_sha256": file_hash(here / "bounded_process.py"), "remote_cancellation_established": False})
        fresh_json(directory / "receipt.json", {"pid": 99999, "process_reaped": True, "exit_code": exit_code,
            "input_complete": True, "input_bytes_written": len(blobs["input"]), "failure": None,
            "output_complete": True, "stdout_bytes": 0, "stderr_bytes": 0, "elapsed_seconds": 1,
            "stdout_sha256": hashes["stdout"], "stderr_sha256": hashes["stderr"], "remote_request_terminal": None,
            "remote_cancellation_established": False, "unused_budget_released": False})
        fresh_json(self.root / "sdk-retry-profile.json", {"connection_retries": 0})
        runtime = json.loads((self.root / "runtime.json").read_text())
        fresh_json(self.root / "deadline-check.json", {"deadline_utc": deadline, "sandbox_id": runtime["sandbox_id"],
            "expiry_at": runtime["expiry_at"], "passed": True})

    def verify(self, succeeded=True):
        reads = Receipts()
        worker.verify_process_receipts(self.root, reads, succeeded=succeeded)
        reads.revalidate()
        return reads

    def test_local_process_and_actual_expiry_receipts_bind(self):
        self.receipts()
        self.assertEqual(len(self.verify().files), 8)

    def test_local_exit_does_not_replace_separate_cloud_cleanup(self):
        self.receipts()
        self.fx.mutate("cleanup-01.json", lambda x: x.update(kill_acknowledged=False))
        with self.assertRaisesRegex(ValueError, "kill"):
            read_sandbox_receipts(self.root, Receipts(), development_harbor.verify_job(self.root)[0],
                                  self.budget, "learning", expected_live=True)

    def test_verified_local_and_remote_cleanup_do_not_release_hold(self):
        self.receipts()
        before = self.budget.snapshot()
        read_sandbox_receipts(self.root, Receipts(), development_harbor.verify_job(self.root)[0],
                              self.budget, "learning", expected_live=True)
        self.assertEqual(self.budget.snapshot(), before)
        self.assertEqual(before["reserved_usd"], "0.10")

    def test_new_create_must_fit_full_original_ttl_without_shortening_it(self):
        deadline = (datetime.now(timezone.utc) + timedelta(seconds=250)).isoformat()
        self.receipts(deadline=deadline)
        with self.assertRaisesRegex(TimeoutError, "full lifetime"):
            worker.require_create_window(self.root)
        self.assertEqual(development_harbor.TTL, 240)

    def test_changed_process_source_context_rejected(self):
        self.receipts()
        self.fx.mutate("harbor-process/input.bin", lambda x: x["source_hashes"].update({"harbor_process.py": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "context"):
            self.verify()

    def test_timeout_cannot_be_imported_as_completed_execution(self):
        self.receipts()
        self.fx.mutate("harbor-process/receipt.json", lambda x: x.update(failure="local_wall_timeout", exit_code=-9))
        with self.assertRaisesRegex(ValueError, "completion is unverified"):
            self.verify()

    def test_failed_worker_can_only_match_failed_completion(self):
        self.receipts(exit_code=1)
        self.verify(succeeded=False)
        with self.assertRaises(ValueError):
            self.verify(succeeded=True)

    def test_cloud_expiry_cannot_run_past_deadline(self):
        self.receipts(deadline="2020-01-01T00:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "expiry"):
            self.verify()

    def test_scoped_child_key_does_not_read_an_env_file(self):
        env = object.__new__(worker.DeadlineDevelopmentE2B)
        env.env_file = Path(worker.SCOPED_ENV)
        with patch.dict(os.environ, {"RSI_E2B_API_KEY": "fake-fixture-key"}), \
                patch("dotenv.dotenv_values") as read_env:
            self.assertEqual(env._paid_key(), "fake-fixture-key")
        read_env.assert_not_called()
        env.env_file = Path("/should/not/be/read")
        with self.assertRaises(ValueError):
            env._paid_key()

    def test_parent_admission_blocks_before_credentials_or_process_creation(self):
        with patch("dotenv.dotenv_values") as key, patch.object(worker, "run_bounded_process") as spawn:
            with self.assertRaisesRegex(RuntimeError, "scientific admission"):
                worker.run_bounded_development(self.root, self.budget.root, "/not/read", deadline_utc="2099-01-01T00:00:00+00:00")
        key.assert_not_called()
        spawn.assert_not_called()

    def test_real_local_child_independently_blocks_admission_without_cloud_call(self):
        before = self.budget.snapshot()
        # Host-only mocked admission permits exercising the child's REAL closed
        # gate. Mock values are not sent to an API; the child rejects before it.
        with patch.object(development_harbor, "require_admission", return_value=None), \
                patch("dotenv.dotenv_values", return_value={"E2B_API_KEY": "fake-not-a-credential"}):
            with self.assertRaisesRegex(RuntimeError, "local Harbor owner failed"):
                worker.run_bounded_development(self.root, self.budget.root, "/fixture-only", deadline_utc="2099-01-01T00:00:00+00:00")
        receipt = json.loads((self.root / "harbor-process/receipt.json").read_text())
        self.assertEqual(receipt["exit_code"], 1)
        self.assertTrue(receipt["process_reaped"])
        self.assertEqual(json.loads((self.root / "harbor-process/stderr.bin").read_text())["error_type"], "RuntimeError")
        self.assertFalse((self.root / "sdk-retry-profile.json").exists())
        self.assertEqual(self.budget.snapshot(), before)

    def test_saved_output_mutation_invalidates_receipt_set(self):
        self.receipts()
        reads = self.verify()
        (self.root / "harbor-process/stdout.bin").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            reads.revalidate()


if __name__ == "__main__":
    unittest.main()
