"""Host literal-source handoff into Native pending admission, never adoption.

Compose the existing owned Native fixture without collecting its test methods.
Responses-shaped Author fixtures are simulated; no provider call or model code
is executed. Static review is source/scope evidence, not a benefit review.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_capacity_adapter as adapter
import earnings_source_review as source_review
import test_earnings_capacity_adapter as capacity_fixture
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class SourceReviewTests(unittest.TestCase):
    def setUp(self):
        self._new_fixture()

    def _new_fixture(self):
        self.native = capacity_fixture.EarningsCapacityTests()
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        self.root = self.native.root
        # Preserve the old fixture's prospective child bytes as inputs only.
        for name in ("researcher_v2.py", "harness_v2.py"):
            (self.root / name).rename(self.root / ("input-" + name))
        self.slot = self.root / "role-area" / "review-01"
        self.slots = {str(self.slot): {"candidate_id": "cp7c-child-01",
            "R": "researcher_v2.py", "H": "harness_v2.py"}}
        self.service = source_review.SourceReview(self.root, slots=self.slots,
            proposer_id="fixture-author", reviewer_id="independent-auditor")
        self.serial = 0

    @staticmethod
    def _envelope(payload):
        return {"status": "completed", "output": [{"type": "message",
            "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": json.dumps(payload)}]}]}

    def _save(self, value, label):
        self.serial += 1
        return engine.save(self.root / (label + "-" + str(self.serial) + ".json"), value)

    def _inputs(self, axis="R", *, source=None):
        snapshot = self.native.batch.snapshot()
        pair = digest(snapshot["micro_evolution"]["active_pair"])
        chosen = adapter.decision({"schema": "earnings_capacity_decision_v1",
            "axis": axis, "component": "research_policy" if axis == "R" else "tool_interface",
            "parent_pair_sha256": pair, "feedback_sha256": "b" * 64,
            "hypothesis": "A literal one-field child addresses the fixture gap",
            "expected_effect": "The named field reaches a later bounded worker"},
            parent_pair_sha256=pair, feedback_sha256="b" * 64)
        name = self.slots[str(self.slot)][axis]
        source = self.native.files[name] if source is None else source
        new = adapter.profile(source.encode(), axis)
        field = "research_instructions" if axis == "R" else "read_chunk_limit"
        payload = {"decision_sha256": digest(chosen), "source_text": source,
            "test_text": "CASES = " + repr([{"field": field, "expected": new[field]}]) + "\n"}
        original = self._envelope(payload)
        old = adapter.profile((self.root / self.native.entry[axis]).read_bytes(), axis)
        candidate = adapter.author_candidate(original, old, chosen)
        descriptor = {"schema": "capacity_review_context_v1", "decision_sha256": digest(chosen),
            "author_original": self._save(original, "author-original"),
            "candidate": self._save(candidate, "decoded-candidate"),
            "parent_pair_sha256": pair, "parent_identity": deepcopy(self.native.before),
            "parent_entrypoints": deepcopy(self.native.entry),
            "state_sha256": snapshot["state_sha256"],
            "micro_evolution": deepcopy(snapshot["micro_evolution"])}
        return chosen, original, descriptor

    def _rebind_payload(self, inputs, updates, *, chosen_updates=None):
        chosen, original, descriptor = deepcopy(inputs)
        if chosen_updates:
            chosen.update(chosen_updates)
        payload = adapter.author_payload(original)
        payload.update(updates)
        payload["decision_sha256"] = digest(chosen)
        original = self._envelope(payload)
        descriptor["author_original"] = self._save(original, "changed-original")
        descriptor["decision_sha256"] = digest(chosen)
        return chosen, original, descriptor

    def _tree(self):
        result = {}
        for path in sorted(self.root.rglob("*")):
            name = str(path.relative_to(self.root))
            if path.is_symlink():
                result[name] = ("symlink", str(path.readlink()))
            elif path.is_dir():
                result[name] = ("directory",)
            else:
                result[name] = ("bytes", path.read_bytes())
        return result

    def _refused(self, inputs, *, slot=None, service=None):
        state = deepcopy(self.native.batch.snapshot())
        tree = self._tree()
        with self.assertRaises(ValueError):
            (service or self.service).review(*inputs, str(self.slot if slot is None else slot))
        self.assertEqual(self.native.batch.snapshot(), state)
        self.assertEqual(self._tree(), tree)

    def _pending_handoff(self, inputs):
        chosen, original, descriptor = inputs
        state = deepcopy(self.native.batch.snapshot())
        original_bytes = Path(descriptor["author_original"]["path"]).read_bytes()
        spec = self.service.review(chosen, original, descriptor, str(self.slot))
        self.assertEqual(set(spec), {"schema", "after", "proposal", "entrypoints",
            "static_review", "review_receipt", "original", "artifacts"})
        self.assertIsNone(spec["review_receipt"])
        self.assertEqual(engine.read(spec["original"]),
            {key: value for key, value in spec.items() if key not in {"original", "artifacts"}})
        self.assertEqual(Path(descriptor["author_original"]["path"]).read_bytes(), original_bytes)
        name = spec["entrypoints"][chosen["axis"]]
        self.assertEqual((self.root / name).read_bytes(),
            adapter.author_payload(original)["source_text"].encode())
        static = engine.read(spec["static_review"])
        self.assertEqual(static["identity_sha256"], digest(spec["after"]))
        self.assertEqual(static["reviewer_id"], "independent-auditor")
        self.assertEqual(static["proposer_id"], "fixture-author")
        self.assertIn("CASES not executed", static["scope"])
        self.assertEqual(self.native.batch.snapshot(), state)
        tree = self._tree()
        preview = self.native.adapter.preview_proposal(spec["after"], spec["proposal"],
            spec["entrypoints"], static_review=spec["static_review"],
            expected_state_sha256=state["state_sha256"])
        self.assertEqual(self.native.batch.snapshot(), state)
        self.assertEqual(self._tree(), tree)
        self.assertEqual(preview["projected_pending"]["candidate_id"], "cp7c-child-01")
        self.native.adapter.propose(spec["after"], spec["proposal"], spec["entrypoints"],
            static_review=spec["static_review"], expected_state_sha256=state["state_sha256"])
        after = self.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(after["active_pair"], state["micro_evolution"]["active_pair"])
        self.assertEqual(after["history"], state["micro_evolution"]["history"])
        self.assertEqual(after["pending"]["candidate_id"], "cp7c-child-01")
        self.assertEqual(after["pending"]["pair"], spec["proposal"]["pair"])
        json.dumps(spec, allow_nan=False)
        return spec

    def test_R_original_bytes_reach_real_native_pending_only(self):
        spec = self._pending_handoff(self._inputs())
        self.assertEqual(spec["entrypoints"], {"R": "researcher_v2.py", "H": "harness_v1.py"})
        self.assertEqual(spec["proposal"]["component"], "research_policy")

    def test_H_original_bytes_reach_real_native_pending_only(self):
        spec = self._pending_handoff(self._inputs("H"))
        self.assertEqual(spec["entrypoints"], {"R": "researcher_v1.py", "H": "harness_v2.py"})
        self.assertEqual(adapter.profile((self.root / "harness_v2.py").read_bytes(), "H")
                         ["read_chunk_limit"], 1000)

    def test_code_shaped_policy_and_CASES_stay_literal_data(self):
        marker = self.root / "must-not-exist"
        policy = "__import__('pathlib').Path(" + repr(str(marker)) + ").write_text('executed')"
        source = "PROFILE = " + repr({"axis": "R", "research_instructions": policy,
            "reuse_facts": True}) + "\n"
        inputs = self._inputs(source=source)
        self.assertFalse(engine.read(inputs[2]["candidate"])["tests_executed"])
        with patch.object(engine.activation.importlib.util, "spec_from_file_location",
                          side_effect=AssertionError("Generated module import forbidden")):
            self._pending_handoff(inputs)
        self.assertFalse(marker.exists())

    def test_bad_original_candidate_or_decision_binding_is_zero_write(self):
        inputs = self._inputs()
        cases = []
        bad = deepcopy(inputs); bad[1]["status"] = "incomplete"; cases.append(("incomplete", bad))
        bad = deepcopy(inputs); bad[2]["author_original"]["sha256"] = "c" * 64
        cases.append(("original-hash", bad))
        bad = deepcopy(inputs); bad[2]["candidate"] = self._save({"invented": True}, "bad-candidate")
        cases.append(("candidate", bad))
        bad = deepcopy(inputs); bad[2]["decision_sha256"] = "c" * 64
        cases.append(("decision", bad))
        for name, bad in cases:
            with self.subTest(name=name):
                self._refused(bad)

    def test_bad_diff_component_or_CASES_is_zero_write(self):
        inputs = self._inputs()
        cases = [
            ("two-fields", self._rebind_payload(inputs, {"source_text":
                "PROFILE = {'axis':'R','research_instructions':'Check','reuse_facts':False}\n"})),
            ("wrong-component", self._rebind_payload(inputs, {},
                chosen_updates={"component": "memory_policy"})),
            ("empty-cases", self._rebind_payload(inputs, {"test_text": "CASES = []\n"})),
            ("call-cases", self._rebind_payload(inputs,
                {"test_text": "CASES = __import__('os').system('false')\n"})),
        ]
        for name, bad in cases:
            with self.subTest(name=name):
                self._refused(bad)

    def test_actor_scope_consumed_ID_and_pending_are_zero_write(self):
        inputs = self._inputs()
        for name, field, value in (
            ("actor", "reviewer_id", "fixture-author"),
            ("scope", "allowed_write_paths", {"researcher": ["researcher_v1.py"],
                                               "harness": ["harness_v1.py", "harness_v2.py"]}),
            ("used-ID", "used_candidate_ids", ["cp7c-child-01"]),
            ("pending", "pending", {"candidate_id": "some-prior-child"}),
        ):
            bad = deepcopy(inputs); bad[2]["micro_evolution"][field] = value
            with self.subTest(name=name):
                self._refused(bad)

    def test_constructor_namespaces_and_undeclared_slot_are_zero_write(self):
        inputs = self._inputs()
        bad_maps = []
        bad = deepcopy(self.slots); bad[str(self.slot)]["R"] = "../escape.py"; bad_maps.append(bad)
        bad = deepcopy(self.slots); bad[str(self.slot)]["H"] = "not-python.txt"; bad_maps.append(bad)
        bad = deepcopy(self.slots); bad[str(self.slot)]["H"] = "researcher_v2.py"; bad_maps.append(bad)
        bad = deepcopy(self.slots); bad[str(self.slot)]["extra"] = True; bad_maps.append(bad)
        bad = deepcopy(self.slots); bad["relative-review"] = bad.pop(str(self.slot)); bad_maps.append(bad)
        bad = deepcopy(self.slots); bad[str(self.root / "review-02")] = {
            "candidate_id": "cp7c-child-01", "R": "researcher_v3.py", "H": "harness_v3.py"}
        bad_maps.append(bad)
        tree = self._tree()
        for index, slots in enumerate(bad_maps):
            with self.subTest(index=index), self.assertRaises(ValueError):
                source_review.SourceReview(self.root, slots=slots,
                    proposer_id="fixture-author", reviewer_id="independent-auditor")
        with self.assertRaises(ValueError):
            source_review.SourceReview(self.root, slots=self.slots,
                proposer_id="same-actor", reviewer_id="same-actor")
        self.assertEqual(self._tree(), tree)
        self._refused(inputs, slot=self.root / "undeclared-review")

    def test_late_source_and_role_ancestor_aliases_are_zero_write(self):
        inputs = self._inputs()
        target = self.root / "researcher_v2.py"
        target.symlink_to(self.root / "absent-source.py")
        self.assertFalse(target.exists())
        self._refused(inputs)
        target.rename(self.root / "retained-source-alias")
        foreign = self.root / "foreign-artifacts"; foreign.mkdir()
        self.slot.parent.symlink_to(foreign, target_is_directory=True)
        self.assertFalse(self.slot.exists())
        self._refused(inputs)
        self.assertEqual(list(foreign.iterdir()), [])
        self.assertFalse(target.exists())

    def test_exact_identity_and_micro_active_parent_required_before_write(self):
        inputs = self._inputs()
        bad = self._rebind_payload(inputs, {}, chosen_updates={"parent_pair_sha256": "c" * 64})
        bad[2]["parent_pair_sha256"] = "c" * 64
        self._refused(bad)
        bad = deepcopy(inputs)
        bad[2]["micro_evolution"]["active_pair"]["researcher_sha256"] = "c" * 64
        self._refused(bad)

    def test_existing_source_slot_and_completed_reentry_are_preserved(self):
        inputs = self._inputs()
        target = self.root / "researcher_v2.py"
        target.write_bytes(b"preserved existing source\n")
        self._refused(inputs)
        # Each consumed case has a distinct fixture/ID namespace, never reopen.
        self._new_fixture()
        inputs = self._inputs()
        self.slot.mkdir(parents=True)
        (self.slot / "retained-attempt.txt").write_bytes(b"closed attempt\n")
        self._refused(inputs)
        self._new_fixture()
        inputs = self._inputs()
        self.service.review(*inputs, str(self.slot))
        self._refused(inputs)

    def test_partial_source_fsync_failure_retains_closed_attempt(self):
        inputs = self._inputs()
        state = deepcopy(self.native.batch.snapshot())
        raw = Path(inputs[2]["author_original"]["path"]).read_bytes()
        with patch.object(source_review.os, "fsync", side_effect=OSError("fixture fsync interruption")):
            with self.assertRaisesRegex(OSError, "fixture fsync interruption"):
                self.service.review(*inputs, str(self.slot))
        self.assertTrue(self.slot.is_dir())
        self.assertEqual((self.root / "researcher_v2.py").read_bytes(),
            adapter.author_payload(inputs[1])["source_text"].encode())
        self.assertFalse((self.slot / "static-review.json").exists())
        self.assertFalse((self.slot / "response.json").exists())
        self.assertEqual(self.native.batch.snapshot(), state)
        self.assertEqual(Path(inputs[2]["author_original"]["path"]).read_bytes(), raw)
        self._refused(inputs)  # Refusal proves no repair or reopened attempt.

    def test_partial_response_publish_failure_retains_source_and_static(self):
        inputs = self._inputs()
        state = deepcopy(self.native.batch.snapshot())
        save = engine.save
        def fail_response(path, value):
            if Path(path).name == "response.json":
                raise OSError("fixture response interruption")
            return save(path, value)
        with patch.object(source_review.engine, "save", side_effect=fail_response):
            with self.assertRaisesRegex(OSError, "fixture response interruption"):
                self.service.review(*inputs, str(self.slot))
        self.assertEqual((self.root / "researcher_v2.py").read_bytes(),
            adapter.author_payload(inputs[1])["source_text"].encode())
        self.assertTrue((self.slot / "static-review.json").is_file())
        self.assertFalse((self.slot / "response.json").exists())
        self.assertEqual(self.native.batch.snapshot(), state)
        self._refused(inputs)


if __name__ == "__main__":
    unittest.main()
