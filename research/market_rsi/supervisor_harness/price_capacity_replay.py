"""Bounded JSON-only capacity calls; no training, account call or activation.

Use reviewed pure apply(context) modules in fresh processes, never root imports.
Static admission/resource sampling is not arbitrary-code OS containment.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from supervisor_harness import price_capacity_source as guard


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def read(binding, *, runtime=False):
    path = Path(binding["path"])
    if (set(binding) != {"path", "sha256"} or not path.is_absolute() or not path.is_file()
            or not runtime and path.resolve() != path):
        raise ValueError("canonical exact capacity binding required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding["sha256"]:
        raise ValueError("capacity artifact/source drift")
    return data


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    return pin(path)


def invoke(source, python, context, directory, *, seconds, rss_bytes, input_bytes=1048576):
    """Once-only measured child; failures returned, diagnostics reaped and saved."""
    guard.validate_source(read(source).decode())
    read(python, runtime=True)
    raw = json.dumps(context, sort_keys=True, allow_nan=False).encode()
    if (type(context) is not dict or len(raw) > input_bytes
            or type(seconds) not in {int, float} or not 0 < seconds <= 900
            or type(rss_bytes) is not int or not 0 < rss_bytes <= 1073741824):
        raise ValueError("bounded aggregate context and resources required")
    directory = Path(directory)
    if not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError("canonical child artifact directory required")
    directory.mkdir()  # Existing execution is never automatically repeated.
    request = {"source": source, "context": context, "adapter": pin(Path(__file__).resolve()),
               "guard": pin(Path(guard.__file__).resolve())}
    request_binding = save(directory / "request.json", request)
    output_path = directory / "output.json"
    # -I/-S prevent ambient site, user modules and implicit project imports.
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('supervisor_harness.price_capacity_replay',run_name='__main__')"
    command = [str(Path(python["path"]).resolve()), "-I", "-S", "-B", "-c", bootstrap,
               str(Path(__file__).resolve().parent.parent), str(directory / "request.json"), str(output_path)]
    environment = {"PATH": "/usr/bin:/bin", **{key: "1" for key in
        ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}}
    start, peak, stopped, error, child, status = time.monotonic(), None, None, None, None, None
    try:
        with (directory / "stdout").open("xb") as stdout, (directory / "stderr").open("xb") as stderr:
            child = subprocess.Popen(command, cwd=directory, env=environment, stdout=stdout,
                                     stderr=stderr, start_new_session=True)
            try:
                from supervisor_harness.opened_train_discovery_worker import sample_rss
                while child.poll() is None:
                    sample = 1024 * sample_rss(child)
                    if sample > 0: peak = max(peak or 0, sample)
                    if time.monotonic() - start > seconds: stopped = "timeout"
                    elif peak is not None and peak > rss_bytes: stopped = "sampled_rss_cap"
                    elif sum((directory / name).stat().st_size for name in ("stdout", "stderr")) > 1048576:
                        stopped = "output_cap"
                    if stopped: break
                    time.sleep(.01)
            finally:
                if child.poll() is None:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                status = child.wait(timeout=5)
    except BaseException as diagnostic:
        error = diagnostic
    output = None
    if status == 0 and stopped is None and error is None:
        try:
            if output_path.stat().st_size > 65536: raise ValueError("bounded JSON advice output required")
            output = json.loads(output_path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("finite JSON required")))
            if type(output) is not dict: raise ValueError("apply must return JSON object")
            read(source)
        except Exception as diagnostic:
            error = diagnostic
    receipt = {"request": request_binding, "source": source, "python": python, "command": command,
        "exit_code": status, "stop_reason": stopped, "wall_seconds": time.monotonic() - start,
        "sampled_peak_rss_bytes": peak if error is None else None, "error_type": type(error).__name__ if error else None,
        "pid": child.pid if child else None, "process_reaped": child is None or child.poll() is not None,
        "succeeded": status == 0 and stopped is None and error is None,
        "output": pin(output_path) if output is not None else None,
        "stdout": pin(directory / "stdout"), "stderr": pin(directory / "stderr"),
        "limits": {"seconds": seconds, "rss_bytes": rss_bytes, "input_bytes": input_bytes},
        "train_fits": 0, "account_calls": 0, "automatic_retry": False,
        "arbitrary_code_containment_claim": False}
    binding = save(directory / "receipt.json", receipt)
    if isinstance(error, (KeyboardInterrupt, SystemExit)): raise error
    return {"receipt": binding, "output": output, "succeeded": receipt["succeeded"]}


def main():
    import sys
    request = json.loads(Path(sys.argv[1]).read_text())
    read(request["adapter"]); read(request["guard"])
    source = read(request["source"]).decode()
    guard.validate_source(source)
    namespace = {"__name__": "reviewed_capacity"}
    exec(compile(source, request["source"]["path"], "exec"), namespace)
    output = namespace["apply"](request["context"])
    if type(output) is not dict: raise ValueError("apply must return JSON object")
    save(Path(sys.argv[2]), output)


if __name__ == "__main__":
    main()
