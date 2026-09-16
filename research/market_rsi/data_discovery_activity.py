"""Verify the append-only path to one controller-authored data plan."""
from __future__ import annotations

from pathlib import Path
import json

from controller_activity_log import read_activity_events, verify_activity_log


def assess_data_discovery_activity(workspace: Path) -> dict:
    workspace = Path(workspace)
    names = ("controller-tool-journal.jsonl", "controller-egress-audit.jsonl",
             "data-source-activity.jsonl", "literature-activity.jsonl",
             "data-plan-activity.jsonl")
    summaries = {name: verify_activity_log(workspace / name) for name in names}
    events = {name: read_activity_events(workspace / name) for name in names}
    counts = {}
    for event in events["controller-tool-journal.jsonl"]:
        counts[event.get("tool")] = counts.get(event.get("tool"), 0) + 1
    successful_calls = sum(event.get("status") == "ok"
                           for event in events["controller-tool-journal.jsonl"])
    if len(events["controller-egress-audit.jsonl"]) != successful_calls:
        raise ValueError("data-controller egress audit is incomplete")
    if counts.get("search_public_literature", 0) != len(events["literature-activity.jsonl"]):
        raise ValueError("data literature actions are not completely logged")
    source_tools = {"list_historical_data_sources", "inspect_historical_data_source",
                    "search_historical_data_sources"}
    if sum(counts.get(name, 0) for name in source_tools) != len(events["data-source-activity.jsonl"]):
        raise ValueError("data-source research is not completely logged")
    plan_tools = {"inspect_current_data_audit", "inspect_source_canary_evidence",
                  "propose_data_plan",
                  "run_data_plan_feasibility_audit", "compare_data_plans",
                  "submit_data_decision"}
    if sum(counts.get(name, 0) for name in plan_tools) != len(events["data-plan-activity.jsonl"]):
        raise ValueError("data-plan activity is not completely logged")
    successful = {event.get("kind")
                  for name in ("data-source-activity.jsonl", "literature-activity.jsonl",
                               "data-plan-activity.jsonl")
                  for event in events[name]
                  if not str(event.get("kind", "")).endswith("_failed")}
    required = {"current_data_audit_read", "data_source_search_completed",
                "literature_search_completed", "data_plan_proposed",
                "data_plan_audit_completed", "data_plans_compared",
                "data_plan_selected"}
    canary = json.loads((workspace / "source-canary-evidence.json").read_bytes())
    if canary.get("status") != "not_provided":
        required.add("source_canary_read")
    if not required <= successful:
        raise ValueError("data discovery lacks a complete research path")
    selected = [event for event in events["data-plan-activity.jsonl"]
                if event.get("kind") == "data_plan_selected"]
    if len(selected) != 1:
        raise ValueError("exactly one data plan must be selected")
    proposal_id = selected[0].get("proposal_id")
    audited = {event.get("proposal_id") for event in events["data-plan-activity.jsonl"]
               if event.get("kind") == "data_plan_audit_completed"
               and event.get("status") == "canary_required"}
    if proposal_id not in audited:
        raise ValueError("selected data plan lacks a completed feasibility audit")
    return {"valid": True, "logs": summaries, "tool_counts": counts,
            "selected_proposal_id": proposal_id,
            "literature_searches": counts.get("search_public_literature", 0)}
