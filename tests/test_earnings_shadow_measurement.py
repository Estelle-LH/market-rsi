"""Measured original-trace facts, not fabricated benefit or learning evidence.

Positive inputs are actual Task.shadow_execution outputs from CP3's raw-HTTP
fixture. Controlled corruption after verification is explicitly untrusted
synthetic input; original bytes are preserved before every such mutation.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import earnings_entry as entry
import earnings_shadow_measurement as measurement
import test_earnings_capacity_forecast as raw_fixture
import test_earnings_shadow_execution as shadow_fixture

METRICS = {"turns", "tool_calls", "input_tokens", "output_tokens",
           "tool_return_characters", "repeated_reads", "rejected_tools", "records_added"}
SAFE_FIELDS = METRICS | {"score_out_of_5", "initial_records"}


class ShadowMeasurementTests(unittest.TestCase):
    def traces(self, axis="R", *, parent_replies=None, child_replies=None):
        helper = shadow_fixture.ShadowExecutionTests(
            "test_actual_parent_and_child_forecasts_share_prior_bytes_but_distinct_consumption")
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture(axis)
        parent, child = helper.worker(fixture, shadow=False), helper.worker(fixture)
        parent_output = helper.invoke(fixture, parent, replies=parent_replies)
        parent_verified = helper.verify(fixture, parent_output, parent, tested_pair_sha256=fixture.active)
        child_output = helper.invoke(fixture, child, slot=1, replies=child_replies)
        child_verified = helper.verify(fixture, child_output, child, slot=1)
        return fixture, parent_verified, child_verified

    def criterion(self, *, component="tool_interface", metric="tool_return_characters",
                  direction="lower", min_delta=1):
        return {"schema": "earnings_shadow_criterion_v1", "component": component,
                "metric": metric, "direction": direction, "min_delta": min_delta}

    def assert_safe(self, observed):
        self.assertEqual(set(observed), SAFE_FIELDS)
        for key, value in observed.items():
            self.assertIn(type(value), (int, float), key)
            self.assertNotIsInstance(value, bool)
            self.assertGreaterEqual(value, 0)
        # No free-form strings/paths/questions/QA/error bodies can be returned.
        self.assertNotIn("artifacts", observed)
        self.assertNotIn("predictions", observed)
        self.assertNotIn("ground_truth", observed)

    def original(self, verified, suffix):
        bound = next(row for row in verified["artifacts"] if Path(row["path"]).name == suffix)
        return json.loads(entry.checked(bound))

    def rebound_corruption(self, verified, name, update):
        """Forge an untrusted post-verification fixture, preserving old bytes."""
        copied = deepcopy(verified)
        index = next(i for i, row in enumerate(copied["artifacts"]) if Path(row["path"]).name == name)
        old = copied["artifacts"][index]
        path = Path(old["path"])
        value = json.loads(entry.checked(old))
        (path.parent / ("before-measurement-corruption-" + path.name)).write_bytes(path.read_bytes())
        update(value)
        path.write_bytes(raw_fixture._wire(value))
        bound = raw_fixture._pin(path)
        copied["artifacts"][index] = bound
        for key in ("result", "score", "state"):
            if copied[key] == old:
                copied[key] = bound
        return copied

    def test_observe_actual_originals_derives_exact_ten_label_free_numeric_facts(self):
        fixture, parent, unused = self.traces()
        before = fixture.native.batch.snapshot()
        originals, rows = fixture.originals(), fixture.rows()
        observed = measurement.observe(parent)
        self.assert_safe(observed)
        observations = [json.loads(path.read_bytes()) for path in Path(fixture.slots[0]).glob("01-tool-*.json")]
        returned = sum(len(row["output"]) for row in observations)
        self.assertEqual(observed, {"turns": 2, "tool_calls": 2, "input_tokens": 24,
            "output_tokens": 14, "tool_return_characters": returned, "repeated_reads": 0,
            "rejected_tools": 0, "records_added": 1, "score_out_of_5": 5, "initial_records": 0})
        self.assertEqual(fixture.originals(), originals)
        self.assertEqual(fixture.native.batch.snapshot(), before)
        self.assertEqual(fixture.rows(), rows)

    def test_actual_H_lowered_tool_return_gives_only_predeclared_operational_benefit(self):
        fixture, parent, child = self.traces("H")
        before = fixture.native.batch.snapshot()
        criterion = self.criterion()
        original_criterion = deepcopy(criterion)
        compared = measurement.compare(parent, child, declaration=criterion)
        self.assertEqual(set(compared), {"schema", "parent", "child", "declaration", "delta",
            "score_delta", "benefit_observed", "originals", "claims"})
        self.assertEqual(compared["schema"], "earnings_matched_shadow_v1")
        self.assert_safe(compared["parent"])
        self.assert_safe(compared["child"])
        for metric in METRICS:
            self.assertEqual(compared["delta"][metric], compared["child"][metric] - compared["parent"][metric])
        self.assertLess(compared["delta"]["tool_return_characters"], -1)
        self.assertEqual(compared["score_delta"], 0)
        self.assertIs(compared["benefit_observed"], True)
        self.assertEqual(compared["declaration"], original_criterion)
        self.assertEqual(criterion, original_criterion)
        self.assertEqual(compared["originals"], {"parent": parent, "child": child})
        self.assertEqual(compared["claims"], {"learning": False, "model_authorship": False, "predictive_gain": False})
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_actual_R_instruction_change_with_unchanged_metrics_has_no_invented_benefit(self):
        fixture, parent, child = self.traces("R")
        before = fixture.native.batch.snapshot()
        compared = measurement.compare(parent, child, declaration=self.criterion(
            component="research_policy", metric="input_tokens", direction="lower"))
        self.assertEqual(compared["score_delta"], 0)
        self.assertTrue(all(compared["delta"][metric] == 0 for metric in METRICS))
        self.assertIs(compared["benefit_observed"], False)
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_real_score_regression_prevents_benefit_despite_lower_H_tool_return(self):
        helper = shadow_fixture.ShadowExecutionTests(
            "test_actual_parent_and_child_forecasts_share_prior_bytes_but_distinct_consumption")
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture("H")
        parent_worker, child_worker = helper.worker(fixture, shadow=False), helper.worker(fixture)
        parent_output = helper.invoke(fixture, parent_worker)
        parent = helper.verify(fixture, parent_output, parent_worker, tested_pair_sha256=fixture.active)
        worse = fixture.final({"predictions": [{"target_id": f"T{i:03d}", "predicted_value": 200}
                                              for i in range(1, 6)]})
        child_output = helper.invoke(fixture, child_worker, slot=1, replies=[fixture.research(), worse])
        child = helper.verify(fixture, child_output, child_worker, slot=1)
        before = fixture.native.batch.snapshot()
        compared = measurement.compare(parent, child, declaration=self.criterion())
        self.assertLess(compared["delta"]["tool_return_characters"], 0)
        self.assertEqual(compared["score_delta"], -5)
        self.assertIs(compared["benefit_observed"], False)
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_opposite_direction_or_unmet_positive_threshold_is_not_benefit(self):
        fixture, parent, child = self.traces("H")
        before = fixture.native.batch.snapshot()
        for criterion in (self.criterion(direction="higher"), self.criterion(min_delta=10**9)):
            with self.subTest(criterion=criterion):
                compared = measurement.compare(parent, child, declaration=criterion)
                self.assertIs(compared["benefit_observed"], False)
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_malformed_or_posthoc_criterion_cannot_create_observed_benefit(self):
        fixture, parent, child = self.traces("H")
        valid = self.criterion()
        variants = [dict(valid, schema="unknown"), dict(valid, component="new_authority"),
            dict(valid, metric="score_out_of_5"), dict(valid, direction="sideways"),
            dict(valid, benefit_observed=True), {key: value for key, value in valid.items() if key != "component"}]
        variants.extend(dict(valid, min_delta=value) for value in (0, -1, True, "1", float("nan"), float("inf")))
        before = fixture.native.batch.snapshot()
        for criterion in variants:
            with self.subTest(criterion=repr(criterion)), self.assertRaises(ValueError):
                measurement.compare(parent, child, declaration=criterion)
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_unmatched_active_pending_state_or_tested_pair_is_rejected(self):
        fixture, parent, child = self.traces("H")
        before = fixture.native.batch.snapshot()
        variants = []
        for name in ("active_pair_sha256", "pending_proposal_sha256", "state_sha256"):
            changed = deepcopy(child)
            changed["consumed"][name] = "d" * 64
            variants.append(changed)
        same_pair = deepcopy(child)
        same_pair["consumed"]["tested_pair_sha256"] = parent["consumed"]["tested_pair_sha256"]
        variants.append(same_pair)
        ordinary = deepcopy(child)
        ordinary["consumed"] = {"pair_sha256": fixture.tested, "state_sha256": fixture.initial["sha256"]}
        variants.append(ordinary)
        for changed in variants:
            with self.assertRaises(ValueError):
                measurement.compare(parent, changed, declaration=self.criterion())
        not_parent = deepcopy(parent)
        not_parent["consumed"]["tested_pair_sha256"] = fixture.tested
        with self.assertRaises(ValueError):
            measurement.compare(not_parent, child, declaration=self.criterion())
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_every_bound_input_original_is_rechecked_before_observation(self):
        for kind in ("request", "qa", "state"):
            with self.subTest(kind=kind):
                fixture, parent, unused = self.traces()
                if kind == "request":
                    binding = next(row for row in parent["artifacts"] if Path(row["path"]).name == "01-request.json")
                elif kind == "qa": binding = fixture.kernel["qa"]
                else: binding = parent["state"]
                path = Path(binding["path"])
                (path.parent / ("before-measurement-corruption-" + path.name)).write_bytes(path.read_bytes())
                path.write_bytes(path.read_bytes() + b" ")
                before, originals = fixture.native.batch.snapshot(), fixture.originals()
                with self.assertRaises(ValueError):
                    measurement.observe(parent)
                self.assertEqual(fixture.originals(), originals)
                self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_missing_duplicate_or_rebound_malformed_count_is_not_valid_trace(self):
        for kind in ("missing", "duplicate", "malformed", "count-too-small"):
            with self.subTest(kind=kind):
                fixture, parent, unused = self.traces()
                changed = deepcopy(parent)
                count = next(row for row in changed["artifacts"] if Path(row["path"]).name == "01-count.json")
                if kind == "missing": changed["artifacts"].remove(count)
                elif kind == "duplicate": changed["artifacts"].append(deepcopy(count))
                else:
                    value = True if kind == "malformed" else 0
                    changed = self.rebound_corruption(parent, "01-count.json",
                        lambda counted: counted.update(input_tokens=value))
                before = fixture.native.batch.snapshot()
                with self.assertRaises(ValueError):
                    measurement.observe(changed)
                self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_valid_rejected_tool_with_bad_argument_shape_counts_rejection_not_read(self):
        helper = shadow_fixture.ShadowExecutionTests(
            "test_actual_parent_and_child_forecasts_share_prior_bytes_but_distinct_consumption")
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture("R")
        worker = helper.worker(fixture, shadow=False)
        rejected = fixture.response([{"type": "function_call", "call_id": "malformed-read",
            "name": "read_file", "arguments": json.dumps({"path": "filings/old.md",
                                                          "offset": 0, "characters": "not an integer"})}])
        output = helper.invoke(fixture, worker, replies=[rejected, fixture.final()])
        verified = helper.verify(fixture, output, worker, tested_pair_sha256=fixture.active)
        before = fixture.native.batch.snapshot()
        observed = measurement.observe(verified)
        self.assert_safe(observed)
        self.assertEqual((observed["tool_calls"], observed["rejected_tools"], observed["repeated_reads"]), (1, 1, 0))
        self.assertEqual(observed["records_added"], 0)
        self.assertEqual(observed["score_out_of_5"], 5)
        self.assertEqual(fixture.native.batch.snapshot(), before)

    def test_repeated_reads_count_duplicate_original_requested_signature(self):
        helper = shadow_fixture.ShadowExecutionTests(
            "test_actual_parent_and_child_forecasts_share_prior_bytes_but_distinct_consumption")
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture("H")
        worker = helper.worker(fixture)
        requested = {"path": "filings/old.md", "offset": 0, "characters": 5000}
        twice = fixture.response([{"type": "function_call", "call_id": f"repeated-read-{n}",
            "name": "read_file", "arguments": json.dumps(requested)} for n in (1, 2)])
        output = helper.invoke(fixture, worker, replies=[twice, fixture.final()])
        verified = helper.verify(fixture, output, worker)
        observed = measurement.observe(verified)
        self.assertEqual((observed["tool_calls"], observed["repeated_reads"], observed["rejected_tools"]), (2, 1, 0))
        self.assertEqual(observed["records_added"], 0)
        # The metric is request repetition, not overlapping spans or evidence quality.
        self.assertEqual(worker.context["tool_bounds"]["read_chunk_limit"], 1000)

    def test_component_metric_families_are_explicit_and_do_not_reward_arbitrary_counts(self):
        fixture, parent, child = self.traces("H")
        research = {"turns", "tool_calls", "input_tokens", "output_tokens",
                    "repeated_reads", "rejected_tools", "records_added"}
        harness = research - {"records_added"} | {"tool_return_characters"}
        before = fixture.native.batch.snapshot()
        for component, allowed in (("research_policy", research), ("memory_policy", research),
                                   ("tool_interface", harness)):
            for metric in METRICS:
                criterion = self.criterion(component=component, metric=metric)
                with self.subTest(component=component, metric=metric):
                    if metric in allowed:
                        compared = measurement.compare(parent, child, declaration=criterion)
                        self.assertEqual(compared["declaration"], criterion)
                    else:
                        with self.assertRaises(ValueError):
                            measurement.compare(parent, child, declaration=criterion)
        self.assertEqual(fixture.native.batch.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
