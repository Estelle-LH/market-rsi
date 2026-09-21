import copy
import json
from pathlib import Path
import tempfile
import unittest

from glm_canary import HF_MODEL
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake, expected_packet, run,
)
from supervisor_harness.p0_gate1_research_contract import DECISION_SCHEMA


def decision():
    return {
        "schema": DECISION_SCHEMA,
        "investigation_id": "gate1-controller-001",
        "question_id": "2025_whole_season_trade_access",
        "source_id": "polymarket_official_trades",
        "hypothesis": "The official interface documents historical market trade access.",
        "fixed_sample_rule": "Inspect the one frozen official documentation page.",
        "requested_operations": ["inspect_official_documentation"],
        "expected_evidence": "A bounded page hash and documented interface fields.",
        "rights_check": "Record only rights stated by the official source.",
        "max_requests": 1,
        "max_bytes": 100000,
        "max_minutes": 10,
        "max_provider_cost_usd": "0",
        "stop_rule": "Stop after one response or any redirect, error, timeout, or rights uncertainty.",
    }


def sampled(text: str, *, finish_reason: str = "stop") -> dict:
    return {
        "text": text,
        "output_tokens": [201, 202, 203],
        "cached_input_tokens": 0,
        "finish_reason": finish_reason,
        "provider": {
            "reported_model": HF_MODEL,
            "session_id": "offline-session",
            "sampling_session_id": "offline-sampling-session",
        },
    }


class Gate1ControllerAdapterTests(unittest.TestCase):
    def call(self, response: dict, *, packet=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        claims = parent / "claims"
        claims.mkdir()
        cycle = "gate1-controller-test-001"
        root = parent / cycle
        backend = OfflineGate1ProviderFake(response)
        result = run(root=root, claim_root=claims, cycle_id=cycle,
                     packet=expected_packet() if packet is None else packet,
                     backend=backend)
        return result, root, claims, backend

    def test_one_first_response_compiles_one_plan_only_task(self):
        raw = "private reasoning</think>\n```json\n" + json.dumps(decision()) + "\n```<|assistant|>"
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertTrue(result["valid_plan_only_decision"])
        self.assertFalse(result["provider_called"])
        self.assertEqual(backend.sample_calls, 1)
        task = json.loads((root / "task.json").read_text())
        self.assertTrue(task["execution_boundary"]["plan_only"])
        self.assertFalse(task["execution_boundary"]["network_fetch_authorized"])
        self.assertEqual((root / "raw-response.txt").read_text(), raw)

    def test_malformed_first_response_is_preserved_and_never_resampled(self):
        raw = "not one JSON object"
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual((root / "raw-response.txt").read_text(), raw)
        self.assertTrue((root / "failure.json").is_file())
        self.assertFalse((root / "task.json").exists())

    def test_model_cannot_add_url_or_other_authority(self):
        value = decision()
        value["url"] = "https://example.invalid"
        result, root, _claims, backend = self.call(sampled(json.dumps(value)))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "task.json").exists())

    def test_truncated_response_is_terminal_failure(self):
        result, root, _claims, backend = self.call(
            sampled(json.dumps(decision()), finish_reason="length"))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertTrue((root / "raw-response.json").is_file())
        self.assertFalse((root / "provider-receipt.json").exists())

    def test_preencoded_request_calls_dispatch_gate_before_one_sample(self):
        response = sampled(json.dumps(decision()))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        claims = parent / "claims"
        claims.mkdir()
        backend = OfflineGate1ProviderFake(response)
        from supervisor_harness.p0_gate1_controller_adapter import request_turn
        encoded = backend.encode(request_turn(expected_packet()))
        order = []
        result = run(
            root=parent / "gate1-controller-test-003",
            claim_root=claims,
            cycle_id="gate1-controller-test-003",
            packet=expected_packet(), backend=backend, preencoded=encoded,
            before_sample=lambda preview: order.append(preview["schema"]),
        )
        self.assertTrue(result["valid_plan_only_decision"])
        self.assertTrue(result["dispatch_gate_called"])
        self.assertEqual(order, ["market_p0_gate1_controller_cost_preview_v1"])
        self.assertEqual(backend.encode_calls, 1)
        self.assertEqual(backend.sample_calls, 1)

    def test_changed_packet_fails_before_claim_or_sample(self):
        packet = copy.deepcopy(expected_packet())
        packet["hard_limits"]["max_requests_ceiling"] = 21
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        claims = parent / "claims"
        claims.mkdir()
        backend = OfflineGate1ProviderFake(sampled(json.dumps(decision())))
        with self.assertRaises(ValueError):
            run(root=parent / "gate1-controller-test-002", claim_root=claims,
                cycle_id="gate1-controller-test-002", packet=packet,
                backend=backend)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(list(claims.iterdir()), [])

    def test_permanent_claim_rejects_reuse(self):
        response = sampled(json.dumps(decision()))
        result, root, claims, _backend = self.call(response)
        self.assertTrue(result["valid_plan_only_decision"])
        root.rename(root.with_name(root.name + "-preserved"))
        with self.assertRaises(FileExistsError):
            run(root=root, claim_root=claims, cycle_id=root.name,
                packet=expected_packet(),
                backend=OfflineGate1ProviderFake(response))


if __name__ == "__main__":
    unittest.main()
