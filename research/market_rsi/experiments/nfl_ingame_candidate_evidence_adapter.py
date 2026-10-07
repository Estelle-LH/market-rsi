#!/usr/bin/env python3
"""Reviewed H1 evidence entry; unchanged scientific callbacks and protected judge."""
from __future__ import annotations
import argparse
import copy
import inspect
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import platform
from experiments import nfl_ingame_market_temperature_offset as c7

parent_module, shared, common = c7.parent_module, c7.shared, c7.common
CONTRACT = Path(__file__).parents[1] / "supervisor_harness/COEVO_H1_CONTRACT_2026-10-05-v3.json"
CONTRACT_SHA256 = "9317c9d2e888cc8b6ca4a65bb8fe361a2493472eca37bbbad25bd462dfb39e3b"
C7_SHA256 = "f5a80888069140a78ab637cf0e03a7bf3df3da2458151323a43e696bf88b8085"
MODEL_FITS, FIT_COUNTS, CHECK_COUNTS = 4, (106, 132, 148, 176), (26, 16, 28, 17)

def validate_binding(binding, callbacks):
    """Hashes bind approved host callbacks, not an arbitrary-code sandbox."""
    if set(callbacks) != {"prepare_features", "fit_predict", "replay_predictor"}:
        raise ValueError("exact three callbacks required")
    expected = held_c7_binding()["dependency_source_hashes"]
    if any(binding["dependency_source_hashes"].get(path) != digest for path, digest in expected.items()):
        raise ValueError("immutable helper dependency coverage changed")
    paths = {binding["candidate_source_path"]: binding["candidate_source_sha256"],
        binding["candidate_contract_path"]: binding["candidate_contract_sha256"],
        binding["adapter_contract_path"]: binding["adapter_contract_sha256"],
        str(Path(__file__).resolve()): binding["adapter_source_sha256"]}
    for path, digest in binding["dependency_source_hashes"].items():
        if path in paths and paths[path] != digest:
            raise ValueError("conflicting source and dependency binding")
        paths[path] = digest
    if Path(binding["adapter_contract_path"]).resolve() != CONTRACT.resolve() or binding["adapter_contract_sha256"] != CONTRACT_SHA256:
        raise ValueError("H1 contract binding changed")
    for filename, digest in paths.items():
        path = Path(filename)
        if not path.is_absolute() or path.is_symlink() or not path.is_file() or not isinstance(digest, str) or len(digest) != 64 or common._sha256(path) != digest:
            raise ValueError(f"admitted source/spec changed: {path.name}")
    for name, callback in callbacks.items():
        source = str(Path(inspect.getsourcefile(callback)).resolve())
        if source != binding["callback_source_bindings"][name] or source not in paths:
            raise ValueError("callback source is not explicitly admitted")
    c7.require_dependencies()
    contract = common.settlement._strict_json(Path(binding["candidate_contract_path"]))
    names = contract.get("fixed_predictive_information", contract.get("predictive_information", {}))["feature_names"]
    incumbent = contract.get("comparison_incumbent_sha256", contract.get("comparison_incumbent", {}).get("sha256"))
    attribution = contract.get("attribution", contract.get("changed_training_recipe", {}).get("attribution"))
    if (contract["candidate_id"] != binding["candidate_id"] or contract["research_parent"] != binding["research_parent"]
            or names != binding["feature_names"] or incumbent != binding["comparison_incumbent_sha256"]
            or attribution != binding["attribution"] or binding["arm"] != callbacks["fit_predict"].__globals__.get("ARM_CANDIDATE")):
        raise ValueError("scientific contract/parent/features/incumbent changed")
    return contract

def load_parent(contract, controls, frozen):
    evidence = contract["research_parent"]
    if evidence["candidate_id"] == parent_module.TASK_ID:
        return c7.load_parent(contract, controls, frozen)
    if evidence["candidate_id"] != c7.TASK_ID or evidence["runner_sha256"] != C7_SHA256:
        raise ValueError("H1 admits only frozen C1/C7 parent schemas")
    evidence = copy.deepcopy(evidence)
    evidence.update({name.split(".")[0] + "_sha256": digest for name, digest in evidence["artifact_hashes"].items()})
    parent = shared.load_parent_predictions({"research_parent": evidence}, controls, frozen)
    root = Path(evidence["artifact_root"])
    names = {"manifest.json", "input_receipts.json", "pre_score_lock.json", "exclusions.json",
        "predictor_states.json", "scorecard.json", "predictions.csv", "fit_progress.json"}
    manifest = common.settlement._strict_json(root / "manifest.json")
    if set(evidence["artifact_hashes"]) != names:
        raise ValueError("C7 parent requires exact eight-file receipts")
    for name, digest in evidence["artifact_hashes"].items():
        path = root / name
        if path.is_symlink() or common._sha256(path) != digest or (name != "manifest.json" and manifest[name.split(".")[0] + "_sha256"] != digest):
            raise ValueError("C7 parent artifact changed")
    receipts, lock, exclusions = [common.settlement._strict_json(root / f"{name}.json") for name in ("input_receipts", "pre_score_lock", "exclusions")]
    if (receipts["task_id"] != c7.TASK_ID or receipts["runner_sha256"] != C7_SHA256
            or receipts["controller_contract_sha256"] != c7.CONTRACT_SHA256 or evidence["controller_contract_sha256"] != c7.CONTRACT_SHA256
            or lock["task_id"] != c7.TASK_ID or lock["controller_contract_sha256"] != c7.CONTRACT_SHA256
            or receipts["v0_artifact_hashes"] != frozen["hashes"] or receipts["pbp_receipts"] != frozen["receipts"]["pbp_receipts"]
            or common._digest(receipts["materialized_receipts"]) != common._digest(frozen["receipts"]["materialized_receipts"])
            or (exclusions["source_events"], exclusions["materialized_events"], exclusions["excluded_events"]) != (195, 193, 2)
            or [(item["game_id"], item["reason"]) for item in exclusions["exclusions"]] != common.identity.EXPECTED_EXCLUSIONS
            or any(receipts.get(key) != value for key, value in common.BOUNDARY_FLAGS.items())):
        raise ValueError("C7 parent causal/authority receipts changed")
    artifact, card = [common.settlement._strict_json(root / f"{name}.json") for name in ("predictor_states", "scorecard")]
    progress = common.settlement._strict_json(root / "fit_progress.json")
    if (artifact["task_id"] != c7.TASK_ID or card["task_id"] != c7.TASK_ID
            or [item["fold"] for item in artifact["folds"]] != [1, 2, 3, 4]
            or len(evidence["state_sha256_by_fold"]) != 4 or len(card["folds"]) != 4
            or progress["fit_calls_entered"] != 4 or progress["fit_calls_completed"] != 4):
        raise ValueError("C7 parent state task/folds changed")
    states = {}
    for item, report, digest in zip(artifact["folds"], card["folds"], evidence["state_sha256_by_fold"], strict=True):
        state = item["state"]
        if (common._digest(state) != digest or item["state_sha256"] != digest or report["fold"] != item["fold"]
                or report["trainer"]["predictor_state_sha256"] != digest or state["schema"] != evidence["state_schema"]
                or state["fit_events"] != report["fit_events"] or state["beta"] != evidence["beta_by_fold"][item["fold"] - 1]):
            raise ValueError("C7 canonical state/fit/beta binding changed")
        states[item["fold"]] = state
    return parent, states

def replay_parent(rows, folds, parent, states, parent_id):
    if parent_id == parent_module.TASK_ID:
        return c7.replay_parent(rows, folds, parent, states)
    if parent_id != c7.TASK_ID or [fold["fold"] for fold in folds] != [1, 2, 3, 4] or set(states) != {1, 2, 3, 4}:
        raise ValueError("C7 replay requires exact parent and ordered four states/folds")
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    seen, reports = set(), []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date[day]], key=lambda row: row.key)
        fit, unavailable = common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        state = states[fold["fold"]]
        values, _ = c7.replay_predictor(state, check)
        if (unavailable or state["fit_events"] != len(fit)
                or state["raw_fit_sha256"] != common._digest(parent_module.raw_probabilities(fit).tolist())
                or state["fit_logit_sha256"] != common._digest([row.market_features[0] for row in fit])):
            raise ValueError("C7 parent past-only fit inputs/count changed")
        if any(row.key in seen or value != parent[row.key] for row, value in zip(check, values, strict=True)):
            raise ValueError("C7 exact parent replay changed")
        seen.update(row.key for row in check)
        reports.append({"fold": fold["fold"], "state_sha256": common._digest(state), "parent_probability_rows_replayed": len(check), "parent_refits": 0})
    if len(seen) != 87 or seen != set(parent) or set(states) != {1, 2, 3, 4}:
        raise ValueError("C7 parent exact87/four-state coverage changed")
    return {"folds": reports, "parent_rows_replayed": 87, "parent_refits": 0, "four_canonical_states_exact": True}

def diagnostics(predictions, arm):
    result = {}
    for name in (arm, shared.ARM_RESEARCH_PARENT):
        correction = [item[name] - item[shared.ARM_RAW] for item in predictions]
        energy = math.fsum(value * value for value in correction) / len(predictions)
        alignment = math.fsum(2 * value * (item[shared.ARM_RAW] - item["row"].trusted["outcome"]) for item, value in zip(predictions, correction, strict=True)) / len(predictions)
        result[name] = {"equal_event_correction_energy": energy, "equal_event_signed_alignment": alignment, "equal_event_brier_delta_raw_identity": energy + alignment}
    return result

def run_recipe(source_root, output, binding, prepare_features, fit_predict, replay_predictor, *, allow_test_paths=False):
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    progress = {"fit_calls_entered": 0, "fit_calls_completed": 0, "optimizer_receipts": [], "entry_semantics": "candidate fit function entry; valid completion includes numeric solve and output replay"}
    candidate_id = binding.get("candidate_id", "UNKNOWN") if isinstance(binding, dict) else "UNKNOWN"
    try:
        arm = binding["arm"]
        contract = validate_binding(binding, dict(prepare_features=prepare_features, fit_predict=fit_predict, replay_predictor=replay_predictor))
        frozen = common.frozen_v0._validate_v0_artifact(shared.V0_ARTIFACT_ROOT)
        controls = common.identity._frozen_controls(frozen)
        parent, parent_states = load_parent(contract, controls, frozen)
        cohort = common.base._validate_source(source_root, expected_events=195, expected_dates=42, allow_test_paths=allow_test_paths)
        pbp = common.base._validate_pbp_receipts(source_root, cohort)
        if pbp != frozen["receipts"]["pbp_receipts"]:
            raise ValueError("opened-Train PBP receipts changed")
        anchors, rows, exclusions = {item["game_id"]: item for item in frozen["anchors"]}, [], []
        for ordinal, item in enumerate(cohort):
            try:
                rows.append(common.base._load_dynamic_market(source_root, item, anchors[item["game_id"]]))
            except common.settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"], "game_date": item["game_date"], "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        receipts, raw = [row.source_receipt for row in rows], parent_module.raw_probabilities(rows)
        if len(rows) != 193 or len(exclusions) != 2 or [(item["game_id"], item["reason"]) for item in exclusions] != common.identity.EXPECTED_EXCLUSIONS or common._digest(receipts) != common._digest(frozen["receipts"]["materialized_receipts"]):
            raise ValueError("frozen195/193+2 causal receipts changed")
        parent_receipt = replay_parent(rows, frozen["folds"], parent, parent_states, binding["research_parent"]["candidate_id"])
        features, feature_receipts = prepare_features(rows, frozen, copy.deepcopy(parent_states))
        common.base._atomic_json(output / "input_receipts.json", {"task_id": candidate_id, "controller_contract_sha256": binding["candidate_contract_sha256"], "runner_sha256": binding["candidate_source_sha256"], "harness_binding": binding, "dependency_source_hashes": binding["dependency_source_hashes"], "parent_replay": parent_receipt, "feature_receipts": feature_receipts, "raw_materialized_sha256": common._digest(raw.tolist()), "native_rows_validated": len(rows), "runtime_versions": {"python": platform.python_version(), "numpy": c7.np.__version__, "scipy": parent_module.scipy.__version__, "sklearn": shared.sklearn.__version__}, "v0_artifact_hashes": frozen["hashes"], "parent_artifacts": binding["research_parent"], "pbp_receipts": pbp, "materialized_receipts": receipts, "source_manifest_sha256": common._sha256(source_root / "manifest.json"), "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": candidate_id, "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": binding["candidate_contract_sha256"], "scientific_recipe": contract, "harness_binding": binding, "folds": frozen["folds"], "fit_budget": 4, "automatic_retries": 0, "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193, "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        def tracked_fit(fit, check, unused):
            ordinal = progress["fit_calls_entered"]
            if ordinal >= 4 or len(fit) != FIT_COUNTS[ordinal] or len(check) != CHECK_COUNTS[ordinal] or any(row.trusted["outcome_available_ms"] >= min(item.trusted["cutoff_ms"] for item in check) for row in fit):
                raise ValueError("prefit exact chronology/four-fit/count boundary changed")
            context = {**copy.deepcopy(features or {}), "fold_id": ordinal + 1, "parent_state": copy.deepcopy(parent_states[ordinal + 1])}
            progress["fit_calls_entered"] += 1
            trainer = None
            try:
                values, trainer = fit_predict(fit, check, context)
                state = trainer["primitive_prediction_state"]
                if (type(trainer["model_fits"]) is not int or trainer["model_fits"] != 1
                        or state["fit_events"] != len(fit) or common._digest(state) != trainer["predictor_state_sha256"]
                        or not isinstance(trainer.get("optimizer"), dict) or trainer["optimizer"].get("converged") is not True):
                    raise ValueError("candidate state/one-fit receipt changed")
                for value in values:
                    common.probability_contract.validate_probability(value, common.probability_contract.DEFAULT_PROBABILITY_POLICY, arm)
                replayed, bounds = replay_predictor(state, check, context)
                if values != replayed or trainer["bounding"] != bounds:
                    raise ValueError("candidate exact numeric prediction replay changed")
            except Exception as error:
                receipt = getattr(error, "receipt", None) or (trainer or {}).get("optimizer")
                if receipt is not None:
                    progress["optimizer_receipts"].append(receipt)
                common.base._atomic_json(output / "fit_progress.json", progress)
                error.receipt = receipt
                raise
            progress["fit_calls_completed"] += 1
            progress["optimizer_receipts"].append(trainer["optimizer"])
            common.base._atomic_json(output / "fit_progress.json", progress)
            return values, trainer
        predictions, reports = parent_module.fit_and_predict(rows, frozen["folds"], controls, parent, fit_predict=tracked_fit, arm=arm)
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256 or any(item["fit_label_unavailable_game_ids"] for item in reports) or progress["fit_calls_completed"] != 4:
            raise ValueError("exact87 chronology/four-fit mask changed")
        for report in reports:
            report["correction_diagnostics"] = diagnostics([item for item in predictions if item["fold"] == report["fold"]], arm)
        states = {"schema": "market_temperature_offset_numeric_states_v1" if candidate_id == c7.TASK_ID else "candidate_numeric_prediction_states_v1", "task_id": candidate_id, "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"], "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", states)
        metrics, paired = shared.aggregate(predictions, arm), shared.paired_evidence(predictions, arm)
        scientific, operational, conditions = common.decision(metrics, reports, paired, arm)
        diag = diagnostics(predictions, arm)
        dates = sorted({item["row"].game_date for item in predictions})
        date_diag = [{"game_date": day, "events": sum(item["row"].game_date == day for item in predictions), "arms": diagnostics([item for item in predictions if item["row"].game_date == day], arm)} for day in dates]
        card = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": candidate_id, "candidate_arm": arm, "actual_research_parent_arm": shared.ARM_RESEARCH_PARENT, "actual_research_parent_id": binding["research_parent"]["candidate_id"], "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions, "model_fits": 4, "control_refits": 0, "feature_names": binding["feature_names"], "alpha": 16., "clipped_check_rows": sum(item["trainer"]["bounding"]["clipped_rows"] for item in reports), "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2, "check_events": 87, "check_dates": len(dates), "check_game_weeks": len({item["row"].game_week for item in predictions})}, "identical_masks": {"all_controls_same_rows_labels_and_checkpoints": True, "check_key_sha256": check_hash, "matches_frozen_v0": True}, "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired, "correction_diagnostics": diag, "per_schedule_date_correction_diagnostics": date_diag, "parent_replay": parent_receipt, "research_parent_sha256": binding["research_parent"]["runner_sha256"], "comparison_incumbent_sha256": binding["comparison_incumbent_sha256"], "attribution": binding["attribution"], "harness_binding": binding, **common.BOUNDARY_FLAGS}
        if candidate_id == c7.TASK_ID:
            card.update(calibration_question_annotation=c7.annotate_question(metrics, reports, paired, diag), training_loss_limit="summed unweighted NLL with identity-centered prior; Brier judge unchanged", inference_boundary="repeatedly inspected Train Discovery; historical event clock only; no new information or H/R effect")
        shared.write_predictions(output / "predictions.csv", predictions, arm)
        common.base._atomic_json(output / "scorecard.json", card)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": candidate_id, "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195, "materialized_events": 193, "excluded_events": 2, "check_events": 87, "model_fits": 4, "control_refits": 0, "automatic_retries": 0, "scientific_decision": scientific, "operational_decision": operational, "harness_binding": binding, **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"), ("fit_progress", "json"), ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "failure.json", {"task_id": candidate_id, "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits_maximum": 4, "automatic_retries": 0, "fit_progress": progress, "optimizer_partial_receipt": getattr(error, "receipt", None), **common.BOUNDARY_FLAGS})
        raise

def prepare_c7(rows, frozen, parent_states):
    parent_module.raw_probabilities(rows)
    return {}, {"predictive_fields": ["market_logit"], "all_materialized_rows_validated": len(rows)}

def replay_c7(state, rows, features):
    return c7.replay_predictor(state, rows)

def held_c7_binding():
    contract = common.settlement._strict_json(c7.CONTRACT)
    dependencies = {str(Path(module.__file__).resolve()): digest for module, digest in common.DEPENDENCIES.items()}
    dependencies.update({str(Path(common.__file__).resolve()): shared.COMMON_SOURCE_SHA256, str(Path(shared.__file__).resolve()): parent_module.SHARED_SOURCE_SHA256, str(Path(parent_module.__file__).resolve()): c7.PARENT_SOURCE_SHA256})
    dependencies[str(Path(c7.__file__).resolve())] = C7_SHA256
    return {"candidate_id": c7.TASK_ID, "arm": c7.ARM_CANDIDATE, "candidate_source_path": str(Path(c7.__file__).resolve()), "candidate_source_sha256": C7_SHA256, "candidate_contract_path": str(c7.CONTRACT.resolve()), "candidate_contract_sha256": c7.CONTRACT_SHA256, "adapter_contract_path": str(CONTRACT.resolve()), "adapter_contract_sha256": CONTRACT_SHA256, "adapter_source_sha256": common._sha256(Path(__file__)), "dependency_source_hashes": dependencies, "research_parent": contract["research_parent"], "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"], "feature_names": c7.FEATURE_NAMES, "attribution": contract["changed_training_recipe"]["attribution"], "callback_source_bindings": {"prepare_features": str(Path(__file__).resolve()), "fit_predict": str(Path(c7.__file__).resolve()), "replay_predictor": str(Path(__file__).resolve())}}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run_recipe(args.source_root, args.output, held_c7_binding(), prepare_c7, c7.fit_temperature, replay_c7), sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
