import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake, expected_packet,
)
from supervisor_harness.p0_gate1_controller_outer import run_outer
from supervisor_harness.p0_gate1_research_contract import DECISION_SCHEMA


def decision():
    return {
        "schema": DECISION_SCHEMA,
        "investigation_id": "gate1-outer-001",
        "question_id": "2025_whole_season_trade_access",
        "source_id": "polymarket_official_trades",
        "hypothesis": "The official interface documents historical market trade access.",
        "fixed_sample_rule": "Inspect the one frozen official documentation page.",
        "requested_operations": ["inspect_official_documentation"],
        "expected_evidence": "A bounded page hash and documented interface fields.",
        "rights_check": "Record only rights stated by the official source.",
        "max_requests": 1,
        "max_bytes": 100000,
        "max_minutes": 10,
        "max_provider_cost_usd": "0",
        "stop_rule": "Stop after one response or any redirect, error, timeout, or rights uncertainty.",
    }


def sampled(text, finish="stop"):
    return {
        "text": text,
        "output_tokens": [401, 402, 403],
        "cached_input_tokens": 0,
        "finish_reason": finish,
        "provider": {
            "reported_model": "zai-org/GLM-5.3",
            "session_id": "offline-outer-session",
            "sampling_session_id": "offline-outer-sampling",
        },
    }


class Gate1ControllerOuterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.claims = self.parent / "claims"
        self.claims.mkdir()
        self.decision_doc = self.parent / "decision.md"
        self.decision_doc.write_text("frozen decision\n")
        self.state = SupervisorGlobalState(
            self.parent / "state", self.decision_doc)
        state = self.state.initialize()
        self.head = state["head_sha256"]
        self.decision_sha = file_hash(self.decision_doc)
        self.budget_root = self.parent / "budget"
        self.budget = PaidBudget.create(self.budget_root, {
            "experiment_id": "gate1-test-budget",
            "cap_usd": "1",
            "target_usd": "0.5",
            "buckets_usd": {"setup": "0.5", "repair": "0.5"},
            "authority": "offline unit test only",
        })
        self.packet = expected_packet()
        self.runtime = {"schema": "offline-runtime"}
        self.publication = {
            "schema": "market_rsi_protocol_publication_v1",
            "origin": "offline",
            "tag": "market-rsi-protocol-v-test",
            "commit": "1" * 40,
            "tag_object": "2" * 40,
            "source_sha256": "3" * 64,
            "source_hashes": {},
            "isolation_proven": False,
            "model_authorship_proven": False,
        }

    def call(self, backend, cycle="gate1-outer-test-001"):
        with (patch("supervisor_harness.p0_gate1_controller_outer._publication",
                    return_value=self.publication),
              patch("supervisor_harness.p0_gate1_controller_outer.shared._runtime",
                    return_value=self.runtime)):
            return run_outer(
                root=self.parent / cycle,
                claim_root=self.claims,
                state=self.state,
                budget=self.budget,
                budget_root=self.budget_root,
                experiment_id="gate1-test-budget",
                budget_cap_usd="1",
                cycle_id=cycle,
                packet=self.packet,
                expected_packet_sha256=digest(self.packet),
                expected_head_sha256=self.head,
                expected_decision_sha256=self.decision_sha,
                prior_canary_sha256="4" * 64,
                release_tag="market-rsi-protocol-v-test",
                expected_source_sha256="3" * 64,
                expected_runtime=self.runtime,
                check_clear=lambda cycle_id: {
                    "schema": "market_bounded_live_outer_preflight_v3",
                    "cycle_id": cycle_id,
                    "clear": True,
                    "matching_process_ids": [],
                    "matching_container_ids": [],
                },
                backend=backend,
            )

    def test_valid_response_settles_metered_and_closes_passed(self):
        result = self.call(OfflineGate1ProviderFake(
            sampled(json.dumps(decision()))))
        self.assertTrue(result["passed"])
        job = self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
        self.assertEqual(job["state"], "metered_terminal")
        state = self.state.snapshot()
        self.assertIsNone(state["active_cycle"])
        self.assertNotEqual(state["last_review_sha256"], "0" * 64)

    def test_reused_adapter_claim_fails_before_global_or_budget_claim(self):
        (self.claims / "gate1-outer-test-001.json").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "permanently claimed"):
            self.call(OfflineGate1ProviderFake(
                sampled(json.dumps(decision()))))
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_malformed_but_metered_response_closes_failed_without_retry(self):
        with self.assertRaisesRegex(RuntimeError, "failed review"):
            self.call(OfflineGate1ProviderFake(sampled("not json")))
        job = self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
        self.assertEqual(job["state"], "metered_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])
        root = self.parent / "gate1-outer-test-001"
        self.assertTrue((root / "outer-failure.json").is_file())
        adapter_result = json.loads(
            (root / "adapter/gate1-outer-test-001/result.json").read_text())
        self.assertEqual(adapter_result["sample_count_max"], 1)

    def test_unmetered_sample_failure_keeps_full_upper(self):
        backend = OfflineGate1ProviderFake(
            sampled(json.dumps(decision())),
            sample_error=TimeoutError("uncertain provider timeout"))
        with self.assertRaisesRegex(RuntimeError, "failed review"):
            self.call(backend)
        job = self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
        self.assertEqual(job["state"], "uncertain_terminal")
        self.assertEqual(job["uncertain_upper_usd"], "0.05")
        self.assertEqual(backend.sample_calls, 1)

    def test_crash_before_dispatch_cancels_and_closes_failed(self):
        backend = OfflineGate1ProviderFake(sampled(json.dumps(decision())))
        with patch(
                "supervisor_harness.p0_gate1_controller_outer.adapter.run",
                side_effect=RuntimeError("crash after dispatch")) as mocked:
            # The patched adapter never invokes the supplied dispatch callback,
            # so force the same boundary directly by wrapping the fake backend's
            # sample is not representative. This assertion instead covers the
            # pre-dispatch branch: no send means reservation is cancelled and
            # the global cycle closes failed.
            with self.assertRaisesRegex(RuntimeError, "crash after dispatch"):
                self.call(backend)
        self.assertEqual(mocked.call_count, 1)
        job = self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
        self.assertEqual(job["state"], "cancelled_before_dispatch")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_unreconciled_dispatch_stays_globally_active_for_repair(self):
        backend = OfflineGate1ProviderFake(sampled(json.dumps(decision())))

        def crash_after_dispatch(**kwargs):
            from glm_canary import cost
            from supervisor_harness.p0_gate1_controller_adapter import MAX_OUTPUT_TOKENS
            upper = cost(len(kwargs["preencoded"]["token_ids"]),
                         MAX_OUTPUT_TOKENS)
            kwargs["before_sample"]({
                "schema": "market_p0_gate1_controller_cost_preview_v1",
                "upper_usd_not_invoice": str(upper),
            })
            raise RuntimeError("crash after dispatch")

        with patch(
                "supervisor_harness.p0_gate1_controller_outer.adapter.run",
                side_effect=crash_after_dispatch):
            with self.assertRaisesRegex(RuntimeError, "crash after dispatch"):
                self.call(backend)
        job = self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
        self.assertEqual(job["state"], "dispatched")
        self.assertEqual(
            self.state.snapshot()["active_cycle"], "gate1-outer-test-001")


if __name__ == "__main__":
    unittest.main()
