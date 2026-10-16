"""One durable same-boot monotonic origin; no deadline renewal on resume."""
import math
from pathlib import Path
import re
import subprocess
import time

import earnings_entry as e
from earnings_night_budget import utc_epoch

FIELDS = {"schema", "source_commit", "boot_id", "wall_origin", "monotonic_origin",
          "cutoff_utc", "deadline_utc", "cutoff_monotonic", "deadline_monotonic"}


def boot_id():
    result = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
                            check=True, capture_output=True, text=True, timeout=5)
    value = result.stdout.strip()
    if not re.fullmatch(r"[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}", value):
        raise ValueError("Verified host boot identity unavailable")
    return value.lower()


def validate(value, config, current_boot):
    if (type(value) is not dict or set(value) != FIELDS or value["schema"] != "earnings_loop_clock_v1"
            or value["source_commit"] != config["source_commit"] or value["boot_id"] != current_boot
            or value["cutoff_utc"] != config["new_request_cutoff_utc"]
            or value["deadline_utc"] != config["deadline_utc"]):
        raise ValueError("Loop clock source/boot/window changed")
    for key in ("wall_origin", "monotonic_origin", "cutoff_monotonic", "deadline_monotonic"):
        if type(value[key]) not in (int, float) or not math.isfinite(value[key]) or value[key] < 0:
            raise ValueError("Finite nonnegative clock origin required")
    wall, mono = value["wall_origin"], value["monotonic_origin"]
    if (value["cutoff_monotonic"] != mono + max(0, utc_epoch(value["cutoff_utc"]) - wall)
            or value["deadline_monotonic"] != mono + max(0, utc_epoch(value["deadline_utc"]) - wall)
            or time.monotonic() < mono):
        raise ValueError("Original monotonic clock mapping changed")
    return value


def capture_or_load(root, config, *, create=True):
    root = Path(root).absolute()
    if root.resolve() != root:
        raise ValueError("Canonical loop clock root required")
    path, seal = root / "clock.json", root / "clock.binding.json"
    boot = boot_id()  # Before any role credentials; unknown identity is a stop.
    inherited = config.get("inherited_clock")
    if inherited is not None:
        if (type(inherited) is not dict or set(inherited) != {"binding", "source_commit"}
                or type(inherited["source_commit"]) is not str
                or not re.fullmatch(r"[0-9a-f]{40}", inherited["source_commit"])):
            raise ValueError("Exact independently reviewed original clock binding required")
        value = e.strict_json(e.checked(inherited["binding"]).decode())
        origin = dict(config, source_commit=inherited["source_commit"])
        # A fresh source/loop may inherit an old sealed window, never recreate it.
        return validate(value, origin, boot), inherited["binding"]
    if path.exists() or seal.exists():
        if not path.is_file() or not seal.is_file() or seal.resolve() != seal:
            raise ValueError("Incomplete immutable loop clock")
        bound = e.strict_json(seal.read_text())
        if type(bound) is not dict or set(bound) != {"path", "sha256"} or bound["path"] != str(path):
            raise ValueError("Loop clock binding changed")
        value = e.strict_json(e.checked(bound).decode())
    else:
        if not create or (root.exists() and any(root.iterdir())):
            raise ValueError("Existing loop has no original clock; do not recreate it")
        mono, wall = time.monotonic(), time.time()
        value = {"schema": "earnings_loop_clock_v1", "source_commit": config["source_commit"],
            "boot_id": boot, "wall_origin": wall, "monotonic_origin": mono,
            "cutoff_utc": config["new_request_cutoff_utc"], "deadline_utc": config["deadline_utc"],
            "cutoff_monotonic": mono + max(0, utc_epoch(config["new_request_cutoff_utc"]) - wall),
            "deadline_monotonic": mono + max(0, utc_epoch(config["deadline_utc"]) - wall)}
        validate(value, config, boot)
        root.mkdir(parents=True, exist_ok=True)
        e.durable_json(path, value)
        bound = {"path": str(path), "sha256": e.digest(path.read_bytes())}
        e.durable_json(seal, bound)
    return validate(value, config, boot), bound
