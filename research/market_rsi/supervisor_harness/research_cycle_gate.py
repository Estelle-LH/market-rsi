"""Fail-closed, zero-paid fixture gate for the proposed recursive research loop.

This is a provenance canary, not a model-authorship or sandbox attestation.
Only an independently verified live controller adapter and Harbor/E2B adapter
may later admit a real controller-led round. Never relabel a fixture as one.
"""
from __future__ import annotations

from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, identifier, load_json


ZERO = "0" * 64
ROLES = {"public_metadata", "opened_train", "synthetic_fixture"}
TASK_ROLES = {
    "public_source_research": "public_metadata",
    "train_only_diagnostic": "opened_train",
    "code_canary": "synthetic_fixture",
}


def _sha(value: str, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def _exact(value: dict, fields: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} requires exact fields")


def _read_bound(path: Path, expected_sha: str, label: str) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"{label} missing, symlinked or oversized")
    if file_hash(path) != _sha(expected_sha, label):
        raise ValueError(f"{label} changed")
    return load_json(path)


def _sealed(value: dict) -> dict:
    return {**value, "record_sha256": digest(value)}


def _verify_seal(value: dict, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    _sha(value.get("record_sha256"), label)
    if digest({k: v for k, v in value.items() if k != "record_sha256"}) != value["record_sha256"]:
        raise ValueError(f"{label} was modified")


def _verify_facts(root: Path, packet: dict) -> None:
    facts_path = root / "facts.json"
    if (facts_path.is_symlink() or not facts_path.is_file()
            or facts_path.stat().st_size > 2 * 1024 * 1024):
        raise ValueError("facts missing, symlinked or oversized")
    if digest(load_json(facts_path)) != packet["facts_sha256"]:
        raise ValueError("controller facts differ from frozen input")


def _verify_decision_lineage(root: Path) -> tuple[dict, dict]:
    packet, decision = load_json(root / "input.json"), load_json(root / "decision.json")
    _verify_seal(packet, "input")
    _verify_seal(decision, "decision")
    _verify_facts(root, packet)
    if (decision.get("cycle_id") != packet.get("cycle_id")
            or decision.get("input_sha256") != packet["record_sha256"]
            or decision.get("attribution") != "scripted_fixture_not_model"):
        raise ValueError("decision lineage or fixture attribution changed")
    raw = _read_bound(root / "raw-decision.json", decision["raw_decision_sha256"],
                      "raw decision")
    if raw != {key: value for key, value in decision.items()
               if key not in {"raw_decision_sha256", "attribution", "record_sha256"}}:
        raise ValueError("bound decision differs from raw output")
    return packet, decision


def open_fixture_cycle(root: Path, packet: dict) -> dict:
    """Create a fresh immutable input; a fixture can never authorize spending."""
    _exact(packet, {"cycle_id", "parent_feedback_sha256", "harness_sha256",
                    "facts_sha256", "allowed_data_roles", "p0_passed",
                    "cost_cap_usd", "evidence_mode"}, "input packet")
    identifier(packet["cycle_id"])
    for key in ("parent_feedback_sha256", "harness_sha256", "facts_sha256"):
        _sha(packet[key], key)
    roles = packet["allowed_data_roles"]
    if (not isinstance(roles, list) or not roles or len(set(roles)) != len(roles)
            or not set(roles) <= ROLES):
        raise ValueError("only explicit non-protected data roles are allowed")
    if (packet["evidence_mode"] != "synthetic_fixture" or packet["cost_cap_usd"] != "0"
            or type(packet["p0_passed"]) is not bool):
        raise ValueError("this gate admits only zero-paid synthetic fixtures")
    root = Path(root)
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    claim = _sealed({"schema": "market_research_cycle_input_v1", **packet})
    fresh_json(root / "input.json", claim)
    return claim


def bind_fixture_decision(root: Path, raw_path: Path, decision: dict) -> dict:
    """Bind an unchanged fixture decision to one input; never claim model authorship."""
    root, raw_path = Path(root), Path(raw_path)
    packet = load_json(root / "input.json")
    _verify_seal(packet, "input")
    _verify_facts(root, packet)
    if raw_path.parent.resolve() != root.resolve() or raw_path.name != "raw-decision.json":
        raise ValueError("raw decision must be a direct artifact of this cycle")
    _exact(decision, {"schema", "cycle_id", "input_sha256", "task_id",
                      "task_type", "data_role", "question", "hypothesis",
                      "expected_evidence", "stop_rule", "max_seconds",
                      "cost_bound_usd", "raw_decision_sha256"}, "controller decision")
    if (decision["schema"] != "market_research_decision_v1"
            or decision["cycle_id"] != packet["cycle_id"]
            or decision["input_sha256"] != packet["record_sha256"]):
        raise ValueError("decision is not bound to the input")
    identifier(decision["task_id"])
    if (decision["task_type"] not in TASK_ROLES
            or decision["data_role"] != TASK_ROLES[decision["task_type"]]
            or decision["data_role"] not in packet["allowed_data_roles"]):
        raise ValueError("task crosses an unadmitted data role")
    if (type(decision["max_seconds"]) is not int or not 1 <= decision["max_seconds"] <= 3600
            or decision["cost_bound_usd"] != "0"):
        raise ValueError("unbounded or paid task is not a fixture")
    if not all(isinstance(decision[key], str) and decision[key].strip() for key in
               ("question", "hypothesis", "expected_evidence", "stop_rule")):
        raise ValueError("decision must be stated before execution")
    raw = _read_bound(raw_path, decision["raw_decision_sha256"], "raw decision")
    if raw != {key: value for key, value in decision.items() if key != "raw_decision_sha256"}:
        raise ValueError("decision was rewritten after raw output")
    record = _sealed({**decision, "attribution": "scripted_fixture_not_model"})
    fresh_json(root / "decision.json", record)
    return record


def record_fixture_execution(root: Path, receipt: dict) -> dict:
    root = Path(root)
    packet, decision = _verify_decision_lineage(root)
    _exact(receipt, {"schema", "cycle_id", "decision_sha256", "task_id",
                     "backend", "status", "exit_code", "trace_path",
                     "trace_sha256", "output_path", "output_sha256",
                     "cost_usd", "cleanup_passed"}, "researcher receipt")
    if (receipt["schema"] != "market_researcher_receipt_v1"
            or receipt["cycle_id"] != packet["cycle_id"]
            or receipt["decision_sha256"] != decision["record_sha256"]
            or receipt["task_id"] != decision["task_id"]):
        raise ValueError("researcher receipt is not bound to the decision")
    if (receipt["backend"] != "local_fixture" or receipt["cost_usd"] != "0"
            or receipt["cleanup_passed"] is not True):
        raise ValueError("fixture has no paid or unverified backend")
    if receipt["status"] not in {"completed", "failed", "timed_out"}:
        raise ValueError("terminal researcher status required")
    if type(receipt["exit_code"]) is not int or (receipt["status"] == "completed") != (receipt["exit_code"] == 0):
        raise ValueError("status and exit code disagree")
    for name in ("trace", "output"):
        relative = receipt[f"{name}_path"]
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise ValueError("researcher artifact escaped run root")
        path = root / relative
        _read_bound(path, receipt[f"{name}_sha256"], name)
    record = _sealed({**receipt, "evidence_mode": "synthetic_fixture"})
    fresh_json(root / "execution.json", record)
    return record


def review_fixture_cycle(root: Path, review: dict) -> dict:
    """Verify exact lineage and emit feedback; never promote fixture evidence."""
    root = Path(root)
    packet, decision = _verify_decision_lineage(root)
    execution = load_json(root / "execution.json")
    _verify_seal(execution, "execution")
    for name in ("trace", "output"):
        _read_bound(root / execution[f"{name}_path"], execution[f"{name}_sha256"], name)
    _exact(review, {"schema", "cycle_id", "decision_sha256", "execution_sha256",
                    "verdict", "reason", "feedback_summary", "protected_data_opened",
                    "budget_ok"}, "supervisor review")
    if (review["schema"] != "market_supervisor_review_v1"
            or review["cycle_id"] != packet["cycle_id"]
            or review["decision_sha256"] != decision["record_sha256"]
            or review["execution_sha256"] != execution["record_sha256"]):
        raise ValueError("review is not bound to exact prior artifacts")
    if (review["verdict"] not in {"accept", "reject"}
            or review["protected_data_opened"] is not False
            or review["budget_ok"] is not True
            or not isinstance(review["reason"], str) or not review["reason"].strip()
            or not isinstance(review["feedback_summary"], str)):
        raise ValueError("review violates safety or explanation requirements")
    if review["verdict"] == "accept" and execution["status"] != "completed":
        raise ValueError("failed execution cannot be accepted as completion")
    record = _sealed({**review, "controller_led_result": False,
                      "empirical_improvement_claim_allowed": False})
    fresh_json(root / "review.json", record)
    return record
