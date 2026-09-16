#!/usr/bin/env python3
"""Stdio MCP broker for controller-led historical-data research."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from controller_activity_log import append_activity, read_activity_events
from data_discovery_activity import assess_data_discovery_activity
from data_discovery_harness import data_discovery_harness_contract
from data_discovery_workspace import (inspect_source, read_json, search_literature,
                                      search_sources, validate_workspace)
from market_rsi import canonical, digest, file_hash


def _text(maximum=4000):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def _strings(minimum=1, maximum=20):
    return {"type": "array", "minItems": minimum, "maxItems": maximum,
            "items": _text(1000)}


TOOLS = [
    {"name": "inspect_current_data_audit", "description": "Inspect aggregate size, independent units, activity and baseline scale of the current opened Train history.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
    {"name": "inspect_source_canary_evidence", "description": "Inspect any runner-verified bounded source canary. A passing sample canary does not authorize a full download.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
    {"name": "list_historical_data_sources", "description": "List the frozen, non-exhaustive catalog of real historical sources and the simulator fallback.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
    {"name": "inspect_historical_data_source", "description": "Inspect one source's streams, coverage, access status and known limitations.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["source_id"], "properties": {"source_id": _text(200)}}},
    {"name": "search_historical_data_sources", "description": "Search the frozen source evidence. This is research evidence, not an automatic winner.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["query"], "properties": {"query": _text(1000), "max_results": {"type": "integer", "minimum": 1, "maximum": 8}}}},
    {"name": "search_public_literature", "description": "Search the frozen time-series and market-microstructure literature snapshot.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["query"], "properties": {"query": _text(1000), "max_results": {"type": "integer", "minimum": 1, "maximum": 8}}}},
    {"name": "propose_data_plan", "description": "Write one immutable real-data acquisition proposal. A simulator may only be a research-only sensitivity check.",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["proposal_id", "strategy", "primary_source_ids", "goal",
                                  "planned_scope", "expected_independent_units", "time_span",
                                  "microstructure_needed", "objective_compatibility", "canary_steps",
                                  "canary_acceptance_tests", "full_ingest_acceptance_tests",
                                  "rejection_conditions", "storage_cap_gb",
                                  "download_cap_gb", "simulator_role", "literature_ids"],
                     "properties": {
                         "proposal_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,99}$"},
                         "strategy": {"type": "string", "enum": ["acquire_real_history", "continue_live_capture", "combine_real_sources", "defer_until_canary"]},
                         "primary_source_ids": _strings(1, 3), "goal": _text(),
                         "planned_scope": _text(), "expected_independent_units": _text(),
                         "time_span": _text(), "microstructure_needed": _text(),
                         "objective_compatibility": _text(), "canary_steps": _strings(1, 20),
                         "canary_acceptance_tests": _strings(1, 20),
                         "full_ingest_acceptance_tests": _strings(1, 20),
                         "rejection_conditions": _strings(1, 20),
                         "storage_cap_gb": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000},
                         "download_cap_gb": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000},
                         "simulator_role": {"type": "string", "enum": ["not_used", "research_only_sensitivity_check"]},
                         "literature_ids": _strings(1, 12),
                     }}},
    {"name": "run_data_plan_feasibility_audit", "description": "Check one proposal against hard source, simulator, canary and resource rules. It never performs a download.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["proposal_id"], "properties": {"proposal_id": _text(100)}}},
    {"name": "compare_data_plans", "description": "Compare two to eight audited plans; no automatic winner is chosen.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["proposal_ids"], "properties": {"proposal_ids": _strings(2, 8)}}},
    {"name": "submit_data_decision", "description": "Freeze the first valid audited data plan. The runner's next action is only its bounded source canary.",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["action", "proposal_id", "rationale", "evidence",
                                  "rejection_trigger", "next_runner_action", "limitations"],
                     "properties": {"action": {"type": "string", "enum": ["select"]},
                                    "proposal_id": _text(100), "rationale": _text(),
                                    "evidence": _text(8000), "rejection_trigger": _text(),
                                    "next_runner_action": _text(), "limitations": _text()}}},
]

ALLOWED_TOOLS = tuple(item["name"] for item in TOOLS)
PROPOSAL_FIELDS = set(TOOLS[6]["inputSchema"]["required"])
DECISION_FIELDS = set(TOOLS[9]["inputSchema"]["required"])
EGRESS = data_discovery_harness_contract()["external_egress"]


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

    def _log(self, name, event):
        return append_activity(self.workspace / name, event)

    def _journal(self, name, arguments, *, result=None, error=None):
        self.sequence += 1
        self._log("controller-tool-journal.jsonl", {
            "tool_sequence": self.sequence, "tool": name,
            "arguments_sha256": digest(arguments),
            "status": "ok" if error is None else "error",
            "result_sha256": digest(result) if error is None else None,
            "error_type": type(error).__name__ if error is not None else None,
            "error_message": str(error) if isinstance(error, ValueError) else None,
        })

    def _write_once(self, path, value):
        with Path(path).open("xb") as stream:
            stream.write(canonical(value).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _plan_path(self, proposal_id):
        if not isinstance(proposal_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", proposal_id):
            raise ValueError("safe data proposal ID required")
        return self.workspace / "data-plans" / f"{proposal_id}.json"

    def _audit_path(self, proposal_id):
        self._plan_path(proposal_id)
        return self.workspace / "data-plan-audits" / f"{proposal_id}.json"

    def _read(self, path, missing):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError(missing)
        return json.loads(path.read_bytes())

    def _egress(self, name, result):
        raw = canonical(result).encode()
        forbidden = sorted(set(_walk_keys(result)) & set(EGRESS["forbidden_keys"]))
        if forbidden or len(raw) > EGRESS["maximum_tool_result_bytes"]:
            raise ValueError(f"aggregate-only egress violation: forbidden_keys={forbidden}")
        self._log("controller-egress-audit.jsonl", {
            "kind": "aggregate_tool_result_released", "tool": name,
            "bytes": len(raw), "result_sha256": digest(result),
            "raw_rows_released": False, "dev_released": False,
            "future_test_released": False, "local_paths_released": False,
        })

    def _activity(self, name, arguments, result, error):
        source_kinds = {"list_historical_data_sources": "data_source_catalog_read",
                        "inspect_historical_data_source": "data_source_inspected",
                        "search_historical_data_sources": "data_source_search_completed"}
        plan_kinds = {"inspect_current_data_audit": "current_data_audit_read",
                      "inspect_source_canary_evidence": "source_canary_read",
                      "propose_data_plan": "data_plan_proposed",
                      "run_data_plan_feasibility_audit": "data_plan_audit_completed",
                      "compare_data_plans": "data_plans_compared",
                      "submit_data_decision": "data_plan_selected"}
        if name in source_kinds:
            log, kind = "data-source-activity.jsonl", source_kinds[name]
        elif name in plan_kinds:
            log, kind = "data-plan-activity.jsonl", plan_kinds[name]
        else:
            return
        event = {"kind": kind + ("_failed" if error else ""),
                 "proposal_id": arguments.get("proposal_id"),
                 "arguments_sha256": digest(arguments),
                 "result_sha256": digest(result) if error is None else None,
                 "error_type": type(error).__name__ if error else None}
        if name == "run_data_plan_feasibility_audit" and error is None:
            event["status"] = result["status"]
        self._log(log, event)

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        result = error = None
        try:
            if name == "inspect_current_data_audit" and not arguments:
                result = read_json(self.workspace, "current-data-audit.json")
                result.pop("bound_source_sha256", None)
            elif name == "inspect_source_canary_evidence" and not arguments:
                result = read_json(self.workspace, "source-canary-evidence.json")
            elif name == "list_historical_data_sources" and not arguments:
                result = read_json(self.workspace, "data-source-catalog.json")
            elif name == "inspect_historical_data_source" and set(arguments) == {"source_id"}:
                result = inspect_source(self.workspace, arguments["source_id"])
            elif name == "search_historical_data_sources" and set(arguments) in ({"query"}, {"query", "max_results"}):
                result = search_sources(self.workspace, arguments["query"], arguments.get("max_results", 5))
            elif name == "search_public_literature" and set(arguments) in ({"query"}, {"query", "max_results"}):
                result = search_literature(self.workspace, arguments["query"], arguments.get("max_results", 5))
                self._log("literature-activity.jsonl", {"kind": "literature_search_completed",
                          "query": arguments["query"], "arguments_sha256": digest(arguments),
                          "results": [{"paper_id": item["paper_id"]} for item in result["results"]],
                          "result_sha256": digest(result)})
            elif name == "propose_data_plan" and set(arguments) == PROPOSAL_FIELDS:
                path = self._plan_path(arguments["proposal_id"])
                if path.exists():
                    raise ValueError("data proposal ID already claimed")
                source_ids = arguments["primary_source_ids"]
                if len(set(source_ids)) != len(source_ids):
                    raise ValueError("primary source IDs must be unique")
                for source_id in source_ids:
                    inspect_source(self.workspace, source_id)
                if "synthetic-market-simulator" in source_ids:
                    raise ValueError("simulator cannot be a primary data source")
                stored = dict(arguments,
                              primary_source_ids=sorted(source_ids),
                              literature_ids=sorted(set(arguments["literature_ids"])))
                self._write_once(path, stored)
                result = {"written": arguments["proposal_id"], "proposal_sha256": file_hash(path)}
            elif name == "run_data_plan_feasibility_audit" and set(arguments) == {"proposal_id"}:
                proposal = self._read(self._plan_path(arguments["proposal_id"]), "data proposal does not exist")
                path = self._audit_path(arguments["proposal_id"])
                if path.exists():
                    raise ValueError("data proposal already audited")
                sources = [inspect_source(self.workspace, source_id)
                           for source_id in proposal["primary_source_ids"]]
                if any(source["kind"] == "synthetic_research_only" for source in sources):
                    raise ValueError("synthetic source failed the real-history gate")
                result = {"schema": "market_data_plan_feasibility_audit_v2",
                          "status": "canary_required", "proposal_id": proposal["proposal_id"],
                          "proposal_sha256": file_hash(self._plan_path(proposal["proposal_id"])),
                          "real_source_gate": True, "sample_canary_required": True,
                          "source_canary_status": "not_run",
                          "full_ingest_status": "not_authorized",
                          "canary_acceptance_tests": proposal["canary_acceptance_tests"],
                          "full_ingest_acceptance_tests": proposal["full_ingest_acceptance_tests"],
                          "full_download_authorized": False,
                          "terms_verification_required": any(source["license_status"].startswith("must_verify") for source in sources),
                          "source_ids": proposal["primary_source_ids"],
                          "download_cap_gb": proposal["download_cap_gb"],
                          "storage_cap_gb": proposal["storage_cap_gb"],
                          "dev_used": False, "future_test_used": False}
                self._write_once(path, result)
            elif name == "compare_data_plans" and set(arguments) == {"proposal_ids"}:
                ids = arguments["proposal_ids"]
                if len(ids) < 2 or len(ids) > 8 or len(set(ids)) != len(ids):
                    raise ValueError("two to eight unique proposal IDs required")
                audits = [self._read(self._audit_path(item), "data proposal has not been audited") for item in ids]
                plans = [self._read(self._plan_path(item), "data proposal does not exist") for item in ids]
                result = {"schema": "market_data_plan_comparison_v1", "automatic_selection": False,
                          "comparison_axes": ["real_history", "independent_units", "time_span",
                                              "microstructure", "download_cap", "storage_cap",
                                              "source_gaps", "objective_compatibility"],
                          "plans": [{"proposal_id": plan["proposal_id"],
                                     "strategy": plan["strategy"],
                                     "source_ids": plan["primary_source_ids"],
                                     "planned_scope": plan["planned_scope"],
                                     "expected_independent_units": plan["expected_independent_units"],
                                     "time_span": plan["time_span"],
                                     "source_canary_status": audit["source_canary_status"],
                                     "full_ingest_status": audit["full_ingest_status"],
                                     "audit_status": audit["status"]}
                                    for plan, audit in zip(plans, audits)]}
            elif name == "submit_data_decision" and set(arguments) == DECISION_FIELDS:
                if arguments["action"] != "select":
                    raise ValueError("data decision must select one plan")
                target = self.workspace / "submitted-data-decision.json"
                frozen = self.workspace / "frozen-data-acquisition-plan.json"
                if target.exists() or frozen.exists():
                    raise ValueError("data decision already submitted")
                plan = self._read(self._plan_path(arguments["proposal_id"]), "data proposal does not exist")
                audit = self._read(self._audit_path(arguments["proposal_id"]), "data proposal has not been audited")
                seen_papers = {item["paper_id"]
                               for event in read_activity_events(self.workspace / "literature-activity.jsonl")
                               for item in event.get("results", [])}
                if not set(plan["literature_ids"]) <= seen_papers:
                    raise ValueError("plan cites literature not returned in this session")
                if audit["status"] != "canary_required" or audit["full_download_authorized"] is not False:
                    raise ValueError("selected plan did not preserve the canary gate")
                decision = dict(arguments)
                contract_body = {"schema": "market_frozen_data_acquisition_plan_v1",
                                 "experiment_id": self.manifest["experiment_id"],
                                 "proposal": plan, "feasibility_audit": audit,
                                 "decision": decision,
                                 "governance": data_discovery_harness_contract()["hard_rules"]}
                contract = {**contract_body, "plan_sha256": digest(contract_body)}
                self._write_once(target, decision)
                self._write_once(frozen, contract)
                result = {"submitted": True, "bytes": len(canonical(decision).encode()),
                          "plan_sha256": contract["plan_sha256"],
                          "next_action": "bounded_source_canary", "full_download_authorized": False}
            else:
                raise ValueError("unknown data-discovery tool or invalid arguments")
            self._egress(name, result)
        except Exception as caught:
            error = caught
            if name == "search_public_literature":
                self._log("literature-activity.jsonl", {"kind": "literature_search_failed",
                          "query": arguments.get("query"), "arguments_sha256": digest(arguments),
                          "error_type": type(caught).__name__})
            else:
                self._activity(name, arguments, None, caught)
            self._journal(name, arguments, error=caught)
            raise
        if name != "search_public_literature":
            self._activity(name, arguments, result, None)
        self._journal(name, arguments, result=result)
        return result

    def log_assessment(self):
        return assess_data_discovery_activity(self.workspace)


def reply(request_id, result=None, error=None):
    body = {"jsonrpc": "2.0", "id": request_id}
    body["result" if error is None else "error"] = result if error is None else {"code": -32603, "message": str(error)}
    sys.stdout.write(json.dumps(body, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def serve(broker):
    for raw in sys.stdin:
        request = None
        try:
            request = json.loads(raw)
            method, request_id = request.get("method"), request.get("id")
            if method == "initialize":
                reply(request_id, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "market-data-discovery-tools", "version": "1"}})
            elif method == "ping":
                reply(request_id, {})
            elif method == "tools/list":
                reply(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    value = broker.call(params.get("name"), params.get("arguments", {}))
                except ValueError as caught:
                    value = {"accepted": False, "recoverable": True, "error_type": "ValueError", "message": str(caught)}
                reply(request_id, {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True, separators=(",", ":"))}], "isError": False})
            elif request_id is not None:
                reply(request_id, error="unsupported MCP method")
        except Exception as caught:
            if isinstance(request, dict) and request.get("id") is not None:
                reply(request["id"], error=caught)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    os.environ.clear()
    serve(Broker(args.workspace))
