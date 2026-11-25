"""Generic evidence is bytes; candidate/spec/receipt contracts stay typed.

Compose existing task/native/ReviewHandoff fixtures without inherited suites.
No model, provider or proof of learning; supplemental Python is retained data,
never executed. Typed Author candidate validation remains separate.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest import mock

from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import research_capacity_activation as activation
import test_capacity_review_handoff as handoff


class ReviewArtifactTypesTests(unittest.TestCase):
    def helper(self):
        helper = handoff.ReviewHandoffTests()
        self.addCleanup(helper.doCleanups)
        return helper

    def binary(self, owner, name="retained-byte-evidence.dat", data=b"\xff\x00\x81 retained evidence, not JSON"):
        path = owner.root / name
        with path.open("xb") as stream:
            stream.write(data)
        return engine.pin(path)

    def test_actual_literal_and_non_UTF8_evidence_bindings_pass_without_parsing_or_execution(self):
        helper = self.helper()
        owner = helper.owner()
        saved = []
        def evidence(body, context):
            exact_candidate = engine.pin(owner.root / body["entrypoints"]["R"])
            supplemental = self.binary(owner, "never-execute-evidence.py", b"raise AssertionError('EVIDENCE_MUST_NOT_EXECUTE')\n")
            opaque = self.binary(owner)
            saved.extend([exact_candidate, supplemental, opaque])
            context["artifacts"].extend(saved)
        outcome = helper.invoke(owner, helper.offer(owner, evidence, mode="pending"))
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 1))
        micro = owner.native.batch.snapshot()["micro_evolution"]
        self.assertIsNotNone(micro["pending"])
        self.assertEqual(micro["active_pair"], activation.pair(owner.native.before))
        self.assertEqual(micro["history"], [])
        stage = engine.driver._read_pair(owner.root / "episode/loop/round-0001-source_review.done.json")["output"]
        self.assertTrue(all(bound in stage["artifacts"] for bound in saved))
        self.assertEqual(engine.driver.c._read(saved[1], binary=True), b"raise AssertionError('EVIDENCE_MUST_NOT_EXECUTE')\n")
        self.assertEqual(engine.driver.c._read(saved[2], binary=True), b"\xff\x00\x81 retained evidence, not JSON")
        self.assertEqual(len(owner.task.calls), 1)
        self.assertFalse(outcome["result"]["claims"]["learning"])

    def test_retained_binary_byte_drift_refuses_before_native_store_or_forecast(self):
        helper = self.helper()
        def evidence(body, context):
            bound = self.binary(context["owner"])
            context["artifacts"].append(bound)
            path = Path(bound["path"])
            with (path.parent / "before-binary-drift.dat").open("xb") as stream:
                stream.write(path.read_bytes())
            path.write_bytes(path.read_bytes() + b" changed after pin")
        helper.rejected(evidence, mode="pending")

    def test_missing_bytes_wrong_hash_or_extra_binding_field_remain_invalid(self):
        for kind in ("missing", "hash", "extra-field"):
            with self.subTest(kind=kind):
                helper = self.helper()
                def evidence(body, context):
                    owner = context["owner"]
                    if kind == "missing":
                        bound = {"path": str(owner.root / "never-created.dat"), "sha256": "e" * 64}
                    else:
                        bound = self.binary(owner)
                        if kind == "hash": bound["sha256"] = "e" * 64
                        else: bound["format"] = "binary"
                    context["artifacts"].append(bound)
                helper.rejected(evidence, mode="pending")

    def test_relative_noncanonical_or_symlink_byte_binding_refuses_before_native_mutation(self):
        for kind in ("relative", "noncanonical", "symlink"):
            with self.subTest(kind=kind):
                helper = self.helper()
                def evidence(body, context):
                    owner = context["owner"]
                    bound = self.binary(owner)
                    if kind == "relative": bound["path"] = Path(bound["path"]).name
                    elif kind == "noncanonical": bound["path"] = str(owner.root / "episode" / ".." / Path(bound["path"]).name)
                    else:
                        alias = owner.root / "aliased-byte-evidence.dat"
                        alias.symlink_to(Path(bound["path"]).name)
                        bound["path"] = str(alias)
                    context["artifacts"].append(bound)
                helper.rejected(evidence, mode="pending")

    def test_spec_static_review_and_review_receipt_still_require_typed_JSON(self):
        for kind in ("spec", "static_review", "review_receipt"):
            with self.subTest(kind=kind):
                helper = self.helper()
                def evidence(body, context):
                    if kind != "spec":
                        bound = self.binary(context["owner"], kind + ".json", b"PROFILE = {'not': 'JSON'}\n")
                        body[kind] = bound
                        context["artifacts"].append(bound)
                def original(reply, context):
                    if kind == "spec":
                        path = Path(reply["original"]["path"])
                        path.rename(path.with_name("preserved-valid-review-spec.json"))
                        with path.open("xb") as stream:
                            stream.write(b"PROFILE = {'not': 'JSON'}\n")
                        reply["original"] = engine.pin(path)
                helper.rejected(evidence, after_saved=original)

    def test_actual_Author_literal_validation_is_not_replaced_by_binary_artifact_validation(self):
        for bad in ("PROFILE = {'axis':'R','research_instructions':'x','reuse_facts':True}\nraise AssertionError('DO_NOT_EXECUTE')\n",
                    "PROFILE = {'axis':'R','research_instructions':'x','reuse_facts':True,'new_authority':True}\n"):
            with self.subTest(source=bad):
                helper = self.helper()
                owner = helper.owner()
                capacity = owner.native.restore()
                before = helper.persistence(owner)
                actual_author = owner.author_role
                def author(choice, profile, slot):
                    bound = actual_author(choice, profile, slot)
                    value = deepcopy(engine.read(bound)); value["source_text"] = bad
                    path = Path(bound["path"])
                    path.rename(path.with_name("preserved-valid-author.json"))
                    return engine.save(path, value)
                review_calls = []
                actual_review = helper.offer(owner, mode="pending")
                def source_review(*args):
                    review_calls.append(args)
                    return actual_review(*args)
                services = dict(owner.services(), author=author, review=source_review)
                with mock.patch.object(capacity, "_store", side_effect=AssertionError("invalid literal stored")) as store, \
                        mock.patch.object(capacity.batch, "record_micro_evolution", side_effect=AssertionError("invalid literal recorded")) as record:
                    with self.assertRaises(engine.driver.LoopHalted): engine.run(owner.bound, capacity, owner.task, services=services)
                    store.assert_not_called(); record.assert_not_called()
                self.assertEqual(review_calls, [])
                self.assertEqual(helper.persistence(owner), before)
                self.assertEqual(owner.task.calls, [])
                self.assertTrue((owner.root / "episode/loop/round-0001-implement.failed.json").is_file())


if __name__ == "__main__":
    unittest.main()
