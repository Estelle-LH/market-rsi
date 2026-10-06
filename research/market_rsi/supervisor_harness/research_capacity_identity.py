"""Separate source identity from evidence of capacity; no activation authority."""
from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath

from market_rsi import digest

PROTECTED = {".git", ".codex", ".agents", "artifacts", "data", "datasets",
             "paid_budget.py", "supervisor_harness/global_state_gate.py",
             "data_scientist_harness/co_evolution_loop.py",
             "minimal_prediction_loop/proper_scoring.py"}


def sha(value):
    if (not isinstance(value, str) or len(value) != 64 or value == "0" * 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("nonzero lowercase SHA256 required")
    return value


def path(value):
    p = PurePosixPath(value) if isinstance(value, str) else None
    if (p is None or p.is_absolute() or str(p) != value or value == "."
            or ".." in p.parts or any(c in value for c in "\\*?[]\n\r\x00")):
        raise ValueError("canonical repository-relative source path required")
    return value


def source_binding(value):
    if not isinstance(value, dict) or set(value) != {"sources", "configuration_sha256"}:
        raise ValueError("exact source binding required")
    sha(value["configuration_sha256"])
    if not isinstance(value["sources"], dict) or not value["sources"]:
        raise ValueError("nonempty source manifest required")
    for name, token in value["sources"].items():
        path(name)
        sha(token)
    return deepcopy(value)


def _overlap(a, b):
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def manifest(*, kernel, model, predictor, harness, researcher, memory, runtime):
    """M is model identity; Python/dependencies and memory are separate fields.

    Hashes identify versions, never imply scientific improvement. Configuration
    contents remain the trusted caller's responsibility; bind their exact bytes.
    """
    components = {axis: source_binding(value) for axis, value in
                  (("K", kernel), ("C", predictor), ("H", harness), ("R", researcher))}
    for axis in ("C", "H", "R"):
        for name in components[axis]["sources"]:
            local_name = name.removeprefix("research/market_rsi/")
            if any(_overlap(local_name, protected) for protected in PROTECTED):
                raise ValueError("mutable capacity overlaps a protected path")
            if any(_overlap(name, other) for key, binding in components.items()
                   if key != axis for other in binding["sources"]):
                raise ValueError("prediction, harness, researcher and kernel sources overlap")
    if (not isinstance(model, dict) or set(model) !=
            {"requested_model", "serving_snapshot", "serving_snapshot_verified"}):
        raise ValueError("exact requested/serving model identity required")
    if (not all(isinstance(model[k], str) and model[k].strip()
                for k in ("requested_model", "serving_snapshot"))
            or type(model["serving_snapshot_verified"]) is not bool
            or (not model["serving_snapshot_verified"] and model["serving_snapshot"] != "unknown")
            or (model["serving_snapshot_verified"] and model["serving_snapshot"] == "unknown")):
        raise ValueError("serving snapshot must be verified or explicitly unknown")
    if (not isinstance(runtime, dict) or set(runtime) != {"python", "dependencies"}
            or not isinstance(runtime["python"], dict)
            or set(runtime["python"]) != {"path", "sha256"}
            or not isinstance(runtime["python"]["path"], str)
            or not PurePosixPath(runtime["python"]["path"]).is_absolute()
            or not isinstance(runtime["dependencies"], dict)):
        raise ValueError("exact pinned Python/dependency identity required")
    sha(runtime["python"]["sha256"])
    for name, binding in runtime["dependencies"].items():
        if (not isinstance(name, str) or not name.strip() or not isinstance(binding, dict)
                or set(binding) != {"version", "sha256"}
                or not isinstance(binding["version"], str) or not binding["version"].strip()):
            raise ValueError("dependency version/hash required")
        sha(binding["sha256"])
    value = {"schema": "market_rsi_capacity_identity_v1", "components": components,
             "model": deepcopy(model), "runtime": deepcopy(runtime),
             "memory_sha256": sha(memory), "runtime_sha256": digest(runtime),
             "M": digest(model), "capacity_improvement_claimed": False}
    value.update({axis: digest(binding) for axis, binding in components.items()})
    return value


def validate(value):
    rebuilt = manifest(kernel=value["components"]["K"], model=value["model"],
                       predictor=value["components"]["C"], harness=value["components"]["H"],
                       researcher=value["components"]["R"], memory=value["memory_sha256"],
                       runtime=value["runtime"])
    if rebuilt != value:
        raise ValueError("capacity identity was modified")
    return value


def change_axis(before, after):
    validate(before)
    validate(after)
    if any(before[k] != after[k] for k in ("K", "M", "runtime_sha256")):
        raise ValueError("protected kernel, base model and runtime must stay fixed")
    changed = [k for k in ("C", "H", "R", "memory_sha256") if before[k] != after[k]]
    if not changed:
        return "UNCHANGED"
    if changed == ["memory_sha256"]:
        return "MEMORY_ACCUMULATION"
    return changed[0] if len(changed) == 1 else "COMPOSITE_UNATTRIBUTABLE"
