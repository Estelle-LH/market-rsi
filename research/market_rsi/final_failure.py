"""Verify a closed post-isolation final failure without manufacturing a score.

This records observations, not a causal diagnosis. Exact creation/runtime,
independent setup/isolation, bounded available outputs and acknowledged whole-
sandbox cleanup are required. Anything ambiguous remains a pending paid claim.
"""
from pathlib import Path

import development_harbor as execution
from diagnostic_channel import stderr_receipt
from market_rsi import identifier
from sandbox_failure_evidence import partial_predictions, raw
from sandbox_receipts import read_sandbox_receipts, sandbox_usage


def read_final_failure(root, reads, claim, packet, runtime, budget, *, live):
    root = Path(root).absolute()
    failure = reads.read(root / "failure.json")
    command = reads.read(root / "command.json")
    if (failure.get("scored") is not False or failure.get("automatic_retry") is not False
            or type(command.get("exit_code")) is not int or command["exit_code"] == 0):
        raise ValueError("unambiguous nonzero final command required")
    identifier(failure["error_type"])
    reads.absent(root / "command-error.json")
    reads.absent(root / "collected/execution.json")
    worker_failure = reads.read(root / "collected/failure.json")
    if set(worker_failure) != {"error_type", "scored"} or worker_failure["scored"] is not False:
        raise ValueError("trusted unscored final worker failure required")
    identifier(worker_failure["error_type"])
    isolation = reads.read(root / "collected/isolation.json")
    if (set(isolation["checks"]) != execution.ISOLATION_CHECKS
            or any(v is not True for v in isolation["checks"].values()) or isolation["exit_code"] != 0
            or isolation["probe_sha256"] != claim["deployed_hashes"]["public/isolation_probe.py"]):
        raise ValueError("final failure is not verified post-isolation execution")
    if reads.read(root / "libraries.json") != {"expected": runtime["libraries"], "actual": runtime["libraries"], "exit_code": 0}:
        raise ValueError("final setup/library mismatch needs infrastructure diagnosis")
    job = read_sandbox_receipts(root, reads, claim, budget, "transfer", expected_live=live)
    diagnostic = stderr_receipt(root / "collected/candidate-stderr.log")
    raw(reads, root / "collected/candidate-stderr.log")
    if reads.read(root / "collected/candidate-diagnostic.json") != diagnostic:
        raise ValueError("final candidate diagnostic changed")
    protocol = reads.read(root / "collected/protocol.json")
    if (not isinstance(protocol.get("events"), list) or not protocol["events"]
            or any(not isinstance(e, dict) or e.get("type") not in {"request", "response", "timeout", "eof", "oversized_response"}
                   for e in protocol["events"])):
        raise ValueError("observed incomplete final protocol evidence required")
    partial = partial_predictions(root, reads, packet, claim)
    missing = reads.read(root / "collection.json")["missing_or_failed"]
    if set(missing) - {"execution.json", "predictions/complete.json"}:
        raise ValueError("required final failure outputs were not collected")
    for name in ("claim.json", "binding.json", "packet.json", "declared-runtime.json", "sources.json"):
        reads.read(root / name)
    reads.revalidate()
    return {"job_id": root.name, "status": "failed_unscored", "predictions": None,
        "execution_receipts": reads.commitment(), "usage_at_verification": sandbox_usage(job),
        "failure_observation": {"worker_error_type": worker_failure["error_type"],
            "protocol": protocol, "candidate_stderr": diagnostic, "partial_predictions": partial,
            "cause_independently_established": False},
        "continuation_requires_review": True, "scored": False, "scientific_admission": False}
