"""Bounded two-E2B role-isolation canary; never a model or prediction result.

The trusted host owns the budget and E2B key. Neither sandbox receives a key,
market data, Dev/Final data, or a mount. The controller decision is scripted;
model authorship needs a separate adapter and canary before a live research run.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import secrets
import sys
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget, money


TIMEOUT_SECONDS = 180
E2B_SDK_VERSION = "2.38.0"
UPPER_USD = "0.20"  # Two short sandboxes, each covered by the old $0.10 setup hold.
NETWORK = {"allow_out": [], "deny_out": ["0.0.0.0/0", "::/0"],
           "allow_public_traffic": False}
MARKERS = {"controller": "/tmp/market_controller_marker",
           "researcher": "/tmp/market_researcher_marker"}
SECRET_NAMES = ("TINKER_API_KEY", "E2B_API_KEY", "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY")

PROBE = '''import hashlib, json, os, socket, sys
from pathlib import Path
role = sys.argv[1]
peer = sys.argv[2]
payload = json.loads(Path("/tmp/market_input.json").read_text())
network_blocked = True
for address in ("1.1.1.1", "2606:4700:4700::1111"):
    try:
        connection = socket.create_connection((address, 443), timeout=2)
        connection.close()
        network_blocked = False
    except OSError:
        pass
checks = {
    "peer_marker_absent": not Path(peer).exists(),
    "paid_keys_absent": not any(os.environ.get(name) for name in
        ("TINKER_API_KEY", "E2B_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")),
    "host_home_absent": not Path("/Users/estelle").exists(),
    "direct_public_network_blocked": network_blocked,
}
if role == "controller":
    output = {"schema": "scripted_controller_decision_v1",
              "input_sha256": payload["input_sha256"],
              "task": "hash the admitted synthetic task"}
else:
    output = {"schema": "scripted_researcher_output_v1",
              "decision_sha256": payload["decision_sha256"],
              "task_sha256": hashlib.sha256(payload["task"].encode()).hexdigest()}
Path("/tmp/market_output.json").write_text(json.dumps(output, sort_keys=True))
Path("/tmp/market_report.json").write_text(json.dumps({"role": role,
    "checks": checks}, sort_keys=True))
if not all(checks.values()):
    sys.exit(17)
'''


def _local_root(path: Path, label: str) -> Path:
    path = Path(path).resolve()
    allowed = Path("/Users/estelle/Library/Application Support/MarketRSI").resolve()
    if not path.is_relative_to(allowed):
        raise ValueError(f"{label} must stay on the local MarketRSI volume")
    return path


def _require_local_runtime() -> None:
    allowed = Path("/Users/estelle/Library/Application Support/MarketRSI").resolve()
    if not Path(sys.executable).resolve().is_relative_to(allowed):
        raise ValueError("iCloud Python runtime forbidden")
    if importlib.metadata.version("e2b") != E2B_SDK_VERSION:
        raise ValueError("E2B SDK version differs from pinned runtime")


def _require_no_active_market_sandboxes(sandbox_class, key: str) -> None:
    pager = sandbox_class.list(limit=100, api_key=key, request_timeout=15)
    while pager.has_next:
        for item in pager.next_items():
            metadata = item.metadata or {}
            if str(metadata.get("experiment_id", "")).startswith("market-rsi"):
                raise RuntimeError("existing Market RSI E2B sandbox is still active")


def _run_role(sandbox, role: str, payload: dict) -> tuple[dict, dict, dict]:
    peer = MARKERS["researcher" if role == "controller" else "controller"]
    sandbox.files.write(MARKERS[role], secrets.token_hex(16))
    sandbox.files.write("/tmp/market_probe.py", PROBE)
    sandbox.files.write("/tmp/market_input.json", canonical(payload))
    command = f"python3 -I /tmp/market_probe.py {role} {peer}"
    result = sandbox.commands.run(command, timeout=25)
    if len(result.stdout) > 4096 or len(result.stderr) > 4096:
        raise ValueError("oversized sandbox command output")
    report_text = sandbox.files.read("/tmp/market_report.json")
    output_text = sandbox.files.read("/tmp/market_output.json")
    if len(report_text) > 8192 or len(output_text) > 8192:
        raise ValueError("oversized sandbox artifact")
    report, output = json.loads(report_text), json.loads(output_text)
    required_checks = {"peer_marker_absent", "paid_keys_absent",
                       "host_home_absent", "direct_public_network_blocked"}
    if (result.exit_code != 0 or report.get("role") != role
            or set(report.get("checks", {})) != required_checks
            or any(report["checks"][name] is not True for name in required_checks)):
        raise ValueError(f"{role} isolation probe failed")
    return report, output, {"exit_code": result.exit_code,
                            "stdout_sha256": digest(result.stdout),
                            "stderr_sha256": digest(result.stderr)}


def run_pair(root: Path, budget: PaidBudget, create_sandbox) -> dict:
    """Run one permanent, scripted A/B canary; factory is injected for offline tests."""
    root = _local_root(root, "canary output")
    identifier(root.name)
    _local_root(budget.root, "budget")
    if root.exists():
        raise FileExistsError("fresh canary ID required")
    _require_local_runtime()
    snapshot = budget.snapshot()
    if (money(snapshot["available_usd"]) < money(UPPER_USD)
            or money(snapshot["buckets"]["setup"]["available_usd"]) < money(UPPER_USD)):
        raise ValueError("setup/global budget cannot cover both sandboxes")
    input_packet = {"schema": "dual_e2b_synthetic_input_v1", "nonce": secrets.token_hex(16),
                    "task": "hash the admitted synthetic task"}
    claim = {"schema": "dual_e2b_canary_claim_v1", "job_id": root.name,
             "source_sha256": file_hash(__file__), "probe_sha256": digest(PROBE),
             "e2b_sdk_version": E2B_SDK_VERSION,
             "python_executable": str(Path(sys.executable).resolve()),
             "python_version": sys.version,
             "input_sha256": digest(input_packet), "roles": ["controller", "researcher"],
             "network": NETWORK, "timeout_seconds": TIMEOUT_SECONDS,
             "upper_usd_not_spend": UPPER_USD, "controller_led_result": False,
             "empirical_result": False, "automatic_retry": False}
    root.mkdir(mode=0o700)
    fresh_json(root / "claim.json", claim)
    fresh_json(root / "input.json", input_packet)
    budget.reserve(root.name, "setup", UPPER_USD, "e2b", digest(claim))
    budget.dispatch(root.name)
    sandboxes = {}
    create_attempts = []
    cleanup = {}
    error = None
    try:
        for role in ("controller", "researcher"):
            create_attempts.append(role)
            sandbox = create_sandbox(role, root.name)
            sandboxes[role] = sandbox
            sandbox_id = sandbox.sandbox_id
            if not isinstance(sandbox_id, str) or not sandbox_id or any(
                    other.sandbox_id == sandbox_id for name, other in sandboxes.items()
                    if name != role):
                raise ValueError("roles reused one E2B sandbox ID")
            info = sandbox.get_info()
            if (info.allow_internet_access is not False
                    or info.cpu_count > 8 or info.memory_mb > 8192):
                raise ValueError("sandbox network or compute bounds differ from claim")
            fresh_json(root / f"{role}-sandbox.json", {
                "role": role, "sandbox_id": sandbox_id,
                "template_id": info.template_id,
                "cpu_count": info.cpu_count, "memory_mb": info.memory_mb,
                "envd_version": info.envd_version,
                "allow_internet_access": info.allow_internet_access})
        controller_report, decision, controller_command = _run_role(
            sandboxes["controller"], "controller", {"input_sha256": digest(input_packet)})
        if decision != {"schema": "scripted_controller_decision_v1",
                        "input_sha256": digest(input_packet),
                        "task": "hash the admitted synthetic task"}:
            raise ValueError("controller output differs from admitted synthetic task")
        fresh_json(root / "controller-report.json", controller_report)
        fresh_json(root / "decision.json", decision)
        researcher_report, output, researcher_command = _run_role(
            sandboxes["researcher"], "researcher", {
                "decision_sha256": digest(decision), "task": decision["task"]})
        if output != {"schema": "scripted_researcher_output_v1",
                      "decision_sha256": digest(decision),
                      "task_sha256": hashlib.sha256(
                          decision["task"].encode()).hexdigest()}:
            raise ValueError("researcher output differs from bound controller decision")
        fresh_json(root / "researcher-report.json", researcher_report)
        fresh_json(root / "output.json", output)
        fresh_json(root / "commands.json", {"controller": controller_command,
                                            "researcher": researcher_command})
    except Exception as exc:
        error = exc
        fresh_json(root / "failure.json", {"error_type": type(exc).__name__})
    finally:
        for role, sandbox in reversed(list(sandboxes.items())):
            try:
                cleanup[role] = {"sandbox_id": sandbox.sandbox_id,
                                 "kill_acknowledged": sandbox.kill() is True}
            except Exception as exc:
                cleanup[role] = {"sandbox_id": sandbox.sandbox_id,
                                 "kill_acknowledged": False,
                                 "error_type": type(exc).__name__}
        fresh_json(root / "cleanup.json", cleanup)
        if (cleanup and len(sandboxes) == len(create_attempts)
                and all(item["kill_acknowledged"] for item in cleanup.values())):
            budget.settle_uncertain_at_upper(root.name, {
                "terminal_local": True, "process_reaped": True,
                "remote_usage_unknown": True, "automatic_retry": False,
                "evidence_sha256": file_hash(root / "cleanup.json"),
                "note": "Both exact E2B sandboxes killed; invoice unknown; hold charged at upper bound."})
    if error is not None:
        raise error
    if set(cleanup) != {"controller", "researcher"} or not all(
            item["kill_acknowledged"] for item in cleanup.values()):
        raise RuntimeError("incomplete E2B cleanup; preserve exact IDs")
    if file_hash(__file__) != claim["source_sha256"]:
        raise RuntimeError("canary source changed during execution")
    review = {"schema": "dual_e2b_scripted_canary_review_v1",
              "claim_sha256": file_hash(root / "claim.json"),
              "decision_sha256": file_hash(root / "decision.json"),
              "output_sha256": file_hash(root / "output.json"),
              "cleanup_sha256": file_hash(root / "cleanup.json"),
              "distinct_sandbox_ids": True, "isolation_checks_passed": True,
              "controller_led_result": False, "empirical_result": False,
              "cost_status": "upper_bound_only_not_invoice"}
    fresh_json(root / "review.json", review)
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    from dotenv import dotenv_values
    from e2b import Sandbox
    key = dotenv_values(args.env_file).get("E2B_API_KEY")
    if not key:
        raise ValueError("E2B credential unavailable; no sandbox created")

    def create(role: str, job_id: str):
        return Sandbox.create(template="base", timeout=TIMEOUT_SECONDS,
            secure=True, api_key=key, allow_internet_access=False,
            network=NETWORK, lifecycle={"on_timeout": "kill", "auto_resume": False},
            metadata={"experiment_id": "market-rsi-dual-role-canary",
                      "job_id": job_id, "role": role})

    budget = PaidBudget(args.budget)
    _local_root(budget.root, "budget")
    _require_local_runtime()
    with (budget.root / "dual-e2b-canary.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _require_no_active_market_sandboxes(Sandbox, key)
        review = run_pair(args.output, budget, create)
    print(canonical(review))


if __name__ == "__main__":
    main()
