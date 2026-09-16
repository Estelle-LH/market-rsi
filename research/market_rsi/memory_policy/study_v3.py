"""Resource-repaired v3 wrapper around the paired memory-study engine."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from data_scientist_harness.release import git, source_files as harness_source_files
from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy import controller
from memory_policy.broker_v3 import Broker, refit_worker
from memory_policy.semantic_binding import structural_receipt
from memory_policy.semantic_source_preflight import (
    source_hashes as semantic_source_hashes, validate_report,
)
from memory_policy.spec_v3 import validate as validate_spec
from memory_policy.trainer_canary_v3 import source_hashes as trainer_source_hashes
import memory_policy.study as engine
import memory_policy.study_v2 as v2


TAG = "pm-memory-policy-v0.3.1"
ORIGIN = "https://github.com/Estelle-LH/RSIBench-Data.git"
EXPERIMENT_DOC = ROOT / "MEMORY_POLICY_V3_EXPERIMENT_2026-09-15.md"
SELECTION_DOC = ROOT / "MEMORY_POLICY_V3_SOURCE_SELECTION_2026-09-15.json"


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
        SELECTION_DOC,
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
        raise ValueError("dirty frozen v3 memory-policy source")
    for path, sha256 in files.items():
        body = git(REPO, "show", commit + ":research/market_rsi/" + path)
        if hashlib.sha256(body).hexdigest() != sha256:
            raise ValueError("v3 memory-policy source not committed")
    if git(REPO, "cat-file", "-t", ref).decode().strip() != "tag":
        raise ValueError("annotated v3 tag required")
    tag_object = git(REPO, "rev-parse", ref).decode().strip()
    actual = {value.split()[1]: value.split()[0]
              for value in git(REPO, "ls-remote", "origin", ref, ref + "^{}").decode().splitlines()}
    if actual != {ref: tag_object, ref + "^{}": commit}:
        raise ValueError("v3 tag is not published at authorized origin")
    return {"commit": commit, "tag": TAG, "tag_object": tag_object,
            "source_hashes": files}


def preflight_receipts(spec_path, preflight_path, spec):
    value = load_json(preflight_path)
    expected = [{**row, "role": role}
                for role in ("initial_train", "dev", "final")
                for row in spec[role]]
    reports = value.get("reports", [])
    if (value.get("schema") != "memory_policy_semantic_preflight_promotion_v2"
            or value.get("complete") is not True
            or value.get("manifest_sha256") != file_hash(spec_path)
            or value.get("contract_sha256") !=
                spec["fixed_contract"]["target_contract_sha256"]
            or value.get("source_hashes") != semantic_source_hashes()
            or value.get("source_reselection_sha256") !=
                spec["candidate_admission"]["artifact_sha256"]
            or value.get("source_admission_sha256") !=
                spec["candidate_admission"]["source_admission_sha256"]
            or value.get("target_statistics_computed") != 0
            or value.get("provider_calls") != 0
            or [(row.get("session"), row.get("role")) for row in reports]
                != [(row["session"], row["role"]) for row in expected]):
        raise ValueError("same-spec complete v3 semantic preflight required")
    for row, report in zip(expected, reports):
        validate_report(row, report)
        structural_receipt(report)
    cumulative = sum(report["semantic_receipt"]["selected_observations"]
                     for report in reports
                     if report["role"] in {"initial_train", "dev"})
    if cumulative > spec["trainer_resource_gate"][
            "max_cumulative_selected_observations"]:
        raise ValueError("cumulative selected-observation gate failed")
    return {report["session"]: report for report in reports}


def cleanup_remote_cache(root, session, evidence_directory, *, transport=subprocess.run):
    """Remove only one verified derived-cache directory after local transfer."""
    run_id = Path(root).name
    if (not re.fullmatch(r"memory-policy-v3-[0-9]{8}-[0-9]{2}", run_id)
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}", session)):
        raise ValueError("canonical v3 cleanup identity required")
    target = "/opt/d10/derived/" + run_id + "/" + session
    program = (
        "import json,pathlib,shutil,sys;"
        "base=pathlib.Path('/opt/d10/derived').resolve();"
        "target=pathlib.Path(sys.argv[1]);"
        "resolved=target.resolve();"
        "relative=resolved.relative_to(base);"
        "assert len(relative.parts)==2 and resolved==target;"
        "shutil.rmtree(resolved) if resolved.exists() else None;"
        "print(json.dumps({'removed':not resolved.exists(),"
        "'relative_parts':list(relative.parts)}))"
    )
    command = "python3 -c " + shlex.quote(program) + " " + shlex.quote(target)
    attempts = []
    for number in range(1, 4):
        result = transport([
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "root@173.255.231.4", command,
        ], capture_output=True, text=True, timeout=60)
        receipt = None
        try:
            receipt = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            pass
        attempts.append({
            "attempt": number,
            "exit_code": result.returncode,
            "process_reaped": True,
            "receipt": receipt,
        })
        if (result.returncode == 0 and receipt == {
                "removed": True, "relative_parts": [run_id, session]}):
            break
    evidence_directory = Path(evidence_directory)
    fresh_json(evidence_directory / "remote-cleanup.json", {
        "schema": "memory_policy_remote_cache_cleanup_v3",
        "target_sha256": digest(target),
        "attempts": attempts,
        "complete": bool(attempts[-1]["exit_code"] == 0
                         and attempts[-1]["receipt"] == {
                             "removed": True,
                             "relative_parts": [run_id, session]}),
        "local_transfer_verified_before_cleanup": True,
        "raw_source_deleted": False,
    })
    if not load_json(evidence_directory / "remote-cleanup.json")["complete"]:
        raise RuntimeError("exact remote derived-cache cleanup failed")


def materialize(root, row, role, receipt, contract, commitments=None, spec=None):
    record = v2.materialize(
        root, row, role, receipt, contract, commitments, spec)
    cleanup_remote_cache(root, row["session"], Path(record["path"]))
    return record


def configure_engine():
    engine.TAG = TAG
    engine.validate_spec = validate_spec
    engine.source_files = source_files
    engine.hashes = hashes
    engine.publication = publication
    engine.preflight_receipts = preflight_receipts
    engine.materialize = materialize
    engine.run_worker = refit_worker
    engine.Broker = Broker
    controller.Broker = Broker
    controller.BROKER_SCRIPT = ROOT / "memory_policy/broker_v3.py"


def study(root, spec_path, preflight_path, canary_path, env_file, tokenizer_cache):
    configure_engine()
    canary = load_json(canary_path)
    from memory_policy.remote_cleanup_canary_v3 import (
        source_hashes as remote_cleanup_source_hashes,
    )
    if (canary.get("schema") != "memory_policy_full_canary_v3"
            or canary.get("trainer_source_hashes") != trainer_source_hashes()
            or canary.get("trainer_positive_canary", {}).get("provider_calls") != 0
            or canary.get("trainer_positive_canary", {}).get("scores_opened") != 0
            or canary.get("remote_cleanup_source_hashes") !=
                remote_cleanup_source_hashes()
            or canary.get("expected_remote_cleanup_source_hashes") !=
                remote_cleanup_source_hashes()
            or canary.get("remote_cleanup_passed") is not True
            or canary.get("trainer_model_reused") is not False):
        raise ValueError("bound positive trainer canary required")
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
