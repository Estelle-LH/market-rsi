"""Untrusted one-row probability candidate entry point for local Docker.

This file is mounted read-only beside one candidate source file.  It receives
only one already-public row per JSON line and emits one exact probability
submission.  The trusted host owns sequencing, durability, cleanup and every
score.  This guest's self-checks are defense in depth, not isolation evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import socket
import sys
from pathlib import Path
from typing import Any


PUBLIC_ROW_SCHEMA = "minimal_prediction_public_as_of_row_v1"
PREDICTION_SCHEMA = "minimal_prediction_submission_v1"
PUBLIC_RELEASE_FIELDS = {
    "schema", "run_id", "sequence", "row_id", "event_id", "market_id",
    "cutoff_ms", "feature_available_ms", "market_probability",
}
PREDICTION_SUBMISSION_FIELDS = {
    "schema", "run_id", "sequence", "row_id", "probability",
}
ALLOWED_ENVIRONMENT = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "HOME": "/nonexistent",
    "PYTHONHASHSEED": "0",
    "PYTHONDONTWRITEBYTECODE": "1",
}
MAX_REQUEST_BYTES = 64 * 1024
PROBABILITY_EPSILON = 1e-6


def _strict_object(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    def constant(_value: str) -> Any:
        raise ValueError("non-finite JSON number")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("strict UTF-8 JSON object required") from error
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular mounted source required")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probability(value: Any) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("finite numeric probability required")
    result = float(value)
    if not PROBABILITY_EPSILON <= result <= 1 - PROBABILITY_EPSILON:
        raise ValueError("probability violates frozen endpoint policy")
    return result


def _validate_runtime(guest: Path, candidate: Path, *, guest_sha256: str,
                      candidate_sha256: str) -> None:
    if sys.platform != "linux" or os.geteuid() != 65534 or os.getegid() != 65534:
        raise RuntimeError("exact unprivileged Linux identity required")
    if os.getgroups():
        raise RuntimeError("supplementary groups forbidden")
    if set(os.environ.items()) != set(ALLOWED_ENVIRONMENT.items()):
        raise RuntimeError("candidate environment differs from exact allowlist")
    if "NoNewPrivs:\t1" not in Path("/proc/self/status").read_text():
        raise RuntimeError("no-new-privileges required")
    if {name for _, name in socket.if_nameindex()} != {"lo"}:
        raise RuntimeError("network namespace is not isolated")
    if _sha256(guest) != guest_sha256 or _sha256(candidate) != candidate_sha256:
        raise RuntimeError("mounted source commitment mismatch")


def _load_candidate(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("market_rsi_candidate", path)
    if spec is None or spec.loader is None:
        raise ValueError("candidate source cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    predict = getattr(module, "predict", None)
    if not callable(predict):
        raise ValueError("candidate must define predict(public_row)")
    return predict


def run(candidate_path: Path, *, candidate_sha256: str,
        guest_sha256: str) -> None:
    guest_path = Path(__file__).resolve()
    candidate_path = Path(candidate_path)
    _validate_runtime(guest_path, candidate_path, guest_sha256=guest_sha256,
                      candidate_sha256=candidate_sha256)
    predict = _load_candidate(candidate_path)
    while True:
        raw = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
        if not raw:
            return
        if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            raise ValueError("bounded complete request line required")
        release = _strict_object(raw[:-1])
        if set(release) != PUBLIC_RELEASE_FIELDS:
            raise ValueError("exact public-row schema required")
        if (release["schema"] != PUBLIC_ROW_SCHEMA
                or type(release["sequence"]) is not int
                or release["sequence"] < 0):
            raise ValueError("invalid public-row identity")
        public_row = dict(release)
        probability = _probability(predict(public_row))
        response = {
            "schema": PREDICTION_SCHEMA,
            "run_id": release["run_id"],
            "sequence": release["sequence"],
            "row_id": release["row_id"],
            "probability": probability,
        }
        if set(response) != PREDICTION_SUBMISSION_FIELDS:
            raise AssertionError("internal response schema mismatch")
        print(json.dumps(response, sort_keys=True, separators=(",", ":"),
                         allow_nan=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--guest-sha256", required=True)
    args = parser.parse_args()
    run(args.candidate, candidate_sha256=args.candidate_sha256,
        guest_sha256=args.guest_sha256)


if __name__ == "__main__":
    main()
