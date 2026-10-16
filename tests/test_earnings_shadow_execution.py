"""Actual captured shadow forecasts get a distinct, reverified consumption tuple.

CP3's existing raw-HTTP fixture supplies invented five-target filings, scorer
and owned synthetic budget. Forecast, tool/state updates and Task.execution
verification are real. No network, actual ledger or native acceptance occurs.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import earnings_entry as entry
from earnings_capacity_task import EarningsTask
from earnings_capacity_worker import CapacityWorker
from earnings_research_state import ResearchState
from market_rsi import digest
import test_earnings_capacity_forecast as raw_fixture


class ShadowExecutionTests(unittest.TestCase):
    def fixture(self, axis="R"):
        fixture = raw_fixture._ForecastFixture(self)
        fixture.native.propose(axis)
        snapshot = fixture.native.batch.snapshot()
        pending = snapshot["micro_evolution"]["pending"]
        fixture.active = digest(snapshot["micro_evolution"]["active_pair"])
        fixture.tested = digest(pending["pair"])
        fixture.token = pending["record_sha256"]
        fixture.capacity = fixture.native.adapter
        state_api = ResearchState(fixture.company, fixture.task_id)
        fixture.initial = state_api.save(fixture.root / "matched-initial", state_api.empty())
        fixture.task = EarningsTask()
        fixture.task.kernel = fixture.kernel
        fixture.original_wires = []
        return fixture

    def worker(self, fixture, *, shadow=True, name=None):
        return CapacityWorker(fixture.company, fixture.task_id, fixture.capacity,
            fixture.active, fixture.root / (name or ("child-memory" if shadow else "parent-memory")),
            fixture.initial, shadow_proposal_sha256=fixture.token if shadow else None)

    def invoke(self, fixture, worker, *, slot=0, replies=None):
        # Physical originals remain in their distinct immutable slots; retain
        # the invented wires as well when resetting the fixture's exchange index.
        fixture.original_wires.append(deepcopy(fixture.calls))
        fixture.calls, fixture.connections, fixture.raws = [], [], []
        output = fixture.invoke(worker, slot=slot, replies=replies)
        fixture.original_wires.append(deepcopy(fixture.calls))
        return output

    def verify(self, fixture, output, worker, *, slot=0, **changes):
        names = {"active_pair_sha256": fixture.active,
                 "tested_pair_sha256": fixture.tested,
                 "pending_proposal_sha256": fixture.token,
                 "initial_state": fixture.initial}
        names.update(changes)
        return fixture.task.shadow_execution(output, worker, Path(fixture.slots[slot]), **names)

    def originals(self, fixture, slot=0):
        return fixture.originals(slot)

    def tamper(self, path, value):
        path = Path(path)
        # The untampered original is preserved beside the intentionally corrupt
        # fixture, not silently rewritten as if it were the observed response.
        preserved = path.parent / ("before-tamper-" + path.name)
        preserved.write_bytes(path.read_bytes())
        path.write_bytes(raw_fixture._wire(value))

    def reject_pending(self, fixture):
        state = fixture.native.batch.snapshot()
        pending = state["micro_evolution"]["pending"]
        review = {"reviewer_id": "independent-auditor", "proposal_sha256": pending["record_sha256"],
            "decision": "reject", "reason": "Fixture closes unadopted pending proposal",
            "tested_pair_sha256": digest(pending["pair"]),
            "anchor_pair_sha256": digest(state["micro_evolution"]["anchor_pair"]),
            "checks": {}, "benefit_observed": False, "benefit_evidence_sha256": None,
            "actual_write_paths": pending["write_paths"]}
        receipt = fixture.native.artifact({"review": review, "evidence": {}})
        fixture.capacity.review(receipt, expected_state_sha256=state["state_sha256"])

    def test_actual_parent_and_child_forecasts_share_prior_bytes_but_distinct_consumption(self):
        fixture = self.fixture()
        before = fixture.native.batch.snapshot()
        initial_bytes = Path(fixture.initial["path"]).read_bytes()
        parent, child = self.worker(fixture, shadow=False), self.worker(fixture)
        self.assertEqual(parent.pair, fixture.active)
        self.assertEqual(child.pair, fixture.active)
        self.assertEqual(parent.tested_pair, fixture.active)
        self.assertEqual(child.tested_pair, fixture.tested)
        self.assertEqual(Path(parent.state_binding["path"]).read_bytes(), initial_bytes)
        self.assertEqual(Path(child.state_binding["path"]).read_bytes(), initial_bytes)
        self.assertNotEqual(Path(parent.state_binding["path"]).parent, Path(child.state_binding["path"]).parent)
        parent_output = self.invoke(fixture, parent)
        parent_originals = self.originals(fixture)
        parent_verified = self.verify(fixture, parent_output, parent, tested_pair_sha256=fixture.active)
        ordinary = fixture.task.execution(parent_output, parent, Path(fixture.slots[0]))
        self.assertEqual(ordinary["consumed"], {"pair_sha256": fixture.active,
                                              "state_sha256": fixture.initial["sha256"]})
        child_output = self.invoke(fixture, child, slot=1)
        child_verified = self.verify(fixture, child_output, child, slot=1)
        for verified, tested in ((parent_verified, fixture.active), (child_verified, fixture.tested)):
            self.assertEqual(verified["consumed"], {"active_pair_sha256": fixture.active,
                "tested_pair_sha256": tested, "pending_proposal_sha256": fixture.token,
                "state_sha256": fixture.initial["sha256"]})
            self.assertNotIn("pair_sha256", verified["consumed"])
            self.assertIn(verified["state"], verified["artifacts"])
            self.assertEqual(json.loads(entry.checked(verified["score"]))["score_out_of_5"], 5)
        parent_effective = json.loads((Path(fixture.slots[0]) / "effective-capacity.json").read_bytes())
        child_effective = json.loads((Path(fixture.slots[1]) / "effective-capacity.json").read_bytes())
        self.assertNotIn("shadow", parent_effective)
        self.assertEqual(child_effective["shadow"], {"active_pair_sha256": fixture.active,
            "tested_pair_sha256": fixture.tested, "pending_proposal_sha256": fixture.token})
        self.assertEqual(self.originals(fixture), parent_originals)
        self.assertEqual(Path(fixture.initial["path"]).read_bytes(), initial_bytes)
        self.assertEqual(fixture.native.batch.snapshot(), before)
        self.assertEqual(len(fixture.rows()), 4)
        self.assertTrue(all(row[2] == "settled" for row in fixture.rows()))

    def test_actual_pending_H_tool_clamp_and_original_scorer_are_reverified(self):
        fixture = self.fixture("H")
        before = fixture.native.batch.snapshot()
        worker = self.worker(fixture)
        output = self.invoke(fixture, worker)
        verified = self.verify(fixture, output, worker)
        root = Path(fixture.slots[0])
        observations = [json.loads(path.read_bytes()) for path in root.glob("01-tool-*.json")]
        read = next(row for row in observations if row["call_id"] == "read-filing")
        returned = json.loads(read["output"])
        self.assertEqual((len(returned["text"]), returned["next_offset"]), (1000, 1000))
        result = json.loads(entry.checked(verified["result"]))
        self.assertEqual((result["status"], result["turns"], result["tool_calls"], result["points"]),
                         ("COMPLETED_SCORED", 2, 2, 5))
        self.assertEqual(worker.state["records"][0]["record"]["value"], 100)
        self.assertEqual(fixture.native.batch.snapshot(), before)
        self.assertEqual(len(fixture.calls), 4)

    def test_wrong_active_tested_or_pending_digest_refused_without_rewriting_originals(self):
        for field in ("active_pair_sha256", "tested_pair_sha256", "pending_proposal_sha256"):
            with self.subTest(field=field):
                fixture = self.fixture()
                worker = self.worker(fixture)
                output = self.invoke(fixture, worker)
                before, originals = fixture.native.batch.snapshot(), self.originals(fixture)
                rows, calls = fixture.rows(), deepcopy(fixture.calls)
                with self.assertRaises(ValueError):
                    self.verify(fixture, output, worker, **{field: "d" * 64})
                self.assertEqual(self.originals(fixture), originals)
                self.assertEqual(fixture.native.batch.snapshot(), before)
                self.assertEqual(fixture.rows(), rows)
                self.assertEqual(fixture.calls, calls)

    def test_valid_but_different_initial_state_and_mutated_bound_bytes_refused(self):
        for kind in ("different", "bound-byte-drift"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                worker = self.worker(fixture)
                output = self.invoke(fixture, worker)
                if kind == "different":
                    state = worker.state_api.append(worker.state_api.empty(),
                        {"kind": "assumption", "hypothesis": "Invented alternate initial hypothesis"})
                    initial = worker.state_api.save(fixture.root / "other-initial", state)
                else:
                    initial = fixture.initial
                    self.tamper(initial["path"], {"records": []})
                before, originals = fixture.native.batch.snapshot(), self.originals(fixture)
                with self.assertRaises(ValueError):
                    self.verify(fixture, output, worker, initial_state=initial)
                self.assertEqual(self.originals(fixture), originals)
                self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_lost_pending_after_captured_success_invalidates_shadow_consumption(self):
        fixture = self.fixture()
        worker = self.worker(fixture)
        output = self.invoke(fixture, worker)
        originals, rows = self.originals(fixture), fixture.rows()
        self.reject_pending(fixture)
        rejected = fixture.native.batch.snapshot()
        with self.assertRaises(ValueError):
            self.verify(fixture, output, worker)
        self.assertEqual(self.originals(fixture), originals)
        self.assertEqual(fixture.native.batch.snapshot(), rejected)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(len(rejected["micro_evolution"]["history"]), 1)
        self.assertEqual(rejected["micro_evolution"]["history"][0]["review"]["decision"], "reject")

    def test_child_effective_shadow_metadata_is_exact_not_inferred_from_worker_attrs(self):
        variants = ("missing", "extra", "active_pair_sha256", "tested_pair_sha256", "pending_proposal_sha256")
        for kind in variants:
            with self.subTest(kind=kind):
                fixture = self.fixture()
                worker = self.worker(fixture)
                output = self.invoke(fixture, worker)
                path = Path(fixture.slots[0]) / "effective-capacity.json"
                value = json.loads(path.read_bytes())
                if kind == "missing": value.pop("shadow")
                elif kind == "extra": value["shadow"]["benefit_observed"] = True
                else: value["shadow"][kind] = "c" * 64
                self.tamper(path, value)
                before, originals = fixture.native.batch.snapshot(), self.originals(fixture)
                with self.assertRaises(ValueError):
                    self.verify(fixture, output, worker)
                self.assertEqual(self.originals(fixture), originals)
                self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_tampered_result_score_and_physical_request_fail_existing_verifier(self):
        for kind in ("result", "score", "request"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                worker = self.worker(fixture)
                output = self.invoke(fixture, worker)
                if kind in ("result", "score"):
                    value = json.loads(entry.checked(output[kind]))
                    value["points" if kind == "result" else "score_out_of_5"] = 0
                    self.tamper(output[kind]["path"], value)
                    output[kind] = raw_fixture._pin(Path(output[kind]["path"]))
                else:
                    path = Path(fixture.slots[0]) / "01-request.json"
                    value = json.loads(path.read_bytes())
                    value["payload"]["input"] = [{"role": "user", "content": "unbound invented replacement"}]
                    self.tamper(path, value)
                before, originals = fixture.native.batch.snapshot(), self.originals(fixture)
                rows, calls = fixture.rows(), deepcopy(fixture.calls)
                with self.assertRaises(ValueError):
                    self.verify(fixture, output, worker)
                self.assertEqual(self.originals(fixture), originals)
                self.assertEqual(fixture.native.batch.snapshot(), before)
                self.assertEqual(fixture.rows(), rows)
                self.assertEqual(fixture.calls, calls)

    def test_terminal_research_state_binding_drift_is_rejected(self):
        fixture = self.fixture()
        worker = self.worker(fixture)
        output = self.invoke(fixture, worker)
        path = Path(fixture.slots[0]) / "research-state-output.json"
        value = json.loads(path.read_bytes())
        value["state"] = fixture.initial
        self.tamper(path, value)
        before, originals = fixture.native.batch.snapshot(), self.originals(fixture)
        with self.assertRaises(ValueError):
            self.verify(fixture, output, worker)
        self.assertEqual(self.originals(fixture), originals)
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_ordinary_parent_cannot_be_relabelled_as_tested_child_or_shadow_receipt(self):
        for kind in ("pretend-child", "extra-shadow-metadata"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                parent = self.worker(fixture, shadow=False)
                output = self.invoke(fixture, parent)
                if kind == "extra-shadow-metadata":
                    path = Path(fixture.slots[0]) / "effective-capacity.json"
                    value = json.loads(path.read_bytes())
                    value["shadow"] = {"active_pair_sha256": fixture.active,
                        "tested_pair_sha256": fixture.active, "pending_proposal_sha256": fixture.token}
                    self.tamper(path, value)
                before, originals = fixture.native.batch.snapshot(), self.originals(fixture)
                with self.assertRaises(ValueError):
                    self.verify(fixture, output, parent,
                        tested_pair_sha256=fixture.tested if kind == "pretend-child" else fixture.active)
                self.assertEqual(self.originals(fixture), originals)
                self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_actual_failed_forecast_stays_failed_no_score_or_fresh_request(self):
        fixture = self.fixture()
        worker = self.worker(fixture)
        malformed = fixture.final({"predictions": [{"target_id": "T001", "predicted_value": 100}]})
        with self.assertRaises(RuntimeError):
            self.invoke(fixture, worker, replies=[malformed])
        root = Path(fixture.slots[0])
        result = json.loads((root / "result.json").read_bytes())
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        self.assertEqual(result["scored_targets"], 0)
        self.assertFalse((root / "score.json").exists())
        output = {"result": raw_fixture._pin(root / "result.json"),
                  "score": {"path": str(root / "score.json"), "sha256": "a" * 64}}
        before, originals = fixture.native.batch.snapshot(), self.originals(fixture)
        rows, calls = fixture.rows(), deepcopy(fixture.calls)
        with self.assertRaises(RuntimeError):
            self.verify(fixture, output, worker)
        self.assertEqual(self.originals(fixture), originals)
        self.assertEqual(fixture.native.batch.snapshot(), before)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(fixture.calls, calls)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
