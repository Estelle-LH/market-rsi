import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import datetime as dt

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
spec = importlib.util.spec_from_file_location("edgar_model_pilot", Path(__file__).parents[1] / "tools/edgar_forecast_model_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class ModelPilotTest(unittest.TestCase):
    def test_matrix_and_missing_scores(self):
        models = pilot.matrix_rows(json.loads(pilot.MATRIX.read_text()))
        self.assertEqual(len(models), 21)
        rows = pilot.pending_scoreboard(models, 15)
        self.assertTrue(all(r["fresh_score_percent"] is None and r["attempted_companies"] == 0 for r in rows))
        self.assertEqual({m["published_artifact"] for m in models if m["group"] == "paper"},
                         {"gpt-5.5", "gpt-5.4", "gemini-3.1-pro-preview", "anthropic/claude-opus-4.7"})

    def test_selection_is_not_input_order(self):
        self.assertEqual([r["cik"] for r in pilot.select_instances([{"cik": str(i)} for i in [4, 2, 1, 3]], 3)], ["1", "2", "3"])
        with self.assertRaises(ValueError):
            pilot.select_instances([{"cik": "1"}] * 3, 3)

    def test_filing_boundary(self):
        row = {"relative_path": "filings/10-Q_2026-01-01_abc.md", "accession": "abc", "date_filed": "2026-01-01"}
        self.assertEqual(pilot.eligible([row], "hidden", dt.date(2026, 2, 1)), [row])
        for edited in [dict(row, accession="hidden"), dict(row, date_filed="2026-02-02"), dict(row, relative_path="../answers.json")]:
            with self.subTest(edited=edited), self.assertRaises(ValueError):
                pilot.eligible([edited], "hidden", dt.date(2026, 2, 1))
        with self.assertRaises(ValueError):
            pilot.eligible([row, row], "hidden", dt.date(2026, 2, 1))

    def test_unsafe_or_symlinked_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "real").write_text("x")
            (root / "link").symlink_to(root / "real")
            self.assertEqual(pilot.safe_file(root, "real"), root.resolve() / "real")
            for path in ["../real", "/etc/hosts", "link", "missing"]:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    pilot.safe_file(root, path)

    def test_single_numeric_diagnostic(self):
        for value in [0, -10.1, "-12.34", "1e6"]:
            self.assertFalse(pilot.strict_single_number({"predictions": [{"target_id": "T001", "predicted_value": value}]}, ["T001"]))
        for value in [True, None, "0 or 100", "100 million", "NaN", float("inf")]:
            self.assertTrue(pilot.strict_single_number({"predictions": [{"target_id": "T001", "predicted_value": value}]}, ["T001"]))
        self.assertTrue(pilot.strict_single_number({"predictions": []}, ["T001"]))
        self.assertTrue(pilot.strict_single_number({"predictions": [{"target_id": "T001", "predicted_value": 1}] * 2}, ["T001"]))

    def test_stage_is_hash_checked_and_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.write_bytes(b"original")
            with self.assertRaises(ValueError):
                pilot.stage_file(source, root / "wrong", "bad")
            self.assertFalse((root / "wrong").exists())
            receipt = pilot.stage_file(source, root / "staged", pilot.digest(b"original"))
            self.assertEqual(receipt["bytes"], 8)
            with self.assertRaises(FileExistsError):
                pilot.stage_file(source, root / "staged", pilot.digest(b"original"))


if __name__ == "__main__":
    unittest.main()
