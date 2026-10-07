"""Read-only, model-agnostic comparison of independently accepted predictions.

The trusted Supervisor supplies acceptance_binding separately after independently
reviewing its normalization of original source/result/learning evidence. Neither
a candidate manifest nor a self-hashed receipt authenticates that authority.
No fitting, predictor-state loading, weight inheritance or branch admission occurs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re

from minimal_prediction_loop.probability_contract import DEFAULT_PROBABILITY_POLICY, validate_probability

SCHEMA = "market_rsi_prediction_reference_v1"
ACCEPTANCE_SCHEMA = "market_rsi_prediction_reference_acceptance_v1"
ARTIFACTS = {"manifest.json", "input_receipts.json", "pre_score_lock.json",
             "exclusions.json", "scorecard.json", "predictions.csv"}
BASELINES = {"raw_market_probability": "raw_market",
    "frozen_v0_ordinary_market_only_probability": "frozen_v0_ordinary_market_only",
    "frozen_v0_market_plus_state_parent_probability": "frozen_v0_market_plus_state_parent"}
FLAGS = {"route_dev_opened": False, "sealed_final_opened": False,
    "external_fetch": False, "paid_provider": False, "provider_cost_usd": "0",
    "promotion_authorized": False, "historical_event_clock_only": True}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{label} exact fields changed")
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) or value == "0" * 64:
        raise ValueError("exact nonzero SHA256 required")
    return value


def _path(value):
    if not isinstance(value, str):
        raise ValueError("absolute artifact path required")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("absolute non-symlink path required")
    return path


def _read(binding):
    _exact(binding, {"path", "sha256"}, "byte binding")
    body = _path(binding["path"]).read_bytes()
    if not body or hashlib.sha256(body).hexdigest() != _hash(binding["sha256"]):
        raise ValueError("bound evidence bytes changed or empty")
    return body


def _json(body):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"nonfinite JSON: {value}")
    value = json.loads(body, object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("bound JSON must be an object")
    return value


def _key(row):
    if not row["event_id"] or not row["market_id"] or not re.fullmatch(r"[0-9]+", str(row["cutoff_ms"])):
        raise ValueError("invalid prediction row key")
    return row["event_id"], row["market_id"], int(row["cutoff_ms"])


def provenance(binding, frozen):
    """Projection to freeze before loading; caller must supply validated v0 data."""
    return {"task_id": frozen["manifest"]["task_id"], "kernel_sha256": _hash(binding["kernel_sha256"]),
        "v0_artifact_hashes": frozen["hashes"], "folds_sha256": digest(frozen["folds"]),
        "data_time_sha256": digest({"lock": frozen["lock"], "pbp": frozen["receipts"]["pbp_receipts"],
            "materialized": frozen["receipts"]["materialized_receipts"]}),
        "check_rows_sha256": digest(frozen["predictions"]),
        "exclusion_codes_sha256": digest(frozen["exclusion_codes"]),
        "check_key_sha256": digest([list(_key(row)) for row in frozen["predictions"]])}


def _exclusions(value):
    return {name: value[name] for name in ("source_events", "materialized_events", "excluded_events")} | {
        "exclusions": [{"game_id": row["game_id"], "reason": row["reason"]} for row in value["exclusions"]]}


def validate_header(binding, acceptance):
    """Pure structural preflight, NOT semantic acceptance or artifact verification."""
    _exact(binding, {"schema", "candidate_id", "runner", "source_commit", "artifact_root",
                     "artifact_hashes", "kernel_sha256"}, "reference")
    if (binding["schema"] != SCHEMA or not isinstance(binding["candidate_id"], str) or not binding["candidate_id"]
            or not isinstance(binding["source_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"])):
        raise ValueError("original candidate/source identity changed")
    _exact(acceptance, {"schema", "reference_sha256", "performance_status", "prediction_decision",
                        "provenance", "exclusions", "reviews"}, "acceptance")
    if (acceptance["schema"] != ACCEPTANCE_SCHEMA or acceptance["reference_sha256"] != digest(binding)
            or acceptance["performance_status"] != "valid_no_leakage"
            or acceptance["prediction_decision"] not in {"KEEP", "REVERT"}):
        raise ValueError("independent acceptance/validity changed")
    _exact(acceptance["reviews"], {"source", "result", "learning"}, "original reviews")
    _exact(binding["runner"], {"path", "sha256"}, "runner")
    _hash(binding["runner"]["sha256"])
    _hash(binding["kernel_sha256"])
    protocol = _exact(acceptance["provenance"], {"task_id", "kernel_sha256", "v0_artifact_hashes",
        "folds_sha256", "data_time_sha256", "check_key_sha256", "check_rows_sha256", "exclusion_codes_sha256"}, "protocol")
    if protocol["task_id"] != "InGameWinProbabilityTrainDiagnostic-v0" or protocol["kernel_sha256"] != binding["kernel_sha256"]:
        raise ValueError("frozen task/kernel changed")
    for name in ("folds_sha256", "data_time_sha256", "check_key_sha256", "check_rows_sha256", "exclusion_codes_sha256"):
        _hash(protocol[name])
    return acceptance


def load_reference(binding, controls, frozen, acceptance_binding):
    """Return (key->probability, receipt), without model-family/KEEP restriction.

    Trusted Supervisor independently pins acceptance_binding; byte hashes do
    not authenticate reviewer identity/semantics or grant branch eligibility.
    """
    acceptance = validate_header(binding, _json(_read(acceptance_binding)))
    if acceptance["provenance"] != provenance(binding, frozen):
        raise ValueError("independent accepted protocol changed")
    for proof in acceptance["reviews"].values():
        _read(proof)
    if len({proof["path"] for proof in acceptance["reviews"].values()}) != 3:
        raise ValueError("three distinct original review records required")
    _read(binding["runner"])
    root, hashes = _path(binding["artifact_root"]), binding["artifact_hashes"]
    if not isinstance(hashes, dict) or not ARTIFACTS <= set(hashes):
        raise ValueError("complete comparison artifacts required")
    artifacts = {}
    for name, value in hashes.items():
        if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
            raise ValueError("artifact basename required")
        body = _read({"path": str(root / name), "sha256": value})
        if name in ARTIFACTS:
            artifacts[name] = body
    manifest, inputs, lock, exclusions, card = [_json(artifacts[name + ".json"]) for name in
        ("manifest", "input_receipts", "pre_score_lock", "exclusions", "scorecard")]
    if (manifest.get("complete") is not True or type(manifest.get("model_fits")) is not int or manifest.get("model_fits") != len(frozen["folds"])
            or type(manifest.get("check_events")) is not int or manifest.get("check_events") != len(controls)
            or any(item.get("task_id") != binding["candidate_id"] for item in (manifest, inputs, lock, card))):
        raise ValueError("parent completion/task/fit identity changed")
    for name, value in hashes.items():
        if name != "manifest.json" and manifest.get(name.rsplit(".", 1)[0] + "_sha256") != value:
            raise ValueError("parent manifest artifact binding changed")
    if (inputs.get("runner_sha256") != binding["runner"]["sha256"] or inputs.get("v0_artifact_hashes") != frozen["hashes"]
            or inputs.get("pbp_receipts") != frozen["receipts"]["pbp_receipts"]
            or inputs.get("materialized_receipts") != frozen["receipts"]["materialized_receipts"]
            or lock.get("folds") != frozen["folds"] or _exclusions(exclusions) != acceptance["exclusions"]
            or any(type(inputs.get(key)) is not type(value) or type(lock.get(key)) is not type(value)
                or inputs.get(key) != value or lock.get(key) != value for key, value in FLAGS.items())):
        raise ValueError("parent kernel/data-time/exclusion boundary changed")
    for name in ("source_events", "materialized_events", "excluded_events"):
        if type(exclusions[name]) is not int or exclusions[name] != frozen["manifest"][name]:
            raise ValueError("full population denominator changed")
    codes = {row["game_id"]: row["reason"] for row in exclusions["exclusions"]}
    if len(codes) != len(exclusions["exclusions"]) or len(codes) != exclusions["excluded_events"] or codes != frozen["exclusion_codes"]:
        raise ValueError("frozen exclusion codes changed")
    reader = csv.DictReader(io.StringIO(artifacts["predictions.csv"].decode("utf-8"), newline=""))
    required = {"event_id", "market_id", "cutoff_ms", "fold", "game_id", "game_date", "game_week",
                "outcome", "outcome_available_ms", "candidate_probability", *BASELINES}
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not required <= set(reader.fieldnames):
        raise ValueError("prediction CSV schema changed")
    availability = {_key(row): int(row["outcome_available_ms"]) for row in frozen["predictions"]}
    if len(availability) != len(frozen["predictions"]) or set(availability) != set(controls):
        raise ValueError("trusted frozen common mask changed")
    for row in frozen["predictions"]:
        control = controls[_key(row)]
        if (any(str(row[name]) != str(control[name]) for name in ("fold", "game_id", "game_date", "game_week", "outcome"))
                or any(float(row[column]) != control[arm] for column, arm in zip(
                    ("raw_market_probability", "market_model_probability", "market_plus_state_probability"), BASELINES.values(), strict=True))):
            raise ValueError("controls differ from original frozen rows")
    result, ordered = {}, []
    for row in reader:
        key, control = _key(row), controls.get(_key(row))
        if (None in row or any(value is None for value in row.values()) or control is None or key in result
                or any(row[name] != str(control[name]) for name in ("fold", "game_id", "game_date", "game_week", "outcome"))
                or int(row["outcome_available_ms"]) != availability[key]
                or row["game_date"] not in frozen["folds"][control["fold"] - 1]["check_dates"]):
            raise ValueError("prediction row/fold/identity/label changed")
        for column, arm in BASELINES.items():
            if validate_probability(float(row[column]), DEFAULT_PROBABILITY_POLICY, arm) != control[arm]:
                raise ValueError("frozen comparator probability changed")
        result[key] = validate_probability(float(row["candidate_probability"]), DEFAULT_PROBABILITY_POLICY, "reference")
        ordered.append(list(key))
    if set(result) != set(controls) or digest(ordered) != acceptance["provenance"]["check_key_sha256"]:
        raise ValueError("exact ordered prediction mask changed")
    return result, {"schema": "market_rsi_prediction_reference_verification_v1", "reference_sha256": digest(binding),
        "acceptance_sha256": acceptance_binding["sha256"], "original_reviews": acceptance["reviews"],
        "source_commit": binding["source_commit"], "candidate_id": binding["candidate_id"],
        "provenance": acceptance["provenance"], "prediction_rows": len(result), "parent_refits": 0,
        "predictor_states_loaded": False, "parameter_inheritance": False, "comparison_only": True,
        "artifact_bytes_verified": sorted(hashes), "model_state_semantics": "optional state bytes hash-verified only; never decoded or inherited",
        "acceptance_authority": "trusted Supervisor independently reviewed normalization; hashes bind bytes, not reviewer semantics"}
