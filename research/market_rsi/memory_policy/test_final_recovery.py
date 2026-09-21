import json
from pathlib import Path
import unittest

from memory_pilot.materialize import CacheProfile
from memory_policy.final_recovery import (
    ROOT, validate_recovery_spec, verify_source_run, worker_program,
)
from memory_policy.recovery_worker import safe_failure, validate_limits
from test_typed_raw_profile import T, contract, message


SPEC = ROOT / "MEMORY_POLICY_FINAL_RECOVERY_SPEC_2026-09-14.json"


class FinalRecoveryTests(unittest.TestCase):
    def test_exact_spec_and_limits(self):
        value = json.loads(SPEC.read_text())
        self.assertEqual(validate_recovery_spec(value)["recovery_id"],
                         "memory-policy-final-recovery-20260914-01")
        self.assertEqual(validate_limits(value["resource_policy"])
                         ["max_total_observations"], 12000000)
        changed = dict(value["resource_policy"])
        changed["max_total_observations"] += 1
        with self.assertRaises(ValueError):
            validate_limits(changed)

    def test_consumer_failure_is_bounded_and_non_row_bearing(self):
        self.assertEqual(safe_failure(ValueError(
            "row resource limit; no silent truncation")), {
                "type": "ValueError",
                "reason": "row resource limit; no silent truncation",
            })
        self.assertEqual(safe_failure(ValueError("secret raw token"))["reason"],
                         "unexpected_failure")

    def test_total_observation_limit_is_explicitly_replaceable(self):
        low = CacheProfile(contract(), T, max_total_rows=1)
        low.consume(json.dumps(message(T)).encode(), 1)
        with self.assertRaisesRegex(ValueError, "row resource limit"):
            low.consume(json.dumps(message(T + 1)).encode(), 2)
        high = CacheProfile(contract(), T, max_total_rows=2)
        high.consume(json.dumps(message(T)).encode(), 1)
        high.consume(json.dumps(message(T + 1)).encode(), 2)
        self.assertEqual(high.counts["selected_observations"], 2)

    def test_worker_program_binds_recovery_worker_and_no_controller(self):
        value = json.loads(SPEC.read_text())
        operation = {
            "date": "2099-01-01T00", "path": "/tmp/x", "output": "/tmp/y",
            "compressed_bytes": 1, "contract": contract(), "day_start_ms": T,
            "role": "diagnostic_canary", "source_integrity_receipt": {},
            "resource_policy": value["resource_policy"],
            "frozen_model_commitment": {"diagnostic_only": True},
        }
        body = worker_program(operation).decode()
        self.assertIn("memory_policy_final_recovery_materialize_v1", body)
        self.assertNotIn("TinkerGLMBackend", body)

    def test_preserved_source_run_has_no_final_score_and_frozen_models(self):
        source_run = ROOT / "artifacts/memory-policy-20260914-01"
        source_preflight = ROOT / "artifacts/source-preflight-memory-policy-20260914-01"
        if not source_run.exists() and not source_preflight.exists():
            self.skipTest(
                "preserved runtime artifacts are not installed in this source-only checkout")
        source = verify_source_run(validate_recovery_spec(json.loads(SPEC.read_text())))
        self.assertEqual(len(source["original_spec"]["final"]), 20)
        self.assertEqual(set(source["models"]), {"fresh", "archive", "compact", "baseline"})
        self.assertIsNone(source["failed_report"]["header"])


if __name__ == "__main__":
    unittest.main()
