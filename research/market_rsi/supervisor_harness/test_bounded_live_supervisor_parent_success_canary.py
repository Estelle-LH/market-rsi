import json
from pathlib import Path
import tempfile
import unittest

from market_rsi import fresh_json
from supervisor_harness import run_bounded_live_supervisor_parent_success_canary as canary


class SupervisorParentSuccessCanaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_wait_for_claim_requires_bound_cycle(self):
        claim = self.root / "claim.json"
        fresh_json(claim, {
            "cycle_id": "another-cycle", "task_id": "another-cycle",
            "automatic_retry": False,
        })
        with self.assertRaisesRegex(ValueError, "does not bind"):
            canary._wait_for_claim(claim, "expected-cycle", seconds=.01)

    def test_wait_for_claim_accepts_exact_nonretry_claim(self):
        claim = self.root / "claim.json"
        value = {
            "cycle_id": "expected-cycle", "task_id": "expected-cycle",
            "automatic_retry": False, "watchdog_head_sha256": "a" * 64,
        }
        fresh_json(claim, value)
        self.assertEqual(
            canary._wait_for_claim(claim, "expected-cycle", seconds=.01),
            value)

    def test_child_result_schema_is_strict_json(self):
        self.assertEqual(
            json.loads(json.dumps({"schema": canary.CHILD_RESULT_SCHEMA}))[
                "schema"], canary.CHILD_RESULT_SCHEMA)


if __name__ == "__main__":
    unittest.main()
