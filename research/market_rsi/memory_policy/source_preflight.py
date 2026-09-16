"""Runner-owned all-source integrity gate before controller or model work."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from market_rsi import digest, file_hash, fresh_json, load_json
from run_typed_raw_profile import exchange


ROLE_ORDER = ("initial_train", "dev", "final")
MODULES = (
    ("single_object_stream", "audit_tools/single_object_stream.py"),
    ("sealed_jsonl_integrity", "audit_tools/sealed_jsonl_integrity.py"),
)
WORKER = "audit_tools/source_integrity_worker.py"


def source_path(session):
    parsed = datetime.strptime(session, "%Y-%m-%dT%H")
    if parsed.strftime("%Y-%m-%dT%H") != session:
        raise ValueError("canonical hourly session required")
    return "/opt/d10/raw/data/polymarket/polymarket-" + session.replace("-", "") + ".jsonl.zst"


def selected_sources(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("source manifest must be an object")
    rows = []
    seen = set()
    for role in ROLE_ORDER:
        values = manifest.get(role)
        if not isinstance(values, list) or not values:
            raise ValueError("each source role must be nonempty")
        for row in values:
            if (not isinstance(row, dict) or set(row) != {"session", "compressed_bytes"}
                    or not isinstance(row["session"], str)
                    or not isinstance(row["compressed_bytes"], int)
                    or row["compressed_bytes"] <= 0
                    or row["session"] in seen):
                raise ValueError("unique exact source sessions and sizes required")
            source_path(row["session"])
            seen.add(row["session"])
            rows.append({**row, "role": role})
    return rows


def program(row):
    spec = {
        "session": row["session"],
        "role": row["role"],
        "path": source_path(row["session"]),
        "compressed_bytes": row["compressed_bytes"],
        "max_decoded_bytes": 3 * 1024**3,
    }
    code = "import types,sys\n"
    for name, path in MODULES:
        code += "m=types.ModuleType(" + repr(name) + ");m.__file__=" + repr(path)
        code += ";sys.modules[m.__name__]=m\n"
        code += "exec(" + repr((ROOT / path).read_text()) + ",m.__dict__)\n"
    code += "SPEC=" + repr(spec) + "\n"
    code += (ROOT / WORKER).read_text()
    return code.encode(), spec


def source_hashes():
    paths = [path for _, path in MODULES] + [WORKER, "memory_policy/source_preflight.py"]
    return {path: file_hash(ROOT / path) for path in paths}


def validate_complete(manifest, reports):
    selected = selected_sources(manifest)
    if len(reports) != len(selected):
        raise ValueError("every selected source needs one receipt")
    for expected, report in zip(selected, reports):
        receipt = report.get("receipt") or {}
        if (report.get("complete") is not True
                or report.get("session") != expected["session"]
                or report.get("role") != expected["role"]
                or report.get("advertised_bytes") != expected["compressed_bytes"]
                or receipt.get("complete") is not True
                or receipt.get("compressed_bytes") != expected["compressed_bytes"]
                or receipt.get("json_object_records", 0) <= 0
                or receipt.get("raw_rows_exported") != 0
                or receipt.get("target_statistics_computed") != 0
                or receipt.get("provider_calls") != 0):
            raise ValueError("source receipt does not satisfy structural gate")
    return True


def canary(output):
    """Exercise the exact remote decoder/JSON/cleanup transport without providers."""
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("source preflight canary output is append-only")
    raw = b'{"fixture":1}\n{"fixture":2}\n'
    encoded = subprocess.run(
        ["zstd", "-q", "-c"], input=raw,
        stdout=subprocess.PIPE, check=True,
    ).stdout
    row = {"session": "2099-01-01T00", "compressed_bytes": len(encoded),
           "role": "initial_train"}
    body, spec = program(row)
    placeholder = source_path(row["session"])
    wrapped = (
        "import base64,pathlib,tempfile\n"
        "with tempfile.TemporaryDirectory(prefix='sealed-source-canary-') as temp:\n"
        " p=pathlib.Path(temp)/'fixture.jsonl.zst'\n"
        " p.write_bytes(base64.b64decode(" + repr(base64.b64encode(encoded).decode()) + "))\n"
        " exec(" + repr(body.decode()) + ".replace(" + repr(placeholder) + ",str(p)),{'__name__':'__main__'})\n"
        "print('{\"stage\":\"cleanup\",\"temporary_directory_removed\":true}')\n"
    ).encode()
    output.mkdir(parents=True)
    fresh_json(output / "claim.json", {
        "schema": "sealed_source_preflight_canary_claim_v1",
        "synthetic_only": True,
        "program_sha256": hashlib.sha256(wrapped).hexdigest(),
        "source_hashes": source_hashes(),
        "provider_calls_allowed": 0,
    })
    report = exchange(wrapped, output)
    receipt = report.get("receipt") or {}
    if (not report.get("complete")
            or report.get("temporary_directory_removed") is not True
            or receipt.get("compressed_sha256") != hashlib.sha256(encoded).hexdigest()
            or receipt.get("decoded_sha256") != hashlib.sha256(raw).hexdigest()
            or receipt.get("json_object_records") != 2
            or receipt.get("provider_calls") != 0):
        raise ValueError("remote structural canary failed")
    result = {
        "schema": "sealed_source_preflight_canary_v1",
        "passed": True,
        "synthetic_only": True,
        "source_hashes": source_hashes(),
        "receipt": receipt,
        "temporary_directory_removed": True,
        "provider_calls": 0,
    }
    result["result_sha256"] = digest(result)
    fresh_json(output / "canary.json", result)
    return result


def run(manifest_path, output):
    manifest_path = Path(manifest_path).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("source preflight output is append-only; use a fresh ID")
    manifest = load_json(manifest_path)
    selected = selected_sources(manifest)
    output.mkdir(parents=True)
    fresh_json(output / "claim.json", {
        "schema": "sealed_source_preflight_claim_v1",
        "manifest_sha256": file_hash(manifest_path),
        "selection_sha256": digest(selected),
        "source_hashes": source_hashes(),
        "selected_sources": len(selected),
        "paid_calls_allowed": 0,
    })
    reports = []
    try:
        for index, row in enumerate(selected):
            directory = output / f"{index:03d}-{row['role']}-{row['session']}"
            directory.mkdir()
            body, spec = program(row)
            fresh_json(directory / "dispatch.json", {
                "spec": spec,
                "program_sha256": hashlib.sha256(body).hexdigest(),
            })
            report = exchange(body, directory)
            fresh_json(directory / "report.json", report)
            reports.append(report)
            if not report["complete"]:
                raise ValueError("selected source failed before paid work")
        validate_complete(manifest, reports)
        result = {
            "schema": "sealed_source_preflight_v1",
            "complete": True,
            "manifest_sha256": file_hash(manifest_path),
            "selection_sha256": digest(selected),
            "source_hashes": source_hashes(),
            "reports": [{
                "session": report["session"],
                "role": report["role"],
                "receipt": report["receipt"],
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
            "completed_sources": len(reports),
            "paid_work_started": False,
            "no_automatic_replacement": True,
        })
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args()
    if args.canary:
        result = canary(args.output)
        print({"passed": result["passed"], "provider_calls": result["provider_calls"]})
    else:
        if args.manifest is None:
            parser.error("--manifest is required without --canary")
        result = run(args.manifest, args.output)
        print({"complete": result["complete"], "sources": len(result["reports"]),
               "provider_calls": result["provider_calls"]})
