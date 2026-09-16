from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from data_discovery_tools_mcp import Broker, DECISION_FIELDS, TOOLS
from data_discovery_workspace import prepare_workspace, validate_workspace
from data_source_catalog import data_source_catalog, get_data_source
from market_rsi import fresh_json


DATES = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]


def fixture_source():
    rows = []
    for day in range(1, 5):
        base = int(datetime(2026, 9, day, tzinfo=timezone.utc).timestamp() * 1000)
        for second in range(0, 120, 30):
            mid = 0.4 + second / 10000
            rows.append({"row_id": f"{day}-{second}", "game_id": f"game-{day}",
                         "market_id": f"market-{day}", "decision_ms": base + second * 1000,
                         "features": {"mid": mid}, "target": mid + 0.002})
    return {"schema": "fixture", "rows": rows}


def plan(proposal_id, source_id):
    return {"proposal_id": proposal_id, "strategy": "acquire_real_history",
            "primary_source_ids": [source_id],
            "goal": "Build replayable real history before choosing a target.",
            "planned_scope": "Start with a bounded sample, then select date partitions.",
            "expected_independent_units": "Many UTC days and whole markets, not row count.",
            "time_span": "Multiple chronological months if the canary verifies coverage.",
            "microstructure_needed": "Trades, top of book, market metadata and timestamps.",
            "objective_compatibility": "Supports later causal short-horizon target research.",
            "canary_steps": ["Download only the published sample", "Verify checksums and schema"],
            "canary_acceptance_tests": ["No duplicate event key", "Causal source and ingest clocks"],
            "full_ingest_acceptance_tests": ["At least 60 UTC days and 150 whole markets"],
            "rejection_conditions": ["Terms cannot be verified", "Timestamp semantics are unusable"],
            "storage_cap_gb": 20, "download_cap_gb": 10,
            "simulator_role": "not_used",
            "literature_ids": ["zhang-zohren-roberts-deeplob-2018"]}


class DataDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.json"
        fresh_json(self.source, fixture_source())
        self.workspace = self.root / "workspace"
        prepare_workspace(self.workspace, session_id="data-discovery-fixture",
                          experiment_id="data-fixture",
                          current_source_path=self.source,
                          opened_train_utc_dates=DATES)
        self.broker = Broker(self.workspace)

    def tearDown(self):
        self.tmp.cleanup()

    def test_catalog_is_evidence_not_selection(self):
        catalog = data_source_catalog()
        self.assertFalse(catalog["catalog_selects_a_winner"])
        self.assertEqual(get_data_source("openmarket-v0.4.3-unified")["kind"],
                         "real_public_history")

    def test_workspace_binds_current_data_and_has_no_dev(self):
        manifest = validate_workspace(self.workspace)
        self.assertFalse(manifest["dev_artifact_present"])
        audit = json.loads((self.workspace / "current-data-audit.json").read_text())
        self.assertEqual(audit["utc_days"], 4)
        self.assertFalse(audit["rows_are_independent_samples"])

    def test_workspace_accepts_terms_rejection_as_controller_evidence(self):
        report = self.root / "terms.json"
        fresh_json(report, {
            "schema": "market_source_terms_gate_controller_evidence_v1",
            "status": "rejected_before_data_access",
            "full_download_authorized": False,
        })
        other = self.root / "terms-workspace"
        prepare_workspace(other, session_id="terms-discovery-fixture",
                          experiment_id="data-fixture",
                          current_source_path=self.source,
                          opened_train_utc_dates=DATES,
                          source_canary_report=report)
        evidence = json.loads((other / "source-canary-evidence.json").read_text())
        self.assertEqual(evidence["status"], "rejected_before_data_access")

    def test_workspace_accepts_passing_partition_canary(self):
        report = self.root / "partition.json"
        fresh_json(report, {
            "schema": "openmarket_partition_clean_canary_v1",
            "canary_pass": True,
            "full_download_authorized": False,
        })
        other = self.root / "partition-workspace"
        prepare_workspace(other, session_id="partition-discovery-fixture",
                          experiment_id="data-fixture",
                          current_source_path=self.source,
                          opened_train_utc_dates=DATES,
                          source_canary_report=report)
        evidence = json.loads((other / "source-canary-evidence.json").read_text())
        self.assertTrue(evidence["canary_pass"])

    def test_complete_controller_research_path(self):
        self.broker.call("inspect_current_data_audit", {})
        self.broker.call("inspect_source_canary_evidence", {})
        self.broker.call("list_historical_data_sources", {})
        self.broker.call("inspect_historical_data_source", {"source_id": "openmarket-v0.4.3-unified"})
        self.broker.call("search_historical_data_sources", {"query": "historical trades top book"})
        found = self.broker.call("search_public_literature", {"query": "future mid price"})
        self.assertTrue(found["results"])
        first = plan("openmarket-plan", "openmarket-v0.4.3-unified")
        second = plan("kalshi-plan", "kalshi-historical-api")
        self.broker.call("propose_data_plan", first)
        self.broker.call("propose_data_plan", second)
        self.broker.call("run_data_plan_feasibility_audit", {"proposal_id": "openmarket-plan"})
        self.broker.call("run_data_plan_feasibility_audit", {"proposal_id": "kalshi-plan"})
        compared = self.broker.call("compare_data_plans", {"proposal_ids": ["openmarket-plan", "kalshi-plan"]})
        self.assertFalse(compared["automatic_selection"])
        result = self.broker.call("submit_data_decision", {
            "action": "select", "proposal_id": "openmarket-plan",
            "rationale": "The sample canary can test synchronized real streams.",
            "evidence": "The frozen source evidence and literature support a replay audit.",
            "rejection_trigger": "Reject on unusable clocks, terms, gaps or schema.",
            "next_runner_action": "Run only the bounded public sample canary.",
            "limitations": "No full download and no performance claim are authorized.",
        })
        self.assertTrue(result["submitted"])
        self.assertGreater(result["bytes"], 0)
        self.assertFalse(result["full_download_authorized"])
        self.assertTrue(self.broker.log_assessment()["valid"])

    def test_canary_and_full_ingest_acceptance_are_separate(self):
        value = plan("separate-scopes", "polymarket-official-apis")
        self.broker.call("propose_data_plan", value)
        audit = self.broker.call("run_data_plan_feasibility_audit",
                                 {"proposal_id": "separate-scopes"})
        self.assertEqual(audit["source_canary_status"], "not_run")
        self.assertEqual(audit["full_ingest_status"], "not_authorized")
        self.assertNotEqual(audit["canary_acceptance_tests"],
                            audit["full_ingest_acceptance_tests"])

    def test_simulator_cannot_be_primary(self):
        value = plan("sim", "synthetic-market-simulator")
        with self.assertRaisesRegex(ValueError, "simulator cannot be a primary"):
            self.broker.call("propose_data_plan", value)

    def test_submit_schema_is_flat(self):
        tool = next(item for item in TOOLS if item["name"] == "submit_data_decision")
        self.assertEqual(set(tool["inputSchema"]["required"]), DECISION_FIELDS)


if __name__ == "__main__":
    unittest.main()
