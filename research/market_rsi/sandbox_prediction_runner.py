"""Trusted root-side sequential runner. Refuses execution outside Linux/root.

Deployed only by market_harbor.py into a fresh E2B sandbox. Complete future
feature inputs stay root-private; no evaluation labels are uploaded at all.
This module returns execution receipts, never market scores.
"""
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


PRIVATE = Path("/root/market-rsi-private")
PUBLIC = Path("/tmp/market-rsi-public")


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_layout():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("trusted runner requires Linux root inside E2B, never the Mac")
    for path, mode in ((PRIVATE, 0o700), (PUBLIC, 0o755)):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError("unsafe sandbox directory ownership/mode")
    for path in PRIVATE.iterdir():
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
            raise ValueError("private inputs/code readable by candidate")
    for name in ("candidate.py", "prediction_candidate_server.py", "isolation_probe.py"):
        p = PUBLIC / name
        info = p.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o444:
            raise ValueError("public code is not root-owned read-only")


def save(path, value):
    with Path(path).open("x") as f:
        f.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    require_layout()
    # -I removes script-directory imports. Add only the checked root-private dir.
    sys.path.insert(0, str(PRIVATE))
    from prediction_stream import (PredictionJournal, fingerprint, linux_candidate_command,
                                   predict_stream, validate_rows)
    from diagnostic_channel import DiagnosticLineChannel
    packet = json.loads((PRIVATE / "packet.json").read_text())
    claim = json.loads((PRIVATE / "input-claim.json").read_text())
    if fingerprint(packet) != claim["packet_sha256"]:
        raise ValueError("sandbox input packet changed")
    if set(packet) != {"train", "evaluation", "feature_names", "limits"}:
        raise ValueError("unexpected input fields; no evaluation labels allowed")
    validate_rows(packet["train"], packet["evaluation"], packet["feature_names"])
    for rel, sha in claim["deployed_hashes"].items():
        path = (PRIVATE if rel.startswith("private/") else PUBLIC) / rel.split("/", 1)[1]
        if file_sha(path) != sha:
            raise ValueError("sandbox source hash mismatch")
    probe_command = linux_candidate_command(PUBLIC / "isolation_probe.py", PUBLIC / "candidate.py")
    probe = subprocess.run(probe_command, cwd=PUBLIC, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                           capture_output=True, text=True, timeout=8)
    isolation = json.loads(probe.stdout) if probe.returncode == 0 else {}
    required = {"unprivileged", "no_groups", "no_new_privileges", "only_loopback", "network_blocked",
                "private_read_denied", "private_write_denied", "public_write_denied", "provider_keys_absent"}
    save(PRIVATE / "isolation.json", {"checks": isolation, "exit_code": probe.returncode,
                                      "probe_sha256": file_sha(PUBLIC / "isolation_probe.py")})
    if set(isolation) != required or any(isolation[k] is not True for k in required):
        raise ValueError("independent pre-import isolation probe failed")
    journal = PredictionJournal(PRIVATE / "predictions", train_sha256=fingerprint(packet["train"]),
        evaluation_sha256=fingerprint(packet["evaluation"]), candidate_sha256=file_sha(PUBLIC / "candidate.py"),
        expected_predictions=len(packet["evaluation"]))
    channel = None
    try:
        channel = DiagnosticLineChannel(
            linux_candidate_command(PUBLIC / "prediction_candidate_server.py",
                                    PUBLIC / "candidate.py"),
            PUBLIC,
            PRIVATE / "candidate-stderr.bin",
        )
        result = predict_stream(channel.exchange, journal.commit, packet["train"], packet["evaluation"],
                                packet["feature_names"], **packet["limits"])
        completed = journal.finish()
        save(PRIVATE / "execution.json", {"stream": result, "complete": completed, "scored": False})
    except Exception as error:
        save(PRIVATE / "failure.json", {"error_type": type(error).__name__, "scored": False})
        raise
    finally:
        if channel is not None:
            try:
                channel.close()
            finally:
                diagnostic = channel.diagnostic()
                save(PRIVATE / "candidate-stderr.json", diagnostic)
                save(PRIVATE / "protocol.json", {"events": channel.events,
                     "candidate_stderr": {key: diagnostic[key] for key in
                         ("origin", "bytes", "sha256", "encoding", "truncated",
                          "independent_diagnosis")},
                     "scored": False})


if __name__ == "__main__":
    main()
