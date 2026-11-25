import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("edgar_audit", Path(__file__).parents[1] / "tools/edgar_forecast_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditHelpersTest(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(str(audit.remap("sec_parser/edgar_forecast_bench_runs/a/b")), "runs/a/b")

    def test_path_guard(self):
        for path in ["/tmp/test", "sec_parser/edgar_forecast_bench_runs/../test"]:
            with self.assertRaises(ValueError):
                audit.remap(path)

    def test_git_blob(self):
        self.assertEqual(audit.git_blob(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")


if __name__ == "__main__":
    unittest.main()
