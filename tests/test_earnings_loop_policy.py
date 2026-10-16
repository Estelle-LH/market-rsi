"""Pure policy on synthetic artifacts; private benchmark preflight never runs."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_entry as entry
import earnings_loop_policy as policy


class LoopPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.count = 0
        for name in policy.SOURCES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic source\n")
        patches = [patch.object(entry, "ARCHIVE", self.root), patch.object(entry, "REPO", self.root),
                   patch.object(entry, "preflight", return_value=({"synthetic": True}, ["T001"], "synthetic-scorer")),
                   patch.object(entry, "FilingTools", return_value=SimpleNamespace(files={"questions.md": "public questions"})),
                   patch.object(entry, "credential"),
                   patch.object(policy.subprocess, "run", return_value=SimpleNamespace(stdout=b"synthetic source\n"))]
        self.patch_results = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.preflight, self.keys = self.patch_results[2], self.patch_results[4]
        self.base = {"source_commit": "a" * 40, "task_id": "synthetic-task", "cik": "synthetic-cik",
                     "output": str(self.root / "attempts" / "baseline"), "model": "gpt-6.1-sol",
                     "ledger": "synthetic-ledger-not-opened", "scorer": "synthetic-scorer-not-opened",
                     "runtime_config": {"effort": "xhigh", "max_turns_per_company": 24}, "baseline": {"synthetic": True},
                     "deadline_utc": entry.DEADLINE, "new_request_cutoff_utc": entry.CUTOFF,
                     "review": {"synthetic": True}, "launch_policy_sha256": "b" * 64}
        self.envelope = {"schema": "earnings_feedback_envelope_v1", "source_commit": "a" * 40,
                         "baseline_config": self.base, "root": str(self.root / "loops" / "earnings-feedback-01"),
                         "forecasts": [str(self.root / "attempts" / f"round-{i}") for i in (1, 2)],
                         "controllers": [str(self.root / "controllers" / f"round-{i}") for i in (1, 2)],
                         "max_rounds": 2, "controller_limits": {"max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600}}
        self.seal(self.envelope)

    def save(self, value):
        self.count += 1
        path = self.root / f"artifact-{self.count}.json"
        path.write_text(json.dumps(value, sort_keys=True))
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def seal(self, envelope):
        envelope["loop_policy_sha256"] = policy.policy_sha(envelope)
        envelope["review"] = self.save({"verdict": "PASS_FOR_TWO_BOUNDED_FEEDBACK_ROUNDS",
            "source_commit": envelope["source_commit"], "loop_policy_sha256": envelope["loop_policy_sha256"]})

    def child(self, index=0):
        recipe = {"schema": "earnings_research_recipe_v1", "task_id": self.base["task_id"],
                  "parent_feedback_sha256": "c" * 64, "research_instructions": "Inspect available evidence."}
        packet = {"schema": "synthetic-packet", "task_id": self.base["task_id"], "parent_feedback_sha256": "c" * 64,
                  "questions": "public questions", "feedback": {"observation": {"schema": "earnings_aggregate_feedback_v1",
                      "task_id": self.base["task_id"], "cik": self.base["cik"]}, "baseline_score_out_of_5": 1.5}, "prior_recipe": None}
        packet_path = Path(self.envelope["root"]) / f"packet-{index + 1:02d}.json"
        packet_path.parent.mkdir(parents=True, exist_ok=True)
        binding = self.save(packet)
        Path(binding["path"]).rename(packet_path)
        binding["path"] = str(packet_path)
        proposal = {"recipe": recipe, "input_packet": binding, "source_commit": self.base["source_commit"]}
        proposal_path = Path(self.envelope["controllers"][index]) / "proposal.json"
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposed = self.save(proposal)
        Path(proposed["path"]).rename(proposal_path)
        proposed["path"] = str(proposal_path)
        return dict(copy.deepcopy(self.base), output=self.envelope["forecasts"][index],
                    loop_authorization={"envelope": self.save(self.envelope)}, research_recipe=self.save(recipe),
                    parent_feedback_sha256="c" * 64, feedback_packet=binding, controller_proposal=proposed)

    def test_valid_parent_and_both_child_slots_preserve_inputs(self):
        for index in (0, 1):
            child = self.child(index)
            before = copy.deepcopy(child)
            self.assertEqual(policy.validate_child(child), ({"synthetic": True}, ["T001"], "synthetic-scorer"))
            self.assertEqual(child, before)
        self.keys.assert_not_called()
        self.assertEqual(self.preflight.call_args.kwargs, {"require_review": False})

    def test_policy_hash_excludes_only_top_level_review_and_self_hash(self):
        changed = dict(self.envelope, review={"changed": True}, loop_policy_sha256="d" * 64)
        self.assertEqual(policy.policy_sha(changed), policy.policy_sha(self.envelope))
        changed["baseline_config"] = dict(self.base, review={"changed": True})
        self.assertNotEqual(policy.policy_sha(changed), policy.policy_sha(self.envelope))

    def test_resigned_cap_shape_window_or_slot_drift_refuses_before_preflight(self):
        changes = [{"max_rounds": 3}, {"max_rounds": 2.0}, {"controller_limits": {"max_input_tokens": 10000, "max_output_tokens": 16385, "wall_seconds": 600}},
                   {"root": str(self.root / "other")}, {"forecasts": [self.envelope["forecasts"][0]] * 2},
                   {"controllers": [str(self.root / "outside" / "1"), str(self.root / "outside" / "2")]},
                   {"baseline_config": dict(self.base, deadline_utc="2099-01-01T00:00:00Z")},
                   {"baseline_config": dict(self.base, loop_authorization={})}, {"extra": True}]
        for changed in changes:
            with self.subTest(changed=changed):
                candidate = dict(self.envelope, **changed)
                self.seal(candidate)
                with self.assertRaises(ValueError):
                    policy.validate_envelope(candidate)
        self.preflight.assert_not_called()

    def test_review_policy_hash_and_source_drift_refuse_before_preflight(self):
        candidates = [dict(self.envelope, loop_policy_sha256="0" * 64),
                      dict(self.envelope, review=self.save({"verdict": "PASS_FOR_ONE_BOUNDED_FORECAST"})),
                      dict(self.envelope, review=self.save({"verdict": "PASS_FOR_TWO_BOUNDED_FEEDBACK_ROUNDS", "source_commit": "b" * 40,
                           "loop_policy_sha256": self.envelope["loop_policy_sha256"]}))]
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                policy.validate_envelope(candidate)
        (self.root / policy.SOURCES[0]).write_bytes(b"drift")
        with self.assertRaises(ValueError):
            policy.validate_envelope(self.envelope)
        self.preflight.assert_not_called()

    def test_child_protected_extra_output_and_binding_drift_refuse(self):
        child = self.child()
        changes = [{"model": "other"}, {"task_id": "other"}, {"runtime_config": {}}, {"ledger": "other"},
                   {"runtime_config": dict(self.base["runtime_config"], max_turns_per_company=24.0)},
                   {"extra": True}, {"output": str(self.root / "attempts" / "undeclared")},
                   {"parent_feedback_sha256": "d" * 64}, {"research_recipe": self.save({})}]
        for changed in changes:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                policy.validate_child(dict(child, **changed))
        self.keys.assert_not_called()

    def test_packet_question_task_proposal_and_recipe_mismatch_refuse(self):
        for which in ("questions", "packet_task", "packet_cik", "audit_score", "proposal_packet", "proposal_recipe", "proposal_source"):
            child = self.child()
            key = "feedback_packet" if which in ("questions", "packet_task", "packet_cik", "audit_score") else "controller_proposal"
            path = Path(child[key]["path"])
            value = json.loads(path.read_text())
            if which == "questions": value["questions"] = "different"
            elif which == "packet_task": value["task_id"] = "different"
            elif which == "packet_cik": value["feedback"]["observation"]["cik"] = "different"
            elif which == "audit_score": value["feedback"]["baseline_score_out_of_5"] = 6
            elif which == "proposal_packet": value["input_packet"] = {"path": "different", "sha256": "c" * 64}
            elif which == "proposal_recipe": value["recipe"]["research_instructions"] = "different"
            else: value["source_commit"] = "b" * 40
            path.write_text(json.dumps(value))
            child[key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.subTest(which=which), self.assertRaises(ValueError):
                policy.validate_child(child)
        self.keys.assert_not_called()

    def test_wrong_role_leaf_is_refused_before_that_file_is_read(self):
        child = self.child()
        foreign = self.save({"synthetic": "outside the declared packet slot"})
        child["feedback_packet"] = foreign
        with patch.object(entry, "checked", wraps=entry.checked) as checked:
            with self.assertRaisesRegex(ValueError, "declared role slot"):
                policy.validate_child(child)
            self.assertNotIn(foreign, [c.args[0] for c in checked.call_args_list])

    def test_duplicate_or_symlinked_parent_review_refuses_before_preflight(self):
        envelope = copy.deepcopy(self.envelope)
        binding = envelope["review"]
        path = Path(binding["path"])
        original = path.read_bytes()
        path.write_bytes(original.replace(b'{', b'{"verdict":"wrong",', 1))
        binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            policy.validate_envelope(envelope)
        path.write_bytes(original)
        link = self.root / "review-link.json"
        link.symlink_to(path)
        envelope["review"] = dict(self.envelope["review"], path=str(link))
        with self.assertRaises(ValueError):
            policy.validate_envelope(envelope)
        self.preflight.assert_not_called()


if __name__ == "__main__":
    unittest.main()
