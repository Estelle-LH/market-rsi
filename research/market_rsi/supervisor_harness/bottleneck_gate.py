"""Fail-closed checks for supervisor bottleneck delegation and resolution.

This checks an outer-supervisor plan, not a controller scientific decision.
It never grants permission to open protected data or start a paid experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED_STEP = ("id", "owner", "action", "depends_on", "expected_artifact",
                 "verification", "pass_condition", "failure_action", "time_bound_minutes")


def _require_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {label}")


def check_plan(plan_path: Path, *, phase: str) -> dict:
    """Validate a plan before delegation or before declaring resolution.

    Evidence paths must stay inside the plan directory. A supervisor must still
    inspect the contents independently; this gate proves presence/integrity.
    """
    if phase not in {"dispatch", "resolve"}:
        raise ValueError("phase must be dispatch or resolve")
    plan_path = plan_path.resolve(strict=True)
    plan = json.loads(plan_path.read_text())
    if plan.get("schema") != "supervisor_bottleneck_plan_v1":
        raise ValueError("unsupported bottleneck plan schema")
    for field in ("id", "symptom", "source_evidence", "objective", "boundary",
                  "resolution_check", "supervisor_owner"):
        _require_text(plan.get(field), field)
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("plan needs at least one bounded step")
    ids = [step.get("id") for step in steps if isinstance(step, dict)]
    if len(ids) != len(steps) or len(set(ids)) != len(ids):
        raise ValueError("step IDs must be unique")
    for step in steps:
        for field in REQUIRED_STEP:
            if field == "depends_on":
                if not isinstance(step.get(field), list):
                    raise ValueError(f"{step['id']}: depends_on must be a list")
            elif field == "time_bound_minutes":
                if not isinstance(step.get(field), (int, float)) or step[field] <= 0:
                    raise ValueError(f"{step['id']}: positive time bound required")
            else:
                _require_text(step.get(field), f"{step['id']}.{field}")
        if any(dep not in ids or dep == step["id"] for dep in step["depends_on"]):
            raise ValueError(f"{step['id']}: invalid dependency")
    visited: set[str] = set()
    visiting: set[str] = set()
    by_id = {step["id"]: step for step in steps}

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("cyclic step dependencies")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dep in by_id[step_id]["depends_on"]:
            visit(dep)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in ids:
        visit(step_id)
    if phase == "resolve":
        for step in steps:
            result = step.get("result")
            if not isinstance(result, dict) or result.get("verdict") != "pass":
                raise ValueError(f"{step['id']}: no passing verification result")
            _require_text(result.get("observed"), f"{step['id']}.result.observed")
            _require_text(result.get("reviewer"), f"{step['id']}.result.reviewer")
            relative = result.get("evidence_path")
            _require_text(relative, f"{step['id']}.result.evidence_path")
            evidence = (plan_path.parent / relative).resolve(strict=True)
            if not evidence.is_relative_to(plan_path.parent):
                raise ValueError(f"{step['id']}: evidence outside plan directory")
            actual = hashlib.sha256(evidence.read_bytes()).hexdigest()
            if actual != result.get("evidence_sha256"):
                raise ValueError(f"{step['id']}: evidence hash mismatch")
        resolution = plan.get("resolution")
        if not isinstance(resolution, dict) or resolution.get("verdict") != "pass":
            raise ValueError("independent whole-bottleneck resolution check required")
        _require_text(resolution.get("observed"), "resolution.observed")
        _require_text(resolution.get("reviewer"), "resolution.reviewer")
    return {"id": plan["id"], "phase": phase, "steps": len(steps), "passed": True}


def check_state(state_path: Path, *, repo_root: Path) -> dict:
    """Reject invisible/unowned active blockers or missing orchestration files."""
    state = json.loads(state_path.read_text())
    if state.get("schema") != "market_supervisor_bottleneck_state_v1":
        raise ValueError("unsupported bottleneck state schema")
    active = state.get("active")
    if not isinstance(active, list):
        raise ValueError("active bottlenecks must be a list")
    ids: set[str] = set()
    root = repo_root.resolve()
    for item in active:
        if not isinstance(item, dict):
            raise ValueError("invalid active bottleneck")
        for field in ("id", "status", "plan", "result", "next", "evidence"):
            _require_text(item.get(field), f"bottleneck.{field}")
        if item["id"] in ids:
            raise ValueError("duplicate active bottleneck")
        ids.add(item["id"])
        if item["status"] == "resolved":
            raise ValueError("resolved bottleneck cannot remain active")
        for field in ("plan", "evidence"):
            candidate = (root / item[field]).resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file():
                raise ValueError(f"{item['id']}: missing or outside {field}")
    return {"active": len(active), "passed": True}


def check_step_ready(plan_path: Path, *, step_id: str) -> dict:
    """Require passing, intact dependency receipts before one task dispatch."""
    check_plan(plan_path, phase="dispatch")
    plan_path = plan_path.resolve(strict=True)
    steps = {step["id"]: step for step in json.loads(plan_path.read_text())["steps"]}
    if step_id not in steps:
        raise ValueError("unknown step ID")
    step = steps[step_id]
    if step.get("result") is not None:
        raise ValueError(f"{step_id}: already has a result; version plan before retry")
    blockers = step.get("external_blockers", [])
    if not isinstance(blockers, list) or any(not isinstance(x, str) for x in blockers):
        raise ValueError(f"{step_id}: invalid external blockers")
    if blockers:
        raise ValueError(f"{step_id}: external gate blocked: {', '.join(blockers)}")
    for dep_id in step["depends_on"]:
        result = steps[dep_id].get("result")
        if not isinstance(result, dict) or result.get("verdict") != "pass":
            raise ValueError(f"{step_id}: dependency {dep_id} not passed")
        _require_text(result.get("observed"), f"{dep_id}.result.observed")
        _require_text(result.get("reviewer"), f"{dep_id}.result.reviewer")
        _require_text(result.get("evidence_path"), f"{dep_id}.evidence_path")
        evidence = (plan_path.parent / result["evidence_path"]).resolve(strict=True)
        if not evidence.is_relative_to(plan_path.parent):
            raise ValueError(f"{dep_id}: evidence outside plan directory")
        if hashlib.sha256(evidence.read_bytes()).hexdigest() != result.get("evidence_sha256"):
            raise ValueError(f"{dep_id}: evidence hash mismatch")
    return {"plan": json.loads(plan_path.read_text())["id"],
            "step": step_id, "ready": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, nargs="?")
    parser.add_argument("--phase", choices=("dispatch", "resolve"))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--ready-step")
    args = parser.parse_args()
    if args.state is not None:
        if (args.plan is not None or args.phase is not None or args.repo_root is None
                or args.ready_step is not None):
            parser.error("--state requires --repo-root and no plan/phase")
        result = check_state(args.state, repo_root=args.repo_root)
    else:
        if args.plan is None or args.repo_root is not None:
            parser.error("plan required without --state")
        if args.ready_step is not None and args.phase is None:
            result = check_step_ready(args.plan, step_id=args.ready_step)
        elif args.phase is not None and args.ready_step is None:
            result = check_plan(args.plan, phase=args.phase)
        else:
            parser.error("choose exactly one of --phase or --ready-step")
    print(json.dumps(result, sort_keys=True))
