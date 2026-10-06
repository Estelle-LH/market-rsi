"""Trusted reviewed source -> native selection -> existing once-only worker.

Semantic scientific-plan correspondence is independently reviewed by the
Supervisor, not inferred from model text or a candidate source hash. This
adapter does not author code, choose science, or independently review metrics.
"""
from __future__ import annotations

import fcntl
from datetime import datetime, timezone
import os
from pathlib import Path
import re

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import reviewed_candidate_dispatch as d
from supervisor_harness import opened_train_discovery_worker as w


CONTRACT_FIELDS = {"schema", "decision_sha256", "candidate_id", "question_id",
    "hypothesis", "recipe", "expected_evidence", "actual_parent_sha256",
    "comparison_incumbent_sha256", "resources"}
REVIEW_FIELDS = d.REVIEW_FIELDS | {"contract_sha256", "selection_sha256",
    "source_commit", "files", "semantic_source_matches_decision"}
SELECTION_FIELDS = {"attempt_id", "candidate_id", "controller_decision_sha256",
    "research_parent_sha256", "allocation", "method_family",
    "hypothesis_digest_sha256", "question_id", "question_digest_sha256",
    "predeclared_rule_sha256", "resource_hint"}


def _original(directory):
    directory = Path(directory)
    if not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError("original decision directory required")
    packet = d._file(directory / "input.json")
    claim = {"input_sha256": c._digest(packet), "schema_sha256": c._digest(c.SCHEMA),
        "cli_sha256": c.CLI_SHA, **c._identity(packet.get("evidence_session"),
            packet.get("schema") == "controller_failure_feedback_input_v1")}
    if "prospective_budget_binding" in packet:
        claim["prospective_budget_binding_sha256"] = c._digest(packet["prospective_budget_binding"])
    if (d._file(directory / "claim.json") != claim
            or d._file(directory / "schema.json") != c.SCHEMA):
        raise ValueError("original Controller claim/schema drift")
    return packet, c._recover(directory, packet)


def _selected(batch, selection, decision):
    state = batch.snapshot()
    branches = [item for item in state["branches"]
                if item["attempt_id"] == selection["attempt_id"]]
    if len(branches) > 1:
        raise ValueError("ambiguous native branch")
    if branches and (any(c._digest(branches[0].get(key)) != c._digest(value)
                         for key, value in selection.items())
                     or branches[0].get("comparison_incumbent_sha256")
                     != decision["comparison_incumbent_sha256"]):
        raise ValueError("original selected branch/lineage drift")
    return state, branches


def handoff(batch, selection, request_binding, review_binding, contract_binding,
            decision_directory, authority_binding, repo, *, now=None,
            prospective_binding=None):
    """Check Supervisor admission, select once, and return the native receipt.

    A singleton is permitted only by the recorder's existing explicit final
    singleton policy. The scientific global parent pool is preserved in the
    original Controller decision; this local execution queue is not that pool.
    """
    if (not isinstance(selection, dict) or set(selection) != SELECTION_FIELDS
            or not isinstance(selection["attempt_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", selection["attempt_id"])):
        raise ValueError("exact bounded native selection required")
    request, review, contract = [c._read(value)
                                for value in (request_binding, review_binding, contract_binding)]
    packet, decision = _original(decision_directory)
    if set(request) != w.REQUEST_FIELDS or decision["action"] != "propose_candidate":
        raise ValueError("original candidate decision and exact request required")
    expected_contract = {"schema": "controller_candidate_contract_v1",
                         "decision_sha256": c._digest(decision)}
    expected_contract.update({key: decision[key] for key in CONTRACT_FIELDS
                              - {"schema", "decision_sha256"}})
    state, branches = _selected(batch, selection, decision)
    expected_review = {"schema": "reviewed_candidate_request_v1", "passed": True,
        "batch_id": state["batch_id"], "decision_sha256": c._digest(decision),
        "request_sha256": request_binding["sha256"], "authority_sha256": authority_binding["sha256"],
        "research_parent_sha256": decision["actual_parent_sha256"],
        "comparison_incumbent_sha256": decision["comparison_incumbent_sha256"],
        "contract_sha256": contract_binding["sha256"], "selection_sha256": c._digest(selection),
        "source_commit": request["source_commit"], "files": request["files"],
        "semantic_source_matches_decision": True}
    expected_selection = {"candidate_id": decision["candidate_id"],
        "controller_decision_sha256": c._digest(decision),
        "research_parent_sha256": decision["actual_parent_sha256"],
        "question_id": decision["question_id"],
        "question_digest_sha256": c._digest({"question_id": decision["question_id"],
                                             "hypothesis": decision["hypothesis"]}),
        "hypothesis_digest_sha256": c._digest(decision["hypothesis"])}
    if (set(contract) != CONTRACT_FIELDS or c._digest(contract) != c._digest(expected_contract)
            or set(review) != REVIEW_FIELDS or c._digest(review) != c._digest(expected_review)
            or any(selection[key] != value for key, value in expected_selection.items())
            or request["attempt_id"] != selection["attempt_id"]
            or request["candidate_id"] != selection["candidate_id"]
            or request["spec_sha256"] != contract_binding["sha256"]
            or request["max_fits"] > decision["resources"]["fits"]
            or request["max_wall_seconds"] > decision["resources"]["seconds"]):
        raise ValueError("original question/hypothesis/recipe/source admission drift")
    directory = batch.root / "handoff"
    directory.mkdir(exist_ok=True)
    if directory.resolve() != directory:
        raise ValueError("handoff directory symlink")
    attempt = selection["attempt_id"]
    descriptor = os.open(directory / (attempt + ".lock"),
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / (attempt + ".json")
        record = {"schema": "continuous_candidate_handoff_v1", "sources": {
            **d._identities(), "handoff": w.sha(Path(__file__).resolve())},
            "batch_id": state["batch_id"], "selection": selection,
            "request": request_binding, "source_review": review_binding,
            "contract": contract_binding, "authority": authority_binding,
            "decision_directory": str(Path(decision_directory)),
            "decision_sha256": c._digest(decision), "input_sha256": c._digest(packet),
            "prospective_binding_sha256": c._digest(prospective_binding),
            "dispatch_review_role": "derivative adapter of original independent source review"}
        state, branches = _selected(batch, selection, decision)
        if path.exists():
            if c._digest(d._file(path)) != c._digest(record):
                raise ValueError("original handoff/source binding drift")
            if not branches:
                raise RuntimeError("original selection missing; no automatic reselection")
        else:
            if not branches:
                if state["incumbent"]["candidate_sha256"] != decision["comparison_incumbent_sha256"]:
                    raise ValueError("current comparator differs from original decision")
                authority = c._read(authority_binding)
                if (authority.get("batch_id") != state["batch_id"]
                        or authority["start_utc"] != state["start_utc"]
                        or authority["deadline_utc"] != state["deadline_utc"]
                        or c._digest(packet.get("prospective_budget_binding")) != c._digest(prospective_binding)):
                    raise ValueError("outer/native/original prospective binding drift")
                c.check_budget(authority, now or datetime.now(timezone.utc),
                               prospective_binding=prospective_binding)
                if (any(authority.get(key, False) is not False for key in c.FLAGS)
                        or any(item["attempt_id"] == attempt for item in authority["attempts"])):
                    raise ValueError("permission expansion or already reserved outer attempt")
                w.validate(request, repo)
                batch.select_controller_pool([selection], now=now)
            c.save(path, record)
        dispatch_review = {key: review[key] for key in d.REVIEW_FIELDS}
        review_path = directory / (attempt + ".dispatch-review.json")
        if review_path.exists():
            if c._digest(d._file(review_path)) != c._digest(dispatch_review):
                raise ValueError("derived dispatch review drift")
        else:
            c.save(review_path, dispatch_review)
        return d.dispatch(batch, request_binding,
            {"path": str(review_path), "sha256": w.sha(review_path)},
            decision_directory, authority_binding, repo, now=now,
            prospective_binding=prospective_binding)
