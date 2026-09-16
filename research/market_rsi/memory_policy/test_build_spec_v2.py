import unittest

from memory_policy.build_spec_v2 import validate_failed_report


class BuildSpecV2Tests(unittest.TestCase):
    def test_failed_candidate_must_be_score_free_and_bound(self):
        row = {"session": "2026-01-01T00", "role": "dev",
               "compressed_bytes": 10}
        report = {"complete": False, "session": row["session"],
                  "role": row["role"], "advertised_bytes": 10,
                  "failure": {"type": "ValueError"},
                  "raw_rows_exported": 0, "target_statistics_computed": 0,
                  "fits": 0, "provider_calls": 0}
        self.assertIsNone(validate_failed_report(row, report))
        report["target_statistics_computed"] = 1
        with self.assertRaises(ValueError):
            validate_failed_report(row, report)


if __name__ == "__main__":
    unittest.main()
