import unittest

from train_label_sampling_diagnostic import label_selection


class TrainLabelSamplingTests(unittest.TestCase):
    def rows(self):
        return [{"row_id": f"r{i}", "label_available_ms": 1000,
                 "target": .5 if i < 900 else .51, "features": {"mid": .5}}
                for i in range(1000)]

    def choose(self, rows, **kwargs):
        spec = dict(role="opened_train", fit_cutoff_ms=2000,
                    flat_probability=.1, weighting="inverse_probability")
        return label_selection(rows, **{**spec, **kwargs})

    def test_all_moving_train_examples_kept(self):
        masks = self.choose(self.rows())
        self.assertTrue(all(m["keep"] for m in masks[900:]))
        self.assertTrue(any(not m["keep"] for m in masks[:900]))

    def test_dev_final_and_unavailable_labels_rejected(self):
        for role in ("dev", "final"):
            with self.assertRaisesRegex(ValueError, "opened_train"):
                self.choose(self.rows(), role=role)
        with self.assertRaisesRegex(ValueError, "before fit cutoff"):
            self.choose(self.rows(), fit_cutoff_ms=1000)

    def test_weighted_and_unweighted_have_identical_rows(self):
        a, b = self.choose(self.rows()), self.choose(self.rows(), weighting="unweighted")
        self.assertEqual([m["keep"] for m in a], [m["keep"] for m in b])
        self.assertTrue(all(m["loss_weight"] == 10 for m in a[:900] if m["keep"]))
        self.assertTrue(all(m["loss_weight"] == 1 for m in b if m["keep"]))

    def test_probability_one_preserves_every_row(self):
        self.assertTrue(all(m["keep"] for m in self.choose(self.rows(), flat_probability=1)))

    def test_bad_probability_and_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            self.choose(self.rows(), flat_probability=0)
        with self.assertRaisesRegex(ValueError, "duplicate identity"):
            self.choose([self.rows()[0], self.rows()[0]])


if __name__ == "__main__":
    unittest.main()
