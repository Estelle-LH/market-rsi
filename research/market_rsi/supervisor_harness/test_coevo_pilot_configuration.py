"""Pure synthetic prospective configuration tests; no data/model calls."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from supervisor_harness import coevo_pilot_transaction as p
from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness.test_coevo_pilot_transaction import PilotTests


class ConfigurationTests(unittest.TestCase):
    write, rebind, response, transport = PilotTests.write, PilotTests.rebind, PilotTests.response, PilotTests.transport

    def setUp(self):
        PilotTests.setUp(self)
        self.config = {"schema": "supervisor_reviewed_pilot_configuration_v1",
            "batch_id": self.root.name, "root": str(self.root), **p.TIMES,
            "limits": {**p.LIMITS, "candidate_attempts": 3, "statistical_fits": 12,
                       "original_controller_decisions": 3, "live_candidate_processes": 1}}
        self.configuration_binding = self.write("configuration", self.config)
        self.authorization.update(batch_id=self.config["batch_id"], limits=self.config["limits"])
        self.authorization["account_transfer"].update(max_input_bytes=32768,
            payload_scope=["private Train-derived aggregate feedback", "research memory/history", "relevant candidate source context"])
        self.authorization_binding = self.write("authorization", self.authorization)
        self.ledger["batch_id"] = self.config["batch_id"]; self.write("ledger", self.ledger)
        self.packet["authority"] = self.authorization; self.rebind_config()

    def rebind_config(self):
        self.rebind(); self.review["configuration_sha256"] = self.configuration_binding["sha256"]
        self.review_binding = self.write("operation-review", self.review)

    def call(self, transport=None):
        return p.call(self.root, self.input_binding, self.authorization_binding,
            self.review_binding, self.f.repo, transport=transport or self.transport,
            configuration_binding=self.configuration_binding)

    def test_configured_original_success_and_recovery_once(self):
        first = self.call(); self.assertEqual(self.call(), first); self.assertEqual(self.calls, 1)
        claim = p._file(next((self.root / "decisions").iterdir()) / "claim.json")
        self.assertEqual(claim["configuration_sha256"], self.configuration_binding["sha256"])

    def test_hard_caps_types_threads_and_duration_before_claim(self):
        original = deepcopy(self.config)
        for key, value in (("candidate_attempts", 4), ("statistical_fits", 16),
                           ("original_controller_decisions", 4), ("candidate_attempts", True),
                           ("threads_per_candidate", 2), ("paid_provider_calls", 1),
                           ("live_candidate_processes", 2), ("sampled_rss_bytes", 1073741825)):
            config = deepcopy(original); config["limits"][key] = value
            binding = self.write("configuration", config)
            with self.subTest(key=key), self.assertRaises(ValueError): p._configuration(binding, self.root)
        config = deepcopy(original); config["deadline_utc"] = "2026-10-06T18:16:26Z"
        with self.assertRaises(ValueError): p._configuration(self.write("configuration", config), self.root)
        self.assertEqual(self.calls, 0)

    def test_missing_review_configuration_or_authority_drift(self):
        self.review.pop("configuration_sha256"); self.review_binding = self.write("operation-review", self.review)
        with self.assertRaisesRegex(ValueError, "review drift"): self.call()
        self.rebind_config(); self.authorization["limits"] = {**self.config["limits"], "candidate_attempts": 2}
        self.authorization_binding = self.write("authorization", self.authorization)
        self.packet["authority"] = self.authorization; self.rebind_config()
        with self.assertRaisesRegex(ValueError, "exact user grant"): self.call()
        self.assertEqual(self.calls, 0)

    def test_uncertain_call_no_retry_or_refund(self):
        def interrupted(*_): self.calls += 1; raise RuntimeError("unknown completion")
        with self.assertRaises(RuntimeError): self.call(interrupted)
        with self.assertRaises(FileNotFoundError): self.call()
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(p._file(self.root / "ledger.json")["controller_decisions"]), 1)

    def test_three_decision_cap_and_closed_ledger(self):
        self.ledger["controller_decisions"] = [{"feedback_sha256": str(n) * 64, "status": "completed"} for n in (7, 8, 9)]
        self.write("ledger", self.ledger)
        with self.assertRaisesRegex(RuntimeError, "pilot cap"): self.call()
        self.ledger["controller_decisions"] = []; self.ledger["status"] = "closed"; self.write("ledger", self.ledger)
        with self.assertRaisesRegex(RuntimeError, "pilot cap"): self.call()
        self.assertEqual(self.calls, 0)

    def test_cutoff_extra_fields_wrong_root_and_changed_recovery(self):
        class Closed(datetime):
            @classmethod
            def now(cls, tz=None): return datetime(2026, 10, 6, 18, 12, tzinfo=timezone.utc)
        with patch.object(p, "datetime", Closed), self.assertRaisesRegex(ValueError, "selection window"): self.call()
        bad = {**self.config, "granted": True}
        with self.assertRaises(ValueError): p._configuration(self.write("configuration", bad), self.root)
        self.configuration_binding = self.write("configuration", self.config); self.rebind_config(); self.call()
        self.config["limits"]["candidate_attempts"] = 2; self.config["limits"]["statistical_fits"] = 8
        self.config["limits"]["original_controller_decisions"] = 2
        self.configuration_binding = self.write("configuration", self.config); self.rebind_config()
        with self.assertRaisesRegex(ValueError, "claim/input/schema"): self.call()
        self.assertEqual(self.calls, 1)


if __name__ == "__main__": unittest.main()
