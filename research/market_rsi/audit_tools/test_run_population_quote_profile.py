import copy
import unittest
from run_population_quote_profile import mode_spec, validate_terminal, RAW_SHA, PREFIX_SHA, FULL_SHA, CASES


def fixture(mode="pilot"):
    spec = mode_spec(mode)
    cases = [{"key": list(key), "entity_sha256": "a"*64, "raw_sha256": value,
              "source_status": "uncrossed", "depth_status": status, "price_candidate": True}
             for (key, value), status in zip(CASES.items(), ("crossed", "locked", "uncrossed"))] if mode == "hour" else []
    report = {"source_sha256": RAW_SHA, "mode": mode, "raw_records": spec["max_records"],
        "decoded_sha256": spec["expected_decoded_sha256"], "decoder_reaped": True,
        "full_hour_decoded": mode == "hour", "decoder_exit_code": 0 if mode == "hour" else -13,
        "stop_reason": "eof" if mode == "hour" else "fixed_prefix", "source_mutated": False,
        "new_test_opened": False, "source_admitted": False, "fits": 0, "paid_calls": 0, "raw_rows_exported": 0,
        "profile": {"case": cases, "breadth": {"entities": 1},
            "entities": [{"entity_sha256": "a"*64, "counts": {"quote_observations": 3}}],
            "input_counts": {"raw_records": spec["max_records"]},
            "totals": {"counts": {"quote_observations": 3}, "source_status": {"uncrossed": 3},
                       "depth_status": {"uncrossed": 3}, "depth_to_source_status": {"uncrossed -> uncrossed": 3}}}}
    return report, spec


class RunnerTests(unittest.TestCase):
    def test_modes_are_fixed(self):
        self.assertEqual(mode_spec("pilot")["max_records"], 50000)
        self.assertEqual(mode_spec("hour")["max_records"], 4328805)
        with self.assertRaises(ValueError): mode_spec("new_day")

    def test_valid_fixtures(self):
        for mode in ("pilot", "hour"):
            r, s = fixture(mode); validate_terminal(r, s)

    def test_truncated_hour_not_success(self):
        r, s = fixture("hour"); r["decoder_exit_code"] = -13
        with self.assertRaisesRegex(ValueError, "not decoded"): validate_terminal(r, s)

    def test_changed_bytes_fail(self):
        r, s = fixture(); r["decoded_sha256"] = "f"*64
        with self.assertRaisesRegex(ValueError, "scope"): validate_terminal(r, s)

    def test_denominator_mismatch(self):
        r, s = fixture(); r["profile"]["totals"]["source_status"]["uncrossed"] = 4
        with self.assertRaisesRegex(ValueError, "denominators"): validate_terminal(r, s)

    def test_known_case_cannot_switch_entity(self):
        r, s = fixture("hour"); r["profile"]["case"][1]["entity_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "one-token"): validate_terminal(r, s)

    def test_no_source_admission_from_profile(self):
        r, s = fixture(); r["source_admitted"] = True
        with self.assertRaisesRegex(ValueError, "admit"): validate_terminal(r, s)

    def test_bad_decoder_exit_even_with_prefix_count(self):
        r, s = fixture(); r["decoder_exit_code"] = 1
        with self.assertRaisesRegex(ValueError, "pilot"): validate_terminal(r, s)


if __name__ == "__main__": unittest.main()
