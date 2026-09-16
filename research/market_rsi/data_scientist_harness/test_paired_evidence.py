import unittest

from data_scientist_harness.paired_evidence import (
    build_paired_evidence,
    validate_paired_evidence_spec,
)


def spec():
    return {
        "kind": "paired_grouped_loss_v1",
        "unit": "game",
        "block": "UTC_date",
        "loss": "equal_game_mse",
        "delta": "candidate_minus_baseline",
        "reward_direction": "minimize",
        "persist_unit_records_runner_private": True,
        "public_visibility": "aggregate_only",
        "bootstrap_draws": 1000,
        "bootstrap_seed": 23,
        "top_k_units": [1, 5],
    }


def records():
    return [
        {"unit_id": "g1", "block_id": "d1", "rows": 10,
         "baseline_loss": 0.10, "candidate_loss": 0.08},
        {"unit_id": "g2", "block_id": "d1", "rows": 20,
         "baseline_loss": 0.20, "candidate_loss": 0.21},
        {"unit_id": "g3", "block_id": "d2", "rows": 30,
         "baseline_loss": 0.30, "candidate_loss": 0.25},
    ]


class PairedEvidenceTests(unittest.TestCase):
    def test_private_units_and_identity_free_public_summary(self):
        private, public = build_paired_evidence(records(), spec())
        self.assertEqual(len(private["units"]), 3)
        self.assertAlmostEqual(public["equal_unit_mean_delta"], (-0.02 + 0.01 - 0.05) / 3)
        self.assertEqual(public["candidate_better_unit_fraction"], 2 / 3)
        self.assertFalse(public["unit_ids_exposed"])
        self.assertNotIn("g1", repr(public))
        self.assertIn("top_1_absolute_delta_share", public)
        self.assertIn("leave_one_unit_out_mean_delta", public)

    def test_pairing_requires_same_unique_units(self):
        value = records(); value[1]["unit_id"] = "g1"
        with self.assertRaisesRegex(ValueError, "unique"):
            build_paired_evidence(value, spec())

    def test_nonfinite_or_negative_loss_fails(self):
        for value in (float("nan"), -0.1):
            data = records(); data[0]["candidate_loss"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "loss"):
                build_paired_evidence(data, spec())

    def test_fewer_than_two_time_blocks_fails(self):
        value = records()
        for row in value:
            row["block_id"] = "d1"
        with self.assertRaisesRegex(ValueError, "time blocks"):
            build_paired_evidence(value, spec())

    def test_visibility_and_output_cannot_be_weakened(self):
        for key, value in (("public_visibility", "unit_rows"),
                           ("persist_unit_records_runner_private", False),
                           ("top_k_units", [1]),
                           ("delta", "baseline_minus_candidate")):
            candidate = spec(); candidate[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_paired_evidence_spec(candidate)

    def test_positive_delta_is_never_counted_as_candidate_better(self):
        data = records()
        data[0]["candidate_loss"] = data[0]["baseline_loss"] + 0.01
        data[1]["candidate_loss"] = data[1]["baseline_loss"] + 0.01
        data[2]["candidate_loss"] = data[2]["baseline_loss"] - 0.01
        _, public = build_paired_evidence(data, spec())
        self.assertAlmostEqual(public["candidate_better_unit_fraction"], 1 / 3)
        self.assertGreater(public["equal_unit_mean_delta"], 0)


if __name__ == "__main__":
    unittest.main()
