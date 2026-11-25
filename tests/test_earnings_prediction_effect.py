"""Independent original-score effect tests; no actual autonomy or gain claim.

The integrated fixture runs the existing forecast, scorer, matched coordinator,
host review and Native receipt consumer against invented raw HTTP responses and
an owned temporary ledger. Its eight mechanical fact sets are explicitly
synthetic consumer-protocol inputs, not eight independently executed probes.
No real credentials, real QA, network or production ledger are used.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_earnings_shadow_trial as matched_fixture
import earnings_capacity_adapter as adapter
import earnings_effect_review as effect
import earnings_entry as entry
import earnings_research_diagnostics as diagnostics
import earnings_shadow_measurement as measurement
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


COMPONENTS = ("research_policy", "memory_policy", "tool_interface")
THRESHOLDS = ("0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5")
SYNTHETIC = "SYNTHETIC_PREDICTION_CONSUMER_NOT_AUTONOMY_OR_EIGHT_ACTUAL_PROBES"


def criterion(component="tool_interface", minimum=1):
    return {"schema": "earnings_shadow_criterion_v2", "component": component,
            "metric": "score_out_of_5", "direction": "higher", "min_delta": minimum}


def declaration(component="tool_interface", minimum="1"):
    return (f"earnings-shadow-v2|{component}|score_out_of_5|higher|{minimum}"
            "|score_nonregression|matched_trial_only")


class _PredictionReviewFixture:
    """Predeclare the effect before proposal, forecast or score exists."""

    def __init__(self, owner, *, parent_points=4, child_points=5, minimum="1", axis="H"):
        helper = matched_fixture.MatchedShadowTrialTests(
            "test_actual_H_trial_measures_originals_with_parent_owned_native_claims")
        owner.addCleanup(helper.doCleanups)
        self.owner, self.helper, self.serial, self.probe_calls = owner, helper, 0, 0
        component = "tool_interface" if axis == "H" else "research_policy"
        self.effect = declaration(component, minimum)
        original = adapter.EarningsCapacity.propose

        def prospective(capacity, after, proposal, entries, **options):
            return original(capacity, after, dict(proposal, behavior_change=self.effect), entries, **options)

        with patch.object(adapter.EarningsCapacity, "propose", new=prospective):
            self.raw = helper.fixture(axis)
        self.raw.criterion = self.save("predeclared-criterion", criterion(component, float(minimum)))

        def final(points):
            return self.raw.final({"predictions": [
                {"target_id": f"T{i:03d}", "predicted_value": 100 if i <= points else 200}
                for i in range(1, 6)]})

        # Extra child research is a real counted tool turn, not a changed metric
        # literal. Higher scores come only from the synthetic provider's answer.
        extra = self.raw.response([{"type": "function_call", "call_id": "additional-child-read",
            "name": "read_file", "arguments": json.dumps(
                {"path": "filings/old.md", "offset": 1000, "characters": 1000})}])
        self.comparison = helper.invoke(self.raw, replies=[
            self.raw.research(), final(parent_points),
            self.raw.research(), extra, final(child_points)])
        self.before = self.raw.native.batch.snapshot()
        self.synthetic = self.save("synthetic-protocol-only", {
            "label": SYNTHETIC, "actual_probes_executed": False,
            "model_authorship": False, "learning": False, "predictive_gain": False})

    def save(self, name, value):
        self.serial += 1
        return engine.save(self.raw.root / f"prediction-{self.serial:03d}-{name}.json", value)

    def binding(self):
        micro = self.before["micro_evolution"]
        pending = micro["pending"]
        return {"proposal_sha256": pending["record_sha256"],
            "before_identity_sha256": digest(self.raw.capacity._selected(self.before)["manifest"]),
            "after_identity_sha256": digest(self.raw.capacity._version(pending["pair"])["manifest"]),
            "tested_pair_sha256": digest(pending["pair"]),
            "anchor_pair_sha256": digest(micro["anchor_pair"])}

    def probe(self, capacity, comparison_binding, output_root):
        self.probe_calls += 1
        self.owner.assertEqual(comparison_binding, self.comparison)
        Path(output_root).mkdir(parents=True, exist_ok=False)
        return engine.save(Path(output_root) / "synthetic-protocol-observations.json", {
            "schema": "earnings_mechanical_checks_v1", "binding": self.binding(),
            "scopes": deepcopy(effect.SCOPES), "observations": {
                name: {"facts": dict.fromkeys(facts, True), "artifacts": [self.synthetic]}
                for name, facts in effect.FACTS.items()},
            "sources": {"producer": engine.source_of(self.probe), "synthetic_fixture": self.synthetic},
            "native_state_sha256": self.before["state_sha256"]})

    def consume(self, comparison=None):
        pending = self.before["micro_evolution"]["pending"]
        registration = self.save("registration", {
            "schema": "earnings_effect_review_registration_v1",
            "reviewer_id": self.before["micro_evolution"]["reviewer_id"],
            "proposer_id": pending["proposer_id"], "review_source": engine.source_of(effect.review),
            "probe_source": engine.source_of(self.probe), "scopes": deepcopy(effect.SCOPES)})
        self.serial += 1
        self.output_root = self.raw.role_root / "effects" / f"prediction-{self.serial:03d}"
        rows, calls = self.raw.rows(), deepcopy(self.raw.calls)
        originals, factories = self.helper.all_originals(self.raw), self.raw.factory.call_count
        try:
            with patch.object(entry, "credential", side_effect=AssertionError("No credentials")), \
                    patch.object(entry, "NightBudget", side_effect=AssertionError("No ledger reopen")), \
                    patch("earnings_http.http.client.HTTPSConnection", side_effect=AssertionError("No review HTTP")):
                return effect.review(self.raw.capacity,
                    self.comparison if comparison is None else comparison,
                    registration_binding=registration, probe=self.probe, output_root=self.output_root)
        finally:
            self.owner.assertEqual(self.raw.rows(), rows)
            self.owner.assertEqual(self.raw.calls, calls)
            self.owner.assertEqual(self.helper.all_originals(self.raw), originals)
            self.owner.assertEqual(self.raw.factory.call_count, factories)


class PredictionEffectTests(unittest.TestCase):
    def test_canonical_score_grammar_all_components_and_half_point_thresholds(self):
        for component in COMPONENTS:
            for token in THRESHOLDS:
                with self.subTest(component=component, token=token):
                    parsed = effect.effect_criterion(declaration(component, token), component)
                    self.assertEqual(parsed, criterion(component, float(token)))
                    self.assertIn(type(parsed["min_delta"]), (int, float))
                    measurement.validate_criterion(parsed)

    def test_score_grammar_rejects_noncanonical_numbers_and_incompatible_semantics(self):
        good = declaration()
        class TextSubclass(str):
            pass
        invalid = [None, True, 1, 1.0, TextSubclass(good), good + "|extra",
            good.replace("earnings-shadow-v2", "earnings-shadow-v3"),
            good.replace("score_out_of_5", "input_tokens"), good.replace("higher", "lower"),
            good.replace("score_nonregression", "score_optional"),
            good.replace("matched_trial_only", "predictive_gain")]
        invalid += [declaration(minimum=token) for token in (
            "0", "-1", "+1", "01", "1.0", "0.50", "1e0", " 1", "1 ", "١",
            "0.1", "0.4999999999", "0.5000000001", "5.5", "NaN", "Infinity", "")]
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                effect.effect_criterion(value, "tool_interface")
        for component in ("research_policy", "memory_policy", "unknown", None, True):
            with self.subTest(component=component), self.assertRaises(ValueError):
                effect.effect_criterion(good, component)

    def test_strict_score_schema_rejects_extra_fields_types_bounds_and_wrong_version(self):
        good = criterion()
        invalid = [dict(good, schema="unknown"), dict(good, component="unknown"),
            dict(good, metric="input_tokens"), dict(good, direction="lower"),
            dict(good, benefit_observed=True), dict(good, schema="earnings_shadow_criterion_v1")]
        invalid += [{key: value for key, value in good.items() if key != missing} for missing in good]
        invalid += [dict(good, min_delta=value) for value in (
            True, False, "1", None, 0, -1, 0.1, 0.4999999999, 0.5000000001,
            5.5, float("nan"), float("inf"), float("-inf"))]
        class DictSubclass(dict):
            pass
        invalid += [None, True, [], DictSubclass(good)]
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                measurement.validate_criterion(value)
        for minimum in (0.5, 1, 1.0, 1.5, 5, 5.0):
            measurement.validate_criterion(dict(good, min_delta=minimum))

    def test_legacy_parser_and_noninteger_numeric_validator_remain_unchanged(self):
        for component, metrics in effect.FAMILIES.items():
            for metric in metrics:
                for direction in ("lower", "higher"):
                    text = (f"earnings-shadow-v1|{component}|{metric}|{direction}|1"
                            "|score_nonregression|matched_trial_only")
                    expected = {"schema": "earnings_shadow_criterion_v1", "component": component,
                        "metric": metric, "direction": direction, "min_delta": 1}
                    self.assertEqual(effect.effect_criterion(text, component), expected)
                    measurement.validate_criterion(expected)
                    # Existing comparison accepts any positive finite numeric
                    # operational threshold; only its textual grammar is integer.
                    measurement.validate_criterion(dict(expected, min_delta=1.25))

    def test_original_scorer_gain_is_benefit_despite_more_child_calls_and_tokens(self):
        fixture = _PredictionReviewFixture(self, axis="R")
        measured = engine.read(fixture.comparison)
        self.assertEqual((measured["parent"]["score_out_of_5"], measured["child"]["score_out_of_5"]), (4, 5))
        self.assertEqual(measured["score_delta"], 1)
        self.assertEqual(set(measured["delta"]), measurement.METRICS | {"score_out_of_5"})
        self.assertEqual(measured["delta"]["score_out_of_5"], 1)
        for key in ("turns", "tool_calls", "input_tokens", "output_tokens"):
            self.assertGreater(measured["delta"][key], 0, key)
        self.assertIs(measured["benefit_observed"], True)
        self.assertEqual(measured["claims"], {"learning": False, "model_authorship": False, "predictive_gain": False})
        originals = self.helper_originals(fixture)
        recomputed = measurement.compare(measured["originals"]["parent"], measured["originals"]["child"],
                                         declaration=measured["declaration"])
        for key, value in recomputed.items():
            self.assertEqual(measured[key], value)
        legacy = measurement.compare(measured["originals"]["parent"], measured["originals"]["child"],
            declaration={"schema": "earnings_shadow_criterion_v1", "component": "research_policy",
                "metric": "tool_calls", "direction": "higher", "min_delta": 1})
        self.assertEqual(set(legacy["delta"]), measurement.METRICS)
        self.assertNotIn("score_out_of_5", legacy["delta"])
        self.assertEqual(legacy["score_delta"], 1)
        self.assertEqual(self.helper_originals(fixture), originals)
        self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)

    def helper_originals(self, fixture):
        return fixture.helper.all_originals(fixture.raw)

    def test_flat_negative_or_subthreshold_original_scores_cannot_create_benefit(self):
        for parent, child, minimum, expected_delta in ((4, 4, "0.5", 0), (4, 3, "0.5", -1), (4, 5, "1.5", 1)):
            with self.subTest(parent=parent, child=child, minimum=minimum):
                fixture = _PredictionReviewFixture(self, parent_points=parent, child_points=child, minimum=minimum)
                measured = engine.read(fixture.comparison)
                self.assertEqual(measured["delta"]["score_out_of_5"], expected_delta)
                self.assertIs(measured["benefit_observed"], False)
                bound = fixture.consume()
                review = engine.read(bound)["review"]
                self.assertEqual((review["decision"], review["reason"]), ("reject", "NO_MATCHED_BENEFIT"))
                self.assertIs(review["benefit_observed"], False)
                self.assertIsNone(review["benefit_evidence_sha256"])
                self.assertFalse((fixture.output_root / "benefit.json").exists())
                output = dict(measured["originals"]["child"], capacity_review="reject",
                    effect_review={"review_receipt": bound, "comparison": fixture.comparison})
                feedback = fixture.raw.task.feedback(output, fixture.raw.envelope)
                self.assertEqual(feedback["research_diagnostics"]["review"]["metric"], "score_out_of_5")
                self.assertEqual(feedback["research_diagnostics"]["review"]["observed_delta"], expected_delta)
                self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)

    def test_score_review_receipt_native_selection_and_label_free_diagnostics_join(self):
        fixture = _PredictionReviewFixture(self)
        bound = fixture.consume()
        review = engine.read(bound)["review"]
        self.assertEqual((review["decision"], review["reason"]), ("accept", "MATCHED_PREDICTION_BENEFIT"))
        self.assertIs(review["benefit_observed"], True)
        self.assertEqual(set(review["checks"]), set(effect.FACTS))
        self.assertEqual(fixture.probe_calls, 1)
        self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)
        measured = engine.read(fixture.comparison)
        output = dict(measured["originals"]["child"], capacity_review="accept",
            effect_review={"review_receipt": bound, "comparison": fixture.comparison})
        feedback = fixture.raw.task.feedback(output, fixture.raw.envelope)
        projected = feedback["research_diagnostics"]
        self.assertEqual(projected["review"], {
            "verdict": "accept", "reason": "MATCHED_PREDICTION_BENEFIT",
            "metric": "score_out_of_5", "direction": "higher", "min_delta": 1,
            "observed_delta": 1, "score_delta": 1, "benefit_observed": True})
        self.assertEqual(projected["execution"], measured["child"])
        self.assertEqual(diagnostics.validate_diagnostics(projected, feedback["observation"]), projected)
        for changes in ({"metric": "input_tokens"}, {"direction": "lower"},
                        {"observed_delta": 0}, {"score_delta": 0}, {"min_delta": 1.5},
                        {"benefit_observed": False}, {"verdict": "reject"}):
            changed = deepcopy(projected)
            changed["review"].update(changes)
            with self.subTest(invalid_review=changes), self.assertRaises(ValueError):
                diagnostics.validate_diagnostics(changed, feedback["observation"])
        # Free-form QA and arbitrary scorer fields must not appear in this
        # diagnostic projection; the fixture marker is not model evidence.
        serialized = json.dumps(projected)
        for forbidden in ("ground_truth", "predicted_value", str(fixture.raw.root), SYNTHETIC):
            self.assertNotIn(forbidden, serialized)
        fixture.raw.capacity.review(bound, expected_state_sha256=fixture.before["state_sha256"])
        after = fixture.raw.native.batch.snapshot()["micro_evolution"]
        self.assertIsNone(after["pending"])
        self.assertEqual(digest(after["active_pair"]), fixture.raw.tested)
        self.assertEqual(after["history"][-1]["review"]["reason"], "MATCHED_PREDICTION_BENEFIT")

    def test_recomputed_originals_reject_fabricated_score_delta_benefit_and_claims(self):
        fixture = _PredictionReviewFixture(self)
        for key in ("score_delta", "delta", "benefit_observed", "claims"):
            changed = engine.read(fixture.comparison)
            if key == "score_delta": changed[key] = 2
            elif key == "delta": changed[key]["score_out_of_5"] = 2
            elif key == "benefit_observed": changed[key] = False
            else: changed[key]["predictive_gain"] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "recomputed"):
                fixture.consume(fixture.save("forged-comparison", changed))
        self.assertEqual(fixture.probe_calls, 0)
        self.assertEqual(fixture.raw.native.batch.snapshot(), fixture.before)


if __name__ == "__main__":
    unittest.main()
