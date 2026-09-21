"""Durable state/budget transaction around one Gate 1 Controller response.

This layer performs every mutable check before the sole dispatch, calls the
one-response adapter exactly once, settles real returned usage or conservatively
retains the full upper bound, and closes the global cycle.  It has no CLI and
does not load credentials; the Supervisor-owned live entry provides the exact
backend only after binding the child process.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path

from glm_canary import MODEL, RATES, cost
from market_rsi import digest, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget, money
from supervisor_harness import bounded_live_outer_runner_v3 as shared
from supervisor_harness import global_state_gate
from supervisor_harness import p0_gate1_controller_adapter as adapter
from supervisor_harness import protocol_source_release
from supervisor_harness.p0_gate1_research_contract import validate_and_compile


OUTER_SCHEMA = "market_p0_gate1_controller_outer_v1"
RESULT_SCHEMA = "market_p0_gate1_controller_outer_result_v1"
REVIEW_SCHEMA = "market_p0_gate1_controller_review_v1"
BUCKET = "setup"
PROVIDER = "tinker"
UPPER_USD = Decimal("0.05")
ZERO = "0" * 64
SOURCE_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SOURCE_FILES = (
    "codex_glm_provider.py",
    "codex_glm_responses_adapter.py",
    "paid_budget.py",
    "supervisor_harness/global_state_gate.py",
    "supervisor_harness/protocol_source_release.py",
    "supervisor_harness/build_p0_gate1_controller_packet.py",
    "supervisor_harness/p0_gate1_research_contract.py",
    "supervisor_harness/p0_gate1_controller_adapter.py",
    "supervisor_harness/p0_gate1_controller_outer.py",
)


def _required_hashes() -> dict[str, str]:
    values = {}
    for name in REQUIRED_SOURCE_FILES:
        path = SOURCE_ROOT / name
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError("required Gate 1 source is missing or noncanonical")
        values[name] = file_hash(path)
    return values


def _publication(tag: str, expected_source_sha256: str) -> dict:
    value = shared._publication(tag, expected_source_sha256)
    current = _required_hashes()
    if any(value["source_hashes"].get(name) != sha
           for name, sha in current.items()):
        raise ValueError("published Gate 1 source is stale or incomplete")
    return value


def _provider_receipt(root: Path, mode: str) -> dict | None:
    try:
        sampled = load_json(root / "raw-response.json")
        encoded = load_json(root / "encoded.json")
        observed = load_json(root / "provider-receipt.json")
        expected = adapter._provider_receipt(
            sampled, len(encoded["token_ids"]),
            provider_called=mode == "live_pinned")
        metered = money(observed["metered_cost_usd_not_invoice"])
    except Exception:
        return None
    if (observed != expected or observed.get("requested_model") != MODEL
            or observed.get("rates") != RATES or metered > UPPER_USD):
        return None
    return observed


def _adapter_success(root: Path, claims: Path, cycle_id: str,
                     mode: str, packet: dict, result: dict,
                     provider: dict) -> bool:
    try:
        task = load_json(root / "task.json")
        decision = load_json(root / "decision.json")
        if task != validate_and_compile(decision, packet):
            return False
        expected_names = {
            "claim.json", "input.json", "request.json", "encoded.json",
            "cost-preview.json", "raw-response.json", "raw-response.txt",
            "provider-receipt.json", "decision.json", "task.json",
            "failure.json",
        }
        artifacts = result.get("artifact_sha256")
        if not isinstance(artifacts, dict) or set(artifacts) != expected_names:
            return False
        for name, expected in artifacts.items():
            path = root / name
            if expected is None:
                if path.exists() or path.is_symlink():
                    return False
            elif expected != file_hash(path):
                return False
        registry = claims / f"{cycle_id}.json"
        return (
            result.get("schema") == adapter.RESULT_SCHEMA
            and result.get("cycle_id") == cycle_id
            and result.get("execution_mode") == mode
            and result.get("valid_plan_only_decision") is True
            and result.get("completed_live_decision_pending_review")
            is (mode == "live_pinned")
            and result.get("failure_type") is None
            and result.get("registry_claim_sha256") == file_hash(registry)
            and result.get("requested_model") == MODEL
            and result.get("reported_model") == provider["reported_model"]
            and result.get("input_tokens") == provider["input_tokens"]
            and result.get("output_tokens") == provider["output_tokens"]
            and result.get("cached_input_tokens")
            == provider["cached_input_tokens"]
            and result.get("metered_cost_usd_not_invoice")
            == provider["metered_cost_usd_not_invoice"]
            and result.get("provider_called") is (mode == "live_pinned")
            and result.get("dispatch_gate_called") is True
            and result.get("automatic_retry") is False
            and result.get("sample_count_max") == 1
            and result.get("tools") == [adapter.SUBMIT_TOOL]
            and result.get("public_fetch_performed") is False
            and result.get("sealed_data_read") is False
            and result.get("formal_data_admitted") is False
        )
    except Exception:
        return False


def _write_failure(root: Path, cycle_id: str, stage: str,
                   error: Exception, *, dispatched: bool) -> None:
    path = root / "outer-failure.json"
    if not path.exists():
        fresh_json(path, {
            "schema": "market_p0_gate1_controller_outer_failure_v1",
            "cycle_id": cycle_id,
            "stage": stage,
            "error_type": type(error).__name__,
            "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
            "dispatched": dispatched,
            "automatic_retry": False,
        })


def run_outer(*, root: Path, claim_root: Path,
              state: global_state_gate.SupervisorGlobalState,
              budget: PaidBudget, budget_root: Path, experiment_id: str,
              budget_cap_usd, cycle_id: str, packet: dict,
              expected_packet_sha256: str,
              expected_head_sha256: str, expected_decision_sha256: str,
              prior_canary_sha256: str, release_tag: str,
              expected_source_sha256: str, expected_runtime: dict,
              check_clear, backend) -> dict:
    """Run one transaction; any failure consumes the permanent cycle ID."""
    identifier(cycle_id)
    shared._sha(prior_canary_sha256, "prior canary")
    root, claim_root = Path(root), Path(claim_root)
    if (root.name != cycle_id or root.exists() or root.is_symlink()
            or not claim_root.is_dir() or claim_root.is_symlink()
            or root.resolve() == claim_root.resolve()):
        raise ValueError("fresh Gate 1 outer root and separate claims required")
    registry = claim_root / f"{cycle_id}.json"
    if registry.exists() or registry.is_symlink():
        raise ValueError("Gate 1 cycle ID was already permanently claimed")
    publication = _publication(release_tag, expected_source_sha256)
    runtime = shared._runtime(expected_runtime)
    packet = adapter._packet(packet)
    packet_sha = digest(packet)
    if packet_sha != shared._sha(expected_packet_sha256, "Gate 1 packet"):
        raise ValueError("Gate 1 packet differs from frozen hash")
    mode = adapter._mode(backend)
    shared._state_snapshot(
        state, cycle_id, expected_head_sha256, expected_decision_sha256)
    shared._budget_snapshot(
        budget, budget_root, experiment_id, budget_cap_usd, cycle_id)
    shared._clear(check_clear, cycle_id)

    # Tokenization is local and happens before any claim, reservation or send.
    encoded = backend.encode(adapter.request_turn(packet))
    input_tokens = adapter._encoding(encoded)
    upper = cost(input_tokens, adapter.MAX_OUTPUT_TOKENS)
    if upper > UPPER_USD:
        raise ValueError("Gate 1 preflight exceeds fixed paid upper bound")

    state.claim(cycle_id, expected_head_sha256=expected_head_sha256,
                source_sha256=expected_source_sha256,
                prior_canary_sha256=prior_canary_sha256)
    claimed = True
    reserved = False
    dispatched = False
    stage = "outer_root"
    try:
        root.mkdir(mode=0o700)
        fresh_json(root / "publication.json", publication)
        fresh_json(root / "runtime.json", runtime)
        fresh_json(root / "input.json", packet)
        fresh_json(root / "preencoded.json", encoded)
        admission = {
            "schema": OUTER_SCHEMA,
            "cycle_id": cycle_id,
            "publication_sha256": digest(publication),
            "source_sha256": expected_source_sha256,
            "runtime_sha256": digest(runtime),
            "packet_sha256": packet_sha,
            "prior_canary_sha256": prior_canary_sha256,
            "budget_experiment_id": experiment_id,
            "budget_cap_usd": str(money(budget_cap_usd)),
            "budget_bucket": BUCKET,
            "provider": PROVIDER,
            "upper_usd_not_invoice": str(UPPER_USD),
            "execution_mode": mode,
            "provider_sample_max": 1,
            "automatic_retry": False,
            "public_fetch_authorized": False,
            "formal_data_admitted": False,
        }
        fresh_json(root / "admission.json", admission)

        stage = "budget_reserve"
        budget.reserve(cycle_id, BUCKET, UPPER_USD, PROVIDER, packet_sha)
        reserved = True
        reserved_state = shared._budget_snapshot(
            budget, budget_root, experiment_id, budget_cap_usd, cycle_id,
            state="reserved")
        fresh_json(root / "reserved.json", {
            "schema": "market_p0_gate1_controller_reservation_v1",
            "cycle_id": cycle_id,
            "job": reserved_state["jobs"][cycle_id],
            "not_a_charge": True,
        })

        def dispatch_gate(preview: dict) -> None:
            nonlocal dispatched, stage
            stage = "final_pre_dispatch"
            if (preview.get("upper_usd_not_invoice") != str(upper)
                    or load_json(root / "input.json") != packet
                    or load_json(root / "preencoded.json") != encoded
                    or _publication(release_tag, expected_source_sha256)
                    != publication
                    or shared._runtime(expected_runtime) != runtime
                    or shared._state_snapshot(
                        state, cycle_id, expected_head_sha256,
                        expected_decision_sha256, claimed=True
                    ).get("active_cycle") != cycle_id):
                raise ValueError("Gate 1 final pre-dispatch state changed")
            shared._budget_snapshot(
                budget, budget_root, experiment_id, budget_cap_usd, cycle_id,
                state="reserved")
            preflight = shared._clear(check_clear, cycle_id)
            fresh_json(root / "preflight.json", preflight)
            stage = "paid_boundary"
            budget.dispatch(cycle_id)
            dispatched = True
            dispatched_state = shared._budget_snapshot(
                budget, budget_root, experiment_id, budget_cap_usd, cycle_id,
                state="dispatched")
            fresh_json(root / "dispatched.json", {
                "schema": "market_p0_gate1_controller_dispatch_v1",
                "cycle_id": cycle_id,
                "job": dispatched_state["jobs"][cycle_id],
                "adapter_call_next": True,
                "automatic_retry": False,
            })

        stage = "adapter_call"
        adapter_root = root / "adapter" / cycle_id
        (root / "adapter").mkdir(mode=0o700)
        result = adapter.run(
            root=adapter_root, claim_root=claim_root, cycle_id=cycle_id,
            packet=packet, backend=backend, preencoded=encoded,
            before_sample=dispatch_gate)

        provider = _provider_receipt(adapter_root, mode)
        if dispatched:
            stage = "budget_reconciliation"
            if provider is not None:
                terminal = dict(provider)
                terminal["adapter_result_sha256"] = file_hash(
                    adapter_root / "result.json")
                budget.settle_metered(
                    cycle_id, provider["metered_cost_usd_not_invoice"], terminal)
                ledger_outcome = "metered_terminal"
            else:
                evidence = file_hash(adapter_root / "result.json")
                budget.settle_uncertain_at_upper(cycle_id, {
                    "terminal_local": True,
                    "process_reaped": True,
                    "remote_usage_unknown": True,
                    "automatic_retry": False,
                    "evidence_sha256": evidence,
                    "note": "one Controller call dispatched but terminal provider metering is unavailable",
                })
                ledger_outcome = "uncertain_terminal"
        else:
            stage = "pre_dispatch_reconciliation"
            if reserved:
                budget.cancel_before_dispatch(cycle_id)
            ledger_outcome = "cancelled_before_dispatch"

        boundary_unchanged = False
        try:
            boundary_unchanged = (
                _publication(release_tag, expected_source_sha256) == publication
                and shared._runtime(expected_runtime) == runtime
                and load_json(root / "input.json") == packet
                and load_json(root / "preencoded.json") == encoded
                and shared._state_snapshot(
                    state, cycle_id, expected_head_sha256,
                    expected_decision_sha256, claimed=True
                ).get("active_cycle") == cycle_id
            )
        except Exception:
            boundary_unchanged = False
        adapter_passed = (
            dispatched and provider is not None and boundary_unchanged
            and _adapter_success(
                adapter_root, claim_root, cycle_id, mode, packet,
                result, provider)
        )
        review = {
            "schema": REVIEW_SCHEMA,
            "cycle_id": cycle_id,
            "adapter_passed": adapter_passed,
            "publication_runtime_state_unchanged": boundary_unchanged,
            "provider_receipt_valid": provider is not None,
            "ledger_outcome": ledger_outcome,
            "adapter_result_sha256": file_hash(adapter_root / "result.json"),
            "task_sha256": (file_hash(adapter_root / "task.json")
                            if (adapter_root / "task.json").is_file() else None),
            "public_fetch_performed": False,
            "formal_data_admitted": False,
            "automatic_retry": False,
        }
        fresh_json(root / "review.json", review)
        terminal_result = {
            "schema": RESULT_SCHEMA,
            "cycle_id": cycle_id,
            "passed": adapter_passed,
            "execution_mode": mode,
            "publication_sha256": file_hash(root / "publication.json"),
            "runtime_sha256": file_hash(root / "runtime.json"),
            "input_sha256": file_hash(root / "input.json"),
            "admission_sha256": file_hash(root / "admission.json"),
            "preflight_sha256": file_hash(root / "preflight.json"),
            "review_sha256": file_hash(root / "review.json"),
            "adapter_result_sha256": file_hash(adapter_root / "result.json"),
            "ledger_outcome": ledger_outcome,
            "supervisor_outcome": "passed" if adapter_passed else "failed",
            "provider_sample_max": 1,
            "upper_usd_not_invoice": str(UPPER_USD),
            "automatic_retry": False,
            "public_fetch_performed": False,
            "formal_data_admitted": False,
        }
        fresh_json(root / "result.json", terminal_result)
        state.close(
            cycle_id,
            outcome=terminal_result["supervisor_outcome"],
            review_sha256=(file_hash(root / "review.json")
                           if adapter_passed else ZERO),
        )
        claimed = False
        if not adapter_passed:
            error = RuntimeError("Gate 1 Controller response failed review")
            _write_failure(root, cycle_id, "outer_review", error,
                           dispatched=dispatched)
            raise error
        return terminal_result
    except Exception as error:
        if root.is_dir() and not root.is_symlink():
            _write_failure(root, cycle_id, stage, error,
                           dispatched=dispatched)
        # Never make a possibly paid, unreconciled dispatch disappear by
        # freeing the global cycle.  A reserved-but-unsent job can be cancelled;
        # a terminal/cancelled job can close failed; a still-dispatched job must
        # remain active for explicit repair and reconciliation.
        job_state = "unknown"
        try:
            snapshot = budget.snapshot()
            job = snapshot.get("jobs", {}).get(cycle_id)
            job_state = job.get("state") if isinstance(job, dict) else "absent"
            if job_state == "reserved":
                budget.cancel_before_dispatch(cycle_id)
                job_state = "cancelled_before_dispatch"
        except Exception:
            job_state = "unknown"
        if claimed and job_state != "dispatched":
            try:
                current = state.snapshot()
                if current.get("active_cycle") == cycle_id:
                    state.close(cycle_id, outcome="failed")
                claimed = False
            except Exception:
                pass
        raise
