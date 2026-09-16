import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data_scientist_harness.broker import Broker
from data_scientist_harness.store import Store, create
from market_rsi import file_hash, fresh_json


class AggregateWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.receipt = base / "result.json"
        fresh_json(self.receipt, {
            "schema": "fixture_aggregate_result_v1",
            "route_dev_opened": False,
            "sealed_final_opened": False,
        })
        self.root = base / "workspace"
        self.findings = [{
            "id": "result",
            "fact": "Synthetic aggregate only",
            "accessed_utc_date": "2026-09-16",
            "sources": [{
                "evidence_type": "runner_verified_primary_source_fact",
                "url": "https://example.org/official",
                "read": "Methods",
                "finding": "A bounded fixture fact.",
                "transfer_limit": "Not empirical validation.",
            }],
        }]
        self.manifest = create(
            self.root,
            quality=None,
            findings=self.findings,
            allowed_dates=[],
            purpose="aggregate_research",
            network=False,
            aggregate_receipts=[{
                "path": str(self.receipt.resolve()),
                "sha256": file_hash(self.receipt),
            }],
        )
        self.broker = Broker(self.root, self.manifest)

    def tearDown(self):
        self.tmp.cleanup()

    def acknowledge(self):
        status = self.broker.call("inspect_harness", {})
        self.assertEqual(status["quality"]["scope"], "opened_train_aggregate_only")
        self.assertEqual(len(status["aggregate_evidence"]), 1)
        self.assertIn("source-study registration are not admitted", status["source_only_rule"])
        self.broker.call("acknowledge_current_findings", {
            "finding_sha256": status["finding_sha256"],
            "responses": [{
                "id": "result",
                "handling": "Use as opened-Train context only",
                "next_evidence": "Independent confirmation",
            }],
        })

    def test_defer_works_but_training_and_selection_are_blocked(self):
        self.acknowledge()
        with patch("data_scientist_harness.broker.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "aggregate-only"):
                self.broker.call("train_candidate", {
                    "trial_id": "x", "parent_trial_id": "", "plan": {},
                    "feature_review": "0001", "trainer_research": "0001", "experiment": {},
                })
            spawn.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "aggregate-only"):
            self.broker.call("submit_research_decision", {
                "action": "select", "trial_id": "x", "reason": "forbidden",
            })
        result = self.broker.call("submit_research_decision", {
            "action": "defer", "trial_id": "", "reason": "research plan only",
        })
        self.assertTrue(result["submitted"])
        self.assertIsNone(result["selected"])

    def test_frozen_aggregate_copy_detects_mutation(self):
        copied = next((self.root / "aggregate-inputs").iterdir())
        copied.write_text(json.dumps({"changed": True}))
        with self.assertRaisesRegex(ValueError, "frozen data"):
            Store(self.root, self.manifest)

    def test_runner_bound_source_fact_can_be_recorded_without_network(self):
        status = self.broker.call("inspect_harness", {})
        with self.assertRaisesRegex(ValueError, "expected one of"):
            self.broker.call("record_research", {
                "layer": "data_quality", "question": "Reject inspect metadata",
                "read_records": [status["record_id"]],
                "applicability": "None", "limitations": "Not a source read",
                "alternatives": "Use a source evidence record",
                "proposed_test": "Read bounded evidence first",
            })
        evidence = self.broker.call("read_aggregate_source_evidence", {
            "finding_id": "result", "source_index": 0,
        })
        self.assertFalse(evidence["fresh_network_read"])
        self.assertFalse(evidence["full_text_read"])
        self.assertEqual(evidence["provenance"],
                         "runner-bound current aggregate finding")
        research = self.broker.call("record_research", {
            "layer": "data_quality",
            "question": "Can the fixture source support a bounded source canary?",
            "read_records": [evidence["record_id"]],
            "applicability": "Only the declared source capability.",
            "limitations": "No SLA, entitlement or empirical performance claim.",
            "alternatives": "Prospective public-source canary.",
            "proposed_test": "Collect one bounded prospective receipt.",
        })
        self.assertEqual(research["sources"][0]["evidence_type"],
                         "runner_verified_primary_source_fact")
        self.assertFalse(research["sources"][0]["full_text_read"])
        self.assertEqual(status["finding_sha256"],
                         evidence["current_finding_set_sha256"])

    def test_aggregate_source_fact_rejects_wrong_mode_and_unverified_schema(self):
        standard = Path(self.tmp.name) / "standard"
        from data_scientist_harness import fixtures
        standard_broker = Broker(standard, fixtures.workspace(standard))
        standard_broker.call("inspect_harness", {})
        with self.assertRaisesRegex(RuntimeError, "aggregate-only"):
            standard_broker.call("read_aggregate_source_evidence", {
                "finding_id": "fixture-only", "source_index": 0,
            })

        bad_root = Path(self.tmp.name) / "bad-evidence"
        bad_manifest = create(
            bad_root, quality=None,
            findings=[{
                "id": "source", "accessed_utc_date": "2026-09-16",
                "sources": [{
                    "url": "https://example.org", "read": "x",
                    "finding": "x", "transfer_limit": "x",
                    "evidence_type": "unverified_summary",
                }],
            }],
            allowed_dates=[], purpose="aggregate_research", network=False,
            aggregate_receipts=[{
                "path": str(self.receipt.resolve()),
                "sha256": file_hash(self.receipt),
            }],
        )
        bad_broker = Broker(bad_root, bad_manifest)
        bad_broker.call("inspect_harness", {})
        with self.assertRaisesRegex(ValueError, "runner-verified"):
            bad_broker.call("read_aggregate_source_evidence", {
                "finding_id": "source", "source_index": 0,
            })

    def test_raw_or_dates_cannot_be_smuggled_into_aggregate_mode(self):
        with self.assertRaisesRegex(ValueError, "forbids raw data"):
            create(
                Path(self.tmp.name) / "bad",
                data_root=Path(self.tmp.name),
                quality=None,
                findings=self.findings,
                allowed_dates=["2025-01-01"],
                purpose="aggregate_research",
                aggregate_receipts=[{
                    "path": str(self.receipt.resolve()),
                    "sha256": file_hash(self.receipt),
                }],
            )


if __name__ == "__main__":
    unittest.main()
