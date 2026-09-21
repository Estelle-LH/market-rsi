from pathlib import Path
import tempfile
import unittest

from supervisor_harness.run_p0_gate1_controller_adapter_canary import execute


class Gate1ControllerAdapterCanaryTests(unittest.TestCase):
    def test_zero_paid_canary_is_one_sample_and_plan_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gate1-controller-canary-001"
            result = execute(root)
            self.assertTrue(result["passed"])
            self.assertEqual(result["provider_calls"], 0)
            self.assertEqual(result["provider_cost_usd"], "0")
            self.assertFalse(result["public_fetch_performed"])
            self.assertFalse(result["formal_data_admitted"])

    def test_canary_output_is_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gate1-controller-canary-002"
            root.mkdir()
            with self.assertRaises(FileExistsError):
                execute(root)


if __name__ == "__main__":
    unittest.main()
