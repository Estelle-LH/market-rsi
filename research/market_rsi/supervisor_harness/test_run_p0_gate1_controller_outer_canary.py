from pathlib import Path
import tempfile
import unittest

from supervisor_harness.run_p0_gate1_controller_outer_canary import execute


class Gate1ControllerOuterCanaryTests(unittest.TestCase):
    def test_synthetic_transaction_is_explicit_and_zero_provider_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "gate1-outer-canary-001"
            with self.assertRaisesRegex(ValueError, "prior current-source"):
                execute(output)
            self.assertFalse(output.exists())

    def test_novel_proposal_is_archived_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "gate1-proposal-canary-001"
            with self.assertRaisesRegex(ValueError, "not a D0 canary"):
                execute(output, proposal=True)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
