import copy
import json
import unittest

from supervisor_harness.build_p0_gate1_controller_packet import (
    RIGHTS_POLICY, SOURCE_REGISTRY, build,
)
from supervisor_harness.p0_gate1_research_contract import (
    CAPABILITY_REGISTRY, CONTROLLER_SCIENTIFIC_FIELDS, DECISION_SCHEMA,
    EXACT_TRADE_SAMPLE_RULE, IMPLEMENTED_OPERATIONS, KNOWN_OPERATIONS, TASK_SCHEMA,
    TRUSTED_TASK_FIELDS, parse_unique_json, validate_and_compile,
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
            "fixed_sample_rule": "Inspect the one frozen official documentation page.",
            "requested_operations": ["inspect_official_documentation"],
            "expected_evidence": "A bounded raw page hash and documented interface fields.",
            "max_requests": 1,
            "max_bytes": 1000000,
            "max_minutes": 20,
            "max_provider_cost_usd": "0",
            "stop_rule": "Stop after one response or any redirect, error, timeout, or rights uncertainty.",
        }

    def test_compiles_only_a_plan(self):
        task = validate_and_compile(self.decision, self.packet)
        self.assertEqual(task["schema"], TASK_SCHEMA)
        self.assertEqual(task["source"]["url"],
                         "https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets")
        self.assertTrue(task["execution_boundary"]["plan_only"])
        self.assertFalse(task["execution_boundary"]["network_fetch_authorized"])
        self.assertEqual(task["rights_policy"], RIGHTS_POLICY)
        self.assertEqual(task["capability"]["handler_id"],
                         "p0_gate1_public_fetch.fetch_snapshot:v1")
        self.assertTrue(task["capability"]["executable"])
        self.assertEqual(task["capability"]["sample_contract"]["document_count"],
                         1)

    def test_controller_sees_only_implemented_operations(self):
        self.assertEqual(IMPLEMENTED_OPERATIONS,
                         frozenset({"inspect_official_documentation",
                                    "fetch_fixed_public_sample"}))
        self.assertEqual(IMPLEMENTED_OPERATIONS,
                         frozenset(operation
                                   for capabilities in CAPABILITY_REGISTRY.values()
                                   for operation in capabilities))
        self.assertTrue(IMPLEMENTED_OPERATIONS < KNOWN_OPERATIONS)

    def test_scientific_and_trusted_fields_are_explicitly_separate(self):
        task = validate_and_compile(self.decision, self.packet)
        authority = task["field_authority"]
        self.assertEqual(set(authority["controller_scientific"]),
                         CONTROLLER_SCIENTIFIC_FIELDS)
        self.assertEqual(set(authority["trusted"]), TRUSTED_TASK_FIELDS)
        self.assertTrue(CONTROLLER_SCIENTIFIC_FIELDS.isdisjoint(
            TRUSTED_TASK_FIELDS))
        self.assertNotIn("schema", CONTROLLER_SCIENTIFIC_FIELDS)
        self.assertIn("schema", TRUSTED_TASK_FIELDS)

    def test_historical_unimplemented_query_plan_fails_closed(self):
        changed = copy.deepcopy(self.decision)
        changed["fixed_sample_rule"] = (
            "Use the first, middle, and last scheduled weeks without "
            "outcome-based replacement."
        )
        changed["requested_operations"] = [
            "inspect_official_documentation", "query_public_metadata"]
        changed["max_requests"] = 12
        changed["max_provider_cost_usd"] = "0.03"
        with self.assertRaises(ValueError):
            validate_and_compile(changed, self.packet)

    def test_every_known_but_unimplemented_operation_fails_closed(self):
        for operation in KNOWN_OPERATIONS - IMPLEMENTED_OPERATIONS:
            with self.subTest(operation=operation):
                changed = copy.deepcopy(self.decision)
                changed["requested_operations"] = [operation]
                with self.assertRaises(ValueError):
                    validate_and_compile(changed, self.packet)

    def test_unregistered_source_operation_or_sample_fails_closed(self):
        cases = []
        changed = copy.deepcopy(self.decision)
        changed["fixed_sample_rule"] = "Inspect three chosen documentation pages."
        cases.append(changed)
        changed = copy.deepcopy(self.decision)
        changed["source_id"] = "nflverse_official_pbp_releases"
        cases.append(changed)
        changed = copy.deepcopy(self.decision)
        changed["max_requests"] = 2
        cases.append(changed)
        changed = copy.deepcopy(self.decision)
        changed["max_provider_cost_usd"] = "0.01"
        cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    validate_and_compile(changed, self.packet)

    def test_registered_release_page_sample_compiles(self):
        changed = copy.deepcopy(self.decision)
        changed["source_id"] = "nflverse_official_pbp_releases"
        changed["fixed_sample_rule"] = (
            "Inspect the one frozen official project release page.")
        task = validate_and_compile(changed, self.packet)
        self.assertEqual(task["capability"]["source_id"],
                         "nflverse_official_pbp_releases")

    def test_exact_trade_sample_capability_compiles_with_trusted_chain(self):
        changed = copy.deepcopy(self.decision)
        changed["fixed_sample_rule"] = EXACT_TRADE_SAMPLE_RULE
        changed["requested_operations"] = ["fetch_fixed_public_sample"]
        changed["max_requests"] = 6
        changed["max_bytes"] = 2_000_000
        changed["max_minutes"] = 15
        task = validate_and_compile(changed, self.packet)
        self.assertEqual(task["capability"]["handler_id"],
                         "p0_gate1_plan_compiler.compile_exact_request_plan:v1")
        self.assertEqual(task["capability"]["sample_contract"]["rule_id"],
                         "first_middle_last_by_game_date_game_id_v1")
        self.assertEqual(task["bounds"], {
            "max_requests": 6,
            "max_bytes": 2_000_000,
            "max_minutes": 15,
            "max_provider_cost_usd": "0",
        })

    def test_trade_capability_rejects_wrong_question_or_any_limit_drift(self):
        base = copy.deepcopy(self.decision)
        base["fixed_sample_rule"] = EXACT_TRADE_SAMPLE_RULE
        base["requested_operations"] = ["fetch_fixed_public_sample"]
        base["max_requests"] = 6
        base["max_bytes"] = 2_000_000
        base["max_minutes"] = 15
        for field, value in (("question_id", "2023_real_fill_sparsity"),
                             ("max_requests", 7),
                             ("max_bytes", 1_999_999),
                             ("max_minutes", 14),
                             ("max_provider_cost_usd", "0.01")):
            changed = copy.deepcopy(base)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_and_compile(changed, self.packet)

    def test_model_cannot_supply_or_rewrite_rights_policy(self):
        changed = copy.deepcopy(self.decision)
        changed["rights_check"] = "Model-authored rights text"
        with self.assertRaises(ValueError):
            validate_and_compile(changed, self.packet)
        changed = copy.deepcopy(self.packet)
        changed["trusted_rights_policy"] = {
            "policy_id": "weaker",
            "requirements": [],
        }
        with self.assertRaises(ValueError):
            validate_and_compile(self.decision, changed)

    def test_packet_cannot_rewrite_trusted_source_registry(self):
        changed = copy.deepcopy(self.packet)
        changed["allowed_sources"][1]["url"] = "https://example.invalid"
        with self.assertRaises(ValueError):
            validate_and_compile(self.decision, changed)

    def test_shared_nested_packet_objects_cannot_rewrite_trusted_authority(self):
        # build() must not alias these nested constants, and the contract must
        # independently compare against its own frozen authority.
        source = self.packet["allowed_sources"][1]
        old_url = source["url"]
        source["url"] = "https://example.invalid/aliased"
        self.assertEqual(SOURCE_REGISTRY[1]["url"], old_url)
        with self.assertRaisesRegex(ValueError, "source registry changed"):
            validate_and_compile(self.decision, self.packet)

        policy = self.packet["trusted_rights_policy"]
        old_policy_id = policy["policy_id"]
        policy["policy_id"] = "mutated-through-shallow-alias"
        self.assertEqual(RIGHTS_POLICY["policy_id"], old_policy_id)
        with self.assertRaisesRegex(ValueError, "rights policy changed"):
            validate_and_compile(self.decision, self.packet)

    def test_packet_cannot_expand_trusted_hard_limits(self):
        changed = copy.deepcopy(self.packet)
        changed["hard_limits"]["max_bytes_ceiling"] = 50_000_000
        changed["hard_limits"]["max_minutes_ceiling"] = 300
        expanded = copy.deepcopy(self.decision)
        expanded["max_bytes"] = 40_000_000
        expanded["max_minutes"] = 200
        with self.assertRaisesRegex(ValueError, "hard limits changed"):
            validate_and_compile(expanded, changed)

    def test_packet_cannot_reclassify_trusted_schema_as_controller_field(self):
        changed = copy.deepcopy(self.packet)
        changed["required_decision_fields"].append("schema")
        with self.assertRaises(ValueError):
            validate_and_compile(self.decision, changed)

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
        raw = raw[:-1] + ',"schema":"market_p0_gate1_controller_decision_v2"}'
        with self.assertRaises(ValueError):
            parse_unique_json(raw)


if __name__ == "__main__":
    unittest.main()
