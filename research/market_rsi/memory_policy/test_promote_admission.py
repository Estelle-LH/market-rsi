from pathlib import Path
import tempfile
import unittest

from market_rsi import file_hash, fresh_json
from memory_policy.promote_admission import build_value
from memory_policy.test_spec_v2 import valid_spec
from memory_policy.test_study_v2 import report


class PromoteAdmissionTests(unittest.TestCase):
    def test_existing_full_pass_receipts_bind_without_raw_reread(self):
        spec = valid_spec()
        selected = {role: spec[role]
                    for role in ("initial_train", "dev", "final")}
        reports = [report(row, role)
                   for role in ("initial_train", "dev", "final")
                   for row in spec[role]]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fresh_json(root / "complete.json", {"selected_manifest": selected})
            spec["candidate_admission"]["artifact_sha256"] = file_hash(
                root / "complete.json")
            spec_path = root / "spec.json"
            fresh_json(spec_path, spec)
            value = build_value(spec_path, spec, root,
                                {"selected_manifest": selected}, reports)
            self.assertEqual(value["raw_source_rereads_for_promotion"], 0)
            self.assertEqual(len(value["reports"]), 31)
            reports[0]["session"] = "2025-01-01T00"
            with self.assertRaises(ValueError):
                build_value(spec_path, spec, root,
                            {"selected_manifest": selected}, reports)


if __name__ == "__main__":
    unittest.main()
