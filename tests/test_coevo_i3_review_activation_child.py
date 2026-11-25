"""I3 child: unrelated rejection specs cannot mutate native adoption state."""
import hashlib
import unittest

import test_coevo_i3_review_activation as parent_fixture
from supervisor_harness import capacity_feedback_engine as engine


class RejectedAuthorProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.helpers = parent_fixture.ReviewActivationInterfaceTests("runTest")
        self.addCleanup(self.helpers.doCleanups)

    def require_exact_rejection(self, mutation):
        owner = self.helpers.fixture()
        baseline = self.helpers.native_snapshot(owner)
        observation = {}

        def reject_other_child(choice, original, descriptor, slot):
            axis = "H" if mutation == "wrong_axis" else "R"
            source, component = None, None
            authored = parent_fixture.profiles.author_payload(original)
            if mutation == "different_source":
                source = authored["source_text"].replace("Verify signs with calculate", "Unrelated rejected instruction")
            elif mutation == "wrong_component":
                source = "PROFILE = {'axis':'R','research_instructions':'','reuse_facts':False}\n"
                component = "memory_policy"
            spec = self.helpers.review_spec(owner, choice, original, descriptor, slot,
                axis=axis, source=source, component=component, accept=False)
            proposal, after = spec["proposal"], spec["after"]
            observation.update(
                mutation=mutation, chosen_axis=choice["axis"], chosen_component=choice["component"],
                original_author_source_sha256=hashlib.sha256(authored["source_text"].encode()).hexdigest(),
                offered_axis=proposal["axis"], offered_component=proposal["component"],
                offered_source_sha256=next(iter(after["components"][axis]["sources"].values())),
                matching_feedback=proposal["problem_evidence_sha256"] == choice["feedback_sha256"],
                matching_parent=proposal["parent_pair_sha256"] == choice["parent_pair_sha256"],
                offered_decision=engine.read(spec["review_receipt"])["review"]["decision"],
                review_original=spec["original"])
            return spec

        with self.assertRaises(engine.driver.LoopHalted) as halted:
            self.helpers.invoke(owner, review=reject_other_child)
        self.assertIsInstance(halted.exception.__cause__, ValueError)
        reason = "unchanged Author original" if mutation == "different_source" else "Native proposal differs"
        self.assertIn(reason, str(halted.exception.__cause__))
        self.assertEqual(owner.task.calls, [])
        self.assertTrue(observation, "Probe must genuinely offer an unrelated bound rejection spec")
        self.assertEqual(observation["offered_decision"], "reject")
        self.assertTrue(observation["matching_feedback"])
        self.assertTrue(observation["matching_parent"])
        if mutation == "different_source":
            self.assertNotEqual(observation["offered_source_sha256"], observation["original_author_source_sha256"])
        if mutation == "wrong_component":
            self.assertNotEqual(observation["offered_component"], observation["chosen_component"])
        offered = engine.read(observation["review_original"])
        self.assertEqual(offered["schema"], "capacity_review_spec_v1")
        retained = engine.read(engine.pin(owner.root / "episode/roles/author-1/response.json"))
        self.assertEqual(hashlib.sha256(parent_fixture.profiles.author_payload(retained)["source_text"].encode()).hexdigest(),
                         observation["original_author_source_sha256"])
        self.helpers.assert_no_native_mutation(owner, baseline)
        micro = owner.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(micro["history"], [])
        self.assertIsNone(micro["pending"])
        self.assertEqual(micro["used_candidate_ids"], [])

    def test_reject_01_wrong_axis_cannot_close_current_author(self):
        self.require_exact_rejection("wrong_axis")

    def test_reject_02_different_source_cannot_close_current_author(self):
        self.require_exact_rejection("different_source")

    def test_reject_03_wrong_component_cannot_close_current_author(self):
        self.require_exact_rejection("wrong_component")


if __name__ == "__main__":
    unittest.main()
