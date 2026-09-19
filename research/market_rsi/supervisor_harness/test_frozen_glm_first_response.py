"""Offline-only boundary/provenance tests; no Tinker, GLM, B or budget use."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_rsi import file_hash, load_json
from supervisor_harness import frozen_glm_first_response as first


class FrozenGLMFirstResponseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.claims = self.base / "claims"
        self.claims.mkdir()
        self.cycle_id = "glm-first-offline-01"
        self.output_parent = self.base / "output"
        self.output_parent.mkdir()
        self.root = self.output_parent / self.cycle_id
        self.text = "synthetic-public research context only"
        self.item = {"role": "synthetic_fixture", "source_id": "synthetic:one",
                     "text": self.text,
                     "text_sha256": hashlib.sha256(self.text.encode()).hexdigest()}
        self.packet = {"schema": first.PACKET_SCHEMA, "cycle_id": self.cycle_id,
                       "context_items": [self.item]}
        self.sampled = {"text": "A first plain-text response; no action was executed.",
                        "output_tokens": [21, 22], "cached_input_tokens": 0,
                        "finish_reason": "stop",
                        "provider": {"reported_model": first.MODEL,
                                     "session_id": "fake-session",
                                     "sampling_session_id": "fake-sample"}}
        self.backend = first.OfflineFakeBackend(self.sampled)

    def _run(self, *, packet=None, backend=None, root=None):
        return first.run_offline_first_response(
            root=root or self.root, claim_root=self.claims, cycle_id=self.cycle_id,
            packet=self.packet if packet is None else packet,
            backend=self.backend if backend is None else backend)

    def test_one_first_raw_response_no_tools_and_fake_cost_provenance(self):
        result = self._run()
        self.assertTrue(result["valid_fake_response"])
        self.assertEqual(self.backend.sample_calls, 1)
        self.assertEqual(self.backend.encode_calls, 1)
        self.assertEqual(load_json(self.root / "request.json")["tools"], [])
        self.assertEqual(load_json(self.root / "claim.json")["num_samples"], 1)
        self.assertEqual((self.root / "raw-response.txt").read_text(),
                         self.sampled["text"])
        self.assertEqual(result["raw_text_sha256"],
                         file_hash(self.root / "raw-response.txt"))
        self.assertEqual(load_json(self.root / "raw-response.json"), self.sampled)
        self.assertEqual(result["requested_model"], first.MODEL)
        self.assertEqual(result["fake_backend_reported_model"], first.MODEL)
        self.assertEqual(result["actual_provider_cost_usd"], "0")
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["model_identity_proven"])
        self.assertFalse(result["model_authorship_proven"])
        self.assertFalse(result["scientific_decision_validated"])
        self.assertFalse(result["formal_admission"])
        self.assertTrue((self.claims / f"{self.cycle_id}.json").is_file())

    def test_duplicate_id_rejected_across_output_directories_without_resample(self):
        self._run()
        other_parent = self.base / "second"
        other_parent.mkdir()
        other = first.OfflineFakeBackend(self.sampled)
        with self.assertRaises(FileExistsError):
            self._run(backend=other, root=other_parent / self.cycle_id)
        self.assertEqual(other.encode_calls, 0)
        self.assertEqual(other.sample_calls, 0)

    def test_benchmark_fields_and_protected_text_rejected_before_claim(self):
        with self.assertRaisesRegex(ValueError, "exact public/synthetic packet"):
            self._run(packet={**self.packet, "final_labels": [1, 0]})
        leaked = "sealed Final labels from benchmark"
        item = {**self.item, "text": leaked,
                "text_sha256": hashlib.sha256(leaked.encode()).hexdigest()}
        with self.assertRaisesRegex(ValueError, "bounded source-hashed"):
            self._run(packet={**self.packet, "context_items": [item]})
        self.assertFalse(self.root.exists())
        self.assertEqual(self.backend.sample_calls, 0)
        self.assertEqual(list(self.claims.iterdir()), [])

    def test_public_metadata_url_is_syntax_checked_without_fetch(self):
        item = {**self.item, "role": "public_metadata",
                "source_id": "https://example.org/research"}
        result = self._run(packet={**self.packet, "context_items": [item]})
        self.assertTrue(result["valid_fake_response"])
        self.assertFalse(result["model_authorship_proven"])
        self.assertFalse(result["public_origin_independently_verified"])

    def test_private_public_metadata_url_rejected_before_claim(self):
        item = {**self.item, "role": "public_metadata",
                "source_id": "https://localhost/private"}
        with self.assertRaisesRegex(ValueError, "local host denied"):
            self._run(packet={**self.packet, "context_items": [item]})
        self.assertEqual(self.backend.sample_calls, 0)
        self.assertEqual(list(self.claims.iterdir()), [])

    def test_malformed_or_multiple_response_preserved_without_retry(self):
        malformed = {**self.sampled, "candidates": [self.sampled]}
        backend = first.OfflineFakeBackend(malformed)
        result = self._run(backend=backend)
        self.assertFalse(result["valid_fake_response"])
        self.assertEqual(result["reason"], "malformed_or_multiple_response")
        self.assertEqual(load_json(self.root / "raw-response.json"), malformed)
        self.assertEqual(backend.sample_calls, 1)
        self.assertTrue((self.claims / f"{self.cycle_id}.json").is_file())

    def test_missing_model_provenance_fails_after_raw_preservation(self):
        wrong = {**self.sampled, "provider": {**self.sampled["provider"],
                                                "reported_model": "other-model"}}
        result = self._run(backend=first.OfflineFakeBackend(wrong))
        self.assertFalse(result["valid_fake_response"])
        self.assertEqual(result["reason"], "invalid_first_response_or_provenance")
        self.assertEqual(load_json(self.root / "raw-response.json"), wrong)
        self.assertFalse(result["model_identity_proven"])

    def test_truncated_first_response_is_preserved_but_rejected(self):
        truncated = {**self.sampled, "finish_reason": "length"}
        result = self._run(backend=first.OfflineFakeBackend(truncated))
        self.assertFalse(result["valid_fake_response"])
        self.assertEqual(result["reason"], "invalid_first_response_or_provenance")
        self.assertEqual(load_json(self.root / "raw-response.json"), truncated)
        self.assertTrue((self.claims / f"{self.cycle_id}.json").is_file())

    def test_tool_call_markup_not_reinterpreted_or_executed(self):
        tool = {**self.sampled, "text": "<tool_call>run_shell</tool_call>"}
        result = self._run(backend=first.OfflineFakeBackend(tool))
        self.assertFalse(result["valid_fake_response"])
        self.assertEqual(result["reason"], "invalid_first_response_or_provenance")
        self.assertEqual((self.root / "raw-response.txt").read_text(), tool["text"])

    def test_real_backend_object_rejected_before_claim(self):
        with self.assertRaisesRegex(RuntimeError, "live GLM backend disabled"):
            self._run(backend=object())
        self.assertFalse(self.root.exists())
        self.assertEqual(list(self.claims.iterdir()), [])

    def test_source_change_after_first_response_fails_closed(self):
        original = first._current_sources()
        with patch.object(first, "_current_sources",
                          side_effect=[original, {**original, "cost_contract": "0" * 64}]):
            result = self._run()
        self.assertFalse(result["valid_fake_response"])
        self.assertEqual(result["reason"], "executable_source_changed")
        self.assertEqual(self.backend.sample_calls, 1)

    def test_registry_claim_tamper_after_sample_fails_closed(self):
        original_sample = self.backend.sample
        def tamper(*args):
            sampled = original_sample(*args)
            (self.claims / f"{self.cycle_id}.json").write_text('{"tampered":true}\n')
            return sampled
        with patch.object(self.backend, "sample", side_effect=tamper):
            result = self._run()
        self.assertFalse(result["valid_fake_response"])
        self.assertEqual(result["reason"], "claim_input_or_request_changed")
        self.assertEqual(self.backend.sample_calls, 1)

    def test_backend_error_consumes_unique_claim_without_retry(self):
        with patch.object(self.backend, "sample", side_effect=RuntimeError("fake only")):
            with self.assertRaisesRegex(RuntimeError, "fake only"):
                self._run()
        failure = load_json(self.root / "failure.json")
        self.assertEqual(failure["stage"], "first_fake_sample")
        self.assertFalse(failure["automatic_retry"])
        self.assertTrue((self.claims / f"{self.cycle_id}.json").is_file())


if __name__ == "__main__":
    unittest.main()
