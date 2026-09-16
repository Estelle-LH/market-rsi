"""Offline tests for the fixed first Reset/Archive/Learn protocol."""
import copy
import unittest
from pathlib import Path

from market_rsi import digest, file_hash
from polymarket_round1_protocol import build_protocol, validate_protocol, validate_study_binding


class Round1ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.experiment = "polymarket-rsi-round1-20260907-01"
        self.tasks = [f"pm-r1-task-{index:02d}" for index in range(9)]
        self.protocol = build_protocol(experiment_id=self.experiment, task_ids=self.tasks,
                                       opaque_test_commitment="a" * 64)

    def changed(self, path, value):
        obj = copy.deepcopy(self.protocol)
        target = obj
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return obj

    def test_valid_protocol_has_fixed_schedule_and_sub_fifty_upper(self):
        result = validate_protocol(self.protocol)
        self.assertTrue(result["valid"])
        self.assertEqual(result["protocol_sha256"], digest(self.protocol))
        self.assertLessEqual(float(result["total_metered_upper_usd"]), 50.0)
        self.assertEqual(self.protocol["schedule"]["maximum_candidate_executions"], 54)
        self.assertEqual(self.protocol["schedule"]["maximum_diagnostic_executions"], 27)
        self.assertEqual(self.protocol["schedule"]["maximum_failed_or_replacement_calls"], 27)
        self.assertEqual(self.protocol["budget"]["proposal_model_calls"], 108)
        self.assertEqual(self.protocol["budget"]["selection_model_calls"], 27)
        self.assertEqual(self.protocol["response_policy"]["omitted_guide_update"],
                         "normalize_to_null")

    def test_canonical_json_key_sorting_does_not_change_protocol_validity(self):
        import json
        restored = json.loads(json.dumps(self.protocol, sort_keys=True))
        self.assertTrue(validate_protocol(restored)["valid"])

    def test_rejects_task_count_phase_order_or_arm_order_drift(self):
        cases = [
            self.changed(["tasks"], self.protocol["tasks"][:-1]),
            self.changed(["tasks", 5, "phase"], "transfer"),
            self.changed(["arms"], ["archive", "reset", "learn"]),
            self.changed(["arm_task_order", "reset"], list(reversed(self.tasks))),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_protocol(case)

    def test_rejects_more_proposals_selection_calls_or_resampling(self):
        cases = [
            self.changed(["schedule", "max_candidate_proposals_per_task"], 3),
            self.changed(["schedule", "max_diagnostics_per_task"], 2),
            self.changed(["schedule", "selection_calls_per_task"], 2),
            self.changed(["response_policy", "samples_per_claim"], 2),
            self.changed(["response_policy", "automatic_retries"], 1),
            self.changed(["response_policy", "invalid_or_timeout_is_outcome"], False),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_protocol(case)

    def test_rejects_memory_contrast_drift(self):
        cases = [
            self.changed(["memory_policy", "reset", "prior_learning_records"],
                         "complete_own_train_dev"),
            self.changed(["memory_policy", "archive", "guide"],
                         "latest_agent_revision_with_owned_evidence"),
            self.changed(["memory_policy", "learn", "guide"], "none"),
            self.changed(["memory_policy", "learn", "prior_transfer_records"],
                         "complete_own_train_dev"),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_protocol(case)

    def test_rejects_test_visibility_cross_arm_or_second_open(self):
        cases = [
            self.changed(["visibility_policy", "model_visible_splits"], ["train", "dev", "test"]),
            self.changed(["visibility_policy", "test_representation"], "path"),
            self.changed(["visibility_policy", "test_open_count"], 2),
            self.changed(["visibility_policy", "minimum_test_unique_complete_game_ids"], 19),
            self.changed(["visibility_policy", "prospective_source_boundary_utc"],
                         "2026-09-07T16:08:42Z"),
            self.changed(["visibility_policy", "cross_arm_records_visible"], True),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_protocol(case)

    def test_rejects_multi_stage_or_dispatch_ownership_drift(self):
        cases = [
            self.changed(["causal_policy", "changed_stages_per_proposal"], 2),
            self.changed(["causal_policy", "external_target_frozen"], False),
            self.changed(["dispatch_policy", "authority"], "researcher"),
            self.changed(["dispatch_policy", "maximum_concurrent_paid_dispatches"], 2),
            self.changed(["dispatch_policy", "subagents_may_dispatch"], True),
            self.changed(["dispatch_policy", "researcher_tools"], ["shell"]),
            self.changed(["dispatch_policy", "host_can_select_candidate"], True),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_protocol(case)

    def test_rejects_false_or_over_cap_cost_accounting(self):
        with self.assertRaises(ValueError):
            validate_protocol(self.changed(["budget", "total_metered_upper_usd"], "1"))
        with self.assertRaises(ValueError):
            build_protocol(experiment_id=self.experiment, task_ids=self.tasks,
                           opaque_test_commitment="a" * 64,
                           sandbox_upper_per_proposal_usd="1")
        with self.assertRaises(ValueError):
            build_protocol(experiment_id=self.experiment, task_ids=self.tasks,
                           opaque_test_commitment="a" * 64, pilot_cap_usd="51")

    def bound_artifacts(self):
        manifest_tasks = []
        for declared in self.protocol["tasks"]:
            manifest_tasks.append({**declared,
                "schema": "market_research_task_v1", "experiment_id": self.experiment,
                "objective": "fixture",
                "data_catalog": [
                    {"artifact_id": declared["task_id"] + "-train", "split": "train"},
                    {"artifact_id": declared["task_id"] + "-dev", "split": "dev"},
                ],
                "evaluation_contract": {"fixture": True},
                "resource_limits": copy.deepcopy(self.protocol["resource_limits"]),
                "opaque_test_commitment": "a" * 64})
        manifest = {"experiment_id": self.experiment,
            "arms": ["archive", "learn", "reset"], "tasks": manifest_tasks,
            "max_steps_per_task": 2, "max_diagnostics_per_task": 1,
            "max_research_calls_per_task": 4,
            "selection_policy": {"after_scoreable_candidates": 2,
                "max_diagnostic_attempts": 1, "max_research_calls": 4,
                "selection_trigger": "target_scoreable_candidates_or_call_cap", "calls_per_task": 1,
                "invalid_output": "common_baseline", "guide_update": False}}
        runner = {"schema": "market_study_runner_v1", "experiment_id": self.experiment,
            "study_manifest_sha256": digest(manifest), "live": True,
            "scientific_admission": False,
            "source_hashes": {name: file_hash(Path(__file__).parents[1] / name) for name in
                ("study_runner.py", "study_state.py", "researcher_worker.py",
                 "selection_protocol.py")},
            "task_data": {task: {"train_id": task + "-train", "train_path": "/opaque/train",
                                  "dev_id": task + "-dev", "dev_path": "/opaque/dev"}
                          for task in self.tasks}}
        budget = {"experiment_id": self.experiment, "cap_usd": "50",
                  "effective_cost_usd": "0", "reserved_usd": "0"}
        return manifest, runner, budget

    def test_binding_accepts_fresh_runner_owned_train_dev_only_artifacts(self):
        manifest, runner, budget = self.bound_artifacts()
        result = validate_study_binding(self.protocol, manifest, runner, budget)
        self.assertTrue(result["bound"])
        self.assertFalse(result["scientific_admission"])

    def test_binding_rejects_test_path_nonrunner_or_nonfresh_budget(self):
        manifest, runner, budget = self.bound_artifacts()
        bad_test = copy.deepcopy(runner)
        bad_test["task_data"][self.tasks[0]]["test_path"] = "/hidden/test"
        bad_authority = copy.deepcopy(runner)
        bad_authority["source_hashes"].pop("study_runner.py")
        spent = dict(budget, effective_cost_usd="0.01")
        for args in ((manifest, bad_test, budget), (manifest, bad_authority, budget),
                     (manifest, runner, spent)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_study_binding(self.protocol, *args)


if __name__ == "__main__":
    unittest.main()
