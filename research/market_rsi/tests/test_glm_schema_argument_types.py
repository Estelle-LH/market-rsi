"""Regression for the Sep13 JSON-text capability loop; no provider or market data."""
import json
import unittest
from codex_glm_responses_adapter import AdapterProtocolError, parse_glm_completion, response_events
from data_scientist_harness.broker import TOOLS, ALLOWED_TOOLS, validate_shape
from data_scientist_harness.canary import call


SCHEMAS = {"mcp__controller_tools__" + t["name"]: t["inputSchema"] for t in TOOLS}


class SchemaArgumentTests(unittest.TestCase):
    def parse(self, name, args):
        return parse_glm_completion(call(name, args), ALLOWED_TOOLS, tool_schemas=SCHEMAS)

    def test_json_text_capability_roundtrips_without_activation_or_repair(self):
        args = {"name": "fixture", "problem": "Synthetic serialization check",
                "research_record": "0006", "evidence_refs": [{
                    "record_id": "0002", "json_pointer": "/result/read_level",
                    "observed_value_json": '"delivered_text_range_not_proof_of_understanding"',
                    "claim": "A bounded source range was delivered.",
                    "inference_limit": "This does not validate market data or understanding.",
                }], "proposed_interface": "Fixture-only typed operation",
                "verification_needed": '{"operation_kind":"fixture","max_input_bytes":13}',
                "unsupported_assumptions": ["No executable implementation is assumed."]}
        parsed = self.parse("request_capability", args)
        self.assertEqual(parsed["arguments"], args)
        validate_shape(parsed["arguments"], SCHEMAS[parsed["name"]])
        events = response_events(parsed, response_id="fixture", item_id="f", call_id="c", allowed_tools=ALLOWED_TOOLS)
        self.assertEqual(json.loads(events[-1]["response"]["output"][0]["arguments"]), args)

    def test_json_looking_strings_remain_strings_including_quotes(self):
        for value in ('23', 'true', 'null', '[]', '{}', '"quoted"', '0006', ''):
            with self.subTest(value=value):
                parsed = self.parse("submit_research_decision", {"action":"defer", "trial_id":"", "reason":value})
                self.assertEqual(parsed["arguments"]["reason"], value)
                self.assertIsInstance(parsed["arguments"]["reason"], str)

    def test_actual_object_array_and_integer_fields_are_still_decoded(self):
        args = {"finding_sha256":"a"*64, "responses":[{"id":"f001", "handling":"Keep", "next_evidence":"Test"}]}
        self.assertEqual(self.parse("acknowledge_current_findings", args)["arguments"], args)
        args = {"url":"https://example.org/", "offset":6000}
        self.assertEqual(self.parse("read_public_source", args)["arguments"], args)

    def test_schema_does_not_allow_tool_outside_request(self):
        with self.assertRaisesRegex(AdapterProtocolError, "absent"):
            parse_glm_completion(call("inspect_harness", {}), ALLOWED_TOOLS, tool_schemas={})

    def test_unknown_arguments_are_not_deleted_and_still_fail_validation(self):
        parsed = self.parse("inspect_harness", {"invented": "1"})
        with self.assertRaises(ValueError): validate_shape(parsed["arguments"], SCHEMAS[parsed["name"]])


if __name__ == "__main__": unittest.main()
