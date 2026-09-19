import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from supervisor_harness.bottleneck_gate import check_plan, check_state, check_step_ready


def example() -> dict:
    return {
        "schema": "supervisor_bottleneck_plan_v1", "id": "p0-example-01",
        "symptom": "The data source cannot be admitted for formal evaluation.",
        "source_evidence": "read-only inspection of source manifest",
        "objective": "Establish admissible data or an explicit block.",
        "boundary": "No held-out labels or paid run.",
        "resolution_check": "Independent admission check passes on exact dataset hash.",
        "supervisor_owner": "outer supervisor",
        "steps": [{
            "id": "inventory", "owner": "data researcher",
            "action": "Inspect source rights and date coverage.", "depends_on": [],
            "expected_artifact": "inventory.json", "verification": "Check rights and dates against source.",
            "pass_condition": "Rights and three seasons demonstrated.",
            "failure_action": "Stop this data route and record cause.", "time_bound_minutes": 30,
        }],
    }


class BottleneckGateTest(unittest.TestCase):
    def test_dispatch_requires_verifiable_plan(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan = example()
            path.write_text(json.dumps(plan))
            self.assertTrue(check_plan(path, phase="dispatch")["passed"])
            del plan["steps"][0]["owner"]
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "owner"):
                check_plan(path, phase="dispatch")

    def test_resolution_requires_evidence_and_whole_check(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan = example()
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "verification result"):
                check_plan(path, phase="resolve")
            evidence = Path(directory) / "inventory.json"
            evidence.write_text('{"source":"public"}')
            plan["steps"][0]["result"] = {
                "verdict": "pass", "observed": "Rights and coverage checked.",
                "reviewer": "outer supervisor", "evidence_path": "inventory.json",
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            }
            plan["resolution"] = {"verdict": "pass", "observed": "Data admitted.",
                                  "reviewer": "independent evaluator"}
            path.write_text(json.dumps(plan))
            self.assertTrue(check_plan(path, phase="resolve")["passed"])
            evidence.write_text("mutated")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                check_plan(path, phase="resolve")

    def test_dependency_cycle_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan = example()
            plan["steps"][0]["depends_on"] = ["second"]
            second = dict(plan["steps"][0], id="second", depends_on=["inventory"])
            plan["steps"].append(second)
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "cyclic"):
                check_plan(path, phase="dispatch")

    def test_state_requires_visible_plan_and_evidence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.json").write_text("{}")
            (root / "receipt.json").write_text("{}")
            state = {"schema": "market_supervisor_bottleneck_state_v1", "active": [
                {"id": "p0", "status": "blocked", "plan": "plan.json",
                 "result": "missing rights", "next": "check rights", "evidence": "receipt.json"}]}
            path = root / "state.json"
            path.write_text(json.dumps(state))
            self.assertEqual(check_state(path, repo_root=root)["active"], 1)
            state["active"][0]["evidence"] = "missing.json"
            path.write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, "missing or outside evidence"):
                check_state(path, repo_root=root)

    def test_ready_step_rejects_external_gate_and_failed_dependency(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "plan.json"
            plan = example()
            second = dict(plan["steps"][0], id="second", depends_on=["inventory"])
            plan["steps"].append(second)
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "dependency inventory not passed"):
                check_step_ready(path, step_id="second")
            plan["steps"][1]["external_blockers"] = ["live-model-gate"]
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "live-model-gate"):
                check_step_ready(path, step_id="second")
            plan["steps"][1]["external_blockers"] = []
            evidence = root / "receipt.json"
            evidence.write_text("pass")
            plan["steps"][0]["result"] = {
                "verdict": "pass", "evidence_path": "receipt.json",
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "result.observed"):
                check_step_ready(path, step_id="second")
            plan["steps"][0]["result"].update(
                observed="Independent source/rights check passed.",
                reviewer="outer supervisor")
            path.write_text(json.dumps(plan))
            self.assertTrue(check_step_ready(path, step_id="second")["ready"])


if __name__ == "__main__":
    unittest.main()
