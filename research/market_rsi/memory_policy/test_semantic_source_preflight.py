import json
from pathlib import Path
import tempfile
import unittest

from memory_pilot.materialize import CacheProfile
from memory_policy.semantic_preflight_worker import bounded_failure, validate_policy
from memory_policy.semantic_source_preflight import (
    RESOURCE_POLICY, contract_from, midnight_ms, operation, validate_report,
)
from test_typed_raw_profile import T, contract, message


class SemanticSourcePreflightTests(unittest.TestCase):
    def test_remote_exchange_runner_is_bound_into_source_hashes(self):
        from memory_policy.semantic_source_preflight import source_hashes
        self.assertIn("audit_tools/run_typed_raw_profile.py", source_hashes())

    def row(self):
        return {"session": "2026-09-10T00", "role": "final",
                "compressed_bytes": 123}

    def report(self):
        return {
            "complete": True,
            "consumer_failure": None,
            "session": "2026-09-10T00", "role": "final",
            "advertised_bytes": 123,
            "transport": {"complete": True, "compressed_bytes_read": 123,
                          "decoded_records": 7},
            "semantic_receipt": {
                "selected_observations": 8, "entities": 2,
                "last_attempted_record": 7,
                "message_selection_kernel": "CacheProfile.consume",
                "summary_or_cache_called": False,
            },
            "raw_rows_exported": 0, "target_statistics_computed": 0,
            "fits": 0, "provider_calls": 0,
        }

    def test_policy_is_exact_and_failure_does_not_leak_values(self):
        self.assertEqual(validate_policy(dict(RESOURCE_POLICY)), RESOURCE_POLICY)
        changed = dict(RESOURCE_POLICY)
        changed["max_entities"] += 1
        with self.assertRaises(ValueError):
            validate_policy(changed)
        self.assertEqual(bounded_failure(ValueError(
            "selected source timestamp outside declared day; no silent filtering")), {
                "type": "ValueError",
                "reason": "selected source timestamp outside declared day; no silent filtering",
            })
        self.assertEqual(bounded_failure(ValueError("private-token=abc"))["reason"],
                         "unexpected_failure")

    def test_operation_uses_session_midnight_and_exact_resource_policy(self):
        value = operation(self.row(), {"frozen": "contract"})
        self.assertEqual(value["day_start_ms"], midnight_ms("2026-09-10T00"))
        self.assertEqual(value["resource_policy"], RESOURCE_POLICY)
        self.assertTrue(value["path"].endswith("polymarket-20260910T00.jsonl.zst"))

    def test_report_requires_complete_semantics_and_zero_scoring(self):
        self.assertTrue(validate_report(self.row(), self.report()))
        for mutate in ("target_statistics_computed", "fits", "provider_calls"):
            bad = self.report()
            bad[mutate] = 1
            with self.assertRaises(ValueError):
                validate_report(self.row(), bad)
        bad = self.report()
        bad["semantic_receipt"]["selected_observations"] = 0
        with self.assertRaises(ValueError):
            validate_report(self.row(), bad)

    def test_exact_kernel_ignores_old_rest_but_rejects_selected_old_ws(self):
        old_rest = message(T - 1)
        old_rest["t"] = T
        old_rest["src"] = "rest"
        profile = CacheProfile(contract(), T)
        profile.consume(json.dumps(old_rest).encode(), 1)
        self.assertEqual(profile.counts["excluded_kind_messages"], 1)
        self.assertEqual(profile.counts["selected_observations"], 0)

        old_ws = message(T - 1)
        old_ws["t"] = T
        with self.assertRaisesRegex(ValueError, "selected source timestamp outside"):
            profile.consume(json.dumps(old_ws).encode(), 2)

    def test_contract_loader_accepts_only_contract_or_profile_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            direct = root / "direct.json"
            direct.write_text(json.dumps({"a": 1}))
            self.assertEqual(contract_from(direct), {"a": 1})
            nested = root / "nested.json"
            nested.write_text(json.dumps({"spec": {"contract": {"b": 2}}}))
            self.assertEqual(contract_from(nested), {"b": 2})


if __name__ == "__main__":
    unittest.main()
