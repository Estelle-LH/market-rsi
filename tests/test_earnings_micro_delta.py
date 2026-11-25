"""Synthetic small-step R/H policy checks; no real provider or paid ledger.

SourceReview fixtures compose the existing owned Native fixture without
collecting its test methods. Materialization is not adoption or benefit.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_capacity_adapter as adapter
import earnings_source_review as source_review
import test_earnings_source_review as review_fixture


class MicroDeltaTests(unittest.TestCase):
    @staticmethod
    def r(text="", reuse=True):
        return {"axis": "R", "research_instructions": text, "reuse_facts": reuse}

    @staticmethod
    def h(read=20000, search=50):
        return {"axis": "H", "read_chunk_limit": read, "search_hit_limit": search}

    def accepted(self, before, after, axis):
        original = deepcopy((before, after))
        adapter.micro_delta(before, after, axis)
        self.assertEqual((before, after), original)

    def refused(self, before, after, axis):
        original = deepcopy((before, after))
        with self.assertRaises(ValueError):
            adapter.micro_delta(before, after, axis)
        self.assertEqual((before, after), original)

    def test_R_empty_parent_and_exact_character_ceiling(self):
        self.accepted(self.r(), self.r("Check signs and units before producing a forecast."), "R")
        self.accepted(self.r(), self.r("a" * 200), "R")
        self.refused(self.r(), self.r("a" * 201), "R")

    def test_R_exact_UTF8_ceiling_separate_from_character_ceiling(self):
        self.accepted(self.r(), self.r("\U0001f9ea" * 128), "R")  # 128 chars, 512 bytes.
        self.refused(self.r(), self.r("\U0001f9ea" * 129), "R")
        self.accepted(self.r(), self.r("\u6570" * 170 + "ab"), "R")  # 172 chars, 512 bytes.
        self.refused(self.r(), self.r("\u6570" * 171), "R")

    def test_R_parent_prefix_and_rule_separator_are_preserved(self):
        parent = "Check signs."
        self.accepted(self.r(parent), self.r(parent + "\nCheck units."), "R")
        self.accepted(self.r(parent + "\n"), self.r(parent + "\nCheck units."), "R")
        self.refused(self.r(parent), self.r(parent + "Check units."), "R")
        self.refused(self.r(parent), self.r("Verify signs.\nCheck units."), "R")
        self.refused(self.r(parent), self.r("Check units.\n" + parent), "R")

    def test_R_literal_suffix_includes_separator_in_limits(self):
        parent = "Preserved rule."
        self.accepted(self.r(parent), self.r(parent + "\n" + "a" * 199), "R")
        self.refused(self.r(parent), self.r(parent + "\n" + "a" * 200), "R")
        self.accepted(self.r(parent), self.r(parent + "\n" + "\u6570" * 170 + "a"), "R")
        self.refused(self.r(parent), self.r(parent + "\n" + "\u6570" * 170 + "ab"), "R")

    def test_R_blank_multiline_and_removed_rules_are_refused(self):
        for text in ("", " ", "\t\n", "First rule.\nSecond rule.",
                     "First rule.\rSecond rule.", "First rule.\u2028Second rule."):
            with self.subTest(text=repr(text)):
                self.refused(self.r(), self.r(text), "R")
        self.refused(self.r("Existing rule."), self.r(""), "R")

    def test_R_reuse_facts_cannot_change_alone_or_with_rule(self):
        self.refused(self.r(), self.r(reuse=False), "R")
        self.refused(self.r(), self.r("Check units.", reuse=False), "R")
        self.accepted(self.r(reuse=False), self.r("Check units.", reuse=False), "R")

    def test_R_original_total_character_and_byte_bounds_still_apply(self):
        self.accepted(self.r("a" * 2000), self.r("a" * 2000 + "\n" + "b" * 199), "R")
        self.refused(self.r("a" * 2100), self.r("a" * 2100 + "\n" + "b" * 100), "R")
        self.refused(self.r("\u6570" * 1360), self.r("\u6570" * 1360 + "\n" + "\u6570" * 6), "R")

    def test_H_exact_ten_percent_decrease_and_increase(self):
        self.accepted(self.h(), self.h(18000), "H")
        self.refused(self.h(), self.h(17999), "H")
        self.accepted(self.h(1000), self.h(1100), "H")
        self.refused(self.h(1000), self.h(1101), "H")

    def test_H_integer_arithmetic_does_not_round_fractional_allowance_up(self):
        self.accepted(self.h(999), self.h(900), "H")
        self.refused(self.h(999), self.h(899), "H")
        self.accepted(self.h(999), self.h(1098), "H")
        self.refused(self.h(999), self.h(1099), "H")

    def test_H_original_absolute_bounds_still_apply(self):
        self.accepted(self.h(280), self.h(256), "H")
        self.refused(self.h(280), self.h(255), "H")
        self.accepted(self.h(19999), self.h(20000), "H")
        self.refused(self.h(), self.h(20001), "H")
        self.refused(self.h(255), self.h(256), "H")
        self.refused(self.h(20001), self.h(20000), "H")

    def test_H_search_limit_cannot_change_alone_or_with_read_limit(self):
        self.refused(self.h(), self.h(search=49), "H")
        self.refused(self.h(), self.h(18000, search=49), "H")
        self.accepted(self.h(search=1), self.h(18000, search=1), "H")

    def test_H_exact_integer_types_are_required_not_bool_float_or_string(self):
        for value in (True, False, 18000.0, "18000", None):
            with self.subTest(field="read", value=value):
                self.refused(self.h(), self.h(value), "H")
                self.refused(self.h(value), self.h(18000), "H")
        for value in (True, 50.0, "50", None, 0, 51):
            with self.subTest(field="search", value=value):
                self.refused(self.h(search=value), self.h(18000, search=value), "H")

    def test_exact_profiles_axis_and_types_required_before_comparison(self):
        malformed = [None, [], b"PROFILE={}", {"axis": "R"},
                     {"axis": "R", "research_instructions": "", "reuse_facts": 1},
                     {"axis": "R", "research_instructions": 0, "reuse_facts": True},
                     dict(self.r(), permission="network"), self.h()]
        for index, value in enumerate(malformed):
            with self.subTest(index=index, side="before"):
                self.refused(value, self.r("Check units."), "R")
            with self.subTest(index=index, side="after"):
                self.refused(self.r(), value, "R")
        for axis in (None, True, 1, "continue", "K", "r", [], {}):
            with self.subTest(axis=repr(axis)):
                self.refused(self.r(), self.r("Check units."), axis)

    def test_no_change_is_not_an_evolution_on_either_axis(self):
        self.refused(self.r("Same rule."), self.r("Same rule."), "R")
        self.refused(self.h(), self.h(), "H")


class MicroSourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = review_fixture.SourceReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def service(self, **extra):
        fixture = self.fixture
        return source_review.SourceReview(fixture.root, slots=fixture.slots,
            proposer_id="fixture-author", reviewer_id="independent-auditor", **extra)

    @staticmethod
    def source(value):
        return "PROFILE = " + repr(value) + "\n"

    def test_micro_policy_blocks_legacy_valid_broad_H_before_any_write(self):
        fixture = self.fixture
        inputs = fixture._inputs("H")  # Legacy-valid 20000 -> 1000.
        service = self.service(micro_policy="earnings_micro_v1")
        fixture._refused(inputs, service=service)
        self.assertFalse(fixture.slot.exists())
        self.assertFalse((fixture.root / "harness_v2.py").exists())

    def test_micro_policy_blocks_legacy_valid_broad_R_before_any_write(self):
        fixture = self.fixture
        inputs = fixture._inputs("R", source=self.source(
            {"axis": "R", "research_instructions": "a" * 201, "reuse_facts": True}))
        fixture._refused(inputs, service=self.service(micro_policy="earnings_micro_v1"))
        self.assertFalse(fixture.slot.exists())
        self.assertFalse((fixture.root / "researcher_v2.py").exists())

    def test_passing_micro_R_and_H_materialize_exact_bytes_not_adoption(self):
        for axis, profile in (
            ("R", {"axis": "R", "research_instructions": "Verify units.", "reuse_facts": True}),
            ("H", {"axis": "H", "read_chunk_limit": 18000, "search_hit_limit": 50}),
        ):
            if axis == "H":
                self.fixture._new_fixture()
            fixture = self.fixture
            inputs = fixture._inputs(axis, source=self.source(profile))
            before = deepcopy(fixture.native.batch.snapshot())
            original = adapter.author_payload(inputs[1])["source_text"].encode()
            spec = self.service(micro_policy="earnings_micro_v1").review(
                *inputs, str(fixture.slot))
            self.assertEqual((fixture.root / spec["entrypoints"][axis]).read_bytes(), original)
            self.assertEqual(fixture.native.batch.snapshot(), before)
            self.assertIsNone(spec["review_receipt"])
            self.assertFalse(Path(inputs[2]["candidate"]["path"]).is_relative_to(fixture.slot))

    def test_micro_check_precedes_materialization_even_when_check_raises(self):
        fixture = self.fixture
        inputs = fixture._inputs("R")
        service = self.service(micro_policy="earnings_micro_v1")
        with patch.object(source_review, "micro_delta", side_effect=ValueError("fixture micro refusal")) as check:
            fixture._refused(inputs, service=service)
        check.assert_called_once()
        self.assertFalse(fixture.slot.exists())
        self.assertFalse((fixture.root / "researcher_v2.py").exists())

    def test_default_legacy_review_does_not_apply_relative_micro_policy(self):
        fixture = self.fixture
        inputs = fixture._inputs("H")
        before = deepcopy(fixture.native.batch.snapshot())
        with patch.object(source_review, "micro_delta", side_effect=AssertionError("Legacy policy changed")):
            spec = self.service().review(*inputs, str(fixture.slot))
        selected = adapter.profile((fixture.root / spec["entrypoints"]["H"]).read_bytes(), "H")
        self.assertEqual(selected["read_chunk_limit"], 1000)
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_unknown_explicit_policy_is_refused_without_writes(self):
        fixture = self.fixture
        before = fixture._tree()
        for value in ("", "earnings_micro_v2", True, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.service(micro_policy=value)
        self.assertEqual(fixture._tree(), before)


if __name__ == "__main__":
    unittest.main()
