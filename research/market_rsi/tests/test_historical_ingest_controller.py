from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from historical_ingest_controller import (Broker, DATASET, REVISION, MAX_BYTES,
                                          assess_activity, prepare_workspace,
                                          select_files, validate_workspace, recipe_proposal)
from market_rsi import digest, fresh_json
from run_codex_glm_controller import codex_command


class HistoricalIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dates = [(date(2026, 2, 1) + timedelta(days=i)).isoformat() for i in range(45)]
        files = [{"path": "unified/market_meta/unpartitioned/part-000001.parquet",
                  "bytes": 100, "lfs_sha256": "a" * 64}]
        files += [{"path": f"unified/{table}/date={day}/part-000001.parquet",
                   "bytes": 1000, "lfs_sha256": "b" * 64}
                  for table in ("polymarket_ticks_ms", "binance_trades", "lag_pairs_ms")
                  for day in self.dates]
        self.inv = {"dataset": DATASET, "revision": REVISION, "files": files}
        self.inv["inventory_sha256"] = digest(self.inv)
        self.report = {"canary_pass": True, "inventory_sha256": self.inv["inventory_sha256"],
                       "source": {"revision": REVISION, "license": "apache-2.0"}}
        self.report["report_sha256"] = digest(self.report)
        fresh_json(self.root / "inv.json", self.inv)
        fresh_json(self.root / "report.json", self.report)
        self.workspace = self.root / "workspace"
        prepare_workspace(self.workspace, inventory=self.root / "inv.json",
                          canary=self.root / "report.json", session_id="fixture-ingest",
                          experiment_id="fixture")
        self.broker = Broker(self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def proposal(self, pid="first", count=40):
        return {"proposal_id": pid, "tables": ["market_meta", "polymarket_ticks_ms"],
                "utc_dates": self.dates[:count], "rationale": "Causal raw coverage.",
                "limitations": "Dates do not prove complete days or PM trades."}

    def test_exact_manifest_and_dates(self):
        value = select_files(self.inv, self.proposal())
        self.assertEqual(value["tick_date_count"], 40)
        self.assertEqual(len(value["selected_files"]), 41)
        self.assertEqual(value["selected_bytes"], 40100)
        self.assertFalse(value["formal_dataset_ready"])

    def test_no_derived_lag_pairs(self):
        proposal = self.proposal()
        proposal["tables"].append("lag_pairs_ms")
        with self.assertRaisesRegex(ValueError, "nonraw"):
            select_files(self.inv, proposal)

    def test_over_budget(self):
        inv = json.loads(json.dumps(self.inv))
        inv["files"][0]["bytes"] = MAX_BYTES
        with self.assertRaisesRegex(ValueError, "exceed"):
            select_files(inv, self.proposal())

    def test_missing_date_and_hash_fail(self):
        proposal = self.proposal()
        proposal["utc_dates"][-1] = "2026-06-01"
        with self.assertRaisesRegex(ValueError, "missing"):
            select_files(self.inv, proposal)
        self.inv["files"][0]["lfs_sha256"] = None
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            select_files(self.inv, self.proposal())

    def test_input_tamper(self):
        with (self.workspace / "canary.json").open("a") as handle:
            handle.write(" ")
        with self.assertRaisesRegex(ValueError, "input changed"):
            validate_workspace(self.workspace)

    def test_bad_prior_hash(self):
        self.report["canary_pass"] = False
        (self.root / "report.json").write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            prepare_workspace(self.root / "other", inventory=self.root / "inv.json",
                              canary=self.root / "report.json", session_id="other",
                              experiment_id="fixture")

    def test_compare_requires_different_actual_files(self):
        self.broker.call("propose_ingest_plan", self.proposal("a"))
        self.broker.call("propose_ingest_plan", self.proposal("b"))
        with self.assertRaisesRegex(ValueError, "actual selected files"):
            self.broker.call("compare_ingest_plans", {"proposal_ids": ["a", "b"]})

    def test_complete_first_decision_and_activity(self):
        self.broker.call("inspect_history_inventory", {})
        self.broker.call("inspect_source_canary_evidence", {})
        self.broker.call("propose_ingest_plan", self.proposal("a"))
        self.broker.call("propose_ingest_plan", self.proposal("b", 41))
        self.broker.call("compare_ingest_plans", {"proposal_ids": ["a", "b"]})
        answer = {"action": "select", "proposal_id": "a", "rationale": "Bounded coverage."}
        result = self.broker.call("submit_ingest_decision", answer)
        self.assertTrue(result["submitted"])
        self.assertTrue(assess_activity(self.workspace)["valid"])
        with self.assertRaisesRegex(ValueError, "already submitted"):
            self.broker.call("submit_ingest_decision", answer)

    def test_defer_without_fabricated_selection(self):
        self.broker.call("inspect_history_inventory", {})
        self.broker.call("inspect_source_canary_evidence", {})
        self.broker.call("submit_ingest_decision", {
            "action": "defer", "proposal_id": "none", "rationale": "Insufficient stream semantics."})
        self.assertFalse((self.workspace / "frozen-ingest-plan.json").exists())
        self.assertEqual(assess_activity(self.workspace)["action"], "defer")

    def test_injected_paths_fail(self):
        value = self.proposal("../escape")
        with self.assertRaises(ValueError):
            select_files(self.inv, value)

    def test_routes_to_only_ingest_broker(self):
        command = " ".join(codex_command(
            workspace=self.workspace, answer=self.root / "answer", base_url="http://127.0.0.1:1/v1",
            catalog=self.root / "catalog", instructions=self.root / "instructions",
            tool_mode="canary", controller_stage="ingest"))
        self.assertIn("historical_ingest_controller.py", command)
        self.assertNotIn("data_discovery_tools_mcp.py", command)

    def test_unsorted_explicit_dates_are_same_selection(self):
        a = self.proposal()
        b = self.proposal()
        b["utc_dates"] = list(reversed(b["utc_dates"]))
        self.assertEqual(select_files(self.inv, a), select_files(self.inv, b))

    def test_recipes_use_only_real_inventory_dates(self):
        for rule in ("earliest", "latest", "evenly_spaced", "hash_seed23", "smallest_compressed_bytes"):
            args = {"proposal_id": "recipe", "tables": ["market_meta", "polymarket_ticks_ms"],
                    "date_rule": rule, "date_count": 40, "exclude_dates": [self.dates[10]],
                    "rationale": "Metadata-only selection.", "limitations": "No result-based choice."}
            proposal = recipe_proposal(self.inv, args)
            self.assertEqual(len(proposal["utc_dates"]), 40)
            self.assertNotIn(self.dates[10], proposal["utc_dates"])
            self.assertTrue(set(proposal["utc_dates"]) <= set(self.dates))
            self.assertEqual(select_files(self.inv, proposal)["tick_date_count"], 40)

    def test_later_source_issue_is_frozen_and_visible(self):
        issue = {"dataset": DATASET, "revision": REVISION, "raw_modified": False,
                 "identity_mismatch_rows": 3552}
        issue["evidence_sha256"] = digest(issue)
        fresh_json(self.root / "issue.json", issue)
        other = self.root / "with-issue"
        manifest = prepare_workspace(other, inventory=self.root / "inv.json", canary=self.root / "report.json",
                                     session_id="with-issue", experiment_id="fixture", source_issues=self.root / "issue.json")
        self.assertIn("source-issues.json", manifest["files"])
        result = Broker(other).call("inspect_source_canary_evidence", {})
        self.assertEqual(result["later_source_issues"]["identity_mismatch_rows"], 3552)

    def test_recipe_tool_logs_controller_choice(self):
        args = {"proposal_id": "recipe", "tables": ["market_meta", "polymarket_ticks_ms"],
                "date_rule": "latest", "date_count": 40, "exclude_dates": [],
                "rationale": "Metadata only.", "limitations": "Not a fresh test."}
        self.broker.call("propose_ingest_recipe", args)
        plan = json.loads((self.workspace / "plan-recipe.json").read_text())
        self.assertEqual(plan["selection_recipe"], args)
        self.assertEqual(plan["proposal"]["utc_dates"], self.dates[-40:])


if __name__ == "__main__":
    unittest.main()
