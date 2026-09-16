import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data_science_tools import pipeline as p


def spec():
    value = {"schema": p.SCHEMA, "scope_id": "fixture-only", "bindings": {k: "a" * 64 for k in p.BINDINGS},
             "controls": dict(p.CONTROLS), "controller_owns": ["source", "sampling", "features", "objective", "model"],
             "pipeline_policy_sha256": p.policy_sha256()}
    value["spec_sha256"] = p.digest(value)
    return value


def checks(s, ref):
    return [{"check_id": c, "status": "pass", "scope_id": s["scope_id"],
             "bindings": {k: s["bindings"][k] for k in stage[2]},
             "reason": "Synthetic test receipt, not a market-data acceptance.",
             "evidence_refs": [ref], "reviewer_role": "trusted_runner_review"}
            for stage in p.STAGES for c in stage[3]]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.s = spec()
        self.ref = self.write("evidence.json", {"fixture": True})
        self.checks = checks(self.s, self.ref)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        raw = (json.dumps(value) + "\n").encode()
        path = self.root / name
        path.write_bytes(raw)
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

    def saved(self):
        s = self.write("spec.json", self.s)
        r = self.write("checks.json", self.checks)
        return dict(spec_path=s["path"], spec_sha256=s["sha256"], review_path=r["path"], review_sha256=r["sha256"])

    def test_every_question_required_and_unknown_is_not_pass(self):
        result = p.evaluate(self.s, [])
        self.assertFalse(result["data_science_ready"])
        self.assertEqual(len(result["blockers"]), len(p.CHECK_STAGE))
        for check in self.checks:
            altered = copy.deepcopy(self.checks)
            next(c for c in altered if c["check_id"] == check["check_id"])["status"] = "unknown"
            self.assertFalse(p.evaluate(self.s, altered)["data_science_ready"])

    def test_success_does_not_grant_execution_or_open_labels(self):
        result = p.require_data_science_ready(**self.saved())
        self.assertTrue(result["data_science_ready"])
        self.assertFalse(result["execution_admitted"])
        self.assertFalse(result["new_labels_accessed"])

    def test_upstream_failure_blocks_completed_downstream(self):
        self.checks[3]["status"] = "fail"
        result = p.evaluate(self.s, self.checks)
        self.assertEqual(result["stages"][1]["status"], "failed")
        self.assertEqual(result["stages"][-1]["status"], "waiting_upstream")

    def test_changed_source_or_target_invalidates_old_review(self):
        for component in ("source_plan", "objective_contract", "feature_contract", "split_contract"):
            modified = copy.deepcopy(self.s)
            modified["bindings"][component] = "b" * 64
            modified["spec_sha256"] = p.digest({k: v for k, v in modified.items() if k != "spec_sha256"})
            with self.assertRaisesRegex(ValueError, "stale review"):
                p.evaluate(modified, self.checks)

    def test_unfrozen_cannot_pass_controller_cannot_approve(self):
        self.checks[0]["reviewer_role"] = "controller"
        with self.assertRaisesRegex(ValueError, "self-certification"):
            p.evaluate(self.s, self.checks)
        self.checks[0]["reviewer_role"] = "trusted_runner_review"
        self.s["bindings"]["raw_manifest"] = None
        self.s["spec_sha256"] = p.digest({k: v for k, v in self.s.items() if k != "spec_sha256"})
        self.checks = checks(self.s, self.ref)
        with self.assertRaisesRegex(ValueError, "before component"):
            p.evaluate(self.s, self.checks)

    def test_evidence_change_missing_and_symlink_rejected(self):
        args = self.saved()
        Path(self.ref["path"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            p.require_data_science_ready(**args)
        Path(self.ref["path"]).unlink()
        with self.assertRaises(OSError):
            p.require_data_science_ready(**args)
        Path(self.ref["path"]).symlink_to(args["spec_path"])
        with self.assertRaisesRegex(ValueError, "canonical"):
            p.require_data_science_ready(**args)

    def test_failed_data_gate_never_calls_later_validation(self):
        self.checks[3]["status"] = "fail"
        args = self.saved()
        with patch("validation_tools.independent_validation.check_runner_evidence") as later:
            with self.assertRaisesRegex(RuntimeError, "data-science preflight blocked"):
                p.check_independent_validation_after_data_science(**args, proposal={}, context={}, runner={}, budget={})
            later.assert_not_called()

    def test_pass_does_not_bypass_legacy_validation(self):
        args = self.saved()
        with patch("validation_tools.independent_validation.check_runner_evidence",
                   return_value={"metadata_gate_passed": False, "execution_admitted": False}) as later:
            result = p.check_independent_validation_after_data_science(**args, proposal={},
                context={"objective_sha256": "a" * 64, "source_contract_sha256": "a" * 64},
                runner={"raw_manifest_sha256": "a" * 64, "data_science_spec_sha256": self.s["spec_sha256"]}, budget={})
            later.assert_called_once()
            self.assertFalse(result["metadata_gate_passed"])

    def test_another_dataset_cannot_reuse_a_passing_review(self):
        args = self.saved()
        with patch("validation_tools.independent_validation.check_runner_evidence") as later:
            with self.assertRaisesRegex(ValueError, "experiment differs"):
                p.check_independent_validation_after_data_science(**args, proposal={},
                    context={"objective_sha256": "a" * 64, "source_contract_sha256": "a" * 64},
                    runner={"raw_manifest_sha256": "b" * 64, "data_science_spec_sha256": self.s["spec_sha256"]}, budget={})
            later.assert_not_called()

    def test_objective_is_frozen_before_target_dependent_feature_review(self):
        order = [stage[0] for stage in p.STAGES]
        self.assertLess(order.index("objective"), order.index("features"))
        self.assertIn("objective_contract", p.CHECK_STAGE["raw_signal_and_redundancy_measured"][2])

    def test_old_pipeline_policy_cannot_be_relabelled_ready(self):
        self.s["pipeline_policy_sha256"] = "b" * 64
        self.s["spec_sha256"] = p.digest({k: v for k, v in self.s.items() if k != "spec_sha256"})
        with self.assertRaisesRegex(ValueError, "pipeline rules"):
            p.evaluate(self.s, self.checks)

    def test_safety_controls_cannot_be_relaxed(self):
        self.s["controls"]["future_movement_filters_eval"] = True
        self.s["spec_sha256"] = p.digest({k: v for k, v in self.s.items() if k != "spec_sha256"})
        with self.assertRaisesRegex(ValueError, "safety controls"):
            p.evaluate(self.s, self.checks)


if __name__ == "__main__":
    unittest.main()
