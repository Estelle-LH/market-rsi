"""Execute the coding preflight in one isolated, bounded E2B sandbox.

This tests the actual code-execution path, not research improvement. No market
data, hidden outcomes or user credentials are uploaded. Runtime billing remains
an estimate until provider reconciliation; an unresolved hold is not spend.
"""
import argparse
import json
import time
from pathlib import Path

from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget


TIMEOUT = 180
UPPER_USD = "0.10"
EXECUTION_COMMAND = "unshare --net -- setpriv --reuid=65534 --regid=65534 --clear-groups --no-new-privs -- python3 -I /tmp/check.py"
# Above the published maximum 8 vCPU / 8 GiB x 180s = $0.02664.
RATES = {"vcpu_second": "0.000014", "gib_second": "0.0000045",
         "source": "https://e2b.dev/pricing", "checked_utc_date": "2026-09-07"}
REQUIRED_CHECKS = ("all_math_tests_pass", "direct_ipv4_connection_blocked",
                   "unprivileged_uid", "only_loopback_interface",
                   "no_supplementary_groups", "no_new_privileges",
                   "paid_provider_keys_absent", "host_home_absent")


def assessment_passes(report, exit_code):
    # Require actual booleans, not truthy strings or a candidate-provided `passed`.
    return (type(exit_code) is int and exit_code == 0 and isinstance(report, dict)
            and all(report.get(key) is True for key in REQUIRED_CHECKS))


def require_passed(report):
    if report.get("passed") is not True:
        raise ValueError("sandbox execution/isolation assessment failed")

HARNESS = '''import importlib.util, json, math, os, socket
from pathlib import Path
spec = importlib.util.spec_from_file_location("candidate", "/tmp/candidate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
tests = {}
for name, p, y, target in [
    ("perfect", [0, 1], [0, 1], 0),
    ("uncertain", [0.5, 0.5], [0, 1], 0.25),
    ("wrong", [1, 0], [0, 1], 1),
    ("mixed", [0.1, 0.8, 0.7], [0, 1, 0], 0.18),
]:
    try: tests[name] = abs(candidate.brier(p, y) - target) < 1e-10
    except Exception: tests[name] = False
for name, p, y in [
    ("reject_empty", [], []), ("reject_lengths", [0.2], [0, 1]),
    ("reject_range", [1.5], [1]), ("reject_nan", [float("nan")], [1]),
    ("reject_infinity", [float("inf")], [1]), ("reject_nonbinary", [0.5], [2]),
]:
    try:
        candidate.brier(p, y)
        tests[name] = False
    except (ValueError, TypeError): tests[name] = True
try:
    sock = socket.create_connection(("1.1.1.1", 443), timeout=2)
    sock.close()
    network_blocked = False
except OSError: network_blocked = True
interfaces = [name for _, name in socket.if_nameindex()]
status = Path("/proc/self/status").read_text()
report = {"tests": tests, "all_math_tests_pass": all(tests.values()),
          "direct_ipv4_connection_blocked": network_blocked,
          "unprivileged_uid": os.geteuid() == 65534,
          "only_loopback_interface": set(interfaces) == {"lo"},
          "network_namespace_interfaces": interfaces,
          "no_supplementary_groups": os.getgroups() == [],
          "no_new_privileges": "NoNewPrivs:\\t1" in status,
          "paid_provider_keys_absent": not any(os.environ.get(k) for k in
              ("TINKER_API_KEY", "E2B_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")),
          "host_home_absent": not Path("/Users/estelle").exists()}
Path("/tmp/result.json").write_text(json.dumps(report))
print(json.dumps(report))
'''


def main(args):
    root = args.output.resolve()
    identifier(root.name)
    coder = load_json(args.coder / "assessment.json")
    review = args.coder / "assessment-review.json"
    if review.is_file():
        coder = load_json(review)
        if (coder.get("source_events_sha256") != file_hash(args.coder / "events.jsonl") or
                coder.get("source_response_sha256") != file_hash(args.coder / "response.json")):
            raise ValueError("reassessment source integrity failure")
    if coder.get("passed") is not True:
        raise ValueError("coder preflight must pass before sandbox allocation")
    response = load_json(args.coder / "response.json")
    if not isinstance(response.get("code"), str) or len(response["code"]) > 50000:
        raise ValueError("invalid code artifact")
    budget = PaidBudget(args.budget)
    budget.snapshot()
    root.mkdir(parents=True, exist_ok=False)
    claim = dict(job_id=root.name, code_sha256=file_hash(__file__),
                 candidate_sha256=digest(response), source_coder=str(args.coder),
                 timeout_seconds=TIMEOUT, upper_usd=UPPER_USD, rates=RATES,
                 evidence_class="synthetic-code-execution-preflight", research_result=False,
                 template="base", allow_internet_access=False, secure=True,
                 execution_command=EXECUTION_COMMAND,
                 network={"allow_out": [], "deny_out": ["0.0.0.0/0"], "allow_public_traffic": False})
    fresh_json(root / "claim.json", claim)
    fresh_json(root / "source.json", {"script": Path(__file__).read_text(),
               "harness": HARNESS, "candidate_code": response["code"]})
    from dotenv import dotenv_values
    from e2b import Sandbox
    key = dotenv_values(args.env_file).get("E2B_API_KEY")
    if not key:
        raise ValueError("missing E2B credential")
    # Permanent paid claim precedes any cloud resource creation.
    budget.reserve(root.name, "setup", UPPER_USD, "e2b", digest(claim))
    budget.dispatch(root.name)
    sandbox = None
    started = time.monotonic()
    try:
        sandbox = Sandbox.create(template="base", timeout=TIMEOUT, secure=True,
            api_key=key, allow_internet_access=False, network=claim["network"],
            lifecycle={"on_timeout": "kill", "auto_resume": False},
            metadata={"experiment_id": "kalshi-research-glm53-20260907-01", "job_id": root.name})
        fresh_json(root / "sandbox.json", {"sandbox_id": sandbox.sandbox_id})
        info = sandbox.get_info()
        fresh_json(root / "runtime.json", {"sandbox_id": sandbox.sandbox_id,
            "template_id": info.template_id, "cpu_count": info.cpu_count,
            "memory_mb": info.memory_mb, "started_at": info.started_at.isoformat(),
            "expiry_at": info.end_at.isoformat(), "envd_version": info.envd_version,
            "allow_internet_access": info.allow_internet_access})
        if info.cpu_count > 8 or info.memory_mb > 8192 or info.allow_internet_access is not False:
            raise ValueError("unexpected runtime or internet configuration; kill exact sandbox")
        sandbox.files.write("/tmp/candidate.py", response["code"])
        sandbox.files.write("/tmp/check.py", HARNESS)
        result = sandbox.commands.run(EXECUTION_COMMAND, user="root", timeout=20)
        fresh_json(root / "command.json", {"exit_code": result.exit_code,
                   "stdout": result.stdout, "stderr": result.stderr})
        report = json.loads(sandbox.files.read("/tmp/result.json"))
        report["passed"] = assessment_passes(report, result.exit_code)
        fresh_json(root / "assessment.json", report)
        print(canonical(report), flush=True)
        require_passed(report)  # Raises only after preserving the failed assessment.
    except Exception as error:
        fresh_json(root / "failure.json", {"error_type": type(error).__name__,
                   "elapsed_seconds": time.monotonic() - started})
        raise
    finally:
        if sandbox is not None:
            killed = sandbox.kill()
            fresh_json(root / "cleanup.json", {"sandbox_id": sandbox.sandbox_id,
                "kill_acknowledged": killed, "elapsed_host_seconds": time.monotonic() - started,
                "cost_reconciliation": "runtime invoice unavailable; reservation retained, not reported as spend"})
        # Do not manufacture a terminal metered receipt from a wall-clock guess.
        # The small hold remains until billed runtime/invoice can be reconciled.


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--coder", type=Path, required=True)
    p.add_argument("--budget", type=Path, required=True)
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    main(p.parse_args())
