"""Read-only work-plan status. No stage execution or empirical launch authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research/market_rsi/supervisor_harness"))
import bottleneck_gate as gate

DEFAULT_PLAN = REPO / "configs/earnings_coevolution/plan.json"


def recorded_result(plan_path, step):
    result = step.get("result")
    if result is None:
        return None
    if not isinstance(result, dict) or result.get("verdict") not in {"pass", "fail", "partial", "defer"}:
        raise ValueError(f"{step['id']}: invalid recorded verdict")
    for field in ("observed", "reviewer", "evidence_path"):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ValueError(f"{step['id']}: missing {field}")
    relative = Path(result["evidence_path"])
    if relative.is_absolute():
        raise ValueError(f"{step['id']}: evidence must be plan-relative")
    evidence = (plan_path.parent / relative).resolve(strict=True)
    if not evidence.is_relative_to(plan_path.parent) or not evidence.is_file():
        raise ValueError(f"{step['id']}: evidence outside plan directory or not a file")
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != result.get("evidence_sha256"):
        raise ValueError(f"{step['id']}: evidence hash mismatch")
    return result["verdict"]


def summarize(plan_path=DEFAULT_PLAN):
    plan_path = Path(plan_path).resolve(strict=True)
    gate.check_plan(plan_path, phase="dispatch")
    plan = json.loads(plan_path.read_text())
    results = {step["id"]: recorded_result(plan_path, step) for step in plan["steps"]}
    rows = []
    for step in plan["steps"]:
        blockers = step.get("external_blockers", [])
        if not isinstance(blockers, list) or any(not isinstance(b, str) or not b.strip() for b in blockers):
            raise ValueError(f"{step['id']}: invalid external blockers")
        if results[step["id"]] == "pass" and (blockers or any(results[d] != "pass" for d in step["depends_on"])):
            raise ValueError(f"{step['id']}: recorded pass contradicts unresolved dependencies/gates")
        if verdict := results[step["id"]]:
            status, reason = verdict.upper() + "_RECORDED", "Evidence hash checked; result content still requires review."
        elif blockers:
            status, reason = "GATED", "; ".join(blockers)
        elif pending := [d for d in step["depends_on"] if results[d] != "pass"]:
            status, reason = "WAITING", "Needs passing evidence: " + ", ".join(pending)
        else:
            gate.check_step_ready(plan_path, step_id=step["id"])
            status, reason = "READY", "Ready for the named work, not for an empirical launch."
        rows.append({"id": step["id"], "title": step.get("title", step["id"]),
                     "status": status, "owner": step["owner"], "reason": reason,
                     "expected_artifact": step["expected_artifact"]})
    return {"plan": plan["id"], "plan_file": str(plan_path), "structure_valid": True,
            "steps": rows, "recorded_passes": sum(v == "pass" for v in results.values()),
            "next_ready": [r["id"] for r in rows if r["status"] == "READY"],
            "launch_permission": False, "scientific_quality_verified": False,
            "scope": "Dependencies and recorded evidence integrity only; no execution or learning verdict."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--json", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ready-step")
    mode.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = summarize(args.plan)
        if args.ready_step is not None:
            gate.check_step_ready(args.plan, step_id=args.ready_step)
        if args.resolve:
            gate.check_plan(args.plan, phase="resolve")
            plan = json.loads(args.plan.read_text())
            if plan["resolution"]["reviewer"] == plan["supervisor_owner"]:
                raise ValueError("Whole-plan resolution reviewer must be independent")
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"{result['plan']}  recorded evidence: {result['recorded_passes']}/{len(result['steps'])}")
            for step in result["steps"]:
                print(f"{step['id']:4} {step['status']:16} {step['title']} — {step['reason']}")
            print("Read-only: no stages run, no launch authorization, no inferred learning claim.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"check": "NOT_READY_OR_INVALID", "reason": str(error),
                          "launch_permission": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
