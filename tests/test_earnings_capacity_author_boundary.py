"""CP2 synthetic Author admission tests; no provider calls or model-code execution.

Exercise the production decoder and EarningsTask.candidate directly. Invented
Responses objects prove protocol behavior, not live authorship or improvement.
Externally current parent/feedback admission remains an engine responsibility.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import earnings_capacity_adapter as adapter
from earnings_capacity_task import EarningsTask
from market_rsi import digest


class AuthorBoundaryTests(unittest.TestCase):
    @staticmethod
    def choice(axis="R", component="research_policy"):
        return {"schema": "earnings_capacity_decision_v1", "axis": axis,
                "component": component, "parent_pair_sha256": "a" * 64,
                "feedback_sha256": "b" * 64, "hypothesis": "Synthetic admission check",
                "expected_effect": "Exactly one literal field reaches the candidate"}

    @staticmethod
    def before(axis="R"):
        return ({"axis": "R", "research_instructions": "parent", "reuse_facts": True}
                if axis == "R" else
                {"axis": "H", "read_chunk_limit": 20000, "search_hit_limit": 50})

    @staticmethod
    def payload(chosen, after, field):
        return {"decision_sha256": digest(chosen), "source_text": "PROFILE = " + repr(after) + "\n",
                "test_text": "CASES = " + repr([{"field": field, "expected": after[field]}]) + "\n"}

    @staticmethod
    def envelope(payload, *, split=False):
        text = json.dumps(payload, ensure_ascii=False)
        texts = [text[:len(text)//2], text[len(text)//2:]] if split else [text]
        return {"status": "completed", "error": None,
                "output": [{"type": "reasoning", "summary": []},
                           {"type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": part} for part in texts]}]}

    def valid(self, axis="R", field="research_instructions", value="child"):
        component = {"research_instructions": "research_policy", "reuse_facts": "memory_policy",
                     "read_chunk_limit": "tool_interface", "search_hit_limit": "tool_interface"}[field]
        chosen, before = self.choice(axis, component), self.before(axis)
        after = dict(before, **{field: value})
        return chosen, before, self.payload(chosen, after, field)

    def reject(self, original, before, chosen):
        snapshot = deepcopy(original)
        with self.assertRaises((ValueError, SyntaxError)):
            EarningsTask().candidate(original, before, chosen)
        self.assertEqual(original, snapshot)

    def test_all_four_single_field_children_pass_actual_task_without_execution(self):
        for axis, field, value in (("R", "research_instructions", "Check arithmetic"),
                                  ("R", "reuse_facts", False),
                                  ("H", "read_chunk_limit", 1000),
                                  ("H", "search_hit_limit", 20)):
            with self.subTest(axis=axis, field=field):
                chosen, before, payload = self.valid(axis, field, value)
                original = self.envelope(payload)
                snapshots = deepcopy((original, before, chosen))
                child = EarningsTask().candidate(original, before, chosen)
                self.assertEqual(child["profile"], dict(before, **{field: value}))
                self.assertEqual(child["cases"], [{"field": field, "expected": value}])
                self.assertFalse(child["tests_executed"])
                self.assertEqual((original, before, chosen), snapshots)

    def test_split_text_in_one_final_message_is_joined_in_order(self):
        chosen, before, payload = self.valid()
        original = self.envelope(payload, split=True)
        self.assertEqual(adapter.author_payload(original), payload)
        self.assertEqual(EarningsTask().candidate(original, before, chosen)["profile"]["research_instructions"], "child")

    def test_optional_message_role_status_and_top_level_error_remain_compatible(self):
        chosen, before, payload = self.valid()
        original = self.envelope(payload)
        del original["error"]
        del original["output"][1]["role"]
        del original["output"][1]["status"]
        self.assertEqual(adapter.author_payload(original), payload)
        self.assertFalse(EarningsTask().candidate(original, before, chosen)["tests_executed"])

    def test_exact_legacy_business_payload_is_preserved_for_offline_compatibility(self):
        chosen, before, payload = self.valid()
        snapshot = deepcopy(payload)
        self.assertEqual(adapter.author_payload(payload), snapshot)
        child = EarningsTask().candidate(payload, before, chosen)
        self.assertEqual(child["author_sha256"], digest(snapshot))
        self.assertEqual(payload, snapshot)

    def test_business_source_and_original_have_distinct_exact_attribution(self):
        chosen, before, payload = self.valid()
        payload["source_text"] = "PROFILE  =  " + repr(dict(before, research_instructions="child")) + "\n\n"
        original = self.envelope(payload)
        child = EarningsTask().candidate(original, before, chosen)
        self.assertEqual(child["author_sha256"], digest(payload))
        self.assertNotEqual(child["author_sha256"], digest(original))
        self.assertEqual(child["source_sha256"], hashlib.sha256(payload["source_text"].encode("utf-8")).hexdigest())
        self.assertNotEqual(child["source_sha256"], digest(child["profile"]))
        self.assertEqual(adapter.author_payload(original)["source_text"], payload["source_text"])

    def test_noncompleted_or_error_envelopes_are_refused(self):
        chosen, before, payload = self.valid()
        for status in (None, "incomplete", "failed", "queued", "in_progress", True):
            with self.subTest(status=status):
                original = self.envelope(payload); original["status"] = status
                self.reject(original, before, chosen)
        for error in ({}, False, "provider error", {"code": "bad"}):
            with self.subTest(error=error):
                original = self.envelope(payload); original["error"] = error
                self.reject(original, before, chosen)

    def test_missing_or_malformed_envelope_shape_is_refused(self):
        chosen, before, payload = self.valid()
        original = self.envelope(payload)
        for value in (None, [], "not an envelope", 1, {}, {"status": "completed"},
                      dict(original, output=None), dict(original, output={}),
                      dict(original, output=[]), dict(original, output=[None]),
                      dict(original, output=["message"]), dict(original, output=[{}])):
            with self.subTest(value=value):
                self.reject(value, before, chosen)

    def test_tools_and_unknown_output_items_are_never_author_text(self):
        chosen, before, payload = self.valid()
        for item_type in ("function_call", "custom_tool_call", "web_search_call", "file_search_call",
                          "computer_call", "code_interpreter_call", "tool_call", "refusal", "unknown"):
            with self.subTest(item_type=item_type):
                original = self.envelope(payload)
                original["output"].insert(0, {"type": item_type, "name": "synthetic"})
                self.reject(original, before, chosen)

    def test_exactly_one_assistant_completed_final_message_is_required(self):
        chosen, before, payload = self.valid()
        original = self.envelope(payload)
        for output in ([original["output"][0]],
                       [original["output"][1], deepcopy(original["output"][1])]):
            with self.subTest(output=output):
                self.reject(dict(original, output=output), before, chosen)
        for field, values in (("role", ("user", "tool", None)),
                              ("status", ("incomplete", "in_progress", None))):
            for value in values:
                with self.subTest(field=field, value=value):
                    bad = deepcopy(original); bad["output"][1][field] = value
                    self.reject(bad, before, chosen)

    def test_content_requires_nonempty_output_text_fragments_only(self):
        chosen, before, payload = self.valid()
        valid_text = self.envelope(payload)["output"][1]["content"][0]
        for content in (None, {}, [], [None], ["text"], [{}], [{"type": "output_text"}],
                        [{"type": "output_text", "text": None}],
                        [{"type": "output_text", "text": 1}],
                        [{"type": "output_text", "text": ""}],
                        [{"type": "refusal", "refusal": "no"}],
                        [valid_text, {"type": "refusal", "refusal": "no"}]):
            with self.subTest(content=content):
                original = self.envelope(payload); original["output"][1]["content"] = content
                self.reject(original, before, chosen)

    def test_malformed_trailing_or_nonobject_business_json_is_refused(self):
        chosen, before, payload = self.valid()
        for text in ("not JSON", "", "[]", "null", "true", "1", "{", json.dumps(payload) + " {}"):
            with self.subTest(text=text):
                original = self.envelope(payload)
                original["output"][1]["content"] = [{"type": "output_text", "text": text}]
                self.reject(original, before, chosen)

    def test_duplicate_business_json_keys_are_refused_even_when_values_match(self):
        chosen, before, payload = self.valid()
        encoded = json.dumps(payload)
        for key in payload:
            with self.subTest(key=key):
                duplicate = "{" + json.dumps(key) + ":" + json.dumps(payload[key]) + "," + encoded[1:]
                original = self.envelope(payload)
                original["output"][1]["content"] = [{"type": "output_text", "text": duplicate}]
                self.reject(original, before, chosen)

    def test_business_keys_types_and_decision_digest_are_exact(self):
        chosen, before, payload = self.valid()
        variants = [dict(payload, extra="no"), {k: v for k, v in payload.items() if k != "test_text"},
                    dict(payload, decision_sha256="c" * 64), dict(payload, decision_sha256=True)]
        for field in ("source_text", "test_text"):
            variants.extend(dict(payload, **{field: v}) for v in (None, [], {}, 1, True))
        for bad in variants:
            with self.subTest(payload=bad):
                self.reject(self.envelope(bad), before, chosen)
                self.reject(bad, before, chosen)

    def test_continue_cannot_author_a_child(self):
        chosen = self.choice("continue", "none")
        before = self.before()
        payload = self.payload(chosen, dict(before, research_instructions="child"), "research_instructions")
        self.reject(self.envelope(payload), before, chosen)

    def test_invalid_chosen_decisions_are_refused_despite_matching_payload_digest(self):
        chosen, before, _ = self.valid()
        variants = [dict(chosen, schema="wrong"), dict(chosen, extra="scope"),
                    {k: v for k, v in chosen.items() if k != "expected_effect"},
                    dict(chosen, component="memory_policy"), dict(chosen, component="network"),
                    dict(chosen, axis="K"), dict(chosen, parent_pair_sha256="invalid"),
                    dict(chosen, feedback_sha256="invalid"), dict(chosen, hypothesis=""),
                    dict(chosen, expected_effect=3), dict(chosen, expected_effect="x" * 1001)]
        for bad in variants:
            with self.subTest(chosen=bad):
                payload = self.payload(bad, dict(before, research_instructions="child"), "research_instructions")
                self.reject(self.envelope(payload), before, bad)

    def test_nondict_chosen_or_before_profile_is_a_typed_admission_failure(self):
        chosen, before, payload = self.valid()
        for bad in (None, [], "not a decision", 3):
            with self.subTest(chosen=bad):
                changed = dict(payload, decision_sha256=digest(bad))
                self.reject(self.envelope(changed), before, bad)
        for bad in (None, [], "not a profile", 3):
            with self.subTest(before=bad):
                self.reject(self.envelope(payload), bad, chosen)

    def test_before_profile_axis_fields_types_and_bounds_are_validated(self):
        chosen, before, payload = self.valid()
        bad_profiles = [dict(before, axis="H"), dict(before, network=True),
                        {k: v for k, v in before.items() if k != "reuse_facts"},
                        dict(before, reuse_facts=1), dict(before, research_instructions="x" * 2201),
                        dict(before, research_instructions="é" * 2048 + "a")]
        for bad in bad_profiles:
            with self.subTest(before=bad):
                self.reject(self.envelope(payload), bad, chosen)
        chosen, before, payload = self.valid("H", "search_hit_limit", 10)
        for value in (True, 255, 20001):
            with self.subTest(value=value):
                self.reject(self.envelope(payload), dict(before, read_chunk_limit=value), chosen)

    def test_no_change_or_two_fields_changed_is_refused(self):
        chosen, before, payload = self.valid()
        for after in (before, dict(before, research_instructions="child", reuse_facts=False)):
            with self.subTest(after=after):
                bad = dict(payload, source_text="PROFILE = " + repr(after))
                self.reject(self.envelope(bad), before, chosen)

    def test_source_axis_or_named_component_mismatch_is_refused(self):
        chosen, before, payload = self.valid()
        bad = dict(payload, source_text="PROFILE = " + repr(self.before("H")))
        self.reject(self.envelope(bad), before, chosen)
        choice = self.choice("R", "memory_policy")
        self.reject(self.envelope(dict(payload, decision_sha256=digest(choice))), before, choice)

    def test_H_inclusive_limits_pass_when_exactly_one_field_changes(self):
        for field, value in (("read_chunk_limit", 256), ("read_chunk_limit", 20000),
                             ("search_hit_limit", 1), ("search_hit_limit", 50)):
            with self.subTest(field=field, value=value):
                chosen, before, _ = self.valid("H", field, value)
                before[field] = 1000 if field == "read_chunk_limit" else 10
                payload = self.payload(chosen, dict(before, **{field: value}), field)
                self.assertEqual(EarningsTask().candidate(self.envelope(payload), before, chosen)["profile"][field], value)

    def test_H_out_of_bounds_and_bool_as_int_are_refused(self):
        for field, values in (("read_chunk_limit", (0, 255, 20001, True, 1000.0, "1000")),
                              ("search_hit_limit", (0, 51, False, 10.0, "10"))):
            for value in values:
                with self.subTest(field=field, value=value):
                    chosen, before, payload = self.valid("H", field, value)
                    self.reject(self.envelope(payload), before, chosen)

    def test_R_inclusive_char_and_UTF8_limits_pass(self):
        for text in ("", "x" * 2200, "é" * 2048, "😀" * 1024):
            with self.subTest(chars=len(text), bytes=len(text.encode("utf-8"))):
                chosen, before, payload = self.valid(value=text)
                self.assertEqual(EarningsTask().candidate(self.envelope(payload), before, chosen)["profile"]["research_instructions"], text)

    def test_R_char_or_UTF8_overflow_and_field_types_are_refused(self):
        for value in ("x" * 2201, "é" * 2048 + "a", None, [], True):
            with self.subTest(value_type=type(value).__name__):
                chosen, before, payload = self.valid(value=value)
                self.reject(self.envelope(payload), before, chosen)
        chosen, before, payload = self.valid("R", "reuse_facts", 0)
        self.reject(self.envelope(payload), before, chosen)

    def test_exact_8192_source_and_test_UTF8_bytes_pass_but_8193_fail(self):
        chosen, before, payload = self.valid()
        for field in ("source_text", "test_text"):
            with self.subTest(field=field):
                base = payload[field] + "#"
                text = base + "x" * (8192 - len(base.encode("utf-8")))
                self.assertEqual(len(text.encode("utf-8")), 8192)
                accepted = dict(payload, **{field: text})
                self.assertFalse(EarningsTask().candidate(self.envelope(accepted), before, chosen)["tests_executed"])
                self.reject(self.envelope(dict(payload, **{field: text + "x"})), before, chosen)

    def test_profile_extra_authority_fields_or_missing_fields_are_refused(self):
        chosen, before, payload = self.valid()
        after = dict(before, research_instructions="child")
        variants = [dict(after, **{field: True}) for field in ("tools", "network", "budget", "permissions")]
        variants.append({k: v for k, v in after.items() if k != "reuse_facts"})
        for value in variants:
            with self.subTest(profile=value):
                self.reject(self.envelope(dict(payload, source_text="PROFILE = " + repr(value))), before, chosen)

    def test_duplicate_PROFILE_literal_keys_are_refused_before_collapse(self):
        chosen, before, payload = self.valid()
        for source in (
            "PROFILE = {'axis':'R','axis':'R','research_instructions':'child','reuse_facts':True}",
            "PROFILE = {'axis':'R','research_instructions':'child','research_instructions':'child','reuse_facts':True}",
            "PROFILE = {'axis':'R','research_instructions':'parent','research_instructions':'child','reuse_facts':True}",
            "PROFILE = {'axis':'R','research_instructions':'child','reuse_facts':True,'reuse_facts':True}",
        ):
            with self.subTest(source=source):
                self.reject(self.envelope(dict(payload, source_text=source)), before, chosen)

    def test_duplicate_CASES_literal_keys_are_refused_before_collapse(self):
        chosen, before, payload = self.valid()
        for tests in (
            "CASES = [{'field':'research_instructions','field':'research_instructions','expected':'child'}]",
            "CASES = [{'field':'reuse_facts','field':'research_instructions','expected':'child'}]",
            "CASES = [{'field':'research_instructions','expected':'child','expected':'child'}]",
            "CASES = [{'field':'research_instructions','expected':'wrong','expected':'child'}]",
        ):
            with self.subTest(tests=tests):
                self.reject(self.envelope(dict(payload, test_text=tests)), before, chosen)

    def test_CASES_inclusive_count_limits_pass_without_running_tests(self):
        chosen, before, payload = self.valid()
        for count in (1, 8):
            with self.subTest(count=count):
                cases = [{"field": "research_instructions", "expected": "child"}] * count
                child = EarningsTask().candidate(self.envelope(dict(payload, test_text="CASES = " + repr(cases))), before, chosen)
                self.assertEqual(child["cases"], cases)
                self.assertFalse(child["tests_executed"])

    def test_CASES_empty_overflow_shape_field_value_or_type_is_refused(self):
        chosen, before, payload = self.valid()
        valid_case = {"field": "research_instructions", "expected": "child"}
        variants = [[], [valid_case] * 9, valid_case, [None], [{"field": "reuse_facts", "expected": True}],
                    [dict(valid_case, expected="wrong")], [dict(valid_case, expected=True)],
                    [dict(valid_case, extra=1)], [{"field": "research_instructions"}]]
        for cases in variants:
            with self.subTest(cases=cases):
                self.reject(self.envelope(dict(payload, test_text="CASES = " + repr(cases))), before, chosen)
        chosen, before, payload = self.valid("H", "read_chunk_limit", 1000)
        for expected in (True, 1000.0, "1000"):
            self.reject(self.envelope(dict(payload, test_text="CASES = " + repr([{"field": "read_chunk_limit", "expected": expected}]))), before, chosen)
        chosen, before, payload = self.valid("R", "reuse_facts", False)
        self.reject(self.envelope(dict(payload, test_text="CASES = [{'field':'reuse_facts','expected':0}]")), before, chosen)

    def test_only_one_plain_assignment_is_admitted_for_source_and_CASES(self):
        chosen, before, payload = self.valid()
        for field, name in (("source_text", "PROFILE"), ("test_text", "CASES")):
            for text in ("import os\n" + payload[field], payload[field] + "\npass",
                         "OTHER = " + payload[field].split("=", 1)[1],
                         name + " = OTHER = " + payload[field].split("=", 1)[1],
                         name + ": dict = " + payload[field].split("=", 1)[1],
                         name + " += {}"):
                with self.subTest(field=field, text=text):
                    self.reject(self.envelope(dict(payload, **{field: text})), before, chosen)

    def test_calls_comprehensions_lambda_eval_and_attribute_code_never_execute(self):
        chosen, before, payload = self.valid()
        with tempfile.TemporaryDirectory() as temp:
            sentinel = Path(temp) / "must-not-be-created"
            expressions = ("__import__('pathlib').Path(" + repr(str(sentinel)) + ").write_text('ran')",
                           "dict(axis='R', research_instructions='child', reuse_facts=True)",
                           "{key: value for key, value in []}", "(lambda: {})()",
                           "eval('{}')", "exec('pass')", "({}).__class__")
            for field, name in (("source_text", "PROFILE"), ("test_text", "CASES")):
                for expression in expressions:
                    with self.subTest(field=field, expression=expression):
                        self.reject(self.envelope(dict(payload, **{field: name + " = " + expression})), before, chosen)
                        self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
