"""Append-only, hash-chained activity logs for the controller harness."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from market_rsi import canonical, digest


SCHEMA = "market_controller_activity_log_v1"
MAX_LOG_BYTES = 16 * 1024 * 1024


def _records(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("controller activity log is missing, symlinked or oversized")
    records = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("controller activity log contains invalid JSON") from error
        if not isinstance(record, dict):
            raise ValueError("controller activity record must be an object")
        records.append(record)
    return records


def verify_activity_log(path: Path) -> dict:
    """Verify sequence numbers and the complete hash chain without rewriting it."""
    records = _records(path)
    previous = None
    for index, record in enumerate(records, 1):
        if set(record) != {
            "schema", "sequence", "recorded_unix_ns", "previous_record_sha256",
            "event", "record_sha256",
        }:
            raise ValueError("controller activity record fields changed")
        unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
        expected = hashlib.sha256(canonical(unsigned).encode()).hexdigest()
        if (record["schema"] != SCHEMA or record["sequence"] != index
                or type(record["recorded_unix_ns"]) is not int
                or record["recorded_unix_ns"] <= 0
                or record["previous_record_sha256"] != previous
                or not isinstance(record["event"], dict)
                or record["record_sha256"] != expected):
            raise ValueError("controller activity log hash chain changed")
        previous = record["record_sha256"]
    return {
        "valid": True,
        "records": len(records),
        "last_record_sha256": previous,
        "log_sha256": digest(records),
    }


def read_activity_events(path: Path) -> list[dict]:
    """Return a verified copy of event payloads."""
    verify_activity_log(path)
    return [dict(record["event"]) for record in _records(path)]


def append_activity(path: Path, event: dict) -> dict:
    """Append one durable record after verifying every existing record."""
    if not isinstance(event, dict) or not event:
        raise ValueError("nonempty controller activity event required")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    before = verify_activity_log(path)
    unsigned = {
        "schema": SCHEMA,
        "sequence": before["records"] + 1,
        "recorded_unix_ns": time.time_ns(),
        "previous_record_sha256": before["last_record_sha256"],
        "event": event,
    }
    record = {**unsigned,
              "record_sha256": hashlib.sha256(canonical(unsigned).encode()).hexdigest()}
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, (canonical(record) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    verify_activity_log(path)
    return record


def assess_activity_logs(workspace: Path) -> dict:
    """Verify all logs and the complete audit trail for the selected candidate.

    Literature and catalog use are controller choices.  If the controller uses
    them, their specialized records must exactly match the generic tool journal.
    They are not prerequisites for selecting an independently executed candidate.
    """
    workspace = Path(workspace)
    names = ("controller-tool-journal.jsonl", "literature-activity.jsonl",
             "algorithm-activity.jsonl")
    summaries = {name: verify_activity_log(workspace / name) for name in names}
    events = {name: read_activity_events(workspace / name)
              for name in names}
    tool_events = events["controller-tool-journal.jsonl"]
    literature_events = events["literature-activity.jsonl"]
    algorithm_events = events["algorithm-activity.jsonl"]
    tool_counts = {}
    for event in tool_events:
        tool = event.get("tool")
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
    if tool_counts.get("search_public_literature", 0) != len(literature_events):
        raise ValueError("literature actions are not completely logged")
    expected_algorithm = sum(tool_counts.get(name, 0) for name in (
        "list_algorithms", "inspect_algorithm", "write_candidate",
        "run_train_cv_candidate", "submit_decision"))
    if expected_algorithm != len(algorithm_events):
        raise ValueError("algorithm actions are not completely logged")
    successful_kinds = {event.get("kind") for event in literature_events + algorithm_events
                        if not str(event.get("kind", "")).endswith("_failed")}
    required = {"candidate_written", "candidate_execution_returned", "candidate_selected"}
    if not required <= successful_kinds:
        raise ValueError("controller activity log lacks a complete candidate path")
    written = {event.get("candidate") for event in algorithm_events
               if event.get("kind") == "candidate_written"}
    executed = {event.get("candidate") for event in algorithm_events
                if event.get("kind") == "candidate_execution_returned"
                and event.get("status") == "completed"
                and event.get("execution_verified") is True
                and event.get("future_test_used") is False
                and event.get("evaluation_role") == "train_cv"
                and event.get("sealed_dev_scored") is False}
    selected = {event.get("candidate") for event in algorithm_events
                if event.get("kind") == "candidate_selected"}
    if len(selected) != 1 or not selected <= written & executed:
        raise ValueError("selected algorithm lacks logged write and verified execution")
    selected_candidate = next(iter(selected))
    written_events = {event.get("candidate"): event for event in algorithm_events
                      if event.get("kind") == "candidate_written"}
    selected_integrity = written_events[selected_candidate].get("source_integrity")
    if (not isinstance(selected_integrity, dict)
            or selected_integrity.get("valid") is not True):
        raise ValueError("selected candidate lacks source-integrity receipt")

    completed_events = [event for event in algorithm_events
                        if event.get("kind") == "candidate_execution_returned"
                        and event.get("status") == "completed"]
    first_by_prediction = {}
    selected_prediction_sha256 = None
    for event in completed_events:
        score = event.get("aggregate_train_cv_score")
        prediction_sha256 = score.get("prediction_sha256") if isinstance(score, dict) else None
        if (not isinstance(prediction_sha256, str) or len(prediction_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in prediction_sha256)):
            raise ValueError("completed candidate lacks prediction digest in activity log")
        equivalent = first_by_prediction.get(prediction_sha256)
        if (event.get("prediction_novel") is not (equivalent is None)
                or event.get("prediction_equivalent_to") != equivalent):
            raise ValueError("candidate prediction novelty audit changed")
        first_by_prediction.setdefault(prediction_sha256, event.get("candidate"))
        if event.get("candidate") == selected_candidate:
            selected_prediction_sha256 = prediction_sha256
            if equivalent is not None:
                raise ValueError("selected candidate is a prediction-identical no-op")
    if selected_prediction_sha256 is None:
        raise ValueError("selected candidate prediction digest missing")
    controller_integrity = {
        "schema": "market_controller_integrity_assessment_v1",
        "valid": True,
        "selected_candidate": selected_candidate,
        "selected_source_integrity_sha256": digest(selected_integrity),
        "selected_prediction_sha256": selected_prediction_sha256,
        "prediction_identical_no_op": False,
        "scientific_merit_verified": False,
    }
    return {"valid": True, "logs": summaries, "tool_counts": tool_counts,
            "selected_candidate": selected_candidate,
            "controller_integrity": controller_integrity,
            "optional_research_actions": {
                "literature_searches": tool_counts.get("search_public_literature", 0),
                "algorithm_catalog_lists": tool_counts.get("list_algorithms", 0),
                "algorithm_catalog_inspections": tool_counts.get("inspect_algorithm", 0),
            }}
