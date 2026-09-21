import copy
import unittest

from supervisor_harness.build_p0_gate1_controller_packet import (
    ALLOWED_QUESTIONS, SOURCE_REGISTRY, build,
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


if __name__ == "__main__":
    unittest.main()
