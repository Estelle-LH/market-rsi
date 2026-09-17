"""Parent-owned, single-B scripted transport canary; live CLI is disabled.

Only the parent admits a global cycle and setup hold.  A child may dispatch
that exact hold and run the synthetic B transport.  After the child is reaped,
the parent independently checks the published source, exact B kill receipt and
provider account-clear readback before conservative upper-bound settlement.
No path here certifies GLM authorship, isolation or a prediction result.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

CODE_ROOT = Path(__file__).resolve().parent.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from market_rsi import digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget
from supervisor_harness import (directional_handoff, one_b_canary_entry,
                                one_b_live_adapter, protocol_source_release)
from supervisor_harness.global_state_gate import SupervisorGlobalState


CHILD_TIMEOUT_SECONDS = one_b_live_adapter.SANDBOX_TIMEOUT_SECONDS + 90
MAX_RECEIPT_BYTES = 256 * 1024
E2B_SDK_VERSION = "2.38.0"
PYTHON_DOTENV_VERSION = "1.2.2"


def _json(root: Path, name: str) -> dict:
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError("missing, symlinked or oversized one-B receipt")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("one-B receipt must be an object")
    return value


def _sha(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError("lowercase SHA256 required")
    return value


def _source_sha256() -> str:
    """Rehash exact current executable sources, including this new runner."""
    names = protocol_source_release.FILES
    required = {"supervisor_harness/one_b_canary_entry.py",
                "supervisor_harness/one_b_canary_runner.py",
                "supervisor_harness/one_b_live_adapter.py",
                "supervisor_harness/directional_handoff.py",
                "supervisor_harness/directional_guest_worker.py"}
    if not required.issubset(names):
        raise ValueError("one-B executable source absent from release manifest")
    return digest(protocol_source_release.source_hashes())


def _input(public_source: str, guest_source_path: Path) -> dict:
    if (not isinstance(public_source, str) or not public_source
            or len(public_source.encode("utf-8")) > 3000):
        raise ValueError("bounded nonempty public source required")
    path = Path(guest_source_path)
    if (path != Path(one_b_live_adapter.__file__).with_name("directional_guest_worker.py")
            or path.is_symlink() or not path.is_file()
            or path.stat().st_size > one_b_live_adapter.MAX_GUEST_SOURCE_BYTES):
        raise ValueError("exact bounded directional guest source required")
    return {"schema": "market_one_b_canary_input_v1",
            "public_source_sha256": hashlib.sha256(public_source.encode()).hexdigest(),
            "guest_source_sha256": file_hash(path),
            "guest_source_path": str(path)}


def _admission(root: Path, budget: PaidBudget,
               state: SupervisorGlobalState, input_sha256: str) -> dict:
    claim = _json(root, "admission.json")
    reserved = _json(root, "reserved.json")
    if (claim.get("cycle_id") != root.name
            or claim.get("input_sha256") != _sha(input_sha256)
            or claim.get("source_sha256") != _source_sha256()
            or claim.get("one_b_synthetic_transport_only") is not True
            or claim.get("model_authorship_proven") is not False
            or claim.get("isolation_proven") is not False
            or reserved != {"schema": "market_one_b_canary_reserved_v1",
                            "admission_sha256": file_hash(root / "admission.json"),
                            "job_id": root.name,
                            "dispatch_permitted_by_this_module": False}
            or state.snapshot()["active_cycle"] != root.name):
        raise ValueError("one-B admission, source or global state changed")
    job = budget.snapshot()["jobs"].get(root.name)
    if (not job or job["state"] != "reserved"
            or job["input_sha256"] != digest(claim)
            or job["upper_usd"] != one_b_canary_entry.UPPER_USD):
        raise ValueError("one-B exact reserved setup hold missing")
    return claim


def _account_receipt(check_account_clear, expected_id: str | None) -> dict:
    result = check_account_clear(expected_id)
    if (not isinstance(result, dict)
            or set(result) != {"clear", "checked_sandbox_id", "active_market_rsi_ids"}
            or result["clear"] is not True
            or result["checked_sandbox_id"] != expected_id
            or result["active_market_rsi_ids"] != []):
        raise RuntimeError("independent E2B account-clear check missing or negative")
    return result


def account_clear_from_provider(sandbox_class, key: str, expected_id: str | None) -> dict:
    """Read every E2B list page; never infer account-clear from B's report."""
    pager = sandbox_class.list(limit=100, api_key=key, request_timeout=15)
    active = []
    seen = set()
    pages = 0
    while pager.has_next:
        pages += 1
        if pages > 100:
            raise RuntimeError("E2B account listing exceeded bounded pages")
        for item in pager.next_items():
            item_id = getattr(item, "sandbox_id", None)
            if not isinstance(item_id, str) or not item_id or item_id in seen:
                raise ValueError("E2B account listing identity missing or duplicated")
            seen.add(item_id)
            metadata = getattr(item, "metadata", None) or {}
            if not isinstance(metadata, dict):
                raise ValueError("E2B account metadata is not an object")
            if str(metadata.get("experiment_id", "")).startswith("market-rsi"):
                active.append(item_id)
    return {"clear": not active, "checked_sandbox_id": expected_id,
            "active_market_rsi_ids": sorted(active)}


def run_child(*, root: Path, budget: PaidBudget, state: SupervisorGlobalState,
              public_source: str, guest_source_path: Path, load_key,
              create_sandbox, check_account_clear, launch_guest=None) -> dict:
    """Exact admitted child; injected boundaries allow fake-only tests."""
    root = Path(root)
    identifier(root.name)
    inputs = _input(public_source, guest_source_path)
    if _json(root, "input.json") != inputs:
        raise ValueError("one-B child input changed")
    _admission(root, budget, state, digest(inputs))
    key = load_key()  # Only after exact admission/source/hold checks.
    if not isinstance(key, str) or not key:
        raise ValueError("E2B credential unavailable after child preflight")
    # Callback captures the child-owned key; no key enters argv or B's env.
    if not callable(create_sandbox) or not callable(check_account_clear):
        raise TypeError("child provider callbacks unavailable")
    budget.dispatch(root.name)
    fresh_json(root / "dispatch.json", {
        "schema": "market_one_b_dispatch_v1", "job_id": root.name,
        "admission_sha256": file_hash(root / "admission.json"),
        "input_sha256": digest(inputs)})
    kwargs = {}
    if launch_guest is not None:
        kwargs["launch_guest"] = launch_guest
    try:
        result = one_b_live_adapter.run_one_b_transport(
            state=state, cycle_id=root.name, input_sha256=digest(inputs),
            public_source=public_source, guest_source_path=guest_source_path,
            receipt_root=root / "transport",
            create_sandbox=lambda: create_sandbox(key),
            check_account_clear=lambda expected_id: check_account_clear(key, expected_id),
            **kwargs)
    except Exception as exc:
        fresh_json(root / "child-failure.json", {
            "schema": "market_one_b_child_failure_v1",
            "error_type": type(exc).__name__, "job_id": root.name})
        raise
    fresh_json(root / "child-result.json", {
        "schema": "market_one_b_child_result_v1", "job_id": root.name,
        "transport_result_sha256": digest(result),
        "source_sha256": _source_sha256()})
    return result


def _review_transport(root: Path, cycle_id: str, input_sha256: str,
                      expected_sandbox_id: str) -> tuple[bool, bool]:
    transport = root / "transport"
    result = _json(transport, "result.json")
    summary = _json(transport / "handoff", "summary.json")
    handoff_manifest = _json(transport / "handoff", "manifest.json")
    child = _json(root, "child-result.json")
    policy = _json(transport, "sandbox-ttl.json")
    echo_accepted = policy.get("policy_echo_accepted") is True
    diagnostic_only = policy.get("synthetic_transport_diagnostic_only") is True
    if (result.get("schema") != "market_one_b_transport_result_v1"
            or result.get("cycle_id") != cycle_id
            or result.get("sandbox_id") != expected_sandbox_id
            or result.get("handoff_summary_sha256") != digest(summary)
            or result.get("guest_command_sha256") != digest(_json(transport, "guest-command.json"))
            or result.get("milestones_sha256") != file_hash(transport / "milestones.json")
            or result.get("callback_visibility_sha256") != file_hash(
                transport / "callback-visibility.json")
            or result.get("cleanup_sha256") != file_hash(transport / "cleanup.json")
            or result.get("sandbox_policy_sha256") != file_hash(
                transport / "sandbox-ttl.json")
            or type(policy.get("policy_echo_accepted")) is not bool
            or type(policy.get("synthetic_transport_diagnostic_only")) is not bool
            or diagnostic_only == echo_accepted
            or result.get("policy_echo_accepted") is not echo_accepted
            or result.get("synthetic_transport_diagnostic_only") is not diagnostic_only
            or result.get("friction_criterion_passed") is not True
            or result.get("synthetic_tasks") is not True
            or result.get("glm_authorship_proven") is not False
            or result.get("isolation_proven") is not False
            or result.get("provider_latency_proven") is not False
            or result.get("cost_verified") is not False
            or summary.get("cycle_id") != cycle_id
            or summary.get("researcher_sandbox_id") != expected_sandbox_id
            or summary.get("source_sha256") != file_hash(directional_handoff.__file__)
            or handoff_manifest.get("input_sha256") != input_sha256
            or handoff_manifest.get("source_sha256") != summary.get("source_sha256")
            or summary.get("friction_criterion_passed") is not True
            or summary.get("sample_count") != 20
            or summary.get("expected_count") != 20
            or summary.get("missing_count") != 0
            or summary.get("duplicate_count") != 0
            or summary.get("timeout_count") != 0
            or child != {"schema": "market_one_b_child_result_v1",
                         "job_id": cycle_id,
                         "transport_result_sha256": digest(result),
                         "source_sha256": _source_sha256()}
            or (transport / "failure.json").exists()
            or (root / "child-failure.json").exists()):
        return False, False
    return True, echo_accepted


def reconcile_reaped(*, root: Path, budget: PaidBudget,
                     state: SupervisorGlobalState, check_account_clear,
                     exit_code: int | None, timed_out: bool,
                     stdout: str | bytes, stderr: str | bytes) -> dict:
    """Only a parent that has waited for its child may call this function."""
    root = Path(root)
    identifier(root.name)
    if state.snapshot()["active_cycle"] != root.name:
        raise ValueError("exact one-B global cycle is not active")
    def output_hash(value):
        raw = value if isinstance(value, bytes) else value.encode()
        return hashlib.sha256(raw).hexdigest()
    fresh_json(root / "parent-process.json", {
        "schema": "market_one_b_parent_process_v1", "job_id": root.name,
        "process_reaped": True, "exit_code": exit_code,
        "timed_out": timed_out, "stdout_sha256": output_hash(stdout),
        "stderr_sha256": output_hash(stderr)})
    job = budget.snapshot()["jobs"].get(root.name)
    if not job:
        raise ValueError("one-B budget job missing")
    if job["state"] == "reserved":
        if (root / "dispatch.json").exists() or (root / "transport").exists():
            raise ValueError("unaccounted one-B child activity before ledger dispatch")
        fresh_json(root / "parent-account-check.json",
                   _account_receipt(check_account_clear, None))
        budget.cancel_before_dispatch(root.name)
        terminal = {"schema": "market_one_b_terminal_v1", "job_id": root.name,
                    "outcome": "failed_before_dispatch",
                    "cost_status": "cancelled_before_dispatch"}
        fresh_json(root / "parent-terminal.json", terminal)
        state.close(root.name, outcome="failed",
                    review_sha256=file_hash(root / "parent-terminal.json"))
        return terminal
    if job["state"] != "dispatched":
        raise ValueError("one-B job already terminal")
    claim = _json(root, "admission.json")
    inputs = _json(root, "input.json")
    if (claim.get("source_sha256") != _source_sha256()
            or claim.get("input_sha256") != digest(inputs)):
        raise ValueError("published one-B executable source/input changed before settlement")
    transport = root / "transport"
    sandbox = _json(transport, "sandbox.json")
    cleanup = _json(transport, "cleanup.json")
    sandbox_id = sandbox.get("sandbox_id")
    if (not isinstance(sandbox_id, str) or not sandbox_id
            or sandbox.get("schema") != "market_one_b_sandbox_v1"
            or cleanup.get("sandbox_id") != sandbox_id
            or cleanup.get("id_unchanged") is not True
            or cleanup.get("kill_acknowledged") is not True
            or cleanup.get("account_clear") is not True
            or _json(transport, "post-account.json") != {
                "clear": True, "checked_sandbox_id": sandbox_id,
                "active_market_rsi_ids": []}):
        raise ValueError("exact B kill/account cleanup missing; hold remains unresolved")
    fresh_json(root / "parent-account-check.json",
               _account_receipt(check_account_clear, sandbox_id))
    # The independent account read and second source rehash are both required
    # before closing any possibly paid dispatch.
    if claim["source_sha256"] != _source_sha256():
        raise ValueError("one-B source changed during parent reconciliation")
    evidence_sha = digest({
        "admission": file_hash(root / "admission.json"),
        "input": file_hash(root / "input.json"),
        "process": file_hash(root / "parent-process.json"),
        "sandbox": file_hash(transport / "sandbox.json"),
        "cleanup": file_hash(transport / "cleanup.json"),
        "child_account": file_hash(transport / "post-account.json"),
        "parent_account": file_hash(root / "parent-account-check.json")})
    budget.settle_uncertain_at_upper(root.name, {
        "terminal_local": True, "process_reaped": True,
        "remote_usage_unknown": True, "automatic_retry": False,
        "evidence_sha256": evidence_sha,
        "note": "One exact B killed, child reaped, account independently clear; upper bound is not an invoice."})
    passed = not timed_out and exit_code == 0
    policy_echo_accepted = False
    if passed:
        try:
            passed, policy_echo_accepted = _review_transport(
                root, root.name, digest(inputs), sandbox_id)
        except (ValueError, KeyError, OSError, TypeError):
            passed = False
    outcome = ("synthetic_transport_observed" if policy_echo_accepted else
               "synthetic_transport_diagnostic_policy_unconfirmed") if passed else "failed"
    terminal = {"schema": "market_one_b_terminal_v1", "job_id": root.name,
                "outcome": outcome,
                "cost_status": "uncertain_upper_bound_not_invoice",
                "evidence_sha256": evidence_sha,
                "policy_echo_accepted": policy_echo_accepted,
                "model_authorship_proven": False, "isolation_proven": False,
                "prediction_result": False}
    fresh_json(root / "parent-terminal.json", terminal)
    state.close(root.name, outcome="passed" if passed and policy_echo_accepted else "failed",
                review_sha256=file_hash(root / "parent-terminal.json"))
    return terminal


def _child_command(*, root: Path, budget: PaidBudget,
                   state: SupervisorGlobalState, guest_source_path: Path,
                   public_source: str, env_file: Path) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), "--child",
            "--output", str(root), "--budget", str(budget.root),
            "--state-root", str(state.root),
            "--decision-doc", str(state.decision_doc),
            "--guest-source", str(guest_source_path),
            "--public-source", public_source, "--env-file", str(env_file),
            "--admit-live"]


def run_parent(*, root: Path, budget: PaidBudget,
               state: SupervisorGlobalState, expected_head_sha256: str,
               prior_fixture_root: Path, release_tag: str,
               expected_source_sha256: str, public_source: str,
               guest_source_path: Path, env_file: Path, load_key,
               check_account_clear, invoke=None,
               dispatch_enabled: bool = False) -> dict:
    """Fake-injectable parent; default does not claim or dispatch paid work."""
    if dispatch_enabled is not True or invoke is None:
        raise RuntimeError("one-B live dispatch disabled pending audited admission")
    root = Path(root)
    identifier(root.name)
    inputs = _input(public_source, guest_source_path)
    if expected_source_sha256 != _source_sha256():
        raise ValueError("one-B current source manifest mismatch")
    one_b_canary_entry.begin_one_b_canary(
        root=root, cycle_id=root.name, state=state, budget=budget,
        expected_head_sha256=expected_head_sha256,
        prior_fixture_root=prior_fixture_root, release_tag=release_tag,
        expected_source_sha256=expected_source_sha256,
        input_sha256=digest(inputs))
    fresh_json(root / "input.json", inputs)
    try:
        key = load_key()  # The only parent credential read; after global claim/hold.
        if not isinstance(key, str) or not key:
            raise ValueError("E2B credential unavailable after admission")
        fresh_json(root / "parent-pre-account.json",
                   _account_receipt(lambda expected_id: check_account_clear(key, expected_id), None))
    except Exception as exc:
        fresh_json(root / "parent-pre-dispatch-failure.json", {
            "schema": "market_one_b_parent_pre_dispatch_failure_v1",
            "job_id": root.name, "error_type": type(exc).__name__})
        budget.cancel_before_dispatch(root.name)
        state.close(root.name, outcome="failed",
                    review_sha256=file_hash(root / "parent-pre-dispatch-failure.json"))
        raise
    command = _child_command(root=root, budget=budget, state=state,
                             guest_source_path=guest_source_path,
                             public_source=public_source, env_file=env_file)
    try:
        child = invoke(command, capture_output=True, text=True,
                       timeout=CHILD_TIMEOUT_SECONDS, check=False)
        exit_code, timed_out = child.returncode, False
        stdout, stderr = child.stdout, child.stderr
    except subprocess.TimeoutExpired as exc:
        # subprocess.run terminates and waits for the direct child first.
        exit_code, timed_out = None, True
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
    except OSError as exc:
        # No child was created. A callback with a different contract must not
        # be used here; this case is specifically subprocess launch failure.
        fresh_json(root / "parent-pre-dispatch-failure.json", {
            "schema": "market_one_b_parent_pre_dispatch_failure_v1",
            "job_id": root.name, "error_type": type(exc).__name__})
        if budget.snapshot()["jobs"][root.name]["state"] != "reserved":
            raise RuntimeError("child launch outcome uncertain; hold remains open") from exc
        budget.cancel_before_dispatch(root.name)
        state.close(root.name, outcome="failed",
                    review_sha256=file_hash(root / "parent-pre-dispatch-failure.json"))
        raise
    return reconcile_reaped(root=root, budget=budget, state=state,
                            check_account_clear=lambda expected_id: check_account_clear(key, expected_id),
                            exit_code=exit_code, timed_out=timed_out,
                            stdout=stdout, stderr=stderr)


def _require_live_runtime() -> None:
    allowed = Path("/Users/estelle/Library/Application Support/MarketRSI").resolve()
    if (sys.prefix == sys.base_prefix
            or not Path(sys.prefix).resolve().is_relative_to(allowed)
            or not Path(sys.executable).absolute().is_relative_to(allowed)
            or importlib.metadata.version("e2b") != E2B_SDK_VERSION
            or importlib.metadata.version("python-dotenv") != PYTHON_DOTENV_VERSION):
        raise ValueError("local-only pinned E2B runtime required")


def _require_local_path(path: Path, label: str) -> None:
    allowed = Path("/Users/estelle/Library/Application Support/MarketRSI").resolve()
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(allowed):
        raise ValueError(f"{label} must be a non-symlink local MarketRSI path")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--decision-doc", type=Path, required=True)
    parser.add_argument("--guest-source", type=Path, required=True)
    parser.add_argument("--public-source", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--prior-fixture", type=Path)
    parser.add_argument("--release-tag")
    parser.add_argument("--source-sha256")
    parser.add_argument("--expected-head-sha256")
    parser.add_argument("--admit-live", action="store_true")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.admit_live:
        raise RuntimeError("one-B paid dispatch requires explicit --admit-live")
    _require_live_runtime()
    for label, path in (("output", args.output), ("budget", args.budget),
                        ("global state", args.state_root),
                        ("decision document", args.decision_doc),
                        ("guest source", args.guest_source),
                        ("environment", args.env_file)):
        _require_local_path(path, label)
    if args.env_file.is_symlink() or not args.env_file.is_file():
        raise ValueError("exact local E2B environment file required")
    from dotenv import dotenv_values
    from e2b import Sandbox
    budget = PaidBudget(args.budget)
    state = SupervisorGlobalState(args.state_root, args.decision_doc)
    load_key = lambda: dotenv_values(args.env_file).get("E2B_API_KEY")
    check_account_clear = lambda key, expected_id: account_clear_from_provider(
        Sandbox, key, expected_id)
    if args.child:
        result = run_child(
            root=args.output, budget=budget, state=state,
            public_source=args.public_source, guest_source_path=args.guest_source,
            load_key=load_key,
            create_sandbox=lambda key: one_b_live_adapter.create_one_b_sandbox(
                Sandbox, key=key, cycle_id=args.output.name),
            check_account_clear=check_account_clear)
    else:
        if not all((args.prior_fixture, args.release_tag,
                    args.source_sha256, args.expected_head_sha256)):
            raise ValueError("one-B parent requires exact fixture, release, source and state head")
        _require_local_path(args.prior_fixture, "prior fixture")
        lock_path = budget.root / "one-b-parent.lock"
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        lock_fd = os.open(lock_path, flags, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = run_parent(
                root=args.output, budget=budget, state=state,
                expected_head_sha256=args.expected_head_sha256,
                prior_fixture_root=args.prior_fixture,
                release_tag=args.release_tag,
                expected_source_sha256=args.source_sha256,
                public_source=args.public_source,
                guest_source_path=args.guest_source, env_file=args.env_file,
                load_key=load_key, check_account_clear=check_account_clear,
                invoke=subprocess.run, dispatch_enabled=True)
        finally:
            os.close(lock_fd)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
