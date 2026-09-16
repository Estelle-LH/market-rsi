"""Verify one exact sandbox's runtime, cleanup and budget dispatch; no API calls."""
from datetime import datetime
from pathlib import Path

from market_rsi import digest
from paid_budget import money


def read_sandbox_receipts(root, reads, claim, budget, phase, *, expected_live=False):
    root = Path(root).absolute()
    sandbox, actual = reads.read(root / "sandbox.json"), reads.read(root / "runtime.json")
    sid = sandbox["sandbox_id"]
    if (not isinstance(sid, str) or not sid or actual["sandbox_id"] != sid
            or actual["template_id"] != claim["template"] or actual["cpu_count"] != 2 or actual["memory_mb"] != 512
            or actual["allow_internet_access"] is not False):
        raise ValueError("actual sandbox identity does not match completed job")
    started, ended = datetime.fromisoformat(actual["started_at"]), datetime.fromisoformat(actual["expiry_at"])
    if (started.tzinfo is None or ended.tzinfo is None
            or not 0 < (ended - started).total_seconds() <= claim["ttl_seconds"] + 1):
        raise ValueError("actual sandbox lifetime differs from its bound")
    cleanups = sorted(root.glob("cleanup-[0-9][0-9].json"))
    if not cleanups or len(cleanups) > 10:
        raise ValueError("bounded exact sandbox cleanup receipt required")
    for path in cleanups:
        cleanup = reads.read(path)
        if cleanup["sandbox_id"] != sid:
            raise ValueError("cleanup refers to another sandbox")
    if cleanup["kill_acknowledged"] is not True:
        raise ValueError("exact final sandbox kill was not acknowledged")
    if expected_live:
        from harbor_process import verify_process_receipts
        verify_process_receipts(root, reads, succeeded=not (root / "failure.json").exists())
    state = budget.snapshot()
    job = state["jobs"].get(root.name, {})
    if (state["experiment_id"] != claim["experiment_id"] or phase not in {"learning", "transfer"}
            or claim["phase"] != phase or job.get("provider") != "e2b"
            or job.get("state") not in {"dispatched", "metered_terminal"}
            or job["input_sha256"] != digest(claim) or money(job["upper_usd"]) != money(claim["upper_usd"])
            or job["bucket"] != ("final" if phase == "transfer" else "learning")):
        raise ValueError("sandbox has no matching permanent budget dispatch")
    return job


def sandbox_usage(job):
    return {"job_state": job["state"], "metered_usd": job["metered_usd"], "invoiced_usd": job["invoice_usd"],
            "unresolved_hold_usd": job["upper_usd"] if job["state"] == "dispatched" else "0",
            "exact_cleanup_acknowledged": True}
