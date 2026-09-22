import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from glm_canary import HF_MODEL, cost
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import VALID_DECISION
from supervisor_harness.p0_gate1_controller_adapter import (
    MAX_OUTPUT_TOKENS, OfflineGate1ProviderFake, PROPOSE_TOOL, SUBMIT_TOOL,
    _available_capabilities, _submission_parameters,
    expected_packet, request_turn, run,
)
from supervisor_harness.p0_gate1_research_contract import DECISION_SCHEMA


def decision():
    return {
        "investigation_id": "gate1-controller-001",
        "question_id": "2025_whole_season_trade_access",
        "source_id": "polymarket_official_trades",
        "hypothesis": "The official interface documents historical market trade access.",
        "fixed_sample_rule": "Inspect the one frozen official documentation page.",
        "requested_operations": ["inspect_official_documentation"],
        "expected_evidence": "A bounded page hash and documented interface fields.",
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
        self.assertEqual(MAX_OUTPUT_TOKENS, 2944)
        self.assertLessEqual(cost(2819, MAX_OUTPUT_TOKENS),
                             Decimal("0.05"))

    def test_next_input_preserves_prior_choice_and_exact_available_handlers(self):
        packet = expected_packet()
        feedback = packet["prior_controller_feedback"]
        self.assertEqual(feedback["attempt_id"],
                         "market-rsi-gate1-controller-20260922-01")
        self.assertEqual(feedback["selected_source_id"],
                         "polymarket_official_trades")
        self.assertEqual(feedback["outcome"],
                         "invalid_submission_no_task_or_fetch")
        self.assertEqual(feedback["metered_cost_usd_not_invoice"],
                         "0.01666737")
        self.assertEqual(feedback["raw_response_sha256"],
                         "a6155faf4d19940415efac470e75f9c7823c9cafd5cc0f5883e45da9f3d7f27c")
        from supervisor_harness.p0_gate1_controller_adapter import _submission_parameters
        choices = _submission_parameters(packet)["properties"]["fixed_sample_rule"]["enum"]
        self.assertIn("Inspect the one frozen official documentation page.", choices)
        advertised = {
            rule
            for source in packet["current_execution_boundary"][
                "executable_documentation_choices"]
            for rule in source["fixed_sample_rule_options"]
        }
        self.assertEqual(set(choices), advertised)
        self.assertNotIn(
            "Inspect the single frozen official documentation page only: extra words.",
            choices,
        )
        capabilities = _available_capabilities(packet)
        self.assertTrue(capabilities)
        self.assertTrue(all(item["operation"] ==
                            "inspect_official_documentation"
                            for item in capabilities))
        trade_docs = [item for item in capabilities if item["source_id"] ==
                      "polymarket_official_trades"]
        self.assertEqual(trade_docs[0]["required_bounds"], {
            "max_requests": 1, "max_provider_cost_usd": "0"})
        turn = request_turn(packet)
        payload = json.loads(turn["messages"][1]["content"])
        self.assertEqual(payload["packet"]["prior_controller_feedback"],
                         feedback)
        self.assertEqual(payload["currently_available_bounded_capabilities"],
                         capabilities)
        self.assertTrue(payload["open_ended_proposals_enter_review_only"])

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
        raw = submitted(decision())
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertTrue(result["valid_plan_only_decision"])
        self.assertFalse(result["provider_called"])
        self.assertEqual(backend.sample_calls, 1)
        task = json.loads((root / "task.json").read_text())
        recorded = json.loads((root / "decision.json").read_text())
        self.assertEqual(recorded["schema"], DECISION_SCHEMA)
        self.assertTrue(task["execution_boundary"]["plan_only"])
        self.assertFalse(task["execution_boundary"]["network_fetch_authorized"])
        self.assertEqual((root / "raw-response.txt").read_text(), raw)
        request = json.loads((root / "request.json").read_text())
        self.assertEqual(request["reasoning_effort"], "low")
        self.assertEqual(len(request["tools"]), 2)
        self.assertEqual(request["tools"][0]["function"]["name"],
                         "mcp__controller_tools__submit_gate1_decision")
        self.assertEqual(request["tools"][1]["function"]["name"],
                         "mcp__controller_tools__propose_data_gap_resolution")

    def test_novel_proposal_is_terminal_but_cannot_execute(self):
        raw = submitted(proposal(), tool=PROPOSE_TOOL)
        result, root, _claims, backend = self.call(sampled(raw))
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(result["submission_kind"], "non_executable_proposal")
        self.assertTrue(result["valid_non_executable_proposal"])
        self.assertFalse(result["valid_plan_only_decision"])
        self.assertFalse((root / "task.json").exists())
        archived = json.loads((root / "proposal.json").read_text())
        self.assertEqual(archived["status"], "review_required")
        self.assertFalse(archived["network_authorized"])
        self.assertFalse(archived["formal_data_admitted"])

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
        self.assertTrue((root / "task.json").is_file())

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
        self.assertNotIn(
            "fetch_fixed_public_sample",
            parameters["properties"]["requested_operations"]["items"]["enum"])
        self.assertIn("trusted_rights_policy", expected_packet())

    def test_hidden_trade_operation_fails_at_adapter_boundary(self):
        value = copy.deepcopy(VALID_DECISION)
        value.pop("schema")
        self.assertNotIn(
            "fetch_fixed_public_sample",
            _submission_parameters(expected_packet())["properties"]
            ["requested_operations"]["items"]["enum"])
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
