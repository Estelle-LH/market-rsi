import json
import tempfile
import unittest
from pathlib import Path

from build_archive_continuation_data import build as build_continuation
from build_archive_formal_data import build as build_parent
from formal_round_binding import freeze_binding, validate_data_root
from prospective_data_lifecycle import ProspectiveDataLifecycle
from research.market_rsi.tests.test_formal_round_binding import _source


class ArchiveContinuationDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = _source()
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(source))
        self.parent = self.root / "parent"
        build_parent([(self.source, source)], self.parent, "experiment")
        self.data = self.root / "continuation"
        build_continuation(self.parent, self.data, "round-02")

    def tearDown(self):
        self.temp.cleanup()

    def test_unopened_remaining_rounds_form_a_fresh_lifecycle(self):
        checked = validate_data_root(self.data)
        self.assertEqual([item["round_id"] for item in checked["rounds"]],
                         ["round-02", "round-03"])
        lifecycle = ProspectiveDataLifecycle.create(
            self.root / "lifecycle", experiment_id="experiment",
            rounds=checked["rounds"],
            transfer_policy_sha256=checked["receipt"]["transfer_policy_sha256"])
        first = freeze_binding(self.root / "round-02.json", self.data,
                               lifecycle.root, "round-02")
        self.assertEqual(first["train_rows"], 360)
        self.assertEqual(first["dev_rows"], 150)
        lifecycle.claim_dev_score("round-02", candidate_set_sha256="a" * 64)
        lifecycle.complete_dev_score("round-02", score_receipt_sha256="b" * 64)
        second = freeze_binding(self.root / "round-03.json", self.data,
                                lifecycle.root, "round-03")
        self.assertEqual(second["train_rows"], 540)
        self.assertEqual(second["dev_rows"], 150)


if __name__ == "__main__":
    unittest.main()
