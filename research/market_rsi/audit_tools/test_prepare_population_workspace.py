from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from market_rsi import fresh_json, file_hash, load_json
from source_scoped_population_review import review_values
import prepare_population_workspace as subject


class PreparationTests(unittest.TestCase):
    def test_preparation_uses_current_quality_not_parent_pointer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); parent = root/"parent"; parent.mkdir()
            (parent/"session").mkdir()
            fresh_json(parent/"workspace.json", {"files": {}, "quality": {"stale": "vantage"}})
            fresh_json(parent/"session/assessment.json", {"valid": True, "process_reaped": True})
            fresh_json(parent/"round-archive.json", {"archived": True})
            fresh_json(root/"audit.json", {"source_admitted": False})
            fresh_json(root/"report.json", {"profile": {"totals": {"issues": {"source_ms_regression": 3}}, "message_kinds": {"book": 4}}})
            ref = {"path": str(root/"audit.json"), "sha256": file_hash(root/"audit.json")}
            spec, checks = review_values("d10", "a"*64, ref)
            fresh_json(root/"spec.json", spec); fresh_json(root/"checks.json", checks)
            quality = {"spec_path": str(root/"spec.json"), "spec_sha256": file_hash(root/"spec.json"),
                "review_path": str(root/"checks.json"), "review_sha256": file_hash(root/"checks.json")}
            bundle = {"quality": quality, "scope_id": "d10", "source_id": "d10_polymarket_raw",
                "raw_manifest": {"sha256": "a"*64}, "audit": ref, "historical_source_review": {},
                "report": {"path": str(root/"report.json"), "sha256": file_hash(root/"report.json")}}
            def create(output, **kwargs):
                self.assertEqual(kwargs["quality"], quality)
                self.assertNotIn("data_root", kwargs)
                self.assertEqual(kwargs["purpose"], "source_research")
                self.assertEqual(kwargs["findings"][0]["aggregate_event_counts"]["issues"]["source_ms_regression"], 3)
                output.mkdir(); fresh_json(output/"workspace.json", {"quality": kwargs["quality"]})
                return file_hash(output/"workspace.json")
            with patch.object(subject, "PARENT", parent), \
                    patch.object(subject, "PARENT_SHA", file_hash(parent/"workspace.json")), \
                    patch.object(subject, "read_bundle", return_value=bundle), \
                    patch.object(subject, "inspect", return_value={"provider_calls": 0}), \
                    patch.object(subject, "PaidBudget") as budget, patch.object(subject, "create", side_effect=create):
                budget.return_value.snapshot.return_value = {"jobs": {}}
                receipt = subject.prepare(root/"new", root/"bundle", "b"*64, root/"release")
            self.assertTrue(receipt["prepared_not_dispatched"])
            self.assertEqual(receipt["provider_calls"], 0)
            self.assertEqual(load_json(parent/"workspace.json")["quality"], {"stale": "vantage"})

    def test_bad_bundle_stops_before_workspace_or_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(subject, "read_bundle", side_effect=ValueError("wrong source")), \
                    patch.object(subject, "create") as create, patch.object(subject, "inspect") as inspect:
                with self.assertRaisesRegex(ValueError, "wrong source"):
                    subject.prepare(Path(temp)/"new", Path(temp)/"bundle", "a"*64, Path(temp)/"release")
                create.assert_not_called(); inspect.assert_not_called()

    def test_existing_id_rejected_before_read_or_create(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(subject, "read_bundle") as bundle, patch.object(subject, "create") as create:
                with self.assertRaisesRegex(ValueError, "fresh workspace"):
                    subject.prepare(Path(temp), Path(temp)/"bundle", "a"*64, Path(temp)/"release")
                bundle.assert_not_called(); create.assert_not_called()


if __name__ == "__main__": unittest.main()
