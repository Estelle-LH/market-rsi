import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake, PROPOSE_TOOL, SUBMIT_TOOL, expected_packet,
)
from supervisor_harness import p0_gate1_controller_adapter as adapter
from supervisor_harness.p0_gate1_controller_outer import run_outer
from supervisor_harness.p0_gate1_plan_compiler import SYNTHETIC_CATALOG_COMMITMENT_ID
from supervisor_harness.p0_gate1_research_contract import EXACT_TRADE_SAMPLE_RULE
from supervisor_harness.test_p0_gate1_plan_compiler import synthetic_catalog


def decision():
    return {
        "choice_id": "pm_trades_docs_one",
        "question_id": "2025_whole_season_trade_access",
        "hypothesis": "The official interface documents historical market trade access.",
        "expected_evidence": "A bounded page hash and documented interface fields.",
        "stop_rule": "Stop after one response or any redirect, error, timeout, or rights uncertainty.",
    }


def trade_decision():
    value = decision()
    value.update({
        "source_id": "polymarket_official_trades",
        "fixed_sample_rule": EXACT_TRADE_SAMPLE_RULE,
        "requested_operations": ["fetch_fixed_public_sample"],
        "max_requests": 6,
        "max_bytes": 2_000_000,
        "max_minutes": 15,
    })
    return value


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


def submitted(value: dict, *, tool: str = SUBMIT_TOOL) -> str:
    arguments = []
    for key, item in value.items():
        encoded = item if isinstance(item, str) else json.dumps(
            item, separators=(",", ":"))
        arguments.append(
            f"<arg_key>{key}</arg_key><arg_value>{encoded}</arg_value>")
    return (f"<tool_call>{tool}" + "".join(arguments)
            + "</tool_call>")


def proposal():
    return {
        "proposal_id": "outer-novel-source-001",
        "kind": "new_source",
        "hypothesis": "A new public archive may contain missing real fills.",
        "candidate_source": "An unregistered public archive",
        "method": "Check rights and a fixed public sample.",
        "fixed_sample_rule": "First game by public schedule order.",
        "expected_evidence": "Version, rights, raw fill receipts or an exact miss.",
        "stop_rule": "Stop after one sample or a rights failure.",
        "max_requests": 3,
        "max_bytes": 1000000,
        "max_minutes": 10,
        "max_provider_cost_usd": "0",
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

    def call(self, backend, cycle="gate1-outer-test-001", **catalog_binding):
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
                **catalog_binding,
            )

    def call_with_offline_catalog_ready_packet(
            self, backend, cycle="gate1-outer-test-001", **catalog_binding):
        # Exercise the future catalog-ready branch only with a test-scoped
        # packet. The production frozen packet continues to hide trade.
        self.packet = copy.deepcopy(expected_packet())
        self.packet["current_execution_boundary"][
            "reviewed_real_train_catalog_available"] = True
        with patch.object(adapter, "expected_packet", return_value=self.packet):
            return self.call(backend, cycle=cycle, **catalog_binding)

    def test_valid_response_settles_metered_and_closes_passed(self):
        result = self.call(OfflineGate1ProviderFake(
            sampled(submitted(decision()))))
        self.assertTrue(result["passed"])
        job = self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
        self.assertEqual(job["state"], "metered_terminal")
        state = self.state.snapshot()
        self.assertIsNone(state["active_cycle"])
        self.assertNotEqual(state["last_review_sha256"], "0" * 64)

    def test_hidden_trade_plan_fails_at_adapter_without_catalog(self):
        with self.assertRaisesRegex(RuntimeError, "failed review"):
            self.call(OfflineGate1ProviderFake(
                sampled(submitted(trade_decision()))))
        adapter_root = self.parent / "gate1-outer-test-001/adapter/gate1-outer-test-001"
        self.assertFalse((adapter_root / "task.json").exists())
        self.assertFalse((adapter_root / "exact-request-manifest.json").exists())
        self.assertEqual(self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
                         ["state"], "metered_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_catalog_flag_cannot_expose_unoffered_trade_choice(self):
        with self.assertRaisesRegex(RuntimeError, "failed review"):
            self.call_with_offline_catalog_ready_packet(OfflineGate1ProviderFake(
                sampled(submitted(trade_decision()))),
                catalog_json=synthetic_catalog(),
                catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID)
        self.assertFalse((self.parent / "gate1-outer-test-001"
                          / "compiled-plan.json").exists())
        self.assertEqual(self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
                         ["state"], "metered_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_trade_plan_rejects_changed_or_unknown_catalog(self):
        for cycle, catalog, commitment in (
                ("gate1-bad-catalog-001", synthetic_catalog() + b" ",
                 SYNTHETIC_CATALOG_COMMITMENT_ID),
                ("gate1-bad-catalog-002", synthetic_catalog(),
                 "unreviewed-real-catalog")):
            with self.subTest(cycle=cycle):
                self.head = self.state.snapshot()["head_sha256"]
                with self.assertRaisesRegex(RuntimeError, "failed review"):
                    self.call_with_offline_catalog_ready_packet(OfflineGate1ProviderFake(
                        sampled(submitted(trade_decision()))), cycle=cycle,
                        catalog_json=catalog,
                        catalog_commitment_id=commitment)
                self.assertFalse((self.parent / cycle / "compiled-plan.json").exists())
                self.assertEqual(self.budget.snapshot()["jobs"][cycle]["state"],
                                 "metered_terminal")

    def test_synthetic_catalog_cannot_pass_live_review(self):
        # This patch simulates the live mode for the review rule only; it does
        # not contact a provider and cannot be used as live admission proof.
        with patch.object(adapter, "_mode", return_value="live_pinned"):
            with self.assertRaisesRegex(ValueError, "reviewed real Train catalog"):
                self.call_with_offline_catalog_ready_packet(OfflineGate1ProviderFake(
                    sampled(submitted(trade_decision()))),
                    catalog_json=synthetic_catalog(),
                    catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID)
        self.assertFalse((self.parent / "gate1-outer-test-001"
                          / "compiled-plan.json").exists())
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_simulated_live_document_or_proposal_can_finish_without_catalog(self):
        # A missing trade catalog cannot block the data-investigation lane.
        # The fake is patched to exercise live-mode review only: no provider.
        for cycle, answer, tool in (
                ("gate1-no-catalog-doc-001", decision(), SUBMIT_TOOL),
                ("gate1-no-catalog-proposal-001", proposal(), PROPOSE_TOOL)):
            with self.subTest(cycle=cycle), patch.object(
                    adapter, "_mode", return_value="live_pinned"):
                self.head = self.state.snapshot()["head_sha256"]
                result = self.call(OfflineGate1ProviderFake(
                    sampled(submitted(answer, tool=tool))), cycle=cycle)
                self.assertTrue(result["passed"])
                self.assertFalse((self.parent / cycle / "compiled-plan.json").exists())
                self.assertEqual(self.budget.snapshot()["jobs"][cycle]["state"],
                                 "metered_terminal")

    def test_simulated_live_trade_without_catalog_fails_terminal_review(self):
        with patch.object(adapter, "_mode", return_value="live_pinned"):
            with self.assertRaisesRegex(RuntimeError, "failed review"):
                self.call(OfflineGate1ProviderFake(
                    sampled(submitted(trade_decision()))))
        self.assertEqual(self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
                         ["state"], "metered_terminal")
        self.assertFalse((self.parent / "gate1-outer-test-001"
                          / "compiled-plan.json").exists())

    def test_expanded_decision_byte_tamper_fails_outer_review(self):
        original = adapter.run

        def alter(**kwargs):
            result = original(**kwargs)
            path = kwargs["root"] / "decision.json"
            path.write_text(path.read_text() + " ")
            return result

        with patch("supervisor_harness.p0_gate1_controller_outer.adapter.run",
                   side_effect=alter):
            with self.assertRaisesRegex(RuntimeError, "failed review"):
                self.call(OfflineGate1ProviderFake(
                    sampled(submitted(decision()))))
        self.assertEqual(self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
                         ["state"], "metered_terminal")

    def test_changed_submission_or_provenance_fails_outer_replay(self):
        original = adapter.run
        for cycle, name, field, replacement in (
                ("gate1-tampered-submission-001", "submission.json",
                 "choice_id", "pm_market_docs_one"),
                ("gate1-tampered-provenance-001", "field-provenance.json",
                 "run_claim_id", "gate1-other-claim-001")):
            def alter(**kwargs):
                result = original(**kwargs)
                path = kwargs["root"] / name
                value = json.loads(path.read_text())
                value[field] = replacement
                path.write_text(json.dumps(value))
                return result
            with self.subTest(cycle=cycle), patch(
                    "supervisor_harness.p0_gate1_controller_outer.adapter.run",
                    side_effect=alter):
                self.head = self.state.snapshot()["head_sha256"]
                with self.assertRaisesRegex(RuntimeError, "failed review"):
                    self.call(OfflineGate1ProviderFake(
                        sampled(submitted(decision()))), cycle=cycle)
                self.assertEqual(self.budget.snapshot()["jobs"][cycle]["state"],
                                 "metered_terminal")

    def test_novel_proposal_settles_without_granting_a_task(self):
        result = self.call(OfflineGate1ProviderFake(
            sampled(submitted(proposal(), tool=PROPOSE_TOOL))))
        self.assertTrue(result["passed"])
        self.assertEqual(result["submission_kind"], "non_executable_proposal")
        root = self.parent / "gate1-outer-test-001"
        adapter_root = root / "adapter/gate1-outer-test-001"
        self.assertTrue((adapter_root / "proposal.json").is_file())
        self.assertFalse((adapter_root / "task.json").exists())
        self.assertEqual(self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
                         ["state"], "metered_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_proposal_cannot_gain_a_task_after_adapter_returns(self):
        original = adapter.run

        def inject_task(**kwargs):
            result = original(**kwargs)
            (kwargs["root"] / "task.json").write_text('{"executable":true}\n')
            return result

        with patch("supervisor_harness.p0_gate1_controller_outer.adapter.run",
                   side_effect=inject_task):
            with self.assertRaisesRegex(RuntimeError, "failed review"):
                self.call(OfflineGate1ProviderFake(
                    sampled(submitted(proposal(), tool=PROPOSE_TOOL))))
        self.assertEqual(self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
                         ["state"], "metered_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_modified_proposal_archive_fails_outer_review(self):
        original = adapter.run

        def alter_proposal(**kwargs):
            result = original(**kwargs)
            path = kwargs["root"] / "proposal.json"
            value = json.loads(path.read_text())
            value["network_authorized"] = True
            path.write_text(json.dumps(value))
            return result

        with patch("supervisor_harness.p0_gate1_controller_outer.adapter.run",
                   side_effect=alter_proposal):
            with self.assertRaisesRegex(RuntimeError, "failed review"):
                self.call(OfflineGate1ProviderFake(
                    sampled(submitted(proposal(), tool=PROPOSE_TOOL))))
        self.assertEqual(self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
                         ["state"], "metered_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_reused_adapter_claim_fails_before_global_or_budget_claim(self):
        (self.claims / "gate1-outer-test-001.json").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "permanently claimed"):
            self.call(OfflineGate1ProviderFake(
                sampled(submitted(decision()))))
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
            sampled(submitted(decision())),
            sample_error=TimeoutError("uncertain provider timeout"))
        with self.assertRaisesRegex(RuntimeError, "failed review"):
            self.call(backend)
        job = self.budget.snapshot()["jobs"]["gate1-outer-test-001"]
        self.assertEqual(job["state"], "uncertain_terminal")
        self.assertEqual(job["uncertain_upper_usd"], "0.05")
        self.assertEqual(backend.sample_calls, 1)

    def test_crash_before_dispatch_cancels_and_closes_failed(self):
        backend = OfflineGate1ProviderFake(sampled(submitted(decision())))
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
        backend = OfflineGate1ProviderFake(sampled(submitted(decision())))

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
