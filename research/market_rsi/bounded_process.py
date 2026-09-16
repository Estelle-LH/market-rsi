"""Bound one trusted local worker process, not remote provider cancellation.

Candidate code must never use this host runner; it belongs in E2B. This helper
owns a new process group, bounded pipes and an exclusive private receipt directory.
The receipt makes no claim that a remote request is terminal or cost-free.
"""
import hashlib
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

from market_rsi import digest, file_hash, fresh_json


def _save(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def run_bounded_process(command, input_bytes, env, directory, *, wall_seconds,
                        max_stdout_bytes=16 * 1024 * 1024, max_stderr_bytes=256 * 1024,
                        reap_seconds=2):
    if (not isinstance(command, list) or not command or any(not isinstance(x, str) for x in command)
            or not isinstance(input_bytes, bytes) or len(input_bytes) > 16 * 1024 * 1024
            or type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds)
            or not 0 < wall_seconds <= 3600 or type(reap_seconds) not in (int, float)
            or not math.isfinite(reap_seconds) or not 0 < reap_seconds <= 5
            or any(type(n) is not int or not 0 < n <= 64 * 1024 * 1024 for n in (max_stdout_bytes, max_stderr_bytes))
            or not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items())):
        raise ValueError("explicit bounded trusted process inputs required")
    directory = Path(directory).absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("private receipt path cannot traverse symlinks")
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    fresh_json(directory / "claim.json", {"command_sha256": digest(command),
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(), "environment_names": sorted(env),
        "wall_seconds": wall_seconds, "reap_seconds": reap_seconds,
        "max_stdout_bytes": max_stdout_bytes, "max_stderr_bytes": max_stderr_bytes,
        "supervisor_source_sha256": file_hash(__file__), "remote_cancellation_established": False})
    # Caller inputs to this helper must not contain credentials; credentials, if
    # needed by a trusted provider worker, travel in its explicitly scoped env.
    _save(directory / "input.bin", input_bytes)
    output = {"stdout": bytearray(), "stderr": bytearray()}
    caps = {"stdout": max_stdout_bytes, "stderr": max_stderr_bytes}
    started, proc, failure, observed, group_killed = time.monotonic(), None, None, {}, False
    offset = 0
    selector = selectors.DefaultSelector()

    def kill_group():
        nonlocal group_killed
        if proc is not None and not group_killed:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            group_killed = True

    try:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=directory, env=env, start_new_session=True, bufsize=0)
        for stream, name, mode in ((proc.stdin, "stdin", selectors.EVENT_WRITE),
                                   (proc.stdout, "stdout", selectors.EVENT_READ), (proc.stderr, "stderr", selectors.EVENT_READ)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, mode, name)
        while selector.get_map():
            remaining = wall_seconds - (time.monotonic() - started)
            if remaining <= 0:
                failure = "local_wall_timeout"
                break
            if proc.poll() is not None:
                kill_group()  # Descendants cannot retain output pipes after the worker exits.
            for key, _ in selector.select(min(.05, remaining)):
                stream, name = key.fileobj, key.data
                if name == "stdin":
                    try:
                        count = os.write(stream.fileno(), input_bytes[offset:offset + 65536]) if offset < len(input_bytes) else 0
                        offset += count
                    except BrokenPipeError:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    if offset >= len(input_bytes):
                        selector.unregister(stream)
                        stream.close()
                    continue
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                observed[name] = observed.get(name, 0) + len(chunk)
                space = caps[name] - len(output[name])
                output[name].extend(chunk[:space])
                if len(chunk) > space:
                    failure = name + "_limit"
                    break
            if failure:
                break
        if failure is None and proc.poll() is None:
            remaining = wall_seconds - (time.monotonic() - started)
            try:
                proc.wait(timeout=max(.001, remaining))
            except subprocess.TimeoutExpired:
                failure = "local_wall_timeout"
    except BaseException as error:
        failure = "local_" + type(error).__name__
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        kill_group()
        if proc is not None:
            try:
                proc.wait(timeout=reap_seconds)
            except subprocess.TimeoutExpired:
                failure = "local_reap_timeout"
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if not stream.closed:
                    stream.close()
        selector.close()
        for name, data in output.items():
            _save(directory / (name + ".bin"), bytes(data))
        receipt = {"pid": proc.pid if proc is not None else None,
            "process_reaped": proc is not None and proc.returncode is not None,
            "exit_code": proc.returncode if proc is not None else None,
            "failure": failure, "elapsed_seconds": time.monotonic() - started,
            "stdout_bytes": len(output["stdout"]), "stderr_bytes": len(output["stderr"]),
            "stdout_sha256": hashlib.sha256(output["stdout"]).hexdigest(),
            "stderr_sha256": hashlib.sha256(output["stderr"]).hexdigest(),
            "output_complete": failure is None, "observed_bytes": observed,
            "input_bytes_written": offset, "input_complete": offset == len(input_bytes),
            "remote_request_terminal": None, "remote_cancellation_established": False,
            "unused_budget_released": False}
        fresh_json(directory / "receipt.json", receipt)
    return receipt
