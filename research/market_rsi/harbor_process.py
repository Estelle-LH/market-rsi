"""Bound the trusted local Harbor owner; remote cleanup still needs evidence.

Live admission is closed. This new path does not alter the completed cloud
fixture or installed SDK. Its isolated process disables SDK connection retries
explicitly before import, preserving all outcomes without another create call.
"""
import asyncio
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import development_harbor as development
from bounded_process import run_bounded_process
from market_rsi import canonical, digest, file_hash, fresh_json
from worker_receipts import read_regular


WALL_SECONDS, REAP_SECONDS = 270, 2
SOURCES = ("harbor_process.py", "harbor_process_worker.py", "development_harbor.py", "bounded_process.py", "market_harbor.py")
SCOPED_ENV = "scoped-process-env"


def source_hashes():
    return {name: file_hash(Path(__file__).with_name(name)) for name in SOURCES}


def read_context(root):
    root = Path(root).absolute()
    data = json.loads(read_regular(root / "harbor-process/input.bin"))
    if (set(data) != {"root", "budget_path", "deadline_utc", "claim_sha256", "source_hashes",
                     "local_wall_seconds", "sdk_connection_retries"}
            or data["root"] != str(root) or data["source_hashes"] != source_hashes()
            or data["local_wall_seconds"] != WALL_SECONDS or data["sdk_connection_retries"] != 0):
        raise ValueError("exact bounded Harbor context required")
    claim = development.verify_job(root)[0]
    if digest(claim) != data["claim_sha256"]:
        raise ValueError("Harbor process belongs to a different execution claim")
    deadline = datetime.fromisoformat(data["deadline_utc"])
    if deadline.tzinfo is None or deadline.utcoffset().total_seconds() != 0:
        raise ValueError("UTC deadline required")
    return data


def require_create_window(root):
    data = read_context(root)
    # Preserve the fixed cloud TTL. Do not shorten the scientific execution
    # condition just to squeeze another job past the reporting deadline.
    deadline = datetime.fromisoformat(data["deadline_utc"]).timestamp()
    if time.time() + 15 + development.TTL + 15 > deadline:
        raise TimeoutError("new sandbox's full lifetime and cleanup do not fit")
    return data


class DeadlineDevelopmentE2B(development.DevelopmentE2B):
    def _paid_key(self):
        if str(self.env_file) != SCOPED_ENV:
            raise ValueError("bounded Harbor child cannot read a provider env file")
        return os.environ.get("RSI_E2B_API_KEY")

    async def start(self, force_build):
        data = require_create_window(self.control_root)
        if Path(self.budget_path).absolute() != Path(data["budget_path"]).absolute():
            raise ValueError("child budget differs from its bound process context")
        await super().start(force_build)
        actual = json.loads(read_regular(self.control_root / "runtime.json"))
        if datetime.fromisoformat(actual["expiry_at"]) > datetime.fromisoformat(data["deadline_utc"]):
            raise ValueError("actual sandbox expiry exceeds the authorized deadline")
        fresh_json(self.control_root / "deadline-check.json", {"deadline_utc": data["deadline_utc"],
            "sandbox_id": actual["sandbox_id"], "expiry_at": actual["expiry_at"], "passed": True})


async def run_child(root):
    development.require_admission(root)
    data = require_create_window(root)
    import e2b.api
    if e2b.api.connection_retries != 0 or os.environ.get("E2B_CONNECTION_RETRIES") != "0":
        raise ValueError("SDK retry setting was not frozen before import")
    root = Path(root).absolute()
    config = development.trial_config(root, data["budget_path"], SCOPED_ENV)
    config.environment.import_path = "harbor_process:DeadlineDevelopmentE2B"
    fresh_json(root / "harbor-config.json", config.model_dump(mode="json"))
    fresh_json(root / "sdk-retry-profile.json", {"connection_retries": 0,
        "note": "No installed SDK edit; explicit process environment before SDK import."})
    trial = None
    try:
        trial = await development.Trial.create(config)
        result = await asyncio.wait_for(trial.run(), timeout=235)
        if result.exception_info is not None:
            raise ValueError("Harbor development failed; no retry")
        assessment = development.verify_outputs(root)
        fresh_json(root / "assessment.json", assessment)
    except Exception as error:
        fresh_json(root / "failure.json", {"error_type": type(error).__name__, "automatic_retry": False, "scored": False})
        raise
    finally:
        if trial is not None and trial.agent_environment._sandbox is not None:
            await asyncio.shield(trial.agent_environment.stop(delete=True))


def run_bounded_development(root, budget_path, env_file, *, deadline_utc):
    development.require_admission(root)  # Before credentials, claim creation or child process.
    root = Path(root).absolute()
    claim = development.verify_job(root)[0]
    deadline = datetime.fromisoformat(deadline_utc)
    if (deadline.tzinfo is None or deadline.utcoffset().total_seconds() != 0
            or time.time() + WALL_SECONDS + REAP_SECONDS > deadline.timestamp()):
        raise TimeoutError("entire local Harbor allowance does not fit the authorized window")
    from dotenv import dotenv_values
    key = dotenv_values(env_file).get("E2B_API_KEY")
    if not key:
        raise ValueError("scoped E2B credential missing before process creation")
    request = {"root": str(root), "budget_path": str(Path(budget_path).absolute()), "deadline_utc": deadline_utc,
        "claim_sha256": digest(claim), "source_hashes": source_hashes(), "local_wall_seconds": WALL_SECONDS,
        "sdk_connection_retries": 0}
    receipt = run_bounded_process([sys.executable, "-I", str(Path(__file__).with_name("harbor_process_worker.py"))],
        canonical(request).encode(), {"PATH": os.defpath, "LANG": "C.UTF-8",
            "E2B_CONNECTION_RETRIES": "0", "RSI_E2B_API_KEY": key}, root / "harbor-process", wall_seconds=WALL_SECONDS)
    if (receipt["failure"] is not None or receipt["process_reaped"] is not True or receipt["exit_code"] != 0
            or receipt["input_complete"] is not True):
        raise RuntimeError("local Harbor owner failed; reconcile exact sandbox/hold, never create a replacement")
    return receipt


def verify_process_receipts(root, reads, *, succeeded):
    """Local exit plus separate exact cloud cleanup, never local-exit-as-cleanup."""
    root = Path(root).absolute()
    data = read_context(root)
    directory = root / "harbor-process"
    claim, receipt = reads.read(directory / "claim.json"), reads.read(directory / "receipt.json")
    for name in ("input", "stdout", "stderr"):
        path = directory / (name + ".bin")
        raw = read_regular(path)
        sha = hashlib.sha256(raw).hexdigest()
        reads.files[str(path)] = sha
        expected_sha = claim["input_sha256"] if name == "input" else receipt[name + "_sha256"]
        if sha != expected_sha:
            raise ValueError("bounded Harbor process input/output changed")
        if name == "input" and (raw != canonical(data).encode() or receipt.get("input_bytes_written") != len(raw)):
            raise ValueError("bounded Harbor input is incomplete or changed")
        if name != "input" and (len(raw) != receipt.get(name + "_bytes")
                                or len(raw) > claim["max_" + name + "_bytes"]):
            raise ValueError("bounded Harbor output length changed")
    if (claim["command_sha256"] != digest([sys.executable, "-I", str(Path(__file__).with_name("harbor_process_worker.py"))])
            or claim["environment_names"] != sorted(["PATH", "LANG", "E2B_CONNECTION_RETRIES", "RSI_E2B_API_KEY"])
            or claim["wall_seconds"] != WALL_SECONDS or claim["reap_seconds"] != REAP_SECONDS
            or claim["max_stdout_bytes"] != 16 * 1024 * 1024 or claim["max_stderr_bytes"] != 256 * 1024
            or claim["supervisor_source_sha256"] != file_hash(Path(__file__).with_name("bounded_process.py"))
            or claim["remote_cancellation_established"] is not False
            or receipt["process_reaped"] is not True or receipt["input_complete"] is not True
            or type(receipt["pid"]) is not int or receipt["pid"] <= 0
            or type(receipt["elapsed_seconds"]) not in (int, float) or not math.isfinite(receipt["elapsed_seconds"])
            or not 0 <= receipt["elapsed_seconds"] <= WALL_SECONDS + REAP_SECONDS
            or receipt["failure"] is not None or receipt["output_complete"] is not True
            or receipt["exit_code"] != (0 if succeeded else 1)
            or receipt["remote_request_terminal"] is not None
            or receipt["remote_cancellation_established"] is not False or receipt["unused_budget_released"] is not False):
        raise ValueError("bounded Harbor process completion is unverified")
    profile = reads.read(root / "sdk-retry-profile.json")
    deadline_check = reads.read(root / "deadline-check.json")
    runtime = reads.read(root / "runtime.json")
    if (profile["connection_retries"] != 0 or deadline_check != {"deadline_utc": data["deadline_utc"],
            "sandbox_id": runtime["sandbox_id"], "expiry_at": runtime["expiry_at"], "passed": True}
            or datetime.fromisoformat(runtime["expiry_at"]) > datetime.fromisoformat(data["deadline_utc"])):
        raise ValueError("SDK retry or actual cloud expiry check missing")
