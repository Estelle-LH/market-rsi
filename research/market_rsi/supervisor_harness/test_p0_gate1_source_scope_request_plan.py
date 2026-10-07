"""Offline tests for the exact D0-to-document-request trust bridge."""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import inspect
import json
import unittest
from unittest.mock import patch

from supervisor_harness.build_p0_gate1_controller_packet import build
from supervisor_harness import p0_gate1_source_scope_request_plan as bridge
from supervisor_harness.prospective_source_scope_decision import validate_decision


def _digest(value):
    raw = json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _packet():
    return build(
        {
            "schema": "market_p0_gate0_verdict_v1",
            "metadata_inventory_passed": True,
            "2025_formal_final_admitted": False,
        },
        {
            "schema": "market_controller_b_live_acceptance_v1",
            "passed": True,
            "claim_boundaries": {
                "bounded_live_transport_and_accounting_proven": True,
                "formal_admission": False,
                "prediction_improvement_proven": False,
            },
        },
    )


def _decision():
    return deepcopy(bridge._EXPECTED_DECISION)


def _submission(decision):
    investigation = decision["bounded_investigation"]
    future = decision["future_role_split"]
    horizon = decision["horizon_cutoff"]
    return {
        "bounded_investigation": {
            key: investigation[key]
            for key in (
                "max_documents_proposed", "max_elapsed_seconds_proposed",
                "max_provider_requests_proposed", "max_raw_bytes_proposed", "mode",
            )
        },
        "future_role_split": {
            key: future[key]
            for key in (
                "exposure_ledger_id", "requested_future_role", "split_policy_id",
                "split_policy_sha256",
            )
        },
        "horizon_cutoff": {
            key: horizon[key]
            for key in (
                "claim_semantics", "cutoff_contract_sha256", "cutoff_semantics_id",
                "label_window_end_relation", "label_window_start_relation",
                "prediction_horizon_us",
            )
        },
        "intended_uses": deepcopy(decision["intended_uses"]),
        "scientific_source_response": deepcopy(decision["scientific_source_response"]),
    }


def _provenance(decision, packet):
    return {
        "schema": "market_rsi_source_scope_field_provenance_v1",
        "cycle_id": bridge.D0_CYCLE_ID,
        "decision_id": bridge.D0_DECISION_ID,
        "controller_authored_objects": [
            "bounded_investigation", "future_role_split", "horizon_cutoff",
            "intended_uses", "scientific_source_response",
        ],
        "trusted_protocol_fields": [
            "decision_id", "decision_status", "non_authority", "schema",
            "bounded_investigation.max_spend_usd_micros_proposed",
            "bounded_investigation.preserve_failures_without_retry_expansion",
            "bounded_investigation.stop_before_unregistered_response_class",
            "bounded_investigation.stop_on_first_rights_or_authority_unknown",
            "future_role_split.cross_role_reuse_policy",
            "future_role_split.unknown_exposure_policy",
            "horizon_cutoff.availability_cutoff_relation",
            "horizon_cutoff.availability_formula_id",
            "horizon_cutoff.provider_receiver_clocks_separate",
        ],
        "submission_sha256": _digest(_submission(decision)),
        "decision_sha256": _digest(decision),
        "scope_options_sha256": _digest(packet["prospective_source_scope_decision"]),
        "raw_controller_response_sha256": bridge.D0_RAW_RESPONSE_SHA256,
        "all_external_authority_false": True,
    }


class SourceScopeRequestPlanTests(unittest.TestCase):
    def setUp(self):
        self.packet = _packet()
        self.decision = _decision()
        self.provenance = _provenance(self.decision, self.packet)

    def compile(self, **overrides):
        values = {
            "decision": self.decision,
            "decision_provenance": self.provenance,
            "packet": self.packet,
            "d0_source_sha256": bridge.D0_CONTROLLED_SOURCE_SHA256,
        }
        values.update(overrides)
        return bridge.compile_document_request_plan(**values)

    def test_exact_decision_compiles_twice_to_one_nonexecuting_plan(self):
        first = self.compile()
        second = self.compile()
        self.assertEqual(first, second)
        plan = first["request_plan"]
        self.assertEqual(first["request_plan_canonical_sha256"], _digest(plan))
        self.assertEqual(
            first["request_plan_canonical_sha256"],
            "34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c",
        )
        self.assertEqual(plan["prospective_request"]["method"], "GET")
        self.assertEqual(plan["prospective_request"]["url"], bridge.DOCUMENT_URL)
        self.assertEqual(plan["prospective_request"]["query_parameters"], [])
        self.assertIsNone(plan["prospective_request"]["body"])
        self.assertEqual(plan["limits"]["max_http_attempts_if_later_authorized"], 1)
        self.assertEqual(plan["limits"]["d0_provider_requests_proposed"], 0)
        self.assertTrue(plan["authority"]["plan_only"])
        self.assertTrue(all(
            value is False
            for key, value in plan["authority"].items()
            if key != "plan_only"
        ))
        self.assertFalse(
            first["future_fetch_admission_requirements"]["fetch_authorized"]
        )
        self.assertEqual(
            plan["response_contract_if_later_authorized"][
                "allowed_normalized_content_types"
            ],
            ["application/json", "text/html", "text/markdown", "text/plain"],
        )
        from supervisor_harness.protocol_source_release import PROTOCOL_FILES
        self.assertIn(
            "supervisor_harness/p0_gate1_source_scope_request_plan.py",
            PROTOCOL_FILES,
        )
        self.assertIn(
            "supervisor_harness/test_p0_gate1_source_scope_request_plan.py",
            PROTOCOL_FILES,
        )

    def test_generic_validator_accepts_reassignment_but_bridge_rejects_it(self):
        mutated = deepcopy(self.decision)
        mutated["scientific_source_response"]["source_registry_entry_id"] = (
            "src_" + "c" * 26
        )
        validate_decision(mutated)
        with self.assertRaisesRegex(ValueError, "exact independently reviewed D0"):
            self.compile(decision=mutated)

    def test_generic_validator_accepts_role_and_cutoff_mutations_bridge_rejects(self):
        role = deepcopy(self.decision)
        role["future_role_split"]["requested_future_role"] = "train_candidate"
        validate_decision(role)
        with self.assertRaisesRegex(ValueError, "exact independently reviewed D0"):
            self.compile(decision=role)

        horizon = deepcopy(self.decision)
        horizon["horizon_cutoff"].update({
            "claim_semantics": "prospective_point_in_time",
            "prediction_horizon_us": 1,
            "label_window_start_relation": "strictly_after_cutoff",
            "label_window_end_relation": "at_or_before_cutoff_plus_horizon",
        })
        validate_decision(horizon)
        with self.assertRaisesRegex(ValueError, "exact independently reviewed D0"):
            self.compile(decision=horizon)

    def test_provenance_packet_and_source_commitments_fail_closed(self):
        provenance = deepcopy(self.provenance)
        provenance["cycle_id"] += "-changed"
        with self.assertRaisesRegex(ValueError, "exact reviewed record"):
            self.compile(decision_provenance=provenance)

        packet = deepcopy(self.packet)
        packet["purpose"] += " changed"
        with self.assertRaisesRegex(ValueError, "frozen D0 packet"):
            self.compile(packet=packet)

        with self.assertRaisesRegex(ValueError, "controlled-source commitment"):
            self.compile(d0_source_sha256="0" * 64)

    def test_caller_cannot_add_locator_or_authority_inputs(self):
        decision = deepcopy(self.decision)
        decision["url"] = "https://attacker.invalid/"
        with self.assertRaises(ValueError):
            self.compile(decision=decision)
        with self.assertRaises(TypeError):
            bridge.compile_document_request_plan(
                self.decision,
                self.provenance,
                self.packet,
                d0_source_sha256=bridge.D0_CONTROLLED_SOURCE_SHA256,
                url="https://attacker.invalid/",
            )

    def test_registry_capability_and_envelope_mutations_fail_closed(self):
        registry = deepcopy(bridge.SOURCE_REGISTRY)
        for item in registry:
            if item["source_id"] == bridge.SCIENTIFIC_SOURCE_ID:
                item["url"] = "https://attacker.invalid/"
        with patch.object(bridge, "SOURCE_REGISTRY", registry):
            with self.assertRaises(ValueError):
                self.compile()

        capabilities = deepcopy(bridge.CAPABILITY_REGISTRY)
        capabilities[bridge.SCIENTIFIC_SOURCE_ID][bridge.OPERATION][
            "handler_id"
        ] = "attacker.fetch:v1"
        with patch.object(bridge, "CAPABILITY_REGISTRY", capabilities):
            with self.assertRaisesRegex(ValueError, "documentation capability"):
                self.compile()

        choices = deepcopy(bridge.SHORT_BOUNDED_CHOICES)
        for choice in choices:
            if choice["choice_id"] == bridge.LEGACY_ENVELOPE_CHOICE_ID:
                choice["derived_bounds"]["max_requests"] = 2
        with patch.object(bridge, "SHORT_BOUNDED_CHOICES", choices):
            with self.assertRaisesRegex(ValueError, "request envelope"):
                self.compile()

    def test_bridge_has_no_network_filesystem_process_or_provider_import(self):
        forbidden = {
            "pathlib", "urllib", "requests", "http", "socket", "subprocess",
            "os", "shutil", "tempfile", "paid_budget", "codex_glm_provider",
        }
        tree = ast.parse(inspect.getsource(bridge))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(forbidden.isdisjoint(imported), imported & forbidden)


if __name__ == "__main__":
    unittest.main()
