import unittest

from sports_event_research.materialize_controller_targets import (
    elapsed_endpoint,
    event_endpoint,
    materialize_rows,
    target_names,
    transform_value,
)


def spec():
    return {
        "pre_price_max_age_seconds": 20,
        "elapsed_horizons_seconds": [10, 30],
        "event_horizons_trade_count": [1, 2],
        "max_event_target_wall_seconds": 30,
        "target_transform": "price_delta", "direction_deadband_bps": 0,
    }


class MaterializeControllerTargetsTests(unittest.TestCase):
    def test_elapsed_uses_last_strictly_later_trade_inside_horizon(self):
        times, prices = [90, 100, 105, 109, 111], [.4, .5, .6, .7, .8]
        self.assertEqual(elapsed_endpoint(times, prices, 100, 10), (109, .7))
        self.assertIsNone(elapsed_endpoint([90, 100], [.4, .5], 100, 10))

    def test_event_counts_only_strictly_later_trades(self):
        times, prices = [100, 100, 101, 105, 140], [.4, .5, .6, .7, .8]
        self.assertEqual(event_endpoint(times, prices, 100, 1, 30), (101, .6))
        self.assertEqual(event_endpoint(times, prices, 100, 2, 30), (105, .7))
        self.assertIsNone(event_endpoint(times, prices, 100, 3, 30))

    def test_direction_deadband_is_predeclared(self):
        self.assertEqual(transform_value(.002, "direction", 10), 1)
        self.assertEqual(transform_value(.0005, "direction", 10), 0)
        self.assertEqual(transform_value(-.002, "direction", 10), -1)

    def test_all_plays_are_preserved_and_unavailable_is_blank(self):
        rows, summary = materialize_rows([
            {"play_id": "p1", "play_timestamp": "100"},
            {"play_id": "p2", "play_timestamp": "200"},
        ], [90, 105, 109, 120], [.4, .5, .6, .7], spec())
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["elapsed_10s_delta"], .2)
        self.assertAlmostEqual(rows[0]["event_2trades_delta"], .2)
        self.assertEqual(rows[1]["elapsed_10s_delta"], "")
        self.assertEqual(summary["plays"], 2)
        self.assertEqual(summary["common_support_rows"], 1)

    def test_target_names_distinguish_clock_and_event_time(self):
        self.assertEqual(target_names(spec()), [
            ("elapsed_10s_delta", "elapsed", 10),
            ("elapsed_30s_delta", "elapsed", 30),
            ("event_1trades_delta", "event", 1),
            ("event_2trades_delta", "event", 2),
        ])


if __name__ == "__main__":
    unittest.main()
