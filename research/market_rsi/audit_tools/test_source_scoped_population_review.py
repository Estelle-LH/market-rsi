from pathlib import Path
import tempfile
import unittest
from market_rsi import fresh_json, file_hash, load_json
from source_scoped_population_review import diagnostic_manifest, review_values, verify_current_quality, RAW_SHA


class SourceScopedReviewTests(unittest.TestCase):
    def fixture(self, root):
        root = Path(root).resolve()
        fresh_json(root/"audit.json", {"source_admitted": False})
        spec, checks = review_values("current-d10", "a"*64,
            {"path": str(root/"audit.json"), "sha256": file_hash(root/"audit.json")})
        fresh_json(root/"spec.json", spec); fresh_json(root/"checks.json", checks)
        return {"spec_path": str(root/"spec.json"), "spec_sha256": file_hash(root/"spec.json"),
                "review_path": str(root/"checks.json"), "review_sha256": file_hash(root/"checks.json")}

    def test_current_unknown_never_admits(self):
        with tempfile.TemporaryDirectory() as temp:
            report = verify_current_quality(self.fixture(temp), expected_scope="current-d10", expected_raw_manifest_sha="a"*64)
            self.assertFalse(report["data_science_ready"])
            self.assertFalse(report["execution_admitted"])
            self.assertTrue(all(s["status"] == "incomplete" for s in report["stages"]))
            self.assertIsNone(report["component_bindings"]["source_plan"])

    def test_other_scope_rejected_even_if_internally_consistent(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "different source/scope"):
                verify_current_quality(self.fixture(temp), expected_scope="old-vantage", expected_raw_manifest_sha="a"*64)

    def test_other_manifest_rejected_same_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "different source/scope"):
                verify_current_quality(self.fixture(temp), expected_scope="current-d10", expected_raw_manifest_sha="b"*64)

    def test_changed_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            quality = self.fixture(temp)
            (Path(temp)/"audit.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "changed"):
                verify_current_quality(quality, expected_scope="current-d10", expected_raw_manifest_sha="a"*64)

    def test_scientific_contract_not_invented(self):
        spec, _ = review_values("scope", "a"*64, {"path": "/fixture", "sha256": "b"*64})
        self.assertEqual([k for k, v in spec["bindings"].items() if v is not None], ["raw_manifest"])

    def test_pilot_and_wrong_source_rejected(self):
        report = {"mode": "hour", "full_hour_decoded": True, "source_sha256": RAW_SHA,
                  "source_bytes": 331091663, "raw_records": 4328805, "source_admitted": False,
                  "decoded_sha256": "b"*64}
        manifest = diagnostic_manifest(report)
        self.assertFalse(manifest["controller_training_plan"])
        self.assertFalse(manifest["complete_sessions_proven"])
        for update in ({"mode": "pilot"}, {"source_sha256": "b"*64}, {"full_hour_decoded": False}):
            with self.assertRaisesRegex(ValueError, "exact D10 hour"):
                diagnostic_manifest({**report, **update})


if __name__ == "__main__": unittest.main()
