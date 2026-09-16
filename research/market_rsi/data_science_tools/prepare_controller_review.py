"""Feed reviewed data-science evidence into the EXISTING Codex/GLM v2 broker.

No frozen broker/dispatcher is modified. A new immutable workspace carries the
current checklist, failures and old source decision; legacy terminal/claims and
budget gates still apply. Preparation and the STDIO check are entirely unpaid.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "source_review_tools")]
from data_science_tools import pipeline as p
from market_rsi import digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget
import controller_source_review_v2 as review
import run_source_review_v2 as dispatcher


def resident(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("required regular existing file missing")
    if getattr(path.stat(), "st_flags", 0) & getattr(stat, "SF_DATALESS", 0x40000000):
        raise ValueError("required file is dataless: " + str(path))


def prepare(output, feedback_root, purpose):
    output, feedback_root = Path(output).resolve(), Path(feedback_root).resolve()
    if output.exists() or purpose not in ("source_review", "transport_canary"):
        raise ValueError("fresh, explicitly scoped preparation required")
    old = ROOT / "artifacts/historical-source-review-v2-controller-20260910-01"
    for path in (old / "preparation.json", feedback_root / "bindings.json"):
        resident(path)
    old_prep = load_json(old / "preparation.json")
    paths = [Path(k) for k in old_prep["inputs"]]
    paths += [ROOT / k for k in old_prep["source_hashes"]]
    paths += [old / "source-snapshot" / k for k in old_prep["source_hashes"]]
    for path in paths:
        resident(path)
    verified, _, visible = dispatcher.verify_preparation(old)
    if load_json(old / "session/assessment.json").get("valid") is not True or not (old / "dispatch-claim.json").is_file():
        raise ValueError("completed prior controller decision required")
    paths = [feedback_root / n for n in ("spec.json", "reviewed-checks.json", "readiness.json", "controller-feedback.json", "bindings.json")]
    for path in paths:
        resident(path)
    report = p.verify_review_files(paths[0], file_hash(paths[0]), paths[1], file_hash(paths[1]))
    if report != load_json(paths[2]):
        raise ValueError("current readiness differs from independently bound checks")
    feedback = load_json(paths[3])
    if (feedback.get("feedback_sha256") != p.digest({k: v for k, v in feedback.items() if k != "feedback_sha256"})
            or feedback.get("readiness") != report or feedback.get("formal_experiment_allowed") is not False):
        raise ValueError("exact non-admitting data-science feedback required")
    bindings = load_json(paths[4])
    for name, sha in bindings["inputs"].items():
        resident(name)
        if file_hash(name) != sha:
            raise ValueError("underlying QA evidence changed")
    for name, sha in bindings["source_sha256"].items():
        if file_hash(Path(__file__).with_name(name)) != sha:
            raise ValueError("data-science reviewer source changed")
    budget_path = ROOT / "artifacts/kalshi-research-glm53-20260907-01/budget"
    budget = PaidBudget(budget_path).snapshot()
    if any(v["state"] == "dispatched" and "-turn-" in k for k, v in budget["jobs"].items()):
        raise ValueError("another model turn exists")
    context = visible["context.json"]
    if budget["experiment_id"] != context["experiment_id"] or budget["cap_usd"] != context["budget_cap_usd"]:
        raise ValueError("original experiment budget changed")
    visible = copy.deepcopy(visible)
    old_decision = load_json(old / "workspace" / review.DECISION)
    visible["archive.json"]["previous_data_source_decision"] = old_decision
    visible["archive.json"]["previous_data_source_plans"] = [load_json(path) for path in sorted((old / "workspace/plans").glob("*/result.json"))]
    visible["archive.json"]["superseded_source_readiness_before_acquisition"] = visible["readiness.json"]
    visible["archive.json"]["data_science_lessons"] = feedback["earlier_source_lessons"]
    visible["evidence.json"]["data_science_review"] = feedback
    visible["readiness.json"] = {
        "source_review_interface_version": 2, "data_science_pipeline_version": 1,
        "data_science_feedback_sha256": feedback["feedback_sha256"],
        "data_science_required_stages": [{"stage": s[0], "title": s[1], "checks": list(s[3])} for s in p.STAGES],
        "data_science_readiness": report,
        "current_assignment": feedback["instruction"],
        "budget_snapshot_not_spend": {k: v for k, v in budget.items() if k != "jobs"},
        "component_raw_download_authority_bytes": 0,
        "project_transfer_accounting": {k: feedback[k] for k in (
            "raw_download_bytes_recorded", "backup_upload_bytes_recorded",
            "legacy_combined_transfer_guard_remaining_bytes", "download_only_arithmetic_headroom_bytes")},
        "authority_note": "This broker cannot download. Its zero allowance is tool scope, not a provider balance. Project download and backup counters are separate; no new authority is granted here.",
        "first_valid_controller_decision_required": True,
        "formal_experiment_allowed": False,
    }
    # Freeze all preexisting sources plus this additive integration. No edits to
    # the old source snapshot, controller response, selected model or objective.
    sources = set(ROOT / name for name in verified["source_hashes"])
    sources.update(x for x in Path(__file__).parent.glob("*.py") if not x.name.startswith("test_"))
    sources.update(ROOT / "audit_tools" / name for name in ("vantage_coverage_conclusion.py", "vantage_metadata_audit.py"))
    for path in sources:
        resident(path)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    hashes = {}
    for path in sorted(sources):
        name = str(path.relative_to(ROOT))
        hashes[name] = file_hash(path)
        destination = output / "source-snapshot" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        if file_hash(destination) != hashes[name]:
            raise ValueError("snapshot bytes changed")
    sha = review.core.make_workspace(output / "workspace", visible, output.name, purpose)
    review.validate_workspace(output / "workspace", sha)
    inputs = {**verified["inputs"], **bindings["inputs"], **{str(path): file_hash(path) for path in paths}}
    inputs[str(old / "workspace" / review.DECISION)] = file_hash(old / "workspace" / review.DECISION)
    inputs[str(old / "session/assessment.json")] = file_hash(old / "session/assessment.json")
    result = {"schema": "historical_source_review_v2_preparation_v1", "purpose": purpose,
              "source_review_interface_version": 2, "data_science_pipeline_version": 1,
              "source_hashes": hashes, "workspace_sha256": sha, "context_sha256": context["context_sha256"],
              "followup_sha256": verified["followup_sha256"], "inputs": inputs,
              "data_science_feedback_sha256": feedback["feedback_sha256"],
              "data_science_review_root": str(feedback_root),
              "new_model_calls": 0, "new_raw_download_bytes": 0, "execution_admitted": False,
              "paid_dispatch_ready": False}
    fresh_json(output / "preparation.json", result)
    dispatcher.verify_preparation(output)
    return result


def canary(prepared):
    """Real existing broker process; verify full failed review reaches tools."""
    prepared = Path(prepared).resolve()
    prep, manifest, _ = dispatcher.verify_preparation(prepared)
    if manifest["purpose"] != "transport_canary" or prep.get("data_science_pipeline_version") != 1:
        raise ValueError("fresh data-science transport fixture required")
    fresh_json(prepared / "data-science-canary-claim.json", {"preparation_sha256": file_hash(prepared / "preparation.json"),
               "scope": "real existing broker STDIO, no paid model or data execution"})
    requests = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": {}}}
                for i, name in enumerate(("inspect_source_context", "inspect_source_readiness", "inspect_source_archive"), 1)]
    proc = subprocess.run([sys.executable, str(prepared / "source-snapshot/source_review_tools/controller_source_review_v2.py"),
                           "--workspace", str(prepared / "workspace"), "--manifest-sha256", prep["workspace_sha256"]],
                          input="".join(json.dumps(r) + "\n" for r in requests), capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise ValueError("broker STDIO failed: " + proc.stderr[-1000:])
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    if len(replies) != 3 or any(r.get("error") or r["result"].get("isError") for r in replies):
        raise ValueError("data-science inspection tool failed")
    values = [json.loads(r["result"]["content"][0]["text"]) for r in replies]
    actual = values[1]["evidence"]["data_science_review"]
    readiness = values[1]["readiness"]
    if (actual["feedback_sha256"] != prep["data_science_feedback_sha256"]
            or len(readiness["data_science_required_stages"]) != 8
            or actual["data_science_complete"] is not False
            or values[2]["data_science_lessons"] != actual["earlier_source_lessons"]):
        raise ValueError("current review or lessons not delivered")
    result = {"schema": "data_science_existing_broker_stdio_canary_v1", "passed": True,
              "actual_stdio_child": True, "tools_executed": 3, "stages_delivered": 8,
              "checks_delivered": len(p.CHECK_STAGE), "feedback_sha256": actual["feedback_sha256"],
              "model_calls": 0, "formal_experiment_allowed": False,
              "paid_dispatch_ready": False, "no_decision_submitted": not (prepared / "workspace" / review.DECISION).exists()}
    result["result_sha256"] = digest(result)
    fresh_json(prepared / "data-science-canary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--feedback-root", type=Path, required=True)
    a.add_argument("--purpose", choices=["source_review", "transport_canary"], required=True)
    a = sub.add_parser("canary")
    a.add_argument("--prepared", type=Path, required=True)
    args = parser.parse_args()
    result = (prepare(args.output, args.feedback_root, args.purpose) if args.operation == "prepare"
              else canary(args.prepared))
    print(json.dumps({k: v for k, v in result.items() if k not in ("source_hashes", "inputs")}, sort_keys=True))
