"""CP5b independent data-only review admission; local synthetic originals only.

The actual engine/native journal run. Existing task fixtures are composed, not
inherited/discovered. Synthetic accept coverage is compatibility, not CP6 benefit.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import test_capacity_feedback_engine as common_fixture
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import research_capacity_activation as activation
from supervisor_harness import research_capacity_identity as identity


BODY_FIELDS = {"schema", "after", "proposal", "entrypoints", "static_review", "review_receipt"}


class ReviewHandoffTests(unittest.TestCase):
    def owner(self):
        owner = common_fixture.CommonEngineTests()
        owner.setUp()
        self.addCleanup(owner.doCleanups)
        owner.setup_task()
        owner.envelope["max_rounds"] = 1
        owner.bound = engine.save(owner.root / "handoff-envelope.json", owner.envelope)
        return owner

    def persistence(self, owner):
        state = deepcopy(owner.native.batch.snapshot())
        files = {str(path.relative_to(owner.root)): path.read_bytes()
                 for root in (owner.root / "batch", owner.root / "versions")
                 for path in root.rglob("*") if path.is_file()}
        return {"state": state, "files": files}

    def reject_receipt(self, owner, before, after, entries, descriptor, proposal):
        micro = descriptor["micro_evolution"]
        pending = activation.micro.propose_micro_evolution(micro, proposal)["pending"]
        review = {"reviewer_id": micro["reviewer_id"], "proposal_sha256": pending["record_sha256"],
            "decision": "reject", "reason": "Synthetic exact rejection, no benefit measured",
            "tested_pair_sha256": digest(pending["pair"]), "anchor_pair_sha256": digest(micro["anchor_pair"]),
            "checks": {}, "benefit_observed": False, "benefit_evidence_sha256": None, "actual_write_paths": []}
        receipt = owner.native.artifact({"review": review, "evidence": {}})
        return receipt, [receipt]

    def offer(self, owner, mutation=None, *, mode="accept", after_saved=None):
        def review(choice, author, descriptor, slot):
            self.assertEqual(type(descriptor), dict)
            self.assertEqual(json.loads(json.dumps(descriptor)), descriptor)
            self.assertFalse(any(hasattr(descriptor, name) for name in ("batch", "propose", "review")))
            self.assertEqual(set(descriptor), {"schema", "decision_sha256", "author_original", "candidate",
                "parent_pair_sha256", "parent_identity", "parent_entrypoints", "state_sha256", "micro_evolution"})
            receipt_builder = (lambda *args: (None, [])) if mode == "pending" else (
                (lambda *args: self.reject_receipt(owner, *args)) if mode == "reject"
                else owner.synthetic_review_receipt)
            # Capture before any Reviewer original exists; persist exactly once below.
            with mock.patch.object(owner, "record", return_value=None), \
                    mock.patch.object(owner, "synthetic_review_receipt", side_effect=receipt_builder):
                raw = owner.review_role(choice, author, descriptor, slot)
            body = deepcopy({key: raw[key] for key in BODY_FIELDS})
            context = {"owner": owner, "choice": choice, "author": author, "descriptor": descriptor,
                       "slot": slot, "artifacts": deepcopy(raw["artifacts"])}
            if mutation is not None:
                mutation(body, context)
            original = owner.record(slot, body)
            reply = dict(body, original=original, artifacts=context["artifacts"])
            if after_saved is not None:
                after_saved(reply, context)
            return reply
        return review

    def invoke(self, owner, review, capacity=None):
        return engine.run(owner.bound, capacity or owner.native.restore(), owner.task,
                          services=dict(owner.services(), review=review))

    def rejected(self, mutation=None, *, mode="accept", after_saved=None, review_factory=None):
        owner = self.owner()
        capacity = owner.native.restore()
        before = self.persistence(owner)
        review = review_factory(owner) if review_factory else self.offer(owner, mutation, mode=mode, after_saved=after_saved)
        view_patches = []
        self.view_patches = view_patches
        try:
            with mock.patch.object(capacity, "_store", side_effect=AssertionError("bad review stored version")) as store, \
                    mock.patch.object(capacity.batch, "record_micro_evolution",
                                      side_effect=AssertionError("bad review appended native journal")) as record:
                with self.assertRaises(engine.driver.LoopHalted):
                    self.invoke(owner, review, capacity)
                store.assert_not_called()
                record.assert_not_called()
        finally:
            for patcher in reversed(view_patches):
                patcher.stop()
        self.assertEqual(self.persistence(owner), before)
        self.assertEqual(owner.task.calls, [])
        self.assertTrue((owner.root / "episode/loop/round-0001-source_review.failed.json").is_file())
        self.assertFalse((owner.root / "episode/loop/round-0001-execute.claim.json").exists())
        return owner

    def body_receipt(self, body, context, mutate):
        envelope = deepcopy(engine.read(body["review_receipt"]))
        mutate(envelope)
        fresh = context["owner"].native.artifact(envelope)
        body["review_receipt"] = fresh
        context["artifacts"].append(fresh)

    def scope(self, body, context, **changes):
        value = {"passed": True, "reviewer_id": "independent-auditor",
                 "proposer_id": body["proposal"]["proposer_id"],
                 "identity_sha256": digest(body["after"]), "entrypoints": body["entrypoints"]}
        value.update(changes)
        fresh = context["owner"].native.artifact(value)
        body["static_review"] = fresh
        context["artifacts"].append(fresh)

    def rebuild(self, body, **parts):
        old = body["after"]
        args = {"kernel": old["components"]["K"], "predictor": old["components"]["C"],
                "harness": old["components"]["H"], "researcher": old["components"]["R"],
                "model": old["model"], "runtime": old["runtime"], "memory": old["memory_sha256"]}
        args.update(parts)
        body["after"] = identity.manifest(**args)

    def tamper(self, bound, owner, label):
        path = Path(bound["path"])
        backup = owner.root / (label + "-original-bytes.json")
        with backup.open("xb") as stream:
            stream.write(path.read_bytes())
        path.write_text("{}", encoding="utf-8")

    def test_valid_pending_runs_the_parent_without_history_or_invented_benefit(self):
        owner = self.owner()
        review = self.offer(owner, mode="pending")
        outcome = self.invoke(owner, review)
        state = owner.native.batch.snapshot()["micro_evolution"]
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 1))
        self.assertEqual(state["active_pair"], activation.pair(owner.native.before))
        self.assertEqual(state["history"], [])
        self.assertEqual(state["used_candidate_ids"], ["researcher-loop-child"])
        self.assertIsNotNone(state["pending"])
        self.assertEqual(owner.task.calls[0].pair, digest(state["active_pair"]))
        self.assertEqual(owner.task.calls[0].context["messages"][0]["content"], "Execute local sum")
        self.assertEqual(len(owner.task.calls[0].context["messages"]), 2)  # Questions and reused task-state; no R2 instructions.
        stage = engine.driver._read_pair(owner.root / "episode/loop/round-0001-source_review.done.json")["output"]
        self.assertEqual(stage["verdict"], "pending")
        self.assertEqual(outcome["result"]["feedback"]["observed"], {"squared_error": 0})
        before = self.persistence(owner)
        calls = (len(owner.packets), len(owner.reviewed), len(owner.task.calls))
        self.assertEqual(self.invoke(owner, review), outcome)
        self.assertEqual(self.persistence(owner), before)
        self.assertEqual((len(owner.packets), len(owner.reviewed), len(owner.task.calls)), calls)

    def test_exact_reject_is_recorded_once_and_the_parent_is_used(self):
        owner = self.owner()
        outcome = self.invoke(owner, self.offer(owner, mode="reject"))
        state = owner.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(outcome["completed_rounds"], 1)
        self.assertEqual(state["active_pair"], activation.pair(owner.native.before))
        self.assertIsNone(state["pending"])
        self.assertEqual(len(state["history"]), 1)
        latest = state["history"][0]
        self.assertEqual(latest["review"]["decision"], "reject")
        self.assertFalse(latest["review"]["benefit_observed"])
        self.assertEqual(latest["proposal"]["problem_evidence_sha256"], owner.authored[0]["feedback_sha256"])
        self.assertEqual(owner.task.calls[0].pair, digest(state["active_pair"]))

    def test_existing_synthetic_accept_parity_consumes_the_exact_author_child(self):
        owner = self.owner()
        result = self.invoke(owner, self.offer(owner))
        state = owner.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["review"]["decision"], "accept")
        self.assertEqual(owner.task.calls[0].context["messages"][1]["content"], "Verify signs with calculate")
        self.assertEqual(owner.task.calls[0].pair, digest(state["active_pair"]))
        self.assertFalse(result["result"]["claims"]["learning"])
        author = engine.read(engine.pin(owner.root / "episode/roles/author-1/response.json"))
        selected = owner.native.restore()._selected(owner.native.batch.snapshot())
        self.assertEqual(selected["manifest"]["components"]["R"]["sources"][selected["entrypoints"]["R"]],
                         hashlib.sha256(author["source_text"].encode()).hexdigest())

    def test_disposable_choice_author_and_descriptor_copies_have_no_state_authority(self):
        owner = self.owner()
        def mutate(body, context):
            context["choice"].clear()
            context["author"].clear()
            context["descriptor"]["parent_identity"]["components"].clear()
            context["descriptor"]["micro_evolution"]["active_pair"].clear()
            context["descriptor"]["state_sha256"] = "d" * 64
        result = self.invoke(owner, self.offer(owner, mutate, mode="pending"))
        self.assertEqual(result["completed_rounds"], 1)
        self.assertEqual(owner.native.batch.snapshot()["micro_evolution"]["active_pair"], activation.pair(owner.native.before))
        self.assertEqual(engine.read(engine.pin(owner.root / "episode/decision-01.json")), owner.authored[0])

    def test_unknown_fake_verdict_and_extra_spec_fields_reject_before_native_write(self):
        for kind in ("fake-verdict", "extra", "wrong-schema"):
            with self.subTest(kind=kind):
                def mutate(body, context):
                    if kind == "fake-verdict":
                        body.clear(); body["verdict"] = "reject"
                    elif kind == "extra":
                        body["unknown"] = True
                    else:
                        body["schema"] = "wrong-spec"
                self.rejected(mutate)

    def test_different_source_cannot_be_adopted_or_rejected_as_current_author(self):
        for mode in ("accept", "reject"):
            with self.subTest(mode=mode):
                def mutate(body, context):
                    binding = deepcopy(body["after"]["components"]["R"])
                    binding["sources"][body["entrypoints"]["R"]] = "e" * 64
                    self.rebuild(body, researcher=binding)
                self.rejected(mutate, mode=mode)

    def test_wrong_axis_or_composite_manifest_rejects_before_store(self):
        for kind in ("native-axis", "composite"):
            with self.subTest(kind=kind):
                def mutate(body, context):
                    if kind == "native-axis":
                        body["proposal"]["axis"] = "harness"
                    else:
                        value = deepcopy(body["after"]["components"]["H"])
                        value["configuration_sha256"] = "e" * 64
                        self.rebuild(body, harness=value)
                self.rejected(mutate)

    def test_wrong_component_or_expected_effect_rejects_before_store(self):
        for field, wrong in (("component", "memory_policy"), ("behavior_change", "Unrelated effect")):
            with self.subTest(field=field):
                self.rejected(lambda body, ctx: body["proposal"].update({field: wrong}))

    def test_wrong_feedback_or_parent_rejects_before_store(self):
        for field in ("problem_evidence_sha256", "parent_pair_sha256"):
            with self.subTest(field=field):
                self.rejected(lambda body, ctx: body["proposal"].update({field: "e" * 64}))

    def test_native_pair_patch_and_file_delta_are_prechecked(self):
        for field, wrong in (("pair", {"harness_sha256": "e" * 64, "researcher_sha256": "f" * 64}),
                             ("patch_sha256", "e" * 64), ("write_paths", ["researcher_v2.py"])):
            with self.subTest(field=field):
                self.rejected(lambda body, ctx: body["proposal"].update({field: wrong}))

    def test_fixed_evaluation_model_predictor_memory_and_runtime_are_protected(self):
        for kind in ("kernel", "model", "predictor", "memory", "runtime"):
            with self.subTest(kind=kind):
                def mutate(body, context):
                    if kind in ("kernel", "predictor"):
                        axis = "K" if kind == "kernel" else "C"
                        value = deepcopy(body["after"]["components"][axis]); value["configuration_sha256"] = "e" * 64
                    elif kind == "model":
                        value = deepcopy(body["after"]["model"]); value["requested_model"] = "different-model"
                    elif kind == "memory":
                        value = "e" * 64
                    else:
                        value = deepcopy(body["after"]["runtime"]); value["dependencies"] = {"fixture": {"version": "1", "sha256": "e" * 64}}
                    self.rebuild(body, **{kind: value})
                self.rejected(mutate)

    def test_bad_static_scope_identity_actor_and_proposer_are_prechecked(self):
        for kind in ("failed", "identity", "reviewer", "same-configured-actor", "proposer"):
            with self.subTest(kind=kind):
                def mutate(body, context):
                    if kind == "same-configured-actor":
                        body["proposal"]["proposer_id"] = "independent-auditor"
                        self.scope(body, context)
                    else:
                        field, value = {"failed": ("passed", False), "identity": ("identity_sha256", "e" * 64),
                            "reviewer": ("reviewer_id", "wrong-auditor"), "proposer": ("proposer_id", "wrong-author")}[kind]
                        self.scope(body, context, **{field: value})
                self.rejected(mutate)

    def test_review_receipt_actor_proposal_and_decision_are_prechecked(self):
        for field, wrong in (("reviewer_id", "wrong-auditor"), ("proposal_sha256", "e" * 64), ("decision", "unknown")):
            with self.subTest(field=field):
                def mutate(body, context):
                    self.body_receipt(body, context, lambda value: value["review"].update({field: wrong}))
                self.rejected(mutate)

    def test_missing_benefit_or_incomplete_accept_checks_cannot_leave_pending(self):
        for kind in ("benefit-false", "missing-check", "failed-check"):
            with self.subTest(kind=kind):
                def change(value):
                    if kind == "benefit-false":
                        value["review"]["benefit_observed"] = False
                    elif kind == "missing-check":
                        value["review"]["checks"].pop(next(iter(value["review"]["checks"])))
                    else:
                        next(iter(value["review"]["checks"].values()))["passed"] = False
                self.rejected(lambda body, ctx: self.body_receipt(body, ctx, change))

    def test_unrelated_compatibility_evidence_cannot_leave_pending(self):
        def mutate(body, context):
            def change(value):
                token = next(iter(value["review"]["checks"].values()))["evidence_sha256"]
                evidence = deepcopy(engine.read({"path": value["evidence"][token], "sha256": token}))
                evidence["binding"]["before_identity_sha256"] = "e" * 64
                fresh = context["owner"].native.artifact(evidence)
                value["evidence"][fresh["sha256"]] = fresh["path"]
                for check in value["review"]["checks"].values(): check["evidence_sha256"] = fresh["sha256"]
                context["artifacts"].append(fresh)
            self.body_receipt(body, context, change)
        self.rejected(mutate)

    def test_unrelated_benefit_identity_effect_or_outputs_cannot_leave_pending(self):
        for field, wrong in (("after_identity_sha256", "e" * 64), ("effect", "Different benefit"),
                             ("matched_outputs_sha256", "e" * 64)):
            with self.subTest(field=field):
                def mutate(body, context):
                    def change(value):
                        token = value["review"]["benefit_evidence_sha256"]
                        benefit = deepcopy(engine.read({"path": value["evidence"][token], "sha256": token}))
                        benefit[field] = wrong
                        fresh = context["owner"].native.artifact(benefit)
                        value["evidence"][fresh["sha256"]] = fresh["path"]
                        value["review"]["benefit_evidence_sha256"] = fresh["sha256"]
                        context["artifacts"].append(fresh)
                    self.body_receipt(body, context, change)
                self.rejected(mutate)

    def test_returned_spec_must_equal_the_preserved_reviewer_original(self):
        self.rejected(after_saved=lambda reply, ctx: reply["proposal"].update(component="memory_policy"))

    def test_reviewer_original_slot_hash_and_symlink_are_checked(self):
        for kind in ("slot", "hash", "symlink"):
            with self.subTest(kind=kind):
                def change(reply, context):
                    if kind == "slot":
                        reply["original"] = context["owner"].native.artifact({key: reply[key] for key in BODY_FIELDS})
                    elif kind == "hash":
                        reply["original"]["sha256"] = "e" * 64
                    else:
                        path = Path(reply["original"]["path"]); path.rename(path.with_name("preserved-response.json"))
                        path.symlink_to("preserved-response.json")
                self.rejected(after_saved=change)

    def test_missing_or_drifted_returned_artifact_is_checked_before_store(self):
        for kind in ("missing", "drift"):
            with self.subTest(kind=kind):
                def mutate(body, context):
                    context["artifacts"].append({"path": str(context["owner"].root / "missing.json") if kind == "missing"
                        else body["static_review"]["path"], "sha256": "e" * 64})
                self.rejected(mutate)

    def test_unchanged_author_original_is_rechecked_after_reviewer(self):
        self.rejected(lambda body, ctx: self.tamper(ctx["descriptor"]["author_original"], ctx["owner"], "author"))

    def test_saved_choice_and_candidate_are_rechecked_after_reviewer(self):
        for kind in ("decision", "candidate"):
            with self.subTest(kind=kind):
                def mutate(body, context):
                    bound = context["descriptor"]["candidate"] if kind == "candidate" else engine.pin(context["owner"].root / "episode/decision-01.json")
                    self.tamper(bound, context["owner"], kind)
                self.rejected(mutate)

    def test_observed_state_drift_stops_before_native_write(self):
        def mutate(body, context):
            # Observation-only view drift. This probe does not itself append a native record.
            value = context["owner"].native.batch.snapshot()
            value["state_sha256"] = "e" * 64
            patcher = mock.patch.object(context["owner"].native.batch, "snapshot", return_value=value)
            patcher.start(); self.view_patches.append(patcher)
        self.rejected(mutate)

    def test_old_callback_has_no_mutable_native_object_capability(self):
        def factory(owner):
            def old_review(choice, author, descriptor, slot):
                return descriptor.batch.snapshot()
            return old_review
        self.rejected(review_factory=factory)


if __name__ == "__main__":
    unittest.main()
