import copy
import json
from pathlib import Path
import tempfile
import unittest

from market_rsi import digest, file_hash
from supervisor_harness.build_p0_gate1_controller_packet import (
    ALLOWED_QUESTIONS, EXECUTABLE_DOCUMENTATION_CHOICES,
    SOURCE_REGISTRY, build, run,
)


class Gate1ControllerPacketTests(unittest.TestCase):
    def setUp(self):
        self.gate0 = {
            "schema": "market_p0_gate0_verdict_v1",
            "metadata_inventory_passed": True,
            "2025_formal_final_admitted": False,
        }
        self.live = {
            "schema": "market_controller_b_live_acceptance_v1",
            "passed": True,
            "claim_boundaries": {
                "bounded_live_transport_and_accounting_proven": True,
                "formal_admission": False,
                "prediction_improvement_proven": False,
            },
        }

    def test_packet_is_plan_only_and_has_fixed_bounds(self):
        packet = build(self.gate0, self.live)
        self.assertEqual(packet["allowed_questions"], list(ALLOWED_QUESTIONS))
        self.assertEqual(packet["allowed_sources"], list(SOURCE_REGISTRY))
        self.assertFalse(packet["hard_limits"]["purchase_allowed"])
        self.assertFalse(packet["hard_limits"]["sealed_or_scored_rows_allowed"])
        self.assertFalse(packet["current_execution_boundary"]
                         ["arbitrary_research_task_execution_accepted"])
        self.assertEqual(
            packet["current_execution_boundary"]["executable_documentation_choices"],
            EXECUTABLE_DOCUMENTATION_CHOICES,
        )
        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value))
            return set()
        self.assertTrue({"game_id", "task_id", "prompt", "label",
                         "prediction"}.isdisjoint(keys(packet)))
        self.assertNotIn("prediction", packet["known_aggregate_evidence"])

    def test_closed_gate0_is_required(self):
        changed = copy.deepcopy(self.gate0)
        changed["2025_formal_final_admitted"] = True
        with self.assertRaises(ValueError):
            build(changed, self.live)

    def test_transport_claim_cannot_be_overstated(self):
        changed = copy.deepcopy(self.live)
        changed["claim_boundaries"]["formal_admission"] = True
        with self.assertRaises(ValueError):
            build(self.gate0, changed)

    def test_receipt_distinguishes_file_and_canonical_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            gate0 = (repo / "artifacts/p0-data-admission-gate0-20260918-01"
                     / "gate0-verdict.json")
            acceptance = (repo / "research/market_rsi/supervisor_harness"
                          / "P0_CONTROLLER_B_LIVE_ACCEPTANCE_2026-09-19.json")
            gate0.parent.mkdir(parents=True)
            acceptance.parent.mkdir(parents=True)
            gate0.write_text(json.dumps(self.gate0, sort_keys=True) + "\n")
            acceptance.write_text(json.dumps(self.live, sort_keys=True) + "\n")
            output = repo / "artifacts/fresh-packet"
            receipt = run(repo, output)
            packet_path = output / "controller-input.json"
            packet = json.loads(packet_path.read_text())
            self.assertEqual(receipt["packet_sha256"], file_hash(packet_path))
            self.assertEqual(receipt["packet_file_sha256"],
                             file_hash(packet_path))
            self.assertEqual(receipt["packet_canonical_sha256"],
                             digest(packet))
            self.assertNotEqual(receipt["packet_file_sha256"],
                                receipt["packet_canonical_sha256"])


if __name__ == "__main__":
    unittest.main()
