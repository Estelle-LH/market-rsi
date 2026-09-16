"""Full source semantic gate before any paid controller or score access."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_pilot.run_materialize import modules as materialize_modules
from memory_policy.source_preflight import selected_sources, source_path
from run_typed_raw_profile import exchange


RESOURCE_POLICY = {
    "parent_address_space_bytes": 4 * 1024**3,
    "decoder_address_space_bytes": 256 * 1024**2,
    "max_decoded_bytes": 4 * 1024**3,
    "max_entities": 10000,
    "max_total_observations": 12000000,
    "max_entity_observations": 200000,
    "remote_wall_seconds": 570,
}
WORKER = "memory_policy/semantic_preflight_worker.py"


def modules():
    return materialize_modules()


def source_hashes():
    paths = {path for _, path in modules()} | {
        "audit_tools/run_typed_raw_profile.py",
        WORKER,
        "memory_policy/semantic_source_preflight.py",
        "memory_policy/source_preflight.py",
    }
    return {path: file_hash(ROOT / path) for path in sorted(paths)}


def midnight_ms(session):
    parsed = datetime.strptime(session, "%Y-%m-%dT%H")
    return int(parsed.replace(hour=0, tzinfo=timezone.utc).timestamp() * 1000)


def contract_from(path):
    value = load_json(path)
    if isinstance(value.get("spec"), dict) and isinstance(value["spec"].get("contract"), dict):
        value = value["spec"]["contract"]
    if not isinstance(value, dict):
        raise ValueError("contract object required")
    return value


def operation(row, contract):
    return {
        "session": row["session"],
        "role": row["role"],
        "path": source_path(row["session"]),
        "compressed_bytes": row["compressed_bytes"],
        "day_start_ms": midnight_ms(row["session"]),
        "contract": contract,
        "resource_policy": RESOURCE_POLICY,
    }


def program(spec):
    code = "import types,sys\n"
    for name in ("quote_source", "data_scientist_harness"):
        code += "m=types.ModuleType(" + repr(name) + ");m.__path__=[];sys.modules[m.__name__]=m\n"
    for name, path in modules():
        code += "m=types.ModuleType(" + repr(name) + ");m.__file__=" + repr(path)
        code += ";sys.modules[m.__name__]=m\n"
        code += "exec(" + repr((ROOT / path).read_text()) + ",m.__dict__)\n"
    code += "SPEC=" + repr(spec) + "\n"
    code += (ROOT / WORKER).read_text()
    return code.encode()


def validate_report(row, report):
    transport = report.get("transport") or {}
    semantic = report.get("semantic_receipt") or {}
    if (report.get("complete") is not True
            or report.get("session") != row["session"]
            or report.get("role") != row["role"]
            or report.get("advertised_bytes") != row["compressed_bytes"]
            or transport.get("complete") is not True
            or transport.get("compressed_bytes_read") != row["compressed_bytes"]
            or transport.get("decoded_records", 0) <= 0
            or semantic.get("selected_observations", 0) <= 0
            or semantic.get("entities", 0) <= 0
            or semantic.get("last_attempted_record") != transport.get("decoded_records")
            or semantic.get("message_selection_kernel") != "CacheProfile.consume"
            or semantic.get("summary_or_cache_called") is not False
            or any(report.get(key) != 0 for key in (
                "raw_rows_exported", "target_statistics_computed", "fits", "provider_calls"))):
        raise ValueError("source receipt does not satisfy semantic gate")
    return True


def run_rows(rows, contract, output, *, manifest_sha256=None):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("semantic preflight output is append-only; use a fresh ID")
    output.mkdir(parents=True)
    fresh_json(output / "claim.json", {
        "schema": "memory_policy_semantic_preflight_claim_v1",
        "manifest_sha256": manifest_sha256,
        "selection_sha256": digest(rows),
        "contract_sha256": digest(contract),
        "source_hashes": source_hashes(),
        "selected_sources": len(rows),
        "paid_work_started": False,
        "target_statistics_allowed": 0,
    })
    reports = []
    try:
        for index, row in enumerate(rows):
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
            reports.append(report)
            validate_report(row, report)
        result = {
            "schema": "memory_policy_semantic_preflight_v1",
            "complete": True,
            "manifest_sha256": manifest_sha256,
            "selection_sha256": digest(rows),
            "contract_sha256": digest(contract),
            "source_hashes": source_hashes(),
            "reports": [{
                "session": report["session"],
                "role": report["role"],
                "complete": report["complete"],
                "advertised_bytes": report["advertised_bytes"],
                "transport": report["transport"],
                "semantic_receipt": report["semantic_receipt"],
                "raw_rows_exported": report["raw_rows_exported"],
                "target_statistics_computed": report["target_statistics_computed"],
                "fits": report["fits"],
                "provider_calls": report["provider_calls"],
            } for report in reports],
            "raw_rows_exported": 0,
            "target_statistics_computed": 0,
            "fits": 0,
            "provider_calls": 0,
        }
        result["result_sha256"] = digest(result)
        fresh_json(output / "complete.json", result)
        return result
    except BaseException as error:
        fresh_json(output / "failure.json", {
            "type": type(error).__name__,
            "completed_sources": sum(report.get("complete") is True for report in reports),
            "attempted_sources": len(reports),
            "paid_work_started": False,
            "target_statistics_computed": 0,
            "no_automatic_replacement": True,
        })
        raise


def run(manifest_path, contract_path, output):
    manifest_path = Path(manifest_path).resolve()
    rows = selected_sources(load_json(manifest_path))
    return run_rows(rows, contract_from(contract_path), output,
                    manifest_sha256=file_hash(manifest_path))


def run_one(session, role, compressed_bytes, contract_path, output):
    row = {"session": session, "role": role, "compressed_bytes": compressed_bytes}
    source_path(session)
    return run_rows([row], contract_from(contract_path), output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--session")
    parser.add_argument("--role")
    parser.add_argument("--compressed-bytes", type=int)
    args = parser.parse_args()
    if args.manifest:
        result = run(args.manifest, args.contract, args.output)
    elif args.session and args.role and args.compressed_bytes:
        result = run_one(args.session, args.role, args.compressed_bytes,
                         args.contract, args.output)
    else:
        parser.error("use --manifest or all single-source arguments")
    print({"complete": result["complete"], "sources": len(result["reports"]),
           "provider_calls": result["provider_calls"]})
