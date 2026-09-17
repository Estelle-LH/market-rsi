"""The dry gate must fail closed; passing tests are not a model round."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json
from supervisor_harness.research_cycle_gate import (
    ZERO, bind_fixture_decision, open_fixture_cycle, record_fixture_execution,
    review_fixture_cycle,
)


class ResearchCycleGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "cycle-01"
        self.facts = {"scope": "synthetic_fixture", "message": "public canary"}
        self.packet = open_fixture_cycle(self.root, {
            "cycle_id": "cycle-01", "parent_feedback_sha256": ZERO,
            "harness_sha256": "a" * 64, "facts_sha256": digest(self.facts),
            "allowed_data_roles": ["synthetic_fixture"], "p0_passed": False,
            "cost_cap_usd": "0", "evidence_mode": "synthetic_fixture",
        })
        fresh_json(self.root / "facts.json", self.facts)

    def decision(self, **changes):
        raw = {
            "schema": "market_research_decision_v1", "cycle_id": "cycle-01",
            "input_sha256": self.packet["record_sha256"], "task_id": "task-01",
            "task_type": "code_canary", "data_role": "synthetic_fixture",
            "question": "Can the researcher preserve a source hash?",
            "hypothesis": "The output hash will equal the precommitted input hash.",
            "expected_evidence": "A JSON output and tool trace.",
            "stop_rule": "Stop after one bounded call.", "max_seconds": 30,
            "cost_bound_usd": "0",
        }
        raw.update(changes)
        fresh_json(self.root / "raw-decision.json", raw)
        return bind_fixture_decision(self.root, self.root / "raw-decision.json",
                                     {**raw, "raw_decision_sha256": file_hash(self.root / "raw-decision.json")})

    def execution(self, decision, **changes):
        if not (self.root / "trace.json").exists():
            fresh_json(self.root / "trace.json", {"calls": ["read_public_fixture"]})
            fresh_json(self.root / "output.json", {"result": "bounded fixture"})
        receipt = {
            "schema": "market_researcher_receipt_v1", "cycle_id": "cycle-01",
            "decision_sha256": decision["record_sha256"], "task_id": "task-01",
            "backend": "local_fixture", "status": "completed", "exit_code": 0,
            "trace_path": "trace.json", "trace_sha256": file_hash(self.root / "trace.json"),
            "output_path": "output.json", "output_sha256": file_hash(self.root / "output.json"),
            "cost_usd": "0", "cleanup_passed": True,
        }
        receipt.update(changes)
        return record_fixture_execution(self.root, receipt)

    def test_complete_fixture_is_never_model_or_improvement_claim(self):
        decision = self.decision()
        execution = self.execution(decision)
        review = review_fixture_cycle(self.root, {
            "schema": "market_supervisor_review_v1", "cycle_id": "cycle-01",
            "decision_sha256": decision["record_sha256"],
            "execution_sha256": execution["record_sha256"], "verdict": "accept",
            "reason": "Exact fixture artifacts match.", "feedback_summary": "No empirical result.",
            "protected_data_opened": False, "budget_ok": True,
        })
        self.assertFalse(review["controller_led_result"])
        self.assertFalse(review["empirical_improvement_claim_allowed"])

    def test_paid_or_protected_fixture_is_rejected(self):
        with self.assertRaises(ValueError):
            open_fixture_cycle(Path(self.tmp.name) / "paid", {
                "cycle_id": "paid", "parent_feedback_sha256": ZERO,
                "harness_sha256": "a" * 64, "facts_sha256": "b" * 64,
                "allowed_data_roles": ["sealed_final"], "p0_passed": False,
                "cost_cap_usd": "1", "evidence_mode": "synthetic_fixture",
            })
        with self.assertRaises(ValueError):
            self.decision(data_role="sealed_final")

    def test_decision_cannot_be_reused_or_rewritten(self):
        self.decision()
        with self.assertRaises(FileExistsError):
            self.decision()

    def test_mutated_input_is_rejected(self):
        self.root.joinpath("input.json").write_text('{"changed":true}\n')
        with self.assertRaises(ValueError):
            self.decision()

    def test_mutated_facts_are_rejected(self):
        self.root.joinpath("facts.json").write_text('{"scope":"synthetic_fixture","message":"changed"}\n')
        with self.assertRaises(ValueError):
            self.decision()

    def test_execution_must_match_decision_and_artifacts(self):
        decision = self.decision()
        with self.assertRaises(ValueError):
            self.execution(decision, decision_sha256="f" * 64)
        # A failed first receipt does not create execution.json; the artifacts
        # remain append-only, but the fixture can test a corrected receipt.
        with self.assertRaises(ValueError):
            self.execution(decision, trace_sha256="f" * 64)

    def test_raw_decision_change_after_binding_blocks_execution(self):
        decision = self.decision()
        self.root.joinpath("raw-decision.json").write_text('{"changed":true}\n')
        with self.assertRaises(ValueError):
            self.execution(decision)

    def test_trace_change_after_receipt_blocks_review(self):
        decision = self.decision()
        execution = self.execution(decision)
        self.root.joinpath("trace.json").write_text('{"changed":true}\n')
        with self.assertRaises(ValueError):
            review_fixture_cycle(self.root, {
                "schema": "market_supervisor_review_v1", "cycle_id": "cycle-01",
                "decision_sha256": decision["record_sha256"],
                "execution_sha256": execution["record_sha256"], "verdict": "accept",
                "reason": "Should reject.", "feedback_summary": "No empirical result.",
                "protected_data_opened": False, "budget_ok": True,
            })

    def test_review_rejects_failure_and_protected_open(self):
        decision = self.decision()
        execution = self.execution(decision)
        base = {
            "schema": "market_supervisor_review_v1", "cycle_id": "cycle-01",
            "decision_sha256": decision["record_sha256"],
            "execution_sha256": execution["record_sha256"], "verdict": "accept",
            "reason": "Checked.", "feedback_summary": "No empirical result.",
            "protected_data_opened": False, "budget_ok": True,
        }
        with self.assertRaises(ValueError):
            review_fixture_cycle(self.root, {**base, "execution_sha256": "f" * 64})
        with self.assertRaises(ValueError):
            review_fixture_cycle(self.root, {**base, "protected_data_opened": True})


if __name__ == "__main__":
    unittest.main()
