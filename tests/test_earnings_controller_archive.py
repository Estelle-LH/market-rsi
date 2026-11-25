"""Archived compilation on fictional files/ledger; no providers or real keys."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_controller_archive as archive
from edgar_forecast_budget import PilotBudget
from edgar_forecast_full_budget import activate, FullBudget


class ControllerArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.old = self.root / "controllers" / "original-first"
        self.old.mkdir(parents=True)
        self.new_root = self.root / "loops" / "recovery-first"
        self.new_root.mkdir(parents=True)
        self.output = self.root / "controllers" / "recovery-first"
        self.ledger = self.root / "fiction.sqlite3"
        budget = PilotBudget(self.ledger)
        budget.close()
        activate(self.ledger, "a" * 64, "b" * 40)
        budget = FullBudget(self.ledger)
        budget.reserve("original-request", "gpt-6.1-sol", 164090000)
        budget.settle("original-request", 225000)
        budget.close()
        limits = {"max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600}
        clock = self.write(self.root / "loops" / "earnings-feedback-01" / "sealed-clock.json", {"fiction": "original clock"})
        self.config = {"ledger": str(self.ledger), "task_id": "fixture", "model": "gpt-6.1-sol",
            "runtime_config": {"models": {"gpt-6.1-sol": {"api_model": "gpt-6.1-sol", "effort": "xhigh",
                "input": "2", "cached": ".1", "write": "2.5", "output": "10"}}},
            "inherited_clock": {"binding": clock, "source_commit": "a" * 40}}
        self.envelope = {"source_commit": "b" * 40, "loop_policy_sha256": "d" * 64,
            "root": str(self.new_root), "controllers": [str(self.output)], "baseline_config": self.config}
        self.packet = {"task_id": "fixture", "parent_feedback_sha256": "c" * 64, "questions": "invented questions",
            "feedback": {"observation": {"cik": "fixture", "prediction": {"planned_targets": 5,
                "scored_targets": 0, "score_out_of_5": None}, "execution": {"status": "FAILED_NO_RETRY", "error_type": "ValueError"}},
                "baseline_score_out_of_5": 1.5}, "prior_recipe": None}
        old_packet = self.write(self.root / "loops" / "earnings-feedback-01" / "packet-01.json", self.packet)
        self.packet_binding = self.write(self.new_root / "packet-01.json", self.packet)
        self.recipe = {"schema": "earnings_research_recipe_v1", "task_id": "fixture", "parent_feedback_sha256": "c" * 64,
            "research_instructions": "x" * 2027}
        response = {"status": "completed", "model": "gpt-6.1-sol", "service_tier": "default",
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30, "input_tokens_details": {"cached_tokens": 0}},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(self.recipe)}]}]}
        payload = {"model": "gpt-6.1-sol", "reasoning": {"effort": "xhigh"}, "tools": [], "tool_choice": "none",
            "parallel_tool_calls": False, "instructions": "Original fictional no-tool Controller instructions.",
            "input": [{"role": "user", "content": json.dumps(archive.controller.safe_input(self.packet), sort_keys=True)}]}
        selector = {"response": self.write(self.old / "01-response.json", response),
            "count": self.write(self.old / "01-count.json", {"input_tokens": 100}),
            "request": self.write(self.old / "01-request.json", {"request_id": "original-request", "reserved_nano_usd": 164090000, "payload": payload}),
            "failure_result": self.write(self.old / "result.json", {"status": "FAILED_NO_RETRY", "error_type": "ValueError"}),
            "identity": self.write(self.old / "identity.json", {"source_commit": "a" * 40, "input_packet": old_packet,
                "round_index": 1, "limits": limits, "clock": clock}), "input_packet": old_packet, "original_source_commit": "a" * 40}
        self.config["archived_first_controller"] = selector
        patches = [patch.object(archive, "validate_envelope", return_value=({"fiction": True}, [], None)),
            patch.object(archive.entry, "ARCHIVE", self.root),
            patch.object(archive.entry, "FilingTools", return_value=SimpleNamespace(files={"questions.md": "invented questions"})),
            patch.object(archive.controller, "credential"), patch.object(archive.controller, "RawOpenAIHTTP")]
        self.validate, _, _, self.keys, self.provider = [p.start() for p in patches]
        for p in patches: self.addCleanup(p.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True))
        return {"path": str(path), "sha256": archive.entry.digest(path.read_bytes())}

    def mutate(self, key, update):
        binding = self.config["archived_first_controller"][key]
        value = json.loads(Path(binding["path"]).read_text())
        update(value)
        binding.update(self.write(Path(binding["path"]), value))

    def rows(self):
        db = sqlite3.connect(self.ledger.as_uri() + "?mode=ro", uri=True)
        try: return db.execute("SELECT * FROM requests ORDER BY id").fetchall()
        finally: db.close()

    def invoke(self):
        return archive.archive_proposal(self.envelope, self.packet_binding, 1)

    def test_exact_recipe_new_compilation_preserves_all_originals_and_rows(self):
        before = {p: p.read_bytes() for p in self.old.glob("*.json")}
        rows = self.rows()
        proposal = archive.entry.strict_json(archive.entry.checked(self.invoke()).decode())
        self.assertEqual(proposal, {"recipe": self.recipe, "input_packet": self.packet_binding, "source_commit": "b" * 40})
        origin = json.loads((self.output / "archive-origin.json").read_text())
        self.assertEqual((origin["original_generation_source_commit"], origin["current_compiler_source_commit"]), ("a" * 40, "b" * 40))
        self.assertEqual((origin["new_provider_calls"], origin["new_generations"], origin["original_status"]), (0, 0, "FAILED_NO_RETRY"))
        self.assertEqual(origin["original_accounting"]["accounted_charge_nano_usd"], 225000)
        self.assertEqual(before, {p: p.read_bytes() for p in self.old.glob("*.json")})
        self.assertEqual(rows, self.rows())
        self.keys.assert_not_called()
        self.provider.assert_not_called()
        with self.assertRaises(FileExistsError): self.invoke()

    def test_current_envelope_failure_precedes_any_archive_read(self):
        self.validate.side_effect = ValueError("not reviewed")
        with patch.object(archive.entry, "checked") as checked:
            with self.assertRaises(ValueError): self.invoke()
            checked.assert_not_called()

    def test_identity_limits_context_request_and_usage_tamper_refuses(self):
        cases = [("identity", lambda v: v.update(source_commit="z" * 40)),
                 ("identity", lambda v: v.update(input_packet={})),
                 ("identity", lambda v: v.update(limits={})),
                 ("request", lambda v: v["payload"]["reasoning"].update(effort="other")),
                 ("request", lambda v: v.update(reserved_nano_usd=1)),
                 ("response", lambda v: v.update(model="other")),
                 ("response", lambda v: v["usage"].update(total_tokens=999))]
        for key, update in cases:
            binding = self.config["archived_first_controller"][key]
            original = Path(binding["path"]).read_bytes()
            self.mutate(key, update)
            with self.subTest(key=key), self.assertRaises(ValueError): self.invoke()
            Path(binding["path"]).write_bytes(original)
            binding["sha256"] = archive.entry.digest(original)
        changed = dict(self.packet, parent_feedback_sha256="e" * 64)
        self.packet_binding.update(self.write(Path(self.packet_binding["path"]), changed))
        with self.assertRaises(ValueError): self.invoke()
        self.assertFalse(self.output.exists())

    def test_uncertain_or_wrong_accounted_row_never_changes_ledger(self):
        for status, charged in (("uncertain", 225000), ("settled", 0)):
            with sqlite3.connect(self.ledger) as db:
                db.execute("UPDATE requests SET status=?,charged=?", (status, charged))
            before = self.rows()
            with self.subTest(status=status), self.assertRaises(ValueError): self.invoke()
            self.assertEqual(before, self.rows())
        self.assertFalse(self.output.exists())

    def test_refusal_oversize_or_other_failure_cannot_be_recovered(self):
        # A valid response is restored between cases; no previous invalidity
        # may mask the failure-result rejection being checked last.
        self.mutate("response", lambda v: v["output"].append({"type": "refusal"}))
        with self.assertRaises(ValueError): self.invoke()
        self.mutate("response", lambda v: v["output"].pop())
        for size in (1999, 2201):
            value = dict(self.recipe, research_instructions="x" * size)
            self.mutate("response", lambda v: v["output"][0]["content"][0].update(text=json.dumps(value)))
            with self.subTest(size=size), self.assertRaises(ValueError): self.invoke()
        self.mutate("failure_result", lambda v: v.update(error_type="BudgetStop"))
        self.mutate("response", lambda v: v["output"][0]["content"][0].update(text=json.dumps(self.recipe)))
        with self.assertRaises(ValueError): self.invoke()

    def test_settled_upper_bound_preserves_ceiling_and_distinct_actual_charge(self):
        with sqlite3.connect(self.ledger) as db:
            db.execute("UPDATE requests SET status='settled_upper_bound',charged=reserved")
        before = self.rows()
        self.invoke()
        charged = json.loads((self.output / "archive-origin.json").read_text())["original_accounting"]
        self.assertEqual((charged["computed_charge_nano_usd"], charged["accounted_charge_nano_usd"]), (225000, 164090000))
        self.assertEqual(before, self.rows())

    def test_first_slot_only_wrong_path_or_existing_new_directory_refuses(self):
        with self.assertRaises(ValueError): archive.archive_proposal(self.envelope, self.packet_binding, 2)
        self.envelope["controllers"][0] = str(self.old)
        with self.assertRaises(ValueError): self.invoke()
        self.envelope["controllers"][0] = str(self.output)
        self.config["archived_first_controller"]["count"]["path"] = str(self.old / "elsewhere.json")
        with self.assertRaises(ValueError): self.invoke()
        self.keys.assert_not_called()
        self.provider.assert_not_called()


if __name__ == "__main__": unittest.main()
