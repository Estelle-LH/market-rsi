"""Offline transaction tests for the v3 outer runner; zero external calls."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from glm_canary import MODEL, cost
from market_rsi import canonical, digest, load_json
from paid_budget import PaidBudget
from supervisor_harness import bounded_live_adapter_v2 as adapter
from supervisor_harness import bounded_live_outer_runner_v3 as outer
from supervisor_harness import frozen_glm_first_response as first
from supervisor_harness.global_state_gate import SupervisorGlobalState


class ClearFake:
    external_called = False

    def __init__(self, *, process_ids=None, container_ids=None):
        self.process_ids = [] if process_ids is None else process_ids
        self.container_ids = [] if container_ids is None else container_ids
        self.calls = 0

    def __call__(self, cycle_id):
        self.calls += 1
        return {"schema": outer.PREFLIGHT_SCHEMA, "cycle_id": cycle_id,
                "clear": not self.process_ids and not self.container_ids,
                "matching_process_ids": self.process_ids,
                "matching_container_ids": self.container_ids}


class OuterRunnerV3Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.index = 0

    def _fixture(self, suffix="ok", *, buckets=None, cap="0.10"):
        self.index += 1
        base = self.base / f"case-{self.index}"
        base.mkdir()
        cycle_id = "outer-v3-" + suffix
        decision = base / "decision.md"
        decision.write_text("pinned offline Supervisor decision\n")
        state = SupervisorGlobalState(base / "state", decision)
        head = state.initialize()["head_sha256"]
        budget = PaidBudget.create(base / "budget", {
            "experiment_id": "outer-v3-offline",
            "cap_usd": cap, "target_usd": cap,
            "buckets_usd": buckets or {"setup": "0.05", "other": "0.05"},
            "authority": "strict offline fake test only",
        })
        claims = base / "adapter-claims"
        claims.mkdir()
        text = "one bounded synthetic public item"
        packet = {"schema": first.PACKET_SCHEMA, "cycle_id": cycle_id,
                  "context_items": [{
                      "role": "synthetic_fixture", "source_id": "synthetic:one",
                      "text": text,
                      "text_sha256": hashlib.sha256(text.encode()).hexdigest()}]}
        choice = {"schema": adapter.offline_driver.DECISION_SCHEMA,
                  "task_id": "one-public-hash", "source_id": "synthetic:one",
                  "action": "hash_public_text"}
        sampled = {"text": canonical(choice), "output_tokens": [31, 32],
                   "cached_input_tokens": 1, "finish_reason": "stop",
                   "provider": {"reported_model": MODEL,
                                "session_id": "fake-provider-session",
                                "sampling_session_id": "fake-sampling-session"}}
        hashes = outer._current_required_hashes()
        source_sha = digest(hashes)
        publication = {
            "schema": "market_rsi_protocol_publication_v1",
            "origin": outer.protocol_source_release.ORIGIN,
            "tag": "market-rsi-protocol-v0.1.7",
            "commit": "a" * 40, "tag_object": "b" * 40,
            "source_sha256": source_sha, "source_hashes": hashes,
            "isolation_proven": False, "model_authorship_proven": False,
        }
        clear = ClearFake()
        backend = adapter.OfflinePinnedProviderFake(sampled)
        process = adapter.OfflineOneTaskProcessFake()
        control = adapter.OfflineContainerControlFake()
        args = dict(
            root=base / cycle_id, adapter_claim_root=claims,
            state=state, budget=budget, budget_root=budget.root,
            experiment_id="outer-v3-offline", budget_cap_usd=cap,
            cycle_id=cycle_id, packet=packet,
            expected_packet_sha256=digest(packet),
            expected_head_sha256=head,
            expected_decision_sha256=state.snapshot()["decision_doc_sha256"],
            prior_canary_sha256="c" * 64,
            release_tag=publication["tag"],
            expected_source_sha256=source_sha,
            expected_runtime=outer.runtime_receipt(), check_clear=clear,
            backend=backend, process=process, container_control=control)
        return base, state, budget, publication, clear, backend, process, control, args

    def _run(self, publication, args):
        with patch.object(outer.protocol_source_release, "verify_published",
                          return_value=publication):
            return outer.run_outer(**args)

    def test_success_binds_release_state_budget_one_sample_task_and_cleanup(self):
        base, state, budget, publication, clear, backend, process, control, args = \
            self._fixture("success")
        with patch.object(adapter.subprocess, "Popen",
                          side_effect=AssertionError("Docker forbidden")), \
             patch.object(adapter.subprocess, "run",
                          side_effect=AssertionError("container CLI forbidden")), \
             patch.object(adapter.TinkerGLMBackend, "sample",
                          side_effect=AssertionError("Tinker forbidden")):
            result = self._run(publication, args)
        self.assertTrue(result["passed"])
        self.assertEqual(result["ledger_outcome"], "metered_terminal")
        self.assertEqual(result["adapter_calls"], 1)
        self.assertEqual((backend.encode_calls, backend.sample_calls), (1, 1))
        self.assertEqual((process.launch_calls, process.publish_calls,
                          process.wait_calls, control.calls), (1, 1, 1, 1))
        self.assertEqual(clear.calls, 1)
        job = budget.snapshot()["jobs"][args["cycle_id"]]
        self.assertEqual(job["state"], "metered_terminal")
        self.assertEqual(job["metered_usd"], str(cost(3, 2, 1)))
        self.assertIsNone(state.snapshot()["active_cycle"])
        self.assertFalse(result["invoice_reconciled"])
        self.assertFalse(result["model_authorship_proven"])
        self.assertEqual(load_json(args["root"] / "publication.json"), publication)
        self.assertTrue(load_json(args["root"] / "adapter" / args["cycle_id"] /
                                  "cleanup.json")["exact_container_cleanup_verified"])

    def test_unpublished_or_stale_source_rejected_before_claim_and_budget(self):
        _base, state, budget, publication, _clear, backend, process, _control, args = \
            self._fixture("unpublished")
        with patch.object(outer.protocol_source_release, "verify_published",
                          side_effect=ValueError("not published")):
            with self.assertRaisesRegex(ValueError, "not published"):
                outer.run_outer(**args)
        self.assertEqual((backend.encode_calls, process.launch_calls), (0, 0))
        self.assertEqual(budget.snapshot()["jobs"], {})
        self.assertIsNone(state.snapshot()["active_cycle"])

        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("missing-source")
        publication["source_hashes"].pop(
            "supervisor_harness/bounded_live_outer_runner_v3.py")
        publication["source_sha256"] = digest(publication["source_hashes"])
        args["expected_source_sha256"] = publication["source_sha256"]
        with self.assertRaisesRegex(ValueError, "stale, incomplete or altered"):
            self._run(publication, args)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(budget.snapshot()["jobs"], {})
        self.assertIsNone(state.snapshot()["active_cycle"])

    def test_source_change_at_final_gate_cancels_reservation_and_closes_cycle(self):
        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("source-change")
        changed = dict(publication)
        changed["commit"] = "d" * 40
        with patch.object(outer.protocol_source_release, "verify_published",
                          side_effect=[publication, changed]):
            with self.assertRaisesRegex(ValueError, "pre-dispatch gate changed"):
                outer.run_outer(**args)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "cancelled_before_dispatch")
        self.assertIsNone(state.snapshot()["active_cycle"])

    def test_changed_active_and_reused_global_state_reject_without_sample(self):
        base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("changed")
        state.decision_doc.write_text("unrecorded changed decision\n")
        with self.assertRaisesRegex(ValueError, "decision document changed"):
            self._run(publication, args)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(budget.snapshot()["jobs"], {})

        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("active")
        state.claim("other-active", expected_head_sha256=args["expected_head_sha256"],
                    source_sha256=args["expected_source_sha256"],
                    prior_canary_sha256="d" * 64)
        with self.assertRaisesRegex(ValueError, "changed, active or reuses"):
            self._run(publication, args)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(budget.snapshot()["jobs"], {})

        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("reused")
        state.claim(args["cycle_id"],
                    expected_head_sha256=args["expected_head_sha256"],
                    source_sha256=args["expected_source_sha256"],
                    prior_canary_sha256="d" * 64)
        state.close(args["cycle_id"], outcome="failed")
        args["expected_head_sha256"] = state.snapshot()["head_sha256"]
        with self.assertRaisesRegex(ValueError, "changed, active or reuses"):
            self._run(publication, args)
        self.assertEqual(backend.sample_calls, 0)
        self.assertEqual(budget.snapshot()["jobs"], {})

    def test_inadequate_category_and_global_budget_reject_preclaim(self):
        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("low-category", buckets={"setup": "0.04", "other": "0.06"})
        with self.assertRaisesRegex(ValueError, "inadequate global/category"):
            self._run(publication, args)
        self.assertEqual(backend.sample_calls, 0)
        self.assertIsNone(state.snapshot()["active_cycle"])

        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("low-global")
        budget.reserve("prior-job", "other", "0.05", "fake", "e" * 64)
        budget.dispatch("prior-job")
        budget.settle_metered("prior-job", "0.05", {"terminal": True})
        budget.record_invoice("prior-job", "0.07", "f" * 64)
        with self.assertRaisesRegex(ValueError, "inadequate global/category"):
            self._run(publication, args)
        self.assertEqual(backend.sample_calls, 0)
        self.assertIsNone(state.snapshot()["active_cycle"])

    def test_matching_process_or_container_cancels_before_dispatch(self):
        for kind in ("process", "container"):
            with self.subTest(kind=kind):
                _base, state, budget, publication, _clear, backend, process, _control, args = \
                    self._fixture("matching-" + kind)
                args["check_clear"] = ClearFake(
                    process_ids=["pid-1"] if kind == "process" else [],
                    container_ids=["container-1"] if kind == "container" else [])
                with self.assertRaisesRegex(
                        ValueError,
                        "pid-1" if kind == "process" else "container-1") as caught:
                    self._run(publication, args)
                self.assertIn("matching process/container exists", str(caught.exception))
                self.assertEqual((backend.sample_calls, process.launch_calls), (0, 0))
                self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                                 "cancelled_before_dispatch")
                self.assertIsNone(state.snapshot()["active_cycle"])
                failure = load_json(args["root"] / "outer-failure.json")
                self.assertTrue(failure["pre_dispatch"])
                self.assertEqual(failure["ledger_state"],
                                 "cancelled_before_dispatch")
                self.assertEqual(failure["supervisor_state"], "closed_failed")
                self.assertTrue(failure["cancel_succeeded"])
                self.assertTrue(failure["close_succeeded"])
                self.assertEqual(failure["budget_snapshot_sha256"],
                                 digest(budget.snapshot()))
                self.assertEqual(failure["supervisor_snapshot_sha256"],
                                 digest(state.snapshot()))
                self.assertEqual(failure["reconciliation_errors"], [])

    def test_clear_distinguishes_malformed_receipt_from_valid_nonclear(self):
        valid_nonclear = {
            "schema": outer.PREFLIGHT_SCHEMA,
            "cycle_id": "exact-id",
            "clear": False,
            "matching_process_ids": ["9191"],
            "matching_container_ids": ["abc123"],
        }
        with self.assertRaisesRegex(ValueError, "9191") as caught:
            outer._clear(lambda _cycle_id: valid_nonclear, "exact-id")
        self.assertIn("abc123", str(caught.exception))

        malformed = {**valid_nonclear, "clear": True}
        with self.assertRaisesRegex(
                ValueError, "preflight is malformed or incomplete") as caught:
            outer._clear(lambda _cycle_id: malformed, "exact-id")
        self.assertNotIn("9191", str(caught.exception))

    def test_clear_callback_cannot_close_claim_then_permit_dispatch(self):
        _base, state, budget, publication, _clear, backend, process, _control, args = \
            self._fixture("callback-closes-claim")

        def closes_claim_but_returns_clear(cycle_id):
            state.close(cycle_id, outcome="failed")
            return {"schema": outer.PREFLIGHT_SCHEMA, "cycle_id": cycle_id,
                    "clear": True, "matching_process_ids": [],
                    "matching_container_ids": []}

        args["check_clear"] = closes_claim_but_returns_clear
        with self.assertRaisesRegex(ValueError, "global state is changed"):
            self._run(publication, args)
        self.assertEqual((backend.encode_calls, backend.sample_calls,
                          process.launch_calls), (0, 0, 0))
        self.assertFalse((args["root"] / "dispatched.json").exists())
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "cancelled_before_dispatch")
        self.assertIsNone(state.snapshot()["active_cycle"])
        failure = load_json(args["root"] / "outer-failure.json")
        self.assertEqual(failure["adapter_calls"], 0)
        self.assertEqual(failure["ledger_state"], "cancelled_before_dispatch")
        self.assertEqual(failure["supervisor_state"], "closed_failed")
        self.assertTrue(failure["close_already_observed"])
        self.assertFalse(failure["close_attempted"])
        self.assertEqual(failure["reconciliation_errors"], [])

    def test_pre_dispatch_reconciliation_errors_preserve_primary_failure(self):
        _base, state, budget, publication, _clear, backend, process, _control, args = \
            self._fixture("pre-dispatch-reconciliation-errors")
        args["check_clear"] = ClearFake(process_ids=["pid-1"])
        with patch.object(budget, "cancel_before_dispatch",
                          side_effect=RuntimeError("fake cancel failure")), \
             patch.object(state, "close",
                          side_effect=RuntimeError("fake close failure")):
            with self.assertRaisesRegex(ValueError, "matching process/container"):
                self._run(publication, args)
        self.assertEqual((backend.sample_calls, process.launch_calls), (0, 0))
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "reserved")
        self.assertEqual(state.snapshot()["active_cycle"], args["cycle_id"])
        failure = load_json(args["root"] / "outer-failure.json")
        self.assertEqual(failure["error_type"], "ValueError")
        self.assertEqual(failure["ledger_state"], "reserved")
        self.assertEqual(failure["supervisor_state"], "active_unresolved")
        self.assertFalse(failure["cancel_succeeded"])
        self.assertFalse(failure["close_succeeded"])
        self.assertEqual([item["action"] for item in
                          failure["reconciliation_errors"]],
                         ["cancel_before_dispatch", "state_close_failed"])

    def test_wrong_runtime_image_and_public_packet_reject_before_claim(self):
        for kind in ("image", "runtime", "packet", "packet-hash", "protected"):
            with self.subTest(kind=kind):
                _base, state, budget, publication, _clear, backend, process, _control, args = \
                    self._fixture("wrong-" + kind)
                if kind == "image":
                    args["expected_runtime"] = {**args["expected_runtime"],
                                                "container_image": "python:latest"}
                elif kind == "runtime":
                    args["expected_runtime"] = {**args["expected_runtime"],
                                                "python_version": "changed"}
                elif kind == "packet":
                    second = dict(args["packet"]["context_items"][0])
                    second["source_id"] = "synthetic:two"
                    args["packet"] = {**args["packet"],
                                      "context_items": [
                                          args["packet"]["context_items"][0], second]}
                elif kind == "packet-hash":
                    item = dict(args["packet"]["context_items"][0])
                    item["text"] = "different but otherwise valid synthetic item"
                    item["text_sha256"] = hashlib.sha256(
                        item["text"].encode()).hexdigest()
                    args["packet"] = {**args["packet"], "context_items": [item]}
                else:
                    args["packet"] = {**args["packet"], "final_labels": [1]}
                with self.assertRaises(ValueError):
                    self._run(publication, args)
                self.assertEqual((backend.sample_calls, process.launch_calls), (0, 0))
                self.assertEqual(budget.snapshot()["jobs"], {})
                self.assertIsNone(state.snapshot()["active_cycle"])

    def test_duplicate_id_cannot_make_a_second_adapter_call(self):
        base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("duplicate")
        self._run(publication, args)
        second_backend = adapter.OfflinePinnedProviderFake(backend.sampled)
        second_parent = base / "second"
        second_parent.mkdir()
        second_args = {**args, "root": second_parent / args["cycle_id"],
                       "expected_head_sha256": state.snapshot()["head_sha256"],
                       "backend": second_backend,
                       "process": adapter.OfflineOneTaskProcessFake(),
                       "container_control": adapter.OfflineContainerControlFake()}
        with self.assertRaisesRegex(ValueError, "changed, active or reuses"):
            self._run(publication, second_args)
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(second_backend.sample_calls, 0)

    def test_provider_timeout_or_missing_cost_settles_uncertain_and_closes_failed(self):
        for kind in ("timeout", "missing-cost"):
            with self.subTest(kind=kind):
                _base, state, budget, publication, _clear, backend, process, _control, args = \
                    self._fixture("provider-" + kind)
                if kind == "timeout":
                    backend.sample_error = TimeoutError("offline fake timeout")
                else:
                    backend.sampled = dict(backend.sampled)
                    backend.sampled.pop("cached_input_tokens")
                with self.assertRaisesRegex(RuntimeError, "adapter receipts"):
                    self._run(publication, args)
                self.assertEqual(backend.sample_calls, 1)
                self.assertEqual(process.launch_calls, 0)
                self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                                 "uncertain_terminal")
                self.assertIsNone(state.snapshot()["active_cycle"])
                self.assertEqual(load_json(args["root"] / "result.json")
                                 ["supervisor_outcome"], "failed")

    def test_malformed_provider_receipt_is_not_treated_as_metered(self):
        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("malformed-provider-receipt")
        original = adapter.run_bounded_adapter

        def tamper(**kwargs):
            result = original(**kwargs)
            path = kwargs["root"] / "provider-receipt.json"
            receipt = load_json(path)
            receipt["provider_called"] = "not-a-boolean"
            path.write_text(canonical(receipt) + "\n")
            return result

        with patch.object(adapter, "run_bounded_adapter", side_effect=tamper):
            with self.assertRaisesRegex(RuntimeError, "adapter receipts"):
                self._run(publication, args)
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "uncertain_terminal")
        self.assertIsNone(state.snapshot()["active_cycle"])

    def test_missing_process_or_cleanup_preserves_dispatched_active_evidence(self):
        for kind in ("process", "cleanup"):
            with self.subTest(kind=kind):
                _base, state, budget, publication, _clear, backend, process, control, args = \
                    self._fixture("missing-" + kind)
                if kind == "process":
                    process.mode = "process_timeout"
                else:
                    control.mode = "missing_cleanup"
                with self.assertRaisesRegex(RuntimeError, "process/cleanup unresolved"):
                    self._run(publication, args)
                self.assertEqual(backend.sample_calls, 1)
                self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                                 "dispatched")
                self.assertEqual(state.snapshot()["active_cycle"], args["cycle_id"])
                unresolved = load_json(args["root"] / "outer-unresolved.json")
                self.assertIn("process.json", unresolved["preserved_adapter_files"])
                self.assertIn("cleanup.json", unresolved["preserved_adapter_files"])

    def test_malformed_process_receipt_preserves_dispatched_active_evidence(self):
        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("malformed-process-receipt")
        original = adapter.run_bounded_adapter

        def tamper(**kwargs):
            result = original(**kwargs)
            path = kwargs["root"] / "process.json"
            receipt = load_json(path)
            receipt["unexpected"] = True
            path.write_text(canonical(receipt) + "\n")
            return result

        with patch.object(adapter, "run_bounded_adapter", side_effect=tamper):
            with self.assertRaisesRegex(RuntimeError, "process/cleanup unresolved"):
                self._run(publication, args)
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "dispatched")
        self.assertEqual(state.snapshot()["active_cycle"], args["cycle_id"])

    def test_partial_launch_failure_keeps_receipts_then_meters_and_closes_failed(self):
        _base, state, budget, publication, _clear, backend, process, control, args = \
            self._fixture("partial-launch")
        process.mode = "launch_error_after_start"
        with self.assertRaisesRegex(RuntimeError, "adapter receipts"):
            self._run(publication, args)
        adapter_root = args["root"] / "adapter" / args["cycle_id"]
        self.assertEqual((backend.sample_calls, process.launch_calls,
                          process.wait_calls, control.calls), (1, 1, 1, 1))
        self.assertTrue((adapter_root / "raw-response.json").is_file())
        self.assertTrue(load_json(adapter_root / "cleanup.json")
                        ["exact_container_cleanup_verified"])
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "metered_terminal")
        self.assertIsNone(state.snapshot()["active_cycle"])

    def test_settlement_failure_leaves_dispatch_and_claim_unresolved(self):
        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("settlement-failure")
        with patch.object(PaidBudget, "settle_metered",
                          side_effect=RuntimeError("fake settlement failure")):
            with self.assertRaisesRegex(RuntimeError, "fake settlement failure"):
                self._run(publication, args)
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "dispatched")
        self.assertEqual(state.snapshot()["active_cycle"], args["cycle_id"])
        failure = load_json(args["root"] / "outer-failure.json")
        self.assertEqual(failure["stage"], "budget_reconciliation")

    def test_close_failure_keeps_terminal_ledger_and_active_claim(self):
        _base, state, budget, publication, _clear, backend, _process, _control, args = \
            self._fixture("close-failure")
        original = state.close
        with patch.object(state, "close",
                          side_effect=RuntimeError("fake close failure")):
            with self.assertRaisesRegex(RuntimeError, "fake close failure"):
                self._run(publication, args)
        self.assertEqual(backend.sample_calls, 1)
        self.assertEqual(budget.snapshot()["jobs"][args["cycle_id"]]["state"],
                         "metered_terminal")
        self.assertEqual(state.snapshot()["active_cycle"], args["cycle_id"])
        self.assertEqual(load_json(args["root"] / "outer-failure.json")["stage"],
                         "global_close")

    def test_arbitrary_boundary_types_reject_before_claim_or_dispatch(self):
        for field in ("backend", "process", "container_control"):
            with self.subTest(field=field):
                _base, state, budget, publication, _clear, backend, process, _control, args = \
                    self._fixture("bad-interface-" + field)
                args[field] = object()
                with self.assertRaisesRegex(RuntimeError, "exact matched types"):
                    self._run(publication, args)
                self.assertEqual((backend.sample_calls, process.launch_calls), (0, 0))
                self.assertEqual(budget.snapshot()["jobs"], {})
                self.assertIsNone(state.snapshot()["active_cycle"])
        self.assertFalse(hasattr(outer, "main"))


if __name__ == "__main__":
    unittest.main()
