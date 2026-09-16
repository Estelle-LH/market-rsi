"""Memory-policy broker with explicit candidate and production fit envelopes."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "audit_tools")]

from market_rsi import file_hash, fresh_json, load_json
from memory_pilot import broker as runtime_base
import memory_policy.broker as policy_base


TRIAL_MAX_RSS_GIB = 6
TRIAL_TIMEOUT_SECONDS = 480
REFIT_MAX_RSS_GIB = 8
REFIT_TIMEOUT_SECONDS = 600


def run_worker_bounded(request, directory, *, max_rss_gib, timeout_seconds):
    """Run one exact fit without subsampling under a declared resource envelope."""
    if (type(max_rss_gib) is not int or max_rss_gib <= 0
            or type(timeout_seconds) is not int or timeout_seconds <= 0):
        raise ValueError("positive integer worker bounds required")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    fresh_json(directory / "request.json", request)
    command = [
        sys.executable,
        str(ROOT / "memory_pilot/learning.py"),
        "--request", str(directory / "request.json"),
        "--output", str(directory),
    ]
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    with (directory / "stdout.log").open("x") as stdout, (
            directory / "stderr.log").open("x") as stderr:
        process = subprocess.Popen(
            command, stdout=stdout, stderr=stderr, env=environment,
            start_new_session=True,
        )
        fresh_json(directory / "process.json", {
            "pid": process.pid,
            "args": command,
            "environment_keys": sorted(environment),
            "max_rss_gib": max_rss_gib,
            "timeout_seconds": timeout_seconds,
            "no_subsampling": True,
        })
        failure = None
        peak_rss_kib = 0
        start = time.monotonic()
        try:
            while process.poll() is None:
                rss = subprocess.run(
                    ["ps", "-p", str(process.pid), "-o", "rss="],
                    capture_output=True, text=True, timeout=3,
                ).stdout.strip()
                peak_rss_kib = max(
                    peak_rss_kib, int(rss) if rss.isdigit() else 0)
                if peak_rss_kib > max_rss_gib * 1024**2:
                    raise MemoryError(
                        f"trainer RSS exceeds {max_rss_gib} GiB; no silent subsampling")
                if time.monotonic() - start > timeout_seconds:
                    raise TimeoutError(
                        f"trainer exceeded {timeout_seconds} seconds")
                time.sleep(0.5)
            if process.returncode:
                raise RuntimeError(
                    "trainer exited unsuccessfully; see preserved stderr")
        except BaseException as error:
            failure = {"type": type(error).__name__,
                       "message": str(error)[:500]}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            fresh_json(directory / "cleanup.json", {
                "pid": process.pid,
                "exit_code": process.returncode,
                "process_reaped": True,
                "peak_rss_kib": peak_rss_kib,
                "max_rss_gib": max_rss_gib,
                "timeout_seconds": timeout_seconds,
            })
        if failure:
            fresh_json(directory / "failure.json", failure)
            return {"success": False, "failure": failure,
                    "result_sha256": file_hash(directory / "failure.json")}
    result = load_json(directory / "result.json")
    public = {
        **result,
        "scores": [
            {key: value for key, value in score.items()
             if key != "market_scores"}
            for score in result["scores"]
        ],
    }
    return {"success": True, "result": public,
            "result_sha256": file_hash(directory / "result.json")}


def trial_worker(request, directory):
    return run_worker_bounded(
        request, directory, max_rss_gib=TRIAL_MAX_RSS_GIB,
        timeout_seconds=TRIAL_TIMEOUT_SECONDS)


def refit_worker(request, directory):
    return run_worker_bounded(
        request, directory, max_rss_gib=REFIT_MAX_RSS_GIB,
        timeout_seconds=REFIT_TIMEOUT_SECONDS)


class Broker(policy_base.Broker):
    def _call(self, name, arguments, records):
        # The v1 Broker resolves its worker from its own module. Scope the
        # replacement to this call so importing v3 cannot change older runners.
        original = runtime_base.run_worker
        runtime_base.run_worker = trial_worker
        try:
            result = super()._call(name, arguments, records)
        finally:
            runtime_base.run_worker = original
        if name == "inspect_experiment":
            result["library"].update({
                "cpu_seconds_per_fit": TRIAL_TIMEOUT_SECONDS,
                "max_fit_rss_gib": TRIAL_MAX_RSS_GIB,
                "mandatory_refit_cpu_seconds": REFIT_TIMEOUT_SECONDS,
                "mandatory_refit_max_rss_gib": REFIT_MAX_RSS_GIB,
                "max_cumulative_selected_observations": 10_000_000,
                "max_fit_rows": 12_000_000,
                "no_silent_subsampling": True,
            })
        return result


ALLOWED = policy_base.ALLOWED
INSTRUCTIONS = policy_base.INSTRUCTIONS
TOOLS = policy_base.TOOLS


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    runtime_base.serve(Broker(args.workspace, args.manifest_sha256))
