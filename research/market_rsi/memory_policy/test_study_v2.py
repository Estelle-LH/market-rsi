from pathlib import Path
import tempfile
import unittest

from market_rsi import file_hash, fresh_json
from memory_policy.semantic_source_preflight import source_hashes
from memory_policy.study_v2 import (
    MATERIALIZATION_POLICY, configure_engine, preflight_receipts, worker_program,
)
from memory_policy.test_spec_v2 import valid_spec
import memory_policy.study as engine


def report(row, role):
    transport = {
        "complete": True, "compressed_bytes_read": row["compressed_bytes"],
        "decoded_records": 2, "compressed_sha256": "a" * 64,
        "decoded_bytes": 20, "decoded_sha256": "b" * 64,
        "source_initial_stat": {"device": 1, "inode": 2,
                                "bytes": row["compressed_bytes"],
                                "mtime_ns": 3, "ctime_ns": 4},
        "source_unchanged_verified": True, "decoder_exit_code": 0,
        "decoder_reaped": True, "feeder_reaped": True,
    }
    semantic = {
        "schema": "memory_policy_semantic_receipt_v1",
        "raw_records": 2, "excluded_kind_messages": 0,
        "price_change_messages": 1,
        "selected_observations": 2, "entities": 1,
        "selected_source_regressions": 0,
        "entities_with_source_regression": 0,
        "last_attempted_record": 2,
        "message_selection_kernel": "CacheProfile.consume",
        "summary_or_cache_called": False,
        "target_statistics_computed": 0, "raw_rows_exported": 0,
        "fits": 0, "provider_calls": 0,
    }
    return {"session": row["session"], "role": role, "complete": True,
            "advertised_bytes": row["compressed_bytes"],
            "transport": transport, "semantic_receipt": semantic,
            "raw_rows_exported": 0, "target_statistics_computed": 0,
            "fits": 0, "provider_calls": 0}


class StudyV2Tests(unittest.TestCase):
    def test_same_spec_semantic_receipts_are_required(self):
        spec = valid_spec()
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "spec.json"
            receipt_path = Path(temp) / "preflight.json"
            fresh_json(spec_path, spec)
            reports = [report(row, role)
                       for role in ("initial_train", "dev", "final")
                       for row in spec[role]]
            fresh_json(receipt_path, {
                "schema": "memory_policy_semantic_preflight_promotion_v1",
                "complete": True, "manifest_sha256": file_hash(spec_path),
                "contract_sha256": "a" * 64,
                "candidate_admission_sha256": "b" * 64,
                "source_hashes": source_hashes(), "reports": reports,
                "raw_rows_exported": 0, "target_statistics_computed": 0,
                "fits": 0, "provider_calls": 0,
            })
            receipts = preflight_receipts(spec_path, receipt_path, spec)
            self.assertEqual(len(receipts), 31)
            reports[0]["semantic_receipt"]["selected_observations"] = 0
            fresh_json(Path(temp) / "bad.json", {
                "schema": "memory_policy_semantic_preflight_v1",
                "complete": True, "manifest_sha256": file_hash(spec_path),
                "contract_sha256": "a" * 64,
                "source_hashes": source_hashes(), "reports": reports,
                "raw_rows_exported": 0, "target_statistics_computed": 0,
                "fits": 0, "provider_calls": 0,
            })
            with self.assertRaises(ValueError):
                preflight_receipts(spec_path, Path(temp) / "bad.json", spec)

    def test_engine_and_worker_use_v2_gates(self):
        configure_engine()
        self.assertIs(engine.preflight_receipts, preflight_receipts)
        body = worker_program({"resource_policy": MATERIALIZATION_POLICY})
        self.assertIn(b"memory_policy_materialize_v2", body)
        self.assertIn(b"verify_semantic_materialization", body)


if __name__ == "__main__":
    unittest.main()
