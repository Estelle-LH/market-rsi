import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from edgar_forecast_model_pilot import digest  # noqa: E402
from edgar_forecast_tools import FilingTools  # noqa: E402


class FilingToolsTest(unittest.TestCase):
    def _receipt(self, root, name):
        data = (root / name).read_bytes()
        return {"path": name, "bytes": len(data), "sha256": digest(data)}

    def _company(self, root, *, date="2026-01-15", accession="visible-accession"):
        (root / "filings").mkdir(parents=True)
        (root / "questions.md").write_text("Forecast T001 through T005.\n", encoding="utf-8")
        filing = "filings/10-Q_2026-01-15_visible-accession.md"
        (root / filing).write_text("Revenue was 123 and operating income was 45.\n", encoding="utf-8")
        (root / "filing_index.tsv").write_text(
            "date_filed\tform_type\taccession\tpath\n"
            f"{date}\t10-Q\t{accession}\t{filing}\n",
            encoding="utf-8",
        )
        names = ["questions.md", "filing_index.tsv", filing]
        return {
            "visible_root": str(root),
            "target_accession": "hidden-target-accession",
            "cutoff": "2026-02-01",
            "allowed_files": [self._receipt(root, name) for name in names],
        }

    @staticmethod
    def _refresh_receipt(company, root, name):
        data = (root / name).read_bytes()
        for receipt in company["allowed_files"]:
            if receipt["path"] == name:
                receipt.update(bytes=len(data), sha256=digest(data))
                return
        company["allowed_files"].append({"path": name, "bytes": len(data), "sha256": digest(data)})

    def test_reads_searches_and_calculates_only_allowed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            company = self._company(Path(directory))
            tools = FilingTools(company)

            read = tools.dispatch("read_file", {"path": "questions.md", "offset": 0, "characters": 8})
            self.assertEqual(read["text"], "Forecast")
            self.assertEqual(read["next_offset"], 8)
            search = tools.dispatch(
                "search_files", {"query": "operating income", "path_prefix": "filings/", "max_hits": 5}
            )
            self.assertEqual(search["total_matching_lines"], 1)
            self.assertEqual(search["hits"][0]["path"], "filings/10-Q_2026-01-15_visible-accession.md")
            self.assertEqual(tools.dispatch("calculate", {"expression": "(123 - 45) / 3"}), {"value": 26.0})

            with self.assertRaisesRegex(ValueError, "outside allowed files"):
                tools.dispatch("read_file", {"path": "../answers.json", "offset": 0, "characters": 1})

    def test_hash_drift_is_rejected_before_any_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = self._company(root)
            (root / "questions.md").write_text("changed after manifest\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from prepared manifest"):
                FilingTools(company)

    def test_hidden_target_accession_in_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = self._company(root, accession="hidden-target-accession")
            with self.assertRaisesRegex(ValueError, "Hidden target or post-cutoff"):
                FilingTools(company)

    def test_hidden_qa_file_is_rejected_even_when_hash_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = self._company(root)
            qa = root / "forecast_benchmark_qa.json"
            qa.write_text('{"targets": ["hidden"]}\n', encoding="utf-8")
            company["allowed_files"].append(self._receipt(root, qa.name))
            with self.assertRaisesRegex(ValueError, "Non-filing allowlist entry"):
                FilingTools(company)

    def test_post_cutoff_index_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = self._company(root, date="2026-02-02")
            with self.assertRaisesRegex(ValueError, "Hidden target or post-cutoff"):
                FilingTools(company)

    def test_traversal_in_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = self._company(root)
            (root / "outside.md").write_text("not allowed\n", encoding="utf-8")
            data = (root / "outside.md").read_bytes()
            company["allowed_files"].append(
                {"path": "filings/../outside.md", "bytes": len(data), "sha256": digest(data)}
            )
            with self.assertRaisesRegex(ValueError, "Unsafe relative path"):
                FilingTools(company)

    def test_index_and_allowlist_must_match_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company = self._company(root)
            (root / "filings" / "8-K_2026-01-20_extra.md").write_text("extra\n", encoding="utf-8")
            company["allowed_files"].append(self._receipt(root, "filings/8-K_2026-01-20_extra.md"))
            with self.assertRaisesRegex(ValueError, "Index and allowlist differ"):
                FilingTools(company)


if __name__ == "__main__":
    unittest.main()
