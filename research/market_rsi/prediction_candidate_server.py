"""Unprivileged candidate endpoint. Run only through the E2B runner launcher.

The root-owned runner withholds future feature rows and all evaluation labels.
This process cannot be trusted to grade itself: candidate code may alter any of
its own state or stdout. The parent independently validates and commits output.
"""
import importlib.util
import json
import os
import resource
import socket
import sys
from pathlib import Path


def main():
    if sys.platform != "linux" or os.geteuid() != 65534 or os.getgroups():
        raise RuntimeError("unprivileged sandbox required")
    if set(name for _, name in socket.if_nameindex()) != {"lo"}:
        raise RuntimeError("isolated network namespace required")
    if "NoNewPrivs:\t1" not in Path("/proc/self/status").read_text():
        raise RuntimeError("no-new-privileges required")
    for name in ("TINKER_API_KEY", "E2B_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if os.environ.get(name):
            raise RuntimeError("provider key present in candidate environment")
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    spec = importlib.util.spec_from_file_location("candidate", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fitted, model = False, None
    while True:
        line = sys.stdin.buffer.readline(8 * 1024 * 1024 + 1)
        if not line:
            return
        if not line.endswith(b"\n") or len(line) > 8 * 1024 * 1024:
            raise ValueError("request too large or incomplete")
        request = json.loads(line)
        if request["type"] == "fit" and not fitted:
            model = module.fit(request["train"], request["features"])
            fitted = True
            response = {"type": "fitted", "request_id": request["request_id"]}
        elif request["type"] == "predict" and fitted:
            prediction = module.predict(model, request["row"])
            response = {"type": "prediction", "request_id": request["request_id"],
                        "row_id": request["row"]["row_id"], "prediction": prediction}
        else:
            raise ValueError("invalid fit/predict order")
        print(json.dumps(response, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
