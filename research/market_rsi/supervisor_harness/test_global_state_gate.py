"""The supervisor's global state must be checked at each cycle entry."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from supervisor_harness.global_state_gate import SupervisorGlobalState, ZERO


class GlobalStateGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.doc = base / "RESEARCH_STATE.md"
        self.doc.write_text("P0 closed. Next: safe public research.\n")
        self.state = SupervisorGlobalState(base / "global-state", self.doc)

    def _claim(self, cycle_id: str, head: str):
        return self.state.claim(cycle_id, expected_head_sha256=head,
                                source_sha256="a" * 64,
                                prior_canary_sha256=ZERO)

    def test_missing_state_and_silent_document_change_fail_closed(self):
        with self.assertRaises(ValueError):
            self.state.snapshot()
        start = self.state.initialize()
        self.doc.write_text("Different priority.\n")
        with self.assertRaises(ValueError):
            self.state.snapshot()
        with self.assertRaises(ValueError):
            self._claim("round-01", start["head_sha256"])
        revised = self.state.revise_decision("Supervisor reviewed the changed priority")
        self.assertNotEqual(start["head_sha256"], revised["head_sha256"])
        self.assertEqual(self.state.snapshot(), revised)

    def test_stale_head_duplicate_and_overlapping_round_fail_closed(self):
        initial = self.state.initialize()
        claimed = self._claim("round-01", initial["head_sha256"])
        self.assertEqual(claimed["active_cycle"], "round-01")
        with self.assertRaises(ValueError):
            self._claim("round-02", initial["head_sha256"])
        with self.assertRaises(ValueError):
            self._claim("round-02", claimed["head_sha256"])
        with self.assertRaises(ValueError):
            self.state.revise_decision("Not allowed while a cycle is active")
        closed = self.state.close("round-01", outcome="passed", review_sha256="b" * 64)
        self.assertEqual(closed["last_review_sha256"], "b" * 64)
        with self.assertRaises(ValueError):
            self._claim("round-01", closed["head_sha256"])
        self._claim("round-02", closed["head_sha256"])

    def test_failed_attempt_stays_in_history_and_mutation_is_detected(self):
        initial = self.state.initialize()
        self._claim("round-01", initial["head_sha256"])
        closed = self.state.close("round-01", outcome="failed")
        self.assertEqual(closed["completed_cycles"], ["round-01"])
        with self.assertRaises(ValueError):
            self._claim("round-01", closed["head_sha256"])
        journal = self.state.journal.path
        journal.write_text(journal.read_text().replace("round-01", "round-99"))
        with self.assertRaises(ValueError):
            self.state.snapshot()

    def test_invalid_pass_cannot_poison_journal(self):
        initial = self.state.initialize()
        self._claim("round-01", initial["head_sha256"])
        with self.assertRaises(ValueError):
            self.state.close("round-01", outcome="passed")
        self.assertEqual(self.state.snapshot()["active_cycle"], "round-01")


if __name__ == "__main__":
    unittest.main()
