"""Final-only recovery for one no-score materialization failure."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import selectors
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from data_scientist_harness.release import git
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from memory_pilot.learning import evaluate, read_cache
from memory_pilot.run_materialize import modules as materialize_modules
from memory_policy.evaluation import ARMS, summarize
from paid_budget import PaidBudget


TAG = "pm-memory-policy-final-recovery-v0.1.0"
ORIGIN = "https://github.com/Estelle-LH/RSIBench-Data.git"
SOURCE_RUN = ROOT / "artifacts/memory-policy-20260914-01"
SOURCE_SPEC = ROOT / "MEMORY_POLICY_SPEC_2026-09-14.json"
SOURCE_PREFLIGHT = ROOT / "artifacts/source-preflight-memory-policy-20260914-01/complete.json"
DIAGNOSTIC_REPORT = (ROOT /
    "artifacts/memory-replication-20260914-02/data/2026-09-14T03/report.json")
BUDGET = ROOT / "artifacts/kalshi-research-glm53-20260907-01/budget"


def source_files(recovery_spec):
    paths = {ROOT / path for _, path in materialize_modules()}
    paths |= {
        ROOT / "audit_tools/run_typed_raw_profile.py",
        ROOT / "audit_tools/single_object_stream.py",
        ROOT / "audit_tools/sealed_jsonl_integrity.py",
        ROOT / "memory_policy/recovery_worker.py",
        ROOT / "memory_policy/final_recovery.py",
        ROOT / "memory_policy/evaluation.py",
        ROOT / "memory_policy/spec.py",
        ROOT / "memory_policy/test_final_recovery.py",
        ROOT / "memory_pilot/learning.py",
        ROOT / "MEMORY_POLICY_FINAL_RECOVERY_2026-09-14.md",
        Path(recovery_spec).resolve(),
    }
    return sorted(paths)


def source_hashes(recovery_spec):
    return {str(path.relative_to(ROOT)): file_hash(path)
            for path in source_files(recovery_spec)}


def publication(recovery_spec):
    files = source_hashes(recovery_spec)
    if git(REPO, "remote", "get-url", "origin").decode().strip() != ORIGIN:
        raise ValueError("wrong origin")
    ref = "refs/tags/" + TAG
    commit = git(REPO, "rev-parse", ref + "^{commit}").decode().strip()
    names = ["research/market_rsi/" + path for path in files]
    if git(REPO, "status", "--porcelain", "--untracked-files=all", "--", *names).strip():
        raise ValueError("dirty recovery source")
    for path, sha256 in files.items():
        body = git(REPO, "show", commit + ":research/market_rsi/" + path)
        if hashlib.sha256(body).hexdigest() != sha256:
            raise ValueError("recovery source not committed")
    if git(REPO, "cat-file", "-t", ref).decode().strip() != "tag":
        raise ValueError("annotated recovery tag required")
    tag_object = git(REPO, "rev-parse", ref).decode().strip()
    actual = {value.split()[1]: value.split()[0]
              for value in git(REPO, "ls-remote", "origin", ref, ref + "^{}").decode().splitlines()}
    if actual != {ref: tag_object, ref + "^{}": commit}:
        raise ValueError("recovery tag not published at authorized origin")
    return {"commit": commit, "tag": TAG, "tag_object": tag_object,
            "source_hashes": files}


def validate_recovery_spec(value):
    expected_keys = {
        "schema", "recovery_id", "source_experiment_id",
        "source_claim_sha256",
        "source_experiment_spec_sha256", "source_failure_sha256",
        "source_final_model_freeze_sha256", "source_preflight_sha256",
        "failed_session", "changed_stage", "unchanged_scientific_state",
        "resource_policy", "large_canary", "recovery_rules",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ValueError("exact Final recovery spec required")
    if (value["schema"] != "memory_policy_final_recovery_v1"
            or value["source_experiment_id"] != SOURCE_RUN.name
            or value["failed_session"] != "2026-09-09T20"
            or value["changed_stage"] != "raw_data_materialization_resource_envelope"):
        raise ValueError("wrong recovery identity or changed stage")
    unchanged = value["unchanged_scientific_state"]
    if unchanged != {
        "controller_rounds": 8,
        "controller_calls": 24,
        "model_selection": "frozen Round 8 submissions",
        "target": "unchanged",
        "features": "unchanged per frozen arm model",
        "train_rows": "unchanged",
        "final_sessions": "exact original ordered manifest",
        "evaluation": "unchanged paired evaluator",
        "final_scores_seen_before_recovery": 0,
    }:
        raise ValueError("scientific state is not frozen")
    rules = value["recovery_rules"]
    if rules != {
        "controller_or_training_calls": 0,
        "model_changes": 0,
        "session_replacement": False,
        "score_retry": False,
        "automatic_second_recovery": False,
        "qualification": "same preregistered Final after one runner-only no-score infrastructure failure",
    }:
        raise ValueError("recovery may not adapt models, sessions, or scores")
    from memory_policy.recovery_worker import validate_limits
    validate_limits(value["resource_policy"])
    canary = value["large_canary"]
    if (canary.get("session") != "2026-09-14T03"
            or canary.get("evidence_class") != "previously opened diagnostic only"
            or canary.get("expected_selected_observations") != 3867212):
        raise ValueError("exact disclosed large canary required")
    return value


def verify_source_run(recovery_spec):
    checks = {
        SOURCE_SPEC: recovery_spec["source_experiment_spec_sha256"],
        SOURCE_RUN / "claim.json": recovery_spec["source_claim_sha256"],
        SOURCE_RUN / "failure.json": recovery_spec["source_failure_sha256"],
        SOURCE_RUN / "final-model-freeze.json":
            recovery_spec["source_final_model_freeze_sha256"],
        SOURCE_PREFLIGHT: recovery_spec["source_preflight_sha256"],
    }
    for path, expected in checks.items():
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError("source experiment artifact changed")
    failure = load_json(SOURCE_RUN / "failure.json")
    source_claim = load_json(SOURCE_RUN / "claim.json")
    if (failure.get("no_automatic_retry") is not True
            or failure.get("partial_outcomes_preserved") is not True
            or (SOURCE_RUN / "complete.json").exists()):
        raise ValueError("source run is not the preserved incomplete run")
    original = load_json(SOURCE_SPEC)
    from memory_policy.spec import validate as validate_original_spec
    validate_original_spec(original)
    preflight = load_json(SOURCE_PREFLIGHT)
    freeze = load_json(SOURCE_RUN / "final-model-freeze.json")
    receipts = {row["session"]: row["receipt"] for row in preflight["reports"]}
    if (preflight.get("complete") is not True
            or preflight.get("manifest_sha256") != file_hash(SOURCE_SPEC)
            or preflight.get("provider_calls") != 0
            or set(receipts) != {row["session"] for role in ("initial_train", "dev", "final")
                                for row in original[role]}
            or freeze.get("selection") != "Round 8 submissions; no further model dispatch"
            or freeze.get("final_manifest_commitment") != digest(original["final"])):
        raise ValueError("original source receipts or Final freeze differ")
    original_publication = source_claim.get("publication") or {}
    if (original_publication.get("commit") != "ac11a021aff8cc8486ec417576179972f6fcca85"
            or original_publication.get("tag") != "pm-memory-policy-v0.1.0"
            or original_publication.get("source_hashes", {}).get(
                "MEMORY_POLICY_SPEC_2026-09-14.json") != file_hash(SOURCE_SPEC)):
        raise ValueError("original published experiment identity differs")
    for number in range(1, 9):
        round_dir = SOURCE_RUN / f"round-{number}"
        if (not (round_dir / "dev-scores.json").is_file()
                or load_json(round_dir / "promotion-to-train.json").get("consumed") is not True):
            raise ValueError("all eight original rolling rounds must be complete")
    if (list(SOURCE_RUN.glob("final-20??-??-??T??.json"))
            or list(SOURCE_RUN.glob("*-final-20??-??-??T??.npy"))):
        raise ValueError("source run already contains a Final score or prediction")
    exposed = []
    for report_path in (SOURCE_RUN / "data").glob("*/report.json"):
        report = load_json(report_path)
        if report.get("role") == "final":
            exposed.append((report_path.parent.name, report))
    if len(exposed) != 1 or exposed[0][0] != recovery_spec["failed_session"]:
        raise ValueError("unexpected prior Final exposure")
    report = exposed[0][1]
    if (report.get("complete") is not False or report.get("header") is not None
            or report.get("fits") != 0 or report.get("provider_calls") != 0
            or report.get("raw_rows_exported") != 0
            or report.get("controller_access") is not False):
        raise ValueError("prior Final failure was not score-free and runner-only")
    paths = {
        "archive": SOURCE_RUN / "round-8/archive-refit",
        "baseline": SOURCE_RUN / "round-8/common-baseline-refit",
        "compact": SOURCE_RUN / "round-8/compact-refit",
        "fresh": SOURCE_RUN / "round-8/fresh-refit",
    }
    if set(paths) != set(ARMS):
        raise ValueError("four frozen arms required")
    for arm, path in paths.items():
        if file_hash(path / "model.pkl") != freeze["models"][arm]:
            raise ValueError("frozen Round 8 model changed")
    return {"original_spec": original, "preflight": preflight,
            "receipts": receipts, "freeze": freeze, "models": paths,
            "failed_report": report}


def worker_program(operation):
    code = "import types,sys\n"
    for name in ("quote_source", "data_scientist_harness"):
        code += "m=types.ModuleType(" + repr(name) + ");m.__path__=[];sys.modules[m.__name__]=m\n"
    modules = materialize_modules() + [
        ("sealed_jsonl_integrity", "audit_tools/sealed_jsonl_integrity.py")]
    for name, path in modules:
        code += "m=types.ModuleType(" + repr(name) + ");m.__file__=" + repr(path)
        code += ";sys.modules[m.__name__]=m\n"
        code += "exec(" + repr((ROOT / path).read_text()) + ",m.__dict__)\n"
    code += "SPEC=" + repr(operation) + "\n"
    code += (ROOT / "memory_policy/recovery_worker.py").read_text()
    return code.encode()


def exchange(code, output, limits):
    command = ("flock -n /tmp/market-rsi-population-quote.lock nice -n 10 timeout "
               "--signal=TERM --kill-after=5s " +
               str(limits["remote_process_seconds"]) + "s python3 -u - --remote")
    process = subprocess.Popen([
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "root@173.255.231.4", command,
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    fresh_json(output / "process.json", {"ssh_pid": process.pid})
    process.stdin.write(code)
    process.stdin.close()
    os.set_blocking(process.stdout.fileno(), False)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    pending = b""
    total = sequence = 0
    terminal = None
    deadline = time.monotonic() + limits["local_transport_seconds"]
    error = None
    try:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("recovery transport deadline")
            if not selector.select(1):
                continue
            data = os.read(process.stdout.fileno(), 65536)
            if not data:
                break
            total += len(data)
            pending += data
            if total > 16 * 1024**2:
                raise ValueError("aggregate recovery output bound")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                packet = json.loads(line)
                fresh_json(output / f"progress-{sequence:03d}.json", packet)
                sequence += 1
                if packet["stage"] == "terminal":
                    terminal = packet["report"]
                else:
                    print(json.dumps(packet), flush=True)
        exit_code = process.wait(timeout=10)
        if exit_code or pending or terminal is None:
            raise ValueError("recovery terminal missing")
        terminal.update(ssh_reaped=True, exit_code=exit_code)
    except BaseException as found:
        error = type(found).__name__
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        selector.close()
        process.stdout.close()
    if error:
        fresh_json(output / "transport-failure.json", {
            "failure_type": error, "ssh_reaped": True, "retry": False})
        raise RuntimeError("recovery worker did not return verified terminal evidence")
    return terminal


def operation(session, row, role, receipt, contract, limits, remote_root, freeze):
    return {
        "date": session,
        "path": "/opt/d10/raw/data/polymarket/polymarket-" +
                session.replace("-", "") + ".jsonl.zst",
        "output": remote_root + "/" + session,
        "compressed_bytes": row["compressed_bytes"],
        "contract": contract,
        "day_start_ms": int(__import__("datetime").datetime.strptime(
            session[:10], "%Y-%m-%d").replace(
                tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000),
        "role": role,
        "source_integrity_receipt": receipt,
        "resource_policy": limits,
        "frozen_model_commitment": freeze,
    }


def materialize(output, operation_value, limits):
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / "exposure-claim.json", operation_value)
    report = exchange(worker_program(operation_value), output, limits)
    fresh_json(output / "report.json", report)
    if (report.get("complete") is not True
            or report.get("preflight_receipt_reproduced") is not True
            or report.get("provider_calls") != 0
            or report.get("raw_rows_exported") != 0):
        raise ValueError("recovery materialization failed; no retry")
    transfer = subprocess.run([
        "scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "root@173.255.231.4:" + operation_value["output"] + "/rows.f64",
        str(output / "rows.f64"),
    ], capture_output=True, timeout=360)
    fresh_json(output / "transfer.json", {
        "exit_code": transfer.returncode, "process_reaped": True,
        "derived_cache_only": True})
    header = report["header"]
    if (transfer.returncode or file_hash(output / "rows.f64") != header["sha256"]
            or (output / "rows.f64").stat().st_size != header["bytes"]):
        raise ValueError("recovery cache transfer failed; no retry")
    fresh_json(output / "header.json", header)
    record = {"date": operation_value["date"], "path": str(output),
              "header_sha256": file_hash(output / "header.json"),
              "cache_sha256": header["sha256"]}
    read_cache(record)
    return record


def large_canary(output, recovery_spec, published):
    if output.exists():
        raise ValueError("fresh large-canary ID required")
    expected = recovery_spec["large_canary"]
    if file_hash(DIAGNOSTIC_REPORT) != expected["prior_report_sha256"]:
        raise ValueError("prior diagnostic report changed")
    old = load_json(DIAGNOSTIC_REPORT)
    if old.get("report"):
        old = old["report"]
    if (old.get("complete") is not True
            or old["header"]["sha256"] != expected["expected_cache_sha256"]
            or old["header"]["quality"]["counts"]["selected_observations"]
                != expected["expected_selected_observations"]):
        raise ValueError("prior large diagnostic evidence differs")
    output.mkdir(parents=True)
    fresh_json(output / "claim.json", {
        "publication": published,
        "prior_report_sha256": file_hash(DIAGNOSTIC_REPORT),
        "evidence_class": expected["evidence_class"],
        "new_final_opened": False,
    })
    session = expected["session"]
    source = old["spec"]
    op = operation(session, {"compressed_bytes": source["compressed_bytes"]},
        "diagnostic_canary", old["spec"].get("source_integrity_receipt") or {
            "schema": "sealed_jsonl_integrity_v1", "complete": True,
            "compressed_bytes": old["transport"]["compressed_bytes_read"],
            "compressed_sha256": old["transport"]["compressed_sha256"],
            "decoded_bytes": old["transport"]["decoded_bytes"],
            "decoded_sha256": old["transport"]["decoded_sha256"],
            "json_object_records": old["transport"]["decoded_records"],
            "source_initial_stat": old["transport"]["source_initial_stat"],
        }, source["contract"], recovery_spec["resource_policy"],
        "/opt/d10/derived/" + output.name, {"diagnostic_only": True})
    record = materialize(output / "data", op, recovery_spec["resource_policy"])
    header = load_json(Path(record["path"]) / "header.json")
    if (header["sha256"] != expected["expected_cache_sha256"]
            or header["quality"]["counts"]["selected_observations"]
                != expected["expected_selected_observations"]):
        raise ValueError("large recovery canary cache differs")
    result = {
        "schema": "memory_policy_final_recovery_large_canary_v1",
        "passed": True,
        "publication": published,
        "session": session,
        "evidence_class": expected["evidence_class"],
        "cache_sha256": header["sha256"],
        "selected_observations":
            header["quality"]["counts"]["selected_observations"],
        "provider_calls": 0,
        "new_final_opened": False,
    }
    result["result_sha256"] = digest(result)
    fresh_json(output / "complete.json", result)
    return result


def run(output, recovery_spec_path, canary_path):
    output = Path(output).resolve()
    recovery_spec_path = Path(recovery_spec_path).resolve()
    canary_path = Path(canary_path).resolve()
    with (ROOT / "artifacts/memory-policy-final-recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if output.exists():
            raise ValueError("permanent recovery ID already used")
        spec = validate_recovery_spec(load_json(recovery_spec_path))
        if output.name != spec["recovery_id"]:
            raise ValueError("output must match permanent recovery ID")
        published = publication(recovery_spec_path)
        canary = load_json(canary_path)
        if (canary.get("passed") is not True
                or canary.get("publication") != published
                or canary.get("cache_sha256") !=
                    spec["large_canary"]["expected_cache_sha256"]
                or canary.get("provider_calls") != 0
                or canary.get("new_final_opened") is not False):
            raise ValueError("same-source published large canary required")
        source = verify_source_run(spec)
        for package, version in {"numpy": "1.26.4", "scipy": "1.14.0",
                                 "scikit-learn": "1.6.1"}.items():
            if importlib.metadata.version(package) != version:
                raise ValueError("pinned recovery runtime differs: " + package)
        before = PaidBudget(BUDGET).snapshot()
        original = source["original_spec"]
        contract = load_json(ROOT /
            "artifacts/memory-train-data-20260913-01/2026-08-26/report.json")["spec"]["contract"]
        if digest(contract) != original["fixed_contract"]["target_contract_sha256"]:
            raise ValueError("frozen target contract differs")
        output.mkdir(parents=True)
        (output / "data").mkdir()
        fresh_json(output / "pre-score-lock.json", {
            "recovery_spec_sha256": file_hash(recovery_spec_path),
            "publication": published,
            "source_failure_sha256": spec["source_failure_sha256"],
            "source_final_model_freeze_sha256": spec["source_final_model_freeze_sha256"],
            "final_manifest_commitment": digest(original["final"]),
            "scores_seen_before_recovery": 0,
            "qualification": spec["recovery_rules"]["qualification"],
        })
        final_scores = []
        try:
            for row in original["final"]:
                session = row["session"]
                op = operation(session, row, "final", source["receipts"][session],
                    contract, spec["resource_policy"],
                    "/opt/d10/derived/" + output.name,
                    source["freeze"]["models"])
                record = materialize(output / "data" / session, op,
                                     spec["resource_policy"])
                scores = {}
                paired = set()
                for arm, directory in source["models"].items():
                    if file_hash(directory / "model.pkl") != source["freeze"]["models"][arm]:
                        raise ValueError("frozen model changed during recovery")
                    with (directory / "model.pkl").open("rb") as stream:
                        model = pickle.load(stream)
                    scores[arm] = evaluate(model, record,
                        output / (arm + "-final-" + session + ".npy"))
                    paired.add((scores[arm]["n"], scores[arm]["paired_rows_sha256"]))
                if len(paired) != 1:
                    raise ValueError("Final arms are not on identical rows")
                fresh_json(output / ("final-" + session + ".json"), scores)
                final_scores.append(scores)
                print(canonical({"stage": "final_session_complete", "session": session,
                    "completed": len(final_scores), "total": len(original["final"])}),
                    flush=True)
            metrics = summarize(final_scores)
            after = PaidBudget(BUDGET).snapshot()
            if after != before:
                raise ValueError("CPU-only Final recovery changed paid budget")
            report = {
                "schema": "memory_policy_final_recovery_complete_v1",
                "complete": True,
                "metrics": metrics,
                "final_sessions": len(final_scores),
                "publication": published,
                "source_experiment_id": SOURCE_RUN.name,
                "source_final_model_freeze_sha256": file_hash(
                    SOURCE_RUN / "final-model-freeze.json"),
                "qualification": spec["recovery_rules"]["qualification"],
                "first_final_partial_runner_read_disclosed": True,
                "controller_calls": 0,
                "training_calls": 0,
                "paid_budget_unchanged": True,
                "formal_promotion": False,
                "pnl_measured": False,
            }
            fresh_json(output / "complete.json", report)
            print(canonical(report), flush=True)
            return report
        except BaseException as error:
            fresh_json(output / "failure.json", {
                "type": type(error).__name__,
                "message": str(error)[:800],
                "completed_final_sessions": len(final_scores),
                "automatic_retry": False,
                "partial_outcomes_preserved": True,
            })
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--large-canary", action="store_true")
    parser.add_argument("--canary-receipt", type=Path)
    args = parser.parse_args()
    spec = validate_recovery_spec(load_json(args.spec))
    if args.large_canary:
        result = large_canary(args.output.resolve(), spec, publication(args.spec))
        print(canonical(result))
    else:
        if args.canary_receipt is None:
            parser.error("--canary-receipt required for Final recovery")
        run(args.output, args.spec, args.canary_receipt)
