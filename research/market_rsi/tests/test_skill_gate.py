import subprocess
import sys
import unittest
from pathlib import Path


class SkillGateTest(unittest.TestCase):
    def test_two_day_report_cannot_pass_promotion_gate(self):
        script = Path("/Users/estelle/.codex/skills/indicator-prediction-evals/scripts/validate_experiment_spec.py")
        if not script.is_file():
            self.skipTest("external skill validator not installed on this host")
        fixture = Path(__file__).parent / "fixtures/two_day_not_promotion.json"
        result = subprocess.run([sys.executable, str(script), str(fixture)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least 20 unique sessions", result.stderr)
