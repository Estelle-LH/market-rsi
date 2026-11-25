"""I3: actual native review closure, using synthetic local role originals only.

Fixture composition keeps inherited TestCases out of this module's discovery.
No provider, credentials or empirical data are used; production source is unchanged.
"""
from copy import deepcopy
import unittest

import earnings_capacity_adapter as profiles
import test_capacity_feedback_engine as fixtures
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class ReviewActivationInterfaceTests(unittest.TestCase):
    def fixture(self, *, rounds=1):
        owner = fixtures.CommonEngineTests("runTest")
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        owner.setup_task("sum")
        owner.envelope["max_rounds"] = rounds
        owner.bound = engine.save(owner.root / "i3-envelope.json", owner.envelope)
        return owner

    def invoke(self, owner, *, review=None, author=None):
        services = owner.services()
        if review is not None:
            services["review"] = review
        if author is not None:
            services["author"] = author
        return engine.run(owner.bound, owner.native.restore(), owner.task, services=services)

    def assert_halted_before_worker(self, owner, *, review=None, author=None, reason):
        with self.assertRaises(engine.driver.LoopHalted) as halted:
            self.invoke(owner, review=review, author=author)
        self.assertIsInstance(halted.exception.__cause__, ValueError)
        self.assertIn(reason, str(halted.exception.__cause__))
        self.assertEqual(owner.task.calls, [])
        loop = owner.root / "episode/loop"
        self.assertTrue((loop / "round-0001-source_review.failed.json").is_file())
        self.assertFalse((loop / "round-0001-source_review.done.json").exists())
        self.assertFalse((loop / "round-0001-execute.claim.json").exists())

    @staticmethod
    def native_snapshot(owner):
        """Assert native state/registry separately from role-slot evidence writes."""
        return {"state": deepcopy(owner.native.batch.snapshot()),
                "registry": {str(path.relative_to(owner.root / "versions")): engine.driver.c.sha(path)
                             for path in (owner.root / "versions").rglob("*") if path.is_file()}}

    def assert_no_native_mutation(self, owner, baseline):
        self.assertEqual(self.native_snapshot(owner), baseline)
        micro = baseline["state"]["micro_evolution"]
        self.assertEqual(owner.native.batch.snapshot()["micro_evolution"]["active_pair"], micro["active_pair"])
        self.assertEqual(owner.native.batch.snapshot()["micro_evolution"]["history"], micro["history"])
        self.assertEqual(owner.native.batch.snapshot()["micro_evolution"]["pending"], micro["pending"])
        self.assertEqual(owner.native.batch.snapshot()["micro_evolution"]["used_candidate_ids"], micro["used_candidate_ids"])

    def review_spec(self, owner, choice, original, descriptor, slot, *, axis=None, updates=None,
                    source=None, component=None, accept=True, receipt=True, external_receipt=None):
        """Offer plain data only; never propose/review/resolve native capacity.

        Source overrides intentionally offer an unrelated but internally bound
        literal child, allowing the production engine to reject substitution.
        """
        axis = axis or choice["axis"]
        self.assertEqual(descriptor["schema"], "capacity_review_context_v1")
        before = descriptor["parent_identity"]
        args = deepcopy(owner.native.args)
        args["harness"], args["researcher"] = before["components"]["H"], before["components"]["R"]
        kind = {"R": "researcher", "H": "harness"}[axis]
        name = kind + "_v2.py"
        if source is not None:
            (owner.root / name).write_text(source)
        args[kind] = {"sources": {name: engine.driver.c.sha(owner.root / name)},
                      "configuration_sha256": owner.native.args[kind]["configuration_sha256"]}
        after = profiles.identity.manifest(**args)
        entries = {key: next(iter(after["components"][key]["sources"])) for key in ("R", "H")}
        proposal = {"candidate_id": "i3-" + axis, "proposer_id": "fixture-author", "axis": kind,
                    "component": component or ("research_policy" if axis == "R" else "tool_interface"),
                    "behavior_change": choice["expected_effect"],
                    "problem_evidence_sha256": choice["feedback_sha256"],
                    "parent_pair_sha256": choice["parent_pair_sha256"],
                    "pair": profiles.activation.pair(after), "fixed_context": descriptor["micro_evolution"]["fixed_context"],
                    "write_paths": list(before["components"][axis]["sources"]) + [name],
                    "patch_sha256": profiles.activation.patch_digest(before, after)}
        scope = owner.native.artifact({"passed": True, "reviewer_id": "independent-auditor",
                                       "proposer_id": "fixture-author", "identity_sha256": digest(after),
                                       "entrypoints": entries})
        review_receipt, artifacts = None, [scope]
        if receipt:
            previous = owner.reject
            owner.reject = not accept
            try:
                review_receipt, evidence = owner.synthetic_review_receipt(before, after, entries, descriptor, proposal)
            finally:
                owner.reject = previous
            artifacts.extend(evidence)
            if external_receipt is not None:
                review_receipt = external_receipt
                artifacts.append(external_receipt)
        # Mutate offered data after making internally valid synthetic receipts:
        # bad parent/feedback/component must reach the production handoff check.
        proposal.update(updates or {})
        body = {"schema": "capacity_review_spec_v1", "after": after, "proposal": proposal,
                "entrypoints": entries, "static_review": scope, "review_receipt": review_receipt}
        return dict(body, original=owner.record(slot, body), artifacts=artifacts)

    def test_original_author_R_then_H_reaches_native_selected_worker_and_cold_restore(self):
        owner = self.fixture(rounds=2)
        outcome = self.invoke(owner)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 2))
        state = owner.native.batch.snapshot()["micro_evolution"]
        self.assertIsNone(state["pending"])
        self.assertEqual([row["proposal"]["axis"] for row in state["history"]], ["researcher", "harness"])
        self.assertEqual([row["review"]["decision"] for row in state["history"]], ["accept", "accept"])
        selected = owner.native.restore()._selected(owner.native.batch.snapshot())
        for index, axis in enumerate(("R", "H"), 1):
            original = engine.read(engine.pin(owner.root / f"episode/roles/author-{index}/response.json"))
            name = selected["entrypoints"][axis]
            self.assertEqual(selected["manifest"]["components"][axis]["sources"][name],
                             profiles.author_candidate(original, {"R": {"axis": "R", "research_instructions": "", "reuse_facts": True},
                                                                  "H": {"axis": "H", "read_chunk_limit": 20000, "search_hit_limit": 50}}[axis],
                                                       owner.authored[index - 1])["source_sha256"])
        first, second = owner.task.calls
        self.assertEqual(first.context["messages"][1]["content"], "Verify signs with calculate")
        self.assertEqual(second.context["tool_bounds"]["read_chunk_limit"], 1000)
        self.assertEqual(outcome["result"]["pair_sha256"], digest(state["active_pair"]))
        self.assertFalse(outcome["result"]["claims"]["live_RH_authorship"])
        self.assertEqual(owner.packets[1]["feedback"]["observed"], {"squared_error": 0})
        self.assertEqual(second.state["records"][0], first.state["records"][0])
        counts = (len(owner.packets), len(owner.authored), len(owner.reviewed), len(owner.task.calls))
        self.assertEqual(self.invoke(owner), outcome)
        self.assertEqual((len(owner.packets), len(owner.authored), len(owner.reviewed), len(owner.task.calls)), counts)

    def test_pretend_accept_or_reject_without_native_review_cannot_execute(self):
        for verdict in ("accept", "reject"):
            with self.subTest(verdict=verdict):
                owner = self.fixture()
                baseline = self.native_snapshot(owner)
                def pretend(choice, original, descriptor, slot):
                    body = {"verdict": verdict}
                    return dict(body, original=owner.record(slot, body), artifacts=[])
                self.assert_halted_before_worker(owner, review=pretend, reason="Exact data-only source review")
                self.assert_no_native_mutation(owner, baseline)

    def test_selected_child_must_be_the_unchanged_author_original(self):
        owner = self.fixture()
        baseline = self.native_snapshot(owner)
        captured = []
        offered = []
        def substitute(choice, original, descriptor, slot):
            captured.append(deepcopy(original))
            payload = profiles.author_payload(original)
            altered_source = payload["source_text"].replace("Verify signs with calculate", "Use calculator on every sign")
            spec = self.review_spec(owner, choice, original, descriptor, slot, source=altered_source)
            offered.append(spec)
            return spec
        self.assert_halted_before_worker(owner, review=substitute, reason="unchanged Author original")
        retained = engine.read(engine.pin(owner.root / "episode/roles/author-1/response.json"))
        self.assertEqual(retained, captured[0])
        self.assertIn("Verify signs with calculate", profiles.author_payload(retained)["source_text"])
        self.assertTrue(offered, "Probe must genuinely offer a bound unrelated spec")
        proposed = offered[0]["after"]["components"]["R"]["sources"]["researcher_v2.py"]
        self.assertNotEqual(proposed, profiles.author_candidate(retained,
            {"axis":"R","research_instructions":"","reuse_facts":True}, owner.authored[0])["source_sha256"])
        self.assert_no_native_mutation(owner, baseline)

    def test_wrong_axis_parent_or_feedback_lineage_cannot_close_source_review(self):
        for mutation in ("axis", "component", "parent", "feedback"):
            with self.subTest(mutation=mutation):
                owner = self.fixture()
                baseline = self.native_snapshot(owner)
                offered = []
                def wrong(choice, original, descriptor, slot):
                    updates = {"parent_pair_sha256": "c" * 64} if mutation == "parent" else (
                        {"problem_evidence_sha256": "d" * 64} if mutation == "feedback" else (
                        {"component": "memory_policy"} if mutation == "component" else {}))
                    spec = self.review_spec(owner, choice, original, descriptor, slot,
                        axis="H" if mutation == "axis" else "R", updates=updates)
                    offered.append(spec)
                    return spec
                self.assert_halted_before_worker(owner, review=wrong, reason="Native proposal differs")
                self.assertTrue(offered, "Invalid data spec must reach engine validation")
                self.assert_no_native_mutation(owner, baseline)

    def test_valid_unmeasured_pending_executes_unchanged_parent_without_adoption(self):
        owner = self.fixture()
        parent = profiles.activation.pair(owner.native.before)
        def pending(choice, original, descriptor, slot):
            return self.review_spec(owner, choice, original, descriptor, slot, receipt=False)
        outcome = self.invoke(owner, review=pending)
        micro = owner.native.batch.snapshot()["micro_evolution"]
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 1))
        self.assertEqual(micro["active_pair"], parent)
        self.assertEqual(micro["history"], [])
        self.assertIsNotNone(micro["pending"])
        self.assertEqual(len(micro["used_candidate_ids"]), 1)
        self.assertEqual(owner.task.calls[0].pair, digest(parent))
        self.assertEqual(owner.task.calls[0].context["tool_bounds"]["read_chunk_limit"], 20000)
        self.assertNotIn("Verify signs with calculate", [message["content"]
            for message in owner.task.calls[0].context["messages"]])
        reviewed = engine.driver._read_pair(owner.root / "episode/loop/round-0001-source_review.done.json")["output"]
        self.assertEqual(reviewed["verdict"], "pending")
        self.assertFalse(outcome["result"]["claims"]["learning"])

    def test_preexisting_stale_review_history_cannot_close_new_author_proposal(self):
        owner = self.fixture()
        # Intentional pre-existing native rejection, outside the reviewer service.
        before, after = owner.native.propose("R")
        stale = owner.native.review_receipt(before, after, accept=False)
        owner.native.adapter.review(stale, expected_state_sha256=owner.native.batch.snapshot()["state_sha256"])
        baseline = self.native_snapshot(owner)
        self.assertEqual(len(baseline["state"]["micro_evolution"]["history"]), 1)
        def stale_history(choice, original, descriptor, slot):
            return self.review_spec(owner, choice, original, descriptor, slot, external_receipt=stale)
        self.assert_halted_before_worker(owner, review=stale_history, reason="pending proposal")
        self.assert_no_native_mutation(owner, baseline)

    def test_actual_reject_preserves_selected_parent_and_appends_exact_history(self):
        owner = self.fixture()
        owner.reject = True
        parent = profiles.activation.pair(owner.native.before)
        outcome = self.invoke(owner)
        state = owner.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(state["active_pair"], parent)
        self.assertIsNone(state["pending"])
        self.assertEqual(len(state["history"]), 1)
        record = state["history"][0]
        self.assertEqual(record["review"]["decision"], "reject")
        self.assertEqual(record["proposal"]["parent_pair_sha256"], digest(parent))
        self.assertEqual(record["proposal"]["problem_evidence_sha256"], owner.packets[0]["feedback_sha256"])
        self.assertEqual(owner.task.calls[0].pair, digest(parent))
        self.assertEqual(owner.task.calls[0].context["tool_bounds"]["read_chunk_limit"], 20000)
        self.assertEqual(owner.native.restore().resolve("R", expected_pair_sha256=digest(parent))["profile"]["research_instructions"], "")

    def test_real_parent_drift_before_source_review_stops_before_reviewer_and_worker(self):
        owner = self.fixture()
        def drift(choice, before_profile, slot):
            original = owner.author_role(choice, before_profile, slot)
            # Deliberate external native mutation during Author, not reviewer authority.
            before, after = owner.native.propose("H")
            receipt = owner.native.review_receipt(before, after)
            owner.native.adapter.review(receipt, expected_state_sha256=owner.native.batch.snapshot()["state_sha256"])
            return original
        self.assert_halted_before_worker(owner, author=drift, reason="Capacity drift before source review")
        self.assertEqual(owner.reviewed, [])
        self.assertEqual(len(owner.native.batch.snapshot()["micro_evolution"]["history"]), 1)
        self.assertTrue((owner.root / "episode/roles/author-1/response.json").is_file())


if __name__ == "__main__":
    unittest.main()
