"""Portable full CLI/request-to-prediction checks; no resident Train access."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
import copy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from experiments import nfl_ingame_temperature_possession_pressure_entry as entry
from experiments import test_nfl_ingame_candidate_evidence_adapter as adapter_tests

d1, harness, common = entry.d1, entry.harness, entry.common
NOW = datetime(2026, 10, 5, 16, tzinfo=timezone.utc)

def numeric_parent(rows, folds):
    parents, states = {}, {}
    for fold in folds:
        check = sorted([row for row in rows if row.game_date in fold["check_dates"]], key=lambda row: row.key)
        fit = sorted([row for row in rows if row.game_date in fold["fit_dates"]], key=lambda row: row.key)
        raw = d1.parent.parent_module.raw_probabilities
        optimizer = {"beta": 0., "F": 1., "F_zero": 1., "gradient": 0., "hessian": 16., "KKT": 0.,
            "converged": True, "optimization_calls_started": 1, "optimization_calls_completed": 1}
        state = {"schema": "market_temperature_offset_numeric_state_v1", "feature_columns": ["market_logit"],
            "beta": 0., "temperature": 1., "alpha": 16., "intercept": 0, "normalization": "none",
            "sample_weights": None, "lower_bound": -1., "fit_events": len(fit),
            "raw_fit_sha256": common._digest(raw(fit).tolist()), "raw_check_sha256": common._digest(raw(check).tolist()),
            "fit_logit_sha256": common._digest([row.market_features[0] for row in fit]), "optimizer": optimizer}
        states[fold["fold"]] = state
        parents.update({row.key: row.trusted["market_probability"] for row in check})
    return parents, states

@contextmanager
def entry_fixture(directory):
    root = Path(directory)
    repo, pilot = root / "repo", root / "pilot"
    repo.mkdir()
    output = pilot / "runs/synthetic-d1"
    request_path = pilot / "worker/synthetic-d1.request.json"
    request_path.parent.mkdir(parents=True)
    real_repo = Path(entry.__file__).parents[3]
    envelope = common.settlement._strict_json(real_repo / entry.ENVELOPE)
    files = {}
    # Exact immutable source hashes are actually checked, not mocked away.
    paths = {str(Path(filename).relative_to(real_repo)): digest
        for filename, digest in harness.held_c7_binding()["dependency_source_hashes"].items()}
    for section in ("fixed_scientific_bindings", "fixed_harness_bindings"):
        for key, relative in envelope[section].items():
            if key.endswith("_path"):
                paths[relative] = common._sha256(real_repo / relative)
    paths.update({entry.ENVELOPE: entry.ENVELOPE_SHA256,
        "research/market_rsi/experiments/nfl_ingame_temperature_possession_pressure_entry.py": common._sha256(Path(entry.__file__)),
        "research/market_rsi/experiments/test_nfl_ingame_candidate_evidence_adapter.py": envelope["fixed_harness_bindings"]["adapter_test_sha256"]})
    gates = envelope["mandatory_live_review_gates"]
    paths[gates["source_review_path"]] = entry.SOURCE_REVIEW_SHA256
    for relative, digest in paths.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real_repo / relative, target)
        files[relative] = digest
    parity = {**gates["required_parity_fields"], "source_review_sha256": entry.SOURCE_REVIEW_SHA256}
    parity_path = repo / gates["live_parity_review_path"]
    common.base._atomic_json(parity_path, parity)
    files[gates["live_parity_review_path"]] = common._sha256(parity_path)
    memory = root / "synthetic-memory.json"
    common.base._atomic_json(memory, {"synthetic": True})
    request = {"attempt_id": output.name, "candidate_id": d1.TASK_ID, "module": entry.MODULE,
        "source_commit": "synthetic-reviewed-checkpoint", "files": files,
        "python": envelope["runtime"]["python"], "python_sha256": envelope["runtime"]["python_sha256"],
        "memory": str(memory), "memory_sha256": common._sha256(memory), "runtime_pair_sha256": "a" * 64,
        "spec_sha256": entry.ENVELOPE_SHA256, "max_fits": 4, "max_wall_seconds": 900}
    common.base._atomic_json(request_path, request)
    with adapter_tests.synthetic_environment(root) as fixture, ExitStack() as stack:
        source, rows, folds, frozen, controls = fixture
        for index, anchor in enumerate(frozen["anchors"]):
            anchor.update(possession_is_home=index % 2, down=index % 4 + 1,
                yards_to_go=index % 11, yards_to_opponent_goal=index % 101)
        parent, states = numeric_parent(rows, folds)
        stack.enter_context(mock.patch.object(harness, "load_parent", return_value=(parent, states)))
        stack.enter_context(mock.patch.object(entry, "REPO", repo))
        stack.enter_context(mock.patch.object(entry, "utc_now", return_value=NOW))
        stack.enter_context(mock.patch.object(entry.worker, "TRAIN", source))
        # Only current-Git query is synthetic; worker.validate checks every real fixture byte.
        stack.enter_context(mock.patch.object(entry.worker.subprocess, "check_output", return_value="synthetic-reviewed-checkpoint\n"))
        yield {"source": source, "output": output, "request": request, "request_path": request_path,
            "repo": repo, "envelope": envelope, "rows": rows, "states": states}

class TemperaturePressureEntryTests(unittest.TestCase):
    def test_exact_CLI_arguments_full195_four_fits87_and_saved_replay(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, \
                mock.patch.object(d1, "solve_joint", wraps=d1.solve_joint) as solve, \
                mock.patch.object(entry.worker, "validate", wraps=entry.worker.validate) as validate, \
                mock.patch("sys.argv", [entry.MODULE, "--source-root", str(f["source"]), "--output", str(f["output"])]), \
                mock.patch("builtins.print") as stdout:
            entry.main()
            self.assertEqual(solve.call_count, 4)
            self.assertEqual(validate.call_count, 1)
            self.assertTrue(stdout.called)
            manifest = common.settlement._strict_json(f["output"] / "manifest.json")
            card = common.settlement._strict_json(f["output"] / "scorecard.json")
            states = common.settlement._strict_json(f["output"] / "predictor_states.json")
            self.assertEqual((manifest["source_events"], manifest["materialized_events"], manifest["excluded_events"], manifest["check_events"], manifest["model_fits"]), (195, 193, 2, 87, 4))
            self.assertEqual(card["actual_research_parent_id"], d1.parent.TASK_ID)
            self.assertEqual(len(card["aggregate"]), 5)
            self.assertEqual([report["fit_events"] for report in card["folds"]], [106, 132, 148, 176])
            self.assertEqual([report["check_events"] for report in card["folds"]], [26, 16, 28, 17])
            self.assertEqual(len(card["per_schedule_date_correction_diagnostics"]), 20)
            self.assertEqual(card["parent_replay"]["parent_refits"], 0)
            for report in card["folds"]:
                self.assertEqual(report["trainer"]["model_fits"], 1)
                self.assertEqual(len(report["fit_label_unavailable_game_ids"]), 0)
            features, _ = d1.prepare_features(f["rows"], {"anchors": [{"game_id": row.game_id,
                "possession_is_home": i % 2, "down": i % 4 + 1, "yards_to_go": i % 11,
                "yards_to_opponent_goal": i % 101} for i, row in enumerate(f["rows"])]}, f["states"])
            csv = common.frozen_v0._read_csv(f["output"] / "predictions.csv")
            with mock.patch.object(d1, "solve_joint", side_effect=AssertionError("no refits")):
                for item, report in zip(states["folds"], card["folds"], strict=True):
                    check = sorted([row for row in f["rows"] if row.game_date in report["check_dates"]], key=lambda row: row.key)
                    context = {**features, "fold_id": item["fold"], "parent_state": f["states"][item["fold"]]}
                    values, _ = d1.replay_predictor(item["state"], check, context)
                    self.assertEqual(values, [float(row["candidate_probability"]) for row in csv if int(row["fold"]) == item["fold"]])
            paired = card["paired_grouped_evidence"]
            self.assertEqual((card["scientific_decision"], card["operational_decision"], card["decision_conditions"]),
                common.decision(card["aggregate"], card["folds"], paired, d1.ARM_CANDIDATE))
            before = (f["output"] / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):
                entry.run(f["source"], f["output"])
            self.assertEqual(before, (f["output"] / "manifest.json").read_bytes())

    def test_binding_uses_unchanged_direct_science_callbacks_A2_and_parent(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            binding = entry.require_admission(f["source"], f["output"])
            self.assertEqual(binding["candidate_source_sha256"], "c57ed002b507e219c788c256b33e0f853fc418ea41713fbfbc845bcb7782d838")
            self.assertEqual(binding["candidate_contract_sha256"], d1.CONTRACT_SHA256)
            self.assertEqual(binding["research_parent"], common.settlement._strict_json(d1.CONTRACT)["research_parent"])
            self.assertEqual(binding["dependency_source_hashes"][str(Path(d1.pressure.__file__).resolve())], "4ea2935fb896397b4d21125bb040a0f82ff82be01abd2779717378d3465a0ab3")
            self.assertTrue(all(path == str(Path(d1.__file__).resolve()) for path in binding["callback_source_bindings"].values()))

    def test_expired_or_not_started_authority_rejects_before_data_or_fit(self):
        for now in (datetime(2026, 10, 5, 12, tzinfo=timezone.utc), datetime(2026, 10, 5, 19, 27, 11, tzinfo=timezone.utc)):
            with self.subTest(now=now), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, \
                    mock.patch.object(entry, "utc_now", return_value=now), \
                    mock.patch.object(harness, "run_recipe") as run, self.assertRaisesRegex(ValueError, "authority"):
                entry.run(f["source"], f["output"])
            self.assertEqual(run.call_count, 0)

    def test_request_spec_runtime_and_identity_drift_reject_prefit(self):
        mutations = {"attempt_id": "other", "candidate_id": "other", "module": "experiments.nfl_ingame_other",
            "spec_sha256": "0" * 64, "source_commit": "changed", "max_fits": 3, "max_wall_seconds": 901,
            "python_sha256": "0" * 64, "python": "/not-authorized/python"}
        for key, value in mutations.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, \
                    mock.patch.object(d1, "solve_joint") as solve:
                f["request"][key] = value
                common.base._atomic_json(f["request_path"], f["request"])
                with self.assertRaises(ValueError):
                    entry.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)
                failure = common.settlement._strict_json(f["output"] / "failure.json")
                self.assertEqual((failure["phase"], failure["model_fits"]), ("entry_admission", 0))

    def test_source_envelope_core_A2_ownentry_and_missing_review_drift(self):
        paths = [entry.ENVELOPE, "research/market_rsi/experiments/nfl_ingame_temperature_possession_pressure_entry.py",
            "research/market_rsi/experiments/nfl_ingame_temperature_possession_pressure_joint_offset.py",
            "research/market_rsi/experiments/nfl_ingame_causal_possession_pressure_offset.py",
            "research/market_rsi/minimal_prediction_loop/proper_scoring.py",
            "research/market_rsi/supervisor_harness/COEVO_H1_SOURCE_REVIEW_V3_2026-10-05.json",
            "research/market_rsi/supervisor_harness/COEVO_H1_LIVE_PARITY_REVIEW_2026-10-05.json"]
        for relative in paths:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, \
                    mock.patch.object(d1, "solve_joint") as solve:
                f["request"]["files"][relative] = "0" * 64
                common.base._atomic_json(f["request_path"], f["request"])
                with self.assertRaises(ValueError):
                    entry.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            (f["repo"] / entry.ENVELOPE).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "envelope"):
                entry.run(f["source"], f["output"])

    def test_failed_or_malformed_parity_fields_cannot_be_self_reported_PASS(self):
        for key, value in (("verdict", "FAIL"), ("predictions_exact", False), ("predictor_states_exact", 1),
                ("source_review_sha256", "0" * 64), ("fit_calls_completed", 3), ("control_refits", 1),
                ("source_K_C_worker_unchanged", False)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
                relative = f["envelope"]["mandatory_live_review_gates"]["live_parity_review_path"]
                path = f["repo"] / relative
                receipt = common.settlement._strict_json(path)
                receipt[key] = value
                common.base._atomic_json(path, receipt)
                f["request"]["files"][relative] = common._sha256(path)
                common.base._atomic_json(f["request_path"], f["request"])
                with self.assertRaisesRegex(ValueError, "parity"):
                    entry.run(f["source"], f["output"])

    def test_failed_source_review_predicates_are_independent_of_hash_integrity(self):
        for key, value in (("passed", False), ("source_sha256", "0" * 64), ("verdict", "PROPOSAL_ONLY")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
                gates = f["envelope"]["mandatory_live_review_gates"]
                path = f["repo"] / gates["source_review_path"]
                receipt = common.settlement._strict_json(path)
                receipt[key] = value
                common.base._atomic_json(path, receipt)
                changed_hash = common._sha256(path)
                f["request"]["files"][gates["source_review_path"]] = changed_hash
                common.base._atomic_json(f["request_path"], f["request"])
                # Synthetic admitted hash deliberately updated to exercise payload predicates.
                # Production constant stays immutable13913664; it never accepts this fixture.
                with mock.patch.object(entry, "SOURCE_REVIEW_SHA256", changed_hash), self.assertRaisesRegex(ValueError, "source is not"):
                    entry.run(f["source"], f["output"])

    def test_missing_malformed_or_symlinked_request_refuses_before_fit(self):
        for mode in ("missing", "malformed", "symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, \
                    mock.patch.object(d1, "solve_joint") as solve:
                path = f["request_path"]
                if mode == "missing":
                    path.unlink()
                elif mode == "malformed":
                    common.base._atomic_json(path, {})
                else:
                    moved = path.with_suffix(".original")
                    path.rename(moved)
                    path.symlink_to(moved)
                with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
                    entry.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)
                self.assertEqual(common.settlement._strict_json(f["output"] / "failure.json")["model_fits"], 0)

    def test_partial_fit_and_postprediction_failure_keep_H_truth(self):
        for mode in ("fit", "output"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
                if mode == "fit":
                    receipt = {"converged": False, "optimization_calls_started": 1, "optimization_calls_completed": 0}
                    patch = mock.patch.object(d1, "solve_joint", side_effect=d1.FitFailure("synthetic fit failure", receipt))
                else:
                    patch = mock.patch.object(d1, "probabilities", side_effect=ValueError("synthetic output failure"))
                with patch, self.assertRaises(d1.FitFailure):
                    entry.run(f["source"], f["output"])
                failure = common.settlement._strict_json(f["output"] / "failure.json")
                self.assertEqual((failure["fit_progress"]["fit_calls_entered"], failure["fit_progress"]["fit_calls_completed"]), (1, 0))
                self.assertEqual(failure["optimizer_partial_receipt"]["optimization_calls_completed"], int(mode == "output"))
                self.assertFalse((f["output"] / "scorecard.json").exists())

if __name__ == "__main__":
    unittest.main()
