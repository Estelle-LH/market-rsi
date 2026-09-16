import copy
import unittest
from selected_source_document import validate_selected


class SelectedDocumentTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"proposal_valid": True, "acquisition_admitted": False,
                     "body": {"objects": [{"source_id": "a/b", "revision": "a" * 40}]}}
        self.listing = {"dataset": "a/b", "revision": "a" * 40,
                        "objects": [{"path": "README.md", "type": "file", "advertised_bytes": 12}]}

    def test_selected_exact_document_url(self):
        url, obj = validate_selected(self.plan, self.listing, "README.md")
        self.assertEqual(url, "https://huggingface.co/datasets/a/b/raw/" + "a" * 40 + "/README.md")
        self.assertEqual(obj["advertised_bytes"], 12)

    def test_no_data_or_samples_or_traversal(self):
        for name in ("x.db.zst", "samples/README.md", "../README.md", "schema.sql"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_selected(self.plan, self.listing, name)

    def test_unselected_source_revision_and_branch_refused(self):
        for key, value in (("dataset", "c/d"), ("revision", "b" * 40), ("revision", "main")):
            changed = copy.deepcopy(self.listing)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_selected(self.plan, changed, "README.md")

    def test_oversized_or_missing_document_refused(self):
        for size in (0, 65537):
            changed = copy.deepcopy(self.listing)
            changed["objects"][0]["advertised_bytes"] = size
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_selected(self.plan, changed, "README.md")
        with self.assertRaises(ValueError):
            validate_selected(self.plan, self.listing, "VALIDATION.md")

    def test_acquisition_flag_not_accepted(self):
        changed = copy.deepcopy(self.plan)
        changed["acquisition_admitted"] = True
        with self.assertRaises(ValueError):
            validate_selected(changed, self.listing, "README.md")


if __name__ == "__main__":
    unittest.main()
