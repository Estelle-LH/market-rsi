import unittest

from data_scientist_harness.target_discovery_contract import (
    freeze_target_discovery_spec,
    verify_frozen_target_discovery_spec,
)


def spec():
    return {
        "spec_id": "s1", "opened_data_role": "opened_train",
        "clock_domain": "historical_provider_and_exchange_epoch_seconds",
        "decision_anchor": "play_event_time",
        "price_source": "historical_executed_trade_print_home_outcome",
        "pre_price_rule": "last_trade_at_or_before_decision_with_max_age",
        "pre_price_max_age_seconds": 300,
        "elapsed_horizons_seconds": [15, 30, 60],
        "elapsed_endpoint_rule": "last_trade_strictly_after_decision_at_or_before_horizon",
        "event_horizons_trade_count": [1, 5],
        "event_endpoint_rule": "nth_trade_strictly_after_decision",
        "max_event_target_wall_seconds": 300,
        "target_transform": "price_delta", "direction_deadband_bps": 0,
        "missing_endpoint_policy": "unavailable_do_not_filter",
        "comparison_support": "common_all_targets", "source_receipt_sha256": "a" * 64,
        "route_dev_access": False, "sealed_final_access": False,
    }


class TargetDiscoveryContractTests(unittest.TestCase):
    def test_valid_spec_freezes_and_verifies(self):
        frozen = freeze_target_discovery_spec(spec())
        self.assertEqual(verify_frozen_target_discovery_spec(frozen)["elapsed_horizons_seconds"], [15, 30, 60])
        self.assertIsNone(frozen["performance_reward"])

    def test_no_target_rejected(self):
        value = spec(); value["elapsed_horizons_seconds"] = []; value["event_horizons_trade_count"] = []
        with self.assertRaisesRegex(ValueError, "at least one"):
            freeze_target_discovery_spec(value)

    def test_unsorted_or_duplicate_horizon_rejected(self):
        value = spec(); value["elapsed_horizons_seconds"] = [30, 15, 30]
        with self.assertRaisesRegex(ValueError, "sorted and unique"):
            freeze_target_discovery_spec(value)

    def test_route_dev_rejected(self):
        value = spec(); value["route_dev_access"] = True
        with self.assertRaisesRegex(ValueError, "Route-Dev"):
            freeze_target_discovery_spec(value)

    def test_deadband_only_applies_to_direction(self):
        value = spec(); value["direction_deadband_bps"] = 10
        with self.assertRaisesRegex(ValueError, "cannot carry"):
            freeze_target_discovery_spec(value)
        value["target_transform"] = "direction"
        self.assertEqual(freeze_target_discovery_spec(value)["spec"]["direction_deadband_bps"], 10)

    def test_mutation_rejected(self):
        frozen = freeze_target_discovery_spec(spec())
        frozen["spec"]["elapsed_horizons_seconds"] = [30]
        with self.assertRaisesRegex(ValueError, "modified"):
            verify_frozen_target_discovery_spec(frozen)


if __name__ == "__main__":
    unittest.main()
