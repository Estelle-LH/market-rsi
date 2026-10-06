"""Reviewed execution failures become factual inputs, never forecast evidence.

The recorder's legacy scorecard field may bind the *same actual failure receipt*
as execution_receipt_sha256. An explicit independent failure review verifies
that alias; no scorecard, predictions, supplement or replacement receipt exists.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import opened_train_discovery_worker as worker

FAILED_ROLES = {"feedback", "review", "failure", "memory", "history", "pool", "authority", "overhead", "request"}
FAILURE_FIELDS = {"attempt_id", "request_sha256", "source_commit", "command", "runtime_pair_sha256",
    "memory_sha256", "outcome", "exit_code", "error", "wall_seconds", "fits_reserved",
    "sampled_peak_rss_kib", "rss_limit_kib", "rss_limit_enforcement", "stdout_sha256",
    "stderr_sha256", "output", "metrics_independently_reviewed", "network_isolation_enforced",
    "provider_calls_requested"}
REVIEW_FIELDS = {"schema", "passed", "artifact_kind", "candidate_id", "attempt_id", "source_commit",
    "request_sha256", "failure_sha256", "failure_stage", "actual_fits"}
STAGES = {"process_start", "pre_fit", "fit", "post_fit", "unknown"}


def _hash(value):
    if type(value) is not str or len(value) != 64 or any(x not in "0123456789abcdef" for x in value):
        raise ValueError("failure digest required")


def prepare_input(bindings, batch, repo, now, *, prospective_binding=None):
    """Trusted Supervisor supplies an immutable failed-attempt review and budget."""
    if type(bindings) is not dict or set(bindings) != FAILED_ROLES:
        raise ValueError("exact failure file roles required; no numerical artifacts")
    data = {role: c._read(binding) for role, binding in bindings.items()}
    feedback, review, failure, request = [data[name] for name in ("feedback", "review", "failure", "request")]
    if (type(review) is not dict or set(review) != REVIEW_FIELDS
            or review["schema"] != "controller_failure_review_v1" or review["passed"] is not True
            or review["artifact_kind"] != "failure" or review["failure_stage"] not in STAGES):
        raise ValueError("independent factual failure review required")
    if type(failure) is not dict or set(failure) != FAILURE_FIELDS or set(request) != worker.REQUEST_FIELDS:
        raise ValueError("exact native worker failure/request required")
    if type(request["module"]) is not str or not re.fullmatch(r"experiments\.nfl_ingame_[a-z0-9_]+", request["module"]):
        raise ValueError("reviewed in-game sibling module required")
    if type(request["files"]) is not dict:
        raise ValueError("exact failed source mapping required")
    branches = [item for item in batch.snapshot()["branches"] if item["attempt_id"] == feedback["attempt_id"]]
    if len(branches) != 1:
        raise ValueError("one original failed branch required")
    branch = branches[0]
    failure_sha = bindings["failure"]["sha256"]
    if (branch["stage"] != "controller_feedback_ready" or branch["feedback_packet"] != feedback
            or branch["feedback_packet_sha256"] != c._digest(feedback)
            or branch["claim_id"] is None or branch["execution_outcome"] != feedback["execution_outcome"]
            or branch["execution_receipt_sha256"] != failure_sha or branch["review_sha256"] != bindings["review"]["sha256"]
            or branch["review_decision"] != "REVERT" or branch["independently_reviewed"] is not True
            or feedback["independently_reviewed"] is not True or feedback["review_decision"] != "REVERT"
            or feedback["execution_outcome"] != "failed"
            or feedback["execution_outcome"] != failure["outcome"]
            or feedback["review_sha256"] != bindings["review"]["sha256"]
            or feedback["execution_receipt_sha256"] != failure_sha or feedback["scorecard_sha256"] != failure_sha
            or review["failure_sha256"] != failure_sha):
        raise ValueError("reviewed failed branch/receipt binding drift")
    if c._feedback_protocol(feedback) != 4 or feedback["learning_checkpoint"]["validity"]["status"] != "invalid":
        raise ValueError("failure requires explicit invalid-performance v4 evidence")
    for key in ("attempt_id", "candidate_id", "source_commit"):
        expected = request[key]
        if review[key] != expected or (key != "source_commit" and feedback[key] != expected):
            raise ValueError("failure attempt/candidate/source drift")
    if (failure["attempt_id"] != request["attempt_id"] or failure["source_commit"] != request["source_commit"]
            or failure["request_sha256"] != bindings["request"]["sha256"] or review["request_sha256"] != bindings["request"]["sha256"]
            or failure["runtime_pair_sha256"] != request["runtime_pair_sha256"]
            or failure["memory_sha256"] != request["memory_sha256"] or request["memory_sha256"] != bindings["memory"]["sha256"]
            or request["memory"] != bindings["memory"]["path"]
            or branch["candidate_id"] != request["candidate_id"]
            or branch["runner_sha256"] != feedback["runner_sha256"] or branch["spec_sha256"] != request["spec_sha256"]
            or branch["runtime_pair_sha256"] != request["runtime_pair_sha256"]
            or branch["memory_snapshot_sha256"] != request["memory_sha256"]):
        raise ValueError("failure request/runtime/memory drift")
    for key in ("max_fits", "max_wall_seconds"):
        limit = 4 if key == "max_fits" else 900
        if type(request[key]) is not int or not 1 <= request[key] <= limit:
            raise ValueError("failure request resource ceiling")
    if (type(review["actual_fits"]) is not int or not 0 <= review["actual_fits"] <= request["max_fits"]
            or type(failure["fits_reserved"]) is not int or failure["fits_reserved"] != request["max_fits"]
            or review["failure_stage"] in {"process_start", "pre_fit"} and review["actual_fits"] != 0):
        raise ValueError("failure stage/actual fit evidence drift")
    error_ok = (failure["error"] is None and type(failure["exit_code"]) is int and failure["exit_code"] != 0
                or type(failure["error"]) is str and bool(failure["error"].strip()) and len(failure["error"]) <= 8192)
    if (failure["exit_code"] is not None and type(failure["exit_code"]) is not int
            or not error_ok
            or type(failure["wall_seconds"]) not in {int, float} or failure["wall_seconds"] < 0
            or type(failure["sampled_peak_rss_kib"]) is not int or failure["sampled_peak_rss_kib"] < 0
            or type(failure["rss_limit_kib"]) is not int or failure["rss_limit_kib"] != 1048576
            or failure["rss_limit_enforcement"] != "one-second polling; not OS-hard isolation"
            or failure["metrics_independently_reviewed"] is not False or failure["network_isolation_enforced"] is not False
            or type(failure["provider_calls_requested"]) is not int or failure["provider_calls_requested"] != 0):
        raise ValueError("failure resource/error/claim evidence drift")
    for key in ("stdout_sha256", "stderr_sha256", "runtime_pair_sha256"):
        _hash(failure[key])
    output = Path(failure["output"])
    if not output.is_absolute() or output.resolve() != output:
        raise ValueError("failure output path drift")
    expected_command = [request["python"], "-B", "-m", request["module"], "--source-root", str(worker.TRAIN), "--output", str(output)]
    if failure["command"] != expected_command:
        raise ValueError("failure command drift")
    runner = "research/market_rsi/" + request["module"].replace(".", "/") + ".py"
    if not request["files"] or request["files"].get(runner) != feedback["runner_sha256"]:
        raise ValueError("failed source binding changed")
    for name, expected in request["files"].items():
        path = Path(repo) / name
        if Path(name).is_absolute() or ".." in Path(name).parts or path.resolve() != path or c.sha(path) != expected:
            raise ValueError("source byte drift")
        original = subprocess.check_output(["git", "show", request["source_commit"] + ":" + name], cwd=repo)
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError("source commit drift")
    if c.sha(request["python"]) != request["python_sha256"]:
        raise ValueError("runtime byte drift")
    ranked = feedback["next_pool_selection_hint"]["ranked_research_parents"]
    if any(item["candidate_sha256"] == feedback["runner_sha256"] and c.parent_eligibility(item, 4) for item in ranked):
        raise ValueError("failed candidate cannot be a predictive parent")
    binding = c._prospective_binding(prospective_binding)
    c.check_budget(data["authority"], now, prospective_binding=binding)
    attempts = [item for item in data["authority"]["attempts"] if item["attempt_id"] == request["attempt_id"]]
    if (len(attempts) != 1 or attempts[0]["actual_fits"] != review["actual_fits"]
            or attempts[0]["fits_reserved"] != failure["fits_reserved"]
            or attempts[0]["status"] not in {"closed", "failed", "interrupted"}):
        raise ValueError("reviewed actual fits/outer attempt drift")
    result = {"schema": "controller_failure_feedback_input_v1", "bindings": bindings, "feedback": feedback,
        "numerical": None, "supplement": None, "failure": failure, "failure_review": review,
        "legacy_non_predictive_artifact_alias": {"field": "scorecard_sha256", "artifact_kind": "failure", "sha256": failure_sha},
        "interpretation": "Execution failure is not scientific refutation. No valid predictions or scores are supplied; actual fit count is independently reviewed.",
        "omitted_from_prompt": [], **{key: data[key] for key in ("memory", "history", "pool", "authority", "overhead")}}
    if binding is not None:
        result["prospective_budget_binding"] = binding
    c._digest(result)
    return c._json(json.dumps(result, allow_nan=False))
