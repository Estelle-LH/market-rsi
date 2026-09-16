"""Audit the complete append-only path to one frozen objective decision."""
from __future__ import annotations

from pathlib import Path

from controller_activity_log import read_activity_events, verify_activity_log


def assess_objective_activity(workspace: Path) -> dict:
    workspace = Path(workspace)
    names = (
        "controller-tool-journal.jsonl",
        "controller-egress-audit.jsonl",
        "literature-activity.jsonl",
        "objective-activity.jsonl",
    )
    summaries = {name: verify_activity_log(workspace / name) for name in names}
    events = {name: read_activity_events(workspace / name) for name in names}
    tool_events = events["controller-tool-journal.jsonl"]
    objective_events = events["objective-activity.jsonl"]
    literature_events = events["literature-activity.jsonl"]
    egress_events = events["controller-egress-audit.jsonl"]
    counts = {}
    for event in tool_events:
        tool = event.get("tool")
        counts[tool] = counts.get(tool, 0) + 1
    if counts.get("search_public_literature", 0) != len(literature_events):
        raise ValueError("objective literature actions are not completely logged")
    successful_tool_calls = sum(event.get("status") == "ok" for event in tool_events)
    if (len(egress_events) != successful_tool_calls
            or any(event.get("raw_rows_released") is not False
                   or event.get("market_identity_released") is not False
                   or event.get("timestamps_released") is not False
                   or event.get("local_paths_released") is not False
                   for event in egress_events)):
        raise ValueError("objective controller egress is incomplete or unsafe")
    objective_tools = {
        "inspect_open_train_source_inventory", "run_automatic_time_series_data_diagnostics",
        "profile_open_train_cadence", "profile_open_train_target",
        "list_objective_families", "propose_objective_definition",
        "run_open_train_objective_audit", "compare_open_train_objective_stability",
        "submit_objective_decision",
    }
    if sum(counts.get(name, 0) for name in objective_tools) != len(objective_events):
        raise ValueError("objective actions are not completely logged")
    successful = {event.get("kind") for event in objective_events
                  if not str(event.get("kind", "")).endswith("_failed")}
    required = {
        "automatic_diagnostics_read",
        "objective_proposed",
        "objective_audit_completed",
        "objective_selected",
    }
    if not required <= successful:
        raise ValueError("objective activity lacks a complete discovery path")
    selected = [event for event in objective_events
                if event.get("kind") == "objective_selected"]
    if len(selected) != 1:
        raise ValueError("exactly one objective must be selected")
    proposal_id = selected[0].get("proposal_id")
    audited = {event.get("proposal_id") for event in objective_events
               if event.get("kind") == "objective_audit_completed"
               and event.get("status") == "completed"}
    if proposal_id not in audited:
        raise ValueError("selected objective lacks a completed Train-only audit")
    return {
        "valid": True,
        "logs": summaries,
        "tool_counts": counts,
        "selected_proposal_id": proposal_id,
        "selected_objective_id": selected[0].get("objective_id"),
        "literature_searches": counts.get("search_public_literature", 0),
    }
