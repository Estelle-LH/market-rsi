"""Pre-freeze candidate scan; select only by structural/semantic admission."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.semantic_source_preflight import (
    contract_from, operation, program, source_hashes, validate_report,
)
from memory_policy.source_preflight import source_path
from run_typed_raw_profile import exchange


ROLES = ("initial_train", "dev", "final")


def admission_source_hashes():
    return {**source_hashes(),
            "memory_policy/candidate_source_admission.py": file_hash(Path(__file__))}


def require_unchanged(expected_hashes, plan_path, plan_sha256):
    if admission_source_hashes() != expected_hashes:
        raise ValueError("candidate admission scientific source mutated")
    if file_hash(plan_path) != plan_sha256:
        raise ValueError("candidate admission plan mutated")


def validate_plan(plan):
    if (not isinstance(plan, dict)
            or set(plan) != {"schema", "selection_rule", "groups", "prior_exposure"}
            or plan["schema"] != "memory_policy_candidate_pool_v1"
            or plan["selection_rule"] != "first passing candidates in each ordered group; no target statistics"):
        raise ValueError("exact candidate-pool plan required")
    if not isinstance(plan["prior_exposure"], list):
        raise ValueError("prior exposure list required")
    exposed = set(plan["prior_exposure"])
    if len(exposed) != len(plan["prior_exposure"]):
        raise ValueError("unique prior exposure required")
    groups = plan["groups"]
    if not isinstance(groups, list) or len(groups) < 3:
        raise ValueError("Train, Dev, and Final candidate groups required")
    names = set()
    sessions = set()
    normalized = []
    for group in groups:
        if (not isinstance(group, dict)
                or set(group) != {"name", "role", "required", "candidates"}
                or not isinstance(group["name"], str) or not group["name"]
                or group["name"] in names or group["role"] not in ROLES
                or type(group["required"]) is not int or group["required"] <= 0
                or not isinstance(group["candidates"], list)
                or len(group["candidates"]) < group["required"]):
            raise ValueError("invalid candidate group")
        names.add(group["name"])
        rows = []
        for row in group["candidates"]:
            if (not isinstance(row, dict)
                    or set(row) != {"session", "compressed_bytes"}
                    or not isinstance(row["session"], str)
                    or type(row["compressed_bytes"]) is not int
                    or row["compressed_bytes"] <= 0
                    or row["session"] in sessions
                    or row["session"] in exposed):
                raise ValueError("candidate source is invalid, duplicate, or previously exposed")
            source_path(row["session"])
            sessions.add(row["session"])
            rows.append({**row, "role": group["role"]})
        if [row["session"] for row in rows] != sorted(row["session"] for row in rows):
            raise ValueError("candidate group must be chronological")
        normalized.append({**group, "candidates": rows})
    if ({group["role"] for group in normalized} != set(ROLES)
            or normalized[0]["role"] != "initial_train"
            or normalized[1]["role"] != "dev"
            or any(group["role"] != "final" for group in normalized[2:])):
        raise ValueError("candidate groups must be Train, Dev, then Final strata")
    if (max(row["session"] for row in normalized[0]["candidates"])
            >= min(row["session"] for row in normalized[1]["candidates"])
            or max(row["session"] for row in normalized[1]["candidates"])
            >= min(row["session"] for group in normalized[2:]
                   for row in group["candidates"])):
        raise ValueError("candidate role windows must be strictly chronological")
    return normalized


def select(groups, results):
    selected = {role: [] for role in ROLES}
    rejected = []
    for group in groups:
        passing = []
        for row in group["candidates"]:
            report = results[row["session"]]
            if report.get("complete") is True:
                validate_report(row, report)
                passing.append(row)
            else:
                rejected.append({
                    "session": row["session"], "role": row["role"],
                    "group": group["name"],
                    "failure": report.get("consumer_failure") or report.get("failure"),
                })
        if len(passing) < group["required"]:
            raise ValueError("candidate group has too few admitted sources")
        selected[group["role"]].extend(
            {"session": row["session"], "compressed_bytes": row["compressed_bytes"]}
            for row in passing[:group["required"]])
    if (not selected["initial_train"] or len(selected["dev"]) != 8
            or len(selected["final"]) < 20
            or max(row["session"] for row in selected["initial_train"])
                >= min(row["session"] for row in selected["dev"])
            or max(row["session"] for row in selected["dev"])
                >= min(row["session"] for row in selected["final"])):
        raise ValueError("selected manifest does not meet experiment split")
    return selected, rejected


def run(plan_path, contract_path, output):
    plan_path = Path(plan_path).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("candidate admission output is append-only")
    plan = load_json(plan_path)
    groups = validate_plan(plan)
    contract = contract_from(contract_path)
    plan_sha256 = file_hash(plan_path)
    frozen_source_hashes = admission_source_hashes()
    output.mkdir(parents=True)
    ordered = [row for group in groups for row in group["candidates"]]
    fresh_json(output / "claim.json", {
        "schema": "memory_policy_candidate_admission_claim_v1",
        "plan_sha256": plan_sha256,
        "candidate_order_sha256": digest(ordered),
        "contract_sha256": digest(contract),
        "source_hashes": frozen_source_hashes,
        "selection_rule": plan["selection_rule"],
        "target_statistics_allowed": 0,
        "provider_calls_allowed": 0,
    })
    results = {}
    try:
        for index, row in enumerate(ordered):
            require_unchanged(frozen_source_hashes, plan_path, plan_sha256)
            directory = output / f"{index:03d}-{row['role']}-{row['session']}"
            directory.mkdir()
            spec = operation(row, contract)
            body = program(spec)
            fresh_json(directory / "dispatch.json", {
                "spec_sha256": digest(spec),
                "program_sha256": hashlib.sha256(body).hexdigest(),
                "session": row["session"], "role": row["role"],
            })
            report = exchange(body, directory)
            fresh_json(directory / "report.json", report)
            results[row["session"]] = report
            print({"stage": "candidate_complete", "index": index + 1,
                   "total": len(ordered), "session": row["session"],
                   "admitted": report.get("complete") is True}, flush=True)
        require_unchanged(frozen_source_hashes, plan_path, plan_sha256)
        selected, rejected = select(groups, results)
        result = {
            "schema": "memory_policy_candidate_admission_v1",
            "complete": True,
            "plan_sha256": plan_sha256,
            "contract_sha256": digest(contract),
            "source_hashes": frozen_source_hashes,
            "selected_manifest": selected,
            "rejected": rejected,
            "all_receipts": [{
                "session": row["session"], "role": row["role"],
                "complete": results[row["session"]].get("complete") is True,
                "transport": results[row["session"]].get("transport"),
                "semantic_receipt": results[row["session"]].get("semantic_receipt"),
                "failure": (results[row["session"]].get("consumer_failure")
                            or results[row["session"]].get("failure")),
            } for row in ordered],
            "raw_rows_exported": 0,
            "target_statistics_computed": 0,
            "fits": 0,
            "provider_calls": 0,
        }
        result["result_sha256"] = digest(result)
        fresh_json(output / "complete.json", result)
        fresh_json(output / "selected-manifest.json", selected)
        return result
    except BaseException as error:
        fresh_json(output / "failure.json", {
            "type": type(error).__name__,
            "reason": (
                "scientific_source_mutation"
                if str(error) == "candidate admission scientific source mutated"
                else "plan_mutation"
                if str(error) == "candidate admission plan mutated"
                else "candidate_admission_failure"
            ),
            "attempted_sources": len(results),
            "paid_work_started": False,
            "target_statistics_computed": 0,
            "no_automatic_retry": True,
        })
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.plan, args.contract, args.output)
    print({"complete": value["complete"],
           "selected": {key: len(rows) for key, rows in value["selected_manifest"].items()},
           "rejected": len(value["rejected"]), "provider_calls": 0})
