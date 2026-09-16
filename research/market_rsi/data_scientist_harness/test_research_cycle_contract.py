import unittest

from data_scientist_harness.research_cycle_contract import (
    begin_confirmation,
    begin_discovery,
    complete_discovery,
    freeze_confirmation,
)


def sha(char):
    return char * 64


def release():
    return {
        "harness_version": "h1",
        "release_sha256": sha("a"),
        "commit": "b" * 40,
        "tag": "h1",
        "published": True,
        "canary_sha256": sha("c"),
    }


def discovery_plan():
    return {
        "discovery_id": "d1",
        "broad_problem": "Find useful research directions for prediction-market learning.",
        "allowed_research_types": ["data_discovery", "prediction", "algorithm_design"],
        "accessible_data_roles": ["opened_train", "public_literature", "frozen_archive"],
        "maximum_iterations": 20,
        "maximum_cost_usd": 30.0,
        "required_outputs": ["trace", "candidate_graphs", "negative_findings"],
        "primary_reward": None,
        "formal_claims_allowed": False,
        "route_dev_access": False,
        "sealed_final_access": False,
    }


def discovery_result():
    return {
        "discovery_id": "d1",
        "trace_sha256": sha("d"),
        "opened_data_hashes": {"train": sha("e")},
        "literature_record_ids": ["0042"],
        "candidate_graphs": [{
            "candidate_id": "new-representation",
            "research_type": "representation_learning",
            "question": "Can event sequences learn a more useful state representation?",
            "method": "Self-supervised event encoder followed by a frozen downstream probe.",
            "evidence_refs": ["0042", "train-profile"],
            "evaluation_idea": "Compare frozen probes on an untouched later game block.",
            "previously_untried_in_project": True,
        }],
        "iterations_completed": 8,
        "cost_usd": 4.0,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "terminal_cleanup_passed": True,
    }


def confirmation_contract():
    return {
        "confirmation_id": "c1",
        "selected_candidate_id": "new-representation",
        "research_question": "Does the event representation improve a frozen downstream probe?",
        "claim_type": "out_of_sample_prediction",
        "baseline_id": "unchanged-parent-representation",
        "primary_metric": "equal_game_mse_delta",
        "reward_direction": "minimize",
        "target_spec_sha256": sha("2"),
        "evaluator_spec_sha256": sha("f"),
        "eligible_data_sha256": sha("1"),
        "untouched_data_role": "route_dev_one_shot",
        "secondary_metrics": ["calibration_slope", "positive_game_fraction"],
        "constraints": ["same rows", "same downstream probe", "same cost"],
        "disqualifiers": ["leakage", "missing predictions", "second Dev view"],
        "maximum_cost_usd": 20.0,
        "maximum_evaluation_uses": 1,
        "reward_locked_before_results": True,
        "reward_change_after_results_allowed": False,
        "evaluation_evidence_output": {
            "kind": "paired_grouped_loss_v1", "unit": "game", "block": "UTC_date", "loss": "equal_game_mse",
            "delta": "candidate_minus_baseline", "reward_direction": "minimize",
            "persist_unit_records_runner_private": True,
            "public_visibility": "aggregate_only", "bootstrap_draws": 1000,
            "bootstrap_seed": 23, "top_k_units": [1, 5],
        },
    }


def experiment_claim(frozen):
    return {
        "experiment_id": "e1-confirmation",
        "harness_release_sha256": frozen["release"]["release_sha256"],
        "harness_commit": frozen["release"]["commit"],
        "pre_score_lock_sha256": frozen["record_sha256"],
        "planned_inner_rounds": 1,
        "artifact_root": "artifacts/e1-confirmation",
        "route_dev_policy": "one_shot_after_train_selection",
        "final_policy": "sealed_until_terminal_acceptance",
    }


class ResearchCycleContractTests(unittest.TestCase):
    def setUp(self):
        self.session = begin_discovery(release(), discovery_plan())
        self.completed = complete_discovery(self.session, discovery_result())
        self.frozen = freeze_confirmation(self.completed, confirmation_contract())

    def test_discovery_is_open_ended_without_performance_reward(self):
        self.assertTrue(self.session["questions_may_change"])
        self.assertTrue(self.session["targets_may_change_on_opened_data"])
        self.assertTrue(self.session["horizons_may_change_on_opened_data"])
        self.assertTrue(self.session["algorithms_may_be_invented"])
        self.assertIsNone(self.session["plan"]["primary_reward"])

    def test_discovery_cannot_access_dev(self):
        plan = discovery_plan(); plan["route_dev_access"] = True
        with self.assertRaisesRegex(ValueError, "Route-Dev"):
            begin_discovery(release(), plan)

    def test_opened_discovery_data_cannot_be_confirmation_data(self):
        contract = confirmation_contract(); contract["eligible_data_sha256"] = sha("e")
        with self.assertRaisesRegex(ValueError, "already opened"):
            freeze_confirmation(self.completed, contract)

    def test_confirmation_reward_is_frozen_before_experiment(self):
        started = begin_confirmation(self.frozen, experiment_claim(self.frozen))
        self.assertEqual(started["state"], "experiment_running")
        self.assertEqual(started["claim"]["pre_score_lock_sha256"], self.frozen["record_sha256"])

    def test_confirmation_requires_target_spec_including_horizon(self):
        contract = confirmation_contract(); contract.pop("target_spec_sha256")
        with self.assertRaisesRegex(ValueError, "exact schema"):
            freeze_confirmation(self.completed, contract)

    def test_confirmation_cannot_change_reward_after_results(self):
        contract = confirmation_contract(); contract["reward_change_after_results_allowed"] = True
        with self.assertRaisesRegex(ValueError, "next research cycle"):
            freeze_confirmation(self.completed, contract)

    def test_confirmation_freezes_private_paired_evidence_output(self):
        spec = self.frozen["contract"]["evaluation_evidence_output"]
        self.assertEqual(spec["unit"], "game")
        self.assertEqual(spec["public_visibility"], "aggregate_only")
        contract = confirmation_contract()
        contract["evaluation_evidence_output"]["public_visibility"] = "unit_rows"
        with self.assertRaisesRegex(ValueError, "identities"):
            freeze_confirmation(self.completed, contract)

    def test_confirmation_claim_must_bind_reward_contract(self):
        claim = experiment_claim(self.frozen); claim["pre_score_lock_sha256"] = sha("9")
        with self.assertRaisesRegex(ValueError, "frozen confirmation reward"):
            begin_confirmation(self.frozen, claim)


if __name__ == "__main__":
    unittest.main()
