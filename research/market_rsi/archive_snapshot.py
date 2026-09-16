"""Immutable, verifiable research Archive carried between controller rounds.

The Archive is the learning state for the fixed-H0 experiment.  It keeps the
controller's own executed record without adding runner-authored advice.  This
module performs no networking, model calls, sandbox work, or scoring.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from controller_activity_log import assess_activity_logs, read_activity_events
from controller_workspace import validate_workspace
from market_rsi import canonical, digest, fresh_json, identifier


SNAPSHOT_SCHEMA = "market_controller_archive_snapshot_v2"
HISTORY_SCHEMA = "market_controller_history_v2"
MAX_ARCHIVE_BYTES = 1_048_576
LOG_NAMES = (
    "controller-tool-journal.jsonl",
    "literature-activity.jsonl",
    "algorithm-activity.jsonl",
)


def _regular(path: Path, maximum: int = MAX_ARCHIVE_BYTES) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized Archive input")
    return path.read_bytes()


def _json(path: Path, maximum: int = MAX_ARCHIVE_BYTES):
    return json.loads(_regular(path, maximum))


def _jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    raw = _regular(path)
    records = []
    for line in raw.decode().splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("Archive log record must be an object")
            records.append(value)
    return records


def _verify_embedded_log(records: list[dict]) -> dict:
    previous = None
    for index, record in enumerate(records, 1):
        if set(record) != {
            "schema", "sequence", "recorded_unix_ns", "previous_record_sha256",
            "event", "record_sha256",
        }:
            raise ValueError("Archive log fields changed")
        unsigned = {key: value for key, value in record.items()
                    if key != "record_sha256"}
        expected = hashlib.sha256(canonical(unsigned).encode()).hexdigest()
        if (record["sequence"] != index
                or record["previous_record_sha256"] != previous
                or record["record_sha256"] != expected):
            raise ValueError("Archive log hash chain changed")
        previous = record["record_sha256"]
    return {"records": len(records), "last_record_sha256": previous,
            "log_sha256": digest(records)}


def _candidate_sources(workspace: Path, algorithm_records: list[dict]) -> list[dict]:
    candidates = []
    seen = set()
    for record in algorithm_records:
        event = record["event"]
        if event.get("kind") != "candidate_written":
            continue
        name = event.get("candidate")
        if not isinstance(name, str) or name in seen:
            raise ValueError("Archive candidate names are missing or reused")
        path = workspace / name
        source = _regular(path, 131_072).decode()
        source_sha256 = hashlib.sha256(source.encode()).hexdigest()
        if source_sha256 != event.get("source_sha256"):
            raise ValueError("Archive candidate source changed")
        candidates.append({
            "candidate": name,
            "source": source,
            "source_sha256": source_sha256,
            "algorithm_family": event.get("algorithm_family"),
            "hypothesis": event.get("hypothesis"),
            "literature_ids": event.get("literature_ids"),
            "change_summary": event.get("change_summary"),
            "parent_candidate": event.get("parent_candidate"),
            "parent_source_sha256": event.get("parent_source_sha256"),
            "archive_parent": event.get("archive_parent"),
        })
        seen.add(name)
    return candidates


def _executions(workspace: Path) -> list[dict]:
    requests = workspace / "execution-requests"
    results = workspace / "execution-results"
    executions = []
    for request_path in sorted(requests.glob("*.json")):
        request = _json(request_path, 2 * 1024 * 1024)
        result_path = results / request_path.name
        result = _json(result_path, 2 * 1024 * 1024)
        if (result.get("execution_id") != request.get("execution_id")
                or result.get("request_sha256") != digest(request)
                or result.get("candidate_sha256") != request.get("candidate_sha256")
                or request.get("evaluation_role") != "train_cv"
                or result.get("evaluation_role") != "train_cv"
                or result.get("future_test_used") is not False
                or result.get("automatic_retry") is not False):
            raise ValueError("Archive execution receipt is not bound")
        executions.append({"request": request, "request_sha256": digest(request),
                           "result": result, "result_sha256": digest(result)})
    return executions


def _turns(session_output: Path) -> tuple[list[dict], str]:
    turns = []
    cost = Decimal(0)
    for path in sorted(session_output.glob("turn-*")):
        request = _json(path / "request.json", 2 * 1024 * 1024)
        response = _json(path / "response.json", 16 * 1024 * 1024)
        assessment = _json(path / "assessment.json")
        receipt = response.get("receipt")
        if (not isinstance(receipt, dict) or receipt.get("terminal") is not True
                or receipt.get("provider") != "tinker"):
            raise ValueError("Archive turn lacks terminal provider receipt")
        metered = Decimal(str(receipt.get("metered_cost_usd")))
        if not metered.is_finite() or metered < 0:
            raise ValueError("Archive turn has invalid metered cost")
        cost += metered
        turns.append({
            "turn_id": path.name,
            "request_sha256": digest(request),
            "response_sha256": digest(response),
            "response_text": response.get("text"),
            "receipt": receipt,
            "assessment": assessment,
        })
    if not turns:
        raise ValueError("Archive requires at least one completed controller turn")
    return turns, str(cost)


def build_snapshot(
    output: Path,
    *,
    workspace: Path,
    session_output: Path,
    prompt_path: Path,
    source_manifest_path: Path,
    lineage_id: str,
    round_index: int,
    previous_snapshot_sha256: str | None,
) -> dict:
    """Freeze one completed formal controller session into a new Archive file."""
    identifier(lineage_id)
    if type(round_index) is not int or round_index < 0:
        raise ValueError("nonnegative Archive round required")
    if round_index == 0 and previous_snapshot_sha256 is not None:
        raise ValueError("first Archive snapshot cannot have a parent")
    if round_index > 0 and (not isinstance(previous_snapshot_sha256, str)
                            or len(previous_snapshot_sha256) != 64):
        raise ValueError("later Archive snapshot requires previous hash")
    workspace = Path(workspace).resolve()
    session_output = Path(session_output).resolve()
    manifest = validate_workspace(workspace)
    activity = assess_activity_logs(workspace)
    final_assessment = _json(session_output / "assessment.json", 16 * 1024 * 1024)
    if final_assessment.get("valid") is not True:
        raise ValueError("only a valid completed controller session can enter Archive")
    prompt = _regular(prompt_path, 262_144).decode()
    source_manifest = _json(source_manifest_path, 256 * 1024)
    if source_manifest.get("schema") != "market_controller_source_manifest_v1":
        raise ValueError("frozen controller source manifest required")
    logs = {name: _jsonl(workspace / name) for name in LOG_NAMES}
    log_summaries = {name: _verify_embedded_log(records)
                     for name, records in logs.items()}
    decision = _json(workspace / "submitted-decision.json", 16_384)
    candidates = _candidate_sources(workspace, logs["algorithm-activity.jsonl"])
    executions = _executions(workspace)
    sealed_dev_path = workspace / "sealed-dev-result.json"
    sealed_dev_outcome = (_json(sealed_dev_path, 2 * 1024 * 1024)
                          if sealed_dev_path.exists() else None)
    turns, metered_cost = _turns(session_output)
    profile_raw = _regular(workspace / "harness-profile.json")
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "lineage_id": lineage_id,
        "round_index": round_index,
        "previous_snapshot_sha256": previous_snapshot_sha256,
        "session_id": manifest["session_id"],
        "experiment_id": manifest["experiment_id"],
        "task_id": manifest["task_id"],
        "arm": manifest["arm"],
        "harness_profile_sha256": hashlib.sha256(profile_raw).hexdigest(),
        "workspace_manifest_sha256": digest(manifest),
        "source_manifest_sha256": digest(source_manifest),
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "logs": logs,
        "log_summaries": log_summaries,
        "candidates": candidates,
        "executions": executions,
        "sealed_dev_outcome": sealed_dev_outcome,
        "decision": decision,
        "decision_sha256": digest(decision),
        "turns": turns,
        "metered_controller_usd": metered_cost,
        "future_test_used": False,
        "runner_authored_next_step": None,
    }
    snapshot = {**payload, "payload_sha256": digest(payload)}
    validate_snapshot(snapshot)
    encoded = canonical(snapshot).encode()
    if len(encoded) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive snapshot exceeds controller-visible bound")
    fresh_json(output, snapshot)
    return snapshot


def validate_snapshot(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema", "lineage_id", "round_index", "previous_snapshot_sha256",
        "session_id", "experiment_id", "task_id", "arm", "harness_profile_sha256",
        "workspace_manifest_sha256", "source_manifest_sha256", "prompt",
        "prompt_sha256", "logs", "log_summaries", "candidates", "executions",
        "sealed_dev_outcome",
        "decision", "decision_sha256", "turns", "metered_controller_usd",
        "future_test_used", "runner_authored_next_step", "payload_sha256",
    }:
        raise ValueError("Archive snapshot fields changed")
    payload = {key: value for key, value in snapshot.items() if key != "payload_sha256"}
    for value in (snapshot["lineage_id"], snapshot["session_id"],
                  snapshot["experiment_id"], snapshot["task_id"], snapshot["arm"]):
        identifier(value)
    if (snapshot["schema"] != SNAPSHOT_SCHEMA
            or snapshot["payload_sha256"] != digest(payload)
            or type(snapshot["round_index"]) is not int
            or snapshot["round_index"] < 0
            or snapshot["prompt_sha256"]
            != hashlib.sha256(snapshot["prompt"].encode()).hexdigest()
            or snapshot["decision_sha256"] != digest(snapshot["decision"])
            or snapshot["future_test_used"] is not False
            or snapshot["runner_authored_next_step"] is not None):
        raise ValueError("Archive snapshot integrity changed")
    for name in LOG_NAMES:
        if name not in snapshot["logs"]:
            raise ValueError("Archive log missing")
        if _verify_embedded_log(snapshot["logs"][name]) != snapshot["log_summaries"][name]:
            raise ValueError("Archive log summary changed")
    candidate_index = {item["candidate"]: item for item in snapshot["candidates"]}
    if len(candidate_index) != len(snapshot["candidates"]):
        raise ValueError("Archive candidate reused")
    for item in snapshot["candidates"]:
        if hashlib.sha256(item["source"].encode()).hexdigest() != item["source_sha256"]:
            raise ValueError("Archive candidate source hash changed")
    selected = snapshot["decision"].get("candidate_artifact")
    completed = {item["request"].get("candidate_name") for item in snapshot["executions"]
                 if item["result"].get("status") == "completed"
                 and item["result"].get("execution_verified") is True}
    if selected not in candidate_index or selected not in completed:
        raise ValueError("Archive selected candidate lacks completed execution")
    sealed = snapshot["sealed_dev_outcome"]
    if sealed is not None:
        if (not isinstance(sealed, dict)
                or sealed.get("schema") not in {
                    "market_controller_sealed_dev_outcome_v1",
                    "market_controller_prospective_sealed_dev_outcome_v2",
                }
                or sealed.get("selected", {}).get("candidate") != selected
                or sealed.get("score_receipt", {}).get("score_visible_to_same_session") is not False
                or sealed.get("visible_starting_next_archive") is not True
                or sealed.get("future_test_used") is not False):
            raise ValueError("Archive sealed Dev outcome is not bound to the selected candidate")
    cost = Decimal(0)
    for turn in snapshot["turns"]:
        receipt = turn.get("receipt")
        if not isinstance(receipt, dict) or receipt.get("terminal") is not True:
            raise ValueError("Archive turn receipt changed")
        cost += Decimal(str(receipt["metered_cost_usd"]))
    if str(cost) != snapshot["metered_controller_usd"]:
        raise ValueError("Archive controller cost changed")
    return {"valid": True, "snapshot_sha256": digest(snapshot),
            "selected_candidate": selected, "round_index": snapshot["round_index"]}


def empty_history(*, lineage_id: str, harness_profile_sha256: str,
                  source_manifest_sha256: str) -> dict:
    identifier(lineage_id)
    if not isinstance(harness_profile_sha256, str) or len(harness_profile_sha256) != 64:
        raise ValueError("H0 profile hash required")
    if not isinstance(source_manifest_sha256, str) or len(source_manifest_sha256) != 64:
        raise ValueError("frozen H0 source-manifest hash required")
    history = {"schema": HISTORY_SCHEMA, "lineage_id": lineage_id,
               "harness_profile_sha256": harness_profile_sha256,
               "source_manifest_sha256": source_manifest_sha256, "snapshots": []}
    validate_history(history)
    return history


def append_snapshot(history: dict, snapshot: dict) -> dict:
    validate_history(history)
    checked = validate_snapshot(snapshot)
    if (snapshot["lineage_id"] != history["lineage_id"]
            or snapshot["harness_profile_sha256"] != history["harness_profile_sha256"]
            or snapshot["source_manifest_sha256"] != history["source_manifest_sha256"]
            or snapshot["round_index"] != len(history["snapshots"])
            or snapshot["previous_snapshot_sha256"] != (
                history["snapshots"][-1]["snapshot_sha256"]
                if history["snapshots"] else None)):
        raise ValueError("Archive snapshot does not continue this fixed-H0 lineage")
    updated = {**history, "snapshots": [*history["snapshots"], {
        "snapshot_sha256": checked["snapshot_sha256"], "snapshot": snapshot,
    }]}
    validate_history(updated)
    if len(canonical(updated).encode()) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive history exceeds controller-visible bound")
    return updated


def validate_history(history: dict) -> dict:
    """Validate v2 history; retain old empty fixtures only for legacy canaries."""
    if history == {"rounds": []}:
        return {"valid": True, "legacy_empty": True, "snapshots": 0}
    if (isinstance(history, dict) and history.get("schema") == "market_controller_history_v1"
            and history.get("rounds") == []):
        return {"valid": True, "legacy_empty": True, "snapshots": 0}
    if not isinstance(history, dict) or set(history) != {
        "schema", "lineage_id", "harness_profile_sha256", "source_manifest_sha256",
        "snapshots",
    } or history["schema"] != HISTORY_SCHEMA:
        raise ValueError("invalid controller Archive history")
    identifier(history["lineage_id"])
    if (not isinstance(history["harness_profile_sha256"], str)
            or len(history["harness_profile_sha256"]) != 64
            or not isinstance(history["source_manifest_sha256"], str)
            or len(history["source_manifest_sha256"]) != 64
            or not isinstance(history["snapshots"], list)):
        raise ValueError("invalid fixed-H0 Archive binding")
    previous = None
    sessions = set()
    for index, entry in enumerate(history["snapshots"]):
        if not isinstance(entry, dict) or set(entry) != {"snapshot_sha256", "snapshot"}:
            raise ValueError("invalid Archive entry")
        snapshot = entry["snapshot"]
        checked = validate_snapshot(snapshot)
        if (entry["snapshot_sha256"] != checked["snapshot_sha256"]
                or snapshot["lineage_id"] != history["lineage_id"]
                or snapshot["harness_profile_sha256"] != history["harness_profile_sha256"]
                or snapshot["source_manifest_sha256"] != history["source_manifest_sha256"]
                or snapshot["round_index"] != index
                or snapshot["previous_snapshot_sha256"] != previous
                or snapshot["session_id"] in sessions):
            raise ValueError("Archive lineage chain changed")
        previous = entry["snapshot_sha256"]
        sessions.add(snapshot["session_id"])
    return {"valid": True, "legacy_empty": False,
            "snapshots": len(history["snapshots"]), "last_snapshot_sha256": previous}


def find_archive_candidate(history: dict, reference: dict) -> dict:
    validate_history(history)
    if (not isinstance(reference, dict) or set(reference) != {
            "session_id", "candidate", "source_sha256"}):
        raise ValueError("exact Archive parent reference required")
    matches = []
    for entry in history.get("snapshots", []):
        snapshot = entry["snapshot"]
        if snapshot["session_id"] != reference["session_id"]:
            continue
        matches.extend(item for item in snapshot["candidates"]
                       if item["candidate"] == reference["candidate"]
                       and item["source_sha256"] == reference["source_sha256"])
    if len(matches) != 1:
        raise ValueError("Archive parent does not exist exactly once")
    return matches[0]


def assess_carryover(workspace: Path) -> dict:
    """Prove the selected current candidate descends from the prior selection."""
    workspace = Path(workspace)
    validate_workspace(workspace)
    history = _json(workspace / "own-history.json")
    checked_history = validate_history(history)
    if checked_history["legacy_empty"] or not history["snapshots"]:
        raise ValueError("Archive carryover requires a prior snapshot")
    activity = assess_activity_logs(workspace)
    if activity["tool_counts"].get("read_own_research_history", 0) < 1:
        raise ValueError("controller did not read its Archive")
    previous = history["snapshots"][-1]["snapshot"]
    previous_selected = previous["decision"]["candidate_artifact"]
    previous_candidate = next(item for item in previous["candidates"]
                              if item["candidate"] == previous_selected)
    expected = {"session_id": previous["session_id"],
                "candidate": previous_selected,
                "source_sha256": previous_candidate["source_sha256"]}
    events = read_activity_events(workspace / "algorithm-activity.jsonl")
    written = {event["candidate"]: event for event in events
               if event.get("kind") == "candidate_written"}
    current = activity["selected_candidate"]
    visited = set()
    while current in written and current not in visited:
        visited.add(current)
        event = written[current]
        if event.get("archive_parent") == expected:
            return {"valid": True, "prior_snapshot_sha256":
                    history["snapshots"][-1]["snapshot_sha256"],
                    "archive_parent": expected, "selected_candidate":
                    activity["selected_candidate"], "ancestry_depth": len(visited),
                    "activity_logs": activity}
        current = event.get("parent_candidate")
    raise ValueError("selected candidate has no lineage to the prior Archive selection")
