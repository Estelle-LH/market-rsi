"""Unprivileged, one-request inspection endpoint; only inside isolated E2B.

Its output remains a candidate-authored diagnostic, never a trusted score.
Complete Train and label-free public Dev may be inspected. Dev labels and
hidden Test are never mounted.
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
            raise RuntimeError("provider key in inspection environment")
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    line = sys.stdin.buffer.readline(8 * 1024 * 1024 + 1)
    if not line.endswith(b"\n") or len(line) > 8 * 1024 * 1024:
        raise ValueError("incomplete or oversized inspection request")
    request = json.loads(line)
    if set(request) != {"type", "request_id", "train", "dev", "feature_names"} or request["type"] != "inspect":
        raise ValueError("unexpected inspection input fields")
    spec = importlib.util.spec_from_file_location("candidate", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    diagnostic = module.inspect(request["train"], request["dev"], request["feature_names"])
    print(json.dumps({"type": "inspection", "request_id": request["request_id"],
                      "diagnostic": diagnostic}, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
