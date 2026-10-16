"""Independent inert tests of the three-slot earnings research archive.

All sources, evidence, scores and companies here are synthetic temporary
fixtures.  These tests neither query the benchmark nor claim live progress.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_population as population


class PopulationFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.serial = 0
        self.r = self.artifact("baseline R source\n", "r")
        self.h = self.artifact("baseline H source\n", "h")
        self.evidence = [self.artifact({"scope": "synthetic capability evidence"})]
        self.protected = {key: hashlib.sha256(key.encode()).hexdigest() for key in "KMC"}
        self.stable = population.version(self.r, self.h)
        self.initial = population.initialize(self.stable, self.protected,
                                             exposed_companies=["synthetic-exposed"])

    def artifact(self, value, label="evidence"):
        self.serial += 1
        path = self.root / f"{label}-{self.serial}.txt"
        payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        path.write_text(payload)
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def child(self, *, parent=None, axis="R", label="alternative"):
        parent = parent or self.stable
        r, h = parent["R"], parent["H"]
        if axis == "R":
            r = self.artifact(f"synthetic {label} R implementation\n", "r")
        else:
            h = self.artifact(f"synthetic {label} H implementation\n", "h")
        return population.version(r, h, parent=parent["id"], axis=axis,
                                  method=label, author="synthetic-author",
                                  evidence=self.evidence)

    def retained(self, *, state=None, child=None):
        child = child or self.child()
        result = population.retain(state or self.initial, child,
                                   reason="Test a distinct documented hypothesis",
                                   evidence=self.evidence)
        return result, child

    def observed(self, state, company, scores):
        results = [{"version_id": version_id, "points": points,
                    "evidence": self.evidence} for version_id, points in scores.items()]
        feedback = self.artifact({"company": company, "interpretation": "synthetic only"})
        return population.observe(state, company, results, feedback=feedback)


class PopulationTests(PopulationFixture):
    def test_initialize_has_one_stable_anchor_and_no_explorers(self):
        self.assertEqual(self.initial["stable_id"], self.stable["id"])
        self.assertEqual(self.initial["anchor_id"], self.stable["id"])
        self.assertEqual(self.initial["explorers"], [])
        self.assertEqual(set(self.initial["versions"]), {self.stable["id"]})
        self.assertEqual(self.initial["protected"], self.protected)
        self.assertEqual(self.initial["exposed_companies"], ["synthetic-exposed"])
        self.assertEqual(population.validate(self.initial), self.initial)

    def test_same_source_pair_has_same_version_identity(self):
        again = population.version(self.r, self.h)
        self.assertEqual(again["id"], self.stable["id"])
        self.assertNotEqual(self.child()["id"], self.stable["id"])

    def test_initialize_and_validate_do_not_mutate_inputs(self):
        stable, protected = copy.deepcopy(self.stable), copy.deepcopy(self.protected)
        population.initialize(self.stable, self.protected)
        self.assertEqual(self.stable, stable)
        self.assertEqual(self.protected, protected)
        before = copy.deepcopy(self.initial)
        population.validate(self.initial)
        self.assertEqual(self.initial, before)

    def test_two_explorers_allowed_third_refused_without_losing_archive(self):
        first, child1 = self.retained()
        second, child2 = self.retained(state=first, child=self.child(label="second-method"))
        self.assertEqual(second["explorers"], [child1["id"], child2["id"]])
        self.assertEqual(second["stable_id"], self.stable["id"])
        before = copy.deepcopy(second)
        with self.assertRaises(ValueError):
            self.retained(state=second, child=self.child(label="third-method"))
        self.assertEqual(second, before)

    def test_retain_is_pure_and_siblings_keep_exact_parent(self):
        before = copy.deepcopy(self.initial)
        child = self.child()
        child_before = copy.deepcopy(child)
        result, _ = self.retained(child=child)
        self.assertEqual(self.initial, before)
        self.assertEqual(child, child_before)
        self.assertEqual(result["versions"][child["id"]]["parent"], self.stable["id"])
        self.assertEqual(result["versions"][self.stable["id"]], self.stable)

    def test_duplicate_version_is_not_an_additional_explorer(self):
        state, child = self.retained()
        with self.assertRaises(ValueError):
            self.retained(state=state, child=child)
        with self.assertRaises(ValueError):
            self.retained(child=self.stable)

    def test_unknown_parent_and_same_source_nonmutation_are_refused(self):
        child = self.child()
        child["parent"] = "f" * 64
        with self.assertRaises(ValueError):
            self.retained(child=child)
        with self.assertRaises(ValueError):
            unchanged = population.version(self.r, self.h, parent=self.stable["id"],
                axis="R", method="unchanged", author="synthetic", evidence=self.evidence)
            self.retained(child=unchanged)

    def test_axis_must_identify_exactly_one_actual_source_change(self):
        for axis, r, h in (
            ("R", self.r, self.artifact("changed H")),
            ("H", self.artifact("changed R"), self.h),
            ("R", self.artifact("changed R"), self.artifact("changed H")),
        ):
            with self.subTest(axis=axis), self.assertRaises(ValueError):
                child = population.version(r, h, parent=self.stable["id"], axis=axis,
                    method="misdeclared axis", author="synthetic", evidence=self.evidence)
                self.retained(child=child)

    def test_empty_rationale_or_evidence_cannot_retain(self):
        child = self.child()
        for reason, evidence in (("", self.evidence), ("   ", self.evidence),
                                 ("unsubstantiated", [])):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                population.retain(self.initial, child, reason=reason, evidence=evidence)

    def test_retirement_keeps_full_descriptor_and_append_only_history(self):
        state, child = self.retained()
        before = copy.deepcopy(state)
        retired = population.retire(state, child["id"], reason="Specific question resolved",
                                    evidence=self.evidence)
        self.assertEqual(state, before)
        self.assertEqual(retired["explorers"], [])
        self.assertEqual(retired["versions"], state["versions"])
        self.assertEqual(retired["history"][:len(state["history"])], state["history"])
        self.assertGreater(len(retired["history"]), len(state["history"]))

    def test_stable_or_unknown_branch_cannot_be_retired(self):
        for version_id in (self.stable["id"], "e" * 64):
            with self.subTest(version_id=version_id), self.assertRaises(ValueError):
                population.retire(self.initial, version_id, reason="not an explorer",
                                  evidence=self.evidence)

    def test_negative_and_tied_scores_retain_exploration_without_promoting(self):
        state, child = self.retained()
        for index, score in enumerate((1.0, 2.0)):
            before = copy.deepcopy(state)
            updated = self.observed(state, f"synthetic-company-{index}",
                {self.stable["id"]: 2.0, child["id"]: score})
            self.assertEqual(state, before)
            self.assertEqual(updated["stable_id"], self.stable["id"])
            self.assertIn(child["id"], updated["explorers"])
            state = updated
        self.assertEqual(len(state["observations"]), 2)
        with self.assertRaises(ValueError):
            population.promote(state, child["id"], evidence=self.evidence)

    def test_promotion_requires_two_distinct_paired_companies(self):
        state, child = self.retained()
        state = self.observed(state, "synthetic-new-1",
            {self.stable["id"]: 1.0, child["id"]: 2.0})
        with self.assertRaises(ValueError):
            population.promote(state, child["id"], evidence=self.evidence)
        with self.assertRaises(ValueError):
            population.promote(state, child["id"], evidence=self.evidence, minimum_companies=1)
        state = self.observed(state, "synthetic-new-2",
            {self.stable["id"]: 2.0, child["id"]: 2.5})
        before = copy.deepcopy(state)
        promoted = population.promote(state, child["id"], evidence=self.evidence)
        self.assertEqual(state, before)
        self.assertEqual(promoted["stable_id"], child["id"])
        self.assertEqual(promoted["anchor_id"], self.stable["id"])
        self.assertIn(self.stable["id"], promoted["versions"])
        self.assertNotIn(child["id"], promoted["explorers"])
        self.assertEqual(promoted["observations"], state["observations"])

    def test_one_large_win_does_not_cancel_a_regression_for_promotion(self):
        state, child = self.retained()
        state = self.observed(state, "synthetic-first",
            {self.stable["id"]: 1.0, child["id"]: 5.0})
        state = self.observed(state, "synthetic-second",
            {self.stable["id"]: 2.0, child["id"]: 1.5})
        with self.assertRaises(ValueError):
            population.promote(state, child["id"], evidence=self.evidence)

    def test_observe_requires_exact_complete_current_pool(self):
        state, child = self.retained()
        for scores in ({self.stable["id"]: 1.0}, {child["id"]: 1.0},
                       {self.stable["id"]: 1.0, child["id"]: 1.0, "f" * 64: 5.0}):
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                self.observed(state, "synthetic-company", scores)

    def test_duplicate_company_or_version_score_is_refused(self):
        state, child = self.retained()
        scores = {self.stable["id"]: 1.0, child["id"]: 1.5}
        state = self.observed(state, "synthetic-company", scores)
        with self.assertRaises(ValueError):
            self.observed(state, "synthetic-company", scores)
        result = {"version_id": self.stable["id"], "points": 1.0, "evidence": self.evidence}
        with self.assertRaises(ValueError):
            population.observe(self.initial, "synthetic-other", [result, result],
                               feedback=self.artifact({"synthetic": True}))

    def test_original_five_point_half_increment_scores_are_enforced(self):
        for score in (-0.5, 5.5, 1.25, True, float("nan"), float("inf"), "1.5"):
            with self.subTest(score=repr(score)), self.assertRaises(ValueError):
                self.observed(self.initial, "synthetic-company", {self.stable["id"]: score})
        for index, score in enumerate((0, 0.5, 1.5, 5)):
            self.observed(self.initial, f"synthetic-valid-{index}", {self.stable["id"]: score})

    def test_exposed_company_is_not_fresh_validation(self):
        with self.assertRaises(ValueError):
            self.observed(self.initial, "synthetic-exposed", {self.stable["id"]: 1.0})

    def test_source_content_drift_invalidates_state(self):
        Path(self.r["path"]).write_text("different source after binding")
        with self.assertRaises(ValueError):
            population.validate(self.initial)

    def test_evidence_content_drift_invalidates_retained_state(self):
        state, _ = self.retained()
        Path(self.evidence[0]["path"]).write_text("different evidence after binding")
        with self.assertRaises(ValueError):
            population.validate(state)

    def test_tampered_or_unbounded_pool_and_history_are_refused(self):
        state, child = self.retained()
        variants = []
        wrong = copy.deepcopy(state)
        wrong["explorers"] = [child["id"]] * 3
        variants.append(wrong)
        wrong = copy.deepcopy(state)
        wrong["stable_id"] = "f" * 64
        variants.append(wrong)
        wrong = copy.deepcopy(state)
        wrong["protected"]["K"] = "f" * 64
        variants.append(wrong)
        wrong = copy.deepcopy(state)
        wrong["history"] = []
        variants.append(wrong)
        for index, altered in enumerate(variants):
            with self.subTest(variant=index), self.assertRaises(ValueError):
                population.validate(altered)

    def test_history_must_bind_current_stable_explorers_and_archive(self):
        state, child = self.retained()
        variants = []
        wrong = copy.deepcopy(state)
        wrong["stable_id"], wrong["explorers"] = child["id"], []
        variants.append(wrong)
        wrong = copy.deepcopy(state)
        wrong["explorers"] = []
        variants.append(wrong)
        wrong = copy.deepcopy(state)
        extra = self.child(label="unrecorded")
        wrong["versions"][extra["id"]] = extra
        variants.append(wrong)
        for index, altered in enumerate(variants):
            with self.subTest(variant=index), self.assertRaises(ValueError):
                population.validate(altered)

    def test_scored_observations_cannot_be_edited_duplicated_or_deleted(self):
        state, child = self.retained()
        state = self.observed(state, "synthetic-observed",
            {self.stable["id"]: 1.0, child["id"]: 1.5})
        variants = []
        wrong = copy.deepcopy(state)
        wrong["observations"][0]["results"][0]["points"] = 5.0
        variants.append(wrong)
        wrong = copy.deepcopy(state)
        wrong["observations"].append(copy.deepcopy(wrong["observations"][0]))
        variants.append(wrong)
        wrong = copy.deepcopy(state)
        wrong["observations"] = []
        variants.append(wrong)
        for index, altered in enumerate(variants):
            with self.subTest(variant=index), self.assertRaises(ValueError):
                population.validate(altered)

    def test_exposure_list_cannot_silently_lose_or_gain_companies(self):
        state = self.observed(self.initial, "synthetic-observed", {self.stable["id"]: 1.0})
        for exposures in (["synthetic-exposed"],
                          ["synthetic-exposed", "synthetic-observed", "unrecorded-company"]):
            changed = dict(state, exposed_companies=exposures)
            with self.subTest(exposures=exposures), self.assertRaises(ValueError):
                population.validate(changed)

    def test_observed_feedback_content_is_revalidated_before_next_operation(self):
        state = self.observed(self.initial, "synthetic-observed", {self.stable["id"]: 1.0})
        Path(state["observations"][0]["feedback"]["path"]).write_text("different feedback")
        with self.assertRaises(ValueError):
            population.validate(state)

    def test_retirement_evidence_remains_bound_even_after_branch_stops(self):
        state, child = self.retained()
        retired_evidence = self.artifact({"synthetic": "distinct retirement observation"})
        state = population.retire(state, child["id"], reason="Resolved follow-up",
                                  evidence=[retired_evidence])
        Path(retired_evidence["path"]).write_text("changed retirement evidence")
        with self.assertRaises(ValueError):
            population.validate(state)

    def test_retired_method_can_parent_a_new_distinct_followup(self):
        state, child = self.retained()
        state = population.retire(state, child["id"], reason="Stop this exact recipe",
                                  evidence=self.evidence)
        followup = self.child(parent=child, axis="H", label="follow-up tool")
        continued, _ = self.retained(state=state, child=followup)
        self.assertEqual(continued["explorers"], [followup["id"]])
        self.assertEqual(continued["versions"][followup["id"]]["parent"], child["id"])
        self.assertIn(child["id"], continued["versions"])
        self.assertEqual(continued["stable_id"], self.stable["id"])

    def test_stale_scores_against_previous_stable_cannot_promote_another_branch(self):
        state, first = self.retained()
        state, second = self.retained(state=state, child=self.child(label="second-method"))
        for index in (1, 2):
            state = self.observed(state, f"synthetic-before-promotion-{index}",
                {self.stable["id"]: 1.0, first["id"]: 2.0, second["id"]: 2.5})
        state = population.promote(state, first["id"], evidence=self.evidence)
        with self.assertRaises(ValueError):
            population.promote(state, second["id"], evidence=self.evidence)

    def test_promotion_requires_predeclared_mean_gain_not_merely_any_gain(self):
        state, child = self.retained()
        for company, score in (("synthetic-small-gain", 1.5), ("synthetic-tie", 1.0)):
            state = self.observed(state, company, {self.stable["id"]: 1.0, child["id"]: score})
        with self.assertRaises(ValueError):
            population.promote(state, child["id"], evidence=self.evidence)

    def test_symlink_or_relative_source_is_not_a_canonical_absolute_binding(self):
        symlink = self.root / "symlink-source.txt"
        symlink.symlink_to(self.r["path"])
        for path in (str(symlink), "tools/earnings_population.py"):
            source = {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            with self.subTest(path=path), self.assertRaises(ValueError):
                population.version(source, self.h)


if __name__ == "__main__":
    unittest.main()
