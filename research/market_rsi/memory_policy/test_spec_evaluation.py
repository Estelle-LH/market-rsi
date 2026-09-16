from copy import deepcopy
import unittest

from market_rsi import digest
from memory_policy.evaluation import ARMS, summarize
from memory_policy.spec import ARM_DEFINITIONS, validate


def rows(start, count, size=10):
    return [{"session": f"2026-01-{start + i:02d}T12", "compressed_bytes": size + i}
            for i in range(count)]


def valid_spec():
    arms = deepcopy(ARM_DEFINITIONS)
    return {
        "schema": "market_rsi_memory_policy_v1",
        "experiment_id": "fixture-memory-policy-01",
        "question": "Which controller memory representation works best?",
        "changed_stage": "controller_memory_representation",
        "arms": arms,
        "component_hashes": {name: digest({"arm": name, **definition,
            "all_other_inputs": "identical"}) for name, definition in arms.items()},
        "fixed_contract": {
            "target_contract_sha256": "a" * 64,
            "target": "causal variable-span quote-midpoint change",
            "horizon_seconds": 60,
            "latency": "frozen",
            "costs": "not applicable to prediction MSE",
            "row_policy": "same eligible rows",
            "controller_model": "frozen GLM",
            "harness": "frozen Codex harness",
            "seed": 23,
            "candidate_library": "same library",
            "trainer_selection": "same frozen Train-only library",
            "normalizer_selection": "same frozen Train-only library",
            "rounds": 8,
            "candidate_attempts_per_round": 3,
            "final_metric": "equal-session mean squared error",
            "pnl_policy": "not measured",
        },
        "source_integrity": {
            "scope": "all initial Train, rolling Dev and Final objects",
            "timing": "complete before first paid controller call",
            "checks": "full zstd decode, every-line JSON parse, bytes, compressed and decoded hashes, start/end file identity",
            "controller_visibility": "receipt metadata only; no source rows or target statistics",
            "materialization_binding": "must reproduce the preflight receipt",
            "failure_action": "stop before paid work; select a new manifest, never post-score replacement",
        },
        "initial_train": rows(1, 3),
        "dev": rows(4, 8),
        "final": rows(12, 20),
        "rounds": 8,
        "minimum_final_sessions": 20,
        "formal_promotion": False,
        "stop_policy": {
            "planned_rounds": 8,
            "performance_early_stop": False,
            "stop_before_unaffordable_atomic_triple": True,
            "no_score_retry": True,
        },
        "budget": {
            "existing_global_cap_usd": "200",
            "new_authorization_usd": "0",
            "paid_component": "GLM controller turns only",
            "atomic_unit": "fresh plus archive plus compact controller sessions",
            "unused_reservation_is_not_spend": True,
        },
        "prior_exposure": {"opened_sessions": []},
        "claim_limits": {"profitability": False},
    }


def score(date, mse, n=10):
    return {"date": date, "candidate_mse": mse, "n": n,
            "pearson_ic": 0.1, "rank_ic": 0.05, "calibration_slope": 1.0}


class SpecAndEvaluationTests(unittest.TestCase):
    def test_valid_three_arm_spec(self):
        self.assertEqual(validate(valid_spec())["rounds"], 8)

    def test_only_memory_and_unopened_future_data_can_change(self):
        value = valid_spec()
        value["arms"]["compact"]["prior_own_round_memory"] = "model_summary"
        with self.assertRaises(ValueError):
            validate(value)
        value = valid_spec()
        value["prior_exposure"]["opened_sessions"] = [value["final"][0]["session"]]
        with self.assertRaises(ValueError):
            validate(value)

    def test_final_summary_is_equal_session_primary(self):
        sessions = []
        for index in range(20):
            date = f"2026-02-{index + 1:02d}T12"
            sessions.append({arm: score(date, index + offset, n=1 if index == 0 else 100)
                             for arm, offset in zip(ARMS, (0.0, 1.0, -1.0, 2.0))})
        result = summarize(sessions)
        self.assertEqual(result["final_sessions"], 20)
        self.assertEqual(result["primary_equal_session_mse"]["compact"], 8.5)
        self.assertEqual(result["pairwise"]["fresh_minus_compact"]
                         ["equal_session_mean_delta"], 1.0)
        self.assertEqual(result["pairwise"]["fresh_minus_compact"]
                         ["left_better_session_fraction"], 0.0)
        self.assertTrue(result["multiple_pairwise_comparisons_exploratory"])

    def test_incomplete_or_row_mismatched_final_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize([])
        sessions = []
        for index in range(20):
            date = f"2026-02-{index + 1:02d}T12"
            sessions.append({arm: score(date, 1.0) for arm in ARMS})
        sessions[-1]["compact"]["n"] = 9
        with self.assertRaises(ValueError):
            summarize(sessions)


if __name__ == "__main__":
    unittest.main()
