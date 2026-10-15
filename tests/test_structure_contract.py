"""Small invariants that keep the active repository layout legible."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StructureContractTests(unittest.TestCase):
    def test_active_earnings_contract_is_in_named_benchmark(self):
        self.assertTrue((ROOT / "benchmarks" / "earnings" / "README.md").is_file())

    def test_coevolution_engine_has_named_owner(self):
        self.assertTrue((ROOT / "research" / "market_rsi" / "supervisor_harness").is_dir())

    def test_legacy_market_benchmark_remains_separate(self):
        self.assertTrue((ROOT / "benchmarks" / "nfl_price" / "README.md").is_file())

    def test_structure_contract_is_present(self):
        self.assertTrue((ROOT / "docs" / "CODE_STRUCTURE_MAINTENANCE.md").is_file())


if __name__ == "__main__":
    unittest.main()
