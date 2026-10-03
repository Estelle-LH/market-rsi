"""Trusted Supervisor binding for reviewed, resident-Train sibling runners.

No arbitrary-code isolation or provider authority. The Supervisor supplies the
reviewed immutable request; candidate metrics remain independently reviewed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

THREADS = {name: "1" for name in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
THREADS["PYTHONHASHSEED"] = "0"
TRAIN = Path("/Users/estelle/Library/Application Support/MarketRSI/"
             "self-evolving-v18-local/artifacts/nfl-2025-train-refresh-20260922-01")
REQUEST_FIELDS = {"attempt_id", "candidate_id", "module", "source_commit",
    "files", "python", "python_sha256", "memory", "memory_sha256",
    "runtime_pair_sha256", "spec_sha256", "max_fits", "max_wall_seconds"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    """Never overwrite prior execution evidence."""
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


def sample_rss(child):
    try:
        return int(subprocess.check_output(["/bin/ps", "-o", "rss=", "-p", str(child.pid)], text=True).strip())
    except (ValueError, subprocess.CalledProcessError):
        if child.poll() is not None:
            return 0
        raise RuntimeError("live child RSS could not be measured")


def validate(request, repo):
    if set(request) != REQUEST_FIELDS:
        raise ValueError("exact reviewed worker request required")
    if not re.fullmatch(r"experiments\.nfl_ingame_[a-z0-9_]+", request["module"]):
        raise ValueError("only reviewed in-game sibling modules admitted")
    for field in ("attempt_id", "candidate_id"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", request[field]):
            raise ValueError("bounded identifier required")
    for field in ("max_fits", "max_wall_seconds"):
        if type(request[field]) is not int or not 1 <= request[field] <= (
                4 if field == "max_fits" else 900):
            raise ValueError("four-fit / 900-second per-attempt ceiling")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if head != request["source_commit"]:
        raise ValueError("source commit drift")
    runner = "research/market_rsi/" + request["module"].replace(".", "/") + ".py"
    if runner not in request["files"] or not request["files"]:
        raise ValueError("runner missing from source commitment")
    for relative, expected in request["files"].items():
        path = Path(repo) / relative
        if (Path(relative).is_absolute() or ".." in Path(relative).parts
                or path.is_symlink() or not path.resolve().is_relative_to(Path(repo).resolve())
                or sha(path) != expected):
            raise ValueError("source file drift or invalid path")
    for field in ("python", "memory"):
        path = Path(request[field])
        if not path.is_absolute() or sha(path) != request[field + "_sha256"]:
            raise ValueError("runtime or memory identity drift")
    return runner


def execute(batch, request, repo):
    """Reserve before spawning; a claimed ID is never automatically retried."""
    runner = validate(request, repo)
    attempt = request["attempt_id"]
    with (batch.root / ".worker.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = batch.snapshot()
        branch = next(item for item in state["branches"] if item["attempt_id"] == attempt)
        if branch["claim_id"] is not None:
            raise RuntimeError("already claimed; inspect/recover without relaunch")
        if branch["candidate_id"] != request["candidate_id"]:
            raise ValueError("candidate differs from selected branch")
        if sum(item["stage"] == "execution_claimed" for item in state["branches"]) >= 2:
            raise RuntimeError("two execution slots already occupied")
        directory = batch.root / "worker"
        directory.mkdir(exist_ok=True)
        reserved = sum(json.loads(path.read_text())["max_fits"]
                       for path in directory.glob("*.request.json"))
        if reserved + request["max_fits"] > 12:
            raise RuntimeError("twelve-fit aggregate reservation ceiling")
        deadline = datetime.fromisoformat(state["deadline_utc"].replace("Z", "+00:00"))
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            batch.stop_if_due(); raise RuntimeError("pilot deadline reached")
        save(directory / f"{attempt}.request.json", request)
        batch.mark_implementation_ready(attempt, runner_sha256=request["files"][runner],
                                        spec_sha256=request["spec_sha256"])
        batch.claim_execution(attempt, claim_id=attempt + "-claim",
            runtime_pair_sha256=request["runtime_pair_sha256"],
            memory_snapshot_sha256=request["memory_sha256"])
    output = batch.root / "runs" / attempt
    output.parent.mkdir(exist_ok=True)
    command = [request["python"], "-B", "-m", request["module"],
               "--source-root", str(TRAIN), "--output", str(output)]
    env = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", **THREADS}
    start = time.monotonic(); outcome = "failed"; code = None; error = None; peak_rss = 0
    child = None
    with (directory / f"{attempt}.stdout").open("xb") as stdout, (
            directory / f"{attempt}.stderr").open("xb") as stderr:
        try:
            child = subprocess.Popen(command, cwd=Path(repo) / "research/market_rsi",
                                     env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            save(directory / f"{attempt}.process.json", {"pid": child.pid,
                 "command": command, "source_commit": request["source_commit"]})
            cutoff = time.monotonic() + min(request["max_wall_seconds"], remaining)
            while True:
                peak_rss = max(peak_rss, sample_rss(child))
                if peak_rss > 1048576:
                    os.killpg(child.pid, 9); code = child.wait(); error = "sampled RSS ceiling"; break
                try:
                    code = child.wait(timeout=min(1.0, max(0.01, cutoff - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= cutoff:
                        os.killpg(child.pid, 9); code = child.wait(); error = "bounded timeout"; break
            if code == 0:
                manifest = json.loads((output / "manifest.json").read_text())
                if (manifest.get("complete") is not True
                        or manifest.get("model_fits") != request["max_fits"]):
                    raise ValueError("incomplete or unexpected fit count")
                for name in ("pre_score_lock", "input_receipts", "exclusions", "predictions", "scorecard"):
                    filename = name + (".csv" if name == "predictions" else ".json")
                    if sha(output / filename) != manifest[name + "_sha256"]:
                        raise ValueError("artifact hash drift")
                outcome = "succeeded"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if child is not None and child.poll() is None:
                os.killpg(child.pid, 9); code = child.wait()
    receipt = {"attempt_id": attempt, "request_sha256": sha(directory / f"{attempt}.request.json"),
        "source_commit": request["source_commit"], "command": command,
        "runtime_pair_sha256": request["runtime_pair_sha256"], "memory_sha256": request["memory_sha256"],
        "outcome": outcome, "exit_code": code, "error": error,
        "wall_seconds": time.monotonic() - start, "fits_reserved": request["max_fits"],
        "sampled_peak_rss_kib": peak_rss, "rss_limit_kib": 1048576,
        "rss_limit_enforcement": "one-second polling; not OS-hard isolation",
        "stdout_sha256": sha(directory / f"{attempt}.stdout"),
        "stderr_sha256": sha(directory / f"{attempt}.stderr"),
        "output": str(output), "metrics_independently_reviewed": False,
        "network_isolation_enforced": False, "provider_calls_requested": 0}
    path = directory / f"{attempt}.receipt.json"; save(path, receipt)
    batch.mark_execution_terminal(attempt, claim_id=attempt + "-claim", outcome=outcome,
                                  execution_receipt_sha256=sha(path))
    return receipt
