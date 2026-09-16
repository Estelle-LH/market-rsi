"""Assemble development execution inputs from completed, owned worker jobs.

This is pure preparation, not a cloud launcher or scientific admission. The
supervisor supplies its frozen runtime and original admitted research request.
No hidden Test payload is accepted by this development interface.
"""
from __future__ import annotations

import copy
import json

from inspection_stream import limits_valid, permitted_artifact, prepare_inspection
from prediction_stream import PUBLIC_FIELDS, encoded, finite, fingerprint, validate_rows
from worker_receipts import code_request_from_job, read_code_job


def execution_profile(runtime):
    """Match currently implemented candidate CPU/memory and bounded protocols.

    Installed library/version identity still needs outer sandbox verification.
    This check neither installs libraries nor certifies availability.
    """
    profile = runtime["execution_limits"]
    if (not isinstance(profile, dict) or set(profile) != {"cpu_seconds", "memory_mb", "prediction", "inspection"}
            or profile["cpu_seconds"] != 120 or profile["memory_mb"] != 512):
        raise ValueError("execution profile differs from implemented candidate resource limits")
    limits_valid(profile["inspection"])
    p = profile["prediction"]
    if not isinstance(p, dict) or set(p) != {"fit_timeout_seconds", "predict_timeout_seconds", "wall_seconds", "max_request_bytes"}:
        raise ValueError("exact prediction execution limits required")
    if (any(type(p[k]) is not int or not 0 < p[k] <= 120
            for k in ("fit_timeout_seconds", "predict_timeout_seconds", "wall_seconds"))
            or p["fit_timeout_seconds"] > p["wall_seconds"] or p["predict_timeout_seconds"] > p["wall_seconds"]
            or type(p["max_request_bytes"]) is not int or not 0 < p["max_request_bytes"] <= 8 * 1024 * 1024):
        raise ValueError("prediction execution limits exceed deployed safety envelope")
    return copy.deepcopy(profile)


def prepare_development_trial(research_directory, coding_directory, prepared_research, budget, *,
                              frozen_runtime, frozen_coder_limits, expected_live, expected_coder_identity,
                              train_id, train_bytes, dev_id, dev_bytes):
    profile = execution_profile(frozen_runtime)
    research, coding = code_request_from_job(research_directory, prepared_research, budget,
        frozen_runtime, frozen_coder_limits, expected_live=expected_live)
    code = read_code_job(coding_directory, research, coding, expected_live=expected_live,
                         expected_identity=expected_coder_identity)
    action = research["proposal"]["action"]
    task = json.loads(prepared_research["messages"][1]["content"])["task"]
    # Build only from the public task's exact artifact commitments. Paths, hidden
    # masks, score files and runner endpoints are never accepted as substitutes.
    catalog = task["data_catalog"]
    by_id = {entry["artifact_id"]: entry for entry in catalog}
    if (len(by_id) != len(catalog) or train_id == dev_id or train_id not in by_id or dev_id not in by_id
            or by_id[train_id]["split"] != "train" or by_id[dev_id]["split"] != "dev"):
        raise ValueError("one exact public Train and Dev artifact required")
    if not isinstance(train_bytes, bytes) or not isinstance(dev_bytes, bytes):
        raise ValueError("exact committed artifact bytes required")
    # Bound parsing even when an inspection is not requested. No silent subsample.
    if len(train_bytes) + len(dev_bytes) > 16 * 1024 * 1024:
        raise ValueError("development artifact safety cap exceeded")
    if code["entrypoint"] == "inspect":
        packet = prepare_inspection(prepared_research, coding, train_id=train_id, train_bytes=train_bytes,
            dev_id=dev_id, dev_bytes=dev_bytes, limits=profile["inspection"])
    else:
        names = frozen_runtime["feature_names"]
        train = permitted_artifact(train_bytes, by_id[train_id], task, names)["rows"]
        dev = permitted_artifact(dev_bytes, by_id[dev_id], task, names)["rows"]
        evaluation = [{k: copy.deepcopy(row[k]) for k in PUBLIC_FIELDS} for row in dev]
        validate_rows(train, evaluation, names)
        for row in dev:
            finite(row["target"])
            if type(row["label_available_ms"]) is not int or row["label_available_ms"] < row["decision_ms"]:
                raise ValueError("invalid Dev label metadata; do not pay to predict an unscorable mask")
        limits = dict(profile["prediction"], prediction_min=frozen_runtime["prediction_min"],
                      prediction_max=frozen_runtime["prediction_max"])
        fit = {"type": "fit", "request_id": "0" * 32, "features": names, "train": train}
        requests = [fit] + [{"type": "predict", "request_id": "0" * 32, "row": row} for row in evaluation]
        if any(len(encoded(r)) + 1 > limits["max_request_bytes"] for r in requests):
            raise ValueError("actual fit/predict request exceeds frozen byte cap")
        packet = {"train": train, "evaluation": evaluation, "feature_names": names, "limits": limits}
    research["receipts"].revalidate()
    code["receipts"].revalidate()
    binding = {"schema": "market_development_execution_v1", "research_job_id": research["job_id"],
        "coding_job_id": code["job_id"], "research_packet_sha256": prepared_research["packet_sha256"],
        "coding_packet_sha256": coding["packet_sha256"], "candidate_sha256": code["source_sha256"],
        "execution_packet_sha256": fingerprint(packet), "mode": code["entrypoint"], "action": action,
        "owner": {k: prepared_research["audit"][k] for k in
                  ("experiment_id", "arm", "task_id", "task_index", "step_index", "phase")},
        "train_source_sha256": by_id[train_id]["sha256"], "dev_source_sha256": by_id[dev_id]["sha256"],
        "runtime_sha256": fingerprint(frozen_runtime), "research_receipts": research["receipts"].commitment(),
        "coding_receipts": code["receipts"].commitment(), "scientific_admission": False,
        "library_availability_verified": False, "hidden_test_uploaded": False}
    return {"binding": binding, "packet": packet, "candidate_source": code["source"],
            "runtime": copy.deepcopy(frozen_runtime),
            "binding_sha256": fingerprint(binding), "research_receipts": research["receipts"],
            "coding_receipts": code["receipts"], "executed": False}
