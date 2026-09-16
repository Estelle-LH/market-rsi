"""Semantically admitted v2 wrapper around the paired memory-study engine."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from data_scientist_harness.release import git, source_files as harness_source_files
from market_rsi import digest, file_hash, fresh_json, load_json
from memory_pilot.run_materialize import modules as materialize_modules
from memory_policy.final_recovery import exchange as long_exchange
from memory_policy.materialize_worker_v2 import validate_policy
from memory_policy.semantic_binding import structural_receipt
from memory_policy.semantic_source_preflight import (
    source_hashes as semantic_source_hashes, validate_report,
)
from memory_policy.spec_v2 import validate as validate_spec
import memory_policy.study as engine


TAG = "pm-memory-policy-v0.2.0"
ORIGIN = "https://github.com/Estelle-LH/RSIBench-Data.git"
EXPERIMENT_DOC = ROOT / "MEMORY_POLICY_EXPERIMENT_2026-09-15.md"
MATERIALIZATION_POLICY = {
    "parent_address_space_bytes": 4 * 1024**3,
    "decoder_address_space_bytes": 256 * 1024**2,
    "max_decoded_bytes": 4 * 1024**3,
    "max_entities": 10000,
    "max_total_observations": 12000000,
    "max_entity_observations": 200000,
    "remote_wall_seconds": 2100,
    "remote_process_seconds": 2180,
    "local_transport_seconds": 2220,
}
validate_policy(MATERIALIZATION_POLICY)


def source_files(spec_path):
    paths = set(harness_source_files(ROOT))
    paths |= set((ROOT / "memory_pilot").glob("*.py"))
    paths |= set((ROOT / "memory_policy").glob("*.py"))
    paths |= {
        ROOT / "audit_tools/run_typed_raw_profile.py",
        ROOT / "audit_tools/single_object_stream.py",
        ROOT / "audit_tools/sealed_jsonl_integrity.py",
        ROOT / "audit_tools/source_integrity_worker.py",
        ROOT / "MEMORY_POLICY_CANDIDATE_POOL_2026-09-15.json",
        EXPERIMENT_DOC,
        Path(spec_path).resolve(),
    }
    return sorted(paths)


def hashes(spec_path):
    return {str(path.relative_to(ROOT)): file_hash(path)
            for path in source_files(spec_path)}


def publication(spec_path):
    files = hashes(spec_path)
    ref = "refs/tags/" + TAG
    commit = git(REPO, "rev-parse", ref + "^{commit}").decode().strip()
    if git(REPO, "remote", "get-url", "origin").decode().strip() != ORIGIN:
        raise ValueError("wrong origin")
    names = ["research/market_rsi/" + path for path in files]
    if git(REPO, "status", "--porcelain", "--untracked-files=all", "--", *names).strip():
        raise ValueError("dirty frozen v2 memory-policy source")
    for path, sha256 in files.items():
        if hashlib.sha256(git(
                REPO, "show", commit + ":research/market_rsi/" + path)).hexdigest() != sha256:
            raise ValueError("v2 memory-policy source not committed")
    if git(REPO, "cat-file", "-t", ref).decode().strip() != "tag":
        raise ValueError("annotated v2 tag required")
    tag_object = git(REPO, "rev-parse", ref).decode().strip()
    actual = {value.split()[1]: value.split()[0]
              for value in git(REPO, "ls-remote", "origin", ref, ref + "^{}").decode().splitlines()}
    if actual != {ref: tag_object, ref + "^{}": commit}:
        raise ValueError("v2 tag is not published at authorized origin")
    return {"commit": commit, "tag": TAG, "tag_object": tag_object,
            "source_hashes": files}


def preflight_receipts(spec_path, preflight_path, spec):
    value = load_json(preflight_path)
    expected = [{**row, "role": role}
                for role in ("initial_train", "dev", "final")
                for row in spec[role]]
    reports = value.get("reports", [])
    if (value.get("schema") not in {
                "memory_policy_semantic_preflight_v1",
                "memory_policy_semantic_preflight_promotion_v1",
            }
            or value.get("complete") is not True
            or value.get("manifest_sha256") != file_hash(spec_path)
            or value.get("contract_sha256") !=
                spec["fixed_contract"]["target_contract_sha256"]
            or value.get("source_hashes") != semantic_source_hashes()
            or value.get("target_statistics_computed") != 0
            or value.get("provider_calls") != 0
            or (value.get("schema") == "memory_policy_semantic_preflight_promotion_v1"
                and value.get("candidate_admission_sha256") !=
                    spec["candidate_admission"]["artifact_sha256"])
            or [(row.get("session"), row.get("role")) for row in reports]
                != [(row["session"], row["role"]) for row in expected]):
        raise ValueError("same-spec complete semantic preflight required")
    for row, report in zip(expected, reports):
        validate_report(row, report)
        structural_receipt(report)
    return {report["session"]: report for report in reports}


def midnight_ms(session):
    day = datetime.strptime(session[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(day.timestamp() * 1000)


def worker_program(operation):
    code = "import types,sys\n"
    for name in ("quote_source", "data_scientist_harness"):
        code += "m=types.ModuleType(" + repr(name) + ");m.__path__=[];sys.modules[m.__name__]=m\n"
    modules = materialize_modules() + [
        ("sealed_jsonl_integrity", "audit_tools/sealed_jsonl_integrity.py"),
        ("semantic_binding", "memory_policy/semantic_binding.py"),
    ]
    for name, path in modules:
        code += "m=types.ModuleType(" + repr(name) + ");m.__file__=" + repr(path)
        code += ";sys.modules[m.__name__]=m\n"
        code += "exec(" + repr((ROOT / path).read_text()) + ",m.__dict__)\n"
    code += "SPEC=" + repr(operation) + "\n"
    code += (ROOT / "memory_policy/materialize_worker_v2.py").read_text()
    return code.encode()


def materialize(root, row, role, receipt, contract, commitments=None, spec=None):
    session = row["session"]
    if role != "initial_train":
        engine.heldout_gate(root, session, role, commitments, spec)
    output = Path(root) / "data" / session
    output.mkdir(parents=True, exist_ok=False)
    remote_path = "/opt/d10/derived/" + Path(root).name + "/" + session
    operation = {
        "date": session,
        "path": engine.source_path(session),
        "output": remote_path,
        "compressed_bytes": row["compressed_bytes"],
        "contract": contract,
        "day_start_ms": midnight_ms(session),
        "role": role,
        "commitments": commitments or [],
        "semantic_preflight_report": receipt,
        "resource_policy": MATERIALIZATION_POLICY,
    }
    fresh_json(output / "exposure-claim.json", operation)
    report = long_exchange(worker_program(operation), output, MATERIALIZATION_POLICY)
    fresh_json(output / "report.json", report)
    if (report.get("complete") is not True
            or report.get("semantic_preflight_reproduced") is not True
            or report.get("provider_calls") != 0
            or report.get("raw_rows_exported") != 0
            or not isinstance(report.get("header"), dict)):
        raise ValueError("semantic-preflight-bound materialization failed; no score retry")
    transfer = subprocess.run([
        "scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "root@173.255.231.4:" + remote_path + "/rows.f64",
        str(output / "rows.f64"),
    ], capture_output=True, timeout=360)
    fresh_json(output / "transfer.json", {
        "exit_code": transfer.returncode, "process_reaped": True,
        "derived_cache_only": True,
    })
    header = report["header"]
    if (transfer.returncode
            or file_hash(output / "rows.f64") != header["sha256"]
            or (output / "rows.f64").stat().st_size != header["bytes"]):
        raise ValueError("derived v2 cache transfer failed")
    fresh_json(output / "header.json", header)
    return engine.cache_record(output, session)


def configure_engine():
    engine.TAG = TAG
    engine.validate_spec = validate_spec
    engine.source_files = source_files
    engine.hashes = hashes
    engine.publication = publication
    engine.preflight_receipts = preflight_receipts
    engine.materialize = materialize


def study(root, spec_path, preflight_path, canary_path, env_file, tokenizer_cache):
    configure_engine()
    return engine.study(root, spec_path, preflight_path, canary_path,
                        env_file, tokenizer_cache)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source-preflight", type=Path, required=True)
    parser.add_argument("--canary", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--tokenizer-cache", type=Path, required=True)
    args = parser.parse_args()
    study(args.output, args.spec, args.source_preflight, args.canary,
          args.env_file, args.tokenizer_cache)
