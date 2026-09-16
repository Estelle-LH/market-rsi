"""Close one locally reaped GLM timeout without retrying or inventing usage.

The remote request may still be billed.  This path therefore moves the entire
reserved upper bound into effective cost until an invoice replaces it.  It is
only a continuation mechanism for an exact permanent claim, never a free retry.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

import development_harbor
from glm_canary import MODEL, RATES, cost
from market_rsi import digest, file_hash
from researcher_worker import (CONTROLLER_REASONING_EFFORT, CONTROLLER_TEMPERATURE,
                               GLMTransport)
from worker_receipts import Receipts, read_regular


def build_uncertain_timeout(study, research_directory, budget, *, expected_live):
    active = study.snapshot()["active"]
    if active is None or active.get("kind") == "selection" or type(expected_live) is not bool:
        raise ValueError("exact active research claim required")
    prepared = active["prepared"]
    audit = prepared["audit"]
    if not expected_live and not audit["experiment_id"].startswith("fixture-"):
        raise ValueError("mock timeout evidence cannot close a real experiment")

    directory = Path(research_directory).absolute()
    if expected_live:
        development_harbor.require_admission(directory)
    reads = Receipts()
    claim = reads.read(directory / "claim.json")
    request = reads.read(directory / "request.json")
    failure = reads.read(directory / "failure.json")
    reads.absent(directory / "response.json")
    reads.absent(directory / "assessment.json")
    limits = audit["resource_limits"]
    if (claim.get("audit") != audit or claim.get("code_sha256") !=
            file_hash(Path(__file__).with_name("researcher_worker.py"))
            or claim.get("model") != MODEL or claim.get("num_samples") != 1
            or claim.get("sampling_retries") != 0 or claim.get("seed") != 23
            or claim.get("temperature") != CONTROLLER_TEMPERATURE
            or claim.get("reasoning_effort") != CONTROLLER_REASONING_EFFORT
            or claim.get("tools") != [] or claim.get("live_transport") is not expected_live
            or not isinstance(claim.get("nonce"), str) or len(claim["nonce"]) != 32
            or claim.get("max_input_tokens") != limits["max_input_tokens"]
            or claim.get("max_output_tokens") != limits["max_output_tokens"]):
        raise ValueError("timeout research claim changed")
    if (request.get("messages") != prepared["messages"] or request.get("audit") != audit
            or request.get("rates") != RATES
            or request.get("max_output_tokens") != limits["max_output_tokens"]
            or not isinstance(request.get("token_ids"), list) or not request["token_ids"]
            or len(request["token_ids"]) > limits["max_input_tokens"]
            or request.get("upper_usd") != str(cost(len(request["token_ids"]),
                                                    limits["max_output_tokens"]))):
        raise ValueError("timeout request is not the active bounded request")
    if (not isinstance(failure, dict) or failure.get("error_type") not in {"RuntimeError", "TimeoutError"}
            or type(failure.get("elapsed_seconds")) not in {int, float}
            or not math.isfinite(failure["elapsed_seconds"])
            or not 0 <= failure["elapsed_seconds"] <= limits["max_wall_seconds"] + 5):
        raise ValueError("outer worker timeout evidence is not bounded")

    root = directory / "sample-process"
    process_claim = reads.read(root / "claim.json")
    process_receipt = reads.read(root / "receipt.json")
    blobs = {}
    for name in ("input", "stdout", "stderr"):
        path = root / (name + ".bin")
        blobs[name] = read_regular(path)
        reads.files[str(path)] = hashlib.sha256(blobs[name]).hexdigest()
    body = json.loads(blobs["input"])
    expected_sources = {name: file_hash(Path(__file__).with_name(name)) for name in
        ("glm_process_worker.py", "researcher_worker.py", "glm_canary.py")}
    expected_keys = {"operation", "cache_dir", "job_directory", "source_hashes",
                     "token_ids", "max_output", "timeout_seconds"}
    if (not isinstance(body, dict) or set(body) != expected_keys or body["operation"] != "sample"
            or body["job_directory"] != str(directory) or body["source_hashes"] != expected_sources
            or body["token_ids"] != request["token_ids"]
            or body["max_output"] != request["max_output_tokens"]
            or type(body["timeout_seconds"]) not in {int, float}
            or not math.isfinite(body["timeout_seconds"]) or body["timeout_seconds"] <= 0):
        raise ValueError("timed-out process was not the exact sample request")
    command = [sys.executable, "-I", str(Path(__file__).with_name("glm_process_worker.py"))]
    wall = process_claim.get("wall_seconds")
    if (process_claim.get("command_sha256") != digest(command)
            or process_claim.get("input_sha256") != reads.files[str(root / "input.bin")]
            or process_claim.get("environment_names") !=
               ["LANG", "PATH", "RSI_TINKER_API_KEY", "TOKENIZERS_PARALLELISM"]
            or process_claim.get("supervisor_source_sha256") !=
               file_hash(Path(__file__).with_name("bounded_process.py"))
            or process_claim.get("remote_cancellation_established") is not False
            or process_claim.get("max_stdout_bytes") != 16 * 1024 * 1024
            or process_claim.get("max_stderr_bytes") != 256 * 1024
            or type(wall) not in {int, float} or not math.isfinite(wall)
            or not 0 < wall <= limits["max_wall_seconds"]
            or body["timeout_seconds"] > wall or process_claim.get("reap_seconds") != 2):
        raise ValueError("timeout process claim changed")
    if (process_receipt.get("failure") != "local_wall_timeout"
            or process_receipt.get("process_reaped") is not True
            or type(process_receipt.get("exit_code")) is not int
            or process_receipt["exit_code"] == 0
            or process_receipt.get("input_complete") is not True
            or process_receipt.get("input_bytes_written") != len(blobs["input"])
            or process_receipt.get("output_complete") is not False
            or process_receipt.get("remote_request_terminal") is not None
            or process_receipt.get("remote_cancellation_established") is not False
            or process_receipt.get("unused_budget_released") is not False
            or type(process_receipt.get("elapsed_seconds")) not in {int, float}
            or not math.isfinite(process_receipt["elapsed_seconds"])
            or not 0 <= process_receipt["elapsed_seconds"] <= wall + 2):
        raise ValueError("local timeout is not safely reaped and remotely unresolved")
    for name in ("stdout", "stderr"):
        if (process_receipt.get(name + "_bytes") != len(blobs[name])
                or process_receipt.get(name + "_sha256") != reads.files[str(root / (name + ".bin"))]):
            raise ValueError("timeout process bytes changed")

    budget_state = budget.snapshot()
    job = budget_state["jobs"].get(directory.name)
    if (budget_state["experiment_id"] != audit["experiment_id"] or not isinstance(job, dict)
            or job["provider"] != "tinker" or job["input_sha256"] != digest(request)
            or job["upper_usd"] != request["upper_usd"]
            or job["state"] not in {"dispatched", "uncertain_terminal"}):
        raise ValueError("timeout budget claim is not the exact unresolved dispatch")
    evidence_sha = reads.commitment()["sha256"]
    accounting = {"terminal_local": True, "process_reaped": True,
        "remote_usage_unknown": True, "automatic_retry": False,
        "evidence_sha256": evidence_sha,
        "note": "Full reserved upper bound is effective cost until invoice reconciliation."}
    completed = {"trial_id": active["trial_id"],
        "research_packet_sha256": prepared["packet_sha256"], "raw_research_response": "",
        "eligible_submission": False,
        "evidence_commitments": {"timeout_receipts": evidence_sha,
            "timeout_producer_source": file_hash(__file__)},
        "payload": {"proposal": None, "candidate_code": None, "train_dev_results": {},
            "usage": {"research_token_metered_estimate_usd": None, "coding": None,
                "sandbox": None,
                "note": "Remote usage unknown; budget uses the request upper bound."},
            "failure": {"stage": "research", "kind": "provider_timeout_usage_unknown",
                "terminal_local": True, "remote_usage_unknown": True,
                "automatic_retry": False, "independent_score": None,
                "scientific_admission": False}}}
    reads.revalidate()
    return {"completion": completed, "read_sets": [reads],
            "budget_accounting": accounting, "scientific_admission": False}


def settle_uncertain_timeout_budget(research_directory, budget, built):
    for reads in built["read_sets"]:
        reads.revalidate()
    job_id = Path(research_directory).absolute().name
    state = budget.snapshot()["jobs"][job_id]
    if state["state"] == "dispatched":
        budget.settle_uncertain_at_upper(job_id, built["budget_accounting"])
    elif state["state"] == "uncertain_terminal":
        saved = json.loads(read_regular(budget.root / f"{job_id}.uncertain.json"))
        if saved != built["budget_accounting"]:
            raise ValueError("uncertain budget recovery receipt changed")
    else:
        raise ValueError("timeout budget was already resolved differently")


def commit_uncertain_timeout(study, research_directory, budget, built):
    settle_uncertain_timeout_budget(research_directory, budget, built)
    for reads in built["read_sets"]:
        reads.revalidate()
    study.complete(built["completion"])
