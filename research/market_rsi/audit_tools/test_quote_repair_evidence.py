import copy
import unittest
from market_rsi import digest
from quote_repair_evidence import validate, RAW_SHA, DECODED_SHA, CSV_SHA, RAW_CASE_HASHES, CASE_ROW_SHA


def fixture():
    # Deliberately synthetic aggregate protocol fixture, not financial evidence.
    claim = {"day": "2026-08-21", "hour": 0, "source_tag": "pm-source-quotes-v0.1.0",
             "sources": {"quote_source/reconstruct.py": "a"*64}}
    case = [{"key": [i, 0, 0], "record_sha256": sha, "depth_status": status,
             "source_status": "uncrossed", "price_candidate": True, "source_size_present": False}
            for (i, sha), status in zip(RAW_CASE_HASHES.items(), ("crossed", "locked", "uncrossed"))]
    report = {"raw_sha256": RAW_SHA, "decoded_sha256": DECODED_SHA, "csv_sha256": CSV_SHA,
              "csv_case_sha256": CASE_ROW_SHA, "raw_records": 4328805,
              "adapter_sha256": "a"*64, "ssh_reaped": True, "decoder_reaped": True,
              "analysis": {"case": case, "known_cross_record_case_fixed": True,
                  "counts": {"target_raw_records": 65401, "observations": 3, "price_candidates": 3},
                  "source_status_counts": {"uncrossed": 3},
                  "same_record_depth_to_source_status": {"crossed -> uncrossed": 1, "locked -> uncrossed": 1, "uncrossed -> uncrossed": 1}},
              "claim_sha256": "b"*64}
    report.update({k: 0 for k in ("exit_code", "decoder_exit_code", "fits", "new_tinker_cost_usd", "raw_frames_exported", "identifiers_exported")})
    report.update({k: False for k in ("source_mutated", "source_admitted", "new_test_opened", "source_clock_attested", "coverage_admitted")})
    report["result_sha256"] = digest(report)
    return report, claim


def packets(report):
    return [{"stage": "complete", "report": {k: v for k, v in report.items()
        if k not in ("result_sha256", "claim_sha256", "exit_code", "ssh_reaped")}}]


class EvidenceTests(unittest.TestCase):
    def test_consistent_receipt(self):
        r, c = fixture()
        self.assertTrue(validate(r, c, "b"*64, packets(r))["known_cross_record_case_fixed"])

    def test_hash_tamper(self):
        r, c = fixture(); r["fits"] = 1
        with self.assertRaisesRegex(ValueError, "report hash"):
            validate(r, c, "b"*64, packets(r))

    def test_resealed_bad_denominator(self):
        r, c = fixture(); r["analysis"]["counts"]["observations"] = 4
        r["result_sha256"] = digest({k: v for k, v in r.items() if k != "result_sha256"})
        with self.assertRaisesRegex(ValueError, "denominators"):
            validate(r, c, "b"*64, packets(r))

    def test_no_cleanup_no_admission(self):
        for key in ("decoder_reaped", "source_admitted"):
            r, c = fixture(); r[key] = not r[key]
            r["result_sha256"] = digest({k: v for k, v in r.items() if k != "result_sha256"})
            with self.assertRaises(ValueError): validate(r, c, "b"*64, packets(r))

    def test_missing_terminal(self):
        r, c = fixture()
        with self.assertRaisesRegex(ValueError, "terminal"):
            validate(r, c, "b"*64, [])

    def test_forged_success_flag_not_enough(self):
        r, c = fixture(); r["analysis"]["case"][0]["source_status"] = "crossed"
        r["result_sha256"] = digest({k: v for k, v in r.items() if k != "result_sha256"})
        with self.assertRaisesRegex(ValueError, "known-case"):
            validate(r, c, "b"*64, packets(r))

    def test_source_hash_binding(self):
        r, c = fixture(); c["sources"]["quote_source/reconstruct.py"] = "c"*64
        with self.assertRaisesRegex(ValueError, "adapter source"):
            validate(r, c, "b"*64, packets(r))


if __name__ == "__main__": unittest.main()
