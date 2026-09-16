import unittest

from data_scientist_harness.feature_availability_contract import (
    REQUIRED_ORDER,
    audit_feature_availability,
    freeze_feature_availability,
)


def contract():
    return {
        "contract_id": "same-event-state-delta-v1",
        "feature_names": ["state_wp_delta"],
        "clock_domain": "UTC_nanoseconds",
        "row_id_field": "row_id",
        "feature_event_time_field": "event_ns",
        "feature_available_time_field": "available_ns",
        "decision_time_field": "decision_ns",
        "label_start_time_field": "label_start_ns",
        "label_end_time_field": "label_end_ns",
        "required_order": REQUIRED_ORDER,
        "missing_time_policy": "fail_closed",
        "source_receipt_sha256": "a" * 64,
    }


def rows():
    return [
        {"row_id": "a", "event_ns": 10, "available_ns": 11, "decision_ns": 11,
         "label_start_ns": 12, "label_end_ns": 20},
        {"row_id": "b", "event_ns": 20, "available_ns": 21, "decision_ns": 23,
         "label_start_ns": 24, "label_end_ns": 30},
    ]


class FeatureAvailabilityContractTests(unittest.TestCase):
    def test_same_event_rows_pass_with_explicit_clocks(self):
        frozen = freeze_feature_availability(contract())
        audit = audit_feature_availability(frozen, rows())
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["violations"], 0)
        self.assertEqual(audit["rows"], 2)

    def test_later_feature_row_fails_closed(self):
        value = rows(); value[0]["available_ns"] = 13
        with self.assertRaisesRegex(ValueError, "clock order"):
            audit_feature_availability(freeze_feature_availability(contract()), value)

    def test_label_must_begin_after_decision(self):
        value = rows(); value[0]["label_start_ns"] = 11
        with self.assertRaisesRegex(ValueError, "clock order"):
            audit_feature_availability(freeze_feature_availability(contract()), value)

    def test_rows_cannot_be_silently_deduplicated(self):
        value = rows(); value[1]["row_id"] = "a"
        with self.assertRaisesRegex(ValueError, "unique"):
            audit_feature_availability(freeze_feature_availability(contract()), value)

    def test_contract_cannot_weaken_order_or_missing_policy(self):
        for key, value in (("required_order", "available<=label_end"),
                           ("missing_time_policy", "drop_row")):
            candidate = contract(); candidate[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                freeze_feature_availability(candidate)


if __name__ == "__main__":
    unittest.main()

