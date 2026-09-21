"""Durable liveness and repair state machine for the outer Supervisor.

This module is deterministic.  It does not choose scientific work, call a
model, kill a process, or retry a run.  It detects missing heartbeats or
material progress, freezes an incident packet and repair plan, and requires a
separate verified canary plus a fresh run ID before infrastructure/data work
can resume.  Scientific outcomes are terminal evidence, never auto-retries.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


SCHEMA = "market_supervisor_watchdog_v1"
INCIDENT_SCHEMA = "market_supervisor_incident_v1"
PLAN_SCHEMA = "market_supervisor_repair_plan_v1"
TASK_KINDS = frozenset({"data", "infrastructure", "research", "training", "evaluation"})
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
ZERO = "0" * 64


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("watchdog time must include timezone")
    return parsed.astimezone(timezone.utc)


def _now(value: datetime | None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("watchdog clock must include timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"{label} must be lowercase SHA256")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _exclusive_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"fresh receipt required: {path.name}")
    encoded = json.dumps(value, sort_keys=True, indent=2).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _replace_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".watchdog-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(value, sort_keys=True, indent=2).encode() + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SupervisorWatchdog:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.journal = self.root / "journal.jsonl"
        self.snapshot_path = self.root / "snapshot.json"
        self.incidents = self.root / "incidents"
        self.lock = self.root / "watchdog.lock"

    @contextmanager
    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("watchdog root cannot be a symlink")
        with self.lock.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _replay(self) -> dict:
        state = {"schema": SCHEMA, "initialized": False, "seq": 0,
                 "head_sha256": ZERO, "active_task": None,
                 "claimed_task_ids": [], "incidents": [], "last_event_utc": None}
        if not self.journal.exists():
            return state
        if self.journal.is_symlink() or self.journal.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("unsafe watchdog journal")
        for raw in self.journal.read_text().splitlines():
            event = json.loads(raw)
            required = {"schema", "seq", "time_utc", "event", "payload",
                        "prev_sha256", "sha256"}
            if not isinstance(event, dict) or set(event) != required:
                raise ValueError("invalid watchdog event")
            sha = event.pop("sha256")
            if (event["schema"] != SCHEMA or event["seq"] != state["seq"] + 1
                    or event["prev_sha256"] != state["head_sha256"]
                    or sha != _digest(event)):
                raise ValueError("watchdog journal hash chain changed")
            _time(event["time_utc"])
            kind, payload = event["event"], event["payload"]
            if kind == "initialize":
                if state["initialized"] or payload != {}:
                    raise ValueError("invalid watchdog initialization")
                state["initialized"] = True
            elif kind == "task_claim":
                task_id = payload["task_id"]
                if state["active_task"] is not None or task_id in state["claimed_task_ids"]:
                    raise ValueError("duplicate or concurrent watchdog task")
                state["claimed_task_ids"].append(task_id)
                state["active_task"] = payload
            elif kind == "heartbeat":
                task = state["active_task"]
                if task is None or payload["task_id"] != task["task_id"]:
                    raise ValueError("heartbeat does not match active task")
                task["last_heartbeat_utc"] = event["time_utc"]
                if payload["material_progress"]:
                    task["last_progress_utc"] = event["time_utc"]
                    task["progress_seq"] += 1
                    task["last_progress_sha256"] = payload["progress_sha256"]
            elif kind == "data_gate":
                task = state["active_task"]
                if task is None or payload["task_id"] != task["task_id"]:
                    raise ValueError("data gate does not match active task")
                task["data_gate"] = payload
            elif kind == "incident":
                task = state["active_task"]
                if task is None or payload["task_id"] != task["task_id"]:
                    raise ValueError("incident does not match active task")
                task["status"] = "repair_pending"
                task["incident_id"] = payload["incident_id"]
                state["incidents"].append(payload)
            elif kind == "task_close":
                task = state["active_task"]
                if task is None or payload["task_id"] != task["task_id"]:
                    raise ValueError("close does not match active task")
                state["active_task"] = None
            else:
                raise ValueError("unknown watchdog event")
            state["seq"] = event["seq"]
            state["head_sha256"] = sha
            state["last_event_utc"] = event["time_utc"]
        if not state["initialized"]:
            raise ValueError("watchdog journal lacks initialization")
        return state

    def _append(self, kind: str, payload: dict, now: datetime | None) -> dict:
        state = self._replay()
        event = {"schema": SCHEMA, "seq": state["seq"] + 1,
                 "time_utc": _now(now), "event": kind, "payload": payload,
                 "prev_sha256": state["head_sha256"]}
        event["sha256"] = _digest(event)
        with self.journal.open("ab") as handle:
            handle.write(_canonical(event) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        state = self._replay()
        _replace_json(self.snapshot_path, state)
        return state

    def initialize(self, *, now: datetime | None = None) -> dict:
        with self._locked():
            if self.journal.exists():
                raise FileExistsError("watchdog already initialized")
            return self._append("initialize", {}, now)

    def snapshot(self) -> dict:
        with self._locked():
            return self._replay()

    def claim_task(self, *, task_id: str, task_kind: str, stage: str, owner: str,
                   heartbeat_timeout_seconds: int, progress_timeout_seconds: int,
                   input_sha256: str, process_identity: dict | None = None,
                   container_identity: dict | None = None,
                   data_admission_sha256: str | None = None,
                   now: datetime | None = None) -> dict:
        with self._locked():
            state = self._replay()
            if not state["initialized"] or state["active_task"] is not None:
                raise ValueError("watchdog is not idle")
            _identifier(task_id, "task ID")
            if task_kind not in TASK_KINDS:
                raise ValueError("invalid task kind")
            if task_kind in {"training", "evaluation"}:
                _sha(data_admission_sha256, "data admission")
            elif data_admission_sha256 is not None:
                raise ValueError("data admission receipt is only bound to training/evaluation")
            _identifier(stage, "stage")
            _identifier(owner, "owner")
            if (type(heartbeat_timeout_seconds) is not int
                    or type(progress_timeout_seconds) is not int
                    or not 5 <= heartbeat_timeout_seconds <= 3600
                    or not heartbeat_timeout_seconds <= progress_timeout_seconds <= 21600):
                raise ValueError("invalid watchdog deadlines")
            _sha(input_sha256, "task input")
            if process_identity is not None and set(process_identity) != {"pid", "command_sha256"}:
                raise ValueError("exact process identity required")
            if process_identity is not None:
                if type(process_identity["pid"]) is not int or process_identity["pid"] <= 1:
                    raise ValueError("invalid process PID")
                _sha(process_identity["command_sha256"], "process command")
            if container_identity is not None and set(container_identity) != {"name", "label"}:
                raise ValueError("exact container identity required")
            if container_identity is not None:
                _identifier(container_identity["name"], "container name")
                _identifier(container_identity["label"], "container label")
            started = _now(now)
            payload = {"task_id": task_id, "task_kind": task_kind,
                       "stage": stage, "owner": owner, "status": "active",
                       "started_utc": started, "last_heartbeat_utc": started,
                       "last_progress_utc": started, "progress_seq": 0,
                       "last_progress_sha256": None,
                       "heartbeat_timeout_seconds": heartbeat_timeout_seconds,
                       "progress_timeout_seconds": progress_timeout_seconds,
                       "input_sha256": input_sha256,
                       "data_admission_sha256": data_admission_sha256,
                       "process_identity": process_identity,
                       "container_identity": container_identity,
                       "data_gate": None, "incident_id": None}
            return self._append("task_claim", payload, now)

    def close_success(self, task_id: str, *, result_sha256: str,
                      now: datetime | None = None) -> dict:
        """Close a healthy task; data work must carry a passing gate first."""
        with self._locked():
            task = self._replay()["active_task"]
            if task is None or task["task_id"] != task_id or task["status"] != "active":
                raise ValueError("matching active task required")
            _sha(result_sha256, "task result")
            if (task["task_kind"] == "data"
                    and (task["data_gate"] is None
                         or task["data_gate"]["passed"] is not True)):
                raise ValueError("data task cannot close successfully before its gate passes")
            return self._append("task_close", {
                "task_id": task_id, "outcome": "passed",
                "result_sha256": result_sha256,
                "old_id_reusable": False}, now)

    def heartbeat(self, task_id: str, *, material_progress: bool,
                  progress_sha256: str | None = None,
                  now: datetime | None = None) -> dict:
        with self._locked():
            task = self._replay()["active_task"]
            if task is None or task["task_id"] != task_id or task["status"] != "active":
                raise ValueError("task is not active")
            if type(material_progress) is not bool:
                raise ValueError("progress flag must be boolean")
            if material_progress:
                _sha(progress_sha256, "progress evidence")
            elif progress_sha256 is not None:
                raise ValueError("nonmaterial heartbeat cannot carry progress evidence")
            return self._append("heartbeat", {"task_id": task_id,
                         "material_progress": material_progress,
                         "progress_sha256": progress_sha256}, now)

    def record_data_gate(self, task_id: str, *, passed: bool,
                         evidence_sha256: str,
                         now: datetime | None = None) -> dict:
        with self._locked():
            task = self._replay()["active_task"]
            if task is None or task["task_id"] != task_id or task["task_kind"] != "data":
                raise ValueError("active data task required")
            if type(passed) is not bool:
                raise ValueError("data gate result must be boolean")
            _sha(evidence_sha256, "data gate evidence")
            return self._append("data_gate", {"task_id": task_id,
                         "passed": passed, "evidence_sha256": evidence_sha256}, now)

    def tick(self, *, now: datetime | None = None, evidence: dict) -> dict | None:
        with self._locked():
            state = self._replay()
            task = state["active_task"]
            if task is None or task["status"] != "active":
                return None
            required = {"process", "container", "data", "budget", "log_tail_sha256"}
            if not isinstance(evidence, dict) or set(evidence) != required:
                raise ValueError("complete watchdog evidence required")
            _sha(evidence["log_tail_sha256"], "log tail")
            self._validate_evidence(task, evidence)
            observed = _time(_now(now))
            heartbeat_age = (observed - _time(task["last_heartbeat_utc"])).total_seconds()
            progress_age = (observed - _time(task["last_progress_utc"])).total_seconds()
            classification = None
            if task["data_gate"] is not None and task["data_gate"]["passed"] is False:
                classification = "data_admission_failure"
            elif heartbeat_age > task["heartbeat_timeout_seconds"]:
                classification = "worker_heartbeat_timeout"
            elif progress_age > task["progress_timeout_seconds"]:
                classification = "no_material_progress"
            if classification is None:
                return None
            return self._incident(task, state, classification, evidence, now)

    def report_failure(self, task_id: str, *, classification: str,
                       evidence: dict, now: datetime | None = None) -> dict:
        """Freeze an immediate causal failure without waiting for a deadline."""
        allowed = {"worker_error", "cleanup_failure", "budget_state_mismatch",
                   "malformed_data"}
        if classification not in allowed:
            raise ValueError("failure classification is not allowlisted")
        with self._locked():
            state = self._replay()
            task = state["active_task"]
            if (task is None or task["task_id"] != task_id
                    or task["status"] != "active"):
                raise ValueError("matching active task required")
            if not isinstance(evidence, dict) or set(evidence) != {
                    "process", "container", "data", "budget", "log_tail_sha256"}:
                raise ValueError("complete watchdog evidence required")
            _sha(evidence["log_tail_sha256"], "log tail")
            self._validate_evidence(task, evidence)
            return self._incident(task, state, classification, evidence, now)

    def _incident(self, task: dict, state: dict, classification: str,
                  evidence: dict, now: datetime | None) -> dict:
        incident_id = f"incident-{task['task_id']}-{state['seq'] + 1:06d}"
        plan = self._repair_plan(task, incident_id, classification)
        observed = _time(_now(now))
        heartbeat_age = (observed - _time(task["last_heartbeat_utc"])).total_seconds()
        progress_age = (observed - _time(task["last_progress_utc"])).total_seconds()
        packet = {"schema": INCIDENT_SCHEMA, "incident_id": incident_id,
                  "task_id": task["task_id"], "task_kind": task["task_kind"],
                  "stage": task["stage"], "classification": classification,
                  "detected_utc": _now(now), "heartbeat_age_seconds": heartbeat_age,
                  "progress_age_seconds": progress_age, "task_snapshot": task,
                  "evidence": evidence, "repair_plan": plan,
                  "automatic_retry": False,
                  "downstream_training_allowed": False}
        path = self.incidents / f"{incident_id}.json"
        _exclusive_json(path, packet)
        payload = {"incident_id": incident_id, "task_id": task["task_id"],
                   "classification": classification,
                   "packet_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "automatic_retry": False}
        self._append("incident", payload, now)
        return packet

    @staticmethod
    def _validate_evidence(task: dict, evidence: dict) -> None:
        process = evidence["process"]
        if (not isinstance(process, dict)
                or set(process) != {"checked", "pid", "command_sha256", "present"}
                or process["checked"] is not True or type(process["present"]) is not bool):
            raise ValueError("exact process evidence is incomplete")
        expected_process = task["process_identity"]
        if expected_process is None:
            if process["pid"] is not None or process["command_sha256"] is not None:
                raise ValueError("unexpected process identity")
        elif (process["pid"] != expected_process["pid"]
              or process["command_sha256"] != expected_process["command_sha256"]):
            raise ValueError("process evidence does not match exact task identity")

        container = evidence["container"]
        if (not isinstance(container, dict)
                or set(container) != {"checked", "name", "label", "present"}
                or container["checked"] is not True or type(container["present"]) is not bool):
            raise ValueError("exact container evidence is incomplete")
        expected_container = task["container_identity"]
        if expected_container is None:
            if container["name"] is not None or container["label"] is not None:
                raise ValueError("unexpected container identity")
        elif (container["name"] != expected_container["name"]
              or container["label"] != expected_container["label"]):
            raise ValueError("container evidence does not match exact task identity")

        data = evidence["data"]
        if (not isinstance(data, dict)
                or set(data) != {"gate_status", "evidence_sha256"}
                or data["gate_status"] not in {
                    "not_applicable", "unknown", "passed", "failed"}):
            raise ValueError("data-gate evidence is incomplete")
        if data["evidence_sha256"] is not None:
            _sha(data["evidence_sha256"], "data gate evidence")
        if task["data_gate"] is not None:
            expected_status = "passed" if task["data_gate"]["passed"] else "failed"
            if (data["gate_status"] != expected_status
                    or data["evidence_sha256"] != task["data_gate"]["evidence_sha256"]):
                raise ValueError("data evidence does not match recorded gate")

        budget = evidence["budget"]
        if (not isinstance(budget, dict)
                or set(budget) != {"checked", "task_id", "state", "snapshot_sha256"}
                or budget["checked"] is not True or budget["task_id"] != task["task_id"]
                or budget["state"] not in {
                    "none", "reserved", "dispatched", "settled", "uncertain_terminal"}):
            raise ValueError("budget evidence is incomplete")
        _sha(budget["snapshot_sha256"], "budget snapshot")

    @staticmethod
    def _repair_plan(task: dict, incident_id: str, classification: str) -> dict:
        if classification == "data_admission_failure":
            action = "Controller chooses one bounded data diagnosis; Researcher repairs; independent auditor reruns the same gate."
        else:
            action = "Supervisor isolates the exact failed layer, preserves evidence, applies one causal repair, then runs a minimal canary."
        return {"schema": PLAN_SCHEMA, "incident_id": incident_id,
                "steps": [
                    {"order": 1, "owner": "supervisor", "action": "freeze exact logs, process/container identity, data gate and budget evidence", "pass": "all evidence fields present and hash-bound"},
                    {"order": 2, "owner": "supervisor", "action": "classify infrastructure, data, or scientific cause without changing the original result", "pass": f"classification remains {classification}"},
                    {"order": 3, "owner": "controller_researcher", "action": action, "pass": "bounded repair artifact and tests exist"},
                    {"order": 4, "owner": "independent_checker", "action": "run the predeclared minimal canary", "pass": "canary passes under repaired source"},
                    {"order": 5, "owner": "supervisor", "action": "close the failed task and permit only a fresh run ID", "pass": "old ID remains terminal and new ID was never claimed"},
                ],
                "scientific_outcome_retry_allowed": False,
                "same_id_retry_allowed": False}

    def close_after_verified_repair(self, task_id: str, *, incident_id: str,
                                    canary_sha256: str, fresh_resume_id: str,
                                    now: datetime | None = None) -> dict:
        with self._locked():
            state = self._replay()
            task = state["active_task"]
            if (task is None or task["task_id"] != task_id
                    or task["status"] != "repair_pending"
                    or task["incident_id"] != incident_id):
                raise ValueError("matching repair-pending task required")
            _sha(canary_sha256, "repair canary")
            _identifier(fresh_resume_id, "fresh resume ID")
            if fresh_resume_id == task_id or fresh_resume_id in state["claimed_task_ids"]:
                raise ValueError("repair requires a never-used ID")
            incident = next(item for item in state["incidents"]
                            if item["incident_id"] == incident_id)
            if incident["classification"] not in {
                    "worker_heartbeat_timeout", "no_material_progress",
                    "data_admission_failure", "worker_error", "cleanup_failure",
                    "budget_state_mismatch", "malformed_data"}:
                raise ValueError("scientific result cannot be repaired into a retry")
            return self._append("task_close", {
                "task_id": task_id, "outcome": "repaired_canary_passed",
                "incident_id": incident_id, "canary_sha256": canary_sha256,
                "fresh_resume_id": fresh_resume_id,
                "old_id_reusable": False}, now)
