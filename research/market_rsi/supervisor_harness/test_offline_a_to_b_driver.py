"""Offline Controller-to-broker-to-fake-B binding tests; no providers/Docker."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from market_rsi import canonical, digest, file_hash, load_json
from supervisor_harness import frozen_glm_first_response as first
from supervisor_harness import offline_a_to_b_driver as driver


class OfflineAToBDriverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.cycle_id = "offline-a-b-01"
        self.glm_claims = self.base / "glm-claims"
        self.glm_claims.mkdir()
        self.driver_claims = self.base / "driver-claims"
        self.driver_claims.mkdir()
        self.glm_parent = self.base / "glm"
        self.glm_parent.mkdir()
        self.glm_root = self.glm_parent / self.cycle_id
        self.driver_parent = self.base / "driver"
        self.driver_parent.mkdir()
        self.root = self.driver_parent / self.cycle_id
        self.public_text = "synthetic-only fixture text for a hash task"
        self.source_id = "synthetic:hash-fixture"
        self.packet = {
            "schema": first.PACKET_SCHEMA, "cycle_id": self.cycle_id,
            "context_items": [{
                "role": "synthetic_fixture", "source_id": self.source_id,
                "text": self.public_text,
                "text_sha256": hashlib.sha256(self.public_text.encode()).hexdigest()}]}
        self.decision = {
            "schema": driver.DECISION_SCHEMA, "task_id": "hash-once",
            "source_id": self.source_id, "action": "hash_public_text"}

    def _first(self, decision=None, *, raw=None):
        sampled = {
            "text": raw if raw is not None else canonical(
                self.decision if decision is None else decision),
            "output_tokens": [21, 22], "cached_input_tokens": 0,
            "finish_reason": "stop",
            "provider": {"reported_model": first.MODEL,
                         "session_id": "fake-session",
                         "sampling_session_id": "fake-sample"}}
        result = first.run_offline_first_response(
            root=self.glm_root, claim_root=self.glm_claims,
            cycle_id=self.cycle_id, packet=self.packet,
            backend=first.OfflineFakeBackend(sampled))
        self.assertTrue(result["valid_fake_response"])
        return result

    def _bind(self, fake_b=None, *, root=None):
        fake_b = fake_b or driver.OfflineFakeLocalB()
        result = driver.run_offline_binding(
            root=root or self.root, claim_root=self.driver_claims,
            cycle_id=self.cycle_id, glm_root=self.glm_root,
            glm_claim_root=self.glm_claims, researcher=fake_b)
        return result, fake_b

    def test_one_allowed_public_task_has_exact_hash_lineage_and_cleanup(self):
        self._first()
        before = {path.name: file_hash(path) for path in self.glm_root.iterdir()}
        result, fake_b = self._bind()
        self.assertTrue(result["passed_offline_binding"])
        self.assertEqual((fake_b.sent, fake_b.kills), (1, 1))
        order = load_json(self.root / "broker-order.json")
        self.assertEqual(order["public_text"], self.public_text)
        self.assertEqual(order["public_text_sha256"], self.packet["context_items"][0]["text_sha256"])
        self.assertEqual(order["decision_sha256"], digest(self.decision))
        self.assertEqual(order["first_response_sha256"], file_hash(self.glm_root / "raw-response.txt"))
        self.assertEqual(order["input_sha256"], file_hash(self.glm_root / "input.json"))
        self.assertEqual(set(order), {"schema", "cycle_id", "task_id", "source_id",
                                      "public_text", "public_text_sha256",
                                      "decision_sha256", "first_response_sha256",
                                      "input_sha256"})
        self.assertEqual(load_json(self.root / "raw-ack.json")["order_sha256"], digest(order))
        self.assertEqual(load_json(self.root / "raw-event.json")["order_sha256"], digest(order))
        self.assertEqual(result["raw_event_sha256"], file_hash(self.root / "raw-event.json"))
        self.assertTrue(load_json(self.root / "cleanup.json")["exact_fake_cleanup_verified"])
        self.assertEqual(before, {path.name: file_hash(path) for path in self.glm_root.iterdir()})
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["model_authorship_proven"])
        self.assertFalse(result["full_isolation_proven"])
        self.assertFalse(result["formal_admission"])

    def test_malformed_response_consumes_claim_without_sending_to_b(self):
        self._first(raw="not JSON")
        result, fake_b = self._bind()
        self.assertFalse(result["passed_offline_binding"])
        self.assertEqual(result["failure_type"], "JSONDecodeError")
        self.assertEqual(load_json(self.root / "failure.json")["stage"], "choice")
        self.assertEqual((fake_b.sent, fake_b.kills), (0, 1))
        self.assertTrue((self.driver_claims / f"{self.cycle_id}.json").is_file())

    def test_ambiguous_duplicate_json_field_is_denied_before_b(self):
        self._first(raw=(
            '{"schema":"market_glm_bounded_synthetic_choice_v1",'
            '"task_id":"first","task_id":"second",'
            '"source_id":"synthetic:hash-fixture",'
            '"action":"hash_public_text"}'))
        result, fake_b = self._bind()
        self.assertFalse(result["passed_offline_binding"])
        self.assertEqual(result["failure_type"], "ValueError")
        self.assertEqual((fake_b.sent, fake_b.kills), (0, 1))

    def test_model_cannot_supply_code_paths_or_extra_authority(self):
        for extra in ({"code": "print('unsafe')"},
                      {"host_path": "/tmp/host"},
                      {"key": "synthetic-key"},
                      {"a_path": "/tmp/a"}):
            with self.subTest(extra=extra):
                alternate = f"{self.cycle_id}-{len(extra)}-{next(iter(extra))}"
                self.cycle_id = alternate
                self.packet["cycle_id"] = alternate
                self.glm_root = self.glm_parent / alternate
                self.root = self.driver_parent / alternate
                self._first(decision={**self.decision, **extra})
                result, fake_b = self._bind()
                self.assertFalse(result["passed_offline_binding"])
                self.assertEqual(fake_b.sent, 0)
                self.assertEqual(fake_b.kills, 1)

    def test_timeout_is_terminal_and_exact_fake_cleanup_runs(self):
        self._first()
        result, fake_b = self._bind(driver.OfflineFakeLocalB(mode="timeout"))
        self.assertFalse(result["passed_offline_binding"])
        self.assertEqual(result["failure_type"], "TimeoutError")
        self.assertEqual(load_json(self.root / "failure.json")["stage"], "read_ack")
        self.assertEqual((fake_b.sent, fake_b.kills), (1, 1))
        self.assertTrue(load_json(self.root / "cleanup.json")["exact_fake_cleanup_verified"])
        self.assertFalse((self.root / "raw-event.json").exists())

    def test_duplicate_id_rejected_before_second_fake_b_receives_order(self):
        self._first()
        self._bind()
        other_parent = self.base / "other"
        other_parent.mkdir()
        second = driver.OfflineFakeLocalB(sandbox_id="second-fake-b")
        with self.assertRaises(FileExistsError):
            self._bind(second, root=other_parent / self.cycle_id)
        self.assertEqual((second.sent, second.kills), (0, 0))

    def test_failed_exact_cleanup_never_passes(self):
        self._first()
        result, fake_b = self._bind(driver.OfflineFakeLocalB(mode="kill_false"))
        self.assertFalse(result["passed_offline_binding"])
        self.assertEqual(result["failure_type"], "CleanupUnverified")
        self.assertEqual((fake_b.sent, fake_b.kills), (1, 1))
        cleanup = load_json(self.root / "cleanup.json")
        self.assertFalse(cleanup["kill_acknowledged"])
        self.assertFalse(cleanup["exact_fake_cleanup_verified"])

    def test_wrong_b_event_fails_after_raw_preservation_and_cleanup(self):
        self._first()
        result, fake_b = self._bind(driver.OfflineFakeLocalB(mode="wrong_event"))
        self.assertFalse(result["passed_offline_binding"])
        self.assertEqual(load_json(self.root / "failure.json")["stage"], "read_event")
        self.assertEqual(result["raw_event_sha256"], file_hash(self.root / "raw-event.json"))
        self.assertEqual((fake_b.sent, fake_b.kills), (1, 1))

    def test_broker_order_receipt_tamper_during_b_response_fails_closed(self):
        self._first()
        fake_b = driver.OfflineFakeLocalB()
        original_publish = fake_b.publish

        def tampering_publish(order):
            original_publish(order)
            (self.root / "broker-order.json").write_text('{"tampered":true}\n')

        fake_b.publish = tampering_publish
        result, fake_b = self._bind(fake_b)
        self.assertFalse(result["passed_offline_binding"])
        self.assertEqual(load_json(self.root / "failure.json")["stage"],
                         "post_execution_integrity")
        self.assertTrue(load_json(self.root / "cleanup.json")["exact_fake_cleanup_verified"])
        self.assertEqual((fake_b.sent, fake_b.kills), (1, 1))

    def test_tampered_controller_evidence_denied_before_claim_or_b(self):
        self._first()
        (self.glm_root / "raw-response.txt").write_text("different")
        fake_b = driver.OfflineFakeLocalB()
        with self.assertRaisesRegex(ValueError, "lineage changed"):
            self._bind(fake_b)
        self.assertFalse(self.root.exists())
        self.assertEqual(list(self.driver_claims.iterdir()), [])
        self.assertEqual((fake_b.sent, fake_b.kills), (0, 0))

    def test_non_fake_backend_rejected_before_claim(self):
        self._first()
        with self.assertRaisesRegex(RuntimeError, "real local-B dispatch disabled"):
            self._bind(object())
        self.assertEqual(list(self.driver_claims.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
