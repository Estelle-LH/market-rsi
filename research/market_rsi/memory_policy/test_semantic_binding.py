from types import SimpleNamespace
import unittest

from memory_policy.semantic_binding import (
    structural_receipt, verify_semantic_materialization,
)


def fixture():
    transport = {
        "complete": True,
        "compressed_bytes_read": 10,
        "compressed_sha256": "a" * 64,
        "decoded_bytes": 20,
        "decoded_sha256": "b" * 64,
        "decoded_records": 2,
        "source_initial_stat": {"device": 1, "inode": 2, "bytes": 10,
                                "mtime_ns": 3, "ctime_ns": 4},
        "source_unchanged_verified": True,
        "decoder_exit_code": 0,
        "decoder_reaped": True,
        "feeder_reaped": True,
    }
    semantic = {
        "schema": "memory_policy_semantic_receipt_v1",
        "raw_records": 2,
        "excluded_kind_messages": 1,
        "price_change_messages": 1,
        "selected_observations": 2,
        "entities": 1,
        "selected_source_regressions": 0,
        "entities_with_source_regression": 0,
        "last_attempted_record": 2,
        "message_selection_kernel": "CacheProfile.consume",
        "summary_or_cache_called": False,
        "target_statistics_computed": 0,
        "raw_rows_exported": 0,
        "fits": 0,
        "provider_calls": 0,
    }
    report = {"complete": True, "transport": transport,
              "semantic_receipt": semantic}
    profile = SimpleNamespace(
        counts={"raw_records": 2, "excluded_kind_messages": 1,
                "price_change_messages": 1, "selected_observations": 2},
        entities={"a": SimpleNamespace(gaps={"negative": 0})},
        last_ordinal=2,
    )
    return report, transport, profile


class SemanticBindingTests(unittest.TestCase):
    def test_exact_receipt_reproduces(self):
        report, transport, profile = fixture()
        self.assertEqual(structural_receipt(report)["json_object_records"], 2)
        self.assertTrue(verify_semantic_materialization(report, transport, profile))

    def test_changed_bytes_or_selection_are_rejected(self):
        report, transport, profile = fixture()
        changed = dict(transport, decoded_sha256="c" * 64)
        with self.assertRaises(ValueError):
            verify_semantic_materialization(report, changed, profile)
        report, transport, profile = fixture()
        profile.counts["selected_observations"] = 1
        with self.assertRaises(ValueError):
            verify_semantic_materialization(report, transport, profile)

    def test_incomplete_or_scored_receipt_is_rejected(self):
        report, _, _ = fixture()
        report["semantic_receipt"]["target_statistics_computed"] = 1
        with self.assertRaises(ValueError):
            structural_receipt(report)


if __name__ == "__main__":
    unittest.main()
