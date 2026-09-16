#!/usr/bin/env python3
"""Stdio MCP broker for the Train-only objective-discovery controller."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from controller_activity_log import append_activity, read_activity_events
from market_rsi import canonical, digest, file_hash
from objective_contract import build_objective_contract
from objective_discovery_activity import assess_objective_activity
from objective_discovery_harness import discovery_harness_contract
from objective_discovery_workspace import (
    automatic_audit,
    read_json,
    search_literature,
    validate_workspace,
)


TOOLS = [
    {
        "name": "inspect_open_train_source_inventory",
        "description": "Inspect which opened-Train quote, trade and resolution streams actually exist. No Dev exists in this phase.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "run_automatic_time_series_data_diagnostics",
        "description": "Read the runner-owned first-pass Train diagnostics: cadence, coverage, flatness, scale and naive-baseline strength.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "profile_open_train_cadence",
        "description": "Read the opened-Train decision cadence and source-cadence evidence.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "profile_open_train_target",
        "description": "Inspect coverage and baseline diagnostics for one objective family on opened Train only.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["objective_id"], "properties": {
                            "objective_id": {"type": "string", "minLength": 1, "maxLength": 200}}},
    },
    {
        "name": "search_public_literature",
        "description": "Search the frozen public time-series and market-microstructure literature snapshot.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["query"], "properties": {
                            "query": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "max_results": {"type": "integer", "minimum": 1, "maximum": 8}}},
    },
    {
        "name": "list_objective_families",
        "description": "List a non-exhaustive objective catalog. The controller may propose a new objective, but it must be executable and audited before selection.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "propose_objective_definition",
        "description": "Write one immutable objective proposal with its causal clock, baseline, metrics and validation plan.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": [
                            "proposal_id", "objective_id", "research_question",
                            "label_formula", "source_and_availability_clock",
                            "horizon_and_window", "minimum_coverage", "baseline",
                            "raw_and_scale_free_scores", "expected_failure_condition",
                            "required_materializer_and_validation_tests", "literature_ids",
                        ], "properties": {
                            "proposal_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,99}$"},
                            "objective_id": {"type": "string", "minLength": 1, "maxLength": 200},
                            "research_question": {"type": "string", "minLength": 1, "maxLength": 4000},
                            "label_formula": {"type": "string", "minLength": 1, "maxLength": 4000},
                            "source_and_availability_clock": {"type": "string", "minLength": 1, "maxLength": 4000},
                            "horizon_and_window": {"type": "string", "minLength": 1, "maxLength": 2000},
                            "minimum_coverage": {"type": "number", "minimum": 0, "maximum": 1},
                            "baseline": {"type": "string", "minLength": 1, "maxLength": 2000},
                            "raw_and_scale_free_scores": {"type": "string", "minLength": 1, "maxLength": 2000},
                            "expected_failure_condition": {"type": "string", "minLength": 1, "maxLength": 4000},
                            "required_materializer_and_validation_tests": {
                                "type": "array", "minItems": 1, "maxItems": 20,
                                "items": {"type": "string", "minLength": 1, "maxLength": 1000}},
                            "literature_ids": {"type": "array", "maxItems": 12,
                                "items": {"type": "string", "minLength": 1, "maxLength": 200}},
                        }},
    },
    {
        "name": "run_open_train_objective_audit",
        "description": "Validate one immutable proposal against the runner-owned opened-Train objective audit. This cannot use Dev or model scores.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["proposal_id"], "properties": {
                            "proposal_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,99}$"}}},
    },
    {
        "name": "compare_open_train_objective_stability",
        "description": "Compare two or more already-audited objective proposals by Train coverage, scale, stability and persistence baseline; no automatic winner is chosen.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["proposal_ids"], "properties": {
                            "proposal_ids": {"type": "array", "minItems": 2, "maxItems": 8,
                                "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,99}$"}}}},
    },
    {
        "name": "submit_objective_decision",
        "description": "Freeze the first valid, previously audited objective decision. Dev can be scheduled only after this succeeds.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["action", "proposal_id", "objective_id",
                                     "rationale", "evidence", "literature_ids",
                                     "expected_failure_condition", "limitations"],
                        "properties": {
                            "action": {"type": "string", "enum": ["select"]},
                            "proposal_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,99}$"},
                            "objective_id": {"type": "string", "minLength": 1, "maxLength": 200},
                            "rationale": {"type": "string", "minLength": 1, "maxLength": 4000},
                            "evidence": {"type": "string", "minLength": 1, "maxLength": 8000},
                            "literature_ids": {"type": "array", "minItems": 1, "maxItems": 12,
                                "items": {"type": "string", "minLength": 1, "maxLength": 200}},
                            "expected_failure_condition": {"type": "string", "minLength": 1, "maxLength": 4000},
                            "limitations": {"type": "string", "minLength": 1, "maxLength": 4000},
                        }},
    },
]

ALLOWED_TOOLS = tuple(item["name"] for item in TOOLS)
PROPOSAL_FIELDS = set(TOOLS[6]["inputSchema"]["required"])
DECISION_FIELDS = set(
    TOOLS[9]["inputSchema"]["required"]
)
EGRESS_POLICY = discovery_harness_contract()["external_egress"]
FORBIDDEN_EGRESS_KEYS = set(EGRESS_POLICY["forbidden_keys"])
MAX_EGRESS_BYTES = EGRESS_POLICY["maximum_tool_result_bytes"]


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


class Broker:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.manifest = validate_workspace(self.workspace)
        self.sequence = 0

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

    def _proposal_path(self, proposal_id: str) -> Path:
        if not isinstance(proposal_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", proposal_id):
            raise ValueError("safe objective proposal ID required")
        return self.workspace / "objective-proposals" / f"{proposal_id}.json"

    def _audit_path(self, proposal_id: str) -> Path:
        self._proposal_path(proposal_id)
        return self.workspace / "objective-audits" / f"{proposal_id}.json"

    def _read_proposal(self, proposal_id: str) -> dict:
        path = self._proposal_path(proposal_id)
        if path.is_symlink() or not path.is_file():
            raise ValueError("objective proposal does not exist")
        return json.loads(path.read_bytes())

    def _read_audit(self, proposal_id: str) -> dict:
        path = self._audit_path(proposal_id)
        if path.is_symlink() or not path.is_file():
            raise ValueError("objective proposal has not been audited")
        return json.loads(path.read_bytes())

    def _write_once(self, path: Path, value: dict) -> None:
        encoded = canonical(value).encode() + b"\n"
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

    def _audit_egress(self, name: str, result: dict) -> None:
        encoded = canonical(result).encode()
        forbidden = sorted(set(_walk_keys(result)) & FORBIDDEN_EGRESS_KEYS)
        if forbidden or len(encoded) > MAX_EGRESS_BYTES:
            raise ValueError(
                f"controller result violates aggregate-only egress policy: "
                f"forbidden_keys={forbidden}, bytes={len(encoded)}"
            )
        self._log("controller-egress-audit.jsonl", {
            "kind": "aggregate_tool_result_released",
            "tool": name,
            "bytes": len(encoded),
            "result_sha256": digest(result),
            "raw_rows_released": False,
            "market_identity_released": False,
            "timestamps_released": False,
            "local_paths_released": False,
        })

    def _objective_event(self, name: str, arguments: dict, result, error) -> None:
        kinds = {
            "inspect_open_train_source_inventory": "source_inventory_read",
            "run_automatic_time_series_data_diagnostics": "automatic_diagnostics_read",
            "profile_open_train_cadence": "cadence_profile_read",
            "profile_open_train_target": "target_profile_read",
            "list_objective_families": "objective_catalog_read",
            "propose_objective_definition": "objective_proposed",
            "run_open_train_objective_audit": "objective_audit_completed",
            "compare_open_train_objective_stability": "objective_stability_compared",
            "submit_objective_decision": "objective_selected",
        }
        kind = kinds[name] + ("_failed" if error is not None else "")
        event = {
            "kind": kind,
            "proposal_id": arguments.get("proposal_id"),
            "objective_id": arguments.get("objective_id"),
            "arguments_sha256": digest(arguments),
            "result_sha256": digest(result) if error is None else None,
            "error_type": type(error).__name__ if error is not None else None,
        }
        if name == "run_open_train_objective_audit" and error is None:
            event["status"] = result.get("status")
        self._log("objective-activity.jsonl", event)

    def call(self, name: str, arguments: dict) -> dict:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        result = None
        error = None
        try:
            if name == "inspect_open_train_source_inventory" and not arguments:
                result = read_json(self.workspace, "source-inventory.json")
                result = {key: value for key, value in result.items()
                          if key != "source_path"}
            elif name == "run_automatic_time_series_data_diagnostics" and not arguments:
                result = read_json(self.workspace, "automatic-diagnostics.json")
            elif name == "profile_open_train_cadence" and not arguments:
                diagnostics = read_json(self.workspace, "automatic-diagnostics.json")
                result = {
                    "opened_train_utc_dates": diagnostics["opened_train_utc_dates"],
                    "decision_cadence_seconds": diagnostics["decision_cadence_seconds"],
                    "raw_quote_cadence_receipt_present": diagnostics["source_inventory"]["raw_quote_cadence_receipt_present"],
                    "evidence_class": "opened_train_only",
                }
            elif name == "profile_open_train_target" and set(arguments) == {"objective_id"}:
                objective_id = arguments["objective_id"]
                audited = automatic_audit(self.workspace)
                if audited["status"] == "completed":
                    candidate = audited["result"]["candidate_diagnostics"].get(objective_id)
                else:
                    candidate = None
                if candidate is None and objective_id == "future-midpoint-point-60s-v1":
                    candidate = read_json(self.workspace, "automatic-diagnostics.json")["point_target"]
                if candidate is None:
                    raise ValueError("objective has no executable opened-Train diagnostic")
                result = {"objective_id": objective_id, "diagnostic": candidate,
                          "dev_labels_used": False, "candidate_model_scores_used": False}
            elif name == "search_public_literature" and set(arguments) <= {"query", "max_results"} \
                    and "query" in arguments:
                result = search_literature(
                    self.workspace, arguments["query"], arguments.get("max_results", 5)
                )
                self._log("literature-activity.jsonl", {
                    "kind": "literature_search_completed",
                    "query": arguments["query"],
                    "result_sha256": digest(result),
                    "results": [{key: paper[key] for key in
                                 ("paper_id", "title", "url", "year", "content_sha256")}
                                for paper in result["results"]],
                })
            elif name == "list_objective_families" and not arguments:
                result = read_json(self.workspace, "objective-catalog.json")
            elif name == "propose_objective_definition" and set(arguments) == PROPOSAL_FIELDS:
                proposal_id = arguments["proposal_id"]
                target = self._proposal_path(proposal_id)
                if target.exists():
                    raise ValueError("objective proposal ID already claimed")
                if not isinstance(arguments["objective_id"], str) or not arguments["objective_id"].strip():
                    raise ValueError("objective_id must be a nonempty string")
                if (isinstance(arguments["minimum_coverage"], bool)
                        or not isinstance(arguments["minimum_coverage"], (int, float))
                        or not 0 <= arguments["minimum_coverage"] <= 1):
                    raise ValueError("minimum_coverage must be a number in [0,1]")
                tests = arguments["required_materializer_and_validation_tests"]
                if (not isinstance(tests, list) or not tests or len(tests) > 20
                        or any(not isinstance(item, str) or not item.strip()
                               for item in tests)):
                    raise ValueError("one to twenty nonempty validation tests are required")
                literature_ids = arguments["literature_ids"]
                if (not isinstance(literature_ids, list) or len(literature_ids) > 12
                        or any(not isinstance(item, str) or not item.strip()
                               for item in literature_ids)
                        or len(set(literature_ids)) != len(literature_ids)):
                    raise ValueError("literature_ids must be a unique bounded string list")
                for key in PROPOSAL_FIELDS - {
                    "minimum_coverage", "required_materializer_and_validation_tests",
                    "literature_ids", "proposal_id"
                }:
                    if not isinstance(arguments[key], str) or not arguments[key].strip():
                        raise ValueError(f"{key} must be a nonempty string")
                stored = dict(arguments, literature_ids=sorted(literature_ids))
                self._write_once(target, stored)
                result = {"written": proposal_id, "proposal_sha256": file_hash(target)}
            elif name == "run_open_train_objective_audit" and set(arguments) == {"proposal_id"}:
                proposal = self._read_proposal(arguments["proposal_id"])
                target = self._audit_path(arguments["proposal_id"])
                if target.exists():
                    raise ValueError("objective proposal already audited")
                automatic = automatic_audit(self.workspace)
                if automatic["status"] != "completed":
                    raise ValueError(
                        "current materialization cannot execute window-objective audit: "
                        + automatic.get("message", "unknown audit failure")
                    )
                diagnostic = automatic["result"]["candidate_diagnostics"].get(
                    proposal["objective_id"]
                )
                if diagnostic is None:
                    raise ValueError(
                        "proposed objective is not executable in the frozen materializer; "
                        "implement and test it in a new pre-controller preparation"
                    )
                coverage = diagnostic.get("coverage_fraction")
                if not isinstance(coverage, (int, float)) or coverage < proposal["minimum_coverage"]:
                    raise ValueError("objective does not meet its declared Train coverage")
                result = {
                    "schema": "market_open_train_objective_proposal_audit_v1",
                    "status": "completed",
                    "proposal_id": proposal["proposal_id"],
                    "proposal_sha256": file_hash(self._proposal_path(proposal["proposal_id"])),
                    "objective_id": proposal["objective_id"],
                    "diagnostic": diagnostic,
                    "train_audit_sha256": automatic["result"]["audit_sha256"],
                    "dev_labels_used": False,
                    "future_test_used": False,
                    "candidate_model_scores_used": False,
                }
                self._write_once(target, result)
            elif name == "compare_open_train_objective_stability" \
                    and set(arguments) == {"proposal_ids"}:
                proposal_ids = arguments["proposal_ids"]
                if (not isinstance(proposal_ids, list) or len(proposal_ids) < 2
                        or len(proposal_ids) > 8 or proposal_ids != list(dict.fromkeys(proposal_ids))):
                    raise ValueError("two to eight unique audited proposal IDs required")
                audits = [self._read_audit(proposal_id) for proposal_id in proposal_ids]
                result = {
                    "schema": "market_open_train_objective_comparison_v1",
                    "automatic_selection": False,
                    "comparison_axes": ["coverage", "raw_scale", "persistence_error",
                                        "window_half_stability", "effective_horizon"],
                    "candidates": [{"proposal_id": audit["proposal_id"],
                                    "objective_id": audit["objective_id"],
                                    "diagnostic": audit["diagnostic"]}
                                   for audit in audits],
                    "dev_labels_used": False,
                }
            elif name == "submit_objective_decision" and set(arguments) == DECISION_FIELDS:
                target = self.workspace / "submitted-objective-decision.json"
                contract_path = self.workspace / "frozen-objective-contract.json"
                if target.exists() or contract_path.exists():
                    raise ValueError("objective decision already submitted")
                decision = arguments
                if (decision["action"] != "select"
                        or any(not isinstance(decision[key], str) or not decision[key].strip()
                               for key in DECISION_FIELDS - {"literature_ids"})
                        or not isinstance(decision["literature_ids"], list)
                        or not decision["literature_ids"]
                        or any(not isinstance(item, str) or not item.strip()
                               for item in decision["literature_ids"])
                        or len(set(decision["literature_ids"])) != len(decision["literature_ids"])):
                    raise ValueError("final objective decision schema is incomplete")
                decision = dict(decision, literature_ids=sorted(decision["literature_ids"]))
                proposal = self._read_proposal(decision["proposal_id"])
                audited = self._read_audit(decision["proposal_id"])
                if (decision["objective_id"] != proposal["objective_id"]
                        or audited["objective_id"] != proposal["objective_id"]
                        or audited["status"] != "completed"):
                    raise ValueError("decision does not match one completed Train-only audit")
                seen_literature = {
                    paper["paper_id"]
                    for event in read_activity_events(self.workspace / "literature-activity.jsonl")
                    if event.get("kind") == "literature_search_completed"
                    for paper in event.get("results", [])
                }
                if not set(decision["literature_ids"]) <= seen_literature:
                    raise ValueError("decision cites literature not returned in this session")
                contract = build_objective_contract(
                    experiment_id=self.manifest["experiment_id"],
                    objective_id=decision["objective_id"],
                    train_diagnostics_sha256=audited["train_audit_sha256"],
                    literature_snapshot_sha256=file_hash(
                        self.workspace / "literature-snapshot.json"
                    ),
                    literature_ids=decision["literature_ids"],
                    evidence_class=self.manifest["evidence_class"],
                )
                self._write_once(target, decision)
                self._write_once(contract_path, contract)
                result = {"submitted": True, "bytes": len(canonical(decision).encode()),
                          "objective_contract_sha256": contract["objective_contract_sha256"]}
            else:
                if name == "propose_objective_definition":
                    missing = sorted(PROPOSAL_FIELDS - set(arguments))
                    extra = sorted(set(arguments) - PROPOSAL_FIELDS)
                    raise ValueError(
                        f"objective proposal fields changed; missing={missing}, extra={extra}"
                    )
                if name == "submit_objective_decision":
                    missing = sorted(DECISION_FIELDS - set(arguments))
                    extra = sorted(set(arguments) - DECISION_FIELDS)
                    raise ValueError(
                        f"final decision fields changed; missing={missing}, extra={extra}"
                    )
                raise ValueError("unknown objective-discovery tool or invalid arguments")
            self._audit_egress(name, result)
        except Exception as caught:
            error = caught
            if name == "search_public_literature":
                self._log("literature-activity.jsonl", {
                    "kind": "literature_search_failed",
                    "query": arguments.get("query"),
                    "arguments_sha256": digest(arguments),
                    "error_type": type(caught).__name__,
                })
            elif name in ALLOWED_TOOLS:
                self._objective_event(name, arguments, None, caught)
            self._journal(name, arguments, error=caught)
            raise
        if name != "search_public_literature":
            self._objective_event(name, arguments, result, None)
        self._journal(name, arguments, result=result)
        return result

    def log_assessment(self) -> dict:
        return assess_objective_activity(self.workspace)


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
        request = None
        try:
            request = json.loads(raw)
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                reply(request_id, {"protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "market-objective-discovery-tools", "version": "1"}})
            elif method == "ping":
                reply(request_id, {})
            elif method == "tools/list":
                reply(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    value = broker.call(params.get("name"), params.get("arguments", {}))
                except ValueError as validation_error:
                    value = {"accepted": False, "recoverable": True,
                             "error_type": "ValueError", "message": str(validation_error)}
                reply(request_id, {"content": [{"type": "text", "text": json.dumps(
                    value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}],
                    "isError": False})
            elif request_id is not None:
                reply(request_id, error="unsupported MCP method")
        except Exception as caught:
            request_id = request.get("id") if isinstance(request, dict) else None
            if request_id is not None:
                reply(request_id, error=caught)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parsed = parser.parse_args()
    os.environ.clear()
    serve(Broker(parsed.workspace))
