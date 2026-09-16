"""Trusted pre-import probe; candidate code has not run when this executes."""
import json
import os
import socket
from pathlib import Path

private = Path("/root/market-rsi-private/packet.json")
public = Path("/tmp/market-rsi-public/candidate.py")
checks = {"unprivileged": os.geteuid() == 65534, "no_groups": os.getgroups() == [],
          "no_new_privileges": "NoNewPrivs:\t1" in Path("/proc/self/status").read_text(),
          "only_loopback": {name for _, name in socket.if_nameindex()} == {"lo"},
          "provider_keys_absent": not any(os.environ.get(k) for k in (
              "TINKER_API_KEY", "E2B_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"))}
try:
    private.read_bytes()
    checks["private_read_denied"] = False
except PermissionError:
    checks["private_read_denied"] = True
for path, name in [(private, "private_write_denied"), (public, "public_write_denied")]:
    try:
        # Open without truncating or writing. Unexpected permission still fails.
        with path.open("r+"):
            pass
        checks[name] = False
    except PermissionError:
        checks[name] = True
try:
    with socket.create_connection(("1.1.1.1", 443), timeout=1):
        checks["network_blocked"] = False
except OSError:
    checks["network_blocked"] = True
print(json.dumps(checks, sort_keys=True))
