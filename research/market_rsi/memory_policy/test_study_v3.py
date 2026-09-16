from pathlib import Path
import tempfile
import unittest

from market_rsi import file_hash, fresh_json
from memory_policy.semantic_source_preflight import source_hashes
from memory_policy.study_v3 import cleanup_remote_cache, preflight_receipts
from memory_policy.test_spec_v3 import valid_spec


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
        "price_change_messages": 1, "selected_observations": 2,
        "entities": 1, "selected_source_regressions": 0,
        "entities_with_source_regression": 0, "last_attempted_record": 2,
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


class StudyV3Tests(unittest.TestCase):
    def test_exact_v3_promotion_and_cumulative_gate(self):
        spec = valid_spec()
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "spec.json"
            receipt_path = Path(temp) / "preflight.json"
            fresh_json(spec_path, spec)
            reports = [report(row, role)
                       for role in ("initial_train", "dev", "final")
                       for row in spec[role]]
            value = {
                "schema": "memory_policy_semantic_preflight_promotion_v2",
                "complete": True,
                "manifest_sha256": file_hash(spec_path),
                "contract_sha256": "a" * 64,
                "source_hashes": source_hashes(),
                "source_reselection_sha256": "b" * 64,
                "source_admission_sha256": "c" * 64,
                "reports": reports,
                "target_statistics_computed": 0,
                "provider_calls": 0,
            }
            fresh_json(receipt_path, value)
            self.assertEqual(len(preflight_receipts(
                spec_path, receipt_path, spec)), 31)
            reports[0]["semantic_receipt"]["selected_observations"] = 10_000_001
            fresh_json(Path(temp) / "too-large.json", value)
            with self.assertRaisesRegex(ValueError, "cumulative"):
                preflight_receipts(spec_path, Path(temp) / "too-large.json", spec)

    def test_remote_cleanup_is_exact_and_retries_idempotently(self):
        class Result:
            returncode = 0
            stdout = ('{"removed":true,"relative_parts":'
                      '["memory-policy-v3-20990101-01","2099-01-01T00"]}')

        calls = []

        def transport(command, **kwargs):
            calls.append((command, kwargs))
            return Result()

        with tempfile.TemporaryDirectory() as temp:
            cleanup_remote_cache(
                Path("memory-policy-v3-20990101-01"), "2099-01-01T00",
                Path(temp), transport=transport)
            self.assertEqual(len(calls), 1)
            self.assertTrue((Path(temp) / "remote-cleanup.json").is_file())
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                cleanup_remote_cache(Path("unsafe"), "2099-01-01T00",
                                     Path(temp), transport=transport)


if __name__ == "__main__":
    unittest.main()
