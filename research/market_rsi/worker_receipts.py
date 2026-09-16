"""Read completed worker receipts before handing a proposal/code to the next stage.

No dispatch, imports of candidate code, or data-admission authority lives here.
These checks assume runner-owned storage: hashes are not signatures against a
malicious host. The outer supervisor must own claims and independently admit the
task/source/phase/deadline. A successful receipt check never replaces that gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import stat
from pathlib import Path

from coder_probe import inspect_events
from coder_worker import assess_code, prepare_code_request
from glm_canary import MODEL, HF_MODEL, RATES, cost
from market_rsi import digest, file_hash, identifier
from paid_budget import money
from researcher_worker import (CONTROLLER_REASONING_EFFORT, CONTROLLER_TEMPERATURE,
                               GLMTransport, assess_response)


ROOT = Path(__file__).parent
MAX_FILE_BYTES = 16 * 1024 * 1024


def read_regular(path, max_bytes=MAX_FILE_BYTES):
    """Bound reads and refuse symlink paths; never follow caller-selected links."""
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink receipt path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > max_bytes:
            raise ValueError("bounded regular receipt required")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(max_bytes + 1)
        after = os.fstat(fd)
        if (len(raw) > max_bytes or meta.st_size != after.st_size
                or meta.st_mtime_ns != after.st_mtime_ns or len(raw) != after.st_size):
            raise ValueError("receipt changed while reading")
        return raw
    finally:
        os.close(fd)


class Receipts:
    """Local read-set, revalidated immediately before an outer-stage handoff."""
    def __init__(self):
        self.files = {}
        self.absent_paths = set()

    def absent(self, path):
        self.absent_paths.add(str(Path(path).absolute()))

    def read(self, path):
        path = str(Path(path).absolute())
        raw = read_regular(path)
        self.files[path] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    def revalidate(self):
        for path in self.absent_paths:
            if Path(path).exists() or Path(path).is_symlink():
                raise ValueError("job failed after its completed receipts were read")
        for path, sha in self.files.items():
            if hashlib.sha256(read_regular(path)).hexdigest() != sha:
                raise ValueError("completed receipt mutated after verification")

    def commitment(self):
        # Runner-only paths: never include this object in a model prompt.
        content = {"files": dict(sorted(self.files.items())), "absent_paths": sorted(self.absent_paths)}
        return dict(content, sha256=digest(content))


def _directory(path):
    path = Path(path).absolute()
    identifier(path.name)
    if not path.is_dir() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("runner-owned regular job directory required")
    if (path / "failure.json").exists() or (path / "failure.json").is_symlink():
        raise ValueError("failed job cannot become a completed handoff")
    return path


def _packet(value, fields):
    if (not isinstance(value, dict) or set(value) != fields | {"packet_sha256"}
            or digest({k: v for k, v in value.items() if k != "packet_sha256"}) != value["packet_sha256"]):
        raise ValueError("bound worker packet required")


def _mode(live, experiment):
    if type(live) is not bool or (not live and not experiment.startswith("fixture-")):
        raise ValueError("mock receipts require an explicit fixture experiment")


def _elapsed(value, maximum):
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value < maximum:
        raise ValueError("terminal wall allowance not verified")


def read_research_terminal(directory, prepared, budget, *, expected_live):
    """Bind exact stored response to the request, claim and append-only metering.

    `prepared` must come from the supervisor's already-admitted task/common/owned
    history, not from the candidate. No caller-supplied response string is used.
    """
    _packet(prepared, {"messages", "audit"})
    p = copy.deepcopy(prepared)
    audit = p["audit"]
    _mode(expected_live, audit["experiment_id"])
    if digest(p["messages"]) != audit["messages_sha256"]:
        raise ValueError("research message binding failed")
    directory, reads = _directory(directory), Receipts()
    reads.absent(directory / "failure.json")
    claim, request, response, assessment = [reads.read(directory / name) for name in
        ("claim.json", "request.json", "response.json", "assessment.json")]
    limits = audit["resource_limits"]
    if (claim["audit"] != audit or claim["code_sha256"] != file_hash(ROOT / "researcher_worker.py")
            or claim["live_transport"] is not expected_live or claim["model"] != MODEL
            or claim["num_samples"] != 1 or claim["sampling_retries"] != 0
            or claim["seed"] != 23 or claim["temperature"] != CONTROLLER_TEMPERATURE
            or claim["reasoning_effort"] != CONTROLLER_REASONING_EFFORT or claim["tools"] != []
            or claim["max_input_tokens"] != limits["max_input_tokens"]
            or claim["max_output_tokens"] != limits["max_output_tokens"]
            or not isinstance(claim["nonce"], str) or len(claim["nonce"]) != 32
            or request["audit"] != audit or request["messages"] != p["messages"]
            or request["rates"] != RATES or request["max_output_tokens"] != limits["max_output_tokens"]):
        raise ValueError("research claim/request/source mismatch")
    ids, outputs = request["token_ids"], response["output_tokens"]
    if (not isinstance(ids, list) or not ids or not isinstance(outputs, list)
            or any(type(t) is not int or t < 0 for t in ids + outputs)
            or len(ids) > limits["max_input_tokens"] or len(outputs) > limits["max_output_tokens"]
            or not isinstance(response["text"], str)):
        raise ValueError("invalid terminal token evidence")
    if expected_live and (request["tokenizer_repo"] != HF_MODEL
            or request["tokenizer_revision"] != GLMTransport.TOKENIZER_REVISION
            or request["chat_template_sha256"] != GLMTransport.TEMPLATE_SHA256
            or response["provider"].get("reported_model") not in {MODEL, HF_MODEL}):
        raise ValueError("live research model/tokenizer changed")
    if expected_live:
        from glm_process_receipts import verify_glm_processes
        if claim.get("transport_source_hashes") != {n: file_hash(ROOT / n) for n in
                ("bounded_process.py", "glm_process_worker.py", "glm_process_receipts.py")}:
            raise ValueError("bounded GLM transport source changed")
        verify_glm_processes(directory, p, request, response, reads)
    upper = cost(len(ids), limits["max_output_tokens"])
    charge = cost(len(ids), len(outputs), response["cached_input_tokens"])
    state = budget.snapshot()  # Validates the complete journal, not a saved summary.
    job = state["jobs"].get(directory.name, {})
    if (state["experiment_id"] != audit["experiment_id"] or job.get("state") != "metered_terminal"
            or job["input_sha256"] != digest(request) or job["provider"] != "tinker"
            or job["bucket"] != ("final" if audit["phase"] == "transfer" else "learning")
            or money(job["upper_usd"]) != upper or money(request["upper_usd"]) != upper
            or money(job["metered_usd"]) != charge):
        raise ValueError("research request has no matching terminal budget receipt")
    metering = reads.read(budget.root / f"{directory.name}.metering.json")
    if (digest(metering) != job["receipt_sha256"] or metering["terminal"] is not True
            or metering["provider"] != "tinker" or metering["model"] != MODEL
            or metering["input_tokens"] != len(ids) or metering["output_tokens"] != len(outputs)
            or metering["cached_input_tokens"] != response["cached_input_tokens"]
            or money(metering["metered_cost_usd"]) != charge or metering["rates"] != RATES
            or metering["provider_receipt"] != response["provider"]):
        raise ValueError("research terminal metering/response mismatch")
    elapsed = metering["elapsed_seconds"]
    if type(elapsed) not in {int, float} or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("invalid terminal research wall evidence")
    fresh = assess_response(response["text"], audit, finish_reason=response.get("finish_reason"))
    wall = assessment.get("wall_limit_exceeded")
    if (type(wall) is not bool or (elapsed > limits["max_wall_seconds"] and not wall)
            or assessment.get("valid") is not (fresh["valid"] and not wall)
            or assessment.get("live_transport") is not expected_live
            or assessment.get("research_score") is not None
            or assessment.get("reason") != fresh.get("reason")
            or assessment.get("proposal") != fresh.get("proposal")
            or assessment.get("selection") != fresh.get("selection")
            or money(assessment["metered_cost_usd"]) != charge):
        raise ValueError("invalid or altered first research response")
    reads.revalidate()
    valid = fresh["valid"] and not wall and elapsed < limits["max_wall_seconds"]
    return {"prepared": p, "raw_response": response["text"], "proposal": fresh.get("proposal"),
            "job_id": directory.name, "metered_usd": str(charge), "receipts": reads,
            "selection": fresh.get("selection"),
            "valid": valid, "terminal": True,
            "failure_kind": None if valid else ("wall_limit" if wall or elapsed >= limits["max_wall_seconds"]
                else fresh.get("reason", "invalid_proposal")),
            "scientific_admission": False}


def read_research_job(directory, prepared, budget, *, expected_live):
    result = read_research_terminal(directory, prepared, budget, expected_live=expected_live)
    if not result["valid"] or prepared["audit"].get("response_kind") is not None:
        raise ValueError("invalid first research response cannot proceed to coding")
    return result


def code_request_from_job(directory, prepared, budget, runtime, limits, *, expected_live):
    research = read_research_job(directory, prepared, budget, expected_live=expected_live)
    coding = prepare_code_request(prepared, research["raw_response"], runtime, limits)
    return research, coding


def read_code_terminal(directory, research, prepared, *, expected_live, expected_identity):
    """Read source as text, checking the exact terminal event and subscribed pin.

    The expected identity is supervisor-frozen configuration, not an identity
    copied from this job's runtime.json. No execution is done on this host.
    """
    _packet(prepared, {"prompt", "audit"})
    prepared = copy.deepcopy(prepared)
    audit = prepared["audit"]
    _mode(expected_live, audit["experiment_id"])
    runtime = json.loads(prepared["prompt"])["runtime"]
    rebuilt = prepare_code_request(research["prepared"], research["raw_response"], runtime, audit["limits"])
    if rebuilt != prepared:
        raise ValueError("coder input is not the preserved first research response")
    research["receipts"].revalidate()
    directory, reads = _directory(directory), Receipts()
    reads.absent(directory / "failure.json")
    claim, request, identity, dispatch, response, usage, assessment = [reads.read(directory / name) for name in
        ("claim.json", "request.json", "runtime.json", "dispatch.json", "response.json",
         "subscription-usage.json", "assessment.json")]
    sha = file_hash(ROOT / "coder_worker.py")
    dependencies = {name: file_hash(ROOT / name) for name in
                    ("coder_probe.py", "researcher_worker.py", "market_rsi.py", "bounded_process.py")}
    if (claim["audit"] != audit or claim["code_sha256"] != sha or claim["transport_code_sha256"] != sha
            or claim["dependencies"] != dependencies or claim["live"] is not expected_live
            or claim["logical_dispatches"] != 1 or claim["automatic_reinvocation"] is not False
            or claim["scored"] is not False or request != prepared or identity != expected_identity
            or dispatch["identity_sha256"] != digest(identity)):
        raise ValueError("coder source/request/runtime claim mismatch")
    if expected_live and identity["authentication"] != "chatgpt":
        raise ValueError("subscribed coding authentication required")
    if not expected_live and identity.get("authentication") != "fixture":
        raise ValueError("mock coding identity required")
    checks = inspect_events(response["events"])
    messages = [event["item"].get("text") for line in response["events"].splitlines() if line.strip()
                for event in [json.loads(line)] if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "agent_message"]
    fresh = assess_code(response["body"], audit["entrypoint"], audit["limits"]["max_code_bytes"])
    if (checks["completed_once"] is not True or checks["event_failures"] != 0
            or checks["unexpected_item_types"] or len(messages) != 1
            or json.loads(messages[0]) != response["body"]
            or assessment.get("event_checks") != checks
            or assessment.get("response_matches_saved_event") is not True
            or assessment.get("source_sha256") != fresh.get("source_sha256")
            or assessment.get("executed") is not False or assessment.get("scored") is not False):
        raise ValueError("incomplete or altered coding output; never choose another answer")
    terminal_usage = checks["usage"]
    if (not isinstance(terminal_usage, dict) or any(type(terminal_usage.get(k)) is not int or terminal_usage[k] < 0
                                                 for k in ("input_tokens", "output_tokens"))
            or usage["usage"] != terminal_usage or usage["authentication"] != identity["authentication"]
            or usage["model_requested"] != identity["model"] or usage["allocated_cost_usd"] is not None
            or usage["economic_cost_complete"] is not False):
        raise ValueError("coding subscription evidence missing or misreported")
    elapsed = [assessment["elapsed_seconds"], usage["elapsed_seconds"]]
    if any(type(t) not in {int, float} or not math.isfinite(t) or t < 0 for t in elapsed):
        raise ValueError("invalid terminal coding wall evidence")
    within_wall = all(t < audit["limits"]["wall_seconds"] for t in elapsed)
    valid = (fresh["valid"] and response["exit_code"] == 0
             and response.get("transport_failure") is None and within_wall)
    if assessment.get("valid") is not valid:
        raise ValueError("terminal coding assessment differs from preserved evidence")
    if expected_live:
        verify_coder_preflights(directory, identity, audit["limits"], reads)
        # Actual CLI path records both streams as well as the parsed response.
        actual_events = read_regular(directory / "events.jsonl").decode()
        if actual_events != response["events"] or json.loads(reads.read(directory / "raw-answer.json")["text"]) != response["body"]:
            raise ValueError("CLI source files differ from recorded response")
        reads.files[str(directory / "events.jsonl")] = hashlib.sha256(actual_events.encode()).hexdigest()
        transport = reads.read(directory / "transport.json")
        if (transport["process_reaped"] is not True or transport["exit_code"] != response["exit_code"]
                or transport["failure_type"] != response.get("transport_failure")):
            raise ValueError("exact coding process termination not verified")
    reads.revalidate()
    research["receipts"].revalidate()
    return {"prepared": prepared, "source": response["body"].get("code") if isinstance(response["body"], dict) else None,
            "source_sha256": fresh.get("source_sha256"),
            "job_id": directory.name, "entrypoint": audit["entrypoint"], "receipts": reads,
            "subscription_usage": usage, "events": response["events"], "response_body": response["body"],
            "valid": valid, "terminal": True, "failure_kind": None if valid else
                ("wall_limit" if not within_wall else "coding_transport" if response["exit_code"] != 0
                 or response.get("transport_failure") is not None else "invalid_or_unsupported_code"),
            "executed": False, "scientific_admission": False}


def read_code_job(directory, research, prepared, *, expected_live, expected_identity):
    result = read_code_terminal(directory, research, prepared, expected_live=expected_live,
                                expected_identity=expected_identity)
    if not result["valid"]:
        raise ValueError("invalid first coding response cannot proceed to execution")
    return result


def verify_coder_preflights(directory, identity, limits, reads):
    """Re-read the bounded, no-inference CLI identity checks; never invoke CLI."""
    directory = Path(directory).absolute()
    total_elapsed = 0
    for operation, suffix in (("version", ["--version"]), ("auth", ["login", "status"])):
        root = directory / (operation + "-process")
        claim, receipt = reads.read(root / "claim.json"), reads.read(root / "receipt.json")
        blobs = {}
        for name in ("input", "stdout", "stderr"):
            path = root / (name + ".bin")
            blobs[name] = read_regular(path, max_bytes=65536)
            reads.files[str(path)] = hashlib.sha256(blobs[name]).hexdigest()
        wall = claim.get("wall_seconds")
        env_names = claim.get("environment_names")
        if (claim["command_sha256"] != digest([identity["cli_path"], *suffix])
                or blobs["input"] != b"" or claim["input_sha256"] != hashlib.sha256(b"").hexdigest()
                or not isinstance(env_names, list) or env_names != sorted(set(env_names))
                or not set(env_names) <= {"HOME", "PATH", "TMPDIR", "LANG", "USER"}
                or claim["supervisor_source_sha256"] != file_hash(ROOT / "bounded_process.py")
                or type(wall) not in (int, float) or not math.isfinite(wall)
                or not 0 < wall <= min(10, limits["wall_seconds"] - 2)
                or claim["reap_seconds"] != 2 or claim["remote_cancellation_established"] is not False
                or claim["max_stdout_bytes"] != 65536 or claim["max_stderr_bytes"] != 65536):
            raise ValueError("coding readiness command/environment/bounds changed")
        elapsed = receipt.get("elapsed_seconds")
        if (receipt["process_reaped"] is not True or receipt["exit_code"] != 0
                or receipt["failure"] is not None or receipt["output_complete"] is not True
                or receipt["input_complete"] is not True or receipt["input_bytes_written"] != 0
                or type(receipt["pid"]) is not int or receipt["pid"] <= 0
                or type(elapsed) not in (int, float) or not math.isfinite(elapsed)
                or not 0 <= elapsed <= wall + 2
                or receipt["remote_request_terminal"] is not None
                or receipt["remote_cancellation_established"] is not False
                or receipt["unused_budget_released"] is not False):
            raise ValueError("coding readiness process is not independently terminal")
        total_elapsed += elapsed
        for name in ("stdout", "stderr"):
            if (receipt[name + "_bytes"] != len(blobs[name])
                    or receipt[name + "_sha256"] != reads.files[str(root / (name + ".bin"))]):
                raise ValueError("coding readiness output changed")
        if operation == "version" and blobs["stdout"].decode().strip() != identity["cli_version"]:
            raise ValueError("coding readiness version differs from pinned identity")
        if operation == "auth" and b"Logged in using ChatGPT" not in blobs["stdout"] + blobs["stderr"]:
            raise ValueError("coding readiness did not confirm subscribed authentication")
    if total_elapsed >= limits["wall_seconds"]:
        raise ValueError("coding readiness exhausted original request allowance")
