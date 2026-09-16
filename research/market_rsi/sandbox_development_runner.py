"""Prospective general E2B runner with preserved candidate-only diagnostics.

The completed canary's original runner/channel remain untouched. This new runner
does not score itself. Its root traceback stays runner-only; the unprivileged
candidate's stderr is separately retained as untrusted evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


PRIVATE = Path("/root/market-rsi-private")
PUBLIC = Path("/tmp/market-rsi-public")
ISOLATION = {"unprivileged", "no_groups", "no_new_privileges", "only_loopback", "network_blocked",
             "private_read_denied", "private_write_denied", "public_write_denied", "provider_keys_absent"}


def save(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_layout():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("development runner requires Linux root in E2B, never the Mac")
    for directory, mode in ((PRIVATE, 0o700), (PUBLIC, 0o755)):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError("unsafe development directory")
        for path in directory.iterdir():
            meta = path.lstat()
            expected = 0o600 if directory == PRIVATE else 0o444
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) != expected:
                raise ValueError("unsafe development file ownership/permissions")


def main():
    require_layout()
    sys.path.insert(0, str(PRIVATE))
    from diagnostic_channel import DiagnosticLineChannel
    from prediction_stream import PredictionJournal, fingerprint, linux_candidate_command, predict_stream, validate_rows
    packet = json.loads((PRIVATE / "packet.json").read_text())
    claim = json.loads((PRIVATE / "input-claim.json").read_text())
    if (set(claim) != {"packet_sha256", "deployed_hashes", "mode"} or claim["mode"] not in {"fit_predict", "inspect"}
            or fingerprint(packet) != claim["packet_sha256"]):
        raise ValueError("exact development input and mode commitments required")
    expected_sources = {"private/prediction_stream.py", "private/diagnostic_channel.py",
                        "private/sandbox_development_runner.py", "public/candidate.py", "public/isolation_probe.py"}
    server = "prediction_candidate_server.py" if claim["mode"] == "fit_predict" else "inspection_candidate_server.py"
    expected_sources.add("public/" + server)
    if claim["mode"] == "inspect":
        expected_sources.add("private/inspection_stream.py")
    if set(claim["deployed_hashes"]) != expected_sources:
        raise ValueError("unexpected deployed source set")
    for name, expected in claim["deployed_hashes"].items():
        directory, filename = name.split("/", 1)
        if sha((PRIVATE if directory == "private" else PUBLIC) / filename) != expected:
            raise ValueError("deployed source changed")
    if claim["mode"] == "fit_predict":
        if set(packet) != {"train", "evaluation", "feature_names", "limits"}:
            raise ValueError("unexpected prediction input fields")
        validate_rows(packet["train"], packet["evaluation"], packet["feature_names"])
    else:
        from inspection_stream import inspect_once, verify_packet
        verify_packet(packet, {"payload", "audit"})
    probe = subprocess.run(linux_candidate_command(PUBLIC / "isolation_probe.py", PUBLIC / "candidate.py"),
        cwd=PUBLIC, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, capture_output=True, text=True, timeout=8)
    checks = json.loads(probe.stdout) if probe.returncode == 0 else {}
    save(PRIVATE / "isolation.json", {"checks": checks, "exit_code": probe.returncode,
                                      "probe_sha256": sha(PUBLIC / "isolation_probe.py")})
    if set(checks) != ISOLATION or any(checks[k] is not True for k in checks):
        raise ValueError("independent pre-import isolation probe failed")
    channel = None
    try:
        max_response = 16384 if claim["mode"] == "fit_predict" else packet["audit"]["limits"]["max_response_bytes"]
        channel = DiagnosticLineChannel(linux_candidate_command(PUBLIC / server, PUBLIC / "candidate.py"),
            PUBLIC, PRIVATE / "candidate-stderr.log", max_response_bytes=max_response)
        if claim["mode"] == "fit_predict":
            journal = PredictionJournal(PRIVATE / "predictions", train_sha256=fingerprint(packet["train"]),
                evaluation_sha256=fingerprint(packet["evaluation"]), candidate_sha256=sha(PUBLIC / "candidate.py"),
                expected_predictions=len(packet["evaluation"]))
            result = predict_stream(channel.exchange, journal.commit, packet["train"], packet["evaluation"],
                                    packet["feature_names"], **packet["limits"])
            save(PRIVATE / "execution.json", {"stream": result, "complete": journal.finish(), "scored": False})
        else:
            save(PRIVATE / "execution.json", {"inspection": inspect_once(channel.exchange, packet), "scored": False})
    except Exception as error:
        save(PRIVATE / "failure.json", {"error_type": type(error).__name__, "scored": False})
        raise
    finally:
        if channel is not None:
            try:
                channel.close()
            finally:
                save(PRIVATE / "protocol.json", {"events": channel.events, "scored": False})
            save(PRIVATE / "candidate-diagnostic.json", channel.diagnostic())


if __name__ == "__main__":
    main()
