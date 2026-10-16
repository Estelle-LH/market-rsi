"""Invented sources only: continuity/provenance, never forecast improvement."""
import copy
import hashlib
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_research_state as s


class ResearchStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.files = {"questions.md": "### T001 | invented quantity",
            "filing_index.tsv": "date_filed\tform_type\taccession\tpath\n2026-01-01\t10-Q\told\tfilings/old.md\n",
            "filings/old.md": "Invented revenue 100 USD and expense -5 USD."}
        self.company = {"cik": "CIK0000000001", "cutoff": "2026-02-01", "target_accession": "hidden",
                        "visible_root": str(self.root / "visible"), "allowed_files": []}
        for name, text in self.files.items():
            path = self.root / "visible" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self.company["allowed_files"].append({"path": name, "bytes": len(text.encode()),
                                                  "sha256": hashlib.sha256(text.encode()).hexdigest()})
        self.api = s.ResearchState(self.company, "fixture-task")
        self.fact = {"kind": "fact", "period_end": "2025-12-31", "unit": "USD", "value": 100,
            "source_path": "filings/old.md", "source_sha256": self.company["allowed_files"][2]["sha256"],
            "offset": 0, "quote": self.files["filings/old.md"], "literal": "100"}

    def facts(self):
        state = self.api.append(self.api.empty(), self.fact)
        second = dict(self.fact, value=-5, literal="-5")
        return self.api.append(state, second)

    def calculation(self):
        state = self.facts()
        record = {"kind": "calculation", "period_end": "2025-12-31", "unit": "USD", "value": 95,
                  "inputs": {"x0": state["records"][0]["sha256"], "x1": state["records"][1]["sha256"]},
                  "expression": "x0 + x1"}
        return state, record

    def test_write_restart_load_consume_including_actual_calculation(self):
        state, calc = self.calculation()
        state = self.api.append(state, calc)
        binding = self.api.save(self.root / "memory", state)
        cold = s.ResearchState(self.company, "fixture-task")
        self.assertEqual(cold.load(binding), state)
        message, receipt = cold.consume(binding)
        decoded = json.loads(message["content"].split("\n", 1)[1])
        self.assertEqual(decoded["records"][-1]["record"]["value"], 95)
        self.assertEqual(receipt["state_sha256"], binding["sha256"])
        self.assertEqual(receipt["record_count"], 3)
        self.assertFalse(receipt["scientific_benefit_verified"])
        self.assertEqual(cold.save(self.root / "memory", state), binding)

    def test_append_preserves_parent_and_old_history(self):
        empty = self.api.empty()
        parent = self.api.save(self.root / "memory", empty)
        state = self.api.append(empty, self.fact)
        child = self.api.save(self.root / "memory", state)
        self.assertEqual(empty["records"], [])
        self.assertNotEqual(parent["sha256"], child["sha256"])
        self.assertEqual(self.api.load(parent), empty)
        self.assertEqual(self.api.load(child), state)

    def test_assumptions_stay_distinct_and_cannot_be_calc_inputs(self):
        state = self.api.append(self.api.empty(), {"kind": "assumption", "hypothesis": "Growth may slow"})
        record = {"kind": "calculation", "period_end": "2025-12-31", "unit": "USD", "value": 1,
                  "inputs": {"x0": state["records"][0]["sha256"]}, "expression": "x0"}
        with self.assertRaisesRegex(ValueError, "numeric record"):
            self.api.append(state, record)

    def test_hidden_gold_questions_and_unknown_sources_refused(self):
        for name in ("labels/qa.json", "questions.md", "../labels/qa.json", "filings/hidden.md", "/tmp/gold"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.api.append(self.api.empty(), dict(self.fact, source_path=name))

    def test_fact_quote_hash_offset_value_sign_and_fields_checked(self):
        for update in ({"quote": "made up 100"}, {"source_sha256": "a" * 64}, {"offset": True},
                       {"offset": -1}, {"literal": "-100"}, {"value": -100}, {"value": True},
                       {"value": float("nan")}, {"target_id": "T001"}, {"predictions": []}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.api.append(self.api.empty(), dict(self.fact, **update))

    def test_future_period_and_changed_source_snapshot_refused(self):
        binding = self.api.save(self.root / "memory", self.facts())
        with self.assertRaises(ValueError):
            self.api.append(self.api.empty(), dict(self.fact, period_end="2026-02-02"))
        (self.root / "visible/filings/old.md").write_text("changed public source")
        with self.assertRaisesRegex(ValueError, "changed since construction"):
            self.api.consume(binding)
        with self.assertRaisesRegex(ValueError, "snapshot differs"):
            s.ResearchState(self.company, "fixture-task")

    def test_cross_company_cutoff_and_task_load_refused(self):
        binding = self.api.save(self.root / "memory", self.facts())
        for c, task in ((dict(self.company, cik="CIK0000000002"), "fixture-task"),
                        (dict(self.company, cutoff="2026-02-02"), "fixture-task"), (self.company, "other-task")):
            with self.assertRaises(ValueError):
                s.ResearchState(c, task).load(binding)

    def test_calculation_inputs_units_period_constants_and_code_refused(self):
        state, calc = self.calculation()
        for update in ({"value": 94}, {"unit": "shares"}, {"period_end": "2024-12-31"},
                       {"inputs": {"x0": "a" * 64}}, {"expression": "x0 + 999"},
                       {"expression": "x0 / x1"}, {"expression": "__import__('os')"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.api.append(state, dict(calc, **update))

    def test_duplicate_changed_record_and_canonical_state_checked(self):
        state = self.api.append(self.api.empty(), self.fact)
        with self.assertRaises(ValueError):
            self.api.append(state, self.fact)
        state["records"][0]["record"]["value"] = 99
        with self.assertRaises(ValueError):
            self.api.validate(state)

    def test_mutated_binding_and_partial_write_preserved(self):
        state = self.facts()
        binding = self.api.save(self.root / "memory", state)
        path = Path(binding["path"])
        path.write_bytes(b'{"partial":')
        with self.assertRaises(ValueError):
            self.api.load(binding)
        with self.assertRaisesRegex(ValueError, "preserve and diagnose"):
            self.api.save(self.root / "memory", state)
        self.assertEqual(path.read_bytes(), b'{"partial":')

    def test_symlink_and_parent_alias_refused(self):
        binding = self.api.save(self.root / "memory", self.facts())
        alias = self.root / "alias.json"
        alias.symlink_to(binding["path"])
        with self.assertRaises(ValueError):
            self.api.load(dict(binding, path=str(alias)))
        with self.assertRaises(ValueError):
            self.api.save(self.root / "memory/../other", self.facts())

    def test_record_byte_bounds_before_write_or_read(self):
        with patch.object(s, "MAX_RECORDS", 1), self.assertRaises(ValueError):
            self.facts()
        with patch.object(s, "MAX_BYTES", 1), self.assertRaises(ValueError):
            self.api.save(self.root / "memory", self.api.empty())
        path = self.root / "huge.json"
        path.write_bytes(b" " * (s.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "byte bound"):
            self.api.load({"path": str(path), "sha256": "a" * 64})

    def test_duplicate_json_object_and_unsupported_schema_refused(self):
        path = self.root / "duplicate.json"
        data = b'{"records":[],"records":[]}\n'
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.api.load({"path": str(path), "sha256": hashlib.sha256(data).hexdigest()})
        with self.assertRaises(ValueError):
            self.api.validate(dict(self.api.empty(), api_key="forbidden"))

    def test_full_source_numeric_tokens_refuse_fragments_sign_loss_and_trimmed_quotes(self):
        examples = [("Revenue 100", "1", 1), ("Expense -5", "5", 5), ("Expense +5", "5", 5),
            ("Revenue 1,000", "000", 0), ("Revenue 100.50", "50", 50), ("Revenue 1e3", "1", 1),
            ("Expense −5", "5", 5), ("Expense (5)", "5", 5), ("Revenue 1_000", "000", 0)]
        for source, literal, value in examples:
            path = self.root / "visible/filings/old.md"
            path.write_text(source)
            token = hashlib.sha256(source.encode()).hexdigest()
            self.company["allowed_files"][2].update(bytes=len(source.encode()), sha256=token)
            api = s.ResearchState(self.company, "fixture-task")
            for offset, quote in ((0, source), (source.index(literal), literal)):
                record = dict(self.fact, value=value, literal=literal, source_sha256=token, offset=offset, quote=quote)
                with self.subTest(source=source, quote=quote), self.assertRaisesRegex(ValueError, "complete signed numeric"):
                    api.append(api.empty(), record)
                # Saved vulnerable-parent notes also fail cold validation/consumption.
                old = api.empty()
                old["records"].append({"record": record, "sha256": s.sha(record)})
                raw = s.encoded(old)
                saved = self.root / "vulnerable-parent.json"
                saved.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, "complete signed numeric"):
                    api.consume({"path": str(saved), "sha256": hashlib.sha256(raw).hexdigest()})

    def test_full_signed_grouped_decimal_and_sentence_tokens_remain_usable(self):
        for source, literal, value in (("Revenue 100.", "100", 100), ("Expense -5, then tax.", "-5", -5),
                                      ("Revenue +1,000.50 USD", "+1,000.50", 1000.5)):
            path = self.root / "visible/filings/old.md"
            path.write_text(source)
            token = hashlib.sha256(source.encode()).hexdigest()
            self.company["allowed_files"][2].update(bytes=len(source.encode()), sha256=token)
            api = s.ResearchState(self.company, "fixture-task")
            record = dict(self.fact, value=value, literal=literal, source_sha256=token, offset=source.index(literal), quote=literal)
            state = api.append(api.empty(), record)
            binding = api.save(self.root / "memory", state)
            message, _ = api.consume(binding)
            self.assertEqual(json.loads(message["content"].split("\n", 1)[1])["records"][0]["record"]["value"], value)

    def test_exponent_tails_and_leading_decimal_fragments_refused_both_quote_forms(self):
        for amount, literal, value in (("1e3", "3", 3), ("1e-3", "-3", -3), ("1E+3", "+3", 3),
                                      ("-.5", "5", 5), (".5", "5", 5), ("−.5", "5", 5)):
            source = "Revenue " + amount + " USD"
            (self.root / "visible/filings/old.md").write_text(source)
            token = hashlib.sha256(source.encode()).hexdigest()
            self.company["allowed_files"][2].update(bytes=len(source.encode()), sha256=token)
            api = s.ResearchState(self.company, "fixture-task")
            for offset, quote in ((0, source), (source.index(literal), literal)):
                record = dict(self.fact, value=value, literal=literal, source_sha256=token, offset=offset, quote=quote)
                with self.subTest(amount=amount, quote=quote), self.assertRaisesRegex(ValueError, "complete signed numeric"):
                    api.append(api.empty(), record)

    def test_all_numeric_substrings_match_only_whole_supported_source_tokens(self):
        supported = ("100", "-5", "+1,234.50", "0.125", "-0.125")
        unsupported = ("1e3", "1e-3", "1.e3", "-.5", ".5", "(5)", "(-5)", "−5", "1_000", "1,,000", "-$5")
        literal_pattern = r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?"
        for amount in supported + unsupported:
            source = "Revenue " + amount + " USD"
            for start in range(len(amount)):
                for end in range(start + 1, len(amount) + 1):
                    literal = amount[start:end]
                    if re.fullmatch(literal_pattern, literal) is None:
                        continue
                    offset = len("Revenue ") + start
                    expected = amount in supported and literal == amount
                    with self.subTest(amount=amount, literal=literal):
                        self.assertEqual(s.complete_literal(source, 0, source, literal), expected)
                        self.assertEqual(s.complete_literal(source, offset, literal, literal), expected)


if __name__ == "__main__":
    unittest.main()
