import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from glm_canary import HF_MODEL, cost
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import VALID_DECISION
from supervisor_harness.p0_gate1_controller_adapter import (
    MAX_OUTPUT_TOKENS, OFFLINE_FAKE_TOKEN_IDS, OfflineGate1ProviderFake,
    PROPOSE_TOOL, SUBMIT_TOOL,
    _available_capabilities, _submission_parameters,
    expected_packet, request_turn, run,
)
from supervisor_harness.prospective_source_scope_decision import SCHEMA as DECISION_SCHEMA


def decision():
    options = expected_packet()["prospective_source_scope_decision"]
    pair = options["source_response_options"][1]
    split = options["split_policy"]
    cutoff = options["cutoff_contract"]
    return {
        "scientific_source_response": {
            "source_registry_entry_id": pair["source_registry_entry_id"],
            "response_class_id": pair["response_class_id"],
        },
        "intended_uses": {
            "requested_use_ids": ["model_training", "private_research"],
        },
        "future_role_split": {
            "requested_future_role": "train_candidate",
            "split_policy_id": split["split_policy_id"],
            "split_policy_sha256": split["split_policy_sha256"],
            "exposure_ledger_id": "not_yet_created",
        },
        "horizon_cutoff": {
            "claim_semantics": "prospective_point_in_time",
            "prediction_horizon_us": 60_000_000,
            "cutoff_semantics_id": cutoff["cutoff_semantics_id"],
            "cutoff_contract_sha256": cutoff["cutoff_contract_sha256"],
            "label_window_start_relation": "strictly_after_cutoff",
            "label_window_end_relation": "at_or_before_cutoff_plus_horizon",
        },
        "bounded_investigation": {
            "mode": "first_party_document_review_only",
            "max_documents_proposed": 1,
            "max_provider_requests_proposed": 0,
            "max_raw_bytes_proposed": 0,
            "max_elapsed_seconds_proposed": 300,
        },
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


def submitted(value: dict, *, prefix: str = "private reasoning</think>\n",
              tool: str = SUBMIT_TOOL) -> str:
    arguments = []
    for key, item in value.items():
        encoded = item if isinstance(item, str) else json.dumps(
            item, separators=(",", ":"))
        arguments.append(
            f"<arg_key>{key}</arg_key><arg_value>{encoded}</arg_value>")
    return (prefix + f"<tool_call>{tool}" + "".join(arguments)
            + "</tool_call>")


def proposal():
    return {
        "proposal_id": "novel-source-001",
        "kind": "new_source",
        "hypothesis": "A new public archive may contain missing real fills.",
        "candidate_source": "An unregistered public archive",
        "method": "Check rights and one fixed public game sample.",
        "fixed_sample_rule": "First game by schedule identity, before outcomes.",
        "expected_evidence": "Raw fill and rights receipts or an exact failure.",
        "stop_rule": "Stop on rights uncertainty or after one sample.",
        "max_requests": 3,
        "max_bytes": 1000000,
        "max_minutes": 10,
        "max_provider_cost_usd": "0",
    }


class Gate1ControllerAdapterTests(unittest.TestCase):
    def test_output_cap_fits_frozen_packet_under_single_sample_gate(self):
        self.assertEqual(MAX_OUTPUT_TOKENS, 1600)
        self.assertLessEqual(cost(6000, MAX_OUTPUT_TOKENS),
                             Decimal("0.05"))

    def test_next_input_preserves_prior_choice_and_exact_available_handlers(self):
        packet = expected_packet()
        feedback = packet["prior_controller_feedback"]
        self.assertEqual(feedback["attempt_id"],
                         "market-rsi-gate1-controller-20260922-02")
        self.assertEqual(feedback["selected_source_id"],
                         "polymarket_official_trades")
        self.assertEqual(feedback["outcome"],
                         "invalid_submission_no_task_or_fetch")
        self.assertEqual(feedback["metered_cost_usd_not_invoice"],
                         "0.01790424")
        self.assertEqual(feedback["raw_response_sha256"],
                         "b34b169ba79b1ecebb55c127c350ef568a982c518f0c4454459bc1c357bcb4bb")
        from supervisor_harness.p0_gate1_controller_adapter import _submission_parameters
        parameters = _submission_parameters(packet)
        self.assertEqual(set(parameters["required"]), {
            "scientific_source_response", "intended_uses", "future_role_split",
            "horizon_cutoff", "bounded_investigation"})
        capabilities = _available_capabilities(packet)
        self.assertEqual(len(capabilities), 4)
        self.assertTrue(all(item["scope_only"] is True
                            and item["executable"] is False
                            for item in capabilities))
        turn = request_turn(packet)
        payload = json.loads(turn["messages"][1]["content"])
        self.assertEqual(payload["packet"]["prior_controller_feedback"],
                         feedback)
        self.assertEqual(payload["currently_available_source_response_options"],
                         capabilities)
        self.assertTrue(payload["complete_D0_required"])
        self.assertTrue(payload["all_external_authority_remains_false"])

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

    def test_one_first_response_records_complete_scope_only_decision(self):
        raw = submitted(decision())
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertTrue(result["valid_source_scope_decision"])
        self.assertFalse(result["provider_called"])
        self.assertEqual(backend.sample_calls, 1)
        recorded = json.loads((root / "decision.json").read_text())
        choice = json.loads((root / "submission.json").read_text())
        provenance = json.loads((root / "decision-provenance.json").read_text())
        self.assertEqual(recorded["schema"], DECISION_SCHEMA)
        self.assertEqual(recorded["decision_status"], "scope_only_non_executable")
        self.assertEqual(recorded["scientific_source_response"],
                         decision()["scientific_source_response"])
        self.assertTrue(all(value is False
                            for value in recorded["non_authority"].values()))
        self.assertEqual(choice, decision())
        self.assertEqual(provenance["cycle_id"], "gate1-controller-test-001")
        self.assertTrue(provenance["all_external_authority_false"])
        self.assertFalse((root / "task.json").exists())
        self.assertEqual((root / "raw-response.txt").read_text(), raw)
        request = json.loads((root / "request.json").read_text())
        self.assertEqual(request["reasoning_effort"], "low")
        self.assertEqual(len(request["tools"]), 1)
        self.assertEqual(request["tools"][0]["function"]["name"],
                         "mcp__controller_tools__submit_source_scope_decision")

    def test_legacy_novel_proposal_tool_is_rejected(self):
        raw = submitted(proposal(), tool=PROPOSE_TOOL)
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertEqual(backend.sample_calls, 1)
        self.assertIsNone(result["submission_kind"])
        self.assertFalse(result["valid_non_executable_proposal"])
        self.assertFalse(result["valid_source_scope_decision"])
        self.assertFalse((root / "task.json").exists())
        self.assertFalse((root / "proposal.json").exists())

    def test_novel_proposal_cannot_add_execution_authority(self):
        value = proposal()
        value["network_authorized"] = True
        result, root, _claims, backend = self.call(
            sampled(submitted(value, tool=PROPOSE_TOOL)))
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse(result["valid_non_executable_proposal"])
        self.assertFalse((root / "proposal.json").exists())

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
        result, root, _claims, backend = self.call(sampled(submitted(value)))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "task.json").exists())

    def test_unknown_choice_and_choice_source_mismatch_fail_closed(self):
        for change in ({"choice_id": "unknown_choice"},
                       {"source_id": "kalshi_official_historical_data"},
                       {"requested_operations": ["query_public_metadata"]},
                       {"max_bytes": 5000000},
                       {"investigation_id": "model-selected-id"}):
            with self.subTest(change=change):
                value = decision()
                value.update(change)
                result, root, _claims, backend = self.call(
                    sampled(submitted(value)))
                self.assertFalse(result["valid_plan_only_decision"])
                self.assertEqual(backend.sample_calls, 1)
                self.assertFalse((root / "task.json").exists())

    def test_packet_choice_mapping_mutation_fails_before_claim(self):
        changed = copy.deepcopy(expected_packet())
        changed["trusted_bounded_choices"][1]["source_id"] = (
            "kalshi_official_historical_data")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        claims = parent / "claims"
        claims.mkdir()
        backend = OfflineGate1ProviderFake(sampled(submitted(decision())))
        with self.assertRaisesRegex(ValueError, "exact frozen packet"):
            run(root=parent / "gate1-choice-mismatch", claim_root=claims,
                cycle_id="gate1-choice-mismatch", packet=changed,
                backend=backend)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(list(claims.iterdir()), [])

    def test_packet_integer_to_float_coercion_fails_before_claim(self):
        packet = copy.deepcopy(expected_packet())
        packet["known_aggregate_evidence"]["season_2024"][
            "trade_rows"] = 407225.0
        self.assertEqual(packet, expected_packet())
        self.assertIs(type(packet["known_aggregate_evidence"]["season_2024"]
                           ["trade_rows"]), float)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        claims = parent / "claims"
        claims.mkdir()
        backend = OfflineGate1ProviderFake(sampled(submitted(decision())))
        with self.assertRaisesRegex(ValueError, "exact frozen packet"):
            run(root=parent / "gate1-int-float-coercion", claim_root=claims,
                cycle_id="gate1-int-float-coercion", packet=packet,
                backend=backend)
        self.assertEqual(backend.encode_calls, 0)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(list(claims.iterdir()), [])

    def test_packet_boolean_to_integer_coercion_fails_before_claim(self):
        packet = copy.deepcopy(expected_packet())
        packet["hard_limits"]["purchase_allowed"] = 0
        self.assertEqual(packet, expected_packet())
        self.assertIs(type(packet["hard_limits"]["purchase_allowed"]), int)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        claims = parent / "claims"
        claims.mkdir()
        backend = OfflineGate1ProviderFake(sampled(submitted(decision())))
        with self.assertRaisesRegex(ValueError, "exact frozen packet"):
            run(root=parent / "gate1-bool-int-coercion", claim_root=claims,
                cycle_id="gate1-bool-int-coercion", packet=packet,
                backend=backend)
        self.assertEqual(backend.encode_calls, 0)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(list(claims.iterdir()), [])

    def test_offline_fake_token_ids_are_exact_and_constructor_drift_fails(self):
        response = sampled(submitted(decision()))
        backend = OfflineGate1ProviderFake(response)
        encoded = backend.encode(request_turn(expected_packet()))
        self.assertEqual(OFFLINE_FAKE_TOKEN_IDS, (101, 102, 103))
        self.assertEqual(encoded["token_ids"], list(OFFLINE_FAKE_TOKEN_IDS))
        self.assertIs(backend.token_ids, OFFLINE_FAKE_TOKEN_IDS)
        for changed in (
                (101, 102, 104), [101, 102, 103],
                (101.0, 102, 103), (True, 102, 103)):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "token IDs are frozen"):
                    OfflineGate1ProviderFake(response, token_ids=changed)

    def test_mutated_offline_preencoding_cannot_reach_a_valid_decision(self):
        for changed, sample_calls in (([101, 102, 104], 1),
                                      ([101.0, 102, 103], 0),
                                      ([True, 102, 103], 0)):
            with self.subTest(changed=changed):
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                parent = Path(temporary.name)
                claims = parent / "claims"
                claims.mkdir()
                backend = OfflineGate1ProviderFake(
                    sampled(submitted(decision())))
                encoded = backend.encode(request_turn(expected_packet()))
                encoded["token_ids"] = changed
                result = run(
                    root=parent / "gate1-mutated-token-encoding",
                    claim_root=claims,
                    cycle_id="gate1-mutated-token-encoding",
                    packet=expected_packet(), backend=backend,
                    preencoded=encoded,
                )
                self.assertFalse(result["valid_source_scope_decision"])
                self.assertEqual(result["failure_type"], "ValueError")
                self.assertEqual(backend.sample_calls, sample_calls)

    def test_legacy_verbose_submission_is_not_relabelled(self):
        legacy = decision()
        legacy.update({
            "investigation_id": "historical-01",
            "source_id": "polymarket_official_trades",
            "fixed_sample_rule": "Inspect the one frozen official documentation page.",
            "requested_operations": ["inspect_official_documentation"],
            "max_requests": 1, "max_bytes": 100000,
            "max_minutes": 10, "max_provider_cost_usd": "0",
        })
        result, root, _claims, backend = self.call(sampled(submitted(legacy)))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())

    def test_truncated_response_is_terminal_failure(self):
        result, root, _claims, backend = self.call(
            sampled("unfinished analysis without submission", finish_reason="length"))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertTrue((root / "raw-response.json").is_file())
        self.assertFalse((root / "provider-receipt.json").exists())

    def test_preencoded_request_calls_dispatch_gate_before_one_sample(self):
        response = sampled(submitted(decision()))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        claims = parent / "claims"
        claims.mkdir()
        backend = OfflineGate1ProviderFake(response)
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
        backend = OfflineGate1ProviderFake(sampled(submitted(decision())))
        with self.assertRaises(ValueError):
            run(root=parent / "gate1-controller-test-002", claim_root=claims,
                cycle_id="gate1-controller-test-002", packet=packet,
                backend=backend)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(list(claims.iterdir()), [])

    def test_permanent_claim_rejects_reuse(self):
        response = sampled(submitted(decision()))
        result, root, claims, _backend = self.call(response)
        self.assertTrue(result["valid_plan_only_decision"])
        root.rename(root.with_name(root.name + "-preserved"))
        with self.assertRaises(FileExistsError):
            run(root=root, claim_root=claims, cycle_id=root.name,
                packet=expected_packet(),
                backend=OfflineGate1ProviderFake(response))

    def test_multiple_terminal_submissions_fail_without_resampling(self):
        raw = submitted(decision(), prefix="") + submitted(decision(), prefix="")
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())
        self.assertFalse((root / "task.json").exists())

    def test_incomplete_submission_is_not_repaired(self):
        raw = ("</think><tool_call>submit_gate1_decision"
               "<arg_key>investigation_id</arg_key><arg_value>"
               "unfinished</arg_value>")
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())

    def test_valid_submission_followed_by_unfinished_second_call_fails(self):
        raw = (submitted(decision(), prefix="")
               + "<tool_call>submit_gate1_decision")
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())

    def test_valid_submission_followed_by_narrative_fails(self):
        raw = submitted(decision(), prefix="") + " extra answer"
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())

    def test_one_empty_glm_observation_terminator_is_accepted(self):
        raw = submitted(decision()) + "<|observation|>"
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertTrue(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertTrue((root / "decision.json").is_file())
        self.assertTrue((root / "decision-provenance.json").is_file())
        self.assertFalse((root / "task.json").exists())

    def test_observation_terminator_plus_narrative_fails(self):
        raw = submitted(decision()) + "<|observation|>extra answer"
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())

    def test_observation_terminator_does_not_excuse_extra_field(self):
        value = decision()
        value["rights_check_placeholder"] = ""
        raw = submitted(value) + "<|observation|>"
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())
        self.assertFalse((root / "task.json").exists())

    def test_tool_schema_excludes_model_authored_rights_policy(self):
        parameters = _submission_parameters(expected_packet())
        self.assertNotIn("rights_check", parameters["properties"])
        self.assertNotIn("rights_check", parameters["required"])
        self.assertNotIn("schema", parameters["properties"])
        self.assertNotIn("schema", parameters["required"])
        self.assertNotIn("source_id", parameters["properties"])
        self.assertNotIn("requested_operations", parameters["properties"])
        self.assertNotIn("max_bytes", parameters["properties"])
        self.assertNotIn("investigation_id", parameters["properties"])
        self.assertIn("trusted_rights_policy", expected_packet())

    def test_hidden_trade_operation_fails_at_adapter_boundary(self):
        value = copy.deepcopy(VALID_DECISION)
        value.pop("schema")
        self.assertNotIn("fetch_fixed_public_sample", [
            item["operation"] for item in expected_packet()["trusted_bounded_choices"]])
        result, root, _claims, backend = self.call(sampled(submitted(value)))
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertFalse((root / "decision.json").exists())
        self.assertFalse((root / "task.json").exists())

    def test_model_cannot_supply_trusted_schema(self):
        value = decision()
        value["schema"] = DECISION_SCHEMA
        result, root, _claims, backend = self.call(sampled(submitted(value)))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())
        self.assertFalse((root / "task.json").exists())

    def test_v016_duplicate_rights_shape_remains_fail_closed(self):
        duplicate = (
            "<arg_key>rights_check</arg_key><arg_value>first</arg_value>"
            "<arg_key>rights_check</arg_key><arg_value>second</arg_value>"
        )
        raw = submitted(decision()).replace("</tool_call>", duplicate + "</tool_call>")
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertFalse((root / "decision.json").exists())
        self.assertFalse((root / "task.json").exists())

    def test_captured_2048_token_analysis_only_failure_is_terminal(self):
        response = sampled(
            "analysis without a terminal submission",
            finish_reason="length",
        )
        response["output_tokens"] = list(range(2048))
        result, root, _claims, backend = self.call(response)
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertEqual(backend.sample_calls, 1)
        self.assertTrue((root / "raw-response.json").is_file())
        self.assertFalse((root / "provider-receipt.json").exists())
        self.assertFalse((root / "decision.json").exists())
        self.assertFalse((root / "task.json").exists())


if __name__ == "__main__":
    unittest.main()
