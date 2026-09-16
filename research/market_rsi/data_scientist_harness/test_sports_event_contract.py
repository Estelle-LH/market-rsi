from pathlib import Path
import copy
import subprocess
import sys
import tempfile
import unittest

from data_scientist_harness import fixtures, sports_event_contract
from data_scientist_harness.broker import Broker, TOOLS, validate_shape


def contract():
    return {
        "sport": "NFL",
        "season": "2025",
        "requested_stage": "state_prediction",
        "identity": {
            "canonical_game_mapping": "verified",
            "home_away_orientation": "verified",
            "market_outcome_orientation": "verified",
            "resolution_rule_compatibility": "verified",
        },
        "play_by_play": {
            "provider": "fixture PBP",
            "manifest_sha256": "a" * 64,
            "games": 285,
            "plays": 48771,
            "coverage": "verified",
            "immutable_raw": "verified",
            "event_id": "verified",
            "game_clock": "verified",
            "provider_wall_clock": "verified",
            "provider_publish_time": "partial",
            "local_receive_time": "missing",
            "correction_or_overturn_state": "verified",
            "historical_backfill": "yes",
        },
        "market": {
            "venue": "fixture prediction market",
            "manifest_sha256": "b" * 64,
            "games": 253,
            "streams": ["market_metadata", "resolutions", "prices", "trades"],
            "immutable_raw": "verified",
            "game_contract_mapping": "verified",
            "source_timestamp": "verified",
            "local_receive_time": "missing",
            "sequence_or_snapshot_reset_state": "missing",
            "research_storage_permission": "verified_for_research",
        },
        "execution": {
            "fee_schedule": "partial",
            "order_send_time": "missing",
            "order_acknowledgement": "missing",
            "fill_confirmation": "missing",
            "cancel_acknowledgement": "missing",
        },
        "evaluation": {
            "split_unit": "game",
            "train_games": 200,
            "dev_games": 50,
            "final_games": 35,
            "chronological": "yes",
            "final_opened": "no",
        },
    }


class SportsEventContractUnitTests(unittest.TestCase):
    def test_historical_pbp_supports_state_not_live_latency(self):
        value = sports_event_contract.probe(contract())
        self.assertTrue(value["stage_gates"]["state_prediction"]["policy_passed"])
        self.assertTrue(value["stage_gates"]["market_response"]["policy_passed"])
        self.assertFalse(value["stage_gates"]["lead_lag"]["policy_passed"])
        self.assertFalse(value["historical_backfill_is_live_latency_evidence"])
        self.assertIn("observed local PBP receive time",
                      " ".join(value["stage_gates"]["lead_lag"]["blockers"]))

    def test_observed_receive_times_allow_lead_lag_but_not_pnl(self):
        value = contract()
        value["requested_stage"] = "lead_lag"
        value["play_by_play"]["local_receive_time"] = "verified"
        value["market"]["local_receive_time"] = "verified"
        value["market"]["sequence_or_snapshot_reset_state"] = "verified"
        result = sports_event_contract.probe(value)
        self.assertTrue(result["requested_stage_policy_passed"])
        self.assertFalse(result["stage_gates"]["executable_pnl"]["policy_passed"])

    def test_pnl_requires_account_evidence_and_fees(self):
        value = contract()
        value["requested_stage"] = "executable_pnl"
        value["play_by_play"]["local_receive_time"] = "verified"
        value["market"]["local_receive_time"] = "verified"
        value["market"]["sequence_or_snapshot_reset_state"] = "verified"
        for key in value["execution"]:
            value["execution"][key] = "verified"
        result = sports_event_contract.probe(value)
        self.assertTrue(result["requested_stage_policy_passed"])
        self.assertFalse(result["displayed_depth_is_fill_evidence"])

    def test_permission_and_final_game_gates_fail_closed(self):
        value = contract()
        value["requested_stage"] = "market_response"
        value["market"]["research_storage_permission"] = "unresolved"
        value["evaluation"]["final_games"] = 4
        result = sports_event_contract.probe(value)
        blockers = " ".join(result["stage_gates"]["market_response"]["blockers"])
        self.assertIn("at least 20 untouched games", blockers)
        self.assertIn("permission", blockers)


class SportsEventContractBrokerTests(unittest.TestCase):
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
            "layer": "data_quality",
            "question": "fixture event data",
            "read_records": [read["record_id"]],
            "applicability": "fixture",
            "limitations": "fixture",
            "alternatives": "fixture",
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

    def test_tool_schema_and_logged_probe(self):
        schema = next(t["inputSchema"] for t in TOOLS
                      if t["name"] == "probe_sports_event_contract")
        args = {"contract": contract(), "research_record": self.research["record_id"]}
        validate_shape(args, schema)
        self.acknowledge()
        result = self.broker.call("probe_sports_event_contract", args)
        self.assertEqual(result["schema"], "sports_event_contract_probe_v1")
        self.assertFalse(result["source_admitted"])

    def test_probe_requires_findings_and_correct_research_layer(self):
        with self.assertRaisesRegex(ValueError, "address current findings"):
            self.broker.call("probe_sports_event_contract", {
                "contract": contract(), "research_record": self.research["record_id"],
            })

    def test_frozen_workspace_contains_sports_contract_without_checkout(self):
        program = (
            "import sys; sys.path.insert(0,sys.argv[1]); "
            "from data_scientist_harness import sports_event_contract; "
            "assert sports_event_contract.probe(eval(sys.argv[2]))"
            "['stage_gates']['state_prediction']['policy_passed']"
        )
        done = subprocess.run(
            [sys.executable, "-c", program, str(self.root / "code"), repr(contract())],
            cwd=self.temp.name,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
