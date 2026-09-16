import tempfile
import unittest
from pathlib import Path

from market_rsi import digest, file_hash
from data_scientist_harness.research_cycle_contract import (
    begin_discovery,
    complete_discovery,
    freeze_confirmation,
)
from data_scientist_harness.sealed_dev_gate import SealedDevGate, data_commitment


def sha(character: str) -> str:
    return character * 64


class SealedDevGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.train = self.base / "train.json"; self.train.write_text("train rows\n")
        self.dev = self.base / "dev.json"; self.dev.write_text("secret held-out rows\n")
        self.eligibility = self.base / "eligible.json"; self.eligibility.write_text("fixed cohort\n")
        self.evaluator = self.base / "evaluator.py"; self.evaluator.write_text("# frozen score\n")
        release = {"harness_version": "h1", "release_sha256": sha("a"),
            "commit": "b" * 40, "tag": "h1", "published": True,
            "canary_sha256": sha("c")}
        session = begin_discovery(release, {
            "discovery_id": "d1", "broad_problem": "open research",
            "allowed_research_types": ["data_discovery", "algorithm_design"],
            "accessible_data_roles": ["opened_train"], "maximum_iterations": 3,
            "maximum_cost_usd": 0.0, "required_outputs": ["trace", "candidates"],
            "primary_reward": None, "formal_claims_allowed": False,
            "route_dev_access": False, "sealed_final_access": False,
        })
        completed = complete_discovery(session, {
            "discovery_id": "d1", "trace_sha256": sha("d"),
            "opened_data_hashes": {"train": file_hash(self.train)},
            "literature_record_ids": [], "candidate_graphs": [{
                "candidate_id": "candidate", "research_type": "algorithm_design",
                "question": "Does it help?", "method": "Frozen candidate",
                "evidence_refs": ["train"], "evaluation_idea": "One untouched Dev view",
                "previously_untried_in_project": True,
            }], "iterations_completed": 1, "cost_usd": 0.0,
            "route_dev_opened": False, "sealed_final_opened": False,
            "terminal_cleanup_passed": True,
        })
        self.confirmation = freeze_confirmation(completed, {
            "confirmation_id": "c1", "selected_candidate_id": "candidate",
            "research_question": "Does it help?", "claim_type": "prediction",
            "baseline_id": "frozen-baseline", "primary_metric": "paired_mse_delta",
            "reward_direction": "minimize", "target_spec_sha256": sha("2"),
            "evaluator_spec_sha256": file_hash(self.evaluator),
            "eligible_data_sha256": file_hash(self.eligibility),
            "untouched_data_role": "route_dev_one_shot",
            "secondary_metrics": ["positive_game_fraction"],
            "constraints": ["same rows"], "disqualifiers": ["second Dev view"],
            "maximum_cost_usd": 0.0, "maximum_evaluation_uses": 1,
            "reward_locked_before_results": True,
            "reward_change_after_results_allowed": False,
            "evaluation_evidence_output": {
                "kind": "paired_grouped_loss_v1", "unit": "game", "block": "UTC_date", "loss": "equal_game_mse",
                "delta": "candidate_minus_baseline", "reward_direction": "minimize",
                "persist_unit_records_runner_private": True,
                "public_visibility": "aggregate_only", "bootstrap_draws": 1000,
                "bootstrap_seed": 23, "top_k_units": [1, 5],
            },
        })

    def tearDown(self):
        self.tmp.cleanup()

    def freeze(self):
        gate = SealedDevGate.reserve(self.base / "gate", self.confirmation,
                                     self.eligibility, self.evaluator)
        gate.register_materialization({"dev": self.dev}, {
            "eligible_data_sha256": file_hash(self.eligibility),
            "selection_count": 1, "materialized_count": 1, "excluded_count": 0,
            "scored": False, "labels_summarized": False,
            "source_manifest_sha256": sha("8"),
        })
        return gate

    def test_public_commitment_hides_dev_paths_and_values(self):
        gate = self.freeze()
        text = (gate.public / "confirmation-commitment.json").read_text()
        self.assertNotIn(str(self.dev), text)
        self.assertNotIn("secret held-out rows", text)

    def test_reward_and_cohort_can_freeze_before_materialization(self):
        gate = SealedDevGate.reserve(self.base / "gate", self.confirmation,
                                     self.eligibility, self.evaluator)
        self.assertFalse((gate.private / "dev-manifest.json").exists())
        gate.register_materialization({"dev": self.dev}, {
            "eligible_data_sha256": file_hash(self.eligibility),
            "selection_count": 1, "materialized_count": 1, "excluded_count": 0,
            "scored": False, "labels_summarized": False,
            "source_manifest_sha256": sha("8"),
        })
        self.assertTrue((gate.private / "dev-manifest.json").exists())

    def test_materialization_cannot_drop_a_selected_member(self):
        gate = SealedDevGate.reserve(self.base / "gate", self.confirmation,
                                     self.eligibility, self.evaluator)
        with self.assertRaisesRegex(ValueError, "every preregistered"):
            gate.register_materialization({"dev": self.dev}, {
                "eligible_data_sha256": file_hash(self.eligibility),
                "selection_count": 2, "materialized_count": 1, "excluded_count": 1,
                "scored": False, "labels_summarized": False,
                "source_manifest_sha256": sha("8"),
            })

    def test_materialization_count_must_match_committed_files(self):
        gate = SealedDevGate.reserve(self.base / "gate", self.confirmation,
                                     self.eligibility, self.evaluator)
        with self.assertRaisesRegex(ValueError, "exactly one committed file"):
            gate.register_materialization({"dev": self.dev}, {
                "eligible_data_sha256": file_hash(self.eligibility),
                "selection_count": 2, "materialized_count": 2, "excluded_count": 0,
                "scored": False, "labels_summarized": False,
                "source_manifest_sha256": sha("8"),
            })

    def test_materialization_source_hash_must_be_hex(self):
        gate = SealedDevGate.reserve(self.base / "gate", self.confirmation,
                                     self.eligibility, self.evaluator)
        with self.assertRaisesRegex(ValueError, "source manifest hash"):
            gate.register_materialization({"dev": self.dev}, {
                "eligible_data_sha256": file_hash(self.eligibility),
                "selection_count": 1, "materialized_count": 1, "excluded_count": 0,
                "scored": False, "labels_summarized": False,
                "source_manifest_sha256": "z" * 64,
            })

    def test_claim_is_consumed_before_a_second_view(self):
        gate = self.freeze()
        first = gate.claim_once("eval-1")
        self.assertEqual(first["dev_files"], {"dev": str(self.dev)})
        with self.assertRaisesRegex(ValueError, "already consumed"):
            gate.claim_once("eval-2")

    def test_dev_mutation_after_freeze_fails_closed(self):
        gate = self.freeze(); self.dev.write_text("changed after freeze\n")
        with self.assertRaisesRegex(ValueError, "changed after freeze"):
            gate.claim_once("eval-1")

    def test_evaluator_mutation_after_freeze_fails_closed(self):
        gate = self.freeze(); self.evaluator.write_text("# changed score\n")
        with self.assertRaisesRegex(ValueError, "evaluator changed"):
            gate.claim_once("eval-1")

    def test_result_is_bound_and_terminal_once(self):
        gate = self.freeze(); gate.claim_once("eval-1")
        result = {"paired_mse_delta": -0.01}
        receipt = gate.record_result("eval-1", result)
        self.assertEqual(receipt["result_sha256"], digest(result))
        with self.assertRaisesRegex(ValueError, "already has"):
            gate.record_result("eval-1", result)


if __name__ == "__main__":
    unittest.main()
