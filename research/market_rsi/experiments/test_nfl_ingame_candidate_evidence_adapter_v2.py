"""Matched synthetic execution: no resident Train or account/provider operations."""
from __future__ import annotations
import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from experiments import nfl_ingame_candidate_evidence_adapter_v2 as adapter
from experiments import test_nfl_ingame_candidate_evidence_adapter as inherited

common, c7, shared, reference = adapter.common, adapter.c7, adapter.shared, adapter.reference
ARM_CANDIDATE = c7.ARM_CANDIDATE


def prepare(rows, frozen, parent_reference):
    if set(parent_reference) != {"candidate_id", "runner_sha256", "reference_sha256", "provenance", "comparison_only"} or parent_reference["comparison_only"] is not True:
        raise AssertionError("no implicit parent state/weights")
    return {"constant": 1}, {"synthetic": True, "rows": len(rows), "parent_context": parent_reference}


def fit(fit_rows, check, context):
    if set(context) != {"features", "fold_id", "parent_reference"} or context["features"] != {"constant": 1}:
        raise AssertionError("wrong generic context")
    return c7.fit_temperature(fit_rows, check, None)


def replay(state, check, context):
    return c7.replay_predictor(state, check)


def fit_tree(fit_rows, check, context):
    # A single trained, two-leaf primitive model; fixed stage count is completion
    # evidence, without imposing an optimizer or convergence boolean.
    groups = [[row.trusted["outcome"] for row in fit_rows if (row.trusted["market_probability"] >= .5) == side] for side in (False, True)]
    state = {"schema": "synthetic_two_leaf_tree_v1", "fit_events": len(fit_rows),
             "leaves": [sum(group) / len(group) if group else .5 for group in groups]}
    values, bounds = replay_tree(state, check, context)
    return values, {"model_fits": 1, "n_iter": 1, "primitive_prediction_state": state,
        "predictor_state_sha256": common._digest(state), "bounding": bounds}


def replay_tree(state, check, context):
    epsilon = common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
    values = [min(1 - epsilon, max(epsilon, state["leaves"][int(row.trusted["market_probability"] >= .5)])) for row in check]
    return values, {"clipped_rows": 0, "rows_removed": 0, "epsilon": epsilon}


def fixture_binding(root, rows, folds, frozen, controls, parent_id="SyntheticValidNegativeParent-v1", requirements=None):
    checks = [row for fold in folds for row in sorted([r for r in rows if r.game_date in fold["check_dates"]], key=lambda r: r.key)]
    frozen.update(manifest={"task_id": "InGameWinProbabilityTrainDiagnostic-v0", "source_events": 195, "materialized_events": 193, "excluded_events": 2},
        lock={"folds": folds, "orientation": "home_token", "synthetic": True},
        exclusion_codes=dict(common.identity.EXPECTED_EXCLUSIONS), check_key_sha256=common._digest([list(r.key) for r in checks]))
    frozen["predictions"] = [{**row.trusted, "fold": controls[row.key]["fold"], "game_id": row.game_id, "game_date": row.game_date,
        "game_week": row.game_week, "raw_market_probability": controls[row.key][shared.ARM_RAW],
        "market_model_probability": controls[row.key][shared.ARM_ORDINARY], "market_plus_state_probability": controls[row.key][shared.ARM_PARENT]} for row in checks]
    parent_root = root / "parent"
    parent_root.mkdir()
    original_source = root / "original_parent.py"
    original_source.write_text("# synthetic archived comparison source only\n", encoding="utf-8")
    parent = {row.key: row.trusted["market_probability"] for row in checks}
    csv_rows = [{"fold": controls[row.key]["fold"], "game_id": row.game_id, "game_date": row.game_date, "game_week": row.game_week,
        "event_id": row.key[0], "market_id": row.key[1], "cutoff_ms": row.key[2], "outcome_available_ms": row.trusted["outcome_available_ms"],
        "outcome": row.trusted["outcome"], "raw_market_probability": parent[row.key],
        "frozen_v0_ordinary_market_only_probability": controls[row.key][shared.ARM_ORDINARY],
        "frozen_v0_market_plus_state_parent_probability": controls[row.key][shared.ARM_PARENT], "candidate_probability": parent[row.key]} for row in checks]
    with (parent_root / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    exclusions = {"source_events": 195, "materialized_events": 193, "excluded_events": 2,
        "exclusions": [{"game_id": game, "reason": code} for game, code in common.identity.EXPECTED_EXCLUSIONS]}
    inputs = {"task_id": parent_id, "runner_sha256": common._sha256(original_source), "v0_artifact_hashes": frozen["hashes"], **frozen["receipts"], **common.BOUNDARY_FLAGS}
    for name, value in (("input_receipts", inputs), ("pre_score_lock", {"task_id": parent_id, "folds": folds, **common.BOUNDARY_FLAGS}),
                        ("exclusions", exclusions), ("scorecard", {"task_id": parent_id, "operational_decision": "REVERT"})):
        common.base._atomic_json(parent_root / (name + ".json"), value)
    hashes = {name: common._sha256(parent_root / name) for name in reference.ARTIFACTS - {"manifest.json"}}
    common.base._atomic_json(parent_root / "manifest.json", {"complete": True, "task_id": parent_id, "model_fits": 4, "check_events": 87,
        **{name.rsplit(".", 1)[0] + "_sha256": value for name, value in hashes.items()}})
    hashes["manifest.json"] = common._sha256(parent_root / "manifest.json")
    parent_spec = {"schema": reference.SCHEMA, "candidate_id": parent_id, "runner": {"path": str(original_source), "sha256": common._sha256(original_source)},
        "source_commit": "a" * 40, "artifact_root": str(parent_root), "artifact_hashes": hashes, "kernel_sha256": "c94492041d5c331a2cc31c4d6cd529984742ce200e1b9365e3fb7d07e5b1ce64"}
    reviews = {}
    for kind in ("source", "result", "learning"):
        path = root / f"synthetic_{kind}_review.json"
        common.base._atomic_json(path, {"schema": "synthetic_original_review", "role": kind, "candidate_id": parent_id})
        reviews[kind] = {"path": str(path), "sha256": common._sha256(path)}
    acceptance_path = root / "acceptance.json"
    common.base._atomic_json(acceptance_path, {"schema": reference.ACCEPTANCE_SCHEMA, "reference_sha256": reference.digest(parent_spec),
        "performance_status": "valid_no_leakage", "prediction_decision": "REVERT", "provenance": reference.provenance(parent_spec, frozen),
        "exclusions": exclusions, "reviews": reviews})
    actual_parent = {"candidate_id": parent_id, "runner_sha256": parent_spec["runner"]["sha256"]}
    contract_path = root / "candidate_contract.json"
    contract = {"candidate_id": "SyntheticForecast-v1", "research_parent": actual_parent,
        "comparison_incumbent_sha256": "d" * 64, "fixed_predictive_information": {"feature_names": ["market_logit"]},
        "attribution": "H-matched synthetic entry", "fit_completion_requirements": requirements or {"optimizer.converged": True},
        "accepted_reference": {"reference": parent_spec, "acceptance_binding": {"path": str(acceptance_path), "sha256": common._sha256(acceptance_path)}}}
    common.base._atomic_json(contract_path, contract)
    source = str(Path(__file__).resolve())
    dependencies = {**adapter.legacy.held_c7_binding()["dependency_source_hashes"], str(Path(adapter.legacy.__file__).resolve()): adapter.LEGACY_SHA256,
        str(Path(reference.__file__).resolve()): adapter.REFERENCE_SHA256, source: common._sha256(Path(source))}
    binding = {"candidate_id": contract["candidate_id"], "arm": ARM_CANDIDATE, "candidate_source_path": source, "candidate_source_sha256": common._sha256(Path(source)),
        "candidate_contract_path": str(contract_path), "candidate_contract_sha256": common._sha256(contract_path), "adapter_contract_path": str(adapter.CONTRACT.resolve()),
        "adapter_contract_sha256": adapter.CONTRACT_SHA256, "adapter_source_sha256": common._sha256(Path(adapter.__file__)), "dependency_source_hashes": dependencies,
        "research_parent": actual_parent, "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"], "feature_names": ["market_logit"],
        "attribution": contract["attribution"], "callback_source_bindings": {name: source for name in ("prepare_features", "fit_predict", "replay_predictor")},
        "accepted_reference": {"reference": parent_spec, "acceptance_binding": {"path": str(acceptance_path), "sha256": common._sha256(acceptance_path)}}}
    return binding, parent


class EvidenceAdapterV2Tests(unittest.TestCase):
    def test_full195_matched_scoring_prediction_and_state_parity(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            root = Path(directory).resolve()
            source, rows, folds, frozen, controls = env
            binding, parent = fixture_binding(root, rows, folds, frozen, controls)
            expected, expected_reports = adapter.parent_module.fit_and_predict(rows, folds, controls, parent, fit_predict=c7.fit_temperature, arm=ARM_CANDIDATE)
            output = root / "new"
            with mock.patch.object(c7, "solve_temperature", wraps=c7.solve_temperature) as solve:
                manifest = adapter.run_recipe(source, output, binding, prepare, fit, replay, allow_test_paths=True)
            self.assertEqual(solve.call_count, 4)
            self.assertEqual(manifest["model_fits"], 4)
            expected_csv = root / "expected.csv"
            shared.write_predictions(expected_csv, expected, ARM_CANDIDATE)
            self.assertEqual(expected_csv.read_bytes(), (output / "predictions.csv").read_bytes())
            card = common.settlement._strict_json(output / "scorecard.json")
            self.assertEqual(card["aggregate"], shared.aggregate(expected, ARM_CANDIDATE))
            self.assertEqual(card["paired_grouped_evidence"], shared.paired_evidence(expected, ARM_CANDIDATE))
            decision = common.decision(shared.aggregate(expected, ARM_CANDIDATE), expected_reports, shared.paired_evidence(expected, ARM_CANDIDATE), ARM_CANDIDATE)
            self.assertEqual((card["scientific_decision"], card["operational_decision"], card["decision_conditions"]), decision)
            self.assertEqual(card["parent_reference"]["parent_refits"], 0)
            self.assertFalse(card["parent_reference"]["parameter_inheritance"])
            self.assertEqual(card["source_denominator"], {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2,
                "check_events": 87, "check_dates": 20, "check_game_weeks": len({row.game_week for row in rows if row.key in controls})})
            progress = common.settlement._strict_json(output / "fit_progress.json")
            self.assertEqual((progress["fit_calls_entered"], progress["fit_calls_completed"]), (4, 4))
            states = common.settlement._strict_json(output / "predictor_states.json")
            for saved, old in zip(states["folds"], expected_reports, strict=True):
                self.assertEqual(saved["state"], old["trainer"]["primitive_prediction_state"])
            for name in ("predictions", "scorecard", "fit_progress", "predictor_states", "input_receipts", "pre_score_lock", "exclusions"):
                suffix = "csv" if name == "predictions" else "json"
                self.assertEqual(manifest[name + "_sha256"], common._sha256(output / (name + "." + suffix)))

    def test_nonlinear_archived_parent_and_fixed_stage_completion(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            source, rows, folds, frozen, controls = env
            binding, _ = fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls,
                parent_id="SyntheticNonlinearArchivedParent-v1", requirements={"n_iter": 1})
            output = Path(directory) / "tree"
            manifest = adapter.run_recipe(source, output, binding, prepare, fit_tree, replay_tree, allow_test_paths=True)
            self.assertEqual(manifest["model_fits"], 4)
            progress = common.settlement._strict_json(output / "fit_progress.json")
            self.assertEqual(len(progress["completion_receipts"]), 4)
            self.assertNotIn("optimizer", common.settlement._strict_json(output / "predictor_states.json")["folds"][0]["state"])

    def test_invalid_parent_is_terminal_before_any_fit_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            source, rows, folds, frozen, controls = env
            binding, _ = fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls)
            binding["accepted_reference"]["acceptance_binding"]["sha256"] = "a" * 64
            output = Path(directory) / "failed"
            with mock.patch.object(c7, "solve_temperature") as solve, self.assertRaises(ValueError):
                adapter.run_recipe(source, output, binding, prepare, fit, replay, allow_test_paths=True)
            self.assertEqual(solve.call_count, 0)
            progress = common.settlement._strict_json(output / "fit_progress.json")
            self.assertEqual((progress["fit_calls_entered"], progress["fit_calls_completed"]), (0, 0))
            before = (output / "failure.json").read_bytes()
            with self.assertRaises(FileExistsError):
                adapter.run_recipe(source, output, binding, prepare, fit, replay, allow_test_paths=True)
            self.assertEqual(before, (output / "failure.json").read_bytes())
            self.assertFalse((output / "scorecard.json").exists())

    def test_entry_progress_is_saved_before_call_and_partial_failure_is_truthful(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            source, rows, folds, frozen, controls = env
            binding, _ = fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls)
            output = Path(directory) / "partial"
            calls = []
            def fail(fit_rows, check, context):
                progress = common.settlement._strict_json(output / "fit_progress.json")
                self.assertEqual(progress["fit_calls_entered"], len(calls) + 1)
                calls.append(1)
                if len(calls) == 2:
                    raise c7.FitFailure("synthetic second-fit failure", {"optimization_calls_started": 1, "optimization_calls_completed": 0})
                return fit(fit_rows, check, context)
            with self.assertRaisesRegex(c7.FitFailure, "second-fit"):
                adapter.run_recipe(source, output, binding, prepare, fail, replay, allow_test_paths=True)
            failure = common.settlement._strict_json(output / "failure.json")
            self.assertEqual((failure["fit_progress"]["fit_calls_entered"], failure["fit_progress"]["fit_calls_completed"]), (2, 1))
            self.assertEqual(failure["candidate_partial_receipt"]["optimization_calls_completed"], 0)
            self.assertEqual(len(calls), 2)
            self.assertFalse((output / "manifest.json").exists())

    def test_source_helper_callback_and_parent_comparator_drift(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            binding, _ = fixture_binding(Path(directory).resolve(), *env[1:])
            callbacks = dict(prepare_features=prepare, fit_predict=fit, replay_predictor=replay)
            self.assertEqual(adapter.validate_binding(binding, callbacks)["candidate_id"], binding["candidate_id"])
            for field in ("candidate_source_sha256", "candidate_contract_sha256", "adapter_source_sha256", "adapter_contract_sha256", "comparison_incumbent_sha256"):
                bad = copy.deepcopy(binding)
                bad[field] = "a" * 64
                with self.subTest(field=field), self.assertRaises(ValueError):
                    adapter.validate_binding(bad, callbacks)
            for mode in ("helper", "callback", "parent", "arm", "features"):
                bad = copy.deepcopy(binding)
                if mode == "helper":
                    bad["dependency_source_hashes"].pop(next(iter(bad["dependency_source_hashes"])))
                elif mode == "callback":
                    bad["callback_source_bindings"]["fit_predict"] = bad["adapter_contract_path"]
                elif mode == "parent":
                    bad["accepted_reference"]["reference"]["candidate_id"] = "different"
                elif mode == "arm":
                    bad["arm"] = shared.ARM_RAW
                else:
                    bad["feature_names"] = ["future_score"]
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    adapter.validate_binding(bad, callbacks)

    def test_receipt_primitive_state_probability_and_replay_denials(self):
        for mode in ("state", "fit_count", "boolfit", "completion", "probability", "bounding", "replay", "json"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
                source, rows, folds, frozen, controls = env
                binding, _ = fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls)
                def changed(fit_rows, check, context):
                    values, trainer = fit(fit_rows, check, context)
                    if mode == "state":
                        trainer["predictor_state_sha256"] = "a" * 64
                    elif mode == "fit_count":
                        trainer["model_fits"] = 2
                    elif mode == "boolfit":
                        trainer["model_fits"] = True
                    elif mode == "completion":
                        trainer["optimizer"]["converged"] = 1
                    elif mode == "probability":
                        values[0] = float("nan")
                    elif mode == "bounding":
                        trainer["bounding"]["clipped_rows"] = 99
                    elif mode == "json":
                        trainer["primitive_prediction_state"]["nonprimitive"] = object()
                    return values, trainer
                def changed_replay(state, check, context):
                    values, bounds = replay(state, check, context)
                    if mode == "replay":
                        values[0] += .001
                    return values, bounds
                output = Path(directory) / "invalid"
                with self.assertRaises((ValueError, TypeError)):
                    adapter.run_recipe(source, output, binding, prepare, changed, changed_replay, allow_test_paths=True)
                progress = common.settlement._strict_json(output / "fit_progress.json")
                self.assertEqual((progress["fit_calls_entered"], progress["fit_calls_completed"]), (1, 0))
                self.assertEqual(progress["fit_callbacks_returned"], 1)
                self.assertEqual(len(progress["returned_fit_receipts"]), 1)
                self.assertFalse((output / "scorecard.json").exists())

    def test_original_adapter_bytes_and_no_production_monkeypatch(self):
        self.assertEqual(common._sha256(Path(adapter.legacy.__file__)), adapter.LEGACY_SHA256)
        text = Path(adapter.__file__).read_text()
        self.assertNotIn("parent_state", text)
        self.assertNotIn("mock.patch", text)
        self.assertNotIn("pickle", text)

    def test_floating_acceptance_pin_and_completion_missing_are_prefit_rejected(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            source, rows, folds, frozen, controls = env
            binding, _ = fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls)
            callbacks = dict(prepare_features=prepare, fit_predict=fit, replay_predictor=replay)
            changed = copy.deepcopy(binding)
            changed["accepted_reference"]["acceptance_binding"]["sha256"] = "a" * 64
            with self.assertRaisesRegex(ValueError, "original Controller"):
                adapter.validate_binding(changed, callbacks)
            path = Path(binding["candidate_contract_path"])
            contract = common.settlement._strict_json(path)
            contract["fit_completion_requirements"] = {}
            path.unlink()
            common.base._atomic_json(path, contract)
            binding["candidate_contract_sha256"] = common._sha256(path)
            with self.assertRaisesRegex(ValueError, "completion receipt requirements"):
                adapter.validate_binding(binding, callbacks)

    def test_candidate_callbacks_cannot_mutate_rows_used_by_frozen_scorer(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            source, rows, folds, frozen, controls = env
            binding, _ = fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls)
            before = common._digest([row.trusted for row in rows])
            def changed_prepare(callback_rows, view, identity):
                for row in callback_rows:
                    row.trusted["synthetic_mutation"] = "candidate-only"
                return prepare(callback_rows, view, identity)
            def changed_fit(fit_rows, check, context):
                values, trainer = fit(fit_rows, check, context)
                for row in fit_rows + check:
                    row.trusted["synthetic_mutation"] = "candidate-only"
                return values, trainer
            def changed_replay(state, check, context):
                values, bounds = replay(state, check, context)
                for row in check:
                    row.trusted["synthetic_mutation"] = "candidate-only"
                return values, bounds
            manifest = adapter.run_recipe(source, Path(directory) / "copied", binding, changed_prepare, changed_fit, changed_replay, allow_test_paths=True)
            self.assertEqual(manifest["model_fits"], 4)
            self.assertEqual(before, common._digest([row.trusted for row in rows]))


if __name__ == "__main__":
    unittest.main()
