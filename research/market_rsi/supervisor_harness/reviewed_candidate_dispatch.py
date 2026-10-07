"""Reviewed original decision -> native worker; no execution of model recipes.

Supervisor owns authoring/admission and outer ledger synchronization. This
helper neither selects algorithms nor provides arbitrary-code containment.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import math
import os
from pathlib import Path

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import continuous_discovery_batch as recorder
from supervisor_harness import opened_train_discovery_worker as w


REVIEW_FIELDS = {"schema", "passed", "batch_id", "decision_sha256", "request_sha256",
                "authority_sha256", "research_parent_sha256", "comparison_incumbent_sha256"}


def _identities():
    return {name: w.sha(Path(module.__file__).resolve()) for name, module in
            (("dispatcher", __import__(__name__, fromlist=["x"])),
             ("consumer", c), ("worker", w), ("recorder", recorder))}


def _file(path):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        raise FileNotFoundError(path)
    if not path.is_absolute() or path.resolve() != path or not path.is_file():
        raise ValueError("regular original artifact required; no symlinks")
    return c._json(path.read_bytes())


def _branch(batch, attempt):
    state = batch.snapshot()
    branches = [item for item in state["branches"] if item["attempt_id"] == attempt]
    if len(branches) != 1:
        raise ValueError("exact selected native branch required")
    return state, branches[0]


def _receipt(batch, request):
    """Reconcile only a complete durable receipt; never poll/relaunch a process."""
    attempt = request["attempt_id"]
    state, branch = _branch(batch, attempt)
    directory = batch.root / "worker"
    native = _file(directory / f"{attempt}.request.json")
    receipt_path = directory / f"{attempt}.receipt.json"
    receipt = _file(receipt_path)
    command = [request["python"], "-B", "-m", request["module"],
               "--source-root", str(w.TRAIN), "--output", str(batch.root / "runs" / attempt)]
    expected = {"attempt_id": attempt, "request_sha256": w.sha(directory / f"{attempt}.request.json"),
        "source_commit": request["source_commit"], "command": command,
        "runtime_pair_sha256": request["runtime_pair_sha256"], "memory_sha256": request["memory_sha256"],
        "fits_reserved": request["max_fits"], "output": str(batch.root / "runs" / attempt),
        "rss_limit_kib": 1048576, "rss_limit_enforcement": "one-second polling; not OS-hard isolation",
        "metrics_independently_reviewed": False, "network_isolation_enforced": False,
        "provider_calls_requested": 0}
    if (c._digest(native) != c._digest(request) or branch["claim_id"] != attempt + "-claim"
            or branch["runner_sha256"] != request["files"]["research/market_rsi/" + request["module"].replace(".", "/") + ".py"]
            or branch["spec_sha256"] != request["spec_sha256"]
            or branch.get("runtime_pair_sha256") != request["runtime_pair_sha256"]
            or branch.get("memory_snapshot_sha256") != request["memory_sha256"]
            or any(c._digest(receipt.get(key)) != c._digest(value) for key, value in expected.items())
            or set(receipt) != set(expected) | {"outcome", "exit_code", "error", "wall_seconds",
                "sampled_peak_rss_kib", "stdout_sha256", "stderr_sha256"}):
        raise ValueError("native receipt/request/claim identity drift")
    for field in ("wall_seconds", "sampled_peak_rss_kib"):
        if type(receipt[field]) not in (int, float) or not math.isfinite(receipt[field]) or receipt[field] < 0:
            raise ValueError("invalid measured native resource receipt")
    if type(receipt["sampled_peak_rss_kib"]) is not int:
        raise ValueError("native RSS measurement must be integer KiB")
    if (receipt["exit_code"] is not None and type(receipt["exit_code"]) is not int) or (
            receipt["error"] is not None and type(receipt["error"]) is not str):
        raise ValueError("native exit/error receipt type drift")
    for name in ("stdout", "stderr"):
        c._read({"path": str(directory / f"{attempt}.{name}"), "sha256": receipt[name + "_sha256"]}, True)
    process_path = directory / f"{attempt}.process.json"
    if type(receipt["exit_code"]) is int and not process_path.exists():
        raise ValueError("native completed child process evidence missing")
    if process_path.exists():
        process = _file(process_path)
        if (set(process) != {"pid", "command", "source_commit"} or type(process["pid"]) is not int
                or process["pid"] <= 0 or process["command"] != command
                or process["source_commit"] != request["source_commit"]):
            raise ValueError("original worker process identity drift")
    if receipt["outcome"] == "succeeded":
        if type(receipt["exit_code"]) is not int or receipt["exit_code"] != 0 or receipt["error"] is not None or not process_path.exists():
            raise ValueError("incomplete successful native execution")
        manifest = _file(Path(receipt["output"]) / "manifest.json")
        if manifest.get("complete") is not True or type(manifest.get("model_fits")) is not int or manifest["model_fits"] != request["max_fits"]:
            raise ValueError("incomplete fit manifest")
        for name in ("pre_score_lock", "input_receipts", "exclusions", "predictions", "scorecard"):
            path = Path(receipt["output"]) / (name + (".csv" if name == "predictions" else ".json"))
            c._read({"path": str(path), "sha256": manifest[name + "_sha256"]}, True)
    elif receipt["outcome"] != "failed" or not (
            (type(receipt["exit_code"]) is int and receipt["exit_code"] != 0)
            or (type(receipt["error"]) is str and receipt["error"].strip())):
        raise ValueError("uncertain failed execution; no retry")
    batch.mark_execution_terminal(attempt, claim_id=attempt + "-claim",
        outcome=receipt["outcome"], execution_receipt_sha256=w.sha(receipt_path))
    return receipt


def dispatch(batch, request_binding, review_binding, decision_directory, authority_binding,
             repo, *, now=None, prospective_binding=None):
    """One reviewed native handoff. A durable record is an at-most-once fence."""
    request = c._read(request_binding)
    review = c._read(review_binding)
    if set(request) != w.REQUEST_FIELDS:
        raise ValueError("exact reviewed request required")
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", request["attempt_id"]):
        raise ValueError("bounded attempt ID required")
    decision_directory = Path(decision_directory)
    if not decision_directory.is_absolute() or decision_directory.resolve() != decision_directory:
        raise ValueError("original decision directory required")
    packet = _file(decision_directory / "input.json")
    claim = {"input_sha256": c._digest(packet), "schema_sha256": c._digest(c.SCHEMA),
             "cli_sha256": c.CLI_SHA, **c._identity(packet.get("evidence_session"),
                packet.get("schema") == "controller_failure_feedback_input_v1")}
    if "prospective_budget_binding" in packet:
        claim["prospective_budget_binding_sha256"] = c._digest(packet["prospective_budget_binding"])
    if (_file(decision_directory / "claim.json") != claim
            or _file(decision_directory / "schema.json") != c.SCHEMA):
        raise ValueError("original Controller claim/schema drift")
    decision = c._recover(decision_directory, packet)
    state, branch = _branch(batch, request["attempt_id"])
    expected_review = {"schema": "reviewed_candidate_request_v1", "passed": True,
        "batch_id": state["batch_id"], "decision_sha256": c._digest(decision),
        "request_sha256": request_binding["sha256"], "authority_sha256": authority_binding["sha256"],
        "research_parent_sha256": decision["actual_parent_sha256"],
        "comparison_incumbent_sha256": decision["comparison_incumbent_sha256"]}
    if (set(review) != REVIEW_FIELDS or c._digest(review) != c._digest(expected_review)
            or decision["action"] != "propose_candidate" or request["candidate_id"] != decision["candidate_id"]
            or branch["candidate_id"] != request["candidate_id"]
            or branch["controller_decision_sha256"] != c._digest(decision)
            or branch.get("research_parent_sha256") != decision["actual_parent_sha256"]
            or branch.get("comparison_incumbent_sha256") != decision["comparison_incumbent_sha256"]):
        raise ValueError("decision/review/selected lineage drift or closed action")
    directory = batch.root / "dispatch"
    directory.mkdir(exist_ok=True)
    if directory.resolve() != directory:
        raise ValueError("dispatch directory symlink")
    descriptor = os.open(directory / (request["attempt_id"] + ".lock"),
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / (request["attempt_id"] + ".json")
        record = {"schema": "reviewed_candidate_dispatch_v1", "sources": _identities(),
            "batch_id": state["batch_id"], "request": request_binding, "review": review_binding,
            "authority": authority_binding, "decision_directory": str(decision_directory),
            "decision_sha256": c._digest(decision), "input_sha256": c._digest(packet),
            "prospective_binding_sha256": c._digest(prospective_binding),
            "research_parent_sha256": branch["research_parent_sha256"],
            "comparison_incumbent_sha256": branch["comparison_incumbent_sha256"]}
        if path.exists():
            if c._digest(_file(path)) != c._digest(record):
                raise ValueError("original dispatch/source binding drift")
            try:
                return _receipt(batch, request)
            except FileNotFoundError as error:
                raise RuntimeError("incomplete original claim; inspect without retry") from error
        state, branch = _branch(batch, request["attempt_id"])
        if branch["claim_id"] is not None or branch["stage"] != "controller_selected":
            raise RuntimeError("unbound existing worker claim; no retry")
        authority = c._read(authority_binding)
        if c._digest(packet.get("prospective_budget_binding")) != c._digest(prospective_binding):
            raise ValueError("original prospective packet binding drift")
        if authority.get("batch_id") != state["batch_id"] or authority["start_utc"] != state["start_utc"] or authority["deadline_utc"] != state["deadline_utc"]:
            raise ValueError("outer/native batch identity drift")
        c.check_budget(authority, now or datetime.now(timezone.utc), prospective_binding=prospective_binding)
        if (any(authority.get(key, False) is not False for key in c.FLAGS)
                or any(item["attempt_id"] == request["attempt_id"] for item in authority["attempts"])):
            raise ValueError("permission expansion or already reserved outer attempt")
        if request["max_fits"] > decision["resources"]["fits"] or request["max_wall_seconds"] > decision["resources"]["seconds"]:
            raise ValueError("reviewed request exceeds original decision resources")
        for name in ("python", "memory"):
            verification_path = str(Path(request[name]).resolve(strict=True)) if name == "python" else request[name]
            c._read({"path": verification_path, "sha256": request[name + "_sha256"]}, True)
        w.validate(request, repo)
        # Short local fence: stale outer snapshots cannot reuse consumed slots.
        # This accounts reservations only; it does not invent measured fits.
        fd = os.open(directory / ".admission.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a+") as admission:
            fcntl.flock(admission, fcntl.LOCK_EX)
            recorded = {item.stem for item in directory.glob("*.json")}
            state = batch.snapshot()
            consumed = recorded | {item["attempt_id"] for item in state["branches"] if item["claim_id"] is not None}
            known = {item["attempt_id"] for item in authority["attempts"]}
            pending = consumed - known
            active = {item["attempt_id"] for item in authority["attempts"]
                      if item["status"] in {"claimed", "running", "execution_claimed", "execution_reserved"}}
            active |= {item["attempt_id"] for item in state["branches"]
                       if item["attempt_id"] in consumed and item["execution_outcome"] is None}
            active |= recorded - {item["attempt_id"] for item in state["branches"]}
            if (len(authority["attempts"]) + len(pending) >= authority["limits"]["attempts"]
                    or sum(item["fits_reserved"] for item in authority["attempts"]) + 4 * len(pending) + 4 > authority["limits"]["statistical_fits"]
                    or len(active) >= authority["limits"]["live_candidate_processes"]):
                raise ValueError("stale outer snapshot consumed local attempt/fit/concurrency allowance")
            c.save(path, record)
        w.execute(batch, request, repo)
        return _receipt(batch, request)
