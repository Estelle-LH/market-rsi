"""Portable H1 matches; all training fixtures and parent artifacts are synthetic."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from experiments import nfl_ingame_candidate_evidence_adapter as adapter
from experiments import test_nfl_ingame_market_temperature_offset as c7_tests

c7, common, shared = adapter.c7, adapter.common, adapter.shared

@contextmanager
def synthetic_environment(directory):
    rows, folds = c7_tests.expanded_problem()
    by_game = {row.game_id: row for row in rows}
    cohort = [{"game_id": row.game_id, "game_date": row.game_date} for row in rows]
    cohort += [{"game_id": game, "game_date": rows[-1].game_date, "exclusion": code}
        for game, code in common.identity.EXPECTED_EXCLUSIONS]
    controls, availability = {}, []
    for fold in folds:
        for row in rows:
            if row.game_date in fold["check_dates"]:
                p = row.trusted["market_probability"]
                controls[row.key] = {"fold": fold["fold"], "game_id": row.game_id, "game_date": row.game_date,
                    "game_week": row.game_week, "outcome": row.trusted["outcome"], shared.ARM_RAW: p,
                    shared.ARM_ORDINARY: p + .01, shared.ARM_PARENT: p - .01}
                availability.append({**row.trusted, "game_id": row.game_id, "game_date": row.game_date,
                    "game_week": row.game_week, "fold": fold["fold"]})
    checks = [row for fold in folds for row in sorted([r for r in rows if r.game_date in fold["check_dates"]], key=lambda r: r.key)]
    frozen = {"hashes": {}, "folds": folds, "anchors": [{"game_id": item["game_id"]} for item in cohort],
        "predictions": availability, "receipts": {"pbp_receipts": [], "materialized_receipts": [r.source_receipt for r in rows]}}
    parent, states = c7_tests.synthetic_parent(rows, folds)
    source = Path(directory) / "source"
    source.mkdir(exist_ok=True)
    for name in ("manifest.json", "cohort.csv"):
        common.base._atomic_json(source / name, {"synthetic": True})
    def materialize(root, item, anchor):
        if "exclusion" in item:
            raise common.settlement.EventExclusion(item["exclusion"], "synthetic frozen exclusion")
        return by_game[item["game_id"]]
    with ExitStack() as stack:
        for owner, name, kwargs in (
            (common.base, "_validate_roots", {"return_value": None}),
            (common.frozen_v0, "_validate_v0_artifact", {"return_value": frozen}),
            (common.identity, "_frozen_controls", {"return_value": controls}),
            (common.base, "_validate_source", {"return_value": cohort}),
            (common.base, "_validate_pbp_receipts", {"return_value": []}),
            (common.base, "_load_dynamic_market", {"side_effect": materialize}),
            (adapter, "load_parent", {"return_value": (parent, states)}),
            (c7, "load_parent", {"return_value": (parent, states)}),
            (common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", {"new": common._digest([list(row.key) for row in checks])})):
            stack.enter_context(mock.patch.object(owner, name, **kwargs))
        yield source, rows, folds, frozen, controls

def run_held(source, output):
    return adapter.run_recipe(source, output, adapter.held_c7_binding(), adapter.prepare_c7, c7.fit_temperature,
        adapter.replay_c7, allow_test_paths=True)

class CandidateEvidenceAdapterTests(unittest.TestCase):
    def test_binding_hash_dependency_callback_and_metadata_drift(self):
        callbacks = dict(prepare_features=adapter.prepare_c7, fit_predict=c7.fit_temperature, replay_predictor=adapter.replay_c7)
        binding = adapter.held_c7_binding()
        self.assertEqual(adapter.validate_binding(binding, callbacks)["candidate_id"], c7.TASK_ID)
        for field in ("candidate_source_sha256", "candidate_contract_sha256", "adapter_source_sha256", "adapter_contract_sha256"):
            bad = copy.deepcopy(binding)
            bad[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                adapter.validate_binding(bad, callbacks)
        for field, value in (("candidate_id", "other"), ("arm", shared.ARM_RAW), ("attribution", "R success"),
                ("feature_names", ["future"]), ("comparison_incumbent_sha256", "0" * 64)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                adapter.validate_binding({**binding, field: value}, callbacks)
        for mode in ("missing", "conflict", "callback", "parent"):
            bad = copy.deepcopy(binding)
            if mode == "missing":
                bad["dependency_source_hashes"].pop(next(iter(bad["dependency_source_hashes"])))
            elif mode == "conflict":
                bad["dependency_source_hashes"][bad["candidate_source_path"]] = "0" * 64
            elif mode == "callback":
                bad["callback_source_bindings"]["fit_predict"] = bad["adapter_contract_path"]
            else:
                bad["research_parent"]["state_sha256_by_fold"][0] = "0" * 64
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                adapter.validate_binding(bad, callbacks)

    def test_full195_matched_original_C7_exact_states_scores_intervals_and_replay(self):
        with tempfile.TemporaryDirectory() as directory, synthetic_environment(directory) as fixture:
            source, rows, _, _, _ = fixture
            old_output, new_output = Path(directory) / "old", Path(directory) / "new"
            old = c7.run(source, old_output, allow_test_paths=True)
            with mock.patch.object(c7, "solve_temperature", wraps=c7.solve_temperature) as solve:
                new = run_held(source, new_output)
            self.assertEqual(solve.call_count, 4)
            self.assertEqual(new["model_fits"], 4)
            self.assertEqual((old_output / "predictions.csv").read_bytes(), (new_output / "predictions.csv").read_bytes())
            self.assertEqual((old_output / "predictor_states.json").read_bytes(), (new_output / "predictor_states.json").read_bytes())
            old_card, new_card = [common.settlement._strict_json(path / "scorecard.json") for path in (old_output, new_output)]
            for key in old_card:
                self.assertEqual(old_card[key], new_card[key], key)
            self.assertEqual(len(new_card["per_schedule_date_correction_diagnostics"]), 20)
            saved = common.settlement._strict_json(new_output / "predictor_states.json")
            with mock.patch.object(c7, "solve_temperature", side_effect=AssertionError("replay must not fit")):
                for item in saved["folds"]:
                    check = [row for row in rows if row.game_date in new_card["folds"][item["fold"] - 1]["check_dates"]]
                    values, _ = adapter.replay_c7(item["state"], sorted(check, key=lambda row: row.key), {})
                    self.assertEqual(len(values), adapter.CHECK_COUNTS[item["fold"] - 1])
            for name, suffix in (("input_receipts", "json"), ("scorecard", "json"), ("predictions", "csv"), ("predictor_states", "json"), ("fit_progress", "json")):
                self.assertEqual(new[f"{name}_sha256"], common._sha256(new_output / f"{name}.{suffix}"))

    def test_prefit_source_failure_receipt_no_fit_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            bad = adapter.held_c7_binding()
            bad["adapter_source_sha256"] = "0" * 64
            with mock.patch.object(common.base, "_validate_roots"), mock.patch.object(c7, "solve_temperature") as solve:
                with self.assertRaises(ValueError):
                    adapter.run_recipe(directory, output, bad, adapter.prepare_c7, c7.fit_temperature, adapter.replay_c7, allow_test_paths=True)
                self.assertEqual(solve.call_count, 0)
                failure = common.settlement._strict_json(output / "failure.json")
                self.assertEqual(failure["fit_progress"]["fit_calls_entered"], 0)
                before = (output / "failure.json").read_bytes()
                with self.assertRaises(FileExistsError):
                    run_held(directory, output)
                self.assertEqual(before, (output / "failure.json").read_bytes())

    def test_partial_second_fit_failure_truth_no_retry_preserved_first_receipt(self):
        partial = {"converged": False, "optimization_calls_started": 1, "optimization_calls_completed": 0, "evaluations": 1}
        original = c7.solve_temperature
        calls = []
        def solve(logits, outcomes):
            calls.append(1)
            if len(calls) == 2:
                raise c7.FitFailure("synthetic second-fold stop", partial)
            return original(logits, outcomes)
        with tempfile.TemporaryDirectory() as directory, synthetic_environment(directory) as fixture:
            output = Path(directory) / "partial"
            with mock.patch.object(c7, "solve_temperature", side_effect=solve), self.assertRaisesRegex(c7.FitFailure, "second-fold"):
                run_held(fixture[0], output)
            failure = common.settlement._strict_json(output / "failure.json")
            self.assertEqual(len(calls), 2)
            self.assertEqual((failure["fit_progress"]["fit_calls_entered"], failure["fit_progress"]["fit_calls_completed"]), (2, 1))
            self.assertEqual(failure["optimizer_partial_receipt"], partial)
            self.assertTrue(failure["fit_progress"]["optimizer_receipts"][0]["converged"])
            self.assertFalse((output / "scorecard.json").exists())
            self.assertFalse((output / "manifest.json").exists())

    def test_postoptimization_prediction_failure_keeps_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory, synthetic_environment(directory) as fixture:
            output = Path(directory) / "output-failure"
            with mock.patch.object(c7, "probabilities", side_effect=ValueError("synthetic output failure")), self.assertRaisesRegex(c7.FitFailure, "output failure"):
                run_held(fixture[0], output)
            failure = common.settlement._strict_json(output / "failure.json")
            self.assertEqual((failure["fit_progress"]["fit_calls_entered"], failure["fit_progress"]["fit_calls_completed"]), (1, 0))
            self.assertTrue(failure["optimizer_partial_receipt"]["converged"])
            self.assertEqual(failure["optimizer_partial_receipt"]["optimization_calls_completed"], 1)

    def test_returned_state_or_prediction_drift_is_terminal_with_completed_optimizer(self):
        original = c7.fit_temperature
        for mode in ("state", "probability", "nonfinite", "bounding", "fitcount", "boolfit", "fit_events", "notconverged"):
            def fit(fit_rows, check_rows, features):
                values, trainer = original(fit_rows, check_rows, features)
                if mode == "state":
                    trainer["predictor_state_sha256"] = "0" * 64
                elif mode == "probability":
                    values[0] += .001
                elif mode == "nonfinite":
                    values[0] = float("nan")
                elif mode == "bounding":
                    trainer["bounding"]["clipped_rows"] += 1
                elif mode == "boolfit":
                    trainer["model_fits"] = True
                elif mode == "fit_events":
                    trainer["primitive_prediction_state"]["fit_events"] -= 1
                    trainer["predictor_state_sha256"] = common._digest(trainer["primitive_prediction_state"])
                elif mode == "notconverged":
                    trainer["optimizer"]["converged"] = False
                else:
                    trainer["model_fits"] = 2
                return values, trainer
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, synthetic_environment(directory) as fixture:
                output = Path(directory) / "drift"
                contract = common.settlement._strict_json(c7.CONTRACT)
                with mock.patch.object(adapter, "validate_binding", return_value=contract), self.assertRaises(ValueError):
                    adapter.run_recipe(fixture[0], output, adapter.held_c7_binding(), adapter.prepare_c7, fit, adapter.replay_c7, allow_test_paths=True)
                failure = common.settlement._strict_json(output / "failure.json")
                self.assertEqual(failure["optimizer_partial_receipt"]["converged"], mode != "notconverged")
                self.assertEqual((failure["fit_progress"]["fit_calls_entered"], failure["fit_progress"]["fit_calls_completed"]), (1, 0))
                self.assertFalse((output / "scorecard.json").exists())

    def test_copied_exact_fold_context_parent_isolation_and_prefit_count_guard(self):
        contexts = []
        original = c7.fit_temperature
        feature_input = {"sentinel": {"value": 1}}
        def fit(fit_rows, check_rows, context):
            contexts.append(copy.deepcopy(context))
            context["sentinel"]["value"] = -1
            context["parent_state"]["X_thresholds_"][0] = -1
            return original(fit_rows, check_rows)
        def prepare(rows, frozen, parent_states):
            return feature_input, {"synthetic": True}
        with tempfile.TemporaryDirectory() as directory, synthetic_environment(directory) as fixture:
            contract = common.settlement._strict_json(c7.CONTRACT)
            with mock.patch.object(adapter, "validate_binding", return_value=contract):
                adapter.run_recipe(fixture[0], Path(directory) / "context", adapter.held_c7_binding(), prepare, fit, adapter.replay_c7, allow_test_paths=True)
            self.assertEqual([item["fold_id"] for item in contexts], [1, 2, 3, 4])
            self.assertEqual([item["parent_state"]["fit_events"] for item in contexts], list(adapter.FIT_COUNTS))
            self.assertTrue(all(item["sentinel"]["value"] == 1 for item in contexts))
            self.assertTrue(all(item["parent_state"]["X_thresholds_"][0] == .2 for item in contexts))
            self.assertEqual(feature_input, {"sentinel": {"value": 1}})
            with mock.patch.object(adapter, "FIT_COUNTS", (105, 132, 148, 176)), mock.patch.object(c7, "solve_temperature") as solve, self.assertRaises(ValueError):
                run_held(fixture[0], Path(directory) / "bad-count")
            self.assertEqual(solve.call_count, 0)
            failure = common.settlement._strict_json(Path(directory) / "bad-count/failure.json")
            self.assertEqual(failure["fit_progress"]["fit_calls_entered"], 0)

    def test_parent_C1_portable_seven_receipts_four_states_and_no_refit(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe, controls, frozen, key_hash = c7_tests.synthetic_parent_artifacts(Path(directory))
            with mock.patch.object(common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", key_hash), \
                    mock.patch.object(parent_module := adapter.parent_module, "fit_isotonic", side_effect=AssertionError("no parent fits")):
                parent, states = adapter.load_parent(recipe, controls, frozen)
                self.assertEqual((len(parent), len(states)), (87, 4))
                bad = copy.deepcopy(recipe)
                bad["research_parent"]["artifact_hashes"]["pre_score_lock.json"] = "0" * 64
                with self.assertRaises(ValueError):
                    adapter.load_parent(bad, controls, frozen)

    def test_C7_eight_receipts_historical_replay_and_drift(self):
        real_loader = adapter.load_parent
        with tempfile.TemporaryDirectory() as directory, synthetic_environment(directory) as fixture:
            source, rows, folds, frozen, controls = fixture
            output = Path(directory) / "synthetic-history"
            run_held(source, output)
            artifact = common.settlement._strict_json(output / "predictor_states.json")
            hashes = {path.name: common._sha256(path) for path in output.iterdir()}
            evidence = {"candidate_id": c7.TASK_ID, "runner_sha256": adapter.C7_SHA256,
                "controller_contract_sha256": c7.CONTRACT_SHA256, "artifact_root": str(output), "artifact_hashes": hashes,
                "state_schema": "market_temperature_offset_numeric_state_v1",
                "state_sha256_by_fold": [item["state_sha256"] for item in artifact["folds"]],
                "beta_by_fold": [item["state"]["beta"] for item in artifact["folds"]]}
            with mock.patch.object(c7, "solve_temperature", side_effect=AssertionError("no historical parent fits")):
                parent, states = real_loader({"research_parent": evidence}, controls, frozen)
                self.assertEqual(adapter.replay_parent(rows, folds, parent, states, c7.TASK_ID)["parent_rows_replayed"], 87)
                for name in hashes:
                    bad = copy.deepcopy(evidence)
                    bad["artifact_hashes"][name] = "0" * 64
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        real_loader({"research_parent": bad}, controls, frozen)
                for mode in ("state", "probability", "fitlogits", "missing"):
                    bad_states, bad_parent = copy.deepcopy(states), dict(parent)
                    if mode == "state":
                        bad_states[1]["optimizer"]["KKT"] = float("nan")
                    elif mode == "probability":
                        bad_parent[next(iter(bad_parent))] += .01
                    elif mode == "fitlogits":
                        bad_states[1]["fit_logit_sha256"] = "0" * 64
                    else:
                        bad_states.pop(1)
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        adapter.replay_parent(rows, folds, bad_parent, bad_states, c7.TASK_ID)

    def test_cli_is_fixed_held_C7(self):
        with mock.patch("sys.argv", ["adapter", "--source-root", "/synthetic", "--output", "/synthetic-output"]), \
                mock.patch.object(adapter, "run_recipe", return_value={}) as run, mock.patch("builtins.print"):
            adapter.main()
        self.assertIs(run.call_args.args[4], c7.fit_temperature)
        self.assertEqual(run.call_args.args[2]["candidate_id"], c7.TASK_ID)

if __name__ == "__main__":
    unittest.main()
