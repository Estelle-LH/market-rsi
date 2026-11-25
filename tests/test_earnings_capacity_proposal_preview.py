"""CP5a pure native preflight on local fixtures, never model/benefit evidence.

Compose the existing fixture builders without inheriting their TestCases or
collecting their tests. Proposal capture does not call the native writer.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest import mock

import test_earnings_capacity_adapter as earnings_fixture
from market_rsi import digest
from supervisor_harness import research_capacity_activation as activation
from supervisor_harness import research_capacity_identity as identity
from supervisor_harness import test_research_capacity_activation as native_fixture


class ProposalPreviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = self.make_fixture()

    def make_fixture(self, *, earnings=False):
        builder = (earnings_fixture.EarningsCapacityTests if earnings
                   else native_fixture.CapacityActivationTests)()
        builder.setUp()
        self.addCleanup(builder.doCleanups)
        return builder

    def draft(self, fixture=None, axis="R"):
        f = fixture or self.fixture
        with mock.patch.object(f.adapter, "propose") as intercepted:
            f.propose(axis)
        after, proposal, entries = intercepted.call_args.args
        return {"after": deepcopy(after), "proposal": deepcopy(proposal),
                "entrypoints": deepcopy(entries), **deepcopy(intercepted.call_args.kwargs)}

    def persistence(self, fixture=None):
        f = fixture or self.fixture
        state = deepcopy(f.batch.snapshot())
        files = {}
        for root in (f.root / "batch", f.root / "versions"):
            for path in root.rglob("*"):
                if path.is_file():
                    files[str(path.relative_to(f.root))] = path.read_bytes()
        return {"state": state, "files": files}

    def preview(self, value, fixture=None):
        f = fixture or self.fixture
        before = self.persistence(f)
        with mock.patch.object(f.adapter, "_store", side_effect=AssertionError("preview wrote registry")) as store, \
                mock.patch.object(f.batch, "record_micro_evolution", side_effect=AssertionError("preview wrote journal")) as record:
            result = f.adapter.preview_proposal(**value)
        store.assert_not_called()
        record.assert_not_called()
        self.assertEqual(self.persistence(f), before)
        return result

    def reject(self, value, fixture=None, *, method="preview_proposal"):
        f = fixture or self.fixture
        before = self.persistence(f)
        with mock.patch.object(f.adapter, "_store", side_effect=AssertionError("invalid proposal wrote registry")) as store, \
                mock.patch.object(f.batch, "record_micro_evolution", side_effect=AssertionError("invalid proposal wrote journal")) as record:
            with self.assertRaises((ValueError, FileNotFoundError)):
                getattr(f.adapter, method)(**value)
        store.assert_not_called()
        record.assert_not_called()
        self.assertEqual(self.persistence(f), before)

    def scope(self, value, fixture=None, **changes):
        f = fixture or self.fixture
        receipt = {"passed": True, "reviewer_id": "independent-auditor",
                   "proposer_id": value["proposal"]["proposer_id"],
                   "identity_sha256": digest(value["after"]), "entrypoints": value["entrypoints"]}
        receipt.update(changes)
        value["static_review"] = f.artifact(receipt, label="preview-scope")

    def rebind(self, value, args, *, axis="R", fixture=None):
        f = fixture or self.fixture
        value["after"] = identity.manifest(**args)
        value["entrypoints"] = {key: next(iter(value["after"]["components"][key]["sources"]))
                                for key in ("R", "H")}
        old = f.before["components"][axis]["sources"]
        new = value["after"]["components"][axis]["sources"]
        value["proposal"].update(pair=activation.pair(value["after"]),
            patch_sha256=activation.patch_digest(f.before, value["after"]),
            write_paths=sorted(name for name in set(old) | set(new) if old.get(name) != new.get(name)))
        self.scope(value, f)

    def test_legitimate_native_R_and_H_preview_are_read_only(self):
        for axis in ("R", "H"):
            with self.subTest(axis=axis):
                value = self.draft(axis=axis)
                result = self.preview(value)
                state = self.fixture.batch.snapshot()
                projected = activation.micro.propose_micro_evolution(state["micro_evolution"], value["proposal"])
                self.assertEqual(set(result), {"before", "projected_pending", "state_sha256"})
                self.assertEqual(result["before"], self.fixture.before)
                self.assertEqual(result["projected_pending"], projected["pending"])
                self.assertEqual(result["state_sha256"], state["state_sha256"])
                self.assertIsNone(state["micro_evolution"]["pending"])
                self.assertEqual(state["micro_evolution"]["used_candidate_ids"], [])

    def test_legitimate_literal_earnings_R_and_H_preview_are_read_only(self):
        f = self.make_fixture(earnings=True)
        for axis in ("R", "H"):
            with self.subTest(axis=axis):
                result = self.preview(self.draft(f, axis), f)
                self.assertEqual(result["before"], f.before)
                self.assertEqual(f.batch.snapshot()["micro_evolution"]["history"], [])

    def test_returned_values_cannot_mutate_stored_parent_or_pending(self):
        result = self.preview(self.draft())
        before = self.persistence()
        result["before"]["components"]["R"]["sources"].clear()
        result["projected_pending"]["pair"]["researcher_sha256"] = native_fixture.sha("changed returned copy")
        self.assertEqual(self.persistence(), before)

    def test_only_later_propose_persists_the_exact_preview(self):
        value = self.draft()
        result = self.preview(value)
        before = self.persistence()
        self.fixture.adapter.propose(**value)
        after = self.persistence()
        state = after["state"]
        self.assertNotEqual(after, before)
        self.assertEqual(state["micro_evolution"]["pending"], result["projected_pending"])
        self.assertEqual(state["micro_evolution"]["used_candidate_ids"], [value["proposal"]["candidate_id"]])
        self.assertEqual(state["micro_evolution"]["active_pair"], activation.pair(self.fixture.before))
        self.assertEqual(state["micro_evolution"]["history"], [])
        self.assertEqual(state["journal_length"], before["state"]["journal_length"] + 1)
        self.assertEqual(len(list((self.fixture.root / "versions").glob("*.json"))), 2)

    def test_invalid_native_proposal_propose_also_rejects_before_store(self):
        value = self.draft()
        value["proposal"]["parent_pair_sha256"] = native_fixture.sha("wrong parent")
        self.reject(value, method="propose")

    def test_unchanged_composite_predictor_and_memory_axes_rejected(self):
        for changed in ("unchanged", "composite", "predictor", "memory"):
            with self.subTest(changed=changed):
                value, args = self.draft(), deepcopy(self.fixture.args)
                if changed != "unchanged":
                    args["researcher"] = value["after"]["components"]["R"]
                if changed == "composite":
                    args["harness"]["configuration_sha256"] = native_fixture.sha("other H config")
                elif changed == "predictor":
                    args["researcher"] = self.fixture.args["researcher"]
                    args["predictor"]["configuration_sha256"] = native_fixture.sha("other C config")
                elif changed == "memory":
                    args["researcher"] = self.fixture.args["researcher"]
                    args["memory"] = native_fixture.sha("other memory")
                self.rebind(value, args)
                self.reject(value)

    def test_protected_kernel_model_and_runtime_identity_rejected(self):
        for changed in ("kernel", "model", "runtime"):
            with self.subTest(changed=changed):
                value, args = self.draft(), deepcopy(self.fixture.args)
                args["researcher"] = value["after"]["components"]["R"]
                if changed == "kernel":
                    args["kernel"]["configuration_sha256"] = native_fixture.sha("other kernel config")
                elif changed == "model":
                    args["model"]["requested_model"] = "different-fixture-model"
                else:
                    args["runtime"]["dependencies"] = {"fixture": {"version": "1", "sha256": native_fixture.sha("dep")}}
                self.rebind(value, args)
                self.reject(value)

    def test_wrong_axis_and_native_component_rejected(self):
        for field, wrong in (("axis", "harness"), ("axis", "unknown"), ("component", "new_provider")):
            with self.subTest(field=field, wrong=wrong):
                value = self.draft()
                value["proposal"][field] = wrong
                self.reject(value)

    def test_missing_extra_and_duplicate_file_delta_rejected(self):
        for paths in (["researcher_v2.py"], ["researcher_v1.py", "researcher_v2.py", "unapproved.py"],
                      ["researcher_v1.py", "researcher_v2.py", "researcher_v2.py"]):
            with self.subTest(paths=paths):
                value = self.draft()
                value["proposal"]["write_paths"] = paths
                self.reject(value)

    def test_wrong_pair_or_patch_hash_rejected(self):
        for field, wrong in (("pair", activation.pair(self.fixture.before)),
                             ("patch_sha256", native_fixture.sha("wrong patch")), ("patch_sha256", "0" * 64)):
            with self.subTest(field=field, wrong=wrong):
                value = self.draft()
                value["proposal"][field] = wrong
                self.reject(value)

    def test_stale_parent_and_stale_snapshot_rejected(self):
        for field in ("parent_pair_sha256", "expected_state_sha256"):
            with self.subTest(field=field):
                value = self.draft()
                target = value["proposal"] if field == "parent_pair_sha256" else value
                target[field] = native_fixture.sha("stale")
                self.reject(value)

    def test_every_fixed_context_commitment_stays_fixed(self):
        for field in self.fixture.config["fixed_context"]:
            with self.subTest(field=field):
                value = self.draft()
                value["proposal"]["fixed_context"][field] = native_fixture.sha("changed " + field)
                self.reject(value)

    def test_exact_measured_but_unapproved_new_path_rejected(self):
        value, args = self.draft(), deepcopy(self.fixture.args)
        text = "def choose(history):\n    return 'new'\n"
        (self.fixture.root / "unapproved.py").write_text(text)
        args["researcher"]["sources"] = {"unapproved.py": native_fixture.sha(text)}
        self.rebind(value, args)
        self.reject(value)

    def test_protected_and_noncanonical_manifest_paths_rejected(self):
        for path in (".git/config", "data/secret.py", "paid_budget.py", "../outside.py", "/tmp/absolute.py"):
            with self.subTest(path=path):
                value = self.draft()
                value["after"]["components"]["R"]["sources"] = {path: native_fixture.sha("fixture bytes")}
                value["after"]["R"] = digest(value["after"]["components"]["R"])
                self.reject(value)

    def test_pending_proposal_blocks_a_second_preview_before_store(self):
        first = self.draft()
        self.fixture.adapter.propose(**first)
        self.reject(self.draft(axis="H"))

    def test_used_candidate_id_stays_consumed_after_exact_reject(self):
        first = self.draft()
        self.fixture.adapter.propose(**first)
        state = self.fixture.batch.snapshot()
        pending = state["micro_evolution"]["pending"]
        rejection = {"reviewer_id": "independent-auditor", "proposal_sha256": pending["record_sha256"],
            "decision": "reject", "reason": "Synthetic native ID-history fixture; no benefit measured",
            "tested_pair_sha256": digest(pending["pair"]), "anchor_pair_sha256": digest(activation.pair(self.fixture.before)),
            "checks": {}, "benefit_observed": False, "benefit_evidence_sha256": None, "actual_write_paths": []}
        self.fixture.batch.record_micro_evolution("review", rejection, expected_state_sha256=state["state_sha256"])
        self.assertIsNone(self.fixture.batch.snapshot()["micro_evolution"]["pending"])
        self.reject(self.draft())

    def test_static_review_actor_identity_and_entrypoints_must_match(self):
        changes = ({"passed": False}, {"reviewer_id": "other-auditor"},
                   {"reviewer_id": "agent-proposer"}, {"proposer_id": "other-proposer"},
                   {"identity_sha256": native_fixture.sha("other identity")}, {"entrypoints": {}})
        for change in changes:
            with self.subTest(change=change):
                value = self.draft()
                self.scope(value, **change)
                self.reject(value)

    def test_static_review_missing_drifted_or_symlink_binding_rejected(self):
        for kind in ("missing", "drifted", "symlink"):
            with self.subTest(kind=kind):
                value = self.draft()
                original = Path(value["static_review"]["path"])
                if kind == "missing":
                    value["static_review"]["path"] = str(self.fixture.root / "missing-review.json")
                elif kind == "drifted":
                    value["static_review"]["sha256"] = native_fixture.sha("wrong review bytes")
                else:
                    alias = self.fixture.root / "scope-alias.json"
                    alias.symlink_to(original.name)
                    value["static_review"]["path"] = str(alias)
                self.reject(value)

    def test_entrypoints_are_exact_and_belong_to_reviewed_py_sources(self):
        for entries in ({"R": "researcher_v2.py"}, {"R": "researcher_v2.py", "H": "harness_v1.py", "K": "kernel.py"},
                        {"R": "harness_v1.py", "H": "harness_v1.py"}, {"R": "unreviewed.py", "H": "harness_v1.py"}):
            with self.subTest(entries=entries):
                value = self.draft()
                value["entrypoints"] = entries
                self.scope(value)
                self.reject(value)
        value, args = self.draft(), deepcopy(self.fixture.args)
        (self.fixture.root / "researcher_v2.txt").write_text(self.fixture.files["researcher_v2.py"])
        args["researcher"]["sources"] = {"researcher_v2.txt": native_fixture.sha(self.fixture.files["researcher_v2.py"])}
        self.rebind(value, args)
        self.reject(value)

    def test_all_physical_after_sources_are_checked_without_registry_write(self):
        for kind in ("missing", "source-hash", "symlink", "non-entrypoint-source"):
            with self.subTest(kind=kind):
                f = self.make_fixture()
                value = self.draft(f)
                path = f.root / "researcher_v2.py"
                if kind == "non-entrypoint-source":
                    args = deepcopy(f.args)
                    args["researcher"]["sources"]["researcher_v2.py"] = native_fixture.sha(f.files["researcher_v2.py"])
                    self.rebind(value, args, fixture=f)
                    self.assertEqual(value["entrypoints"]["R"], "researcher_v1.py")
                    path.rename(f.root / "missing-researcher.py")
                elif kind == "missing":
                    path.rename(f.root / "missing-researcher.py")
                elif kind == "source-hash":
                    path.write_text("raise AssertionError('drifted code must not execute')\n")
                else:
                    path.rename(f.root / "actual-researcher.py")
                    path.symlink_to("actual-researcher.py")
                self.reject(value, f)

    def test_preview_never_imports_or_executes_candidate_code(self):
        value, args = self.draft(), deepcopy(self.fixture.args)
        text = "raise AssertionError('preview must not execute source')\n"
        (self.fixture.root / "researcher_v2.py").write_text(text)
        args["researcher"]["sources"] = {"researcher_v2.py": native_fixture.sha(text)}
        self.rebind(value, args)
        with mock.patch.object(activation.importlib.util, "spec_from_file_location",
                               side_effect=AssertionError("preview imported candidate")) as loader:
            self.preview(value)
        loader.assert_not_called()

    def test_earnings_named_literal_override_still_rejects_before_store(self):
        f = self.make_fixture(earnings=True)
        value = self.draft(f, "H")
        value["proposal"]["component"] = "feedback_delivery"
        self.reject(value, f, method="propose")


if __name__ == "__main__":
    unittest.main()
