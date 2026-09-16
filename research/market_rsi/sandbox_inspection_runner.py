"""Root-side inspection runner, only inside E2B; no hidden Test input.

The separate prediction runner remains unchanged so its completed cloud receipt
continues to identify the exact code that ran. This endpoint still needs actual
Harbor composition verification before any cloud inspection is claimed.
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
SOURCES = {"private/sandbox_inspection_runner.py", "private/prediction_stream.py", "private/inspection_stream.py",
           "public/inspection_candidate_server.py", "public/candidate.py", "public/isolation_probe.py"}
ISOLATION = {"unprivileged", "no_groups", "no_new_privileges", "only_loopback", "network_blocked",
             "private_read_denied", "private_write_denied", "public_write_denied", "provider_keys_absent"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def require_layout():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("inspection runner requires Linux root in E2B, never the Mac")
    for directory, mode in ((PRIVATE, 0o700), (PUBLIC, 0o755)):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError("unsafe inspection directory")
        for path in directory.iterdir():
            meta = path.lstat()
            expected = 0o600 if directory == PRIVATE else 0o444
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or stat.S_IMODE(meta.st_mode) != expected:
                raise ValueError("unsafe inspection file ownership/permissions")


def main():
    require_layout()  # Before changing import paths or importing candidate code.
    sys.path.insert(0, str(PRIVATE))
    from inspection_stream import inspect_once, verify_packet
    from prediction_stream import LineChannel, fingerprint, linux_candidate_command
    packet = json.loads((PRIVATE / "packet.json").read_text())
    claim = json.loads((PRIVATE / "input-claim.json").read_text())
    verify_packet(packet, {"payload", "audit"})
    if (set(claim) != {"packet_sha256", "deployed_hashes"} or fingerprint(packet) != claim["packet_sha256"]
            or set(claim["deployed_hashes"]) != SOURCES):
        raise ValueError("exact inspection input/source commitments required")
    for name, expected in claim["deployed_hashes"].items():
        directory, filename = name.split("/", 1)
        if sha((PRIVATE if directory == "private" else PUBLIC) / filename) != expected:
            raise ValueError("inspection deployed source changed")
    probe = subprocess.run(linux_candidate_command(PUBLIC / "isolation_probe.py", PUBLIC / "candidate.py"),
        cwd=PUBLIC, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, capture_output=True, text=True, timeout=8)
    checks = json.loads(probe.stdout) if probe.returncode == 0 else {}
    save(PRIVATE / "isolation.json", {"checks": checks, "exit_code": probe.returncode,
                                      "probe_sha256": sha(PUBLIC / "isolation_probe.py")})
    if set(checks) != ISOLATION or any(checks[k] is not True for k in checks):
        raise ValueError("inspection pre-import isolation probe failed")
    channel = None
    try:
        channel = LineChannel(linux_candidate_command(PUBLIC / "inspection_candidate_server.py", PUBLIC / "candidate.py"),
                              PUBLIC, max_response_bytes=packet["audit"]["limits"]["max_response_bytes"])
        result = inspect_once(channel.exchange, packet)
        save(PRIVATE / "execution.json", {"inspection": result, "scored": False})
    except Exception as error:
        save(PRIVATE / "failure.json", {"error_type": type(error).__name__, "scored": False})
        raise
    finally:
        if channel is not None:
            try:
                channel.close()
            finally:
                save(PRIVATE / "protocol.json", {"events": channel.events,
                     "candidate_stderr": "discarded by bounded transport", "scored": False})


if __name__ == "__main__":
    main()
