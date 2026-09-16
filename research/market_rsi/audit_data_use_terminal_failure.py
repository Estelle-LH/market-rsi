"""Preserve a first data-use proposal after the missing-bytes terminal bug.

This does not change the original failed assessment, fabricate an acknowledgment,
call a model, or admit training. It audits whether the existing proposal may be
used for the next LOCAL materializer canary despite that specific interface bug.
"""
import argparse
from decimal import Decimal
from pathlib import Path

from codex_glm_provider import _output_text
from controller_activity_log import read_activity_events
from historical_data_use_controller import assess_activity
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget
import json


def check_failure(assessment, events, decision, request, trailing_assessment):
    required = {"valid": False, "failed": False, "exit_code": 0,
                "controller_stage": "data_use", "codex_harness_runtime_unchanged": True,
                "submitted_decision_present": True, "required_tools_complete": True,
                "terminal_handshake": None, "unresolved_accounting": []}
    if any(assessment.get(k) != v for k, v in required.items()):
        raise ValueError("not the isolated missing-bytes terminal failure")
    submissions = [e for e in events if e.get("tool") == "submit_data_use_decision"
                   and e.get("status") == "ok"]
    if len(submissions) != 1 or submissions[0] is not events[-1]:
        raise ValueError("exactly one submission and no subsequent tool activity required")
    if submissions[0]["arguments"] != decision or decision.get("action") != "select":
        raise ValueError("first selected decision changed")
    result = submissions[0]["result"]
    if result.get("submitted") is not True or "bytes" in result:
        raise ValueError("missing submission byte count not reproduced")
    if (trailing_assessment.get("valid") is not True
            or trailing_assessment.get("kind") != "message"
            or trailing_assessment.get("tool_names") != []):
        raise ValueError("extra paid turn must contain only terminal text, no tools")
    calls = [x for x in request["input"] if x.get("type") == "function_call"]
    selected = [x for x in calls if x.get("name") == "submit_data_use_decision"]
    if len(selected) != 1 or calls[-1] != selected[0] or json.loads(selected[0]["arguments"]) != decision:
        raise ValueError("provider request must retain the exact last submitted decision")
    outputs = [x for x in request["input"] if x.get("type") == "function_call_output"
               and x.get("call_id") == selected[0]["call_id"]]
    if len(outputs) != 1 or canonical(result) not in _output_text(outputs[0]["output"]):
        raise ValueError("provider submission receipt differs from broker activity")
    return {"cause": "data_use_submit_receipt_missing_bytes",
            "first_valid_proposal_preserved": True, "original_session_valid": False,
            "terminal_handshake_repaired_retroactively": False,
            "eligible_for_local_materializer_canary": True,
            "training_admitted": False, "new_paid_calls": 0}


def audit(run, output, budget):
    identifier(output.name)
    activity = assess_activity(run / "workspace")
    if activity["valid"] is not True:raise ValueError("original activity is not intact")
    assessment = load_json(run / "session/assessment.json")
    paths = sorted((run / "session").glob("turn-*/assessment.json"))
    if len(paths) != assessment["turns"] or len(paths) < 2:
        raise ValueError("every paid turn must have a terminal assessment")
    tool = "mcp__controller_tools__submit_data_use_decision"
    submissions = [p for p in paths if tool in load_json(p).get("tool_names", [])]
    if submissions != [paths[-2]]:
        raise ValueError("requires exactly one submitted decision and one extra summary turn")
    decision = load_json(run / "workspace/submitted-data-use-decision.json")
    events = read_activity_events(run / "workspace/data-use-activity.jsonl")
    request = load_json(paths[-1].parent / "request.json")["responses_request"]
    result = check_failure(assessment, events, decision, request, load_json(paths[-1]))
    proposal = load_json(run / "workspace/frozen-data-use-proposal.json")
    if proposal.get("training_admitted") is not False or proposal.get("materializer_execution_verified") is not False:
        raise ValueError("proposal must remain unexecuted and diagnostic")
    state = PaidBudget(budget).snapshot()
    jobs = {k: j for k, j in state["jobs"].items() if k.startswith(run.name + "-turn-")}
    if len(jobs) != len(paths) or any(j["state"] != "metered_terminal" for j in jobs.values()):
        raise ValueError("all original model charges must be metered terminal")
    root = Path(__file__).parent
    prep = load_json(run / "preparation.json")
    changes = {n: {"old": h, "new": file_hash(root / n)}
               for n, h in prep["source_hashes"].items() if file_hash(root / n) != h}
    if set(changes) != {"historical_data_use_controller.py"}:
        raise ValueError("unexpected frozen source changes since isolated receipt repair")
    files = [run / "preparation.json", run / "session/assessment.json",
             run / "workspace/submitted-data-use-decision.json",
             run / "workspace/frozen-data-use-proposal.json", run / "workspace/data-use-activity.jsonl",
             *[p for parent in [p.parent for p in paths] for p in parent.glob("*.json")]]
    evidence = {str(p.relative_to(run)): file_hash(p) for p in files}
    result.update(schema="data_use_terminal_failure_audit_v1", original_run=run.name,
                  activity=activity, source_changes=changes, original_artifact_sha256=evidence,
                  proposal_sha256=proposal["proposal_sha256"],
                  session_metered_usd=str(sum(Decimal(j["metered_usd"]) for j in jobs.values())),
                  unnecessary_summary_metered_usd=jobs[run.name + "-" + paths[-1].parent.name]["metered_usd"],
                  budget_after={k: v for k, v in state.items() if k != "jobs"})
    result["audit_sha256"] = digest(result)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    fresh_json(output / "audit.json", result)
    if any(file_hash(run / p) != h for p, h in evidence.items()):
        raise ValueError("original artifact changed during read-only audit")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "output", "budget"):p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args();result = audit(a.run, a.output, a.budget)
    print(canonical({k: result[k] for k in ["schema", "original_run", "proposal_sha256",
        "original_session_valid", "eligible_for_local_materializer_canary", "session_metered_usd", "audit_sha256"]}))
