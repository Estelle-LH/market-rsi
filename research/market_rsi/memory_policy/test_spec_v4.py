from copy import deepcopy
import unittest

from memory_policy.spec_v4 import (
    TERMINAL_CAPACITY_GATE, V3_FAILURE_SHA256, V3_OPENED_DEV, validate,
)
from memory_policy.test_spec_v3 import hourly, valid_spec as valid_v3


def valid_spec():
    value = valid_v3()
    value.update({
        "schema": "market_rsi_memory_policy_v4",
        "experiment_id": "fixture-memory-policy-v4-01",
        "candidate_admission": {
            "schema": "memory_policy_candidate_admission_v1",
            "artifact_sha256": "d" * 64,
            "selection_rule":
                "first passing candidates in each ordered group; no target statistics",
            "target_statistics_computed": 0,
            "fits": 0,
            "provider_calls": 0,
        },
        "terminal_capacity_gate": deepcopy(TERMINAL_CAPACITY_GATE),
        "supersedes": {
            "experiment_id": "memory-policy-v3-20260915-01",
            "failure_status": "invalidated_no_same_run_retry",
            "failure_disposition_sha256": V3_FAILURE_SHA256,
            "opened_dev_sessions": list(V3_OPENED_DEV),
            "artifacts_reused_for_training": False,
            "scientific_change": "none",
            "shared_harness_fix": "controller_terminal_submission_capacity",
        },
        "initial_train": hourly(1, 3),
        "dev": hourly(2, 8),
        "final": sum((hourly(day, 5) for day in range(3, 7)), []),
        "prior_exposure": {"opened_sessions": list(V3_OPENED_DEV)},
        "claim_limits": {
            "distinct_final_utc_dates": 4,
            "evidence_class":
                "three-arm fresh-evidence terminal-capacity-repaired memory-policy rerun",
            "formal_promotion_claim": False,
            "general_rsi_claim": False,
            "profitability_claim": False,
        },
    })
    return value


class SpecV4Tests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(valid_spec())["rounds"], 8)

    def test_terminal_repair_is_shared_and_model_authored(self):
        value = valid_spec()
        value["terminal_capacity_gate"]["same_for_all_arms"] = False
        with self.assertRaises(ValueError):
            validate(value)
        value = valid_spec()
        value["terminal_capacity_gate"]["prose_to_submission_conversion"] = True
        with self.assertRaises(ValueError):
            validate(value)

    def test_v3_evidence_and_artifacts_cannot_return(self):
        value = valid_spec()
        value["dev"][0] = {"session": V3_OPENED_DEV[0], "compressed_bytes": 1}
        with self.assertRaises(ValueError):
            validate(value)
        value = valid_spec()
        value["supersedes"]["artifacts_reused_for_training"] = True
        with self.assertRaises(ValueError):
            validate(value)

    def test_requires_exact_fresh_split(self):
        value = valid_spec()
        value["final"].pop()
        with self.assertRaises(ValueError):
            validate(value)


if __name__ == "__main__":
    unittest.main()
