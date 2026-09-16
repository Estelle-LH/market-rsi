from __future__ import annotations

from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path

from literature_catalog import literature_snapshot
from market_rsi import fresh_json
from objective_discovery_tools_mcp import Broker, DECISION_FIELDS, TOOLS
from objective_discovery_workspace import prepare_workspace


DATES = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]


def source() -> dict:
    rows = []
    for day in range(1, 5):
        base = int(datetime(2026, 9, day, tzinfo=timezone.utc).timestamp() * 1000)
        for second in range(0, 181, 15):
            mid = 0.40 + second / 10_000
            rows.append({
                "row_id": f"{day}-{second}", "game_id": f"game-{day}",
                "market_id": f"market-{day}", "decision_ms": base + second * 1000,
                "features": {"mid": mid}, "target": min(1.0, mid + 0.005),
            })
    return {"schema": "polymarket_midpoint_labels_v1", "rows": rows}


def proposal(proposal_id: str, objective_id: str) -> dict:
    return {
        "proposal_id": proposal_id,
        "objective_id": objective_id,
        "research_question": "Can decision-time data predict the later quoted probability?",
        "label_formula": "Use only admitted future midpoints in the declared window.",
        "source_and_availability_clock": "Quotes use collector observed_at and labels arrive after the full window.",
        "horizon_and_window": "Decision at t; label from t+45s through t+75s.",
        "minimum_coverage": 0.25,
        "baseline": "Decision-time midpoint persistence on exactly common rows.",
        "raw_and_scale_free_scores": "Equal-game MSE and 1-candidate-MSE/persistence-MSE.",
        "expected_failure_condition": "Reject if coverage is low or persistence error is degenerate.",
        "required_materializer_and_validation_tests": [
            "Causal availability test", "Nearby-window stability test"
        ],
        "literature_ids": ["zhang-zohren-roberts-deeplob-2018"],
    }


class ObjectiveDiscoveryBrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        path = self.root / "opened-train.json"
        fresh_json(path, source())
        workspace = self.root / "workspace"
        prepare_workspace(
            workspace,
            session_id="objective-discovery-fixture",
            experiment_id="objective-fixture",
            source_path=path,
            opened_train_utc_dates=DATES,
            literature_snapshot=literature_snapshot(),
        )
        self.workspace = workspace
        self.broker = Broker(workspace)

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_objective_discovery_path(self):
        inventory = self.broker.call("inspect_open_train_source_inventory", {})
        self.assertFalse(inventory["dev_artifact_present"])
        diagnostics = self.broker.call("run_automatic_time_series_data_diagnostics", {})
        self.assertEqual(diagnostics["rows"], 52)
        self.broker.call("profile_open_train_cadence", {})
        papers = self.broker.call("search_public_literature", {
            "query": "future mid price averages"
        })
        ids = {paper["paper_id"] for paper in papers["results"]}
        self.assertIn("zhang-zohren-roberts-deeplob-2018", ids)
        self.broker.call("list_objective_families", {})
        first = proposal("window-mean", "future-midpoint-window-mean-45-75s-v1")
        second = proposal("window-median", "future-midpoint-window-median-45-75s-v1")
        self.broker.call("propose_objective_definition", first)
        self.broker.call("propose_objective_definition", second)
        self.broker.call("profile_open_train_target", {
            "objective_id": first["objective_id"]
        })
        self.broker.call("run_open_train_objective_audit", {"proposal_id": "window-mean"})
        self.broker.call("run_open_train_objective_audit", {"proposal_id": "window-median"})
        compared = self.broker.call("compare_open_train_objective_stability", {
            "proposal_ids": ["window-mean", "window-median"]
        })
        self.assertFalse(compared["automatic_selection"])
        decision = {
            "action": "select", "proposal_id": "window-mean",
            "objective_id": first["objective_id"],
            "rationale": "The future window is less sensitive to one quote.",
            "evidence": "Opened-Train coverage and stability passed the declared audit.",
            "literature_ids": ["zhang-zohren-roberts-deeplob-2018"],
            "expected_failure_condition": first["expected_failure_condition"],
            "limitations": "This selects a target; it does not show model improvement.",
        }
        result = self.broker.call("submit_objective_decision", decision)
        self.assertTrue(result["submitted"])
        self.assertTrue((self.workspace / "frozen-objective-contract.json").is_file())
        self.assertTrue(self.broker.log_assessment()["valid"])

    def test_cannot_select_unaudited_or_unsearched_evidence(self):
        first = proposal("window-mean", "future-midpoint-window-mean-45-75s-v1")
        self.broker.call("propose_objective_definition", first)
        decision = {
            "action": "select", "proposal_id": "window-mean",
            "objective_id": first["objective_id"], "rationale": "x", "evidence": "x",
            "literature_ids": ["zhang-zohren-roberts-deeplob-2018"],
            "expected_failure_condition": "x", "limitations": "x",
        }
        with self.assertRaisesRegex(ValueError, "not been audited"):
            self.broker.call("submit_objective_decision", decision)

    def test_literature_ids_are_normalized_instead_of_rejected_for_order(self):
        value = proposal("window-mean", "future-midpoint-window-mean-45-75s-v1")
        value["literature_ids"] = [
            "zhang-zohren-roberts-deeplob-2018",
            "cont-kukanov-stoikov-2010",
        ]
        self.broker.call("propose_objective_definition", value)
        stored = json.loads(
            (self.workspace / "objective-proposals/window-mean.json").read_text()
        )
        self.assertEqual(stored["literature_ids"], sorted(value["literature_ids"]))

    def test_submit_schema_is_flat_to_avoid_nested_tool_serialization(self):
        tool = next(item for item in TOOLS if item["name"] == "submit_objective_decision")
        self.assertNotIn("decision", tool["inputSchema"]["properties"])
        self.assertEqual(set(tool["inputSchema"]["required"]), DECISION_FIELDS)

    def test_controller_sees_aggregate_inventory_without_local_source_path(self):
        inventory = self.broker.call("inspect_open_train_source_inventory", {})
        self.assertNotIn("source_path", inventory)
        events = (self.workspace / "controller-egress-audit.jsonl").read_text()
        self.assertIn('"raw_rows_released":false', events)

    def test_egress_guard_rejects_raw_rows(self):
        with self.assertRaisesRegex(ValueError, "aggregate-only egress"):
            self.broker._audit_egress("unsafe", {"row_id": "secret"})

    def test_extra_proposal_field_returns_specific_error(self):
        value = proposal("window-mean", "future-midpoint-window-mean-45-75s-v1")
        value["note"] = "not in the tool contract"
        with self.assertRaisesRegex(ValueError, "extra=\\['note'\\]"):
            self.broker.call("propose_objective_definition", value)


if __name__ == "__main__":
    unittest.main()
