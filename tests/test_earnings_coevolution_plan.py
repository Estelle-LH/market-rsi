"""Synthetic plan/checker tests, not tests of an implemented co-evolving agent."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(REPO / "tools"), *sys.path]):
    import check_earnings_coevolution_plan as checker


class PlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / "plan.json"
        self.plan = deepcopy(json.loads(checker.DEFAULT_PLAN.read_text()))
        # These fixtures must remain valid when real progress receipts are added.
        for step in self.plan["steps"]:
            step["result"] = None
        self.plan["resolution"] = None

    def save(self):
        self.path.write_text(json.dumps(self.plan))

    def record(self, index, verdict="pass"):
        evidence = self.root / f"fixture-{index}.json"
        evidence.write_text(json.dumps({"fixture": True, "not_scientific_evidence": True}))
        self.plan["steps"][index]["result"] = {"verdict": verdict, "observed": "Synthetic checker fixture only",
            "reviewer": "Fixture verifier", "evidence_path": evidence.name,
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
        return evidence

    def test_real_plan_is_structurally_valid_without_granting_execution(self):
        result = checker.summarize()
        self.assertTrue(result["structure_valid"])
        self.assertFalse(result["launch_permission"])
        self.assertFalse(result["scientific_quality_verified"])
        self.assertGreater(len(result["steps"]), 0)

    def test_four_arms_caps_and_old_episode_boundaries_are_explicit(self):
        self.assertEqual([(a["evolve_R"], a["evolve_H"]) for a in self.plan["experiment"]["arms"]],
                         [(False, False), (True, False), (False, True), (True, True)])
        self.assertEqual(self.plan["current_authority"]["original_total_api_cap_usd"], 200)
        self.assertFalse(self.plan["current_authority"]["live_launch_authorized"])
        self.assertTrue(self.plan["current_authority"]["prior_overnight_closed"])
        self.assertEqual(self.plan["experiment"]["pilot_evaluation_forecasts"], 24)

    def test_pending_dependency_prevents_work_dispatch(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "dependency P0"):
            checker.gate.check_step_ready(self.path, step_id="P1")

    def test_intact_receipt_unblocks_only_dependent_local_work(self):
        self.record(0)
        self.save()
        result = checker.summarize(self.path)
        self.assertEqual(result["next_ready"], ["P1"])
        self.assertFalse(result["launch_permission"])
        self.assertEqual(result["steps"][0]["status"], "PASS_RECORDED")

    def test_missing_receipt_never_becomes_a_recorded_pass(self):
        evidence = self.record(0)
        evidence.unlink()
        self.save()
        with self.assertRaises(OSError):
            checker.summarize(self.path)

    def test_changed_receipt_is_rejected(self):
        evidence = self.record(0)
        evidence.write_text("changed")
        self.save()
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            checker.summarize(self.path)

    def test_outside_evidence_path_is_rejected(self):
        self.record(0)
        self.plan["steps"][0]["result"]["evidence_path"] = str(self.root / "fixture-0.json")
        self.save()
        with self.assertRaisesRegex(ValueError, "plan-relative"):
            checker.summarize(self.path)

    def test_recorded_pass_cannot_skip_dependencies(self):
        self.record(1)
        self.save()
        with self.assertRaisesRegex(ValueError, "contradicts unresolved"):
            checker.summarize(self.path)

    def test_external_authority_gate_cannot_be_marked_pass_without_resolution(self):
        self.plan["steps"][6]["external_blockers"] = ["Fixture missing authority"]
        for index in range(7):
            self.record(index)
        self.save()
        with self.assertRaisesRegex(ValueError, "contradicts unresolved"):
            checker.summarize(self.path)

    def test_failure_is_preserved_and_does_not_unblock_next_step(self):
        self.record(0, "fail")
        self.save()
        before = self.path.read_bytes()
        result = checker.summarize(self.path)
        self.assertEqual(result["steps"][0]["status"], "FAIL_RECORDED")
        self.assertEqual(result["next_ready"], [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_cycle_is_rejected(self):
        self.plan["steps"][0]["depends_on"] = ["P1"]
        self.save()
        with self.assertRaisesRegex(ValueError, "cyclic"):
            checker.summarize(self.path)

    def test_status_command_works_from_another_directory_without_writes(self):
        before = checker.DEFAULT_PLAN.read_bytes()
        self.save()
        run = subprocess.run([sys.executable, "-B", str(REPO / "tools/check_earnings_coevolution_plan.py"),
                              "--plan", str(self.path), "--json"],
                             cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["next_ready"], ["P0"])
        self.assertEqual(checker.DEFAULT_PLAN.read_bytes(), before)

    def test_early_resolution_and_live_step_readiness_fail_cleanly(self):
        self.save()
        for mode in (["--resolve"], ["--ready-step", "P6"]):
            run = subprocess.run([sys.executable, "-B", str(REPO / "tools/check_earnings_coevolution_plan.py"),
                                  "--plan", str(self.path), *mode],
                                 cwd=self.root, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(json.loads(run.stdout)["launch_permission"])

    def test_missing_reviewer_does_not_make_a_passing_receipt(self):
        self.record(0)
        self.plan["steps"][0]["result"]["reviewer"] = ""
        self.save()
        with self.assertRaisesRegex(ValueError, "missing reviewer"):
            checker.summarize(self.path)

    def completed_fixture(self, reviewer):
        for index, step in enumerate(self.plan["steps"]):
            step["external_blockers"] = []
            self.record(index)
        self.plan["resolution"] = {"verdict": "pass", "observed": "Fixture work records, not research",
                                   "reviewer": reviewer}
        self.save()

    def test_completed_work_records_do_not_assert_learning_or_launch_rights(self):
        self.completed_fixture("Independent fixture reviewer")
        run = subprocess.run([sys.executable, "-B", str(REPO / "tools/check_earnings_coevolution_plan.py"),
                              "--plan", str(self.path), "--resolve", "--json"], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["recorded_passes"], len(self.plan["steps"]))
        self.assertFalse(result["scientific_quality_verified"])
        self.assertFalse(result["launch_permission"])

    def test_whole_work_resolution_requires_a_distinct_recorded_reviewer(self):
        self.completed_fixture(self.plan["supervisor_owner"])
        run = subprocess.run([sys.executable, "-B", str(REPO / "tools/check_earnings_coevolution_plan.py"),
                              "--plan", str(self.path), "--resolve"], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 2)
        self.assertIn("independent", json.loads(run.stdout)["reason"])


if __name__ == "__main__":
    unittest.main()
