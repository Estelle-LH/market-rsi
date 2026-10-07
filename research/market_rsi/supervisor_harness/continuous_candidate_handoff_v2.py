"""Versioned preflight -> original native handoff; no new execution authority.

Supervisor global admission must call prepare() before spending its own slot.
This entry rechecks preflight before native selection. Legacy recovery is intact;
an unbound/uncertain original is not adopted or automatically relaunched.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import candidate_production_preflight as p
from supervisor_harness import continuous_candidate_handoff as legacy
from supervisor_harness import reviewed_candidate_dispatch as d
from supervisor_harness import opened_train_discovery_worker as w

PREFIX = "research/market_rsi/supervisor_harness/"


def _sources():
    return {"entry": w.sha(Path(__file__).resolve()),
            "preflight": w.sha(Path(p.__file__).resolve()),
            "legacy": w.sha(Path(legacy.__file__).resolve())}


def _original(batch, selection, request_binding, review_binding, contract_binding,
              decision_directory, authority_binding, prospective_binding):
    request, review, contract = [c._read(value) for value in
        (request_binding, review_binding, contract_binding)]
    packet, decision = legacy._original(decision_directory)
    if set(selection) != legacy.SELECTION_FIELDS or set(request) != w.REQUEST_FIELDS:
        raise ValueError("exact original selection/request required")
    state, branches = legacy._selected(batch, selection, decision)
    expected_contract = {"schema": "controller_candidate_contract_v1",
                         "decision_sha256": c._digest(decision)}
    expected_contract.update({key: decision[key] for key in legacy.CONTRACT_FIELDS
                             - {"schema", "decision_sha256"}})
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
    if (decision["action"] != "propose_candidate" or c._digest(contract) != c._digest(expected_contract)
            or c._digest(review) != c._digest(expected_review)
            or any(selection[key] != value for key, value in expected_selection.items())
            or request["attempt_id"] != selection["attempt_id"]
            or request["candidate_id"] != decision["candidate_id"]
            or request["spec_sha256"] != contract_binding["sha256"]):
        raise ValueError("original scientific decision/source review drift")
    if c._digest(packet.get("prospective_budget_binding")) != c._digest(prospective_binding):
        raise ValueError("original prospective binding drift")
    return request, state, branches


def prepare(batch, selection, request_binding, review_binding, contract_binding,
            decision_directory, authority_binding, repo, *, parent_check,
            prospective_binding=None):
    """Read-only, before global admission; no native selection or reservations."""
    request, state, branches = _original(batch, selection, request_binding,
        review_binding, contract_binding, decision_directory, authority_binding, prospective_binding)
    if branches:
        raise RuntimeError("not a fresh original; recover rather than repeat preflight")
    authority = c._read(authority_binding)
    if (authority.get("batch_id") != state["batch_id"] or authority["start_utc"] != state["start_utc"]
            or authority["deadline_utc"] != state["deadline_utc"]
            or any(authority.get(key, False) is not False for key in c.FLAGS)
            or any(item["attempt_id"] == request["attempt_id"] for item in authority["attempts"])):
        raise ValueError("outer authority/permission/original attempt drift")
    c.check_budget(authority, batch._trusted_now(None, "outer preflight"),
                   prospective_binding=prospective_binding)
    for module, relative in ((p, PREFIX + "candidate_production_preflight.py"),
                             (None, PREFIX + "continuous_candidate_handoff_v2.py")):
        source = Path(__file__).resolve() if module is None else Path(module.__file__).resolve()
        if request["files"].get(relative) != w.sha(source):
            raise ValueError("reviewed production preflight/entry source missing or changed")
    receipt = p.preflight(batch, request_binding, review_binding, contract_binding,
                          repo, parent_check=parent_check)
    c.check_budget(authority, receipt["preflight_completion_utc"], prospective_binding=prospective_binding)
    return {**receipt, "entry_sources": _sources(),
            "original_decision_directory": str(Path(decision_directory)),
            "selection_sha256": c._digest(selection), "authority_sha256": authority_binding["sha256"]}


def handoff(batch, selection, request_binding, review_binding, contract_binding,
            decision_directory, authority_binding, repo, *, parent_check,
            prospective_binding=None):
    """Fresh-only preflight and existing once-only selection/execution/recovery."""
    request, state, branches = _original(batch, selection, request_binding,
        review_binding, contract_binding, decision_directory, authority_binding, prospective_binding)
    # Validate bounded ID before using it as a filename, including cached recovery.
    import re
    if not isinstance(request["attempt_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", request["attempt_id"]):
        raise ValueError("bounded original attempt required")
    directory = batch.root / "preflight_handoff"
    directory.mkdir(exist_ok=True)
    if directory.resolve() != directory:
        raise ValueError("preflight handoff directory symlink")
    attempt = request["attempt_id"]
    fd = os.open(directory / (attempt + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / (attempt + ".json")
        identity = {"schema": "continuous_candidate_handoff_v2", "sources": _sources(),
            "batch_id": state["batch_id"], "selection": selection, "request": request_binding,
            "review": review_binding, "contract": contract_binding, "authority": authority_binding,
            "decision_directory": str(Path(decision_directory)), "parent_check": parent_check,
            "prospective_binding_sha256": c._digest(prospective_binding)}
        if path.exists():
            record = d._file(path)
            if set(record) != set(identity) | {"preflight", "preflight_sha256"} or any(
                    c._digest(record[key]) != c._digest(value) for key, value in identity.items()):
                raise ValueError("original v2 preflight/source binding drift")
            if (c._digest(record["preflight"]) != record["preflight_sha256"]
                    or record["preflight"].get("passed") is not True
                    or record["preflight"].get("entry_sources") != identity["sources"]
                    or record["preflight"].get("request_sha256") != request_binding["sha256"]):
                raise ValueError("stored original preflight receipt drift")
            if not branches and not (batch.root / "handoff" / (attempt + ".json")).exists():
                raise RuntimeError("interrupted original preflight handoff; inspect without retry")
        else:
            if branches or (batch.root / "handoff" / (attempt + ".json")).exists():
                raise RuntimeError("unbound legacy admission; no automatic v2 adoption")
            receipt = prepare(batch, selection, request_binding, review_binding, contract_binding,
                decision_directory, authority_binding, repo, parent_check=parent_check,
                prospective_binding=prospective_binding)
            c.save(path, {**identity, "preflight": receipt, "preflight_sha256": c._digest(receipt)})
        return legacy.handoff(batch, selection, request_binding, review_binding, contract_binding,
            decision_directory, authority_binding, repo,
            now=batch._trusted_now(None, "outer handoff"), prospective_binding=prospective_binding)
