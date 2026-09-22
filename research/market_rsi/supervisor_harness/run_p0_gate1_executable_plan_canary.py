"""Deterministic, synthetic-only Gate 1 compiler and adversarial canary.

No response is fetched: six HTTPS URLs are *descriptions* in an offline plan.
This module has no executor, provider, release, or data-admission entry point.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch

from market_rsi import canonical, digest
from supervisor_harness.build_p0_gate1_controller_packet import (
    RIGHTS_POLICY, SOURCE_REGISTRY, build,
)
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import (
    ADVERSARIAL_VECTORS, CATALOG_COMMITMENT_ID, EXPECTED_COMPILED,
    EXPECTED_WAVE1, FIXTURE_SCHEMA, VALID_DECISION,
    ZERO_SIDE_EFFECT_ASSERTIONS, fixture, frozen_catalog_bytes,
    trade_builder_input,
)
from supervisor_harness.p0_gate1_plan_compiler import compile_exact_request_plan
from supervisor_harness.p0_gate1_research_contract import parse_unique_json
from supervisor_harness.p0_gate1_trade_query import (
    build_bundle as build_trade_bundle,
)


SCHEMA = "market_p0_gate1_executable_plan_canary_v1"
VECTOR_SCHEMA = "market_p0_gate1_executable_plan_vector_receipt_v1"
ADVERSARIAL_SCHEMA = "market_p0_gate1_executable_plan_adversarial_receipt_v1"
FIXTURE_CANONICAL_SHA256 = (
    "a2cc6b556335ea9108f4fcc4149d666c89a0959ee833f6b4ce278dfd4ca3cef0")
VECTOR_CANONICAL_SHA256 = (
    "dd940406860223d2f0358e820ac0fdd1e14c8146a0118857c725a455dd2375c8")
_STAGES = {
    "decision": "broker_task", "decision_json": "broker_task",
    "packet": "broker_task", "packet_and_decision": "broker_task",
    "catalog": "materialization", "catalog_json": "materialization",
    "materialization": "exact_request_manifest",
    "trade_builder_input": "exact_request_manifest",
    "compiled_bundle": "canary_pass",
}
_REASONS = {
    "decision": "DECISION_CONTRACT_REJECTED",
    "decision_json": "DUPLICATE_DECISION_MEMBER",
    "packet": "TRUSTED_PACKET_REJECTED",
    "packet_and_decision": "TRUSTED_LIMITS_REJECTED",
    "catalog": "CATALOG_COMMITMENT_REJECTED",
    "catalog_json": "CATALOG_COMMITMENT_REJECTED",
    "materialization": "MATERIALIZATION_BINDING_REJECTED",
    "trade_builder_input": "TRADE_INPUT_REJECTED",
    "compiled_bundle": "COMPILED_BUNDLE_MISMATCH",
}
_EXPECTED_ERRORS = {
    "decision_model_url_injection": "decision fields differ",
    "decision_handler_authority_injection": "decision fields differ",
    "decision_unknown_operation": "requested operations are invalid",
    "decision_dev_final_request": "contains forbidden authority",
    "decision_request_budget_expansion": "bounds are not executable",
    "decision_duplicate_field": "duplicate decision field",
    "packet_registry_shallow_alias_mutation": "source registry changed",
    "packet_rights_shallow_alias_mutation": "rights policy changed",
    "packet_hard_limits_tamper": "hard limits changed",
    **{name: "catalog bytes do not match the trusted commitment" for name in (
        "catalog_changed_with_old_hash", "catalog_changed_with_caller_rehash",
        "catalog_duplicate_field", "catalog_dev_row", "catalog_final_scope",
        "catalog_duplicate_sample_id", "catalog_only_two_rows")},
    **{name: "materialization commitment changed" for name in (
        "materialization_commitment_tamper", "materialization_input_hash_tamper",
        "materialization_missing_commitment",
        "materialization_missing_request_inputs_commitment")},
    "builder_arbitrary_well_formed_input_hash": "TRADE_INPUT_PROVENANCE_MISMATCH",
    "builder_limit_pagination_gap": "limit must equal 100",
    **{name: "input fields differ from the frozen schema" for name in (
        "builder_unknown_parameter", "builder_url_injection",
        "builder_retry_injection", "builder_redirect_injection",
        "builder_auth_injection", "builder_paid_injection",
        "builder_write_injection")},
    "builder_budget_expansion": "exceeds its hard ceiling",
    **{name: "COMPILED_BUNDLE_MISMATCH" for name in (
        "compiled_manifest_url_hash_tamper", "compiled_source_mapping_tamper",
        "compiled_offline_builder_mislabeled_as_executor",
        "compiled_policy_retry_redirect_auth_paid_write_tamper")},
}
_POST_COMPILE_POINTERS = (
    "/broker_task/source/url", "/broker_task/capability/handler_id",
    "/broker_task/bounds/max_requests", "/broker_task/rights_policy/policy_id",
    "/broker_task/execution_boundary/network_fetch_authorized",
    "/broker_task_canonical_sha256", "/materialization/sample_ids/0",
    "/materialization/request_plan_inputs/0/input_sha256",
    "/materialization/materialization_sha256",
    "/materialization/request_plan_inputs_sha256",
    "/materialization_canonical_file_sha256",
    "/exact_request_manifest/source_mapping/execution_source_registry_id",
    "/exact_request_manifest/catalog_commitment/catalog_file_sha256",
    "/exact_request_manifest/materialization_binding/materialization_sha256",
    "/exact_request_manifest/materialization_binding/request_plan_inputs_sha256",
    "/exact_request_manifest/trade_builder_manifest_canonical_sha256",
    "/exact_request_manifest/requests/0/url", "/exact_request_manifest/requests/0/url_sha256",
    "/exact_request_manifest/hard_budget/max_total_response_bytes",
    "/exact_request_manifest/handler_chain/future_executor_handler_id",
    "/exact_request_manifest/execution_policy/network_execution_authorized",
    "/exact_request_manifest_canonical_sha256",
    "/execution_receipt_contract/request_manifest_sha256",
    "/execution_receipt_contract/hard_constraints/provider_cost_usd",
    "/execution_receipt_contract_canonical_sha256",
    "/claim_boundaries/formal_data_admitted",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _denial_sha(reason: str, boundary: str) -> str:
    return digest({"outcome": "rejected", "reason_code": reason,
                   "artifact_boundary": boundary, "artifact_emitted": False})


def _bytes(value: object) -> bytes:
    return (canonical(value) + "\n").encode("utf-8")


def _packet() -> dict:
    return build(
        {"schema": "market_p0_gate0_verdict_v1",
         "metadata_inventory_passed": True, "2025_formal_final_admitted": False},
        {"schema": "market_controller_b_live_acceptance_v1", "passed": True,
         "claim_boundaries": {
             "bounded_live_transport_and_accounting_proven": True,
             "formal_admission": False,
             "prediction_improvement_proven": False}},
    )


def _frozen_fixture() -> dict:
    value = fixture()
    if (digest(value) != FIXTURE_CANONICAL_SHA256
            or digest(ADVERSARIAL_VECTORS) != VECTOR_CANONICAL_SHA256
            or value.get("schema") != FIXTURE_SCHEMA
            or value.get("catalog_commitment_id") != CATALOG_COMMITMENT_ID
            or len(ADVERSARIAL_VECTORS) != 34
            or len({v["case_id"] for v in ADVERSARIAL_VECTORS}) != 34
            or set(_EXPECTED_ERRORS) != {v["case_id"] for v in ADVERSARIAL_VECTORS}):
        raise ValueError("FROZEN_FIXTURE_MISMATCH")
    if value["decision"] != VALID_DECISION or value["zero_side_effect_assertions"] != ZERO_SIDE_EFFECT_ASSERTIONS:
        raise ValueError("FROZEN_FIXTURE_MISMATCH")
    if _sha(frozen_catalog_bytes()) != EXPECTED_WAVE1["catalog_file_sha256"]:
        raise ValueError("FROZEN_CATALOG_MISMATCH")
    return value


def _compile(decision: dict, packet: dict, catalog: bytes) -> dict:
    return compile_exact_request_plan(decision, packet, catalog,
                                      CATALOG_COMMITMENT_ID)


def _verified_bundle(value: dict, expected: dict) -> None:
    """Compare all emitted fields, not merely self-asserted embedded digests."""
    if type(value) is not dict or value != expected:
        raise ValueError("COMPILED_BUNDLE_MISMATCH")
    manifest = value["exact_request_manifest"]
    materialization = value["materialization"]
    receipt = value["execution_receipt_contract"]
    binding = manifest["materialization_binding"]
    if (value["broker_task_canonical_sha256"] != digest(value["broker_task"])
            or value["exact_request_manifest_canonical_sha256"] != digest(manifest)
            or value["execution_receipt_contract_canonical_sha256"] != digest(receipt)
            or value["materialization_canonical_file_sha256"] != _sha(_bytes(materialization))
            or binding["materialization_sha256"] != materialization["materialization_sha256"]
            or binding["request_plan_inputs_sha256"] != digest(materialization["request_plan_inputs"])
            or receipt["request_manifest_sha256"] != digest(manifest)
            or manifest["request_count"] != 6
            or manifest["hard_budget"] != {
                "max_requests": 6, "max_total_response_bytes": 2_000_000,
                "max_elapsed_seconds": 900}
            or value["claim_boundaries"] != {
                "synthetic_canary_only": True, "network_requests_made": 0,
                "provider_calls_made": 0, "data_fetched": False,
                "dev_data_read": False, "final_data_read": False,
                "formal_data_admitted": False,
                "prediction_improvement_proven": False}
            or manifest["execution_policy"]["network_execution_authorized"] is not False
            or manifest["handler_chain"]["future_executor_handler_id"] is not None):
        raise ValueError("COMPILED_BUNDLE_MISMATCH")


def _pointer(root: object, pointer: str) -> tuple[object, str | int]:
    parts = [part.replace("~1", "/").replace("~0", "~")
             for part in pointer.strip("/").split("/")]
    parent = root
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    return parent, int(parts[-1]) if isinstance(parent, list) else parts[-1]


def _scalar_pointers(value: object, prefix: str = "") -> tuple[str, ...]:
    """Enumerate every emitted scalar, including hashes and authority flags."""
    if isinstance(value, dict):
        return tuple(pointer for key in sorted(value)
                     for pointer in _scalar_pointers(
                         value[key], prefix + "/" + key.replace("~", "~0").replace("/", "~1")))
    if isinstance(value, list):
        return tuple(pointer for index, item in enumerate(value)
                     for pointer in _scalar_pointers(item, prefix + "/" + str(index)))
    if value is None or type(value) in (bool, int, float, str):
        return (prefix,)
    raise ValueError("UNSUPPORTED_COMPILED_FIELD")


def _mutate(value: object, mutation: dict) -> object:
    changed = deepcopy(value)
    op = mutation["op"]
    if op == "truncate_rows":
        changed["rows"] = changed["rows"][:mutation["length"]]
    elif op == "weaken_execution_policy":
        policy = changed["exact_request_manifest"]["execution_policy"]
        policy.update({"network_execution_authorized": True,
                       "redirects_allowed": True,
                       "authentication_allowed": True,
                       "paid_access_allowed": True,
                       "write_operations_allowed": True,
                       "silent_retries_allowed": True})
    elif op in {"set", "set_then_rehash", "add", "remove", "copy", "mutate_after_build"}:
        parent, key = _pointer(changed, mutation["path"])
        if op == "remove":
            del parent[key]
        elif op == "copy":
            source, source_key = _pointer(changed, mutation["from"])
            parent[key] = deepcopy(source[source_key])
        else:
            if op == "add" and key in parent:
                raise ValueError("MALFORMED_VECTOR")
            parent[key] = deepcopy(mutation["value"])
    else:
        raise ValueError("UNKNOWN_MUTATION")
    return changed


def _duplicate(raw: bytes, mutation: dict) -> bytes:
    if mutation["op"] != "append_duplicate_member" or not raw.endswith(b"}"):
        raise ValueError("MALFORMED_VECTOR")
    return (raw[:-1] + b"," + canonical(mutation["member"]).encode()
            + b":" + canonical(mutation["value"]).encode() + b"}")


def _catalog_attack(mutation: dict) -> tuple[bytes, bytes]:
    changed = canonical(_mutate(json.loads(frozen_catalog_bytes()), mutation)).encode()
    if mutation["op"] == "set_then_rehash":
        # Record the caller's attempted replacement claim. The compiler has
        # no parameter for it and still resolves only the trusted registry ID.
        caller_hash = _sha(changed)
        if caller_hash == EXPECTED_WAVE1["catalog_file_sha256"]:
            raise ValueError("MALFORMED_VECTOR")
        return changed, _bytes({"catalog": json.loads(changed),
                                "caller_claimed_sha256": caller_hash})
    return changed, changed


def _case_input(vector: dict, baseline: dict) -> None:
    """Execute at the declared boundary; only the expected denial can pass."""
    stage, mutation = vector["stage"], vector["mutation"]
    decision, packet, catalog = deepcopy(VALID_DECISION), _packet(), frozen_catalog_bytes()
    if stage == "decision":
        decision = _mutate(decision, mutation)
        _compile(decision, packet, catalog)
    elif stage == "decision_json":
        raw = _duplicate(canonical(decision).encode(), mutation)
        parsed = parse_unique_json(raw.decode())
        _compile(parsed, packet, catalog)
    elif stage in {"packet", "packet_and_decision"}:
        if stage == "packet":
            source_url = SOURCE_REGISTRY[1]["url"]
            rights_id = RIGHTS_POLICY["policy_id"]
            parent, key = _pointer(packet, mutation["path"])
            parent[key] = deepcopy(mutation["value"])
            if SOURCE_REGISTRY[1]["url"] != source_url:
                raise RuntimeError("TRUSTED_SOURCE_ALIASED")
            if RIGHTS_POLICY["policy_id"] != rights_id:
                raise RuntimeError("TRUSTED_RIGHTS_ALIASED")
        else:
            if mutation["op"] != "expand_packet_and_decision_limits":
                raise ValueError("MALFORMED_VECTOR")
            packet["hard_limits"]["max_bytes_ceiling"] = mutation["max_bytes"]
            packet["hard_limits"]["max_minutes_ceiling"] = mutation["max_minutes"]
            decision["max_bytes"] = mutation["max_bytes"]
            decision["max_minutes"] = mutation["max_minutes"]
        _compile(decision, packet, catalog)
    elif stage in {"catalog", "catalog_json"}:
        if stage == "catalog_json":
            raw = _duplicate(catalog, mutation)
        else:
            raw, _ = _catalog_attack(mutation)
        # A caller's recomputed digest has no authority; the registry ID alone
        # chooses the previously committed hash.
        _compile(decision, packet, raw)
    elif stage == "materialization":
        injected = _mutate(baseline["materialization"], mutation)
        with patch("supervisor_harness.p0_gate1_plan_compiler.materialize",
                   return_value=injected):
            _compile(decision, packet, catalog)
    elif stage == "trade_builder_input":
        injected = _mutate(trade_builder_input(), mutation)
        def guarded_builder(value: dict) -> dict:
            # The lower-level builder only validates SHA syntax. A true
            # provenance rejection must happen before calling that builder.
            if vector["case_id"] != "builder_arbitrary_well_formed_input_hash":
                # Check its actual schema/limit/ceiling denial first. If an
                # injected value starts passing the builder in a later version,
                # this canary fails instead of accepting a runner-only denial.
                build_trade_bundle(injected)
                raise AssertionError("builder unexpectedly accepted injected input")
            if injected != value:
                raise ValueError("TRADE_INPUT_PROVENANCE_MISMATCH")
            return build_trade_bundle(injected)
        with patch("supervisor_harness.p0_gate1_plan_compiler.build_trade_bundle",
                   side_effect=guarded_builder):
            _compile(decision, packet, catalog)
    elif stage == "compiled_bundle":
        injected = _mutate(baseline, mutation)
        _verified_bundle(injected, baseline)
    else:
        raise ValueError("UNKNOWN_VECTOR_STAGE")
    raise AssertionError("attack unexpectedly reached " + vector["must_fail_before"])


def _input_bytes(vector: dict, baseline: dict) -> bytes:
    """Capture the injected bytes without using an exception as evidence."""
    stage, mutation = vector["stage"], vector["mutation"]
    if stage == "decision":
        return _bytes(_mutate(VALID_DECISION, mutation))
    if stage == "decision_json":
        return _duplicate(canonical(VALID_DECISION).encode(), mutation)
    if stage in {"packet", "packet_and_decision"}:
        packet, decision = _packet(), deepcopy(VALID_DECISION)
        if stage == "packet":
            packet = _mutate(packet, mutation)
        else:
            packet["hard_limits"]["max_bytes_ceiling"] = mutation["max_bytes"]
            packet["hard_limits"]["max_minutes_ceiling"] = mutation["max_minutes"]
            decision["max_bytes"] = mutation["max_bytes"]
            decision["max_minutes"] = mutation["max_minutes"]
        return _bytes({"packet": packet, "decision": decision})
    if stage == "catalog":
        return _catalog_attack(mutation)[1]
    if stage == "catalog_json":
        return _duplicate(frozen_catalog_bytes(), mutation)
    if stage == "materialization":
        return _bytes(_mutate(baseline["materialization"], mutation))
    if stage == "trade_builder_input":
        return _bytes(_mutate(trade_builder_input(), mutation))
    return _bytes(_mutate(baseline, mutation))


def run_vector(vector_id: str, baseline: dict | None = None) -> dict:
    """Run only a frozen ID; never accept caller-authored vector/trust claims."""
    _frozen_fixture()
    vectors = {v["case_id"]: v for v in ADVERSARIAL_VECTORS}
    if type(vector_id) is not str or vector_id not in vectors:
        raise ValueError("UNKNOWN_VECTOR_ID")
    vector = vectors[vector_id]
    stage = vector["stage"]
    if (stage not in _STAGES or vector["must_fail_before"] != _STAGES[stage]
            or not isinstance(vector.get("mutation"), dict)):
        raise ValueError("MALFORMED_VECTOR")
    known = _compile(deepcopy(VALID_DECISION), _packet(), frozen_catalog_bytes())
    if baseline is not None:
        _verified_bundle(baseline, known)
    raw = _input_bytes(vector, known)
    observed, reason = "accepted", "UNEXPECTED_ACCEPTANCE"
    try:
        _case_input(vector, known)
    except ValueError as exc:
        if _EXPECTED_ERRORS[vector_id] not in str(exc):
            raise RuntimeError("UNEXPECTED_REJECTION_REASON: " + vector_id) from exc
        observed, reason = "rejected", _REASONS[stage]
    # For the deliberately forged selected hash, the compiler's trusted
    # provenance gate is the rejecting component, not the permissive builder.
    if vector_id == "builder_arbitrary_well_formed_input_hash" and observed == "rejected":
        reason = "TRADE_INPUT_PROVENANCE_MISMATCH"
    manifest = known["exact_request_manifest"]
    materialization = known["materialization"]
    receipt = {
        "schema": VECTOR_SCHEMA,
        "vector_id": vector_id,
        "stage": stage,
        "expected_boundary": vector["must_fail_before"],
        "expected_outcome": "rejected",
        "observed_outcome": observed,
        "reason_code": reason,
        "input_sha256": _sha(raw),
        # The output is the canonical terminal denial, not a request artifact.
        "output_sha256": (_denial_sha(reason, vector["must_fail_before"])
                          if observed == "rejected" else digest(known)),
        "output_artifact_sha256": None if observed == "rejected" else digest(known),
        "manifest_sha256": digest(manifest),
        "materialization_sha256": materialization["materialization_sha256"],
        "request_plan_inputs_sha256": materialization["request_plan_inputs_sha256"],
        "ceilings": {"max_requests": 6, "max_bytes": 2_000_000,
                     "max_elapsed_seconds": 900, "max_provider_cost_usd": "0"},
        **ZERO_SIDE_EFFECT_ASSERTIONS,
    }
    return receipt


def _post_compile_tamper_receipts(baseline: dict) -> list[dict]:
    receipts = []
    pointers = _scalar_pointers(baseline)
    if not set(_POST_COMPILE_POINTERS).issubset(pointers):
        raise ValueError("MISSING_COMMITMENT_CRITICAL_FIELD")
    # Missing whole artifacts are distinct from changed leaves. Both must
    # fail before the terminal canary receipt is published.
    removals = ("/broker_task", "/materialization",
                "/exact_request_manifest", "/execution_receipt_contract",
                "/claim_boundaries")
    for pointer in (*pointers, *removals):
        changed = deepcopy(baseline)
        parent, key = _pointer(changed, pointer)
        if pointer in removals:
            del parent[key]
        else:
            previous = parent[key]
            parent[key] = not previous if type(previous) is bool else (
                "tampered" if previous is None else
                previous + 1 if type(previous) in (int, float) else
                "0" * 64 if isinstance(previous, str) and previous != "0" * 64
                else "changed")
            if parent[key] == previous:
                raise ValueError("MALFORMED_POST_COMPILE_TAMPER")
        try:
            _verified_bundle(changed, baseline)
        except ValueError as exc:
            if str(exc) != "COMPILED_BUNDLE_MISMATCH":
                raise RuntimeError("UNEXPECTED_POST_COMPILE_REJECTION") from exc
        else:
            raise ValueError("POST_COMPILE_TAMPER_ACCEPTED: " + pointer)
        receipts.append({
            "schema": VECTOR_SCHEMA, "vector_id": "post_compile:" + pointer,
            "stage": "compiled_bundle", "expected_boundary": "canary_pass",
            "expected_outcome": "rejected", "observed_outcome": "rejected",
            "reason_code": "COMPILED_BUNDLE_MISMATCH",
            "input_sha256": digest(changed),
            "output_sha256": _denial_sha("COMPILED_BUNDLE_MISMATCH", "canary_pass"),
            "output_artifact_sha256": None,
            "manifest_sha256": digest(baseline["exact_request_manifest"]),
            "materialization_sha256": baseline["materialization"]["materialization_sha256"],
            "request_plan_inputs_sha256": baseline["materialization"]["request_plan_inputs_sha256"],
            "ceilings": {"max_requests": 6, "max_bytes": 2_000_000,
                         "max_elapsed_seconds": 900, "max_provider_cost_usd": "0"},
            **ZERO_SIDE_EFFECT_ASSERTIONS,
        })
    return receipts


def _offline() -> tuple[dict, list[dict], list[dict]]:
    _frozen_fixture()
    decision = deepcopy(VALID_DECISION)
    catalog = frozen_catalog_bytes()
    first = _compile(decision, _packet(), catalog)
    second = _compile(deepcopy(decision), _packet(), bytes(catalog))
    _verified_bundle(first, second)
    if _bytes(first) != _bytes(second):
        raise ValueError("NONDETERMINISTIC_COMPILATION")
    for field, literal in EXPECTED_COMPILED.items():
        name = field.removesuffix("_canonical_sha256").removesuffix("_file_sha256")
        item = {"broker_task": first["broker_task"],
                "exact_manifest": first["exact_request_manifest"],
                "execution_receipt_contract": first["execution_receipt_contract"],
                "compiled_bundle": first}[name]
        actual = _sha(_bytes(item)) if field.endswith("_file_sha256") else digest(item)
        if actual != literal:
            raise ValueError("FROZEN_COMPILATION_MISMATCH")
    manifest = first["exact_request_manifest"]
    if ([v["sample_id"] for v in first["materialization"]["request_plan_inputs"]]
            != EXPECTED_WAVE1["selected_sample_ids"]
            or [v["url_sha256"] for v in manifest["requests"]]
            != EXPECTED_WAVE1["request_url_sha256"]):
        raise ValueError("FROZEN_COMPILATION_MISMATCH")
    cases = [run_vector(vector["case_id"], first) for vector in ADVERSARIAL_VECTORS]
    if len(cases) != 34 or any(case["observed_outcome"] != "rejected"
                               for case in cases):
        raise ValueError("ADVERSARIAL_CANARY_FAILED")
    tamper_cases = _post_compile_tamper_receipts(first)
    return first, cases, tamper_cases


def _write_atomic_exclusive(path: Path, raw: bytes) -> None:
    """Fsync temporary bytes, hard-link without replacement, then sync dir."""
    fd, temp_name = tempfile.mkstemp(prefix=".gate1-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp_name, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temp_name)


def execute(output: Path | None = None) -> dict:
    """Run in memory, or persist a fresh immutable directory outside the repo."""
    if output is not None:
        output = Path(output)
        repo = Path(__file__).resolve().parents[3]
        resolved = output.resolve()
        if resolved.is_relative_to(repo):
            raise ValueError("RUNTIME_RECEIPTS_MUST_BE_OUTSIDE_SOURCE_TREE")
        if output.exists() or output.is_symlink():
            raise FileExistsError("fresh canary output required")
    # Forbid Python socket creation and name resolution for the whole compile
    # and attack pass. No provider/HTTP executor is imported or exposed here.
    with ExitStack() as offline_guard:
        for name in ("socket", "socketpair", "fromfd", "create_connection",
                     "getaddrinfo", "getnameinfo", "gethostbyname",
                     "gethostbyname_ex", "gethostbyaddr"):
            offline_guard.enter_context(patch.object(
                socket, name, side_effect=RuntimeError("NETWORK_FORBIDDEN")))
        bundle, cases, tamper_cases = _offline()
        valid_input_sha256 = digest({
            "decision": VALID_DECISION, "packet": _packet(),
            "catalog_file_sha256": _sha(frozen_catalog_bytes()),
            "catalog_commitment_id": CATALOG_COMMITMENT_ID,
        })
    manifest = bundle["exact_request_manifest"]
    materialization = bundle["materialization"]
    ceilings = {"max_requests": 6, "max_bytes": 2_000_000,
                "max_elapsed_seconds": 900, "max_provider_cost_usd": "0"}
    valid = {
        "schema": VECTOR_SCHEMA, "vector_id": "known_good",
        "stage": "decision_to_manifest", "expected_boundary": "offline_plan_only",
        "expected_outcome": "accepted", "observed_outcome": "accepted",
        "reason_code": "EXACT_OFFLINE_PLAN_COMPILED",
        "input_sha256": valid_input_sha256,
        "output_sha256": digest(bundle), "output_artifact_sha256": digest(bundle),
        "manifest_sha256": digest(manifest),
        "materialization_sha256": materialization["materialization_sha256"],
        "request_plan_inputs_sha256": materialization["request_plan_inputs_sha256"],
        "ceilings": ceilings, **ZERO_SIDE_EFFECT_ASSERTIONS,
    }
    adversarial = {
        "schema": ADVERSARIAL_SCHEMA, "fixture_schema": FIXTURE_SCHEMA,
        "vector_count": len(cases), "vectors_rejected": len(cases),
        "vector_receipts": cases,
        "post_compile_tamper_count": len(tamper_cases),
        "post_compile_tamper_receipts": tamper_cases,
        **ZERO_SIDE_EFFECT_ASSERTIONS,
    }
    files = {
        "valid-path-receipt.json": valid,
        "decision.json": deepcopy(VALID_DECISION),
        "catalog.json": frozen_catalog_bytes(),
        "broker-task.json": bundle["broker_task"],
        "materialization.json": materialization,
        "exact-request-manifest.json": manifest,
        "execution-receipt-contract.json": bundle["execution_receipt_contract"],
        "compiled-bundle.json": bundle,
        "adversarial-receipt.json": adversarial,
    }
    raw_files = {name: value if isinstance(value, bytes) else _bytes(value)
                 for name, value in files.items()}
    hashes = {name: _sha(raw) for name, raw in raw_files.items()}
    result = {
        "schema": SCHEMA, "passed": True, "fixture_schema": FIXTURE_SCHEMA,
        "fixture_canonical_sha256": FIXTURE_CANONICAL_SHA256,
        "fixture_source_sha256": _sha(Path(__file__).with_name(
            "p0_gate1_executable_plan_canary_fixtures.py").read_bytes()),
        "catalog_commitment_id": CATALOG_COMMITMENT_ID,
        "decision_canonical_sha256": digest(VALID_DECISION),
        "artifact_sha256": hashes,
        "compiled_bundle_canonical_sha256": digest(bundle),
        "manifest_sha256": digest(manifest),
        "materialization_sha256": materialization["materialization_sha256"],
        "request_plan_inputs_sha256": materialization["request_plan_inputs_sha256"],
        "sample_ids": materialization["sample_ids"],
        "requests_planned": 6, "adversarial_case_count": 34,
        "adversarial_cases_rejected": 34,
        "post_compile_tamper_count": len(tamper_cases),
        "post_compile_tamper_cases_rejected": len(tamper_cases),
        "adversarial_receipt_sha256": hashes["adversarial-receipt.json"],
        "valid_path_receipt_sha256": hashes["valid-path-receipt.json"],
        "ceilings": ceilings,
        "synthetic_only": True, "network_execution_authorized": False,
        "release_authorized": False, "provider_execution_authorized": False,
        "data_fetch_authorized": False, "dev_or_final_access_authorized": False,
        "formal_admission_authorized": False,
        **ZERO_SIDE_EFFECT_ASSERTIONS,
    }
    if output is not None:
        output.mkdir(mode=0o700)
        for name, raw in raw_files.items():
            _write_atomic_exclusive(output / name, raw)
        # Terminal marker last; an interrupted output cannot be a pass.
        _write_atomic_exclusive(output / "canary-result.json", _bytes(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    print(canonical(execute(parser.parse_args().output)))
