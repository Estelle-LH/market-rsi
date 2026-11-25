"""I2 synthetic handoff checks; human fixtures are not live LLM authorship."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

import earnings_capacity_adapter as adapter
import earnings_capacity_task as earnings_task
import test_capacity_feedback_engine as fixtures
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class DecisionTask(fixtures.LocalTask):
    """Reuse invented sum/state hooks and the production earnings I2 hooks."""
    decision = earnings_task.EarningsTask.decision
    candidate = earnings_task.EarningsTask.candidate


class DecisionAuthorInterfaceTests(unittest.TestCase):
    def fixture(self, axis="R"):
        # Composition avoids importing/inheriting discoverable fixture tests.
        fixture = fixtures.CommonEngineTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.task = DecisionTask(fixture, "sum")
        fixture.axes = [axis]
        fixture.envelope.update(mode="offline_replay", task_kind="sum", max_rounds=1,
                                initial_state=fixture.task.initial)
        fixture.bound = engine.save(fixture.root / "generic-envelope.json", fixture.envelope)
        return fixture

    @staticmethod
    def choice(prompt, axis="R", component=None):
        return {"schema": "earnings_capacity_decision_v1", "axis": axis,
                "component": component or {"R": "research_policy", "H": "tool_interface",
                                            "continue": "none"}[axis],
                "parent_pair_sha256": prompt["parent_pair_sha256"],
                "feedback_sha256": prompt["feedback_sha256"],
                "hypothesis": "Check the invented profile handoff",
                "expected_effect": "Exact field reaches the fixture Author"}

    @staticmethod
    def response(choice):
        text = json.dumps(choice)
        middle = len(text) // 2
        return {"status": "completed", "error": None, "output": [
            {"type": "message", "content": [
                {"type": "output_text", "text": text[:middle]},
                {"type": "output_text", "text": text[middle:]}]}]}

    @staticmethod
    def original(choice, source, field="research_instructions", expected="Verify signs with calculate"):
        return {"decision_sha256": digest(choice), "source_text": source,
                "test_text": "CASES = " + repr([{"field": field, "expected": expected}]) + "\n"}

    def invoke(self, fixture, *, controller=None, author=None):
        services = {"controller": controller or fixture.controller_role,
                    "author": author or fixture.author_role,
                    "review": fixture.review_role, "execute": fixture.execute_service}
        return engine.run(fixture.bound, fixture.native.restore(), fixture.task, services=services)

    def assert_closed(self, fixture, stage, *, author_calls, exception_type="ValueError"):
        loop = fixture.root / "episode/loop"
        failure = json.loads((loop / f"round-0001-{stage}.failed.json").read_text())
        self.assertEqual(failure["exception_type"], exception_type)
        self.assertFalse(failure["retry_allowed"])
        self.assertFalse((loop / f"round-0001-{stage}.done.json").exists())
        self.assertEqual(len(fixture.authored), author_calls)
        self.assertEqual(fixture.reviewed, [])
        self.assertEqual(fixture.task.calls, [])

    def test_completed_raw_controller_delivers_bound_decision_and_preserves_author_bytes(self):
        fixture = self.fixture()
        observed = {}

        def controller(prompt, slot):
            observed["prompt"] = deepcopy(prompt)
            observed["choice"] = self.choice(prompt)
            observed["response"] = self.response(observed["choice"])
            observed["controller"] = fixture.record(slot, observed["response"])
            return observed["controller"]

        def author(choice, before, slot):
            self.assertEqual(choice, observed["choice"])
            self.assertEqual(choice["parent_pair_sha256"], observed["prompt"]["parent_pair_sha256"])
            self.assertEqual(choice["feedback_sha256"], observed["prompt"]["feedback_sha256"])
            self.assertEqual(before, observed["prompt"]["profiles"]["R"])
            observed["author"] = fixture.author_role(choice, before, slot)
            observed["bytes"] = Path(observed["author"]["path"]).read_bytes()
            return observed["author"]

        outcome = self.invoke(fixture, controller=controller, author=author)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 1))
        self.assertEqual(engine.read(observed["controller"]), observed["response"])
        self.assertEqual(engine.read(engine.pin(fixture.root / "episode/decision-01.json")), observed["choice"])
        self.assertEqual(Path(observed["author"]["path"]).read_bytes(), observed["bytes"])
        authored = engine.read(observed["author"])
        child = engine.read(engine.pin(fixture.root / "episode/candidate-01.json"))
        self.assertEqual(child["author_sha256"], digest(authored))
        self.assertEqual(child["source_sha256"], hashlib.sha256(authored["source_text"].encode()).hexdigest())
        self.assertEqual(authored["source_text"], fixture.native.files["researcher_v2.py"])
        self.assertEqual(authored["test_text"], "CASES = [{'field': 'research_instructions', 'expected': 'Verify signs with calculate'}]\n")
        self.assertFalse(child["tests_executed"])
        self.assertEqual(child["profile"]["reuse_facts"], observed["prompt"]["profiles"]["R"]["reuse_facts"])
        self.assertFalse(outcome["result"]["claims"]["learning"])
        self.assertFalse(outcome["result"]["claims"]["live_RH_authorship"])

    def test_stale_controller_parent_or_feedback_refused_before_author(self):
        for field in ("parent_pair_sha256", "feedback_sha256"):
            with self.subTest(field=field):
                fixture = self.fixture()

                def controller(prompt, slot):
                    choice = self.choice(prompt)
                    choice[field] = "0" * 64
                    return fixture.record(slot, self.response(choice))

                with self.assertRaises(engine.driver.LoopHalted) as halted:
                    self.invoke(fixture, controller=controller)
                self.assertIn("bind current selected parent and feedback", str(halted.exception.__cause__))
                self.assert_closed(fixture, "controller", author_calls=0)
                original = engine.pin(Path(fixture.envelope["slots"][0]["controller"]) / "response.json")
                self.assertEqual(json.loads("".join(c["text"] for c in engine.read(original)["output"][0]["content"]))[field], "0" * 64)

    def test_malformed_or_noncompleted_controller_originals_refused_without_execution(self):
        for mutation in ("incomplete", "refusal", "tool", "invalid_json"):
            with self.subTest(mutation=mutation):
                fixture = self.fixture()

                def controller(prompt, slot):
                    response = self.response(self.choice(prompt))
                    if mutation == "incomplete":
                        response["status"] = "incomplete"
                    elif mutation == "refusal":
                        response["output"][0]["content"] = [{"type": "refusal", "refusal": "fixture refusal"}]
                    elif mutation == "tool":
                        response["output"].append({"type": "custom_tool_call", "name": "invented"})
                    else:
                        response["output"][0]["content"] = [{"type": "output_text", "text": "not JSON"}]
                    return fixture.record(slot, response)

                with self.assertRaises(engine.driver.LoopHalted):
                    self.invoke(fixture, controller=controller)
                self.assert_closed(fixture, "controller", author_calls=0,
                                   exception_type="JSONDecodeError" if mutation == "invalid_json" else "ValueError")
                self.assertTrue((Path(fixture.envelope["slots"][0]["controller"]) / "response.json").is_file())

    def test_author_original_must_bind_exact_controller_decision(self):
        fixture = self.fixture()

        def author(choice, before, slot):
            fixture.authored.append(choice)
            value = self.original(choice, fixture.native.files["researcher_v2.py"])
            value["decision_sha256"] = "0" * 64
            return fixture.record(slot, value)

        with self.assertRaises(engine.driver.LoopHalted) as halted:
            self.invoke(fixture, author=author)
        self.assertIn("Exact Author/source/test attribution", str(halted.exception.__cause__))
        self.assert_closed(fixture, "implement", author_calls=1)
        original = engine.pin(Path(fixture.envelope["slots"][0]["author"]) / "response.json")
        self.assertEqual(engine.read(original)["decision_sha256"], "0" * 64)
        with self.assertRaisesRegex(engine.driver.LoopHalted, "closed to retry"):
            self.invoke(fixture, author=author)
        self.assertEqual(len(fixture.authored), 1)

    def test_one_named_field_and_axis_are_required_for_author_child(self):
        before = {"axis": "H", "read_chunk_limit": 20000, "search_hit_limit": 50}
        prompt = {"parent_pair_sha256": "a" * 64, "feedback_sha256": "b" * 64}
        choice = self.choice(prompt, "H")
        valid = self.original(choice, "PROFILE = {'axis': 'H', 'read_chunk_limit': 1000, 'search_hit_limit': 50}\n",
                              "read_chunk_limit", 1000)
        child = adapter.author_candidate(valid, before, choice)
        self.assertEqual(child["profile"], {**before, "read_chunk_limit": 1000})
        for source in (
            "PROFILE = {'axis': 'H', 'read_chunk_limit': 1000, 'search_hit_limit': 40}",
            "PROFILE = {'axis': 'H', 'read_chunk_limit': 20000, 'search_hit_limit': 50}",
            "PROFILE = {'axis': 'R', 'research_instructions': 'Changed', 'reuse_facts': True}",
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                adapter.author_candidate({**valid, "source_text": source}, before, choice)
        wrong_component = {**choice, "component": "research_policy"}
        # Strict typed decision validation rejects an R component on an H
        # decision before Author profile-diff validation is reached.
        with self.assertRaisesRegex(ValueError, "Unsupported capacity component; preserve proposal, no execution"):
            adapter.author_candidate({**valid, "decision_sha256": digest(wrong_component)}, before, wrong_component)

    def test_nonliteral_author_source_or_tests_refused_before_execution(self):
        for field in ("source_text", "test_text"):
            with self.subTest(field=field):
                fixture = self.fixture()
                sentinel = fixture.root / "untrusted-code-ran"

                def author(choice, before, slot):
                    fixture.authored.append(choice)
                    value = self.original(choice, fixture.native.files["researcher_v2.py"])
                    assignment = "PROFILE" if field == "source_text" else "CASES"
                    value[field] = f"{assignment} = __import__('pathlib').Path({str(sentinel)!r}).write_text('ran')"
                    return fixture.record(slot, value)

                with self.assertRaises(engine.driver.LoopHalted):
                    self.invoke(fixture, author=author)
                self.assert_closed(fixture, "implement", author_calls=1)
                self.assertFalse(sentinel.exists())
                self.assertTrue((Path(fixture.envelope["slots"][0]["author"]) / "response.json").is_file())

    def test_continue_skips_author_and_preserves_selected_parent(self):
        fixture = self.fixture("continue")
        before = deepcopy(fixture.native.batch.snapshot()["micro_evolution"]["active_pair"])
        outcome = self.invoke(fixture)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 1))
        self.assertEqual(fixture.authored, [])
        self.assertEqual(fixture.reviewed, [])
        self.assertEqual(len(fixture.task.calls), 1)
        self.assertEqual(fixture.native.batch.snapshot()["micro_evolution"]["active_pair"], before)
        self.assertEqual(fixture.native.batch.snapshot()["micro_evolution"]["history"], [])
        implemented = engine.driver._read_pair(fixture.root / "episode/loop/round-0001-implement.done.json")["output"]
        self.assertEqual(implemented, {"candidate": None, "artifacts": []})
        self.assertFalse(Path(fixture.envelope["slots"][0]["author"]).exists())


if __name__ == "__main__":
    unittest.main()
