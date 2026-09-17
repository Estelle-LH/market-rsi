"""Parent-owned, scripted A/B E2B protocol canary (never a research round).

The parent alone claims the global state and setup hold, launches one child,
waits for it, checks exact remote cleanup and account state, and then settles.
No result from this canary is a GLM decision or a prediction improvement.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

CODE_ROOT = Path(__file__).resolve().parent.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from data_scientist_harness import literature
from market_rsi import digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget
from supervisor_harness import (e2b_role_network_component as network_component,
                                protocol_canary_entry, protocol_network_probe,
                                protocol_source_release)
from supervisor_harness.global_state_gate import SupervisorGlobalState


TIMEOUT_SECONDS = 180
E2B_SDK_VERSION = "2.38.0"
PYTHON_DOTENV_VERSION = "1.2.2"
NETWORK = {"allow_out": [], "deny_out": ["0.0.0.0/0"],
           "allow_public_traffic": False}
ROLE_MARKERS = {"controller": "/tmp/market-controller-private",
                "researcher": "/tmp/market-researcher-private"}
GUEST_CHECK = '''import json, os, sys
from pathlib import Path
role, peer = sys.argv[1:]
result = {"schema": "market_rsi_guest_boundary_v1", "role": role,
          "peer_file_absent": not Path(peer).exists(),
          "paid_keys_absent": not any(os.environ.get(name) for name in
              ("TINKER_API_KEY", "E2B_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")),
          "host_home_absent": not Path("/Users/estelle").exists()}
print(json.dumps(result, sort_keys=True))
if not all(result[key] for key in
           ("peer_file_absent", "paid_keys_absent", "host_home_absent")):
    sys.exit(17)
'''


def _json(root: Path, name: str) -> dict:
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("missing, symlinked or oversized protocol receipt")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("protocol receipt must be an object")
    return value


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
    if not Path(path).resolve().is_relative_to(allowed):
        raise ValueError(f"{label} must stay on the local MarketRSI volume")


def _bounded_policy_list(value):
    if (isinstance(value, list) and len(value) <= 32
            and all(isinstance(item, str) and len(item) <= 256 for item in value)):
        return value
    return None


def _account_clear(sandbox_class, key: str) -> dict:
    pager = sandbox_class.list(limit=100, api_key=key, request_timeout=15)
    inspected = 0
    while pager.has_next:
        for item in pager.next_items():
            inspected += 1
            metadata = item.metadata or {}
            if str(metadata.get("experiment_id", "")).startswith("market-rsi"):
                raise RuntimeError("a Market RSI E2B sandbox is still active")
    return {"inspected_sandboxes": inspected,
            "active_market_rsi_sandboxes": 0,
            "checked_at_utc": datetime.now(timezone.utc).isoformat()}


def _check_guest(sandbox, role: str, root: Path) -> None:
    peer = ROLE_MARKERS["researcher" if role == "controller" else "controller"]
    sandbox.files.write("/tmp/market-guest-boundary.py", GUEST_CHECK)
    try:
        command = sandbox.commands.run(
            f"python3 -I /tmp/market-guest-boundary.py {role} {peer}", timeout=15)
    except Exception as exc:
        # E2B raises for an ordinary nonzero command; retain only its type.
        fresh_json(root / f"{role}-boundary-failure.json",
                   {"error_type": type(exc).__name__})
        raise
    if (command.exit_code != 0 or not isinstance(command.stdout, str)
            or len(command.stdout.encode()) > 4096):
        raise ValueError("guest boundary check did not terminate cleanly")
    report = json.loads(command.stdout)
    if (report != {"schema": "market_rsi_guest_boundary_v1", "role": role,
                   "peer_file_absent": True, "paid_keys_absent": True,
                   "host_home_absent": True}):
        raise ValueError("guest role boundary check failed")
    fresh_json(root / f"{role}-boundary.json", report)


def _review_complete_diagnostic_report(direction: Path, attempt: dict,
                                       review: dict) -> None:
    """An omitted echo may yield a diagnostic only with four raw probe results."""
    raw = _json(direction, "raw-report.json")
    report = _json(direction, "report.json")
    if set(raw) != {"raw_utf8"} or not isinstance(raw["raw_utf8"], str):
        raise ValueError("raw diagnostic report missing")
    try:
        parsed = json.loads(raw["raw_utf8"])
    except json.JSONDecodeError as exc:
        raise ValueError("raw diagnostic report invalid") from exc
    hashes = report.get("url_sha256")
    observations = report.get("observations")
    marker_sha = attempt.get("marker_sha256")
    if (parsed != report or set(report) != {"schema", "url_sha256", "observations"}
            or report["schema"] != protocol_network_probe.SCHEMA
            or not isinstance(hashes, dict) or set(hashes) != {"public", "peer"}
            or hashes["public"] != attempt.get("public_url_sha256")
            or not all(isinstance(value, str) and len(value) == 64
                       and all(char in "0123456789abcdef" for char in value)
                       for value in hashes.values())
            or not isinstance(marker_sha, str) or len(marker_sha) != 64
            or any(char not in "0123456789abcdef" for char in marker_sha)
            or not isinstance(observations, dict)
            or set(observations) != {"public", "peer"}):
        raise ValueError("incomplete diagnostic report")
    for label in ("public", "peer"):
        modes = observations[label]
        if not isinstance(modes, dict) or set(modes) != set(protocol_network_probe.MODES):
            raise ValueError("missing diagnostic probe mode")
        for mode in protocol_network_probe.MODES:
            protocol_network_probe._validate_observation(modes[mode])
    public_response = any(item["http_response"] for item in observations["public"].values())
    peer_response = any(item["http_response"] for item in observations["peer"].values())
    peer_marker = any(item["http_response"] and not item["body_truncated"]
                      and item["body_sha256"] == marker_sha
                      for item in observations["peer"].values())
    if review != {"schema": "market_rsi_protocol_network_review_v1",
                  "public_http_response_observed": public_response,
                  "peer_http_response_observed": peer_response,
                  "peer_marker_observed": peer_marker,
                  "isolation_proven": False}:
        raise ValueError("diagnostic review differs from raw report")


def _review_observations(root: Path, ids: dict[str, str]) -> bool:
    """Parent rechecks the child evidence before marking an observation complete."""
    child = _json(root, "child-observations.json")
    if (set(child) != {"schema", "a_to_b_sha256", "b_to_a_sha256",
                       "model_authorship_proven", "prediction_result", "isolation_proven"}
            or child["schema"] != "market_rsi_protocol_child_observations_v1"
            or child["model_authorship_proven"] is not False
            or child["prediction_result"] is not False
            or child["isolation_proven"] is not False):
        raise ValueError("child observation claim changed")
    host_read = _json(root, "host-public-read.json")
    if (host_read.get("controller_read_this_source") is not False
            or host_read.get("read_level") != "delivered_text_range_not_proof_of_understanding"
            or not isinstance(host_read.get("receipt"), dict)):
        raise ValueError("broker-positive public read is missing")
    for role in ROLE_MARKERS:
        boundary = _json(root, f"{role}-boundary.json")
        if boundary != {"schema": "market_rsi_guest_boundary_v1", "role": role,
                        "peer_file_absent": True, "paid_keys_absent": True,
                        "host_home_absent": True}:
            raise ValueError("guest role boundary changed")
    missing_allow_out_roles = []
    for role in ROLE_MARKERS:
        observed = _json(root, f"{role}-policy-observed.json")
        verdict = _json(root, f"{role}-policy-verdict.json")
        keys = observed.get("network_keys")
        if (observed.get("role") != role
                or observed.get("sandbox_id") != ids[role]
                or observed.get("allow_internet_access") is not False
                or observed.get("network_response_type") != "dict"
                or not isinstance(keys, list)
                or not all(isinstance(key, str) for key in keys)
                or "deny_out" not in keys
                or observed.get("deny_out") != NETWORK["deny_out"]
                or "allow_public_traffic" not in keys
                or observed.get("allow_public_traffic") is not False):
            raise ValueError("role network policy observation changed")
        missing_allow_out = "allow_out" not in keys
        if ((missing_allow_out and observed.get("allow_out") is not None)
                or (not missing_allow_out
                    and observed.get("allow_out") != NETWORK["allow_out"])):
            raise ValueError("role allow_out observation changed")
        expected_missing = ["allow_out"] if missing_allow_out else []
        if verdict != {"role": role,
                       "observed_sha256": file_hash(root / f"{role}-policy-observed.json"),
                       "contradiction_fields": [], "missing_fields": expected_missing,
                       "policy_echo_accepted": not missing_allow_out,
                       "synthetic_diagnostic_only": missing_allow_out}:
            raise ValueError("role network policy verdict changed")
        if missing_allow_out:
            missing_allow_out_roles.append(role)
    for label, source, target in (("a-to-b", "controller", "researcher"),
                                  ("b-to-a", "researcher", "controller")):
        direction = root / label
        attempt = _json(direction, "attempt.json")
        observation = _json(direction, "observation.json")
        review = _json(direction, "review.json")
        cleanup = _json(direction, "peer-process-cleanup.json")
        local = _json(direction, "peer-local-positive.json")
        if (attempt.get("source_sandbox_id") != ids[source]
                or attempt.get("target_sandbox_id") != ids[target]
                or observation.get("attempt_sha256") != file_hash(direction / "attempt.json")
                or observation.get("local_positive_sha256") != file_hash(direction / "peer-local-positive.json")
                or observation.get("report_sha256") != file_hash(direction / "report.json")
                or observation.get("review_sha256") != file_hash(direction / "review.json")
                or observation.get("cleanup_sha256") != file_hash(direction / "peer-process-cleanup.json")
                or observation.get("no_forbidden_application_payload_observed") is not True
                or observation.get("isolation_proven") is not False
                or child[label.replace("-", "_") + "_sha256"] != digest(observation)
                or local.get("local_service_responded") is not True
                or cleanup.get("kill_acknowledged") is not True
                or review.get("public_http_response_observed") is not False
                or review.get("peer_marker_observed") is not False
                or review.get("isolation_proven") is not False
                or (direction / "failure.json").exists()):
            raise ValueError("directional application/isolation evidence changed")
        if missing_allow_out_roles:
            _review_complete_diagnostic_report(direction, attempt, review)
    diagnostic = root / "policy-diagnostic-summary.json"
    if missing_allow_out_roles:
        if _json(root, diagnostic.name) != {
                "roles": missing_allow_out_roles,
                "child_observations_sha256": file_hash(root / "child-observations.json"),
                "policy_echo_accepted": False, "isolation_proven": False}:
            raise ValueError("incomplete policy diagnostic changed")
    elif diagnostic.exists():
        raise ValueError("unexpected policy diagnostic")
    return not missing_allow_out_roles


def run_child(*, root: Path, budget: PaidBudget, state: SupervisorGlobalState,
              sandbox_class, public_url: str, key: str | None = None,
              load_key=None) -> dict:
    """Execute once after the parent has admitted this exact ID and hold."""
    root = Path(root)
    identifier(root.name)
    protocol_network_probe._url(public_url)
    claim, reserved = _json(root, "admission.json"), _json(root, "reserved.json")
    if (claim.get("cycle_id") != root.name
            or claim.get("source_sha256") != digest(protocol_source_release.source_hashes())
            or claim.get("public_url_sha256") != hashlib.sha256(public_url.encode()).hexdigest()
            or reserved.get("admission_sha256") != file_hash(root / "admission.json")
            or state.snapshot()["active_cycle"] != root.name):
        raise ValueError("child admission/source/global state changed")
    job = budget.snapshot()["jobs"].get(root.name)
    if (not job or job["state"] != "reserved"
            or job["input_sha256"] != digest(claim)):
        raise ValueError("child has no exact reserved setup hold")
    if key is None:
        if load_key is None:
            raise ValueError("child credential loader unavailable")
        key = load_key()
    if not isinstance(key, str) or not key:
        raise ValueError("E2B credential unavailable after child preflight")
    _account_clear(sandbox_class, key)
    # Fail for an unavailable host-side public source before any paid E2B
    # dispatch. The guest never sees the fetched text or transport secrets.
    try:
        host_read = literature.read(public_url, offset=0, limit=512,
                                    transport=literature.bounded_fetch)
    except Exception as exc:
        fresh_json(root / "pre-dispatch-public-read-failure.json",
                   {"error_type": type(exc).__name__})
        raise
    fresh_json(root / "host-public-read.json", {
        "url_sha256": hashlib.sha256(public_url.encode()).hexdigest(),
        "receipt": host_read["receipt"],
        "text_sha256": host_read["text_sha256"],
        "read_level": host_read["read_level"],
        "controller_read_this_source": False})
    # Anything after this boundary may have incurred remote cost. Only the
    # reaped parent may settle; a failed child never cancels this hold.
    budget.dispatch(root.name)
    fresh_json(root / "dispatch.json", {"job_id": root.name,
        "admission_sha256": file_hash(root / "admission.json"),
        "public_url_sha256": hashlib.sha256(public_url.encode()).hexdigest()})
    sandboxes = {}
    unconfirmed_policy_roles = []
    error = None
    stage = "create_controller"
    try:
        for role in ("controller", "researcher"):
            stage = f"create_{role}"
            sandbox = sandbox_class.create(
                template="base", timeout=TIMEOUT_SECONDS, secure=True,
                api_key=key, allow_internet_access=False, network=NETWORK,
                lifecycle={"on_timeout": "kill", "auto_resume": False},
                metadata={"experiment_id": "market-rsi-protocol-canary",
                          "job_id": root.name, "role": role})
            sandboxes[role] = sandbox
            sandbox_id = sandbox.sandbox_id
            if (not isinstance(sandbox_id, str) or not sandbox_id
                    or any(other.sandbox_id == sandbox_id for name, other in sandboxes.items()
                           if name != role)):
                raise ValueError("distinct host-observed E2B sandbox IDs required")
            # Persist the ID before any later get_info/command can fail.
            fresh_json(root / f"{role}-sandbox-id.json",
                       {"role": role, "sandbox_id": sandbox_id})
            stage = f"policy_{role}"
            info = sandbox.get_info()
            network = info.network if isinstance(info.network, dict) else None
            # Persist only bounded nonsecret policy fields *before* enforcing
            # them. The v0.1.0 canary failed at this gate without recording
            # which optional E2B response field differed; do not guess or
            # weaken the gate from that incomplete evidence.
            observed_policy = {"role": role, "sandbox_id": sandbox_id,
                "allow_internet_access": info.allow_internet_access
                    if type(info.allow_internet_access) is bool else None,
                "network_response_type": type(info.network).__name__,
                "network_keys": sorted(str(key)[:64] for key in network)[:32]
                    if network is not None else [],
                "allow_out": _bounded_policy_list(network.get("allow_out"))
                    if network is not None else None,
                "deny_out": _bounded_policy_list(network.get("deny_out"))
                    if network is not None else None,
                "allow_public_traffic": network.get("allow_public_traffic")
                    if network is not None else None,
                "template_id": info.template_id, "envd_version": info.envd_version}
            fresh_json(root / f"{role}-policy-observed.json", observed_policy)
            contradictions, missing = [], []
            if info.allow_internet_access is True:
                contradictions.append("allow_internet_access")
            elif info.allow_internet_access is None:
                missing.append("allow_internet_access")
            elif info.allow_internet_access is not False:
                contradictions.append("allow_internet_access_type")
            if network is None:
                if info.network is None:
                    missing.append("network_response")
                else:
                    contradictions.append("network_response_type")
            else:
                for name in ("allow_out", "deny_out", "allow_public_traffic"):
                    if name not in network:
                        missing.append(name)
                    elif network[name] != NETWORK[name]:
                        contradictions.append(name)
            fresh_json(root / f"{role}-policy-verdict.json", {
                "role": role, "observed_sha256": file_hash(root / f"{role}-policy-observed.json"),
                "contradiction_fields": contradictions, "missing_fields": missing,
                "policy_echo_accepted": not contradictions and not missing,
                "synthetic_diagnostic_only": bool(missing)})
            if contradictions:
                raise ValueError("E2B explicitly contradicted requested role network policy")
            if missing:
                # get_info() may omit optional network fields. Gather only the
                # predeclared synthetic application probes, with no provider
                # keys or protected data in either guest. Missing echo still
                # fails this canary after the probes; never promote it to a
                # live-controller or isolation pass.
                unconfirmed_policy_roles.append(role)
        for role, sandbox in sandboxes.items():
            sandbox.files.write(ROLE_MARKERS[role], role)
        for role, sandbox in sandboxes.items():
            stage = f"guest_boundary_{role}"
            _check_guest(sandbox, role, root)
        stage = "a_to_b_application_probe"
        first = network_component.observe_direction(
            source=sandboxes["controller"], target=sandboxes["researcher"],
            state=state, cycle_id=root.name, public_url=public_url,
            receipt_root=root / "a-to-b")
        stage = "b_to_a_application_probe"
        second = network_component.observe_direction(
            source=sandboxes["researcher"], target=sandboxes["controller"],
            state=state, cycle_id=root.name, public_url=public_url,
            receipt_root=root / "b-to-a")
        fresh_json(root / "child-observations.json", {
            "schema": "market_rsi_protocol_child_observations_v1",
            "a_to_b_sha256": digest(first), "b_to_a_sha256": digest(second),
            "model_authorship_proven": False, "prediction_result": False,
            "isolation_proven": False})
        if unconfirmed_policy_roles:
            stage = "policy_unconfirmed_after_synthetic_probes"
            fresh_json(root / "policy-diagnostic-summary.json", {
                "roles": unconfirmed_policy_roles,
                "child_observations_sha256": file_hash(root / "child-observations.json"),
                "policy_echo_accepted": False, "isolation_proven": False})
            if any(_json(root, f"{role}-policy-verdict.json")["missing_fields"]
                   != ["allow_out"] for role in unconfirmed_policy_roles):
                raise ValueError("E2B network policy echo unconfirmed after synthetic probes")
    except Exception as exc:
        error = exc
        fresh_json(root / "child-failure.json", {
            "stage": stage, "error_type": type(exc).__name__})
    finally:
        cleanup = {}
        for role, sandbox in reversed(list(sandboxes.items())):
            try:
                cleanup[role] = {"sandbox_id": sandbox.sandbox_id,
                                 "kill_acknowledged": sandbox.kill() is True}
            except Exception as exc:
                cleanup[role] = {"sandbox_id": sandbox.sandbox_id,
                                 "kill_acknowledged": False,
                                 "error_type": type(exc).__name__}
        fresh_json(root / "child-cleanup.json", cleanup)
    if error is not None:
        raise error
    if (set(cleanup) != {"controller", "researcher"}
            or not all(item["kill_acknowledged"] for item in cleanup.values())):
        raise RuntimeError("exact A/B E2B cleanup not acknowledged")
    return _json(root, "child-observations.json")


def reconcile_reaped(*, root: Path, budget: PaidBudget, state: SupervisorGlobalState,
                     sandbox_class, key: str, exit_code: int | None,
                     timed_out: bool, stdout: str | bytes, stderr: str | bytes) -> dict:
    """The parent runs this only after subprocess.run has waited for its child."""
    root = Path(root)
    identifier(root.name)
    if state.snapshot()["active_cycle"] != root.name:
        raise ValueError("exact global cycle is not active")
    def output_hash(value):
        return hashlib.sha256(value if isinstance(value, bytes)
                              else value.encode()).hexdigest()
    fresh_json(root / "parent-process.json", {
        "schema": "market_rsi_protocol_parent_process_v1", "job_id": root.name,
        "process_reaped": True, "exit_code": exit_code, "timed_out": timed_out,
        "stdout_sha256": output_hash(stdout), "stderr_sha256": output_hash(stderr)})
    job = budget.snapshot()["jobs"].get(root.name)
    if not job:
        raise ValueError("protocol job missing from budget")
    if job["state"] == "reserved":
        # No remote call was dispatched by this job; a child may have failed
        # during its preflight. Require a clear account and no role ID before
        # treating that ledger state as evidence of zero remote work.
        if any((root / f"{role}-sandbox-id.json").exists() for role in ROLE_MARKERS):
            raise ValueError("role sandbox ID exists before ledger dispatch")
        account = _account_clear(sandbox_class, key)
        fresh_json(root / "parent-account-check.json", account)
        budget.cancel_before_dispatch(root.name)
        result = {"schema": "market_rsi_protocol_terminal_v1", "job_id": root.name,
                  "outcome": "failed_before_dispatch", "cost_status": "cancelled_before_dispatch"}
        fresh_json(root / "parent-terminal.json", result)
        state.close(root.name, outcome="failed",
                    review_sha256=file_hash(root / "parent-terminal.json"))
        return result
    if job["state"] != "dispatched":
        raise ValueError("protocol job was already terminal")
    claim = _json(root, "admission.json")
    if (claim.get("source_sha256") != digest(protocol_source_release.source_hashes())
            or claim.get("cycle_id") != root.name):
        raise ValueError("published source changed before terminal review")
    cleanup = _json(root, "child-cleanup.json")
    if not cleanup or not set(cleanup).issubset(ROLE_MARKERS):
        raise ValueError("no exact E2B cleanup evidence; hold remains open")
    ids = []
    for role, item in cleanup.items():
        observed = _json(root, f"{role}-sandbox-id.json")
        if (observed != {"role": role, "sandbox_id": item.get("sandbox_id")}
                or item.get("kill_acknowledged") is not True):
            raise ValueError("role sandbox cleanup unverified; hold remains open")
        ids.append(item["sandbox_id"])
    if len(set(ids)) != len(ids):
        raise ValueError("role sandboxes reused an ID")
    account = _account_clear(sandbox_class, key)
    fresh_json(root / "parent-account-check.json", account)
    evidence_sha = digest({"admission": file_hash(root / "admission.json"),
        "process": file_hash(root / "parent-process.json"),
        "cleanup": file_hash(root / "child-cleanup.json"),
        "account": file_hash(root / "parent-account-check.json")})
    budget.settle_uncertain_at_upper(root.name, {
        "terminal_local": True, "process_reaped": True,
        "remote_usage_unknown": True, "automatic_retry": False,
        "evidence_sha256": evidence_sha,
        "note": "Exact child reaped; observed role sandboxes killed; account clear; upper bound is not invoice."})
    passed = (not timed_out and exit_code == 0
              and set(cleanup) == set(ROLE_MARKERS)
              and (root / "child-observations.json").is_file()
              and not (root / "child-failure.json").exists())
    policy_complete = False
    if passed:
        try:
            policy_complete = _review_observations(
                root, {role: item["sandbox_id"] for role, item in cleanup.items()})
        except (ValueError, KeyError, OSError, TypeError):
            passed = False
    outcome = ("protocol_observed" if policy_complete else
               "diagnostic_completed_policy_unconfirmed") if passed else "failed"
    result = {"schema": "market_rsi_protocol_terminal_v1", "job_id": root.name,
              "outcome": outcome,
              "cost_status": "uncertain_upper_bound_not_invoice",
              "evidence_sha256": evidence_sha, "model_authorship_proven": False,
              "prediction_result": False,
              "isolation_proven": False}
    fresh_json(root / "parent-terminal.json", result)
    # A completed diagnostic with an omitted optional policy echo is not a
    # passed global cycle. Neither terminal outcome is an isolation pass.
    state.close(root.name, outcome="passed" if passed and policy_complete else "failed",
                review_sha256=file_hash(root / "parent-terminal.json"))
    return result


def run_parent(*, root: Path, budget: PaidBudget, state: SupervisorGlobalState,
               sandbox_class, load_key, public_url: str,
               expected_head_sha256: str, prior_fixture_root: Path,
               release_tag: str, expected_source_sha256: str,
               command: list[str], invoke=subprocess.run) -> dict:
    protocol_network_probe._url(public_url)
    protocol_canary_entry.begin_protocol_canary(
        root=root, cycle_id=Path(root).name, state=state, budget=budget,
        expected_head_sha256=expected_head_sha256,
        prior_fixture_root=prior_fixture_root, release_tag=release_tag,
        expected_source_sha256=expected_source_sha256,
        public_url=public_url)
    try:
        key = load_key()
        if not isinstance(key, str) or not key:
            raise ValueError("E2B credential unavailable after admission")
    except Exception as exc:
        # There was no child or remote dispatch. Never mark a nonexistent
        # process as reaped, and never leave an ordinary missing-key hold open.
        fresh_json(Path(root) / "parent-pre-dispatch-failure.json",
                   {"job_id": Path(root).name, "error_type": type(exc).__name__})
        budget.cancel_before_dispatch(Path(root).name)
        state.close(Path(root).name, outcome="failed",
                    review_sha256=file_hash(Path(root) / "parent-pre-dispatch-failure.json"))
        raise
    try:
        child = invoke(command, capture_output=True, text=True,
                       timeout=2 * TIMEOUT_SECONDS + 90, check=False)
        exit_code, timed_out = child.returncode, False
        stdout, stderr = child.stdout, child.stderr
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and waits for the direct child before raising.
        exit_code, timed_out = None, True
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
    except OSError as exc:
        # subprocess.run did not create a child; no remote request can have
        # been made by this job. Preserve and cancel the exact reserved ID.
        fresh_json(Path(root) / "parent-pre-dispatch-failure.json",
                   {"job_id": Path(root).name, "error_type": type(exc).__name__})
        budget.cancel_before_dispatch(Path(root).name)
        state.close(Path(root).name, outcome="failed",
                    review_sha256=file_hash(Path(root) / "parent-pre-dispatch-failure.json"))
        raise
    return reconcile_reaped(root=root, budget=budget, state=state,
                            sandbox_class=sandbox_class, key=key,
                            exit_code=exit_code, timed_out=timed_out,
                            stdout=stdout, stderr=stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--decision-doc", type=Path, required=True)
    parser.add_argument("--prior-fixture", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--expected-head-sha256", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    _require_live_runtime()
    for label, path in (("output", args.output), ("budget", args.budget),
                        ("global state", args.state_root),
                        ("decision document", args.decision_doc),
                        ("prior fixture", args.prior_fixture)):
        _require_local_path(path, label)
    budget = PaidBudget(args.budget)
    state = SupervisorGlobalState(args.state_root, args.decision_doc)
    if args.child:
        from dotenv import dotenv_values
        from e2b import Sandbox
        result = run_child(root=args.output, budget=budget, state=state,
            sandbox_class=Sandbox, public_url=args.public_url,
            load_key=lambda: dotenv_values(args.env_file).get("E2B_API_KEY"))
    else:
        # This lock prevents two local parents from racing around a provider
        # call. The global-state claim separately blocks different entry paths.
        lock_path = budget.root / "protocol-canary-parent.lock"
        with lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            from dotenv import dotenv_values
            from e2b import Sandbox
            command = [sys.executable, str(Path(__file__).resolve()),
                "--output", str(args.output), "--budget", str(args.budget),
                "--state-root", str(args.state_root), "--decision-doc", str(args.decision_doc),
                "--prior-fixture", str(args.prior_fixture), "--release-tag", args.release_tag,
                "--source-sha256", args.source_sha256,
                "--expected-head-sha256", args.expected_head_sha256,
                "--public-url", args.public_url, "--env-file", str(args.env_file), "--child"]
            # Admission precedes credential reading; no key is passed in
            # argv. The child independently checks the exact reservation.
            result = run_parent(root=args.output, budget=budget, state=state,
                sandbox_class=Sandbox,
                load_key=lambda: dotenv_values(args.env_file).get("E2B_API_KEY"),
                public_url=args.public_url,
                expected_head_sha256=args.expected_head_sha256,
                prior_fixture_root=args.prior_fixture,
                release_tag=args.release_tag,
                expected_source_sha256=args.source_sha256,
                command=command)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
