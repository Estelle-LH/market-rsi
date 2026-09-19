"""Strict-fake tests for the bounded live adapter; zero external calls."""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from glm_canary import MODEL, cost
from market_rsi import canonical, digest, file_hash, load_json
from supervisor_harness import bounded_live_adapter_v2 as adapter
from supervisor_harness import frozen_glm_first_response as first


class BoundedLiveAdapterV2Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.claims = self.base / "claims"
        self.claims.mkdir()
        self.output = self.base / "output"
        self.output.mkdir()

    def _packet(self, cycle_id: str) -> dict:
        text = "bounded public synthetic context for one hash"
        return {"schema": first.PACKET_SCHEMA, "cycle_id": cycle_id,
                "context_items": [{
                    "role": "synthetic_fixture", "source_id": "synthetic:one",
                    "text": text,
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest()}]}

    def _decision(self, **changes) -> dict:
        return {"schema": adapter.offline_driver.DECISION_SCHEMA,
                "task_id": "one-public-hash", "source_id": "synthetic:one",
                "action": "hash_public_text", **changes}

    def _sampled(self, *, decision=None, text=None, **changes) -> dict:
        value = {"text": text if text is not None else canonical(
                     self._decision() if decision is None else decision),
                 "output_tokens": [21, 22], "cached_input_tokens": 1,
                 "finish_reason": "stop",
                 "provider": {"reported_model": MODEL,
                              "session_id": "fake-provider-session",
                              "sampling_session_id": "fake-sampling-session"}}
        value.update(changes)
        return value

    def _case(self, suffix: str, *, sampled=None, packet=None,
              process_mode="ok", cleanup_mode="ok", sample_error=None,
              root_parent=None):
        cycle_id = "bounded-live-" + suffix
        backend = adapter.OfflinePinnedProviderFake(
            self._sampled() if sampled is None else sampled,
            sample_error=sample_error)
        process = adapter.OfflineOneTaskProcessFake(mode=process_mode)
        control = adapter.OfflineContainerControlFake(mode=cleanup_mode)
        parent = root_parent or self.output
        root = parent / cycle_id
        result = adapter.run_bounded_adapter(
            root=root, claim_root=self.claims, cycle_id=cycle_id,
            packet=self._packet(cycle_id) if packet is None else packet,
            backend=backend, process=process, container_control=control)
        return result, backend, process, control, root

    def test_exact_first_response_cost_task_process_cleanup_hash_chain(self):
        result, backend, process, control, root = self._case("success")
        self.assertTrue(result["passed_offline_boundary_test"])
        self.assertFalse(result["completed_live_chain_pending_review"])
        self.assertEqual((backend.encode_calls, backend.sample_calls), (1, 1))
        self.assertEqual((process.launch_calls, process.publish_calls,
                          process.wait_calls, control.calls), (1, 1, 1, 1))
        self.assertEqual((root / "raw-response.txt").read_text(),
                         self._sampled()["text"])
        provider = load_json(root / "provider-receipt.json")
        self.assertEqual(provider["requested_model"], MODEL)
        self.assertEqual(provider["reported_model"], MODEL)
        self.assertEqual(provider["input_tokens"], 3)
        self.assertEqual(provider["output_tokens"], 2)
        self.assertEqual(provider["cached_input_tokens"], 1)
        self.assertEqual(provider["metered_cost_usd_not_invoice"],
                         str(cost(3, 2, 1)))
        self.assertIn("not invoice", provider["cost_basis"])
        self.assertFalse(provider["provider_called"])
        request = load_json(root / "request.json")
        self.assertEqual(request["tools"], [])
        self.assertEqual(request["num_samples"], 1)
        task, order = load_json(root / "task.json"), load_json(root / "order.json")
        self.assertEqual(set(task), {"schema", "cycle_id", "input_sha256",
                                     "sequence", "task_id", "public_text"})
        self.assertEqual(set(order), {"schema", "cycle_id", "input_sha256",
                                      "sequence", "task_id", "task_sha256",
                                      "public_text"})
        self.assertEqual(order["task_sha256"], digest(task))
        self.assertEqual(process.order, order)
        self.assertEqual(load_json(root / "raw-ack.json")["order_sha256"],
                         digest(order))
        self.assertEqual(load_json(root / "raw-event.json")["order_sha256"],
                         digest(order))
        launch = load_json(root / "b-launch.json")
        self.assertEqual(launch["expected_orders"], 1)
        self.assertEqual(launch["credential_fields_passed_to_b"], [])
        self.assertNotIn("--env", launch["command"])
        self.assertNotIn("--env-file", launch["command"])
        self.assertTrue(load_json(root / "process.json")["process_reaped"])
        self.assertTrue(load_json(root / "cleanup.json")
                        ["exact_container_cleanup_verified"])
        for name, expected in result["artifact_sha256"].items():
            self.assertEqual(expected, file_hash(root / name))
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["model_authorship_independently_proven"])
        self.assertFalse(result["formal_admission"])
        self.assertFalse(result["budget_mutated_by_adapter"])

    def test_reasoning_prefix_keeps_raw_bytes_but_uses_one_final_json(self):
        raw = "<think>unexposed internal work</think>\n" + canonical(self._decision())
        result, _backend, process, _control, root = self._case(
            "reasoning-prefix", sampled=self._sampled(text=raw))
        self.assertTrue(result["passed_offline_boundary_test"])
        self.assertEqual((root / "raw-response.txt").read_text(), raw)
        self.assertEqual(process.publish_calls, 1)

    def test_protected_packet_rejected_before_claim_or_sample(self):
        cycle_id = "bounded-live-protected"
        backend = adapter.OfflinePinnedProviderFake(self._sampled())
        process = adapter.OfflineOneTaskProcessFake()
        control = adapter.OfflineContainerControlFake()
        with self.assertRaisesRegex(ValueError, "exact public/synthetic packet"):
            adapter.run_bounded_adapter(
                root=self.output / cycle_id, claim_root=self.claims,
                cycle_id=cycle_id,
                packet={**self._packet(cycle_id), "final_labels": [1]},
                backend=backend, process=process, container_control=control)
        self.assertEqual((backend.encode_calls, backend.sample_calls), (0, 0))
        self.assertEqual(process.launch_calls, 0)
        self.assertEqual(list(self.claims.iterdir()), [])

        leaked_cycle = "bounded-live-protected-text"
        leaked = "sealed Final labels and API key material"
        leaked_packet = self._packet(leaked_cycle)
        leaked_packet["context_items"][0]["text"] = leaked
        leaked_packet["context_items"][0]["text_sha256"] = hashlib.sha256(
            leaked.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "bounded source-hashed"):
            adapter.run_bounded_adapter(
                root=self.output / leaked_cycle, claim_root=self.claims,
                cycle_id=leaked_cycle, packet=leaked_packet,
                backend=adapter.OfflinePinnedProviderFake(self._sampled()),
                process=adapter.OfflineOneTaskProcessFake(),
                container_control=adapter.OfflineContainerControlFake())
        self.assertEqual(list(self.claims.iterdir()), [])

    def test_truncation_and_tool_call_are_preserved_but_never_reach_b(self):
        cases = {
            "truncated": self._sampled(finish_reason="length"),
            "tool-call": self._sampled(text="<tool_call>shell</tool_call>"),
        }
        for suffix, sampled in cases.items():
            with self.subTest(suffix=suffix):
                result, backend, process, control, root = self._case(
                    suffix, sampled=sampled)
                self.assertFalse(result["passed_offline_boundary_test"])
                self.assertEqual(backend.sample_calls, 1)
                self.assertEqual(process.launch_calls, 0)
                self.assertEqual(control.calls, 0)
                self.assertEqual(load_json(root / "raw-response.json"), sampled)
                self.assertTrue((root / "failure.json").is_file())

    def test_malformed_and_multiple_responses_are_terminal_without_retry(self):
        malformed = self._sampled(text='{"schema":1}{"schema":2}')
        multiple = {**self._sampled(), "candidates": [self._sampled()]}
        for suffix, sampled in (("malformed", malformed), ("multiple", multiple)):
            with self.subTest(suffix=suffix):
                result, backend, process, _control, root = self._case(
                    suffix, sampled=sampled)
                self.assertFalse(result["passed_offline_boundary_test"])
                self.assertEqual(backend.sample_calls, 1)
                self.assertEqual(process.launch_calls, 0)
                self.assertEqual(load_json(root / "raw-response.json"), sampled)
                self.assertFalse(result["automatic_retry"])

    def test_duplicate_id_rejected_without_second_encode_or_sample(self):
        first_result, _backend, _process, _control, _root = self._case("duplicate")
        self.assertTrue(first_result["passed_offline_boundary_test"])
        other = self.base / "other"
        other.mkdir()
        cycle_id = "bounded-live-duplicate"
        backend = adapter.OfflinePinnedProviderFake(self._sampled())
        process = adapter.OfflineOneTaskProcessFake()
        with self.assertRaises(FileExistsError):
            adapter.run_bounded_adapter(
                root=other / cycle_id, claim_root=self.claims,
                cycle_id=cycle_id, packet=self._packet(cycle_id),
                backend=backend, process=process,
                container_control=adapter.OfflineContainerControlFake())
        self.assertEqual((backend.encode_calls, backend.sample_calls), (0, 0))
        self.assertEqual(process.launch_calls, 0)

    def test_nonallowlisted_choice_and_authority_fields_never_launch_b(self):
        choices = [
            self._decision(source_id="synthetic:not-allowed"),
            self._decision(path="/host/private"),
            self._decision(shell="uname"),
            self._decision(key="fake-key"),
            self._decision(host="localhost"),
            self._decision(code="print(1)"),
        ]
        for index, decision in enumerate(choices):
            with self.subTest(decision=decision):
                result, backend, process, _control, _root = self._case(
                    f"authority-{index}", sampled=self._sampled(decision=decision))
                self.assertFalse(result["passed_offline_boundary_test"])
                self.assertEqual(backend.sample_calls, 1)
                self.assertEqual(process.launch_calls, 0)

    def test_source_tamper_after_first_response_stops_before_b(self):
        original = adapter._sources()
        with patch.object(adapter, "_sources", side_effect=[
                original, {**original, "guest": "0" * 64}]):
            result, backend, process, _control, root = self._case("source-tamper")
        self.assertFalse(result["passed_offline_boundary_test"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(process.launch_calls, 0)
        self.assertEqual(load_json(root / "failure.json")["stage"],
                         "provider_receipt")

    def test_provider_and_b_timeouts_are_terminal_and_cleanup_b_if_started(self):
        result, backend, process, control, _root = self._case(
            "provider-timeout", sample_error=TimeoutError("fake provider timeout"))
        self.assertFalse(result["passed_offline_boundary_test"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(process.launch_calls, 0)
        self.assertEqual(control.calls, 0)
        for mode in ("ack_timeout", "event_timeout", "process_timeout"):
            with self.subTest(mode=mode):
                result, backend, process, control, root = self._case(
                    mode, process_mode=mode)
                self.assertFalse(result["passed_offline_boundary_test"])
                self.assertEqual(backend.sample_calls, 1)
                self.assertEqual(process.launch_calls, 1)
                self.assertEqual(control.calls, 1)
                self.assertTrue((root / "cleanup.json").is_file())

    def test_partial_launch_failure_still_reaps_and_cleans_exact_container(self):
        result, backend, process, control, root = self._case(
            "partial-launch", process_mode="launch_error_after_start")
        self.assertFalse(result["passed_offline_boundary_test"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(process.launch_calls, 1)
        self.assertEqual(process.wait_calls, 1)
        self.assertEqual(control.calls, 1)
        self.assertTrue(load_json(root / "cleanup.json")
                        ["exact_container_cleanup_verified"])
        self.assertEqual(load_json(root / "failure.json")["stage"], "b_launch")

    def test_missing_token_cost_model_process_or_cleanup_fails_closed(self):
        missing_cost = self._sampled()
        missing_cost.pop("cached_input_tokens")
        wrong_model = self._sampled(provider={
            "reported_model": "other-model", "session_id": "fake-provider-session",
            "sampling_session_id": "fake-sampling-session"})
        for suffix, sampled in (("missing-cost", missing_cost),
                                ("wrong-model", wrong_model)):
            with self.subTest(suffix=suffix):
                result, _backend, process, _control, root = self._case(
                    suffix, sampled=sampled)
                self.assertFalse(result["passed_offline_boundary_test"])
                self.assertEqual(process.launch_calls, 0)
                self.assertIsNone(result["metered_cost_usd_not_invoice"])
                self.assertFalse((root / "provider-receipt.json").exists())
        result, _backend, _process, control, _root = self._case(
            "missing-process", process_mode="missing_process")
        self.assertFalse(result["passed_offline_boundary_test"])
        self.assertEqual(control.calls, 1)
        result, _backend, _process, control, root = self._case(
            "missing-cleanup", cleanup_mode="missing_cleanup")
        self.assertFalse(result["passed_offline_boundary_test"])
        self.assertEqual(control.calls, 1)
        self.assertFalse(load_json(root / "cleanup.json")
                         ["exact_container_cleanup_verified"])

    def test_wrong_ack_event_extra_exchange_and_receipt_tamper_fail(self):
        for mode in ("wrong_ack", "wrong_event", "extra_order"):
            with self.subTest(mode=mode):
                result, _backend, _process, control, _root = self._case(
                    mode, process_mode=mode)
                self.assertFalse(result["passed_offline_boundary_test"])
                self.assertEqual(control.calls, 1)
        cycle_id = "bounded-live-disk-tamper"
        process = adapter.OfflineOneTaskProcessFake()
        original = process.read_event

        def tamper(timeout_seconds):
            raw = original(timeout_seconds)
            (self.output / cycle_id / "order.json").write_text('{"tampered":true}\n')
            return raw

        process.read_event = tamper
        result = adapter.run_bounded_adapter(
            root=self.output / cycle_id, claim_root=self.claims,
            cycle_id=cycle_id, packet=self._packet(cycle_id),
            backend=adapter.OfflinePinnedProviderFake(self._sampled()),
            process=process,
            container_control=adapter.OfflineContainerControlFake())
        self.assertFalse(result["passed_offline_boundary_test"])

    def test_mismatched_or_arbitrary_interfaces_rejected_before_claim(self):
        cycle_id = "bounded-live-bad-interface"
        for backend, process, control in (
            (object(), adapter.OfflineOneTaskProcessFake(),
             adapter.OfflineContainerControlFake()),
            (adapter.OfflinePinnedProviderFake(self._sampled()), object(),
             adapter.OfflineContainerControlFake()),
            (adapter.OfflinePinnedProviderFake(self._sampled()),
             adapter.OfflineOneTaskProcessFake(), object()),
        ):
            with self.subTest(types=(type(backend), type(process), type(control))):
                with self.assertRaisesRegex(RuntimeError, "exact matched types"):
                    adapter.run_bounded_adapter(
                        root=self.output / cycle_id, claim_root=self.claims,
                        cycle_id=cycle_id, packet=self._packet(cycle_id),
                        backend=backend, process=process,
                        container_control=control)
        self.assertEqual(list(self.claims.iterdir()), [])

    def test_success_fakes_cannot_reach_subprocess_or_live_backend(self):
        with patch.object(adapter.subprocess, "Popen",
                          side_effect=AssertionError("Docker forbidden")), \
             patch.object(adapter.subprocess, "run",
                          side_effect=AssertionError("container control forbidden")), \
             patch.object(adapter.TinkerGLMBackend, "sample",
                          side_effect=AssertionError("Tinker forbidden")):
            result, backend, process, control, _root = self._case("no-external")
        self.assertTrue(result["passed_offline_boundary_test"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse(backend.provider_called)
        self.assertFalse(process.external_called)
        self.assertFalse(control.external_called)

    def test_production_cleanup_reaps_process_even_if_inspection_errors(self):
        class FakePopen:
            def __init__(self):
                self.returncode = None
                self.killed = False

            def poll(self):
                return self.returncode

            def communicate(self, timeout=None):
                if self.returncode is None and not self.killed:
                    raise subprocess.TimeoutExpired("fake", timeout)
                self.returncode = -9 if self.killed else 0
                return "", ""

            def kill(self):
                self.killed = True
                self.returncode = -9

        process = adapter.LocalDockerOneTaskProcess()
        process.container_name = "market-rsi-b-fake-cleanup"
        process.process = FakePopen()
        with patch.object(adapter.cleanup_contract, "_cleanup_exact",
                          side_effect=RuntimeError("offline inspection failure")):
            receipt = adapter.LocalDockerContainerControl().cleanup(process)
        self.assertTrue(receipt["process_reaped"])
        self.assertFalse(receipt["exact_container_cleanup_verified"])
        self.assertEqual(receipt["final_inspection"], "unknown")
        self.assertTrue(process.process.killed)


if __name__ == "__main__":
    unittest.main()
