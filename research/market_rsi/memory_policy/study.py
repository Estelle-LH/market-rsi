"""Eight-round, three-arm controller-memory experiment runner."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from controller_harness_contract import (
    MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS,
)
from data_scientist_harness.release import git, source_files as harness_source_files
from glm_canary import MODEL, cost
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from memory_pilot.learning import BASE, evaluate, read_cache
from memory_pilot.run_materialize import modules as materialize_modules
from memory_policy.broker import Broker, run_worker
from memory_policy.controller import TinkerGLMBackend, harness, run_session
from memory_policy.evaluation import ARMS, summarize
from memory_policy.source_preflight import source_hashes as integrity_source_hashes
from memory_policy.spec import validate as validate_spec
from memory_policy.summary import memory_payload
from paid_budget import PaidBudget, money
from run_typed_raw_profile import exchange


TAG = "pm-memory-policy-v0.1.0"
BUDGET = ROOT / "artifacts/kalshi-research-glm53-20260907-01/budget"
AUTH = "d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9"
UPPER = cost(MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS)
CONTRACT_SOURCE = ROOT / "artifacts/memory-train-data-20260913-01/2026-08-26/report.json"
EXPERIMENT_ARMS = ("fresh", "archive", "compact")


def source_files(spec_path):
    paths = set(harness_source_files(ROOT))
    paths |= set((ROOT / "memory_pilot").glob("*.py"))
    paths |= set((ROOT / "memory_policy").glob("*.py"))
    paths |= {
        ROOT / "audit_tools/run_typed_raw_profile.py",
        ROOT / "audit_tools/single_object_stream.py",
        ROOT / "audit_tools/sealed_jsonl_integrity.py",
        ROOT / "audit_tools/source_integrity_worker.py",
        ROOT / "MEMORY_POLICY_EXPERIMENT_2026-09-14.md",
        Path(spec_path).resolve(),
    }
    return sorted(paths)


def hashes(spec_path):
    return {str(path.relative_to(ROOT)): file_hash(path)
            for path in source_files(spec_path)}


def publication(spec_path):
    files = hashes(spec_path)
    repo = ROOT.parents[1]
    ref = "refs/tags/" + TAG
    commit = git(repo, "rev-parse", ref + "^{commit}").decode().strip()
    if git(repo, "remote", "get-url", "origin").decode().strip() != "https://github.com/Estelle-LH/RSIBench-Data.git":
        raise ValueError("wrong origin")
    names = ["research/market_rsi/" + path for path in files]
    if git(repo, "status", "--porcelain", "--untracked-files=all", "--", *names).strip():
        raise ValueError("dirty frozen memory-policy source")
    for path, sha256 in files.items():
        if hashlib.sha256(git(repo, "show", commit + ":research/market_rsi/" + path)).hexdigest() != sha256:
            raise ValueError("memory-policy source not committed")
    if git(repo, "cat-file", "-t", ref).decode().strip() != "tag":
        raise ValueError("annotated tag required")
    tag_object = git(repo, "rev-parse", ref).decode().strip()
    actual = {value.split()[1]: value.split()[0]
              for value in git(repo, "ls-remote", "origin", ref, ref + "^{}").decode().splitlines()}
    if actual != {ref: tag_object, ref + "^{}": commit}:
        raise ValueError("memory-policy tag is not published at authorized origin")
    return {"commit": commit, "tag": TAG, "tag_object": tag_object,
            "source_hashes": files}


def cache_record(path, session):
    header = load_json(path / "header.json")
    record = {"date": session, "path": str(path),
              "header_sha256": file_hash(path / "header.json"),
              "cache_sha256": header["sha256"]}
    read_cache(record)
    return record


def workspace(path, train, baseline, history, round_number, arm, rounds,
              source_hashes, *, fixture=False):
    path.mkdir(parents=True, exist_ok=False)
    (path / "records").mkdir()
    (path / "trials").mkdir()
    qa = []
    for record in train:
        header = load_json(Path(record["path"]) / "header.json")
        quality = header.get("quality", {})
        qa.append({
            "session": record["date"], "rows": header["shape"][0],
            "counts": quality.get("counts", {}),
            "feature_min": header.get("feature_minimum"),
            "feature_max": header.get("feature_maximum"),
            "target_rms_price_bps": quality.get("target_rms_price_bps"),
            "source_hash": record["cache_sha256"],
        })
    archive = memory_payload(arm, history)
    config = {
        "fixture": fixture,
        "source_hashes": source_hashes,
        "train": train,
        "baseline": baseline,
        "archive": archive,
        "public_context": {
            "round": round_number, "planned_rounds": rounds, "arm": arm,
            "memory_representation": {
                "fresh": "none", "archive": "complete raw own-arm archive",
                "compact": "deterministic own-arm decisions and measured evidence",
            }[arm],
            "memory_characters": len(canonical(archive)),
            "train_qa": qa,
            "train_sessions": [record["date"] for record in train],
            "chronological_fit_sessions": [record["date"] for record in train[:-1]],
            "opened_train_check_session": train[-1]["date"],
            "current_dev": "runner-sealed until all three submissions",
            "final_test": "opaque and closed",
            "maximum_session_usd_not_spend": str(UPPER),
            "primary_final_selection": f"Round {rounds} submitted plan, refit before Final",
            "model": MODEL,
            "component_change": "features OR trainer/normalizer; target, rows, seed and no-clipping policy fixed",
            "operator_limit": "same four tabular learners and same feature library for every arm",
        },
    }
    fresh_json(path / "config.json", config)
    return file_hash(path / "config.json")


def arm_cost(snapshot, prefix):
    jobs = {key: value for key, value in snapshot["jobs"].items()
            if key.startswith(prefix + "-turn-")}
    metered = sum((money(value.get("metered_usd") or 0) for value in jobs.values()), money(0))
    uncertain = sum((money(value.get("uncertain_upper_usd") or 0) for value in jobs.values()), money(0))
    outstanding = sum((money(value["upper_usd"]) for value in jobs.values()
                       if value["state"] in ("reserved", "dispatched")), money(0))
    return {"metered_usd": str(metered), "uncertain_upper_usd": str(uncertain),
            "outstanding_usd": str(outstanding), "turns": len(jobs)}


def source_path(session):
    parsed = datetime.strptime(session, "%Y-%m-%dT%H")
    if parsed.strftime("%Y-%m-%dT%H") != session:
        raise ValueError("canonical session required")
    return "/opt/d10/raw/data/polymarket/polymarket-" + session.replace("-", "") + ".jsonl.zst"


def midnight_ms(session):
    day = datetime.strptime(session[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(day.timestamp() * 1000)


def preflight_receipts(spec_path, preflight_path, spec):
    value = load_json(preflight_path)
    expected_sessions = [row["session"] for role in ("initial_train", "dev", "final")
                         for row in spec[role]]
    reports = value.get("reports", [])
    if (value.get("schema") != "sealed_source_preflight_v1"
            or value.get("complete") is not True
            or value.get("manifest_sha256") != file_hash(spec_path)
            or value.get("source_hashes") != integrity_source_hashes()
            or value.get("provider_calls") != 0
            or [report.get("session") for report in reports] != expected_sessions):
        raise ValueError("same-spec complete all-source preflight required")
    return {report["session"]: report["receipt"] for report in reports}


def heldout_gate(root, session, role, commitments, spec):
    if role not in ("dev", "final") or len(commitments) != 3 or len({item["path"] for item in commitments}) != 3:
        raise ValueError("three distinct submissions required before held-out access")
    for item in commitments:
        if file_hash(item["path"]) != item["sha256"]:
            raise ValueError("submission changed before held-out access")
    rows = spec[role]
    if session not in [row["session"] for row in rows]:
        raise ValueError("session not predeclared for role")
    if role == "dev":
        freeze = load_json(Path(root) / f"round-{[r['session'] for r in rows].index(session) + 1}" / "paired-freeze.json")
    else:
        for number in range(1, spec["rounds"] + 1):
            if load_json(Path(root) / f"round-{number}" / "promotion-to-train.json")["consumed"] is not True:
                raise ValueError("all rolling rounds required before Final")
        freeze = load_json(Path(root) / "final-model-freeze.json")
    if freeze["commitments"] != commitments or set(freeze["models"]) != set(ARMS):
        raise ValueError("three-arm model/submission freeze missing")


def materialize(root, row, role, receipt, contract, commitments=None, spec=None):
    session = row["session"]
    if role != "initial_train":
        heldout_gate(root, session, role, commitments, spec)
    output = Path(root) / "data" / session
    output.mkdir(parents=True, exist_ok=False)
    remote_path = "/opt/d10/derived/" + Path(root).name + "/" + session
    operation = {
        "date": session, "path": source_path(session), "output": remote_path,
        "compressed_bytes": row["compressed_bytes"], "contract": contract,
        "day_start_ms": midnight_ms(session), "role": role,
        "commitments": commitments or [], "source_integrity_receipt": receipt,
    }
    fresh_json(output / "exposure-claim.json", operation)
    code = "import types,sys\n"
    for name in ("quote_source", "data_scientist_harness"):
        code += "m=types.ModuleType(" + repr(name) + ");m.__path__=[];sys.modules[m.__name__]=m\n"
    modules = materialize_modules() + [("sealed_jsonl_integrity", "audit_tools/sealed_jsonl_integrity.py")]
    for name, path in modules:
        code += "m=types.ModuleType(" + repr(name) + ");m.__file__=" + repr(path) + ";sys.modules[m.__name__]=m\n"
        code += "exec(" + repr((ROOT / path).read_text()) + ",m.__dict__)\n"
    code += "SPEC=" + repr(operation) + "\n" + (ROOT / "memory_policy/heldout_worker.py").read_text()
    report = exchange(code.encode(), output)
    fresh_json(output / "report.json", report)
    if not report["complete"] or report.get("preflight_receipt_reproduced") is not True:
        raise ValueError("preflight-bound source failed; no replacement or score retry")
    transfer = subprocess.run([
        "scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "root@173.255.231.4:" + remote_path + "/rows.f64", str(output / "rows.f64"),
    ], capture_output=True, timeout=180)
    fresh_json(output / "transfer.json", {"exit_code": transfer.returncode,
        "process_reaped": True, "derived_cache_only": True})
    if transfer.returncode or file_hash(output / "rows.f64") != report["header"]["sha256"]:
        raise ValueError("derived cache transfer failed")
    fresh_json(output / "header.json", report["header"])
    return cache_record(output, session)


def study(root, spec_path, preflight_path, canary_path, env_file, tokenizer_cache):
    root = Path(root).resolve()
    spec_path = Path(spec_path).resolve()
    with (ROOT / "artifacts/historical-ingest-controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if root.exists():
            raise ValueError("permanent study ID already used")
        spec = validate_spec(load_json(spec_path))
        if root.name != spec["experiment_id"]:
            raise ValueError("output directory must match permanent experiment ID")
        pub = publication(spec_path)
        canary = load_json(canary_path)
        if (not canary["passed"] or canary["source_hashes"] != pub["source_hashes"]
                or canary["actual_tinker_calls"] != 0
                or canary["codex_sha256"] != file_hash(harness.CODEX)
                or canary["python_sha256"] != file_hash(sys.executable)):
            raise ValueError("same-source/runtime zero-paid controller canary required")
        receipts = preflight_receipts(spec_path, preflight_path, spec)
        for package, version in {"numpy": "1.26.4", "scipy": "1.14.0",
                                 "scikit-learn": "1.6.1", "tinker": "0.25.0"}.items():
            if importlib.metadata.version(package) != version:
                raise ValueError("pinned runtime differs: " + package)
        if file_hash(BUDGET / "authorization.json") != AUTH:
            raise ValueError("original authorization changed")
        budget = PaidBudget(BUDGET)
        before = budget.snapshot()
        if money(before["cap_usd"]) != money(200) or any(
                value["state"] == "dispatched" and "-turn-" in key
                for key, value in before["jobs"].items()):
            raise ValueError("budget or active provider dispatch gate")
        if min(money(before["available_usd"]),
               money(before["buckets"]["learning"]["available_usd"])) < 3 * UPPER:
            raise ValueError("first three-arm atomic round does not fit")
        contract = load_json(CONTRACT_SOURCE)["spec"]["contract"]
        if digest(contract) != spec["fixed_contract"]["target_contract_sha256"]:
            raise ValueError("target contract differs")
        root.mkdir(parents=True)
        (root / "data").mkdir()
        fresh_json(root / "pre-score-lock.json", {
            "spec": spec, "spec_sha256": file_hash(spec_path),
            "canonical_spec_sha256": digest(spec), "source_hashes": pub["source_hashes"],
            "source_preflight_sha256": file_hash(preflight_path), "final_opened": False,
        })
        fresh_json(root / "claim.json", {
            "publication": pub, "canary_sha256": file_hash(canary_path),
            "nonce": secrets.token_hex(16), "pid": os.getpid(),
            "original_authorization_sha256": AUTH, "budget_before": before,
            "session_cap_usd": str(UPPER),
            "actual_admission": "each next three-arm controller block must fit remaining learning budget",
            "final_selection": "Round 8 submissions; no hindsight best selection",
        })
        train = [materialize(root, row, "initial_train", receipts[row["session"]], contract)
                 for row in spec["initial_train"]]
        from dotenv import dotenv_values
        backend = TinkerGLMBackend(dotenv_values(env_file).get("TINKER_API_KEY"), tokenizer_cache)
        histories = {arm: [] for arm in EXPERIMENT_ARMS}
        costs = {arm: [] for arm in EXPERIMENT_ARMS}
        last_models = {}
        last_commitments = []
        try:
            for round_number, dev_row in enumerate(spec["dev"], 1):
                if hashes(spec_path) != pub["source_hashes"]:
                    raise ValueError("study source mutated")
                now = budget.snapshot()
                if min(money(now["available_usd"]),
                       money(now["buckets"]["learning"]["available_usd"])) < 3 * UPPER:
                    raise ValueError("next three-arm round exceeds remaining budget")
                round_dir = root / f"round-{round_number}"
                round_dir.mkdir()
                baseline = run_worker({"plan": BASE, "train": train[:-1], "check": train[-1:]},
                                      round_dir / "common-baseline-check")
                if not baseline["success"]:
                    raise ValueError("common baseline infrastructure failed")
                sessions = {}
                commitments = []
                shift = (round_number - 1) % len(EXPERIMENT_ARMS)
                order = EXPERIMENT_ARMS[shift:] + EXPERIMENT_ARMS[:shift]
                for arm in order:
                    session = root / (root.name + "-" + arm + f"-r{round_number:02d}")
                    manifest = workspace(session, train, baseline, histories[arm],
                        round_number, arm, spec["rounds"], pub["source_hashes"])
                    fresh_json(session / "dispatch-claim.json", {
                        "manifest_sha256": manifest, "publication": pub,
                        "canary_sha256": file_hash(canary_path),
                        "session_upper_not_spend": str(UPPER), "nonce": secrets.token_hex(16),
                    })
                    print(canonical({"stage": "controller_started", "round": round_number,
                                     "arm": arm, "path": str(session)}), flush=True)
                    run_session(session, backend, budget)
                    costs[arm].append(arm_cost(budget.snapshot(), session.name))
                    fresh_json(session / "cost.json", costs[arm][-1])
                    submission = load_json(session / "submission.json")
                    sessions[arm] = session
                    commitments.append({"path": str(session / "submission.json"),
                                        "sha256": file_hash(session / "submission.json")})
                    print(canonical({"stage": "controller_complete", "round": round_number,
                        "arm": arm, "trial": submission["trial_id"],
                        "cost": costs[arm][-1]}), flush=True)
                for arm, session in sessions.items():
                    chosen = load_json(session / "submission.json")["plan"]
                    fitted = run_worker({"plan": chosen, "train": train, "check": []},
                                        round_dir / (arm + "-refit"))
                    if not fitted["success"]:
                        raise ValueError("selected refit failed")
                    last_models[arm] = round_dir / (arm + "-refit")
                common = run_worker({"plan": BASE, "train": train, "check": []},
                                    round_dir / "common-baseline-refit")
                if not common["success"]:
                    raise ValueError("baseline refit failed")
                last_models["baseline"] = round_dir / "common-baseline-refit"
                canonical_commitments = sorted(commitments, key=lambda item: item["path"])
                fresh_json(round_dir / "paired-freeze.json", {
                    "commitments": canonical_commitments,
                    "models": {arm: file_hash(path / "model.pkl")
                               for arm, path in last_models.items()},
                })
                dev = materialize(root, dev_row, "dev", receipts[dev_row["session"]],
                                  contract, canonical_commitments, spec)
                scores = {}
                for arm, directory in last_models.items():
                    with (directory / "model.pkl").open("rb") as stream:
                        model = pickle.load(stream)
                    scores[arm] = evaluate(model, dev,
                        round_dir / (arm + "-dev-predictions.npy"))
                fresh_json(round_dir / "dev-scores.json", scores)
                for arm, session in sessions.items():
                    histories[arm].append({
                        "round": round_number,
                        "records": Broker(session, file_hash(session / "config.json")).records(),
                        "submission": load_json(session / "submission.json"),
                        "own_dev": {key: value for key, value in scores[arm].items()
                                    if key != "market_scores"},
                        "common_baseline_dev": {key: value for key, value in scores["baseline"].items()
                                                if key != "market_scores"},
                        "cost": costs[arm][-1],
                    })
                fresh_json(round_dir / "promotion-to-train.json", {
                    "dev": dev, "commitments": canonical_commitments, "consumed": True,
                })
                train.append(dev)
                last_commitments = canonical_commitments
                print(canonical({"stage": "round_complete", "round": round_number,
                    "dev_session": dev_row["session"],
                    "mse": {arm: score["candidate_mse"] for arm, score in scores.items()}}),
                    flush=True)
            fresh_json(root / "final-model-freeze.json", {
                "commitments": last_commitments,
                "models": {arm: file_hash(path / "model.pkl") for arm, path in last_models.items()},
                "source_hashes": pub["source_hashes"],
                "selection": "Round 8 submissions; no further model dispatch",
                "final_manifest_commitment": digest(spec["final"]),
            })
            final_scores = []
            for row in spec["final"]:
                record = materialize(root, row, "final", receipts[row["session"]],
                                     contract, last_commitments, spec)
                scores = {}
                for arm, directory in last_models.items():
                    with (directory / "model.pkl").open("rb") as stream:
                        model = pickle.load(stream)
                    scores[arm] = evaluate(model, record,
                        root / (arm + "-final-" + row["session"] + ".npy"))
                fresh_json(root / ("final-" + row["session"] + ".json"), scores)
                final_scores.append(scores)
                print(canonical({"stage": "final_session_complete", "session": row["session"],
                    "completed": len(final_scores), "total": len(spec["final"])}), flush=True)
            metrics = summarize(final_scores)
            after = budget.snapshot()
            report = {
                "complete": True, "rounds": spec["rounds"], "metrics": metrics,
                "costs": costs, "budget_after": {key: value for key, value in after.items()
                                                  if key != "jobs"},
                "publication": pub, "formal_promotion": False, "pnl_measured": False,
                "source_unchanged": hashes(spec_path) == pub["source_hashes"],
            }
            fresh_json(root / "complete.json", report)
            print(canonical(report), flush=True)
        except BaseException as error:
            fresh_json(root / "failure.json", {
                "type": type(error).__name__, "message": str(error)[:800],
                "budget_after": budget.snapshot(), "no_automatic_retry": True,
                "partial_outcomes_preserved": True,
            })
            raise


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
