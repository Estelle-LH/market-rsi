from copy import deepcopy
import unittest

from market_rsi import digest
from memory_policy.spec import ARM_DEFINITIONS
from memory_policy.spec_v2 import RETRY_POLICY, SOURCE_INTEGRITY, validate


def rows(day, start, count):
    return [{"session": f"2026-01-{day:02d}T{hour:02d}",
             "compressed_bytes": hour + 1}
            for hour in range(start, start + count)]


def valid_spec():
    arms = deepcopy(ARM_DEFINITIONS)
    return {
        "schema": "market_rsi_memory_policy_v2",
        "experiment_id": "fixture-memory-policy-v2-01",
        "question": "Which controller memory representation works best?",
        "changed_stage": "controller_memory_representation",
        "arms": arms,
        "component_hashes": {name: digest({"arm": name, **definition,
            "all_other_inputs": "identical"}) for name, definition in arms.items()},
        "fixed_contract": {
            "target_contract_sha256": "a" * 64,
            "target": "causal variable-span quote-midpoint change",
            "horizon_seconds": 60,
            "latency": "frozen", "costs": "not applicable to prediction MSE",
            "row_policy": "same eligible rows", "controller_model": "frozen GLM",
            "harness": "frozen Codex harness", "seed": 23,
            "candidate_library": "same library",
            "trainer_selection": "same frozen Train-only library",
            "normalizer_selection": "same frozen Train-only library",
            "rounds": 8, "candidate_attempts_per_round": 3,
            "final_metric": "equal-session mean squared error",
            "pnl_policy": "not measured",
        },
        "source_integrity": deepcopy(SOURCE_INTEGRITY),
        "candidate_admission": {
            "schema": "memory_policy_candidate_admission_v1",
            "artifact_sha256": "b" * 64,
            "selection_rule": "first passing candidates in each ordered group; no target statistics",
            "target_statistics_computed": 0, "provider_calls": 0,
        },
        "initial_train": rows(1, 0, 3),
        "dev": rows(2, 0, 8),
        "final": rows(3, 0, 20),
        "rounds": 8, "minimum_final_sessions": 20,
        "formal_promotion": False,
        "stop_policy": {"planned_rounds": 8, "performance_early_stop": False,
                        "stop_before_unaffordable_atomic_triple": True,
                        "no_score_retry": True},
        "retry_policy": deepcopy(RETRY_POLICY),
        "budget": {"existing_global_cap_usd": "200", "new_authorization_usd": "0",
                   "paid_component": "GLM controller turns only",
                   "atomic_unit": "fresh plus archive plus compact controller sessions",
                   "unused_reservation_is_not_spend": True},
        "prior_exposure": {"opened_sessions": []},
        "claim_limits": {
            "distinct_final_utc_dates": 4,
            "evidence_class": "three-arm semantically admitted hourly memory-policy experiment",
            "formal_promotion_claim": False,
            "general_rsi_claim": False,
            "profitability_claim": False,
        },
    }


class SpecV2Tests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(valid_spec())["rounds"], 8)

    def test_source_and_retry_policy_are_not_runtime_choices(self):
        value = valid_spec()
        value["source_integrity"]["semantic_checks"] = "weaker"
        with self.assertRaises(ValueError):
            validate(value)
        value = valid_spec()
        value["retry_policy"]["result_retry"] = True
        with self.assertRaises(ValueError):
            validate(value)

    def test_opened_session_and_bad_admission_are_rejected(self):
        value = valid_spec()
        value["prior_exposure"]["opened_sessions"] = [value["final"][0]["session"]]
        with self.assertRaises(ValueError):
            validate(value)
        value = valid_spec()
        value["candidate_admission"]["target_statistics_computed"] = 1
        with self.assertRaises(ValueError):
            validate(value)


if __name__ == "__main__":
    unittest.main()
