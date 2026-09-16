from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from data_scientist_harness import fixtures, live_timing_contract
from data_scientist_harness.broker import Broker, TOOLS, validate_shape


def contract():
    return {
        "study_id": "nfl-live-timing-fixture-v1",
        "provider": "fixture push provider",
        "provider_clock_semantics": "provider_publish",
        "provider_clock_resolution_ms": 1,
        "local_receive_time_verified": "yes",
        "market_local_receive_time_verified": "yes",
        "immutable_raw": "yes",
        "correction_or_overturn_state": "verified",
        "prospective_capture": "yes",
        "decision_clock": "local_receive",
        "horizon_stage": "protected_confirmation",
        "candidate_horizons_ms": [30000],
        "horizons_chosen_before_stage_score": "yes",
        "horizon_selection_rule": "single frozen horizon",
        "primary_reward_name": "equal-game paired MSE delta",
        "reward_chosen_before_stage_score": "yes",
        "feature_completeness_threshold_per_mille": 900,
        "maximum_publish_to_receive_p99_ms": 5000,
        "latency_threshold_basis": "pre-score strategy horizon and source SLA",
        "market_response_definition_frozen": "yes",
        "market_lead_support_rule_frozen": "yes",
        "minimum_games": 20,
        "minimum_events": 100,
        "protected_holdout_status": "untouched",
        "source_receipt_sha256": "a" * 64,
    }


class LiveTimingContractUnitTests(unittest.TestCase):
    def test_complete_prospective_contract_passes_policy_only(self):
        result = live_timing_contract.probe(contract())
        self.assertTrue(result["claim_gates"]["independent_confirmation"]["policy_passed"])
        self.assertFalse(result["thresholds_scientifically_supported_by_this_probe"])
        self.assertFalse(result["source_admitted"])

    def test_event_start_clock_cannot_claim_strict_latency_or_market_lead(self):
        value = contract()
        value["provider"] = "public polling feed"
        value["provider_clock_semantics"] = "event_start"
        result = live_timing_contract.probe(value)
        self.assertTrue(result["claim_gates"]["capture_integrity"]["policy_passed"])
        self.assertFalse(result["claim_gates"]["strict_publish_to_receive_latency"]["policy_passed"])
        self.assertFalse(result["claim_gates"]["market_lead"]["policy_passed"])
        self.assertIn("event-start", " ".join(
            result["claim_gates"]["strict_publish_to_receive_latency"]["blockers"]))

    def test_opened_or_small_cohort_is_not_independent_confirmation(self):
        value = contract()
        value["minimum_games"] = 1
        value["protected_holdout_status"] = "opened"
        result = live_timing_contract.probe(value)
        blockers = " ".join(result["claim_gates"]["independent_confirmation"]["blockers"])
        self.assertIn("at least 20", blockers)
        self.assertIn("untouched", blockers)

    def test_opened_train_can_explore_predeclared_horizons(self):
        value = contract()
        value["horizon_stage"] = "opened_train_discovery"
        value["candidate_horizons_ms"] = [5000, 15000, 30000, 60000]
        result = live_timing_contract.probe(value)
        self.assertTrue(result["claim_gates"]["capture_integrity"]["policy_passed"])
        self.assertTrue(result["opened_train_may_compare_predeclared_horizons"])
        self.assertFalse(result["post_score_horizon_selection_allowed"])

    def test_confirmation_cannot_select_among_many_horizons(self):
        value = contract()
        value["candidate_horizons_ms"] = [30000, 60000]
        result = live_timing_contract.probe(value)
        blockers = " ".join(result["claim_gates"]["capture_integrity"]["blockers"])
        self.assertIn("one frozen horizon", blockers)

    def test_missing_feature_fields_fail_capture_integrity(self):
        value = contract()
        value["feature_completeness_threshold_per_mille"] = 0
        value["correction_or_overturn_state"] = "missing"
        result = live_timing_contract.probe(value)
        self.assertFalse(result["claim_gates"]["capture_integrity"]["policy_passed"])


class LiveTimingContractBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "work"
        self.broker = Broker(self.root, fixtures.workspace(self.root, network=True),
                             transport=fixtures.fake_transport)
        self.status = self.broker.call("inspect_harness", {})
        read = self.broker.call("read_public_source", {
            "url": "https://example.org/research", "offset": 0,
        })
        self.research = self.broker.call("record_research", {
            "layer": "evaluation", "question": "fixture live timing",
            "read_records": [read["record_id"]], "applicability": "fixture",
            "limitations": "fixture", "alternatives": "fixture",
            "proposed_test": "fixture",
        })

    def tearDown(self):
        self.temp.cleanup()

    def acknowledge(self):
        self.broker.call("acknowledge_current_findings", {
            "finding_sha256": self.status["finding_sha256"],
            "responses": [{
                "id": "fixture-only", "handling": "fixture", "next_evidence": "fixture",
            }],
        })

    def test_schema_and_logged_probe(self):
        schema = next(t["inputSchema"] for t in TOOLS
                      if t["name"] == "probe_live_timing_contract")
        args = {"contract": contract(), "research_record": self.research["record_id"]}
        validate_shape(args, schema)
        self.acknowledge()
        result = self.broker.call("probe_live_timing_contract", args)
        self.assertEqual(result["schema"], "live_timing_contract_probe_v1")
        self.assertFalse(result["data_read"])

    def test_frozen_workspace_contains_contract(self):
        program = (
            "import sys; sys.path.insert(0,sys.argv[1]); "
            "from data_scientist_harness import live_timing_contract; "
            "assert live_timing_contract.probe(eval(sys.argv[2]))"
            "['claim_gates']['capture_integrity']['policy_passed']"
        )
        done = subprocess.run(
            [sys.executable, "-c", program, str(self.root / "code"), repr(contract())],
            cwd=self.temp.name,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
