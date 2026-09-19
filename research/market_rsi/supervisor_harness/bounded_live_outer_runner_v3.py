"""Supervisor transaction around the v2 one-sample Controller -> B adapter.

This module deliberately has no CLI.  It owns publication, global-state and
budget admission around exactly one adapter call.  It does not load provider
credentials, start Docker itself, or make a publication decision.  Until this
file is in an exact published protocol manifest, the production path fails at
the publication gate; offline tests inject only the existing strict fakes.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from glm_canary import MODEL, RATES, cost
from market_rsi import digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget, money
from supervisor_harness import bounded_live_adapter_v2 as adapter
from supervisor_harness import frozen_glm_first_response as first
from supervisor_harness import global_state_gate
from supervisor_harness import local_b_container
from supervisor_harness import protocol_source_release


OUTER_SCHEMA = "market_bounded_live_outer_v3"
RESULT_SCHEMA = "market_bounded_live_outer_result_v3"
PREFLIGHT_SCHEMA = "market_bounded_live_outer_preflight_v3"
BUCKET = "setup"
PROVIDER = "tinker"
UPPER_USD = Decimal("0.05")
ZERO = "0" * 64
HERE = Path(__file__).resolve()
SOURCE_ROOT = HERE.parents[1]
REQUIRED_SOURCE_FILES = (
    "paid_budget.py",
    "supervisor_harness/bounded_live_adapter_v2.py",
    "supervisor_harness/bounded_live_outer_runner_v3.py",
    "supervisor_harness/directional_guest_worker.py",
    "supervisor_harness/frozen_glm_first_response.py",
    "supervisor_harness/global_state_gate.py",
    "supervisor_harness/local_b_container.py",
    "supervisor_harness/protocol_source_release.py",
)


def _sha(value, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def _load(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError(f"unsafe or missing receipt: {path.name}")
    return load_json(path)


def _current_required_hashes() -> dict[str, str]:
    hashes = {}
    for name in REQUIRED_SOURCE_FILES:
        path = SOURCE_ROOT / name
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError("required outer-runner source is missing or noncanonical")
        hashes[name] = file_hash(path)
    return hashes


def runtime_receipt() -> dict:
    """Current values that the caller must pin before admission."""
    return {
        "schema": "market_bounded_live_outer_runtime_v3",
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "container_image": local_b_container.IMAGE,
        "runner_sha256": file_hash(HERE),
        "adapter_sha256": file_hash(adapter.__file__),
        "guest_sha256": file_hash(adapter.GUEST_SOURCE),
    }


def _publication(tag: str, expected_source_sha256: str) -> dict:
    receipt = protocol_source_release.verify_published(
        tag=tag, expected_source_sha256=_sha(expected_source_sha256, "source manifest"))
    required = {
        "schema", "origin", "tag", "commit", "tag_object", "source_sha256",
        "source_hashes", "isolation_proven", "model_authorship_proven",
    }
    if (not isinstance(receipt, dict) or set(receipt) != required
            or receipt.get("schema") != "market_rsi_protocol_publication_v1"
            or receipt.get("origin") != protocol_source_release.ORIGIN
            or receipt.get("tag") != tag
            or receipt.get("source_sha256") != expected_source_sha256
            or receipt.get("isolation_proven") is not False
            or receipt.get("model_authorship_proven") is not False
            or any(not isinstance(receipt.get(key), str)
                   or len(receipt[key]) != 40
                   or any(c not in "0123456789abcdef" for c in receipt[key])
                   for key in ("commit", "tag_object"))
            or not isinstance(receipt.get("source_hashes"), dict)
            or digest(receipt["source_hashes"]) != expected_source_sha256):
        raise ValueError("publication receipt is incomplete or changed")
    current = _current_required_hashes()
    if any(receipt["source_hashes"].get(name) != value
           for name, value in current.items()):
        raise ValueError("published source is stale, incomplete or altered")
    return receipt


def _packet(packet: dict, cycle_id: str) -> dict:
    packet = first._packet(packet, cycle_id)
    if (len(packet["context_items"]) != 1
            or packet["context_items"][0]["role"] != "synthetic_fixture"):
        raise ValueError("one frozen synthetic public item is required")
    return packet


def _runtime(expected: dict) -> dict:
    observed = runtime_receipt()
    if not isinstance(expected, dict) or expected != observed:
        raise ValueError("pinned runtime, image or executable source changed")
    return observed


def _clear(check_clear, cycle_id: str) -> dict:
    value = check_clear(cycle_id)
    if (not isinstance(value, dict)
            or set(value) != {"schema", "cycle_id", "clear",
                              "matching_process_ids", "matching_container_ids"}
            or value.get("schema") != PREFLIGHT_SCHEMA
            or value.get("cycle_id") != cycle_id
            or value.get("clear") is not True
            or value.get("matching_process_ids") != []
            or value.get("matching_container_ids") != []):
        raise ValueError("matching process/container exists or preflight is incomplete")
    return value


def _budget_snapshot(budget: PaidBudget, expected_root: Path,
                     experiment_id: str, cap_usd, cycle_id: str,
                     *, state: str | None = None) -> dict:
    if (type(budget) is not PaidBudget
            or budget.root.resolve() != Path(expected_root).resolve()
            or budget.root.is_symlink()):
        raise ValueError("sole exact PaidBudget authority required")
    value = budget.snapshot()
    cap = money(cap_usd)
    if (value.get("experiment_id") != experiment_id
            or money(value.get("cap_usd")) != cap
            or BUCKET not in value.get("buckets", {})):
        raise ValueError("budget authorization, cap or category changed")
    if state is None:
        if (cycle_id in value.get("jobs", {})
                or money(value.get("available_usd")) < UPPER_USD
                or money(value["buckets"][BUCKET].get("available_usd")) < UPPER_USD):
            raise ValueError("reused job or inadequate global/category budget")
    else:
        job = value.get("jobs", {}).get(cycle_id)
        if (not isinstance(job, dict) or job.get("state") != state
                or job.get("bucket") != BUCKET
                or money(job.get("upper_usd")) != UPPER_USD
                or job.get("provider") != PROVIDER):
            raise ValueError("exact sole budget job changed")
    return value


def _state_snapshot(state: global_state_gate.SupervisorGlobalState,
                    cycle_id: str, expected_head_sha256: str,
                    expected_decision_sha256: str, *, claimed: bool = False) -> dict:
    if type(state) is not global_state_gate.SupervisorGlobalState:
        raise ValueError("exact SupervisorGlobalState required")
    value = state.snapshot()
    if (value.get("decision_doc_sha256") != _sha(
            expected_decision_sha256, "decision document")
            or (not claimed and value.get("head_sha256") != _sha(
                expected_head_sha256, "state head"))
            or value.get("active_cycle") != (cycle_id if claimed else None)
            or (not claimed and cycle_id in value.get("claimed_cycles", []))):
        raise ValueError("global state is changed, active or reuses this ID")
    return value


def _write_failure(root: Path, cycle_id: str, stage: str, error: Exception,
                   *, adapter_calls: int, ledger_state: str,
                   supervisor_state: str) -> Path:
    path = root / "outer-failure.json"
    if not path.exists():
        fresh_json(path, {
            "schema": "market_bounded_live_outer_failure_v3",
            "cycle_id": cycle_id, "stage": stage,
            "error_type": type(error).__name__,
            "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
            "adapter_calls": adapter_calls, "automatic_retry": False,
            "ledger_state": ledger_state, "supervisor_state": supervisor_state,
        })
    return path


def _replace_json(path: Path, value: dict) -> None:
    """Atomically install the final receipt, replacing any provisional one."""
    stage = path.with_name("." + path.name + ".final")
    fresh_json(stage, value)
    stage.replace(path)


def _reconciliation_error(action: str, error: Exception) -> dict:
    return {
        "action": action, "error_type": type(error).__name__,
        "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
    }


def _pre_dispatch_failure(*, root: Path, cycle_id: str, stage: str,
                          primary: Exception, adapter_calls: int,
                          reserved: bool, budget: PaidBudget,
                          state: global_state_gate.SupervisorGlobalState) -> Path:
    """Reconcile no-send state first, then record authoritative final state."""
    errors = []
    cancel_attempted = reserved
    cancel_succeeded = False
    if reserved:
        try:
            budget.cancel_before_dispatch(cycle_id)
            cancel_succeeded = True
        except Exception as exc:
            errors.append(_reconciliation_error("cancel_before_dispatch", exc))

    close_attempted = False
    close_succeeded = False
    close_already_observed = False
    try:
        before_close = state.snapshot()
        if before_close.get("active_cycle") == cycle_id:
            close_attempted = True
            try:
                state.close(cycle_id, outcome="failed")
                close_succeeded = True
            except Exception as exc:
                errors.append(_reconciliation_error("state_close_failed", exc))
        elif cycle_id in before_close.get("completed_cycles", []):
            close_already_observed = True
        else:
            errors.append(_reconciliation_error(
                "state_close_not_owned",
                RuntimeError("claimed cycle is neither active nor completed")))
    except Exception as exc:
        errors.append(_reconciliation_error("state_snapshot_before_close", exc))

    budget_snapshot = None
    try:
        budget_snapshot = budget.snapshot()
        job = budget_snapshot.get("jobs", {}).get(cycle_id)
        ledger_state = job.get("state") if isinstance(job, dict) else "absent"
        budget_snapshot_sha = digest(budget_snapshot)
    except Exception as exc:
        errors.append(_reconciliation_error("budget_snapshot_final", exc))
        ledger_state = "snapshot_unavailable"
        budget_snapshot_sha = None

    state_snapshot = None
    try:
        state_snapshot = state.snapshot()
        active = state_snapshot.get("active_cycle")
        completed = state_snapshot.get("completed_cycles", [])
        if active == cycle_id:
            supervisor_state = "active_unresolved"
        elif cycle_id in completed:
            # A zero review can only represent a failed close.  Nonzero prior
            # closure is still terminal but its outcome is not exposed by the
            # public snapshot contract.
            supervisor_state = (
                "closed_failed" if state_snapshot.get("last_review_sha256") == ZERO
                else "closed_observed")
        elif active is None:
            supervisor_state = "inactive_unresolved"
        else:
            supervisor_state = "other_cycle_active"
        state_snapshot_sha = digest(state_snapshot)
    except Exception as exc:
        errors.append(_reconciliation_error("state_snapshot_final", exc))
        supervisor_state = "snapshot_unavailable"
        state_snapshot_sha = None

    path = root / "outer-failure.json"
    _replace_json(path, {
        "schema": "market_bounded_live_outer_failure_v3",
        "cycle_id": cycle_id, "stage": stage,
        "error_type": type(primary).__name__,
        "error_sha256": hashlib.sha256(str(primary).encode()).hexdigest(),
        "adapter_calls": adapter_calls, "automatic_retry": False,
        "pre_dispatch": True,
        "cancel_attempted": cancel_attempted,
        "cancel_succeeded": cancel_succeeded,
        "close_attempted": close_attempted,
        "close_succeeded": close_succeeded,
        "close_already_observed": close_already_observed,
        "ledger_state": ledger_state,
        "supervisor_state": supervisor_state,
        "budget_snapshot_sha256": budget_snapshot_sha,
        "supervisor_snapshot_sha256": state_snapshot_sha,
        "reconciliation_errors": errors,
    })
    return path


def _local_terminal(adapter_root: Path, cycle_id: str) -> tuple[
        bool, dict | None, dict | None]:
    try:
        process = _load(adapter_root / "process.json")
        cleanup = _load(adapter_root / "cleanup.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return False, None, None
    process_keys = {"schema", "container_name", "exit_code", "timed_out",
                    "process_reaped", "stdout_bytes", "stderr_bytes",
                    "stdout_sha256", "stderr_sha256", "expected_orders",
                    "offline_fake"}
    cleanup_keys = {"schema", "container_name", "initial_inspection",
                    "stop_acknowledged", "final_inspection", "process_reaped",
                    "exact_container_cleanup_verified", "offline_fake"}
    process_ok = (isinstance(process, dict) and set(process) == process_keys
                  and process.get("schema") == adapter.PROCESS_SCHEMA
                  and process.get("process_reaped") is True
                  and process.get("expected_orders") == 1
                  and type(process.get("timed_out")) is bool
                  and (process.get("exit_code") is None
                       or type(process.get("exit_code")) is int)
                  and all(type(process.get(key)) is int
                          and 0 <= process[key] <= adapter.MAX_STDIO_BYTES
                          for key in ("stdout_bytes", "stderr_bytes"))
                  and all(isinstance(process.get(key), str)
                          and len(process[key]) == 64
                          and not any(c not in "0123456789abcdef"
                                      for c in process[key])
                          for key in ("stdout_sha256", "stderr_sha256"))
                  and type(process.get("offline_fake")) is bool)
    cleanup_ok = (isinstance(cleanup, dict) and set(cleanup) == cleanup_keys
                  and cleanup.get("schema") == adapter.CLEANUP_SCHEMA
                  and cleanup.get("process_reaped") is True
                  and cleanup.get("exact_container_cleanup_verified") is True
                  and cleanup.get("final_inspection") == "absent"
                  and type(cleanup.get("stop_acknowledged")) is bool
                  and type(cleanup.get("offline_fake")) is bool
                  and cleanup.get("offline_fake") == process.get("offline_fake")
                  and cleanup.get("container_name") == process.get("container_name"))
    launch_path = adapter_root / "b-launch.json"
    if launch_path.exists() or launch_path.is_symlink():
        try:
            launch = _load(launch_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False, process, cleanup
        launch_keys = {"schema", "cycle_id", "container_name", "image", "command",
                       "expected_orders", "guest_source_sha256",
                       "credential_fields_passed_to_b", "runtime_root", "offline_fake"}
        launch_ok = (isinstance(launch, dict) and set(launch) == launch_keys
                     and launch.get("schema") == adapter.LAUNCH_SCHEMA
                     and launch.get("cycle_id") == cycle_id
                     and launch.get("container_name") == process.get("container_name")
                     and launch.get("image") == local_b_container.IMAGE
                     and launch.get("expected_orders") == 1
                     and launch.get("guest_source_sha256")
                     == file_hash(adapter.GUEST_SOURCE)
                     and launch.get("credential_fields_passed_to_b") == []
                     and launch.get("offline_fake") == process.get("offline_fake"))
    else:
        # This includes a provider failure before B and a launch exception whose
        # exact process/container were nevertheless reaped by the adapter.
        launch_ok = True
    return process_ok and cleanup_ok and launch_ok, process, cleanup


def _provider(adapter_root: Path, upper_usd: Decimal) -> dict | None:
    try:
        value = _load(adapter_root / "provider-receipt.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    keys = {"schema", "requested_model", "reported_model", "input_tokens",
            "output_tokens", "cached_input_tokens", "finish_reason", "terminal",
            "rates", "metered_cost_usd_not_invoice", "cost_basis",
            "provider_called", "automatic_retry", "sample_count",
            "provider_session_id", "sampling_session_id",
            "output_token_ids_sha256"}
    try:
        metered = money(value.get("metered_cost_usd_not_invoice"))
        recomputed = cost(value.get("input_tokens"), value.get("output_tokens"),
                          value.get("cached_input_tokens"))
        raw = _load(adapter_root / "raw-response.json")
        valid_raw, _reason = first._review_sample(raw, value.get("input_tokens"))
    except Exception:
        return None
    if (not isinstance(value, dict) or set(value) != keys
            or value.get("schema") != adapter.PROVIDER_RECEIPT_SCHEMA
            or value.get("requested_model") != MODEL
            or value.get("reported_model") not in {MODEL, adapter.HF_MODEL}
            or value.get("finish_reason") != "stop"
            or value.get("terminal") is not True
            or value.get("rates") != RATES
            or value.get("cost_basis")
            != "returned token quantities x frozen rates; not invoice"
            or value.get("automatic_retry") is not False
            or value.get("sample_count") != 1
            or type(value.get("provider_called")) is not bool
            or not all(isinstance(value.get(key), str) and value[key]
                       and len(value[key]) <= 128
                       for key in ("provider_session_id", "sampling_session_id"))
            or type(value.get("input_tokens")) is not int
            or type(value.get("output_tokens")) is not int
            or type(value.get("cached_input_tokens")) is not int
            or not valid_raw
            or len(raw["output_tokens"]) != value["output_tokens"]
            or raw["cached_input_tokens"] != value["cached_input_tokens"]
            or raw["finish_reason"] != value["finish_reason"]
            or raw["provider"]["reported_model"] != value["reported_model"]
            or raw["provider"]["session_id"] != value["provider_session_id"]
            or raw["provider"]["sampling_session_id"]
            != value["sampling_session_id"]
            or digest(raw["output_tokens"]) != value.get("output_token_ids_sha256")
            or metered != recomputed or metered > upper_usd):
        return None
    return value


def _adapter_success(adapter_root: Path, claim_root: Path, result, provider: dict,
                     process: dict, cleanup: dict, cycle_id: str,
                     execution_mode: str) -> bool:
    try:
        keys = {"schema", "cycle_id", "passed_offline_boundary_test",
                "completed_live_chain_pending_review", "execution_mode",
                "failure_type", "artifact_sha256", "registry_claim_sha256",
                "requested_model", "reported_model", "input_tokens",
                "output_tokens", "cached_input_tokens",
                "metered_cost_usd_not_invoice", "provider_called",
                "automatic_retry", "sample_count_max", "b_task_count_max",
                "exact_container_cleanup_verified",
                "model_identity_independently_proven",
                "model_authorship_independently_proven", "full_isolation_proven",
                "formal_admission", "budget_mutated_by_adapter"}
        if (not isinstance(result, dict) or set(result) != keys
                or result.get("schema") != adapter.RESULT_SCHEMA
                or result.get("cycle_id") != cycle_id
                or result.get("execution_mode") != execution_mode
                or result.get("passed_offline_boundary_test")
                is not (execution_mode == "offline_fake")
                or result.get("completed_live_chain_pending_review")
                is not (execution_mode == "live_pinned")
                or result.get("failure_type") is not None
                or result.get("automatic_retry") is not False
                or result.get("sample_count_max") != 1
                or result.get("b_task_count_max") != 1
                or result.get("exact_container_cleanup_verified") is not True
                or result.get("requested_model") != MODEL
                or result.get("metered_cost_usd_not_invoice")
                != provider["metered_cost_usd_not_invoice"]
                or result.get("reported_model") != provider["reported_model"]
                or result.get("input_tokens") != provider["input_tokens"]
                or result.get("output_tokens") != provider["output_tokens"]
                or result.get("cached_input_tokens")
                != provider["cached_input_tokens"]
                or result.get("provider_called")
                is not (execution_mode == "live_pinned")
                or result.get("budget_mutated_by_adapter") is not False
                or any(result.get(key) is not False for key in (
                    "model_identity_independently_proven",
                    "model_authorship_independently_proven", "full_isolation_proven",
                    "formal_admission"))):
            return False
        artifacts = result.get("artifact_sha256")
        expected_names = {
            "claim.json", "input.json", "request.json", "encoded.json",
            "cost-preview.json", "raw-response.json", "raw-response.txt",
            "provider-receipt.json", "decision.json", "broker-binding.json",
            "task.json", "order.json", "b-launch.json", "raw-ack.json",
            "raw-event.json", "process.json", "cleanup.json",
        }
        if not isinstance(artifacts, dict) or set(artifacts) != expected_names:
            return False
        for name, expected in artifacts.items():
            path = adapter_root / name
            if expected is None:
                if path.exists() or path.is_symlink():
                    return False
            elif _sha(expected, "adapter artifact") != file_hash(path):
                return False
        registry = claim_root / f"{cycle_id}.json"
        if result.get("registry_claim_sha256") != file_hash(registry):
            return False
        return (process.get("exit_code") == 0
                and process.get("timed_out") is False
                and cleanup.get("final_inspection") == "absent")
    except Exception:
        return False


def _unresolved(root: Path, cycle_id: str, stage: str, error: Exception,
                adapter_calls: int, adapter_root: Path) -> None:
    evidence = {
        "schema": "market_bounded_live_outer_unresolved_v3",
        "cycle_id": cycle_id, "stage": stage,
        "error_type": type(error).__name__,
        "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
        "adapter_calls": adapter_calls, "automatic_retry": False,
        "ledger_state": "dispatched_unresolved",
        "supervisor_state": "active_unresolved",
        "preserved_adapter_files": sorted(
            item.name for item in adapter_root.iterdir()
            if item.is_file() and not item.is_symlink()) if adapter_root.is_dir() else [],
    }
    fresh_json(root / "outer-unresolved.json", evidence)


def run_outer(*, root: Path, adapter_claim_root: Path,
              state: global_state_gate.SupervisorGlobalState,
              budget: PaidBudget, budget_root: Path, experiment_id: str,
              budget_cap_usd, cycle_id: str, packet: dict,
              expected_packet_sha256: str,
              expected_head_sha256: str, expected_decision_sha256: str,
              prior_canary_sha256: str, release_tag: str,
              expected_source_sha256: str, expected_runtime: dict,
              check_clear, backend, process, container_control) -> dict:
    """Run one outer transaction.  The caller must supply the exact boundaries."""
    identifier(cycle_id)
    _sha(prior_canary_sha256, "prior canary")
    root, adapter_claim_root = Path(root), Path(adapter_claim_root)
    if (root.name != cycle_id or root.exists() or root.is_symlink()
            or not adapter_claim_root.is_dir() or adapter_claim_root.is_symlink()
            or root.resolve() == adapter_claim_root.resolve()):
        raise ValueError("fresh outer root and separate adapter claim registry required")
    publication = _publication(release_tag, expected_source_sha256)
    runtime = _runtime(expected_runtime)
    packet = _packet(packet, cycle_id)
    execution_mode = adapter._execution_mode(backend, process, container_control)
    packet_sha = digest(packet)
    if packet_sha != _sha(expected_packet_sha256, "frozen public packet"):
        raise ValueError("public synthetic packet differs from frozen hash")
    _state_snapshot(state, cycle_id, expected_head_sha256,
                    expected_decision_sha256)
    _budget_snapshot(budget, budget_root, experiment_id, budget_cap_usd,
                     cycle_id)

    reserved = dispatched = False
    adapter_calls = 0
    stage = "global_claim"
    state.claim(cycle_id, expected_head_sha256=expected_head_sha256,
                source_sha256=expected_source_sha256,
                prior_canary_sha256=prior_canary_sha256)
    try:
        root.mkdir(mode=0o700)
        (root / "adapter").mkdir(mode=0o700)
    except Exception as primary:
        if root.is_dir() and not root.is_symlink():
            try:
                _pre_dispatch_failure(
                    root=root, cycle_id=cycle_id, stage="outer_root_creation",
                    primary=primary, adapter_calls=0, reserved=False,
                    budget=budget, state=state)
            except Exception as reconciliation_error:
                raise primary from reconciliation_error
        else:
            try:
                state.close(cycle_id, outcome="failed")
            except Exception as close_error:
                raise primary from close_error
        raise
    adapter_root = root / "adapter" / cycle_id
    admission = {
        "schema": OUTER_SCHEMA, "cycle_id": cycle_id,
        "publication_sha256": digest(publication),
        "source_sha256": expected_source_sha256,
        "state_head_sha256": expected_head_sha256,
        "decision_doc_sha256": expected_decision_sha256,
        "prior_canary_sha256": prior_canary_sha256,
        "runtime_sha256": digest(runtime), "packet_sha256": packet_sha,
        "budget_experiment_id": experiment_id,
        "budget_cap_usd": str(money(budget_cap_usd)),
        "budget_bucket": BUCKET, "job_id": cycle_id,
        "upper_usd_not_invoice": str(UPPER_USD), "provider": PROVIDER,
        "adapter": "bounded_live_adapter_v2", "adapter_call_max": 1,
        "provider_sample_max": 1, "b_task_max": 1,
        "execution_mode": execution_mode,
        "automatic_retry": False, "formal_admission": False,
    }
    try:
        fresh_json(root / "publication.json", publication)
        fresh_json(root / "runtime.json", runtime)
        fresh_json(root / "input.json", packet)
        fresh_json(root / "admission.json", admission)
        stage = "budget_reserve"
        budget.reserve(cycle_id, BUCKET, UPPER_USD, PROVIDER, packet_sha)
        reserved = True
        reserved_snapshot = _budget_snapshot(
            budget, budget_root, experiment_id, budget_cap_usd, cycle_id,
            state="reserved")
        fresh_json(root / "reserved.json", {
            "schema": "market_bounded_live_outer_reservation_v3",
            "cycle_id": cycle_id, "job": reserved_snapshot["jobs"][cycle_id],
            "not_a_charge": True,
        })

        # Re-read every mutable gate immediately before the only paid boundary.
        stage = "final_pre_dispatch"
        if (_publication(release_tag, expected_source_sha256) != publication
                or _runtime(expected_runtime) != runtime
                or _packet(_load(root / "input.json"), cycle_id) != packet
                or _state_snapshot(state, cycle_id, expected_head_sha256,
                                   expected_decision_sha256, claimed=True).get(
                                       "active_cycle") != cycle_id):
            raise ValueError("pre-dispatch gate changed")
        _budget_snapshot(budget, budget_root, experiment_id, budget_cap_usd,
                         cycle_id, state="reserved")
        preflight = _clear(check_clear, cycle_id)

        # The callback is intentionally outside the trusted state/budget
        # implementation.  Re-establish every mutable admission fact after it
        # returns and before the one ledger dispatch.  State and budget are the
        # first two operations after the callback so it cannot close/cancel a
        # gate while returning a superficially valid clear receipt.
        _state_snapshot(state, cycle_id, expected_head_sha256,
                        expected_decision_sha256, claimed=True)
        _budget_snapshot(budget, budget_root, experiment_id, budget_cap_usd,
                         cycle_id, state="reserved")
        if (_publication(release_tag, expected_source_sha256) != publication
                or _load(root / "publication.json") != publication
                or _runtime(expected_runtime) != runtime
                or _load(root / "runtime.json") != runtime
                or _packet(_load(root / "input.json"), cycle_id) != packet
                or digest(_load(root / "input.json")) != expected_packet_sha256):
            raise ValueError("post-callback gate changed")
        fresh_json(root / "preflight.json", preflight)
        preflight_sha = file_hash(root / "preflight.json")

        stage = "paid_boundary"
        budget.dispatch(cycle_id)
        dispatched = True
        dispatched_snapshot = _budget_snapshot(
            budget, budget_root, experiment_id, budget_cap_usd, cycle_id,
            state="dispatched")
        fresh_json(root / "dispatched.json", {
            "schema": "market_bounded_live_outer_dispatch_v3",
            "cycle_id": cycle_id,
            "job": dispatched_snapshot["jobs"][cycle_id],
            "preflight_sha256": preflight_sha,
            "adapter_call_next": True, "automatic_retry": False,
        })
        stage = "adapter_call"
        adapter_calls += 1
        result = adapter.run_bounded_adapter(
            root=adapter_root, claim_root=adapter_claim_root,
            cycle_id=cycle_id, packet=packet, backend=backend,
            process=process, container_control=container_control)
        if adapter_calls != 1:
            raise RuntimeError("adapter call count changed")
        call_error = None
    except Exception as exc:
        result, call_error = None, exc

    if not dispatched:
        try:
            _pre_dispatch_failure(
                root=root, cycle_id=cycle_id, stage=stage,
                primary=call_error, adapter_calls=adapter_calls,
                reserved=reserved, budget=budget, state=state)
        except Exception as reconciliation_error:
            # The original admission failure remains the raised cause.  A
            # receipt-install problem is chained rather than replacing it.
            raise call_error from reconciliation_error
        raise call_error

    # After dispatch, local termination is mandatory before either accounting
    # or global state can be closed.  The adapter directory is never removed.
    local_terminal, process_receipt, cleanup_receipt = _local_terminal(
        adapter_root, cycle_id)
    if not local_terminal:
        error = call_error or RuntimeError("missing terminal process/cleanup evidence")
        _unresolved(root, cycle_id, stage, error, adapter_calls, adapter_root)
        raise RuntimeError("post-dispatch process/cleanup unresolved") from error

    provider_receipt = _provider(adapter_root, UPPER_USD)
    adapter_passed = (call_error is None and provider_receipt is not None
                      and _adapter_success(
                          adapter_root, adapter_claim_root, result, provider_receipt,
                          process_receipt, cleanup_receipt, cycle_id,
                          execution_mode))
    reconciliation = {
        "schema": "market_bounded_live_outer_reconciliation_v3",
        "cycle_id": cycle_id, "adapter_calls": adapter_calls,
        "adapter_returned": call_error is None,
        "adapter_passed": adapter_passed,
        "provider_receipt_valid": provider_receipt is not None,
        "process_receipt_sha256": file_hash(adapter_root / "process.json"),
        "cleanup_receipt_sha256": file_hash(adapter_root / "cleanup.json"),
        "exact_container_cleanup_verified": True,
        "automatic_retry": False,
    }
    fresh_json(root / "reconciliation.json", reconciliation)
    try:
        if provider_receipt is not None:
            terminal_usage = dict(provider_receipt)
            terminal_usage.update({
                "outer_reconciliation_sha256": digest(reconciliation),
                "process_receipt_sha256": reconciliation["process_receipt_sha256"],
                "cleanup_receipt_sha256": reconciliation["cleanup_receipt_sha256"],
            })
            budget.settle_metered(
                cycle_id, provider_receipt["metered_cost_usd_not_invoice"],
                terminal_usage)
            ledger_outcome = "metered_terminal"
        else:
            budget.settle_uncertain_at_upper(cycle_id, {
                "terminal_local": True, "process_reaped": True,
                "remote_usage_unknown": True, "automatic_retry": False,
                "evidence_sha256": digest(reconciliation),
                "note": "provider metering unavailable after one dispatched call; upper bound retained",
            })
            ledger_outcome = "uncertain_terminal"
    except Exception as exc:
        _write_failure(root, cycle_id, "budget_reconciliation", exc,
                       adapter_calls=adapter_calls,
                       ledger_state="dispatched_unresolved",
                       supervisor_state="active")
        raise

    terminal = {
        "schema": RESULT_SCHEMA, "cycle_id": cycle_id,
        "passed": adapter_passed, "execution_mode": (
            result.get("execution_mode") if isinstance(result, dict) else None),
        "publication_sha256": file_hash(root / "publication.json"),
        "runtime_sha256": file_hash(root / "runtime.json"),
        "input_sha256": file_hash(root / "input.json"),
        "preflight_sha256": file_hash(root / "preflight.json"),
        "admission_sha256": file_hash(root / "admission.json"),
        "reconciliation_sha256": file_hash(root / "reconciliation.json"),
        "adapter_result_sha256": (file_hash(adapter_root / "result.json")
                                  if (adapter_root / "result.json").is_file()
                                  else None),
        "ledger_outcome": ledger_outcome,
        "supervisor_outcome": "passed" if adapter_passed else "failed",
        "adapter_calls": adapter_calls, "provider_sample_max": 1,
        "b_task_max": 1, "upper_usd_not_invoice": str(UPPER_USD),
        "invoice_reconciled": False, "automatic_retry": False,
        "model_authorship_proven": False, "full_isolation_proven": False,
        "formal_admission": False,
    }
    fresh_json(root / "result.json", terminal)
    try:
        state.close(cycle_id, outcome=terminal["supervisor_outcome"],
                    review_sha256=file_hash(root / "result.json"))
    except Exception as exc:
        _write_failure(root, cycle_id, "global_close", exc,
                       adapter_calls=adapter_calls,
                       ledger_state=ledger_outcome,
                       supervisor_state="active_unresolved")
        raise
    if call_error is not None:
        raise call_error
    if not adapter_passed:
        raise RuntimeError("adapter receipts failed outer review")
    return terminal
