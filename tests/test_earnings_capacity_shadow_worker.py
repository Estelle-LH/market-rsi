"""Pending literal profiles reach the real worker, never native adoption.

All company/model responses are invented. This suite uses the real native
proposal journal, public-record store and unchanged forecaster. No provider,
ledger or acceptance/benefit fixture is needed. A native rejection is used only
to test loss/replacement of the exact pending token, not predictive refutation.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import edgar_forecast_openai as forecast
import earnings_capacity_worker as worker_module
from market_rsi import digest
import test_earnings_capacity_adapter as capacity_fixture
import test_earnings_research_state as state_fixture


class PendingShadowWorkerTests(unittest.TestCase):
    def setUp(self):
        self.native = capacity_fixture.EarningsCapacityTests(
            "test_earnings_reject_keeps_parent_and_history")
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        self.data = state_fixture.ResearchStateTests(
            "test_append_preserves_parent_and_old_history")
        self.data.setUp()
        self.addCleanup(self.data.doCleanups)
        self.root, self.company = self.native.root, self.data.company
        self.capacity = self.native.adapter
        self.active_pair = digest(self.native.batch.snapshot()["micro_evolution"]["active_pair"])
        self.rate = {"api_model": "gpt-6.1-sol", "effort": "xhigh"}
        self.config = {"max_turns_per_company": 3, "company_wall_seconds": 30}
        self.requests = []
        self.serial = 0

    def pending(self, axis):
        self.native.propose(axis)
        pending = self.native.batch.snapshot()["micro_evolution"]["pending"]
        self.assertIsNotNone(pending)
        return pending["record_sha256"], digest(pending["pair"])

    def worker(self, token=None, *, state=None, name=None):
        self.serial += 1
        return worker_module.CapacityWorker(
            self.company, "fixture-task", self.capacity, self.active_pair,
            self.root / (name or f"memory-{self.serial}"), state,
            shadow_proposal_sha256=token)

    def output(self):
        self.serial += 1
        output = self.root / f"forecast-{self.serial}"
        output.mkdir()
        return output

    def final_response(self):
        return {"output": [{"type": "message", "content": [{"type": "output_text",
            "text": json.dumps({"predictions": [{"target_id": "T001", "predicted_value": 100}]})}]}]}

    def invoke(self, worker, *, first=None):
        output = self.output()

        def response(client, request, *unused, completion_request=None):
            self.requests.append(deepcopy(request))
            if len(self.requests) == 1 and first is not None:
                result = first()
            else:
                result = self.final_response()
            return (result, False) if completion_request is not None else result

        with patch.object(forecast, "budgeted_response", side_effect=response):
            result = forecast.forecast(None, self.rate, self.config, self.company,
                                       None, output, capacity_worker=worker)
        return result, output

    def assert_shadow_receipts(self, context, tested_pair):
        self.assertEqual({receipt["axis"] for receipt in context["receipts"]}, {"R", "H"})
        for receipt in context["receipts"]:
            self.assertEqual(receipt["selected_pair_sha256"], tested_pair)
            self.assertEqual(receipt["active_pair_sha256"], self.active_pair)
            self.assertIs(receipt["shadow"], True)
            self.assertIs(receipt["model_code_executed"], False)

    def reject_pending(self):
        state = self.native.batch.snapshot()
        pending = state["micro_evolution"]["pending"]
        review = {"reviewer_id": "independent-auditor",
            "proposal_sha256": pending["record_sha256"], "decision": "reject",
            "reason": "Fixture ends unadopted proposal; no scientific refutation",
            "tested_pair_sha256": digest(pending["pair"]),
            "anchor_pair_sha256": digest(state["micro_evolution"]["anchor_pair"]),
            "checks": {}, "benefit_observed": False, "benefit_evidence_sha256": None,
            "actual_write_paths": pending["write_paths"]}
        receipt = self.native.artifact({"review": review, "evidence": {}})
        self.capacity.review(receipt, expected_state_sha256=state["state_sha256"])
        after = self.native.batch.snapshot()
        self.assertIsNone(after["micro_evolution"]["pending"])
        self.assertEqual(digest(after["micro_evolution"]["active_pair"]), self.active_pair)
        self.assertIs(after["micro_evolution"]["history"][-1]["review"]["benefit_observed"], False)

    def test_prepare_pending_R_uses_child_literal_with_active_parent_receipts(self):
        token, tested = self.pending("R")
        before = self.native.batch.snapshot()
        context = self.capacity.prepare(expected_pair_sha256=self.active_pair,
            shadow_proposal_sha256=token, questions="invented question",
            state_message={"role": "user", "content": "invented public record"})
        self.assertEqual(context["messages"][1]["content"], "Verify signs with calculate")
        self.assertEqual(context["messages"][2]["content"], "invented public record")
        self.assertEqual(context["tool_bounds"]["read_chunk_limit"], 20000)
        self.assert_shadow_receipts(context, tested)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_prepare_pending_H_uses_child_bounds_and_both_child_receipts(self):
        token, tested = self.pending("H")
        before = self.native.batch.snapshot()
        context = self.capacity.prepare(expected_pair_sha256=self.active_pair,
            shadow_proposal_sha256=token, questions="invented question")
        self.assertEqual(context["messages"], [{"role": "user", "content": "invented question"}])
        self.assertEqual(context["tool_bounds"]["read_chunk_limit"], 1000)
        self.assertEqual(context["tool_bounds"]["search_hit_limit"], 50)
        self.assert_shadow_receipts(context, tested)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_actual_forecaster_uses_pending_R_without_native_selection_or_claim(self):
        token, tested = self.pending("R")
        before = self.native.batch.snapshot()
        worker = self.worker(token)
        result, output = self.invoke(worker)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(worker.pair, self.active_pair)
        self.assertNotEqual(worker.pair, tested)
        self.assertEqual(self.requests[0]["input"][1]["content"], "Verify signs with calculate")
        effective = json.loads((output / "effective-capacity.json").read_text())
        self.assert_shadow_receipts(effective["context"], tested)
        self.assertTrue((output / "predictions.json").is_file())
        self.assertTrue((output / "research-state-output.json").is_file())
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_actual_forecaster_pending_H_clamps_requested_tool_output(self):
        long_text = "invented public filing " + "x" * 6000
        source = Path(self.company["visible_root"]) / "filings/old.md"
        source.write_text(long_text)
        self.company["allowed_files"][2].update(bytes=len(long_text.encode()),
            sha256=hashlib.sha256(long_text.encode()).hexdigest())
        token, tested = self.pending("H")
        before = self.native.batch.snapshot()
        worker = self.worker(token)

        def read_request():
            return {"output": [{"type": "function_call", "call_id": "shadow-read",
                "name": "read_file", "arguments": json.dumps({"path": "filings/old.md",
                                                            "offset": 0, "characters": 5000})}]}

        result, output = self.invoke(worker, first=read_request)
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(len(self.requests), 2)
        observation = next(item for item in self.requests[1]["input"]
                           if item.get("type") == "function_call_output")
        returned = json.loads(observation["output"])
        self.assertEqual((len(returned["text"]), returned["next_offset"]), (1000, 1000))
        self.assertEqual(worker.pair, self.active_pair)
        self.assert_shadow_receipts(json.loads((output / "effective-capacity.json").read_text())["context"], tested)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_parent_and_shadow_copy_identical_prior_bytes_into_disjoint_roots(self):
        prior = self.data.api.save(self.root / "prior", self.data.facts())
        token, tested = self.pending("R")
        before = self.native.batch.snapshot()
        parent = self.worker(state=prior, name="parent-memory")
        shadow = self.worker(token, state=prior, name="child-memory")
        self.assertEqual(parent.state_binding["sha256"], shadow.state_binding["sha256"])
        self.assertEqual(parent.state_binding["sha256"], prior["sha256"])
        self.assertNotEqual(Path(parent.state_binding["path"]).parent,
                            Path(shadow.state_binding["path"]).parent)
        self.assertEqual(Path(parent.state_binding["path"]).read_bytes(), Path(prior["path"]).read_bytes())
        self.assertEqual(Path(shadow.state_binding["path"]).read_bytes(), Path(prior["path"]).read_bytes())
        self.assertEqual(parent.state_receipt, shadow.state_receipt)
        parent_messages, shadow_messages = parent.start(self.output()), shadow.start(self.output())
        self.assertEqual(parent_messages[-1], shadow_messages[-1])
        self.assert_shadow_receipts(shadow.context, tested)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_ordinary_parent_still_runs_unchanged_while_child_is_pending(self):
        self.pending("R")
        before = self.native.batch.snapshot()
        worker = self.worker()
        expected = self.capacity.prepare(expected_pair_sha256=self.active_pair,
            questions=worker.files["questions.md"],
            state_message=worker.state_api.consume(worker.state_binding)[0])
        self.assertEqual(worker.context, expected)
        result, unused = self.invoke(worker)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertNotIn("Verify signs with calculate", [item.get("content") for item in self.requests[0]["input"]])
        for receipt in worker.context["receipts"]:
            self.assertEqual(receipt["selected_pair_sha256"], self.active_pair)
            self.assertIs(receipt["shadow"], False)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_unknown_token_refused_at_prepare_and_constructor_without_adoption(self):
        self.pending("R")
        before = self.native.batch.snapshot()
        for token in ("", "f" * 64, 7):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    self.capacity.prepare(expected_pair_sha256=self.active_pair,
                        shadow_proposal_sha256=token, questions="invented question")
                with self.assertRaises(ValueError):
                    self.worker(token)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_missing_pending_proposal_refused_even_with_well_formed_token(self):
        before = self.native.batch.snapshot()
        with self.assertRaises(ValueError):
            self.capacity.prepare(expected_pair_sha256=self.active_pair,
                shadow_proposal_sha256="a" * 64, questions="invented question")
        with self.assertRaises(ValueError):
            self.worker("a" * 64)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_rejected_pending_token_stops_worker_before_first_provider_request(self):
        token, unused = self.pending("R")
        worker = self.worker(token)
        self.reject_pending()
        after_rejection = self.native.batch.snapshot()
        with self.assertRaises(ValueError):
            self.invoke(worker)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.native.batch.snapshot(), after_rejection)

    def test_replaced_pending_token_stops_dispatch_and_finish_without_child_adoption(self):
        token, unused = self.pending("R")
        worker = self.worker(token)
        self.reject_pending()
        new_token, unused = self.pending("H")
        self.assertNotEqual(token, new_token)
        before = self.native.batch.snapshot()
        with self.assertRaises(ValueError):
            worker.dispatch("calculate", {"expression": "1+1"})
        with self.assertRaises(ValueError):
            worker.finish(self.output())
        self.assertEqual(worker.calls, 0)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_observed_active_pair_drift_stops_start_dispatch_and_finish(self):
        token, unused = self.pending("R")
        worker = self.worker(token)
        original = self.native.batch.snapshot()
        drift = deepcopy(original)
        drift["micro_evolution"]["active_pair"]["researcher_sha256"] = "e" * 64
        # Observation-only hostile state: no native activation or journal edit.
        with patch.object(self.native.batch, "snapshot", return_value=drift):
            for operation in (lambda: worker.start(self.output()),
                              lambda: worker.dispatch("calculate", {"expression": "1+1"}),
                              lambda: worker.finish(self.output())):
                with self.assertRaises(ValueError):
                    operation()
        self.assertEqual(worker.calls, 0)
        self.assertEqual(self.native.batch.snapshot(), original)

    def test_child_source_drift_refuses_before_first_provider_request_and_never_executes(self):
        token, unused = self.pending("R")
        worker = self.worker(token)
        before = self.native.batch.snapshot()
        marker = self.root / "must-not-execute"
        changed = "PROFILE = __import__('pathlib').Path(" + repr(str(marker)) + ").touch()\n"
        (self.root / "researcher_v2.py").write_text(changed)
        with self.assertRaises(ValueError):
            self.invoke(worker)
        self.assertEqual(self.requests, [])
        self.assertFalse(marker.exists())
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_active_parent_superseded_source_drift_stops_shadow_at_each_boundary(self):
        token, unused = self.pending("R")
        worker = self.worker(token)
        before = self.native.batch.snapshot()
        # Parent retains native ownership even though its R source is not the
        # tested child entrypoint. Verifying only child receipts is insufficient.
        (self.root / "researcher_v1.py").write_text("PROFILE = {'axis':'R','research_instructions':'drift','reuse_facts':True}\n")
        for operation in (lambda: worker.start(self.output()),
                          lambda: worker.dispatch("calculate", {"expression": "1+1"}),
                          lambda: worker.finish(self.output())):
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(worker.calls, 0)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_changed_shadow_receipt_refuses_start_dispatch_and_finish(self):
        token, unused = self.pending("H")
        worker = self.worker(token)
        before = self.native.batch.snapshot()
        original = deepcopy(worker.context)
        for field, value in (("selected_pair_sha256", self.active_pair),
                             ("active_pair_sha256", "d" * 64), ("shadow", False)):
            worker.context = deepcopy(original)
            worker.context["receipts"][0][field] = value
            with self.subTest(field=field):
                for operation in (lambda: worker.start(self.output()),
                                  lambda: worker.dispatch("calculate", {"expression": "1+1"}),
                                  lambda: worker.finish(self.output())):
                    with self.assertRaises(ValueError):
                        operation()
        self.assertEqual(worker.calls, 0)
        self.assertEqual(self.native.batch.snapshot(), before)

    def test_pending_loss_after_first_response_stops_next_send_and_preserves_original(self):
        token, unused = self.pending("R")
        worker = self.worker(token)

        def lose_pending():
            self.reject_pending()
            return {"output": [{"type": "function_call", "call_id": "after-pending-loss",
                "name": "calculate", "arguments": json.dumps({"expression": "1+1"})}]}

        with self.assertRaises(ValueError):
            self.invoke(worker, first=lose_pending)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(worker.calls, 0)
        output = next(self.root.glob("forecast-*"))
        observation_path = output / ("01-tool-" + forecast.digest(b"after-pending-loss")[:12] + ".json")
        observation = json.loads(observation_path.read_text())
        self.assertIn("Tool request rejected", json.loads(observation["output"])["error"])
        self.assertFalse((output / "predictions.json").exists())
        state = self.native.batch.snapshot()["micro_evolution"]
        self.assertEqual(digest(state["active_pair"]), self.active_pair)
        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["review"]["decision"], "reject")
        self.assertEqual(self.requests[0]["input"][1]["content"], "Verify signs with calculate")


if __name__ == "__main__":
    unittest.main()
