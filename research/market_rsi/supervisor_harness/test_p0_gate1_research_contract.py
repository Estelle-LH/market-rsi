import copy
import json
import unittest

from supervisor_harness.build_p0_gate1_controller_packet import build
from supervisor_harness.p0_gate1_research_contract import (
    DECISION_SCHEMA, TASK_SCHEMA, parse_unique_json, validate_and_compile,
)


class Gate1ResearchContractTests(unittest.TestCase):
    def setUp(self):
        gate0 = {"schema": "market_p0_gate0_verdict_v1",
                 "metadata_inventory_passed": True,
                 "2025_formal_final_admitted": False}
        live = {"schema": "market_controller_b_live_acceptance_v1", "passed": True,
                "claim_boundaries": {
                    "bounded_live_transport_and_accounting_proven": True,
                    "formal_admission": False,
                    "prediction_improvement_proven": False}}
        self.packet = build(gate0, live)
        self.decision = {
            "schema": DECISION_SCHEMA,
            "investigation_id": "gate1-source-plan-001",
            "question_id": "2025_whole_season_trade_access",
            "source_id": "polymarket_official_trades",
            "hypothesis": "The official interface can identify whether fixed public markets expose historical trade rows.",
            "fixed_sample_rule": "Use the first, middle, and last scheduled weeks without outcome-based replacement.",
            "requested_operations": ["inspect_official_documentation", "query_public_metadata"],
            "expected_evidence": "Request metadata, response hashes, row counts, and explicit misses.",
            "rights_check": "Record official terms and mark research use unknown unless directly supported.",
            "max_requests": 12,
            "max_bytes": 1000000,
            "max_minutes": 20,
            "max_provider_cost_usd": "0.03",
            "stop_rule": "Stop on access denial, rights uncertainty, cap exhaustion, or completion of the fixed sample.",
        }

    def test_compiles_only_a_plan(self):
        task = validate_and_compile(self.decision, self.packet)
        self.assertEqual(task["schema"], TASK_SCHEMA)
        self.assertEqual(task["source"]["url"],
                         "https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets")
        self.assertTrue(task["execution_boundary"]["plan_only"])
        self.assertFalse(task["execution_boundary"]["network_fetch_authorized"])

    def test_model_cannot_supply_authority_fields(self):
        changed = copy.deepcopy(self.decision)
        changed["url"] = "https://example.invalid"
        with self.assertRaises(ValueError):
            validate_and_compile(changed, self.packet)

    def test_caps_are_hard(self):
        for field, value in (("max_requests", 21), ("max_bytes", 5000001),
                             ("max_minutes", 31), ("max_provider_cost_usd", "0.051")):
            changed = copy.deepcopy(self.decision)
            changed[field] = value
            with self.assertRaises(ValueError):
                validate_and_compile(changed, self.packet)

    def test_forbidden_authority_in_text_fails(self):
        changed = copy.deepcopy(self.decision)
        changed["hypothesis"] = "Run a shell command to inspect sealed_final."
        with self.assertRaises(ValueError):
            validate_and_compile(changed, self.packet)

    def test_duplicate_json_member_fails(self):
        raw = json.dumps(self.decision)
        raw = raw[:-1] + ',"schema":"market_p0_gate1_controller_decision_v1"}'
        with self.assertRaises(ValueError):
            parse_unique_json(raw)


if __name__ == "__main__":
    unittest.main()
