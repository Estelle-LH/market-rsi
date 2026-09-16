import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data_scientist_harness.algorithm_invention_contract import FIELDS, SCHEMA, archive_proposal
from data_scientist_harness.broker import Broker, serve, validate_shape
from data_scientist_harness import fixtures
from data_scientist_harness.data_strengthening_contract import (
    admission_readiness,
    current_nfl_history_plan,
    plan_receipt,
)


def data_plan():
    return {
        "plan_id": "nfl-history-strengthening-v1",
        "parent_harness_version": "h0",
        "evidence_refs": ["artifacts/nfl-train-rsi-trajectory-20260915-01/trajectory.json"],
        "current_independent_units": 163,
        "independent_unit": "game",
        "minimum_total_units": 600,
        "minimum_seasons": 3,
        "candidate_sources": [{
            "source_id": "public-history",
            "venue": "polymarket",
            "coverage_start": "2021-01-01",
            "coverage_end": "2025-12-31",
            "access_path": "public archive plus verified on-chain/API reconstruction",
            "license_status": "needs_review",
            "sample_status": "received",
        }],
        "required_fields": [
            "game_id", "play_id", "play_observed_at", "trade_price", "trade_timestamp"
        ],
        "immutable_row_key": ["venue", "market_id", "game_id", "play_id", "trade_timestamp"],
        "timestamp_policy": "UTC; observed timestamps only; no future feature lookup",
        "alignment_policy": "last valid trade at/before play and exact forward 60s label tolerance",
        "minimum_target_coverage": 0.90,
        "regime_minimums": {"scoring_play": 300, "late_game": 300, "non_scoring_play": 300},
        "learning_curve_units": [163, 300, 600],
        "opened_periods": ["2021", "2022", "2023", "2024", "2025"],
        "reserved_periods": ["future-2026-holdout"],
        "maximum_cost_usd": 200.0,
        "external_actions_authorized": False,
        "train_only_admission": True,
    }


def batch(plan_sha):
    return {
        "batch_id": "history-batch-v1",
        "plan_sha256": plan_sha,
        "source_id": "public-history",
        "source_object_hashes": ["a" * 64],
        "license_allows_research_storage": True,
        "independent_units": 700,
        "season_count": 5,
        "row_count": 100000,
        "immutable_row_key_unique": True,
        "timestamps_utc": True,
        "timestamps_monotonic_within_unit": True,
        "duplicate_rate": 0.0,
        "missing_required_field_rate": 0.0,
        "target_coverage": 0.95,
        "alignment_success_rate": 0.95,
        "regime_counts": {"scoring_play": 400, "late_game": 400, "non_scoring_play": 10000},
        "opened_period_overlap_only": True,
        "reserved_period_overlap": False,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "raw_objects_preserved": True,
        "derived_rows_hash": "b" * 64,
        "cost_usd": 0.0,
    }


def algorithm_proposal():
    return {
        "proposal_id": "event-gated-residual-response-v1",
        "parent_harness_version": "h1",
        "evidence_refs": ["artifacts/nfl-train-rsi-trajectory-20260915-01/trajectory.json"],
        "research_record": "0042",
        "problem": "Most plays have small moves while rare states carry most squared error.",
        "hypothesis": "A learned material-move gate plus a conditional magnitude model reduces MSE.",
        "changed_stage": "prediction",
        "closest_methods": ["mixture_of_experts", "hurdle_model", "random_forest_response"],
        "source_findings": [
            "Mixture models can specialize experts by regime.",
            "Hurdle models separate event occurrence from conditional magnitude.",
        ],
        "transfer_limits": [
            "Published mixture results do not establish sports-market response skill.",
            "Hurdle likelihood assumptions may not match bounded price changes.",
        ],
        "novelty_level": "new_composition",
        "previously_untried_in_project": True,
        "why_existing_library_is_insufficient": (
            "Every installed trainer predicts one unconditional mean and cannot expose gate failure."
        ),
        "mechanism_delta": "Separate probability of a material move from signed conditional magnitude.",
        "mathematical_spec": "prediction(x)=sigmoid(g(x))*m(x), fitted with a joint bounded loss.",
        "pseudocode": "fit gate on Train; fit magnitude on Train positives; multiply; never fit on Dev",
        "input_contract": "same frozen play-state features and row mask as the parent",
        "target_contract": "same 60-second home-price delta",
        "loss_and_regularization": "weighted gate log loss plus conditional Huber loss and L2 penalty",
        "fit_protocol": "expanding game folds; transformations fit on prior games only",
        "same_data_baselines": [
            "unchanged_parent", "simple_baseline", "zero_change", "ridge", "frozen_train_champion"
        ],
        "ablations": ["remove_new_mechanism", "gate_only", "magnitude_only"],
        "failure_modes": ["gate collapse", "rare-regime overfit", "calibration scale inflation"],
        "synthetic_tests": ["all-zero target returns zero", "rare-move fixture activates gate"],
        "maximum_cpu_seconds": 600,
        "maximum_memory_mb": 4096,
        "external_dependencies": [],
        "requests_sealed_data": False,
    }


class CoevolvingDataAlgorithmContractTests(unittest.TestCase):
    def test_current_work_order_is_valid_but_grants_no_authority(self):
        receipt = plan_receipt(current_nfl_history_plan())
        self.assertFalse(receipt["download_authorized"])
        self.assertFalse(receipt["admission_authorized"])

    def test_clean_historical_batch_can_become_train_candidate(self):
        plan = data_plan()
        receipt = plan_receipt(plan)
        result = admission_readiness(plan, batch(receipt["plan_sha256"]))
        self.assertTrue(result["ready_for_versioned_train_candidate"])
        self.assertFalse(result["automatically_admitted"])

    def test_reserved_overlap_fails_closed(self):
        plan = data_plan()
        receipt = plan_receipt(plan)
        value = batch(receipt["plan_sha256"])
        value["reserved_period_overlap"] = True
        result = admission_readiness(plan, value)
        self.assertFalse(result["ready_for_versioned_train_candidate"])

    def test_duplicates_fail_closed(self):
        plan = data_plan()
        receipt = plan_receipt(plan)
        value = batch(receipt["plan_sha256"])
        value["duplicate_rate"] = 0.001
        result = admission_readiness(plan, value)
        self.assertFalse(result["ready_for_versioned_train_candidate"])

    def test_algorithm_design_is_archived_not_activated(self):
        result = archive_proposal(algorithm_proposal())
        self.assertFalse(result["activated"])
        self.assertTrue(result["novelty_is_not_selection_evidence"])

    def test_algorithm_design_needs_mechanism_ablation(self):
        proposal = algorithm_proposal()
        proposal["ablations"] = ["gate_only", "magnitude_only"]
        with self.assertRaisesRegex(ValueError, "removal of the new mechanism"):
            archive_proposal(proposal)

    def test_algorithm_design_cannot_read_sealed_data(self):
        proposal = algorithm_proposal()
        proposal["requests_sealed_data"] = True
        with self.assertRaisesRegex(ValueError, "sealed"):
            archive_proposal(proposal)

    def test_served_algorithm_schema_names_every_required_field(self):
        self.assertEqual(set(SCHEMA["required"]), FIELDS)
        validate_shape(algorithm_proposal(), SCHEMA, "proposal")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "work"
            broker = Broker(root, fixtures.workspace(root))
            output = io.StringIO()
            request = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
            with patch("sys.stdin", io.StringIO(request)), patch("sys.stdout", output):
                serve(broker)
            tools = json.loads(output.getvalue())["result"]["tools"]
            schema = next(tool for tool in tools
                          if tool["name"] == "propose_algorithm_design")["inputSchema"]
            self.assertEqual(set(schema["properties"]["proposal"]["required"]), FIELDS)


if __name__ == "__main__":
    unittest.main()
