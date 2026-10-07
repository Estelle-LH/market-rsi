#!/usr/bin/env python3
"""Frozen fill-age interaction; historical opened-Train diagnostic only."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import math
import os
from pathlib import Path

import numpy as np

from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_ingame_prior_play_success_residual_audit as frozen_v0
from experiments import nfl_ingame_identity_anchored_market_calibration as identity
from experiments import nfl_ingame_prior_play_success_uncertainty_stratified_offset as scaffold
from experiments import nfl_ingame_static_state_nested_shrinkage_train_diagnostic as nested
from experiments import nfl_settlement_probability_train_diagnostic as settlement
from minimal_prediction_loop import proper_scoring, probability_contract


TASK_ID = "InGameMarketFreshnessInteractionOffset-v1"
ARM_CANDIDATE = "market_freshness_interaction_offset"
ARM_RAW, ARM_ORDINARY, ARM_PARENT = scaffold.ARM_RAW, scaffold.ARM_ORDINARY, scaffold.ARM_PARENT
ALL_ARMS = (ARM_RAW, ARM_ORDINARY, ARM_PARENT, ARM_CANDIDATE)
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_CANDIDATE_CONTRACTS_2026-10-03.json"
CONTRACT_SHA256 = "e3b7bac05aeef4376674e8bbf01832e75f7ea6b6c8a6613d541fae01896ffa39"
SOURCE_ROOT, V0_ARTIFACT_ROOT = base.SOURCE_ROOT, frozen_v0.V0_ARTIFACT_ROOT
MODEL_FITS = 4
DEPENDENCIES = {
    base: "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7",
    frozen_v0: "a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb",
    identity: "dc4e372440dc3f29091770394a8989c3602e83c37f0909367a5ce321bc614b05",
    scaffold: "b827eecdd669451d92a24a1023e2407a10ddebd26585f4515e395c0f486ff589",
    nested: "a3026d5a12fa0028087f470e44b71f4e6eb9de1432e351e415e72a039b83f65b",
    settlement: "1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b",
    proper_scoring: "64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b",
    probability_contract: "7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74",
}
_digest, _sha256 = settlement._digest, settlement._sha256
BOUNDARY_FLAGS = {"route_dev_opened": False, "sealed_final_opened": False,
    "external_fetch": False, "paid_provider": False, "provider_cost_usd": "0",
    "promotion_authorized": False, "historical_event_clock_only": True}


def require_dependencies(candidate_id: str) -> tuple[dict, dict]:
    for path, expected in [(CONTRACT, CONTRACT_SHA256), *(
            (Path(module.__file__), digest) for module, digest in DEPENDENCIES.items())]:
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise ValueError(f"frozen dependency missing, symlinked or hash-changed: {path.name}")
    identity._require_single_thread_environment()
    contract = settlement._strict_json(CONTRACT)
    choices = [item for item in contract["candidates"] if item["candidate_id"] == candidate_id]
    if len(choices) != 1:
        raise ValueError("candidate is not uniquely bound by frozen Controller contract")
    return contract, choices[0]


def _vector(values: object, name: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 1 or not len(result) or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a finite nonempty vector")
    return result


def _design(features: object) -> np.ndarray:
    x = _vector(features, "single offset feature")
    return np.column_stack((x, np.zeros_like(x)))


def objective_gradient_hessian(beta: float, features: object, outcomes: object,
                               market_logits: object) -> tuple[float, float, float]:
    value, gradient, hessian = scaffold.objective_gradient_hessian(
        np.asarray([beta, 0.0]), _design(features), outcomes, market_logits)
    return value, float(gradient[0]), float(hessian[0, 0])


def fit_single_offset(features: object, outcomes: object, market_logits: object) -> tuple[float, dict]:
    parameters, report = scaffold.fit_stratified_offset(_design(features), outcomes, market_logits)
    if parameters[1] != 0.0:
        raise RuntimeError("zero-column solver coefficient moved")
    return float(parameters[0]), {**report, "beta": float(parameters[0]),
        "unused_zero_column_coefficient": float(parameters[1]), "single_scientific_coefficient": True}


def candidate_probabilities(beta: float, features: object, market_logits: object,
                            *, raw_probabilities: object | None = None) -> list[float]:
    if raw_probabilities is not None:
        raw = _vector(raw_probabilities, "raw market probability")
        offsets = _vector(market_logits, "market logit")
        if raw.shape != offsets.shape or np.any(raw <= 0) or np.any(raw >= 1):
            raise ValueError("raw market probabilities and offsets are misaligned")
        expected = np.asarray([math.log(value / (1 - value)) for value in raw])
        if not np.array_equal(expected, offsets):
            raise ValueError("market logits do not match frozen raw probabilities")
        if beta == 0.0:
            if _design(features).shape[0] != len(raw):
                raise ValueError("single offset feature and raw probabilities are misaligned")
            return [probability_contract.validate_probability(float(value),
                probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_RAW) for value in raw]
    return scaffold.candidate_probabilities(np.asarray([beta, 0.0]), _design(features), market_logits)


def causal_age(receipt: dict) -> float:
    try:
        event = settlement._utc(receipt["pbp_checkpoint_event_time_utc"], "frozen event clock")
        latest = receipt["latest_trade_epoch_ms"]
        cutoff = receipt["market_feature_cutoff_epoch_s"]
        age = float(receipt["market_staleness_seconds"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("causal age receipt is incomplete") from error
    if (type(latest) is not int or type(cutoff) is not int or latest % 1000 != 0
            or cutoff != math.floor(event.timestamp()) - 1 or latest // 1000 > cutoff
            or not math.isfinite(age) or not 0 <= age <= 300
            or not math.isclose(age, event.timestamp() - latest / 1000, abs_tol=1e-9, rel_tol=0)):
        raise ValueError("causal age receipt arithmetic, strict-before clock or range changed")
    return age


def freshness_features(fit_rows: list, check_rows: list, *, states: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    del states
    fit_age = np.asarray([causal_age(row.source_receipt) for row in fit_rows])
    check_age = np.asarray([causal_age(row.source_receipt) for row in check_rows])
    mean, scale = float(fit_age.mean()), float(fit_age.std(ddof=0))
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("fit-only age scale is zero or invalid")
    return ((fit_age - mean) / scale * np.asarray([row.market_features[0] for row in fit_rows]),
        (check_age - mean) / scale * np.asarray([row.market_features[0] for row in check_rows]),
        {"fit_age_mean": mean, "fit_age_std_ddof0": scale, "fit_only": True})


def _fit_and_predict(rows: list, folds: list, controls: dict, states: dict, feature_builder,
                     arm: str) -> tuple[list[dict], list[dict]]:
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions, reports = [], []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        fit_x, check_x, feature_report = feature_builder(fit, check, states=states)
        beta, optimizer = fit_single_offset(fit_x, [row.trusted["outcome"] for row in fit],
            [row.market_features[0] for row in fit])
        values = candidate_probabilities(beta, check_x, [row.market_features[0] for row in check],
            raw_probabilities=[row.trusted["market_probability"] for row in check])
        fold_predictions = []
        for row, value, feature in zip(check, values, check_x, strict=True):
            frozen = controls.get(row.key)
            raw = probability_contract.validate_probability(float(row.trusted["market_probability"]),
                probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_RAW)
            if (frozen is None or frozen["fold"] != fold["fold"] or frozen["game_id"] != row.game_id
                    or frozen["game_date"] != row.game_date or frozen["game_week"] != row.game_week
                    or frozen["outcome"] != row.trusted["outcome"] or frozen[ARM_RAW] != raw):
                raise ValueError("candidate row differs from frozen v0 identity/label/raw")
            fold_predictions.append({"fold": fold["fold"], "row": row, "feature": float(feature),
                ARM_RAW: raw, ARM_ORDINARY: frozen[ARM_ORDINARY], ARM_PARENT: frozen[ARM_PARENT], arm: value})
        predictions.extend(fold_predictions)
        reports.append({"fold": fold["fold"], "fit_dates": list(fold["fit_dates"]),
            "check_dates": list(fold["check_dates"]), "fit_events": len(fit), "check_events": len(check),
            "fit_label_unavailable_game_ids": unavailable, "feature_transform": feature_report,
            "optimizer": optimizer, "arms": _aggregate(fold_predictions, arm),
            "same_rows_labels_and_checkpoints": True})
    keys = [item["row"].key for item in predictions]
    if len(reports) != 4 or len(keys) != len(set(keys)) or set(keys) != set(controls):
        raise ValueError("exact four fits or frozen common mask changed")
    return predictions, reports


def _aggregate(predictions: list, arm: str) -> dict:
    result = scaffold._aggregate([{**item, scaffold.ARM_CANDIDATE: item[arm]} for item in predictions])
    result[arm] = result.pop(scaffold.ARM_CANDIDATE)
    return result


def _paired_evidence(predictions: list, arm: str) -> dict:
    return scaffold._paired_evidence([{**item, scaffold.ARM_CANDIDATE: item[arm]} for item in predictions])


def decision(aggregate: dict, reports: list, paired: dict, arm: str) -> tuple[str, str, dict]:
    renamed = {**aggregate, scaffold.ARM_CANDIDATE: aggregate[arm]}
    folds = [{**item, "arms": {**item["arms"], scaffold.ARM_CANDIDATE: item["arms"][arm]}} for item in reports]
    return scaffold.decision(renamed, folds, paired)


def _write_predictions(path: Path, predictions: list, arm: str) -> None:
    fields = ("fold", "game_id", "game_date", "game_week", "event_id", "market_id", "cutoff_ms",
        "outcome_available_ms", "outcome", "raw_market_probability",
        "frozen_v0_ordinary_market_only_probability", "frozen_v0_market_plus_state_parent_probability",
        "candidate_feature", "candidate_probability")
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow(dict(zip(fields, [item["fold"], row.game_id, row.game_date, row.game_week,
                row.trusted["event_id"], row.trusted["market_id"], row.trusted["cutoff_ms"],
                row.trusted["outcome_available_ms"], row.trusted["outcome"], item[ARM_RAW],
                item[ARM_ORDINARY], item[ARM_PARENT], item["feature"], item[arm]], strict=True)))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run_recipe(source_root: Path, output: Path, *, candidate_id: str, arm: str,
               runner_file: Path, feature_builder, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        contract, recipe = require_dependencies(candidate_id)
        frozen = frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
        controls = identity._frozen_controls(frozen)
        cohort = base._validate_source(source_root, expected_events=195, expected_dates=42, allow_test_paths=allow_test_paths)
        pbp = base._validate_pbp_receipts(source_root, cohort)
        if pbp != frozen["receipts"]["pbp_receipts"]:
            raise ValueError("opened-Train PBP source receipts differ from frozen v0")
        states = {row["game_id"]: row for row in frozen["anchors"]}
        rows, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                rows.append(base._load_dynamic_market(source_root, item, states[item["game_id"]]))
            except settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"],
                    "game_date": item["game_date"], "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        if (len(rows) != 193 or len(rows) + len(exclusions) != 195
                or [(item["game_id"], item["reason"]) for item in exclusions] != identity.EXPECTED_EXCLUSIONS):
            raise ValueError("exact frozen 195 -> 193 + 2 attrition changed")
        observed_receipts = [row.source_receipt for row in rows]
        if _digest(observed_receipts) != _digest(frozen["receipts"]["materialized_receipts"]):
            raise ValueError("materialized causal receipts differ from frozen v0")
        # Validate the basis on all materialized rows before the first fit.
        feature_builder(rows, rows, states=states)
        inputs = {"schema": "coevo_frozen_candidate_inputs_v1", "task_id": candidate_id,
            "controller_contract_sha256": CONTRACT_SHA256, "v0_artifact_hashes": frozen["hashes"],
            "runner_sha256": _sha256(runner_file), "shared_candidate_scaffold_sha256": _sha256(Path(__file__)),
            "dependency_source_hashes": {module.__name__: digest for module, digest in DEPENDENCIES.items()},
            "source_manifest_sha256": _sha256(source_root / "manifest.json"),
            "cohort_sha256": _sha256(source_root / "cohort.csv"), "pbp_receipts": pbp,
            "materialized_receipts": observed_receipts, **BOUNDARY_FLAGS}
        lock = {"schema": "coevo_frozen_candidate_pre_score_lock_v1", "task_id": candidate_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": recipe, "boundary": contract["boundary"], "folds": frozen["folds"],
            "fit_budget": 4, "automatic_retries": 0, "thread_environment_contract": identity.THREAD_ENV_CONTRACT,
            "resource_cap": {"processes": 1, "threads": 1, "fits": 4, "wall_seconds": 900,
                "network_bytes": 0, "provider_calls": 0, "provider_cost_usd": "0"}, **BOUNDARY_FLAGS}
        base._atomic_json(output / "pre_score_lock.json", lock)
        base._atomic_json(output / "input_receipts.json", inputs)
        base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        predictions, reports = _fit_and_predict(rows, frozen["folds"], controls, states, feature_builder, arm)
        check_hash = _digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports)):
            raise ValueError("frozen chronology, fit counts or exact87 mask changed")
        aggregate, paired = _aggregate(predictions, arm), _paired_evidence(predictions, arm)
        scientific, operational, conditions = decision(aggregate, reports, paired, arm)
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": candidate_id,
            "candidate_arm": arm, "scientific_decision": scientific, "operational_decision": operational,
            "decision_conditions": conditions, "model_fits": 4, "control_refits": 0,
            "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193,
                "excluded_events": 2, "check_events": len(predictions),
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_four_arms_same_rows_labels_and_checkpoints": True,
                "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": aggregate, "folds": reports, "paired_grouped_evidence": paired,
            "inference_boundary": "repeatedly inspected opened-Train Discovery; historical event clock only",
            "research_parent_sha256": recipe["research_parent_sha256"],
            "comparison_incumbent_sha256": recipe["comparison_incumbent_sha256"], **BOUNDARY_FLAGS}
        _write_predictions(output / "predictions.csv", predictions, arm)
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": candidate_id,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195,
            "materialized_events": 193, "excluded_events": 2, "check_events": 87,
            "model_fits": 4, "control_refits": 0, "automatic_retries": 0,
            "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": _sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"),
                ("predictions", "csv"), ("scorecard", "json"))}, **BOUNDARY_FLAGS}
        base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        base._atomic_json(output / "failure.json", {"schema": "coevo_frozen_candidate_failure_v1",
            "task_id": candidate_id, "error_type": type(error).__name__, "error": str(error)[:1200],
            "model_fits_maximum": 4, "automatic_retries": 0, **BOUNDARY_FLAGS})
        raise


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    return run_recipe(source_root, output, candidate_id=TASK_ID, arm=ARM_CANDIDATE,
        runner_file=Path(__file__), feature_builder=freshness_features, allow_test_paths=allow_test_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
