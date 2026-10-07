import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from experiments import nfl_ingame_price_change_train_diagnostic as runner


def row(key, game="a", label=.1):
    return dict(row_id=key, game_id=game, game_date="2025-11-01", game_week="09", fold="check_1",
                anchor_s=1000, p_current=.5, label=label, features=tuple(range(13)),
                history=((-30, .5, 2., 1),), reason="SECRET_FUTURE_LABEL_AVAILABILITY")


class PriceRunnerTests(unittest.TestCase):
    def test_review_binding_has_no_cycle_and_does_not_exclude_other_fields(self):
        op = {"mode": "ordinary", "deadline": "x", "review": {"path": "one", "sha256": "a"}}
        first = runner.operation_commitment(op)
        op["review"] = {"path": "two", "sha256": "b"}
        self.assertEqual(runner.operation_commitment(op), first)
        op["deadline"] = "y"
        self.assertNotEqual(runner.operation_commitment(op), first)

    def test_candidate_inputs_exclude_labels_ids_and_future_missingness(self):
        fit, checks = [row("f")], [row("c", label=None)]
        x, y, weights, xc, histories, check_histories = runner.matrices(fit, checks)
        self.assertEqual(xc.shape, (1, 13))
        self.assertEqual(check_histories, [[(-30, .5, 2., 1)]])
        changed = {**checks[0], "label": .99, "reason": None, "row_id": "changed", "game_id": "secret"}
        other = runner.matrices(fit, [changed])
        np.testing.assert_array_equal(xc, other[3])
        self.assertEqual(check_histories, other[5])

    def test_fit_weights_are_game_equal_and_mean_one(self):
        weights = runner.matrices([row("a1"), row("a2"), row("b", "b")], [row("c")])[2]
        self.assertEqual(weights.mean(), 1.)
        self.assertEqual(weights[:2].sum(), weights[2])

    def test_nonfinite_features_reject(self):
        bad = row("bad")
        bad["features"] = (float("nan"),) + tuple(range(12))
        with self.assertRaises(ValueError):
            runner.matrices([row("f")], [bad])

    def test_reference_requires_identical_prices_labels_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checks = [row("x")]
            fields = ["row_id", "game_id", "game_date", "game_week", "fold", "anchor_s", "p_current", "label", runner.ORDINARY]
            with (root / "predictions.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({**{k: checks[0][k] for k in fields if k != runner.ORDINARY}, runner.ORDINARY: .02})
            (root / "input_receipts.json").write_text(json.dumps({"source": "fixed"}))
            manifest = {"task_id": runner.TASK, "complete": True, "model_fits": 4,
                        "predictions_sha256": runner.sha(root / "predictions.csv"),
                        "input_receipts_sha256": runner.sha(root / "input_receipts.json")}
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            self.assertEqual(runner.reference_predictions(path, checks, {"source": "fixed"}), {"x": .02})
            with self.assertRaises(ValueError):
                runner.reference_predictions(path, [{**checks[0], "label": .2}], {"source": "fixed"})
            with self.assertRaises(ValueError):
                runner.reference_predictions(path, checks, {"source": "different"})


if __name__ == "__main__":
    unittest.main()
