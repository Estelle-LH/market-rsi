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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget, money


TIMEOUT_SECONDS = 180
E2B_SDK_VERSION = "2.38.0"
UPPER_USD = "0.20"  # Two short sandboxes, each covered by the old $0.10 setup hold.
# Live -04 and -05 observed a completed IPv4 TCP connect despite the requested
# deny policy. That does not establish whether an application payload reached
# the public endpoint; either way the current probe cannot certify isolation.
# Keep this runner fail-closed until a causal, protocol-level network test and
# effective enforcement are versioned; never repeat a run for a passing score.
LIVE_DISPATCH_BLOCKED_REASON = "E2B public IPv4 TCP connect succeeded; full egress and isolation remain unverified"
# E2B 2.38.0 rejected ::/0 at create time on 2026-09-17. Keep its
# allow_internet_access=False gate and probe both IPv4 and IPv6 from the guest.
NETWORK = {"allow_out": [], "deny_out": ["0.0.0.0/0"],
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
network_reachability = {}
for address in ("1.1.1.1", "2606:4700:4700::1111"):
    try:
        connection = socket.create_connection((address, 443), timeout=2)
        connection.close()
        network_blocked = False
        network_reachability[address] = True
    except OSError:
        network_reachability[address] = False
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
    "checks": checks, "public_tcp_reachability": network_reachability}, sort_keys=True))
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
    # macOS venv bin/python3 normally symlinks to the system interpreter;
    # the isolated prefix and invoked path, not the symlink target, identify
    # where this task's packages and executable entry point are kept.
    if (sys.prefix == sys.base_prefix
            or not Path(sys.prefix).resolve().is_relative_to(allowed)
            or not Path(sys.executable).absolute().is_relative_to(allowed)):
        raise ValueError("iCloud Python runtime forbidden")
    if importlib.metadata.version("e2b") != E2B_SDK_VERSION:
        raise ValueError("E2B SDK version differs from pinned runtime")


def _require_no_active_market_sandboxes(sandbox_class, key: str) -> None:
    pager = sandbox_class.list(limit=100, api_key=key, request_timeout=15)
    inspected = 0
    while pager.has_next:
        for item in pager.next_items():
            inspected += 1
            metadata = item.metadata or {}
            if str(metadata.get("experiment_id", "")).startswith("market-rsi"):
                raise RuntimeError("existing Market RSI E2B sandbox is still active")
    return {"inspected_sandboxes": inspected, "active_market_rsi_sandboxes": 0}


def _run_role(sandbox, role: str, payload: dict) -> tuple[dict, dict, dict]:
    peer = MARKERS["researcher" if role == "controller" else "controller"]
    sandbox.files.write(MARKERS[role], secrets.token_hex(16))
    sandbox.files.write("/tmp/market_probe.py", PROBE)
    sandbox.files.write("/tmp/market_input.json", canonical(payload))
    command = f"python3 -I /tmp/market_probe.py {role} {peer}"
    command_exit_exception = False
    try:
        result = sandbox.commands.run(command, timeout=25)
    except Exception as exc:
        if type(exc).__name__ != "CommandExitException":
            raise
        # E2B raises on a normal nonzero exit. Read the guest's check report
        # before cleanup so a failed isolation check is diagnosable.
        result = exc
        command_exit_exception = True
    if len(result.stdout) > 4096 or len(result.stderr) > 4096:
        raise ValueError("oversized sandbox command output")
    report_text = sandbox.files.read("/tmp/market_report.json")
    output_text = sandbox.files.read("/tmp/market_output.json")
    if len(report_text) > 8192 or len(output_text) > 8192:
        raise ValueError("oversized sandbox artifact")
    report, output = json.loads(report_text), json.loads(output_text)
    required_checks = {"peer_marker_absent", "paid_keys_absent",
                       "host_home_absent", "direct_public_network_blocked"}
    failed_checks = sorted(name for name in required_checks
                           if report.get("checks", {}).get(name) is not True)
    if set(report.get("checks", {})) != required_checks:
        failed_checks.append("check_schema")
    reachability = report.get("public_tcp_reachability", {})
    if (set(reachability) != {"1.1.1.1", "2606:4700:4700::1111"}
            or any(type(value) is not bool for value in reachability.values())):
        failed_checks.append("network_probe_schema")
    elif any(reachability.values()):
        failed_checks.append("public_tcp_reachable")
    if report.get("role") != role:
        failed_checks.append("role_mismatch")
    if result.exit_code != 0:
        failed_checks.append("nonzero_exit")
    return report, output, {"exit_code": result.exit_code,
                            "isolation_check_failures": failed_checks,
                            "sdk_command_exit_exception": command_exit_exception,
                            "stdout_sha256": digest(result.stdout),
                            "stderr_sha256": digest(result.stderr)}


def run_pair(root: Path, budget: PaidBudget, create_sandbox) -> dict:
    """Run one permanent, scripted A/B canary; factory is injected for offline tests."""
    if isinstance(budget, PaidBudget) and LIVE_DISPATCH_BLOCKED_REASON:
        raise RuntimeError("live E2B canary blocked: " + LIVE_DISPATCH_BLOCKED_REASON)
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
             "python_executable": str(Path(sys.executable).absolute()),
             "python_executable_target": str(Path(sys.executable).resolve()),
             "python_prefix": str(Path(sys.prefix).resolve()),
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
            network_info = getattr(info, "network", None)
            if (info.allow_internet_access is not False
                    or info.cpu_count > 8 or info.memory_mb > 8192
                    or not isinstance(network_info, dict)
                    or network_info.get("allow_out") != NETWORK["allow_out"]
                    or network_info.get("deny_out") != NETWORK["deny_out"]
                    or network_info.get("allow_public_traffic") is not False):
                raise ValueError("sandbox network or compute bounds differ from claim")
            fresh_json(root / f"{role}-sandbox.json", {
                "role": role, "sandbox_id": sandbox_id,
                "template_id": info.template_id,
                "cpu_count": info.cpu_count, "memory_mb": info.memory_mb,
                "envd_version": info.envd_version,
                "allow_internet_access": info.allow_internet_access,
                "network": network_info})
        controller_report, decision, controller_command = _run_role(
            sandboxes["controller"], "controller", {"input_sha256": digest(input_packet)})
        fresh_json(root / "controller-report.json", controller_report)
        fresh_json(root / "controller-command.json", controller_command)
        if controller_command["isolation_check_failures"]:
            raise ValueError("controller isolation probe failed: "
                             + ",".join(controller_command["isolation_check_failures"]))
        if decision != {"schema": "scripted_controller_decision_v1",
                        "input_sha256": digest(input_packet),
                        "task": "hash the admitted synthetic task"}:
            raise ValueError("controller output differs from admitted synthetic task")
        fresh_json(root / "decision.json", decision)
        researcher_report, output, researcher_command = _run_role(
            sandboxes["researcher"], "researcher", {
                "decision_sha256": digest(decision), "task": decision["task"]})
        fresh_json(root / "researcher-report.json", researcher_report)
        fresh_json(root / "researcher-command.json", researcher_command)
        if researcher_command["isolation_check_failures"]:
            raise ValueError("researcher isolation probe failed: "
                             + ",".join(researcher_command["isolation_check_failures"]))
        if output != {"schema": "scripted_researcher_output_v1",
                      "decision_sha256": digest(decision),
                      "task_sha256": hashlib.sha256(
                          decision["task"].encode()).hexdigest()}:
            raise ValueError("researcher output differs from bound controller decision")
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
        # Do not mark this very process as reaped. The parent may reconcile
        # only after it has waited for the child and verified remote cleanup.
        # Until then the dispatched budget hold stays outstanding.
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
              "cost_status": "pending_parent_reconciliation"}
    fresh_json(root / "review.json", review)
    return review


def _reconcile_reaped_child(root: Path, budget: PaidBudget, sandbox_class,
                            key: str) -> dict:
    """Settle conservatively only after a parent has reaped the exact child."""
    root = _local_root(root, "canary output")
    def safe_json(name: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError("missing, symlinked or oversized canary evidence")
        value = load_json(path)
        if not isinstance(value, dict):
            raise ValueError("canary evidence must be an object")
        return value
    process_path = root / "parent-process.json"
    process = safe_json("parent-process.json")
    if (set(process) != {"schema", "job_id", "process_reaped", "exit_code",
                         "timed_out", "stdout_sha256", "stderr_sha256"}
            or process["schema"] != "dual_e2b_parent_process_v1"
            or process["job_id"] != root.name
            or process["process_reaped"] is not True
            or type(process["timed_out"]) is not bool
            or (process["exit_code"] is not None
                and type(process["exit_code"]) is not int)
            or (process["timed_out"] is True and process["exit_code"] is not None)
            or (process["timed_out"] is False and process["exit_code"] is None)
            or any(not isinstance(process[key], str) or len(process[key]) != 64
                   or any(c not in "0123456789abcdef" for c in process[key])
                   for key in ("stdout_sha256", "stderr_sha256"))):
        raise ValueError("parent has not proved exact child termination")
    claim = safe_json("claim.json")
    if (claim.get("job_id") != root.name or claim.get("source_sha256") != file_hash(__file__)
            or claim.get("roles") != ["controller", "researcher"]):
        raise ValueError("canary claim/source changed before reconciliation")
    cleanup = safe_json("cleanup.json")
    if set(cleanup) != {"controller", "researcher"}:
        raise ValueError("both exact E2B sandbox cleanups required")
    sandbox_ids = []
    for role in ("controller", "researcher"):
        info = safe_json(f"{role}-sandbox.json")
        item = cleanup[role]
        if (info.get("role") != role or not isinstance(info.get("sandbox_id"), str)
                or not info["sandbox_id"] or set(item) != {"sandbox_id", "kill_acknowledged"}
                or item["sandbox_id"] != info["sandbox_id"]
                or item["kill_acknowledged"] is not True):
            raise ValueError("exact role sandbox cleanup not verified")
        sandbox_ids.append(info["sandbox_id"])
    if len(set(sandbox_ids)) != 2:
        raise ValueError("controller and researcher reused a sandbox ID")
    account = _require_no_active_market_sandboxes(sandbox_class, key)
    fresh_json(root / "parent-account-check.json", {
        "schema": "dual_e2b_parent_account_check_v1", "job_id": root.name,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(), **account})
    evidence_sha = digest({
        "claim_sha256": file_hash(root / "claim.json"),
        "process_sha256": file_hash(process_path),
        "cleanup_sha256": file_hash(root / "cleanup.json"),
        "account_check_sha256": file_hash(root / "parent-account-check.json")})
    budget.settle_uncertain_at_upper(root.name, {
        "terminal_local": True, "process_reaped": True,
        "remote_usage_unknown": True, "automatic_retry": False,
        "evidence_sha256": evidence_sha,
        "note": "Parent reaped exact child; both role sandboxes killed and no Market RSI sandbox active; invoice unknown."})
    result = {"schema": "dual_e2b_parent_accounting_v1", "job_id": root.name,
              "evidence_sha256": evidence_sha,
              "cost_status": "uncertain_upper_bound_not_invoice",
              "process_reaped": True, "exact_remote_cleanup_verified": True}
    fresh_json(root / "parent-accounting.json", result)
    return result


def run_parent(root: Path, budget: PaidBudget, sandbox_class, key: str,
               command: list[str], invoke=subprocess.run) -> dict:
    """Launch once, wait for the child, then make an honest terminal receipt."""
    if LIVE_DISPATCH_BLOCKED_REASON:
        raise RuntimeError("live E2B canary blocked: " + LIVE_DISPATCH_BLOCKED_REASON)
    root = _local_root(root, "canary output")
    if root.exists():
        raise FileExistsError("fresh canary ID required")
    try:
        child = invoke(command, capture_output=True, text=True,
                       timeout=2 * TIMEOUT_SECONDS + 60, check=False)
        exit_code, timed_out = child.returncode, False
        stdout, stderr = child.stdout, child.stderr
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and waits for its direct child before raising.
        exit_code, timed_out = None, True
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
    if not root.is_dir():
        raise RuntimeError("child exited before a canary claim; no accounting was written")
    def output_sha(value):
        return hashlib.sha256(value if isinstance(value, bytes)
                              else value.encode()).hexdigest()
    fresh_json(root / "parent-process.json", {
        "schema": "dual_e2b_parent_process_v1", "job_id": root.name,
        "process_reaped": True, "exit_code": exit_code, "timed_out": timed_out,
        "stdout_sha256": output_sha(stdout), "stderr_sha256": output_sha(stderr)})
    accounting = _reconcile_reaped_child(root, budget, sandbox_class, key)
    if timed_out or exit_code != 0:
        raise RuntimeError("canary child failed after reaping; preserved exact artifacts and upper-bound accounting")
    review = load_json(root / "review.json")
    if (review.get("claim_sha256") != file_hash(root / "claim.json")
            or review.get("cleanup_sha256") != file_hash(root / "cleanup.json")
            or review.get("isolation_checks_passed") is not True):
        raise ValueError("child's isolation review missing or changed")
    result = {"schema": "dual_e2b_parent_review_v1", "job_id": root.name,
              "child_review_sha256": file_hash(root / "review.json"),
              "accounting_sha256": file_hash(root / "parent-accounting.json"),
              "scripted_only": True, "empirical_result": False}
    fresh_json(root / "parent-review.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if LIVE_DISPATCH_BLOCKED_REASON:
        raise RuntimeError("live E2B canary blocked: " + LIVE_DISPATCH_BLOCKED_REASON)
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
    if args.child:
        with (budget.root / "dual-e2b-canary.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _require_no_active_market_sandboxes(Sandbox, key)
            review = run_pair(args.output, budget, create)
    else:
        with (budget.root / "dual-e2b-parent.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            command = [sys.executable, str(Path(__file__).resolve()),
                       "--output", str(args.output), "--budget", str(args.budget),
                       "--env-file", str(args.env_file), "--child"]
            review = run_parent(args.output, budget, Sandbox, key, command)
    print(canonical(review))


if __name__ == "__main__":
    main()
