import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from coder_worker import dispatch_code_once
from market_rsi import fresh_json, digest
from paid_budget import PaidBudget
from research_context import freeze_common
from researcher_worker import dispatch_once, prepare_request
from worker_receipts import (code_request_from_job, read_code_job, read_research_job, read_regular)
from test_researcher_worker import FakeTransport, task, proposal
from test_coder_worker import FakeCoder, RUNTIME, LIMITS, events


INSPECT_CODE = "def inspect(train, dev, feature_names):\n    return {'rows':len(train)+len(dev)}\n"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.common = self.root / "common.json"
        freeze_common(self.common)
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "fixture-research", "cap_usd": "2", "target_usd": "1",
            "buckets_usd": {"learning": "1", "final": "1"}, "authority": "offline fixture only"})
        self.prepared = prepare_request(self.common, arm="learn", task=task(), step_index=0, records=[])
        self.rdir, self.cdir = self.root / "research-01", self.root / "coding-01"
        self.rt = FakeTransport()
        dispatch_once(self.prepared, self.rt, self.budget, self.rdir)
        self.identity = {"authentication": "fixture", "model": "fixture"}

    def tearDown(self):
        self.tmp.cleanup()

    def read_research(self, **kwargs):
        return read_research_job(self.rdir, self.prepared, self.budget, expected_live=False, **kwargs)

    def coding(self, body=None):
        r, c = code_request_from_job(self.rdir, self.prepared, self.budget,
                                    RUNTIME, LIMITS, expected_live=False)
        body = body or {"status": "implemented", "code": INSPECT_CODE, "notes": "fixture only"}
        self.ct = FakeCoder(body)
        dispatch_code_once(c, self.ct, self.cdir)
        return r, c

    def read_code(self, r, c, **kwargs):
        return read_code_job(self.cdir, r, c, expected_live=False,
                             expected_identity=kwargs.get("identity", self.identity))

    def change(self, path, callback):
        value = json.loads(path.read_text())
        callback(value)
        path.write_text(json.dumps(value))


class ResearchTests(Fixture):
    def test_terminal_request_bound_to_real_component_fixture_ledger(self):
        r = self.read_research()
        self.assertEqual(r["proposal"], proposal())
        self.assertEqual(r["raw_response"], self.rt.text)
        self.assertFalse(r["scientific_admission"])
        self.assertEqual(self.rt.sample_count, 1)
        self.assertEqual(self.budget.snapshot()["reserved_usd"], "0")
        self.assertEqual(len(r["receipts"].commitment()["files"]), 5)

    def test_foreign_arm_packet_rejected(self):
        other = prepare_request(self.common, arm="archive", task=task(), step_index=0, records=[])
        with self.assertRaises(ValueError):
            read_research_job(self.rdir, other, self.budget, expected_live=False)

    def test_live_or_mock_identity_cannot_be_relabeled(self):
        with self.assertRaises(ValueError):
            read_research_job(self.rdir, self.prepared, self.budget, expected_live=True)

    def test_request_mutation_is_detected_by_budget_commitment(self):
        self.change(self.rdir / "request.json", lambda x: x.update(rendered_prompt="replaced"))
        with self.assertRaisesRegex(ValueError, "terminal budget"):
            self.read_research()

    def test_claim_source_drift_rejected(self):
        self.change(self.rdir / "claim.json", lambda x: x.update(code_sha256="0" * 64))
        with self.assertRaises(ValueError):
            self.read_research()

    def test_metering_mutation_is_detected_by_append_only_journal(self):
        self.change(self.budget.root / "research-01.metering.json", lambda x: x.update(input_tokens=999))
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.read_research()

    def test_failed_or_incomplete_job_cannot_handoff(self):
        fresh_json(self.rdir / "failure.json", {"error_type": "TimeoutError"})
        with self.assertRaisesRegex(ValueError, "failed job"):
            self.read_research()

    def test_response_or_assessment_not_blindly_trusted(self):
        self.change(self.rdir / "response.json", lambda x: x.update(text="invalid output"))
        with self.assertRaisesRegex(ValueError, "first research response"):
            self.read_research()

    def test_completed_receipts_revalidated_before_coder_handoff(self):
        r, c = self.coding()
        self.change(self.rdir / "response.json", lambda x: x.update(text="changed"))
        with self.assertRaisesRegex(ValueError, "mutated"):
            self.read_code(r, c)

    def test_late_failure_is_not_ignored(self):
        r, c = self.coding()
        fresh_json(self.rdir / "failure.json", {"error_type": "late_failure"})
        with self.assertRaisesRegex(ValueError, "failed after"):
            self.read_code(r, c)

    def test_missing_terminal_receipt_rejects_even_with_response(self):
        (self.rdir / "assessment.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.read_research()


class CodingTests(Fixture):
    def test_complete_handoff_preserves_code_as_text_without_execution(self):
        marker = self.root / "never-execute-on-mac"
        source = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n" + INSPECT_CODE
        r, c = self.coding({"status": "implemented", "code": source, "notes": "fixture"})
        code = self.read_code(r, c)
        self.assertEqual(code["source"], source)
        self.assertFalse(marker.exists())
        self.assertFalse(code["executed"])
        self.assertFalse(code["scientific_admission"])
        self.assertEqual(self.ct.count, 1)
        self.assertIsNone(code["subscription_usage"]["allocated_cost_usd"])
        code["receipts"].revalidate()

    def test_changed_research_response_in_coding_prompt_rejected(self):
        r, c = self.coding()
        altered = copy.deepcopy(c)
        body = json.loads(altered["prompt"])
        body["proposal"]["coding_brief"] = "Host-selected different experiment"
        altered["prompt"] = json.dumps(body)
        altered["packet_sha256"] = digest({k: v for k, v in altered.items() if k != "packet_sha256"})
        with self.assertRaises(ValueError):
            self.read_code(r, altered)

    def test_swapped_code_body_rejected_even_if_saved_valid_true(self):
        r, c = self.coding()
        self.change(self.cdir / "response.json", lambda x: x["body"].update(code=INSPECT_CODE + "# swapped"))
        with self.assertRaises(ValueError):
            self.read_code(r, c)

    def test_tool_event_rejected_independently_of_saved_assessment(self):
        r, c = self.coding()
        def mutate(x):
            x["events"] += json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}) + "\n"
        self.change(self.cdir / "response.json", mutate)
        with self.assertRaises(ValueError):
            self.read_code(r, c)

    def test_wrong_frozen_runtime_identity_rejected(self):
        r, c = self.coding()
        with self.assertRaises(ValueError):
            self.read_code(r, c, identity={"authentication": "fixture", "model": "different-model"})

    def test_wrong_recorded_usage_rejected(self):
        r, c = self.coding()
        self.change(self.cdir / "subscription-usage.json", lambda x: x["usage"].update(output_tokens=0))
        with self.assertRaisesRegex(ValueError, "subscription evidence"):
            self.read_code(r, c)

    def test_unsupported_not_changed_into_experiment(self):
        r, c = self.coding({"status": "unsupported", "code": "", "notes": "cannot implement"})
        with self.assertRaises(ValueError):
            self.read_code(r, c)
        self.assertEqual(self.ct.count, 1)

    def test_wall_limit_rejected_at_handoff(self):
        r, c = self.coding()
        self.change(self.cdir / "assessment.json", lambda x: x.update(elapsed_seconds=LIMITS["wall_seconds"]))
        with self.assertRaises(ValueError):
            self.read_code(r, c)

    def test_replaced_receipt_after_read_rejected(self):
        r, c = self.coding()
        code = self.read_code(r, c)
        self.change(self.cdir / "response.json", lambda x: x.update(exit_code=1))
        with self.assertRaises(ValueError):
            code["receipts"].revalidate()


class FileTests(Fixture):
    def test_symlink_input_and_parent_rejected(self):
        link = self.root / "link"
        link.symlink_to(self.rdir)
        with self.assertRaises(ValueError):
            read_regular(link / "response.json")
        link2 = self.root / "response-link.json"
        link2.symlink_to(self.rdir / "response.json")
        with self.assertRaises(ValueError):
            read_regular(link2)

    def test_fifo_rejected_without_blocking(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            read_regular(fifo)

    def test_file_bound_is_enforced(self):
        with self.assertRaises(ValueError):
            read_regular(self.rdir / "request.json", 8)


if __name__ == "__main__":
    unittest.main()
