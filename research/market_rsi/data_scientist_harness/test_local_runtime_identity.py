"""The paid provider stack must be frozen with the same local runtime as the canary."""

import unittest
import sys
from pathlib import Path

from data_scientist_harness.store import runtime_identity
from data_scientist_harness.io_preflight import require_local_execution


class LocalRuntimeIdentityTest(unittest.TestCase):
    def test_provider_and_cpu_packages_are_bound(self):
        identity = runtime_identity()
        self.assertEqual(len(identity["installed_distributions_sha256"]), 64)
        self.assertTrue({
            "numpy", "scipy", "scikit-learn", "threadpoolctl", "joblib",
            "tinker", "transformers", "tokenizers", "huggingface-hub",
            "httpx", "python-dotenv",
        }.issubset(identity["packages"]))
        self.assertEqual(identity["environment_prefix"], str(Path(sys.prefix).resolve()))

    def test_paid_execution_rejects_icloud_workspace(self):
        with self.assertRaisesRegex(ValueError, "local-only MarketRSI"):
            require_local_execution((Path.home() / "Documents" / "ChatGPT" / "self-evolving",))

    def test_local_execution_tree_is_accepted(self):
        anchor = Path.home() / "Library" / "Application Support" / "MarketRSI"
        self.assertEqual(require_local_execution((anchor / "repo", anchor / "runtime"))["checked_paths"], 2)


if __name__ == "__main__":
    unittest.main()
