from copy import deepcopy
import unittest

from memory_policy.spec_v2 import RETRY_POLICY, SOURCE_INTEGRITY
from memory_policy.spec_v3 import TRAINER_RESOURCE_GATE, validate
from memory_policy.test_spec_v2 import valid_spec as valid_v2


def hourly(day, count):
    return [{"session": f"2026-01-{day:02d}T{hour:02d}",
             "compressed_bytes": hour + 1}
            for hour in range(count)]


def valid_spec():
    value = valid_v2()
    value.update({
        "schema": "market_rsi_memory_policy_v3",
        "experiment_id": "fixture-memory-policy-v3-01",
        "candidate_admission": {
            "schema": "memory_policy_score_free_reselection_v1",
            "artifact_sha256": "b" * 64,
            "source_admission_sha256": "c" * 64,
            "selection_rule": "No target statistic or score selects a source.",
            "target_statistics_computed": 0,
            "fits": 0,
            "provider_calls": 0,
        },
        "trainer_resource_gate": deepcopy(TRAINER_RESOURCE_GATE),
        "supersedes": {
            "experiment_id": "memory-policy-v2-20260915-01",
            "failure_decision": "invalidate_run_and_redesign",
            "failure_decision_sha256":
                "0d1f2fbf9af7e8d051f9aae91f8c3d36b8b02f60b82f01e29295519431bcebd9",
            "opened_dev_sessions": ["2026-09-10T22", "2026-09-10T23"],
            "artifacts_reused_for_training": False,
        },
        "initial_train": hourly(1, 3),
        "dev": hourly(2, 8),
        "final": sum((hourly(day, 5) for day in range(3, 7)), []),
        "source_integrity": deepcopy(SOURCE_INTEGRITY),
        "retry_policy": deepcopy(RETRY_POLICY),
        "prior_exposure": {"opened_sessions": [
            "2026-09-10T22", "2026-09-10T23"]},
        "claim_limits": {
            "distinct_final_utc_dates": 4,
            "evidence_class":
                "three-arm semantically admitted hourly memory-policy resource-repaired rerun",
            "formal_promotion_claim": False,
            "general_rsi_claim": False,
            "profitability_claim": False,
        },
    })
    return value


class SpecV3Tests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(valid_spec())["rounds"], 8)

    def test_old_opened_dev_cannot_return(self):
        value = valid_spec()
        value["dev"][0] = {"session": "2026-09-10T22",
                           "compressed_bytes": 1}
        with self.assertRaises(ValueError):
            validate(value)

    def test_resource_gate_and_nonreuse_are_frozen(self):
        value = valid_spec()
        value["trainer_resource_gate"]["silent_subsampling"] = True
        with self.assertRaises(ValueError):
            validate(value)
        value = valid_spec()
        value["supersedes"]["artifacts_reused_for_training"] = True
        with self.assertRaises(ValueError):
            validate(value)


if __name__ == "__main__":
    unittest.main()
