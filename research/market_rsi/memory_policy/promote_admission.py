"""Bind selected full-pass candidate receipts to the frozen v2 spec."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.build_spec_v2 import validate_admission
from memory_policy.semantic_binding import structural_receipt
from memory_policy.semantic_source_preflight import source_hashes, validate_report
from memory_policy.spec_v2 import validate as validate_spec


def build_value(spec_path, spec, admission_path, admission, reports):
    expected = [{**row, "role": role}
                for role in ("initial_train", "dev", "final")
                for row in spec[role]]
    if (spec["candidate_admission"]["artifact_sha256"] !=
            file_hash(Path(admission_path) / "complete.json")
            or admission["selected_manifest"] != {
                role: spec[role] for role in ("initial_train", "dev", "final")
            }
            or [(row.get("session"), row.get("role")) for row in reports]
                != [(row["session"], row["role"]) for row in expected]):
        raise ValueError("selected admission does not bind to v2 spec")
    for row, report in zip(expected, reports):
        validate_report(row, report)
        structural_receipt(report)
    value = {
        "schema": "memory_policy_semantic_preflight_promotion_v1",
        "complete": True,
        "manifest_sha256": file_hash(spec_path),
        "selection_sha256": digest(expected),
        "contract_sha256": spec["fixed_contract"]["target_contract_sha256"],
        "source_hashes": source_hashes(),
        "candidate_admission_sha256": file_hash(
            Path(admission_path) / "complete.json"),
        "reports": reports,
        "raw_rows_exported": 0,
        "target_statistics_computed": 0,
        "fits": 0,
        "provider_calls": 0,
        "raw_source_rereads_for_promotion": 0,
    }
    value["result_sha256"] = digest(value)
    return value


def promote(admission_path, plan_path, spec_path, output):
    admission_path = Path(admission_path).resolve()
    spec_path = Path(spec_path).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("promotion output is append-only")
    _, admission, _ = validate_admission(admission_path, plan_path)
    spec = validate_spec(load_json(spec_path))
    by_session = {}
    for directory in sorted(path for path in admission_path.iterdir() if path.is_dir()):
        report_path = directory / "report.json"
        if report_path.exists():
            report = load_json(report_path)
            by_session[report["session"]] = report
    reports = [by_session[row["session"]]
               for role in ("initial_train", "dev", "final")
               for row in spec[role]]
    output.mkdir()
    fresh_json(output / "claim.json", {
        "schema": "memory_policy_semantic_preflight_promotion_claim_v1",
        "manifest_sha256": file_hash(spec_path),
        "candidate_admission_sha256": file_hash(admission_path / "complete.json"),
        "selected_sources": len(reports),
        "raw_source_rereads_allowed": 0,
        "provider_calls_allowed": 0,
    })
    value = build_value(spec_path, spec, admission_path, admission, reports)
    fresh_json(output / "complete.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = promote(args.admission, args.plan, args.spec, args.output)
    print({"complete": value["complete"], "sources": len(value["reports"]),
           "raw_source_rereads": 0, "provider_calls": 0})
