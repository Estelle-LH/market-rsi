#!/usr/bin/env python3
"""Stdio MCP broker for the controller's allowlisted research actions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from candidate_integrity import validate_candidate_source
from controller_activity_log import append_activity, assess_activity_logs, read_activity_events
from controller_workspace import (ExecutionQueue, inspect, inspect_algorithm, list_algorithms,
                                  read_harness_profile, read_objective_contract,
                                  read_research_guide, search_literature,
                                  validate_workspace)
from market_rsi import canonical, digest


TOOLS = [
    {
        "name": "inspect_train_dev",
        "description": "Inspect allowed Train labels and label-free Dev features by summary or page.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "properties": {
                            "view": {"type": "string", "enum": ["summary", "rows"]},
                            "split": {"type": "string", "enum": ["train", "dev"]},
                            "offset": {"type": "integer", "minimum": 0},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
    },
    {
        "name": "read_harness_profile",
        "description": "Read the active baked-in research workbench profile and its immutable authority boundary.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "read_objective_contract",
        "description": "Read the immutable target, horizon, baseline and score selected before Dev scheduling.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "read_research_guide",
        "description": "Read the fixed research process and logging guidance; it does not prescribe an answer.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "search_public_literature",
        "description": "Search public literature through the runner-owned snapshot service.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["query"], "properties": {
                            "query": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "max_results": {"type": "integer", "minimum": 1, "maximum": 8}}},
    },
    {
        "name": "list_algorithms",
        "description": "List the frozen capability catalog; the controller may also create methods outside it.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "properties": {"family": {"type": "string", "minLength": 1,
                                                   "maxLength": 200}}},
    },
    {
        "name": "inspect_algorithm",
        "description": "Read assumptions, dependencies, cost and risks for one catalog method.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["algorithm_id"], "properties": {
                            "algorithm_id": {"type": "string", "minLength": 1,
                                             "maxLength": 200}}},
    },
    {
        "name": "write_candidate",
        "description": (
            "Write one candidate and its research rationale inside the isolated workspace. "
            "The name MUST be a flat lowercase Python filename ending in .py, for example "
            "queue_imbalance_v1.py. Omit parent_candidate for the first candidate; never send "
            "an empty parent. Use archive_parent only when copying or changing an exact candidate "
            "listed in read_own_research_history."
        ),
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["name", "content", "algorithm_family", "hypothesis",
                                     "literature_ids", "change_summary"], "properties": {
                            "name": {"type": "string", "pattern": "^[a-z0-9_-]+\\.py$"},
                            "content": {"type": "string", "maxLength": 131072},
                            "algorithm_family": {"type": "string", "minLength": 1,
                                                   "maxLength": 200},
                            "hypothesis": {"type": "string", "minLength": 1,
                                           "maxLength": 4000},
                            "literature_ids": {"type": "array", "maxItems": 8,
                                               "items": {"type": "string", "minLength": 1,
                                                         "maxLength": 200}},
                            "change_summary": {"type": "string", "minLength": 1,
                                               "maxLength": 2000},
                            "parent_candidate": {"type": "string",
                                                 "pattern": "^[a-z0-9_-]+\\.py$"},
                            "archive_parent": {"type": "object",
                                "additionalProperties": False,
                                "required": ["session_id", "candidate", "source_sha256"],
                                "properties": {
                                    "session_id": {"type": "string", "minLength": 1,
                                                   "maxLength": 100},
                                    "candidate": {"type": "string",
                                                  "pattern": "^[a-z0-9_-]+\\.py$"},
                                    "source_sha256": {"type": "string",
                                                      "pattern": "^[0-9a-f]{64}$"}}}}},
    },
    {
        "name": "run_train_cv_candidate",
        "description": (
            "Ask the runner to execute one candidate on a reusable temporal CV slice made only "
            "from already-open Train data. This never scores the current sealed Dev."
        ),
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["name"], "properties": {
                            "name": {"type": "string", "pattern": "^[a-z0-9_-]+\\.py$"}}},
    },
    {
        "name": "read_own_research_history",
        "description": "Read only this arm-task's saved research history.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "properties": {}},
    },
    {
        "name": "submit_decision",
        "description": "Submit the final bounded controller decision for runner validation.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["decision"], "properties": {
                            "decision": {"type": "object", "additionalProperties": False,
                                "required": ["action", "question", "hypothesis", "evidence",
                                             "candidate_artifact", "expected_failure_condition"],
                                "properties": {
                                    "action": {"type": "string", "enum": ["select"]},
                                    "question": {"type": "string", "minLength": 1},
                                    "hypothesis": {"type": "string", "minLength": 1},
                                    "evidence": {"type": "string", "minLength": 1},
                                    "candidate_artifact": {"type": "string",
                                                           "pattern": "^[a-z0-9_-]+\\.py$"},
                                    "expected_failure_condition": {"type": "string", "minLength": 1},
                                }}}},
    },
]
REQUIRED_DECISION_FIELDS = {
    "action", "question", "hypothesis", "evidence", "candidate_artifact",
    "expected_failure_condition",
}


class Broker:
    def __init__(self, workspace: Path, mode: str):
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise ValueError("controller workspace missing")
        self.mode = mode
        self.executed_candidates: set[str] = set()
        self.executed_candidate_order: list[str] = []
        self.prediction_sha256_by_candidate: dict[str, str] = {}
        self.attempted_candidates: set[str] = set()
        self.sequence = 0
        self.execution_queue = None
        if mode == "formal":
            validate_workspace(self.workspace)
            self.execution_queue = ExecutionQueue(self.workspace)

    def _log(self, name: str, event: dict) -> dict:
        return append_activity(self.workspace / name, event)

    def _journal(self, name: str, arguments: dict, *, result=None, error=None) -> None:
        self.sequence += 1
        self._log("controller-tool-journal.jsonl", {
            "tool_sequence": self.sequence,
            "tool": name,
            "arguments_sha256": digest(arguments),
            "status": "ok" if error is None else "error",
            "result_sha256": digest(result) if error is None else None,
            "error_type": type(error).__name__ if error is not None else None,
            "error_message": str(error) if isinstance(error, ValueError) else None,
        })

    def _file(self, name: str) -> Path:
        if (not isinstance(name, str) or not name.endswith(".py")
                or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-." for ch in name)
                or "/" in name or "\\" in name or name.startswith(".")):
            raise ValueError("flat lowercase candidate filename required")
        return self.workspace / name

    def _normalize_selected_candidate(self, value: str) -> tuple[str, bool]:
        """Accept one unambiguous executed filename with optional prose metadata."""
        if value in self.executed_candidates:
            return value, False
        if not isinstance(value, str):
            raise ValueError("candidate_artifact must be an executed filename only")
        if re.fullmatch(r"[a-z0-9_-]+\.py", value):
            return value, False
        prefix = re.match(r"^([a-z0-9_-]+\.py)\s+\(.+\)$", value, re.DOTALL)
        candidate = prefix.group(1) if prefix else None
        if candidate not in self.executed_candidates:
            raise ValueError("candidate_artifact must identify one executed filename")
        return candidate, True

    def call(self, name: str, arguments: dict) -> dict:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        try:
            if name == "inspect_train_dev":
                if self.mode == "canary" and not arguments:
                    result = json.loads((self.workspace / "train-dev-summary.json").read_text())
                elif self.mode == "formal":
                    result = inspect(self.workspace, arguments)
                else:
                    raise ValueError("invalid canary inspection arguments")
            elif name == "read_harness_profile" and not arguments:
                if self.mode == "canary":
                    result = {"schema": "synthetic-harness-profile", "generation": 0,
                              "workflow_suggestions": ["inspect", "test", "record"],
                              "tool_proposals": []}
                else:
                    result = read_harness_profile(self.workspace)
            elif name == "read_objective_contract" and not arguments:
                if self.mode == "canary":
                    result = {"schema": "synthetic-objective", "objective_id": "fixture"}
                else:
                    result = read_objective_contract(self.workspace)
            elif name == "read_research_guide" and not arguments:
                if self.mode == "canary":
                    result = {"schema": "synthetic-guide", "steps": ["inspect", "test", "record"]}
                else:
                    result = read_research_guide(self.workspace)
            elif name == "search_public_literature" and set(arguments) <= {"query", "max_results"} \
                    and "query" in arguments:
                if self.mode == "canary":
                    result = {"query": arguments["query"], "results": [{
                        "paper_id": "offline-canary-paper", "title": "Offline canary paper",
                        "url": "https://example.invalid/canary", "year": 2026,
                        "abstract": "Synthetic result; not research evidence.",
                        "content_sha256": hashlib.sha256(
                            b"Synthetic result; not research evidence.").hexdigest()}]}
                else:
                    result = search_literature(self.workspace, arguments["query"],
                                               arguments.get("max_results", 5))
                self._log("literature-activity.jsonl", {
                    "kind": "literature_search_completed",
                    "query": arguments["query"],
                    "max_results": arguments.get("max_results", 5),
                    "snapshot_sha256": result.get("snapshot_sha256"),
                    "results": [{key: paper[key] for key in
                                 ("paper_id", "title", "url", "year", "content_sha256")}
                                for paper in result["results"]],
                    "result_sha256": digest(result),
                })
            elif name == "list_algorithms" and set(arguments) <= {"family"}:
                if self.mode == "canary":
                    result = {"schema": "synthetic-catalog", "catalog_is_exhaustive": False,
                              "catalog_sha256": "0" * 64, "algorithms": [{
                                  "algorithm_id": "fixture-baseline", "family": "baseline",
                                  "summary": "Synthetic method.", "cost_class": "low"}]}
                else:
                    result = list_algorithms(self.workspace, arguments.get("family"))
                self._log("algorithm-activity.jsonl", {
                    "kind": "algorithm_catalog_listed", "family": arguments.get("family"),
                    "algorithm_ids": [item["algorithm_id"] for item in result["algorithms"]],
                    "catalog_sha256": result["catalog_sha256"], "result_sha256": digest(result),
                })
            elif name == "inspect_algorithm" and set(arguments) == {"algorithm_id"}:
                if self.mode == "canary":
                    if arguments["algorithm_id"] != "fixture-baseline":
                        raise ValueError("unknown synthetic algorithm ID")
                    result = {"algorithm": {"algorithm_id": "fixture-baseline",
                              "family": "baseline", "summary": "Synthetic method."},
                              "catalog_sha256": "0" * 64}
                else:
                    result = inspect_algorithm(self.workspace, arguments["algorithm_id"])
                self._log("algorithm-activity.jsonl", {
                    "kind": "algorithm_catalog_inspected",
                    "algorithm_id": arguments["algorithm_id"],
                    "catalog_sha256": result["catalog_sha256"], "result_sha256": digest(result),
                })
            elif name == "write_candidate" and set(arguments) in ({
                    "name", "content", "algorithm_family", "hypothesis", "literature_ids",
                    "change_summary"}, {
                    "name", "content", "algorithm_family", "hypothesis", "literature_ids",
                    "change_summary", "parent_candidate"}, {
                    "name", "content", "algorithm_family", "hypothesis", "literature_ids",
                    "change_summary", "archive_parent"}):
                target = self._file(arguments["name"])
                if target.exists():
                    raise ValueError("candidate name already claimed")
                data = arguments["content"].encode()
                literature_ids = arguments["literature_ids"]
                if (not data or len(data) > 131_072
                        or not isinstance(literature_ids, list) or len(literature_ids) > 8
                        or any(not isinstance(item, str) or not item.strip() or len(item) > 200
                               for item in literature_ids)
                        or any(not isinstance(arguments[key], str) or not arguments[key].strip()
                               for key in ("algorithm_family", "hypothesis", "change_summary"))):
                    raise ValueError("bounded candidate and research rationale required")
                seen_literature = {
                    paper["paper_id"]
                    for event in read_activity_events(self.workspace / "literature-activity.jsonl")
                    if event.get("kind") == "literature_search_completed"
                    for paper in event.get("results", [])
                }
                if not set(literature_ids) <= seen_literature:
                    raise ValueError("candidate cites literature not returned in this session")
                integrity = validate_candidate_source(arguments["content"])
                parent = arguments.get("parent_candidate")
                archive_parent = arguments.get("archive_parent")
                parent_sha256 = None
                if parent is not None:
                    parent_path = self._file(parent)
                    if not parent_path.is_file():
                        raise ValueError("parent candidate does not exist in this session")
                    parent_sha256 = hashlib.sha256(parent_path.read_bytes()).hexdigest()
                elif archive_parent is not None:
                    from archive_snapshot import find_archive_candidate, validate_history
                    history = json.loads((self.workspace / "own-history.json").read_text())
                    validate_history(history)
                    archived = find_archive_candidate(history, archive_parent)
                    parent_sha256 = archived["source_sha256"]
                with target.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                result = {"written": target.name, "bytes": len(data),
                          "source_sha256": hashlib.sha256(data).hexdigest()}
                self._log("algorithm-activity.jsonl", {
                    "kind": "candidate_written",
                    "candidate": target.name,
                    "source_sha256": result["source_sha256"],
                    "bytes": result["bytes"],
                    "algorithm_family": arguments["algorithm_family"],
                    "hypothesis": arguments["hypothesis"],
                    "literature_ids": literature_ids,
                    "change_summary": arguments["change_summary"],
                    "parent_candidate": parent,
                    "parent_source_sha256": parent_sha256,
                    "archive_parent": archive_parent,
                    "source_integrity": integrity,
                })
            elif name == "run_train_cv_candidate" and set(arguments) == {"name"}:
                target = self._file(arguments["name"])
                if not target.is_file():
                    raise ValueError("candidate does not exist")
                if target.name in self.attempted_candidates:
                    raise ValueError("candidate already executed; write a new immutable version")
                self.attempted_candidates.add(target.name)
                if self.mode == "canary":
                    result = {"candidate": target.name, "status": "completed",
                              "evaluation_role": "train_cv", "train_cv_metric": 0.50,
                              "score": {"prediction_sha256": digest({"candidate": target.name})},
                              "sealed_dev_scored": False,
                              "note": "synthetic canary result; not research evidence"}
                else:
                    result = self.execution_queue.request(target.name)
                if result.get("status") == "completed":
                    prediction_sha256 = result.get("score", {}).get("prediction_sha256")
                    if (not isinstance(prediction_sha256, str)
                            or not re.fullmatch(r"[0-9a-f]{64}", prediction_sha256)):
                        raise ValueError("completed candidate lacks a bound prediction digest")
                    equivalent = next((item for item in self.executed_candidate_order
                                       if self.prediction_sha256_by_candidate[item]
                                       == prediction_sha256), None)
                    self.executed_candidates.add(target.name)
                    self.executed_candidate_order.append(target.name)
                    self.prediction_sha256_by_candidate[target.name] = prediction_sha256
                    result = dict(result, prediction_novel=equivalent is None,
                                  prediction_equivalent_to=equivalent)
                self._log("algorithm-activity.jsonl", {
                    "kind": "candidate_execution_returned",
                    "candidate": target.name,
                    "source_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "execution_id": result.get("execution_id"),
                    "evaluation_role": result.get("evaluation_role", "train_cv"),
                    "status": result.get("status"),
                    "execution_verified": result.get("execution_verified", self.mode == "canary"),
                    "future_test_used": result.get("future_test_used", False),
                    "result_sha256": digest(result),
                    "aggregate_train_cv_score": result.get("score"),
                    "prediction_novel": result.get("prediction_novel"),
                    "prediction_equivalent_to": result.get("prediction_equivalent_to"),
                    "sealed_dev_scored": False,
                    "failure": result.get("failure"),
                })
            elif name == "read_own_research_history" and not arguments:
                result = json.loads((self.workspace / "own-history.json").read_text())
            elif name == "submit_decision" and set(arguments) == {"decision"}:
                target = self.workspace / "submitted-decision.json"
                if target.exists():
                    raise ValueError("decision already submitted")
                decision = arguments["decision"]
                if (not isinstance(decision, dict) or set(decision) != REQUIRED_DECISION_FIELDS
                        or any(not isinstance(value, str) or not value.strip()
                               for value in decision.values())
                        or decision["action"] != "select"):
                    raise ValueError("final decision requires exactly: "
                                     + ", ".join(sorted(REQUIRED_DECISION_FIELDS)))
                raw_candidate = decision["candidate_artifact"]
                candidate, normalized = self._normalize_selected_candidate(raw_candidate)
                decision = dict(decision, candidate_artifact=candidate)
                self._file(candidate)
                if self.mode == "formal" and candidate not in self.executed_candidates:
                    raise ValueError("final candidate was not independently executed in this session")
                if self.mode == "formal":
                    prediction_sha256 = self.prediction_sha256_by_candidate[candidate]
                    canonical_candidate = next(
                        item for item in self.executed_candidate_order
                        if self.prediction_sha256_by_candidate[item] == prediction_sha256)
                    if candidate != canonical_candidate:
                        raise ValueError(
                            "selected candidate is prediction-identical to earlier executed "
                            f"candidate {canonical_candidate}; select the earlier candidate or "
                            "produce behaviorally distinct predictions"
                        )
                encoded = canonical(decision).encode()
                if len(encoded) > 16_384:
                    raise ValueError("decision exceeds final envelope")
                with target.open("xb") as stream:
                    stream.write(encoded + b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                result = {"submitted": True, "bytes": len(encoded)}
                self._log("algorithm-activity.jsonl", {
                    "kind": "candidate_selected",
                    "candidate": candidate,
                    "decision_sha256": digest(decision),
                    "action": decision["action"],
                    "candidate_artifact_normalized": normalized,
                    "raw_candidate_artifact_sha256": digest(raw_candidate),
                })
            else:
                raise ValueError("unknown tool or invalid arguments")
        except Exception as error:
            if name == "search_public_literature":
                self._log("literature-activity.jsonl", {
                    "kind": "literature_search_failed",
                    "query": arguments.get("query"),
                    "arguments_sha256": digest(arguments),
                    "error_type": type(error).__name__,
                })
            elif name in {"list_algorithms", "inspect_algorithm", "write_candidate",
                           "run_train_cv_candidate", "submit_decision"}:
                event = {
                    "kind": {
                        "list_algorithms": "algorithm_catalog_list_failed",
                        "inspect_algorithm": "algorithm_catalog_inspection_failed",
                        "write_candidate": "candidate_write_failed",
                        "run_train_cv_candidate": "candidate_execution_failed",
                        "submit_decision": "candidate_selection_failed",
                    }[name],
                    "candidate": arguments.get("name") or (
                        arguments.get("decision", {}).get("candidate_artifact")
                        if isinstance(arguments.get("decision"), dict) else None),
                    "arguments_sha256": digest(arguments),
                    "source_sha256": (hashlib.sha256(arguments["content"].encode()).hexdigest()
                                      if isinstance(arguments.get("content"), str) else None),
                    "error_type": type(error).__name__,
                    "error": str(error) if isinstance(error, ValueError) else None,
                }
                if name == "inspect_algorithm":
                    event["algorithm_id"] = arguments.get("algorithm_id")
                self._log("algorithm-activity.jsonl", event)
            self._journal(name, arguments, error=error)
            raise
        self._journal(name, arguments, result=result)
        return result

    def log_assessment(self) -> dict:
        return assess_activity_logs(self.workspace)


def reply(request_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        body["result"] = result
    else:
        body["error"] = {"code": -32603, "message": str(error)}
    sys.stdout.write(json.dumps(body, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def serve(broker: Broker) -> None:
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                reply(request_id, {"protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "market-rsi-controller-tools", "version": "1"}})
            elif method == "ping":
                reply(request_id, {})
            elif method == "tools/list":
                reply(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    value = broker.call(params.get("name"), params.get("arguments", {}))
                except ValueError as error:
                    # Controller-facing validation failures are part of the
                    # research loop. Return them as ordinary tool evidence so
                    # Codex can give the controller another bounded turn.
                    value = {"accepted": False, "recoverable": True,
                             "error_type": "ValueError", "message": str(error)}
                reply(request_id, {"content": [{"type": "text", "text": json.dumps(
                    value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}],
                    "isError": False})
            elif request_id is not None:
                reply(request_id, error="unsupported MCP method")
            # Notifications deliberately have no response.
        except Exception as error:
            request_id = request.get("id") if isinstance(locals().get("request"), dict) else None
            if request_id is not None:
                reply(request_id, error=error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--mode", choices=("canary", "formal"), required=True)
    parsed = parser.parse_args()
    # A minimal deterministic environment is enough for this stdio broker.
    os.environ.clear()
    serve(Broker(parsed.workspace, parsed.mode))
