"""Bind reused and role-revalidated score-free receipts to the v3 spec."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.build_spec_v3 import report_map, validate_selection
from memory_policy.semantic_binding import structural_receipt
from memory_policy.semantic_source_preflight import source_hashes, validate_report
from memory_policy.spec_v3 import validate as validate_spec


def promote(selection_path, admission_root, admission_plan, rebind_paths,
            spec_path, output):
    selection_path = Path(selection_path).resolve()
    spec_path = Path(spec_path).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("v3 promotion output is append-only")
    selection = validate_selection(
        selection_path, admission_root, admission_plan, rebind_paths)
    spec = validate_spec(load_json(spec_path))
    if spec["candidate_admission"]["artifact_sha256"] != file_hash(selection_path):
        raise ValueError("v3 selection does not bind to spec")
    old = report_map(admission_root)
    rebound = {}
    rebind_artifacts = []
    for path in rebind_paths:
        path = Path(path).resolve()
        value = load_json(path / "complete.json")
        report = value["reports"][0]
        rebound[report["session"]] = report
        rebind_artifacts.append({"path": path.name,
                                 "sha256": file_hash(path / "complete.json")})
    expected = [{**row, "role": role}
                for role in ("initial_train", "dev", "final")
                for row in spec[role]]
    reports = []
    for row in expected:
        report = rebound.get(row["session"], old.get(row["session"]))
        validate_report(row, report)
        structural_receipt(report)
        reports.append(report)
    output.mkdir()
    fresh_json(output / "claim.json", {
        "schema": "memory_policy_semantic_preflight_promotion_claim_v2",
        "manifest_sha256": file_hash(spec_path),
        "source_reselection_sha256": file_hash(selection_path),
        "selected_sources": len(reports),
        "raw_source_rereads_allowed": 0,
        "provider_calls_allowed": 0,
    })
    value = {
        "schema": "memory_policy_semantic_preflight_promotion_v2",
        "complete": True,
        "manifest_sha256": file_hash(spec_path),
        "selection_sha256": digest(expected),
        "contract_sha256": spec["fixed_contract"]["target_contract_sha256"],
        "source_hashes": source_hashes(),
        "source_reselection_sha256": file_hash(selection_path),
        "source_admission_sha256":
            selection["source_admission_complete_sha256"],
        "role_rebind_artifacts": sorted(
            rebind_artifacts, key=lambda item: item["path"]),
        "reports": reports,
        "raw_rows_exported": 0,
        "target_statistics_computed": 0,
        "fits": 0,
        "provider_calls": 0,
        "raw_source_rereads_for_promotion": 0,
    }
    value["result_sha256"] = digest(value)
    fresh_json(output / "complete.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--admission-plan", type=Path, required=True)
    parser.add_argument("--role-preflight", type=Path, action="append", default=[])
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = promote(args.selection, args.admission, args.admission_plan,
                    args.role_preflight, args.spec, args.output)
    print({"complete": value["complete"], "sources": len(value["reports"]),
           "raw_source_rereads": 0, "provider_calls": 0})
