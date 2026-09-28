"""Pure schema support for a non-executable prospective source-scope choice.

This module deliberately has no filesystem, network, provider, credential,
budget, data, model, or process integration.  It validates only the five
scientific choice objects described by
``market_rsi_prospective_source_scope_decision_v1`` and the fixed all-false
authority boundary.  Operational provenance and admission are separate gates.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Mapping


SCHEMA = "market_rsi_prospective_source_scope_decision_v1"
DECISION_STATUS = "scope_only_non_executable"

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema",
        "decision_id",
        "decision_status",
        "scientific_source_response",
        "intended_uses",
        "future_role_split",
        "horizon_cutoff",
        "bounded_investigation",
        "non_authority",
    }
)

NON_AUTHORITY_KEYS = frozenset(
    {
        "executable",
        "provider_contact_authorized",
        "provider_access_authorized",
        "network_access_authorized",
        "credential_use_authorized",
        "spend_authorized",
        "paid_model_authorized",
        "data_capture_authorized",
        "raw_data_retention_authorized",
        "train_admission_authorized",
        "model_training_authorized",
        "dev_read_authorized",
        "final_read_authorized",
        "evaluation_or_scoring_authorized",
        "data_redistribution_authorized",
        "repository_operation_authorized",
        "publication_authorized",
    }
)

INTENDED_USE_IDS = frozenset(
    {
        "private_research",
        "durable_local_retention",
        "model_training",
        "internal_derived_outputs",
        "external_derived_outputs",
        "raw_data_redistribution",
        "derived_dataset_redistribution",
        "model_artifact_redistribution",
    }
)

FUTURE_ROLES = frozenset(
    {
        "train_candidate",
        "development_candidate",
        "final_candidate",
        "diagnostic_only",
        "unassigned_candidate",
    }
)

CLAIM_SEMANTICS = frozenset(
    {
        "prospective_point_in_time",
        "retrospective_event_clock_only",
        "descriptive_no_forecast",
    }
)

LABEL_WINDOW_START_RELATIONS = frozenset(
    {"strictly_after_cutoff", "at_or_after_cutoff", "not_applicable"}
)
LABEL_WINDOW_END_RELATIONS = frozenset(
    {
        "at_or_before_cutoff_plus_horizon",
        "strictly_before_cutoff_plus_horizon",
        "not_applicable",
    }
)

INVESTIGATION_MODES = frozenset(
    {
        "first_party_document_review_only",
        "synthetic_contract_fixture_only",
        "bounded_metadata_canary_proposal",
        "bounded_response_canary_proposal",
    }
)

_OPAQUE_ID = re.compile(r"\A(?:dec|src|rsp|spl|led|cut)_[a-z2-7]{26}\Z", re.ASCII)
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_PREFIX_BY_FIELD = {
    "decision_id": "dec_",
    "source_registry_entry_id": "src_",
    "response_class_id": "rsp_",
    "split_policy_id": "spl_",
    "exposure_ledger_id": "led_",
    "cutoff_semantics_id": "cut_",
}


class DecisionValidationError(ValueError):
    """The proposed source-scope decision is not exactly schema-valid."""


def _fail(path: str, message: str) -> None:
    raise DecisionValidationError(f"{path}: {message}")


def _exact_object(value: Any, keys: frozenset[str], path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(path, "must be a JSON object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys) if all(isinstance(k, str) for k in actual) else []
        detail = []
        if missing:
            detail.append(f"missing={missing!r}")
        if extra:
            detail.append(f"unknown={extra!r}")
        if any(not isinstance(k, str) for k in actual):
            detail.append("non-string key")
        _fail(path, "exact member set required (" + ", ".join(detail) + ")")
    return value


def _literal(value: Any, expected: Any, path: str) -> None:
    if type(value) is not type(expected) or value != expected:
        _fail(path, f"must equal {expected!r}")


def _enum(value: Any, allowed: frozenset[str], path: str) -> str:
    if type(value) is not str or value not in allowed:
        _fail(path, f"must be one of {sorted(allowed)!r}")
    return value


def _integer(value: Any, path: str, *, minimum: int) -> int:
    # JSON booleans are Python ints, so exact type identity is intentional.
    if type(value) is not int or value < minimum:
        _fail(path, f"must be a canonical JSON integer >= {minimum}")
    return value


def _sha256(value: Any, path: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(path, "must be 64 lowercase hexadecimal characters")
    return value


def _opaque_id(value: Any, field: str, path: str) -> str:
    prefix = _PREFIX_BY_FIELD[field]
    if (
        type(value) is not str
        or not value.isascii()
        or _OPAQUE_ID.fullmatch(value) is None
        or not value.startswith(prefix)
    ):
        _fail(path, f"must be an exact 30-byte opaque {prefix!r} identifier")
    return value


def _validate_source_response(value: Any) -> None:
    path = "scientific_source_response"
    obj = _exact_object(
        value, frozenset({"source_registry_entry_id", "response_class_id"}), path
    )
    _opaque_id(
        obj["source_registry_entry_id"],
        "source_registry_entry_id",
        f"{path}.source_registry_entry_id",
    )
    _opaque_id(
        obj["response_class_id"],
        "response_class_id",
        f"{path}.response_class_id",
    )


def _validate_intended_uses(value: Any) -> None:
    path = "intended_uses"
    obj = _exact_object(value, frozenset({"requested_use_ids"}), path)
    uses = obj["requested_use_ids"]
    if type(uses) is not list or not uses:
        _fail(f"{path}.requested_use_ids", "must be a non-empty JSON array")
    if any(type(item) is not str or item not in INTENDED_USE_IDS for item in uses):
        _fail(
            f"{path}.requested_use_ids",
            f"contains a value outside the closed vocabulary {sorted(INTENDED_USE_IDS)!r}",
        )
    if uses != sorted(uses) or len(uses) != len(set(uses)):
        _fail(
            f"{path}.requested_use_ids",
            "must be ASCII-sorted and duplicate-free",
        )


def _validate_future_role_split(value: Any) -> None:
    path = "future_role_split"
    obj = _exact_object(
        value,
        frozenset(
            {
                "requested_future_role",
                "split_policy_id",
                "split_policy_sha256",
                "exposure_ledger_id",
                "unknown_exposure_policy",
                "cross_role_reuse_policy",
            }
        ),
        path,
    )
    _enum(obj["requested_future_role"], FUTURE_ROLES, f"{path}.requested_future_role")
    _opaque_id(obj["split_policy_id"], "split_policy_id", f"{path}.split_policy_id")
    _sha256(obj["split_policy_sha256"], f"{path}.split_policy_sha256")
    ledger = obj["exposure_ledger_id"]
    if ledger != "not_yet_created":
        _opaque_id(ledger, "exposure_ledger_id", f"{path}.exposure_ledger_id")
    _literal(obj["unknown_exposure_policy"], "treat_as_exposed", f"{path}.unknown_exposure_policy")
    _literal(
        obj["cross_role_reuse_policy"],
        "no_role_reassignment_after_observation",
        f"{path}.cross_role_reuse_policy",
    )


def _validate_horizon_cutoff(value: Any) -> None:
    path = "horizon_cutoff"
    obj = _exact_object(
        value,
        frozenset(
            {
                "claim_semantics",
                "prediction_horizon_us",
                "cutoff_semantics_id",
                "cutoff_contract_sha256",
                "label_window_start_relation",
                "label_window_end_relation",
                "availability_formula_id",
                "availability_cutoff_relation",
                "provider_receiver_clocks_separate",
            }
        ),
        path,
    )
    claim = _enum(obj["claim_semantics"], CLAIM_SEMANTICS, f"{path}.claim_semantics")
    horizon = _integer(obj["prediction_horizon_us"], f"{path}.prediction_horizon_us", minimum=0)
    _opaque_id(obj["cutoff_semantics_id"], "cutoff_semantics_id", f"{path}.cutoff_semantics_id")
    _sha256(obj["cutoff_contract_sha256"], f"{path}.cutoff_contract_sha256")
    start = _enum(
        obj["label_window_start_relation"],
        LABEL_WINDOW_START_RELATIONS,
        f"{path}.label_window_start_relation",
    )
    end = _enum(
        obj["label_window_end_relation"],
        LABEL_WINDOW_END_RELATIONS,
        f"{path}.label_window_end_relation",
    )
    _literal(
        obj["availability_formula_id"],
        "max_authenticated_inclusive_upper_bound_us_v2",
        f"{path}.availability_formula_id",
    )
    _literal(
        obj["availability_cutoff_relation"],
        "availability_upper_bound_unix_us_lte_forecast_cutoff_unix_us",
        f"{path}.availability_cutoff_relation",
    )
    _literal(
        obj["provider_receiver_clocks_separate"],
        True,
        f"{path}.provider_receiver_clocks_separate",
    )

    if claim == "descriptive_no_forecast":
        if horizon != 0 or start != "not_applicable" or end != "not_applicable":
            _fail(path, "descriptive_no_forecast requires horizon 0 and both label relations not_applicable")
    else:
        if horizon <= 0:
            _fail(path, "prediction claims require a positive prediction_horizon_us")
        if start == "not_applicable" or end == "not_applicable":
            _fail(path, "prediction claims require applicable label-window relations")


def _validate_bounded_investigation(value: Any) -> None:
    path = "bounded_investigation"
    obj = _exact_object(
        value,
        frozenset(
            {
                "mode",
                "max_documents_proposed",
                "max_provider_requests_proposed",
                "max_raw_bytes_proposed",
                "max_elapsed_seconds_proposed",
                "max_spend_usd_micros_proposed",
                "stop_on_first_rights_or_authority_unknown",
                "stop_before_unregistered_response_class",
                "preserve_failures_without_retry_expansion",
            }
        ),
        path,
    )
    mode = _enum(obj["mode"], INVESTIGATION_MODES, f"{path}.mode")
    documents = _integer(obj["max_documents_proposed"], f"{path}.max_documents_proposed", minimum=0)
    requests = _integer(
        obj["max_provider_requests_proposed"],
        f"{path}.max_provider_requests_proposed",
        minimum=0,
    )
    raw_bytes = _integer(obj["max_raw_bytes_proposed"], f"{path}.max_raw_bytes_proposed", minimum=0)
    _integer(obj["max_elapsed_seconds_proposed"], f"{path}.max_elapsed_seconds_proposed", minimum=1)
    _literal(obj["max_spend_usd_micros_proposed"], 0, f"{path}.max_spend_usd_micros_proposed")
    _literal(
        obj["stop_on_first_rights_or_authority_unknown"],
        True,
        f"{path}.stop_on_first_rights_or_authority_unknown",
    )
    _literal(
        obj["stop_before_unregistered_response_class"],
        True,
        f"{path}.stop_before_unregistered_response_class",
    )
    _literal(
        obj["preserve_failures_without_retry_expansion"],
        True,
        f"{path}.preserve_failures_without_retry_expansion",
    )

    if mode == "first_party_document_review_only":
        if documents <= 0 or requests != 0 or raw_bytes != 0:
            _fail(path, "document review requires documents > 0 and zero provider requests/raw bytes")
    elif mode == "synthetic_contract_fixture_only":
        if documents != 0 or requests != 0 or raw_bytes != 0:
            _fail(path, "synthetic fixture mode requires zero documents/provider requests/raw bytes")
    elif documents != 0:
        _fail(path, "canary proposal modes require max_documents_proposed == 0")


def _validate_non_authority(value: Any) -> None:
    obj = _exact_object(value, NON_AUTHORITY_KEYS, "non_authority")
    for key in NON_AUTHORITY_KEYS:
        _literal(obj[key], False, f"non_authority.{key}")


def validate_decision(value: Any) -> dict[str, Any]:
    """Validate one already-decoded decision and return an isolated copy.

    Exact closed member sets mean a URL, credential, command, request, data row,
    result, score, or other operational payload has no accepted location.
    Opaque IDs cannot encode locators because their byte grammar is closed.
    """

    obj = _exact_object(value, _TOP_LEVEL_KEYS, "decision")
    _literal(obj["schema"], SCHEMA, "decision.schema")
    _opaque_id(obj["decision_id"], "decision_id", "decision.decision_id")
    _literal(obj["decision_status"], DECISION_STATUS, "decision.decision_status")
    _validate_source_response(obj["scientific_source_response"])
    _validate_intended_uses(obj["intended_uses"])
    _validate_future_role_split(obj["future_role_split"])
    _validate_horizon_cutoff(obj["horizon_cutoff"])
    _validate_bounded_investigation(obj["bounded_investigation"])
    _validate_non_authority(obj["non_authority"])
    return copy.deepcopy(obj)


def non_authority_boundary() -> dict[str, bool]:
    """Return a fresh exact all-false non-authority object."""

    return {key: False for key in sorted(NON_AUTHORITY_KEYS)}


def build_decision(
    *,
    decision_id: str,
    scientific_source_response: Mapping[str, Any],
    intended_uses: Mapping[str, Any],
    future_role_split: Mapping[str, Any],
    horizon_cutoff: Mapping[str, Any],
    bounded_investigation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and validate the scope-only body without adding a default choice."""

    value = {
        "schema": SCHEMA,
        "decision_id": decision_id,
        "decision_status": DECISION_STATUS,
        "scientific_source_response": copy.deepcopy(scientific_source_response),
        "intended_uses": copy.deepcopy(intended_uses),
        "future_role_split": copy.deepcopy(future_role_split),
        "horizon_cutoff": copy.deepcopy(horizon_cutoff),
        "bounded_investigation": copy.deepcopy(bounded_investigation),
        "non_authority": non_authority_boundary(),
    }
    return validate_decision(value)


def canonical_decision_bytes(value: Any) -> bytes:
    """Return exact sorted ASCII JSON plus one LF after strict validation."""

    validated = validate_decision(value)
    return (
        json.dumps(
            validated,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


def _reject_float(_: str) -> Any:
    raise DecisionValidationError("decision: JSON floats are forbidden")


def _reject_constant(value: str) -> Any:
    raise DecisionValidationError(f"decision: non-finite JSON value {value!r} is forbidden")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DecisionValidationError(f"decision: duplicate JSON member {key!r}")
        value[key] = item
    return value


def parse_canonical_decision(raw: bytes | str) -> dict[str, Any]:
    """Parse only exact canonical bytes; reject duplicate keys and rewrites."""

    if isinstance(raw, str):
        try:
            raw_bytes = raw.encode("ascii")
        except UnicodeEncodeError as exc:
            raise DecisionValidationError("decision: canonical input must be ASCII") from exc
    elif type(raw) is bytes:
        raw_bytes = raw
    else:
        raise DecisionValidationError("decision: canonical input must be bytes or str")
    try:
        text = raw_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise DecisionValidationError("decision: canonical input must be ASCII") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except DecisionValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DecisionValidationError(f"decision: invalid canonical JSON: {exc}") from exc
    validated = validate_decision(value)
    if raw_bytes != canonical_decision_bytes(validated):
        raise DecisionValidationError(
            "decision: bytes are not sorted compact ASCII JSON followed by exactly one LF"
        )
    return validated


__all__ = [
    "CLAIM_SEMANTICS",
    "DECISION_STATUS",
    "DecisionValidationError",
    "FUTURE_ROLES",
    "INTENDED_USE_IDS",
    "INVESTIGATION_MODES",
    "NON_AUTHORITY_KEYS",
    "SCHEMA",
    "build_decision",
    "canonical_decision_bytes",
    "non_authority_boundary",
    "parse_canonical_decision",
    "validate_decision",
]
