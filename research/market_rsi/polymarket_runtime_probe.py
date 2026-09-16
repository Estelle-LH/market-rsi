#!/usr/bin/env python3
"""One bounded E2B runtime/isolation probe for the Polymarket study."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from market_harbor import TEMPLATE
from market_rsi import canonical, digest, file_hash, fresh_json
from paid_budget import PaidBudget


UPPER_USD = "0.10"


def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    claim = {"schema": "polymarket_runtime_probe_v1", "experiment_id": args.experiment_id,
        "job_id": root.name, "template": TEMPLATE, "ttl_seconds": 90,
        "allow_internet_access": False,
        "network": {"allow_out": [], "deny_out": ["0.0.0.0/0"], "allow_public_traffic": False},
        "upper_usd": UPPER_USD, "source_sha256": file_hash(__file__),
        "research_result": False, "test_opened": False}
    fresh_json(root / "claim.json", claim)
    from dotenv import dotenv_values
    from e2b import Sandbox
    key = dotenv_values(args.env_file).get("E2B_API_KEY")
    if not key:
        raise ValueError("E2B key unavailable")
    budget = PaidBudget(args.budget)
    if budget.snapshot()["experiment_id"] != args.experiment_id:
        raise ValueError("runtime probe budget identity mismatch")
    budget.reserve(root.name, "setup", UPPER_USD, "e2b", digest(claim))
    budget.dispatch(root.name)
    sandbox, began = None, time.monotonic()
    try:
        sandbox = Sandbox.create(template=TEMPLATE, timeout=90, secure=True, api_key=key,
            allow_internet_access=False, network=claim["network"],
            lifecycle={"on_timeout": "kill", "auto_resume": False},
            metadata={"experiment_id": args.experiment_id, "job_id": root.name})
        fresh_json(root / "sandbox.json", {"sandbox_id": sandbox.sandbox_id})
        info = sandbox.get_info(request_timeout=15)
        command = sandbox.commands.run(
            "python3 -I -c 'import json,os,platform,socket; print(json.dumps({\"python\":platform.python_version(),\"uid\":os.geteuid(),\"interfaces\":[n for _,n in socket.if_nameindex()]}))'",
            user="root", timeout=10)
        value = json.loads(command.stdout) if command.exit_code == 0 else None
        assessment = {"template_id": info.template_id, "cpu_count": info.cpu_count,
            "memory_mb": info.memory_mb, "allow_internet_access": info.allow_internet_access,
            "python": value.get("python") if value else None,
            "root_probe_uid": value.get("uid") if value else None,
            "interfaces_before_candidate_unshare": value.get("interfaces") if value else None,
            "command_exit_code": command.exit_code,
            "passed": info.template_id == TEMPLATE and info.cpu_count == 2 and info.memory_mb == 512
                and info.allow_internet_access is False and command.exit_code == 0
                and isinstance(value.get("python") if value else None, str),
            "research_result": False, "test_opened": False}
        fresh_json(root / "assessment.json", assessment)
        print(canonical(assessment))
        if assessment["passed"] is not True:
            raise ValueError("runtime probe failed")
    except Exception as error:
        fresh_json(root / "failure.json", {"error_type": type(error).__name__,
                                           "automatic_retry": False})
        raise
    finally:
        if sandbox is not None:
            killed = sandbox.kill(request_timeout=15)
            fresh_json(root / "cleanup.json", {"sandbox_id": sandbox.sandbox_id,
                "kill_acknowledged": killed, "elapsed_host_seconds": time.monotonic() - began,
                "cost_reconciliation": "provider invoice unavailable; hold remains, not reported as spend"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--env-file", required=True, type=Path)
    main(parser.parse_args())
