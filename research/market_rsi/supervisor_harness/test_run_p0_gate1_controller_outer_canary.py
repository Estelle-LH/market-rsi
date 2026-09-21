from pathlib import Path
import tempfile
import unittest

from supervisor_harness.run_p0_gate1_controller_outer_canary import execute


class Gate1ControllerOuterCanaryTests(unittest.TestCase):
    def test_synthetic_transaction_is_explicit_and_zero_provider_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "gate1-outer-canary-001"
            result = execute(output)
            self.assertTrue(result["passed"])
            self.assertEqual(result["provider_calls"], 0)
            self.assertEqual(result["actual_provider_cost_usd"], "0")
            self.assertTrue(result["synthetic_publication_substituted"])
            self.assertFalse(result["public_fetch_performed"])
            self.assertFalse(result["formal_data_admitted"])


if __name__ == "__main__":
    unittest.main()
