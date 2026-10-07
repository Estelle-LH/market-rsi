"""Versioned comparison-only accepted-parent entry; protected judge unchanged."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import inspect
from pathlib import Path
import platform
from experiments import nfl_ingame_candidate_evidence_adapter as legacy
from experiments import nfl_ingame_prediction_reference as reference

common, shared, parent_module, c7 = legacy.common, legacy.shared, legacy.parent_module, legacy.c7
CONTRACT = Path(__file__).parents[1] / "supervisor_harness/PRIORITY_PARENT_ENTRY_CONTRACT_2026-10-06-v1.json"
CONTRACT_SHA256 = "1fc96e5eb9277aeb4d1da8d32d9b87aa3eb4c6c6a65aa5e6c120bb666b0ef916"
REFERENCE_SHA256 = "664b9566ad61c7c4e60e1aeeea0602482a37e8a2ab6db2d2cd319ea56d89b19d"
LEGACY_SHA256 = "f62a5459a8e3c78bcdd7810e25291d1ef164ccc2d41f876fa37fb166f9dcc8bc"


def validate_binding(binding, callbacks):
    reference._exact(callbacks, {"prepare_features", "fit_predict", "replay_predictor"}, "callbacks")
    dependencies = {**legacy.held_c7_binding()["dependency_source_hashes"],
        str(Path(legacy.__file__).resolve()): LEGACY_SHA256, str(Path(reference.__file__).resolve()): REFERENCE_SHA256}
    if any(binding["dependency_source_hashes"].get(path) != value for path, value in dependencies.items()):
        raise ValueError("immutable helper coverage changed")
    sources = {binding["candidate_source_path"]: binding["candidate_source_sha256"],
        binding["candidate_contract_path"]: binding["candidate_contract_sha256"],
        binding["adapter_contract_path"]: binding["adapter_contract_sha256"], str(Path(__file__).resolve()): binding["adapter_source_sha256"]}
    if binding["adapter_contract_path"] != str(CONTRACT.resolve()) or binding["adapter_contract_sha256"] != CONTRACT_SHA256:
        raise ValueError("v2 entry contract changed")
    for path, value in binding["dependency_source_hashes"].items():
        if path in sources and sources[path] != value:
            raise ValueError("conflicting dependency/source binding")
        sources[path] = value
    for path, value in sources.items():
        reference._read({"path": path, "sha256": value})
    for name, callback in callbacks.items():
        path = str(Path(inspect.getsourcefile(callback)).resolve())
        if binding["callback_source_bindings"][name] != path or path not in sources:
            raise ValueError("callback source not independently admitted")
    c7.require_dependencies()
    contract = reference._json(reference._read({"path": binding["candidate_contract_path"], "sha256": binding["candidate_contract_sha256"]}))
    names = contract.get("fixed_predictive_information", contract.get("predictive_information", {}))["feature_names"]
    incumbent = contract.get("comparison_incumbent_sha256", contract.get("comparison_incumbent", {}).get("sha256"))
    attribution = contract.get("attribution", contract.get("changed_training_recipe", {}).get("attribution"))
    if (contract["candidate_id"] != binding["candidate_id"] or contract["research_parent"] != binding["research_parent"]
            or names != binding["feature_names"] or incumbent != binding["comparison_incumbent_sha256"]
            or attribution != binding["attribution"] or binding["arm"] != callbacks["fit_predict"].__globals__.get("ARM_CANDIDATE")
            or binding["arm"] in {shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT, shared.ARM_RESEARCH_PARENT}
            or contract["accepted_reference"] != binding["accepted_reference"]):
        raise ValueError("original Controller recipe/parent/comparator changed")
    parent = binding["accepted_reference"]["reference"]
    if parent["candidate_id"] != contract["research_parent"]["candidate_id"] or parent["runner"]["sha256"] != contract["research_parent"]["runner_sha256"]:
        raise ValueError("accepted comparison differs from actual research parent")
    requirements = contract["fit_completion_requirements"]
    if not isinstance(requirements, dict) or not requirements or any(not isinstance(path, str) or not path or any(not part for part in path.split(".")) for path in requirements):
        raise ValueError("candidate-specific completion receipt requirements missing")
    reference.digest(requirements)
    return contract


def _complete(trainer, state, fit, requirements):
    if (type(trainer["model_fits"]) is not int or trainer["model_fits"] != 1
            or not isinstance(state, dict) or not isinstance(state.get("schema"), str)
            or type(state.get("fit_events")) is not int or state["fit_events"] != len(fit)
            or reference.digest(state) != trainer["predictor_state_sha256"]
            or common.settlement.json.loads(common.settlement.json.dumps(state, allow_nan=False)) != state):
        raise ValueError("one-fit primitive state/receipt changed")
    for path, expected in requirements.items():
        observed = trainer
        for part in path.split("."):
            if not isinstance(observed, dict) or part not in observed:
                raise ValueError("completion receipt field missing")
            observed = observed[part]
        if type(observed) is not type(expected) or observed != expected:
            raise ValueError("candidate-specific fit completion failed")


def run_recipe(source_root, output, binding, prepare_features, fit_predict, replay_predictor, *, allow_test_paths=False):
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    progress = {"fit_calls_entered": 0, "fit_calls_completed": 0, "fit_callbacks_returned": 0, "returned_fit_receipts": [], "completion_receipts": [],
        "entry_semantics": "statistical fit callback entry persisted before call; completion after exact state/prediction replay"}
    candidate = binding.get("candidate_id", "UNKNOWN") if isinstance(binding, dict) else "UNKNOWN"
    try:
        common.base._atomic_json(output / "fit_progress.json", progress)
        contract = validate_binding(binding, dict(prepare_features=prepare_features, fit_predict=fit_predict, replay_predictor=replay_predictor))
        arm = binding["arm"]
        frozen = copy.deepcopy(common.frozen_v0._validate_v0_artifact(shared.V0_ARTIFACT_ROOT))
        frozen["exclusion_codes"] = dict(common.identity.EXPECTED_EXCLUSIONS)
        controls = common.identity._frozen_controls(frozen)
        accepted = binding["accepted_reference"]
        parent, parent_receipt = reference.load_reference(accepted["reference"], controls, frozen, accepted["acceptance_binding"])
        cohort = common.base._validate_source(source_root, expected_events=195, expected_dates=42, allow_test_paths=allow_test_paths)
        pbp = common.base._validate_pbp_receipts(source_root, cohort)
        if pbp != frozen["receipts"]["pbp_receipts"]:
            raise ValueError("frozen PBP receipts changed")
        anchors, rows, exclusions = {item["game_id"]: item for item in frozen["anchors"]}, [], []
        for ordinal, item in enumerate(cohort):
            try:
                rows.append(common.base._load_dynamic_market(source_root, item, anchors[item["game_id"]]))
            except common.settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"], "game_date": item["game_date"], "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        receipts, raw = [row.source_receipt for row in rows], parent_module.raw_probabilities(rows)
        if len(rows) != 193 or len(exclusions) != 2 or [(item["game_id"], item["reason"]) for item in exclusions] != common.identity.EXPECTED_EXCLUSIONS or common._digest(receipts) != common._digest(frozen["receipts"]["materialized_receipts"]):
            raise ValueError("full195/193+2 causal denominator changed")
        identity = {"candidate_id": accepted["reference"]["candidate_id"], "runner_sha256": accepted["reference"]["runner"]["sha256"],
            "reference_sha256": parent_receipt["reference_sha256"], "provenance": parent_receipt["provenance"], "comparison_only": True}
        features, feature_receipts = prepare_features(copy.deepcopy(rows), copy.deepcopy(frozen), copy.deepcopy(identity))
        common.base._atomic_json(output / "input_receipts.json", {"task_id": candidate, "controller_contract_sha256": binding["candidate_contract_sha256"], "runner_sha256": binding["candidate_source_sha256"], "harness_binding": binding, "dependency_source_hashes": binding["dependency_source_hashes"], "parent_reference": parent_receipt, "feature_receipts": feature_receipts, "raw_materialized_sha256": common._digest(raw.tolist()), "native_rows_validated": len(rows), "runtime_versions": {"python": platform.python_version(), "numpy": c7.np.__version__, "scipy": parent_module.scipy.__version__, "sklearn": shared.sklearn.__version__}, "v0_artifact_hashes": frozen["hashes"], "pbp_receipts": pbp, "materialized_receipts": receipts, "source_manifest_sha256": common._sha256(source_root / "manifest.json"), "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": candidate, "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": binding["candidate_contract_sha256"], "scientific_recipe": contract, "harness_binding": binding, "folds": frozen["folds"], "fit_budget": 4, "automatic_retries": 0, "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193, "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        def tracked_fit(fit, check, unused):
            ordinal = progress["fit_calls_entered"]
            if ordinal >= 4 or len(fit) != legacy.FIT_COUNTS[ordinal] or len(check) != legacy.CHECK_COUNTS[ordinal] or any(row.trusted["outcome_available_ms"] >= min(item.trusted["cutoff_ms"] for item in check) for row in fit):
                raise ValueError("prefit strict chronology/four-fit counts changed")
            context = {"features": copy.deepcopy(features), "fold_id": ordinal + 1, "parent_reference": copy.deepcopy(identity)}
            progress["fit_calls_entered"] += 1
            common.base._atomic_json(output / "fit_progress.json", progress)
            isolated_fit, isolated_check = copy.deepcopy((fit, check))
            values, trainer = fit_predict(isolated_fit, isolated_check, context)
            progress["fit_callbacks_returned"] += 1
            returned = {key: value for key, value in trainer.items() if key != "primitive_prediction_state"}
            try:
                reference.digest(returned)
            except (TypeError, ValueError):
                returned = {"receipt_json_status": "unserializable; callback returned but evidence invalid"}
            progress["returned_fit_receipts"].append(returned)
            common.base._atomic_json(output / "fit_progress.json", progress)
            _complete(trainer, trainer["primitive_prediction_state"], fit, contract["fit_completion_requirements"])
            if not isinstance(values, list) or len(values) != len(check):
                raise ValueError("one exact probability per check row required")
            for value in values:
                common.probability_contract.validate_probability(value, common.probability_contract.DEFAULT_PROBABILITY_POLICY, arm)
            replayed, bounds = replay_predictor(copy.deepcopy(trainer["primitive_prediction_state"]), copy.deepcopy(check), copy.deepcopy(context))
            if values != replayed or trainer["bounding"] != bounds:
                raise ValueError("exact candidate numeric replay changed")
            progress["fit_calls_completed"] += 1
            progress["completion_receipts"].append({"fold": ordinal + 1, "state_sha256": trainer["predictor_state_sha256"], "requirements": contract["fit_completion_requirements"]})
            common.base._atomic_json(output / "fit_progress.json", progress)
            return values, trainer
        predictions, reports = parent_module.fit_and_predict(rows, frozen["folds"], controls, parent, fit_predict=tracked_fit, arm=arm)
        key_hash = common._digest([list(item["row"].key) for item in predictions])
        if len(predictions) != 87 or key_hash != frozen["check_key_sha256"] or any(item["fit_label_unavailable_game_ids"] for item in reports) or progress["fit_calls_completed"] != 4:
            raise ValueError("exact87/fourfold common mask changed")
        for report in reports:
            report["correction_diagnostics"] = legacy.diagnostics([item for item in predictions if item["fold"] == report["fold"]], arm)
        states = {"schema": "candidate_numeric_prediction_states_v1", "task_id": candidate, "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"], "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", states)
        metrics, paired = shared.aggregate(predictions, arm), shared.paired_evidence(predictions, arm)
        scientific, operational, conditions = common.decision(metrics, reports, paired, arm)
        dates = sorted({item["row"].game_date for item in predictions})
        card = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": candidate, "candidate_arm": arm, "actual_research_parent_arm": shared.ARM_RESEARCH_PARENT, "actual_research_parent_id": binding["research_parent"]["candidate_id"], "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions, "model_fits": 4, "control_refits": 0, "feature_names": binding["feature_names"], "clipped_check_rows": sum(item["trainer"]["bounding"]["clipped_rows"] for item in reports), "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2, "check_events": 87, "check_dates": len(dates), "check_game_weeks": len({item["row"].game_week for item in predictions})}, "identical_masks": {"all_controls_same_rows_labels_and_checkpoints": True, "check_key_sha256": key_hash, "matches_frozen_v0": True}, "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired, "correction_diagnostics": legacy.diagnostics(predictions, arm), "per_schedule_date_correction_diagnostics": [{"game_date": day, "events": sum(item["row"].game_date == day for item in predictions), "arms": legacy.diagnostics([item for item in predictions if item["row"].game_date == day], arm)} for day in dates], "parent_reference": parent_receipt, "research_parent_sha256": binding["research_parent"]["runner_sha256"], "comparison_incumbent_sha256": binding["comparison_incumbent_sha256"], "attribution": binding["attribution"], "harness_binding": binding, **common.BOUNDARY_FLAGS}
        shared.write_predictions(output / "predictions.csv", predictions, arm)
        common.base._atomic_json(output / "scorecard.json", card)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": candidate, "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195, "materialized_events": 193, "excluded_events": 2, "check_events": 87, "model_fits": 4, "control_refits": 0, "automatic_retries": 0, "scientific_decision": scientific, "operational_decision": operational, "harness_binding": binding, **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"), ("fit_progress", "json"), ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "fit_progress.json", progress)
        common.base._atomic_json(output / "failure.json", {"task_id": candidate, "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits_maximum": 4, "automatic_retries": 0, "fit_progress": progress, "candidate_partial_receipt": getattr(error, "receipt", None), **common.BOUNDARY_FLAGS})
        raise
