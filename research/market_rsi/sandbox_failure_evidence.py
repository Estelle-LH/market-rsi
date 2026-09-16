"""Record a closed, post-isolation sandbox failure, never a market score.

This narrow path requires known input/source/runtime, a nonzero terminal command,
an independent pre-import isolation pass, candidate-only diagnostics and exact
whole-sandbox cleanup. Ambiguous creation, setup, missing output, cleanup failure
or contradictory success receipts remain blocked. Cause must still be reviewed.
"""
import hashlib
import json
from pathlib import Path

import development_harbor
from diagnostic_channel import stderr_receipt
from inspection_stream import permitted_artifact
from market_rsi import digest, file_hash, identifier
from prediction_stream import finite, fingerprint
from sandbox_receipts import read_sandbox_receipts, sandbox_usage
from trial_inputs import prepare_development_trial
from worker_receipts import Receipts, read_regular, read_research_job


def raw(reads, path):
    value = read_regular(path)
    reads.files[str(Path(path).absolute())] = hashlib.sha256(value).hexdigest()
    return value


def partial_predictions(root, reads, packet, claim):
    directory = root / "collected/predictions"
    reads.absent(directory / "complete.json")
    if (directory / "complete.json").exists():
        raise ValueError("completed predictions cannot be silently discarded as failure")
    expected = {"train_sha256": fingerprint(packet["train"]), "evaluation_sha256": fingerprint(packet["evaluation"]),
        "candidate_sha256": claim["deployed_hashes"]["public/candidate.py"],
        "expected_predictions": len(packet["evaluation"]), "scoring_authorized": False}
    if reads.read(directory / "claim.json") != expected:
        raise ValueError("partial prediction log belongs to different inputs/code")
    rows, previous = [], "0" * 64
    data = raw(reads, directory / "predictions.jsonl")
    for index, line in enumerate(data.splitlines()):
        if index >= len(packet["evaluation"]):
            raise ValueError("extra partial predictions")
        row = json.loads(line)
        observation = packet["evaluation"][index]
        if (set(row) != {"sequence", "row_id", "prediction", "feature_row_sha256", "previous", "hash"}
                or row["sequence"] != index or row["row_id"] != observation["row_id"]
                or row["feature_row_sha256"] != fingerprint(observation) or row["previous"] != previous
                or row["hash"] != fingerprint({k: v for k, v in row.items() if k != "hash"})
                or not packet["limits"]["prediction_min"] <= finite(row["prediction"]) <= packet["limits"]["prediction_max"]):
            raise ValueError("partial prediction journal changed")
        rows.append(row)
        previous = row["hash"]
    if data and not data.endswith(b"\n"):
        raise ValueError("partial prediction line was not durably completed")
    return {"committed_before_failure": rows, "complete": False, "score": None}


def build_sandbox_failure(study, development_directory, **trial_arguments):
    active = study.snapshot()["active"]
    if active is None or active.get("kind") == "selection" or "prepared_research" in trial_arguments:
        raise ValueError("exact active experiment claim required")
    prepared = active["prepared"]
    if type(trial_arguments.get("expected_live")) is not bool:
        raise ValueError("explicit worker identity required")
    if trial_arguments["expected_live"]:
        development_harbor.require_admission(development_directory)
    elif not prepared["audit"]["experiment_id"].startswith("fixture-"):
        raise ValueError("fixture failure cannot be recorded as real market execution")
    bundle = prepare_development_trial(prepared_research=prepared, **trial_arguments)
    root, reads = Path(development_directory).absolute(), Receipts()
    claim, packet, runtime, _ = development_harbor.verify_job(root)
    if (reads.read(root / "binding.json") != bundle["binding"] or packet != bundle["packet"]
            or runtime != bundle["runtime"]):
        raise ValueError("failure belongs to another step")
    failed, command = reads.read(root / "failure.json"), reads.read(root / "command.json")
    if (failed.get("scored") is not False or failed.get("automatic_retry") is not False
            or type(command.get("exit_code")) is not int or command["exit_code"] == 0):
        raise ValueError("unambiguous nonzero terminal command required")
    identifier(failed["error_type"])
    reads.absent(root / "command-error.json")
    reads.absent(root / "collected/execution.json")
    if (root / "collected/execution.json").exists():
        raise ValueError("success and failure receipts conflict")
    worker_failure = reads.read(root / "collected/failure.json")
    if set(worker_failure) != {"error_type", "scored"} or worker_failure["scored"] is not False:
        raise ValueError("exact trusted runner failure record required")
    identifier(worker_failure["error_type"])
    isolation = reads.read(root / "collected/isolation.json")
    if (set(isolation["checks"]) != development_harbor.ISOLATION_CHECKS
            or any(v is not True for v in isolation["checks"].values()) or isolation["exit_code"] != 0
            or isolation["probe_sha256"] != claim["deployed_hashes"]["public/isolation_probe.py"]):
        raise ValueError("failure cannot be attributed to post-isolation execution")
    if reads.read(root / "libraries.json") != {"expected": runtime["libraries"], "actual": runtime["libraries"], "exit_code": 0}:
        raise ValueError("setup/library mismatch requires separate infrastructure review")
    job = read_sandbox_receipts(root, reads, claim, trial_arguments["budget"], prepared["audit"]["phase"],
                                expected_live=trial_arguments["expected_live"])
    diagnostic = stderr_receipt(root / "collected/candidate-stderr.log")
    raw(reads, root / "collected/candidate-stderr.log")
    if diagnostic != reads.read(root / "collected/candidate-diagnostic.json"):
        raise ValueError("candidate diagnostic changed")
    protocol = reads.read(root / "collected/protocol.json")
    if (not isinstance(protocol.get("events"), list) or not protocol["events"]
            or any(not isinstance(e, dict) or e.get("type") not in {"request", "response", "timeout", "eof", "oversized_response"}
                   for e in protocol["events"])):
        raise ValueError("bounded observed candidate protocol evidence required")
    partial = partial_predictions(root, reads, packet, claim) if claim["mode"] == "fit_predict" else None
    missing = reads.read(root / "collection.json")["missing_or_failed"]
    allowed_missing = {"execution.json"} | ({"predictions/complete.json"} if partial is not None else set())
    if set(missing) - allowed_missing:
        raise ValueError("required failure evidence was not collected")
    research = read_research_job(trial_arguments["research_directory"], prepared, trial_arguments["budget"],
                                 expected_live=trial_arguments["expected_live"])
    task = json.loads(prepared["messages"][1]["content"])["task"]
    catalog = {x["artifact_id"]: x for x in task["data_catalog"]}
    permitted = {split: permitted_artifact(trial_arguments[split + "_bytes"],
        catalog[trial_arguments[split + "_id"]], task, runtime["feature_names"])["rows"] for split in ("train", "dev")}
    coding_root = Path(trial_arguments["coding_directory"])
    coding = reads.read(coding_root / "response.json")
    coder_usage = reads.read(coding_root / "subscription-usage.json")
    for name in ("claim.json", "packet.json", "declared-runtime.json", "sources.json"):
        reads.read(root / name)
    trace = {"research_response": research["raw_response"], "coding_events": coding["events"],
        "coding_notes": coding["body"]["notes"], **permitted, "protocol": protocol,
        "protocol_status": "observed incomplete trace, not a complete prediction validation",
        "candidate_stderr": diagnostic, "partial_predictions": partial}
    completed = {"trial_id": active["trial_id"], "research_packet_sha256": prepared["packet_sha256"],
        "raw_research_response": research["raw_response"], "eligible_submission": False,
        "evidence_commitments": {"failure_producer_source": file_hash(__file__),
            "sandbox_receipt_source": file_hash(Path(__file__).with_name("sandbox_receipts.py")),
            "failure_receipts": reads.commitment()["sha256"],
            "research_receipts": research["receipts"].commitment()["sha256"],
            "coding_receipts": bundle["coding_receipts"].commitment()["sha256"]},
        "payload": {"proposal": research["proposal"], "candidate_code": bundle["candidate_source"],
            "train_dev_results": {"dev": {"execution_complete": False, "independent_score": None,
                                           "available_trace": trace, "scientific_admission": False}},
            "usage": {"research_token_metered_estimate_usd": research["metered_usd"], "coding": coder_usage,
                      "sandbox": sandbox_usage(job)},
            "failure": {"stage": "sandbox_execution", "observed_error_type": worker_failure["error_type"],
                "cause_independently_established": False, "continuation_requires_causal_review": True,
                "automatic_retry": False, "independent_score": None}}}
    read_sets = [reads, research["receipts"], bundle["research_receipts"], bundle["coding_receipts"]]
    for receipt in read_sets:
        receipt.revalidate()
    return {"completion": completed, "read_sets": read_sets, "scientific_admission": False,
            "continuation_requires_causal_review": True}
