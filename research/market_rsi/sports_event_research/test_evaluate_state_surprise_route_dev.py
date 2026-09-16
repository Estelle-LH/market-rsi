import unittest

import numpy as np

from sports_event_research.evaluate_state_surprise_route_dev import ridge_predict


def row(game, value, target):
    return {"game": game, "numeric": [value] * 13, "categorical": ["pass"], "target": target}


class EvaluateStateSurpriseTests(unittest.TestCase):
    def test_candidate_prediction_requires_train_fitted_transform(self):
        train = [row("g1", 0.0, 0.0), row("g1", 1.0, 1.0),
                 row("g2", 0.0, 0.0), row("g2", 1.0, 1.0)]
        dev = [row("g3", 0.5, 0.5)]
        prediction = ridge_predict(train, dev, np.asarray([[0.0], [1.0], [0.0], [1.0]]),
                                   np.asarray([[0.5]]))
        self.assertEqual(prediction.shape, (1,))
        self.assertTrue(np.isfinite(prediction).all())


if __name__ == "__main__":
    unittest.main()
