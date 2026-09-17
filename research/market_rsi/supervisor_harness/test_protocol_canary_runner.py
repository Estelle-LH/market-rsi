"""Offline A/B canary tests. No E2B, GLM, public fetch or paid call."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness import protocol_canary_entry, protocol_canary_runner as runner
from supervisor_harness import protocol_source_release


PUBLIC = "https://example.org/public-canary"
PRIOR = {"controller_led_result": False, "formal_admission": False,
         "review_sha256": "a" * 64, "source_manifest_sha256": "b" * 64}


class FakeFiles:
    def __init__(self):
        self.contents = {}

    def write(self, path, value):
        self.contents[path] = value


class FakeSandbox:
    def __init__(self, role, sandbox_id):
        self.role, self.sandbox_id = role, sandbox_id
        self.files = FakeFiles()
        self.commands = self
        self.killed = False

    def get_info(self):
        return SimpleNamespace(allow_internet_access=False,
            network=runner.NETWORK.copy(), template_id="base", envd_version="test")

    def run(self, command, *, timeout):
        assert "market-guest-boundary.py" in command
        return SimpleNamespace(exit_code=0, stderr="", stdout=json.dumps({
            "schema": "market_rsi_guest_boundary_v1", "role": self.role,
            "peer_file_absent": True, "paid_keys_absent": True,
            "host_home_absent": True}))

    def kill(self):
        self.killed = True
        return True


class FakeE2B:
    created = []
    active = []

    @classmethod
    def create(cls, **kwargs):
        role = kwargs["metadata"]["role"]
        sandbox = FakeSandbox(role, role + "-unique-id")
        cls.created.append(sandbox)
        cls.active.append(sandbox)
        return sandbox

    @classmethod
    def list(cls, **kwargs):
        class Pager:
            def __init__(self, items):
                self.items = items
                self.has_next = bool(items)

            def next_items(self):
                self.has_next = False
                return [SimpleNamespace(metadata={
                    "experiment_id": "market-rsi-protocol-canary"}) for _ in self.items]
        return Pager([item for item in cls.active if not item.killed])


class ProtocolCanaryRunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.doc = self.root / "state.md"
        self.doc.write_text("unchanged\n")
        self.state = SupervisorGlobalState(self.root / "global", self.doc)
        self.head = self.state.initialize()["head_sha256"]
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "fixture", "cap_usd": "1.00",
            "target_usd": "1.00", "buckets_usd": {
                "setup": "0.30", "model": "0.70"}, "authority": "offline test"})
        self.output = self.root / "protocol-01"
        self.source_sha = digest(protocol_source_release.source_hashes())
        FakeE2B.created, FakeE2B.active = [], []
        prior = patch.object(protocol_canary_entry.research_cycle_gate,
                             "verify_fixture_canary", return_value=PRIOR)
        release = patch.object(protocol_canary_entry.protocol_source_release,
            "verify_published", return_value={"commit": "c" * 40,
                                                 "source_sha256": self.source_sha})
        prior.start(); release.start()
        self.addCleanup(prior.stop); self.addCleanup(release.stop)

    def admit(self):
        protocol_canary_entry.begin_protocol_canary(
            root=self.output, cycle_id=self.output.name,
            state=self.state, budget=self.budget,
            expected_head_sha256=self.head,
            prior_fixture_root=self.root / "fixture",
            release_tag="market-rsi-protocol-v0.1.0",
            expected_source_sha256=self.source_sha, public_url=PUBLIC)

    @staticmethod
    def observed_direction(*, source, target, state, cycle_id, public_url,
                           receipt_root):
        receipt_root.mkdir()
        peer_url = f"https://{target.sandbox_id}.example/marker"
        marker_sha = "a" * 64
        attempt = {"source_sandbox_id": source.sandbox_id,
                   "target_sandbox_id": target.sandbox_id,
                   "public_url_sha256": hashlib.sha256(public_url.encode()).hexdigest(),
                   "marker_sha256": marker_sha}
        fresh_json(receipt_root / "attempt.json", attempt)
        fresh_json(receipt_root / "peer-local-positive.json",
                   {"local_service_responded": True})
        no_response = {"http_response": False, "status": None,
                       "body_sha256": None, "body_truncated": False,
                       "error_type": "URLError"}
        report = {"schema": runner.protocol_network_probe.SCHEMA,
                  "url_sha256": {
                      "public": hashlib.sha256(public_url.encode()).hexdigest(),
                      "peer": hashlib.sha256(peer_url.encode()).hexdigest()},
                  "observations": {label: {mode: no_response.copy()
                                            for mode in runner.protocol_network_probe.MODES}
                                   for label in ("public", "peer")}}
        fresh_json(receipt_root / "raw-report.json", {"raw_utf8": json.dumps(report)})
        fresh_json(receipt_root / "report.json", report)
        fresh_json(receipt_root / "review.json",
                   runner.protocol_network_probe.review(
                       report, public_url=public_url, peer_url=peer_url,
                       peer_marker_sha256=marker_sha))
        fresh_json(receipt_root / "peer-process-cleanup.json",
                   {"kill_acknowledged": True})
        result = {"attempt_sha256": file_hash(receipt_root / "attempt.json"),
                  "local_positive_sha256": file_hash(receipt_root / "peer-local-positive.json"),
                  "report_sha256": file_hash(receipt_root / "report.json"),
                  "review_sha256": file_hash(receipt_root / "review.json"),
                  "cleanup_sha256": file_hash(receipt_root / "peer-process-cleanup.json"),
                  "no_forbidden_application_payload_observed": True,
                  "isolation_proven": False}
        fresh_json(receipt_root / "observation.json", result)
        return result

    def test_child_observes_distinct_roles_and_parent_settles_after_exit(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=self.observed_direction) as directions):
            result = runner.run_child(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        self.assertEqual(directions.call_count, 2)
        self.assertFalse(result["model_authorship_proven"])
        self.assertEqual(self.budget.snapshot()["jobs"][self.output.name]["state"], "dispatched")
        self.assertEqual(len(FakeE2B.created), 2)
        self.assertTrue(all(item.killed for item in FakeE2B.created))
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=0, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "protocol_observed")
        self.assertFalse(terminal["isolation_proven"])
        self.assertEqual(self.state.snapshot()["active_cycle"], None)
        self.assertEqual(self.budget.snapshot()["effective_cost_usd"], "0.20")

    def test_unconfirmed_remote_cleanup_keeps_hold_and_state_active(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=ValueError("direction failed")),
              patch.object(FakeSandbox, "kill", return_value=False)):
            with self.assertRaisesRegex(ValueError, "direction failed"):
                runner.run_child(root=self.output, budget=self.budget,
                    state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        with self.assertRaisesRegex(ValueError, "cleanup unverified"):
            runner.reconcile_reaped(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key",
                exit_code=1, timed_out=False, stdout="", stderr="")
        self.assertEqual(self.state.snapshot()["active_cycle"], self.output.name)
        self.assertEqual(self.budget.snapshot()["jobs"][self.output.name]["state"], "dispatched")

    def test_unavailable_host_public_read_cancels_before_e2b(self):
        self.admit()
        with patch.object(runner.literature, "read",
                          side_effect=ValueError("public source unavailable")):
            with self.assertRaisesRegex(ValueError, "public source unavailable"):
                runner.run_child(root=self.output, budget=self.budget,
                    state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        self.assertEqual(FakeE2B.created, [])
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=1, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "failed_before_dispatch")
        self.assertEqual(self.budget.snapshot()["effective_cost_usd"], "0")

    def test_second_create_failure_settles_only_after_first_exact_cleanup(self):
        self.admit()
        original = FakeE2B.create
        calls = 0
        def create(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second sandbox unavailable")
            return original(**kwargs)
        with (patch.object(FakeE2B, "create", side_effect=create),
              patch.object(runner.literature, "read", return_value={
                  "receipt": {"body_sha256": "f" * 64},
                  "text_sha256": "e" * 64,
                  "read_level": "delivered_text_range_not_proof_of_understanding"})):
            with self.assertRaisesRegex(RuntimeError, "second sandbox unavailable"):
                runner.run_child(root=self.output, budget=self.budget,
                    state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        self.assertEqual(len(FakeE2B.created), 1)
        self.assertTrue(FakeE2B.created[0].killed)
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=1, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "failed")
        self.assertEqual(self.state.snapshot()["active_cycle"], None)
        self.assertEqual(self.budget.snapshot()["effective_cost_usd"], "0.20")

    def test_explicit_policy_contradiction_stops_before_second_sandbox(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(FakeSandbox, "get_info", return_value=SimpleNamespace(
                  allow_internet_access=False,
                  network={**runner.NETWORK, "allow_public_traffic": True},
                  template_id="base", envd_version="test"))):
            with self.assertRaisesRegex(ValueError, "explicitly contradicted"):
                runner.run_child(root=self.output, budget=self.budget,
                    state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        observed = json.loads((self.output / "controller-policy-observed.json").read_text())
        verdict = json.loads((self.output / "controller-policy-verdict.json").read_text())
        self.assertEqual(observed["network_response_type"], "dict")
        self.assertEqual(verdict["contradiction_fields"], ["allow_public_traffic"])
        self.assertFalse(verdict["policy_echo_accepted"])
        self.assertEqual(len(FakeE2B.created), 1)
        self.assertTrue(FakeE2B.created[0].killed)

    def test_missing_policy_echo_collects_synthetic_probes_but_still_fails(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(FakeSandbox, "get_info", return_value=SimpleNamespace(
                  allow_internet_access=False, network=None,
                  template_id="base", envd_version="test")),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=self.observed_direction) as directions):
            with self.assertRaisesRegex(ValueError, "policy echo unconfirmed"):
                runner.run_child(root=self.output, budget=self.budget,
                    state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        self.assertEqual(directions.call_count, 2)
        self.assertEqual(len(FakeE2B.created), 2)
        self.assertTrue(all(item.killed for item in FakeE2B.created))
        verdict = json.loads((self.output / "controller-policy-verdict.json").read_text())
        self.assertEqual(verdict["missing_fields"], ["network_response"])
        self.assertTrue(verdict["synthetic_diagnostic_only"])
        self.assertFalse(verdict["policy_echo_accepted"])
        summary = json.loads((self.output / "policy-diagnostic-summary.json").read_text())
        self.assertEqual(summary["roles"], ["controller", "researcher"])
        self.assertFalse(summary["isolation_proven"])
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=1, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "failed")
        self.assertFalse(terminal["isolation_proven"])

    def test_optional_allow_out_omission_completes_only_a_diagnostic(self):
        self.admit()
        echoed_without_allow_out = {"deny_out": ["0.0.0.0/0"],
                                    "allow_public_traffic": False}
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(FakeSandbox, "get_info", return_value=SimpleNamespace(
                  allow_internet_access=False, network=echoed_without_allow_out,
                  template_id="base", envd_version="test")),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=self.observed_direction) as directions):
            result = runner.run_child(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        self.assertEqual(directions.call_count, 2)
        self.assertFalse(result["isolation_proven"])
        self.assertTrue(all(item.killed for item in FakeE2B.created))
        for role in ("controller", "researcher"):
            verdict = json.loads((self.output / f"{role}-policy-verdict.json").read_text())
            self.assertEqual(verdict["missing_fields"], ["allow_out"])
            self.assertFalse(verdict["policy_echo_accepted"])
            self.assertTrue(verdict["synthetic_diagnostic_only"])
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=0, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "diagnostic_completed_policy_unconfirmed")
        self.assertFalse(terminal["isolation_proven"])
        self.assertEqual(self.state.snapshot()["active_cycle"], None)
        journal = self.state.journal.read()
        self.assertEqual(journal[-1]["payload"]["outcome"], "failed")

    def test_tampered_optional_policy_receipt_cannot_complete_diagnostic(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(FakeSandbox, "get_info", return_value=SimpleNamespace(
                  allow_internet_access=False,
                  network={"deny_out": ["0.0.0.0/0"], "allow_public_traffic": False},
                  template_id="base", envd_version="test")),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=self.observed_direction)):
            runner.run_child(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        verdict_path = self.output / "researcher-policy-verdict.json"
        verdict = json.loads(verdict_path.read_text())
        verdict["policy_echo_accepted"] = True
        verdict_path.write_text(json.dumps(verdict))
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=0, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "failed")
        self.assertFalse(terminal["isolation_proven"])

    def test_missing_raw_report_cannot_complete_optional_diagnostic(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(FakeSandbox, "get_info", return_value=SimpleNamespace(
                  allow_internet_access=False,
                  network={"deny_out": ["0.0.0.0/0"], "allow_public_traffic": False},
                  template_id="base", envd_version="test")),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=self.observed_direction)):
            runner.run_child(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        (self.output / "b-to-a" / "raw-report.json").unlink()
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=0, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "failed")
        self.assertFalse(terminal["isolation_proven"])

    def test_parent_timeout_cannot_complete_optional_diagnostic(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(FakeSandbox, "get_info", return_value=SimpleNamespace(
                  allow_internet_access=False,
                  network={"deny_out": ["0.0.0.0/0"], "allow_public_traffic": False},
                  template_id="base", envd_version="test")),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=self.observed_direction)):
            runner.run_child(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=None, timed_out=True, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "failed")
        self.assertFalse(terminal["isolation_proven"])

    def test_runtime_rejects_unpinned_dotenv_dependency(self):
        with patch.object(runner.importlib.metadata, "version",
                          side_effect=lambda name: "2.38.0" if name == "e2b" else "0.0.0"):
            with self.assertRaisesRegex(ValueError, "pinned E2B runtime"):
                runner._require_live_runtime()

    def test_parent_rejects_changed_direction_receipt_after_child(self):
        self.admit()
        with (patch.object(runner.literature, "read", return_value={
                "receipt": {"body_sha256": "f" * 64},
                "text_sha256": "e" * 64,
                "read_level": "delivered_text_range_not_proof_of_understanding"}),
              patch.object(runner.network_component, "observe_direction",
                           side_effect=self.observed_direction)):
            runner.run_child(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key", public_url=PUBLIC)
        (self.output / "a-to-b" / "review.json").write_text('{"isolation_proven":true}')
        terminal = runner.reconcile_reaped(root=self.output, budget=self.budget,
            state=self.state, sandbox_class=FakeE2B, key="fake-key",
            exit_code=0, timed_out=False, stdout="", stderr="")
        self.assertEqual(terminal["outcome"], "failed")
        self.assertFalse(terminal["isolation_proven"])
        self.assertEqual(self.budget.snapshot()["effective_cost_usd"], "0.20")

    def test_missing_key_cancels_before_child_or_provider(self):
        with self.assertRaisesRegex(ValueError, "credential unavailable"):
            runner.run_parent(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B,
                load_key=lambda: None, public_url=PUBLIC,
                expected_head_sha256=self.head,
                prior_fixture_root=self.root / "fixture",
                release_tag="market-rsi-protocol-v0.1.0",
                expected_source_sha256=self.source_sha,
                command=["never-called"],
                invoke=lambda *a, **k: self.fail("child launched without key"))
        self.assertEqual(self.state.snapshot()["active_cycle"], None)
        self.assertEqual(self.budget.snapshot()["jobs"][self.output.name]["state"],
                         "cancelled_before_dispatch")
        self.assertEqual(FakeE2B.created, [])

    def test_changed_public_probe_url_rejected_before_dispatch(self):
        self.admit()
        with self.assertRaisesRegex(ValueError, "admission/source/global state changed"):
            runner.run_child(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key",
                public_url="https://example.org/a-different-url")
        self.assertEqual(self.budget.snapshot()["jobs"][self.output.name]["state"],
                         "reserved")
        self.assertEqual(FakeE2B.created, [])

    def test_failed_child_without_remote_receipt_does_not_guess_cleanup(self):
        self.admit()
        self.budget.dispatch(self.output.name)
        with self.assertRaisesRegex(ValueError, "missing, symlinked or oversized protocol receipt"):
            runner.reconcile_reaped(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key",
                exit_code=1, timed_out=False, stdout="", stderr="")
        self.assertEqual(self.state.snapshot()["active_cycle"], self.output.name)

    def test_reserved_job_with_active_market_sandbox_cannot_cancel_as_free(self):
        self.admit()
        FakeE2B.active.append(FakeSandbox("unknown", "unreconciled-id"))
        with self.assertRaisesRegex(RuntimeError, "still active"):
            runner.reconcile_reaped(root=self.output, budget=self.budget,
                state=self.state, sandbox_class=FakeE2B, key="fake-key",
                exit_code=1, timed_out=False, stdout="", stderr="")
        self.assertEqual(self.state.snapshot()["active_cycle"], self.output.name)
        self.assertEqual(self.budget.snapshot()["jobs"][self.output.name]["state"],
                         "reserved")


if __name__ == "__main__":
    unittest.main()
