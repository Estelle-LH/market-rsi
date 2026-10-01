"""Compile one exact reviewed D0 choice into a non-executing request plan.

This module is deliberately an offline trust bridge, not a fetch adapter.  It
accepts only the immutable v0.1.25 D0 decision, its field provenance, the exact
frozen Controller packet, and the pinned release source commitment.  All URL,
request, capability and safety fields are resolved from code-owned registries.

No output from this module authorizes a network request, retention, data
admission, Train/Dev/Final access, training, evaluation or publication.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from supervisor_harness.build_p0_gate1_controller_packet import (
    SHORT_BOUNDED_CHOICES,
    SOURCE_REGISTRY,
    SCOPE_DECISION_OPTIONS,
    SCOPE_SOURCE_RESPONSE_OPTIONS,
)
from supervisor_harness.p0_gate1_research_contract import CAPABILITY_REGISTRY
from supervisor_harness.prospective_source_scope_decision import validate_decision


BUNDLE_SCHEMA = "market_p0_gate1_source_scope_document_request_plan_bundle_v1"
PLAN_SCHEMA = "market_p0_gate1_source_scope_document_request_plan_v1"
ADMISSION_REQUIREMENTS_SCHEMA = (
    "market_p0_gate1_source_scope_future_fetch_admission_requirements_v1"
)

D0_CYCLE_ID = "market-rsi-v0125-gate1-controller-d0-20260928-01"
D0_DECISION_ID = "dec_3kd2rdfpz24anpmx5ervi7h6qy"
D0_DECISION_SHA256 = (
    "a4007dfc53d1cda8722e51f2545e95f3666e9d6e3c93c631606809e4f5a763cd"
)
D0_SUBMISSION_SHA256 = (
    "71d3b31caa90b05d95578988bf747386390701421d587cdebef571a59bf051fa"
)
D0_PROVENANCE_SHA256 = (
    "d1344a446e9e04d9f56337cb60d501c7475869213cec7f67db8e00d11a8f683a"
)
D0_RAW_RESPONSE_SHA256 = (
    "126a5a1309251721a45b86ecc51955083234b60a9b40ffe09f4cf03e0f89fd27"
)
FROZEN_PACKET_CANONICAL_SHA256 = (
    "39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b"
)
FROZEN_SCOPE_OPTIONS_SHA256 = (
    "e7834b4946721201feaac1893e356cebd84a3df6eba686d85381cfa612bbd4d0"
)

D0_RELEASE_TAG = "market-rsi-protocol-v0.1.25"
D0_RELEASE_COMMIT = "ed4048e55096b763ba763526e768057b5180cdeb"
D0_RELEASE_TAG_OBJECT = "67b8e4a88e22c1f00e60850f521b26282517d682"
D0_CONTROLLED_SOURCE_SHA256 = (
    "c61f48e21084671c1ff1257639f6a5d5ccfc8c1a64065e02157c5eb75c10a2d4"
)

OPAQUE_SOURCE_ID = "src_" + "b" * 26
OPAQUE_RESPONSE_ID = "rsp_" + "f" * 26
SCIENTIFIC_SOURCE_ID = "polymarket_official_trades"
OPERATION = "inspect_official_documentation"
LEGACY_ENVELOPE_CHOICE_ID = "pm_trades_docs_one"
MAPPING_ID = "d0_scope_pair_to_polymarket_official_trades_v1"
REQUEST_ID = "market-rsi-v0125-polymarket-trades-docs-01"
DOCUMENT_URL = (
    "https://docs.polymarket.com/api-reference/core/"
    "get-trades-for-a-user-or-markets"
)
DOCUMENT_URL_SHA256 = (
    "2f12d47b49fc82adafda53effcc7a11edaa9fbd85a6de9b9403cc90f86cfb3fc"
)

_SOURCE_RECORD_SHA256 = (
    "a61c4017f414d1a3a612c551e3be28afea1f8986397a5f870cf4c2816c1644f8"
)
_SCOPE_OPTION_SHA256 = (
    "47ff092f4255e5ec7b4c2929613146b424854f514b3d67d35ea0324d4cec4554"
)
_CAPABILITY_SHA256 = (
    "39d5c60d3c4bd54fe33fe9662269873a2ec19c2595894fc8c62d44dfe6fddc3c"
)
_ENVELOPE_CHOICE_SHA256 = (
    "aeb48d87f4b2c3a4f26148a910ad756f9bafaa06986e4f2727399cae92f6d0eb"
)

_PROVENANCE_KEYS = frozenset(
    {
        "schema",
        "cycle_id",
        "decision_id",
        "controller_authored_objects",
        "trusted_protocol_fields",
        "submission_sha256",
        "decision_sha256",
        "scope_options_sha256",
        "raw_controller_response_sha256",
        "all_external_authority_false",
    }
)
_CONTROLLER_AUTHORED_OBJECTS = [
    "bounded_investigation",
    "future_role_split",
    "horizon_cutoff",
    "intended_uses",
    "scientific_source_response",
]
_TRUSTED_PROTOCOL_FIELDS = [
    "decision_id",
    "decision_status",
    "non_authority",
    "schema",
    "bounded_investigation.max_spend_usd_micros_proposed",
    "bounded_investigation.preserve_failures_without_retry_expansion",
    "bounded_investigation.stop_before_unregistered_response_class",
    "bounded_investigation.stop_on_first_rights_or_authority_unknown",
    "future_role_split.cross_role_reuse_policy",
    "future_role_split.unknown_exposure_policy",
    "horizon_cutoff.availability_cutoff_relation",
    "horizon_cutoff.availability_formula_id",
    "horizon_cutoff.provider_receiver_clocks_separate",
]

_EXPECTED_DECISION = {
    "schema": "market_rsi_prospective_source_scope_decision_v1",
    "decision_id": D0_DECISION_ID,
    "decision_status": "scope_only_non_executable",
    "scientific_source_response": {
        "source_registry_entry_id": OPAQUE_SOURCE_ID,
        "response_class_id": OPAQUE_RESPONSE_ID,
    },
    "intended_uses": {"requested_use_ids": ["private_research"]},
    "future_role_split": {
        "requested_future_role": "unassigned_candidate",
        "split_policy_id": "spl_" + "j" * 26,
        "split_policy_sha256": (
            "7e3985f09cd825cd888232765aaa567a6990700739741c1896f734243f39730e"
        ),
        "exposure_ledger_id": "not_yet_created",
        "unknown_exposure_policy": "treat_as_exposed",
        "cross_role_reuse_policy": "no_role_reassignment_after_observation",
    },
    "horizon_cutoff": {
        "claim_semantics": "descriptive_no_forecast",
        "prediction_horizon_us": 0,
        "cutoff_semantics_id": "cut_" + "k" * 26,
        "cutoff_contract_sha256": (
            "eff4aa8851da997c8845a43bd137537a08caddb6defeee21355a74e8d567534f"
        ),
        "label_window_start_relation": "not_applicable",
        "label_window_end_relation": "not_applicable",
        "availability_formula_id": (
            "max_authenticated_inclusive_upper_bound_us_v2"
        ),
        "availability_cutoff_relation": (
            "availability_upper_bound_unix_us_lte_forecast_cutoff_unix_us"
        ),
        "provider_receiver_clocks_separate": True,
    },
    "bounded_investigation": {
        "mode": "first_party_document_review_only",
        "max_documents_proposed": 1,
        "max_provider_requests_proposed": 0,
        "max_raw_bytes_proposed": 0,
        "max_elapsed_seconds_proposed": 300,
        "max_spend_usd_micros_proposed": 0,
        "stop_on_first_rights_or_authority_unknown": True,
        "stop_before_unregistered_response_class": True,
        "preserve_failures_without_retry_expansion": True,
    },
    "non_authority": {
        "credential_use_authorized": False,
        "data_capture_authorized": False,
        "data_redistribution_authorized": False,
        "dev_read_authorized": False,
        "evaluation_or_scoring_authorized": False,
        "executable": False,
        "final_read_authorized": False,
        "model_training_authorized": False,
        "network_access_authorized": False,
        "paid_model_authorized": False,
        "provider_access_authorized": False,
        "provider_contact_authorized": False,
        "publication_authorized": False,
        "raw_data_retention_authorized": False,
        "repository_operation_authorized": False,
        "spend_authorized": False,
        "train_admission_authorized": False,
    },
}


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _single(items: list[dict] | tuple[dict, ...], predicate, label: str) -> dict:
    matches = [item for item in items if predicate(item)]
    if len(matches) != 1:
        raise ValueError(f"{label} is missing, duplicated or reassigned")
    return deepcopy(matches[0])


def _controller_submission(decision: dict) -> dict:
    """Reconstruct only the five objects that the Controller authored."""

    investigation = decision["bounded_investigation"]
    future = decision["future_role_split"]
    horizon = decision["horizon_cutoff"]
    return {
        "bounded_investigation": {
            key: investigation[key]
            for key in (
                "max_documents_proposed",
                "max_elapsed_seconds_proposed",
                "max_provider_requests_proposed",
                "max_raw_bytes_proposed",
                "mode",
            )
        },
        "future_role_split": {
            key: future[key]
            for key in (
                "exposure_ledger_id",
                "requested_future_role",
                "split_policy_id",
                "split_policy_sha256",
            )
        },
        "horizon_cutoff": {
            key: horizon[key]
            for key in (
                "claim_semantics",
                "cutoff_contract_sha256",
                "cutoff_semantics_id",
                "label_window_end_relation",
                "label_window_start_relation",
                "prediction_horizon_us",
            )
        },
        "intended_uses": deepcopy(decision["intended_uses"]),
        "scientific_source_response": deepcopy(
            decision["scientific_source_response"]
        ),
    }


def _validate_inputs(
    decision: dict,
    decision_provenance: dict,
    packet: dict,
    d0_source_sha256: str,
) -> tuple[dict, dict, dict, dict]:
    if type(d0_source_sha256) is not str or (
        d0_source_sha256 != D0_CONTROLLED_SOURCE_SHA256
    ):
        raise ValueError("D0 controlled-source commitment changed")
    if type(packet) is not dict or _digest(packet) != FROZEN_PACKET_CANONICAL_SHA256:
        raise ValueError("Controller packet differs from the frozen D0 packet")
    options = packet.get("prospective_source_scope_decision")
    if (
        options != SCOPE_DECISION_OPTIONS
        or _digest(options) != FROZEN_SCOPE_OPTIONS_SHA256
        or packet.get("allowed_sources") != list(SOURCE_REGISTRY)
    ):
        raise ValueError("packet source/scope registries changed")

    validated = validate_decision(decision)
    if validated != _EXPECTED_DECISION or _digest(validated) != D0_DECISION_SHA256:
        raise ValueError("decision is not the exact independently reviewed D0")
    submission = _controller_submission(validated)
    if _digest(submission) != D0_SUBMISSION_SHA256:
        raise ValueError("Controller-authored submission commitment changed")

    expected_provenance = {
        "schema": "market_rsi_source_scope_field_provenance_v1",
        "cycle_id": D0_CYCLE_ID,
        "decision_id": D0_DECISION_ID,
        "controller_authored_objects": _CONTROLLER_AUTHORED_OBJECTS,
        "trusted_protocol_fields": _TRUSTED_PROTOCOL_FIELDS,
        "submission_sha256": D0_SUBMISSION_SHA256,
        "decision_sha256": D0_DECISION_SHA256,
        "scope_options_sha256": FROZEN_SCOPE_OPTIONS_SHA256,
        "raw_controller_response_sha256": D0_RAW_RESPONSE_SHA256,
        "all_external_authority_false": True,
    }
    if (
        type(decision_provenance) is not dict
        or set(decision_provenance) != _PROVENANCE_KEYS
        or decision_provenance != expected_provenance
        or _digest(decision_provenance) != D0_PROVENANCE_SHA256
    ):
        raise ValueError("decision provenance is not the exact reviewed record")

    source_record = _single(
        SOURCE_REGISTRY,
        lambda item: item.get("source_id") == SCIENTIFIC_SOURCE_ID,
        "scientific source registry record",
    )
    if (
        source_record
        != {
            "source_id": SCIENTIFIC_SOURCE_ID,
            "authority": "official",
            "scope": "market-scoped trade query documentation",
            "url": DOCUMENT_URL,
        }
        or _digest(source_record) != _SOURCE_RECORD_SHA256
        or _text_sha256(source_record["url"]) != DOCUMENT_URL_SHA256
    ):
        raise ValueError("trusted scientific source registry record changed")

    scope_option = _single(
        SCOPE_SOURCE_RESPONSE_OPTIONS,
        lambda item: item.get("source_registry_entry_id") == OPAQUE_SOURCE_ID,
        "opaque source/response option",
    )
    if (
        scope_option.get("response_class_id") != OPAQUE_RESPONSE_ID
        or _digest(scope_option) != _SCOPE_OPTION_SHA256
    ):
        raise ValueError("opaque source/response mapping changed")

    capabilities = CAPABILITY_REGISTRY.get(SCIENTIFIC_SOURCE_ID)
    if type(capabilities) is not dict or set(capabilities) != {
        "inspect_official_documentation",
        "fetch_fixed_public_sample",
    }:
        raise ValueError("source capability registry changed")
    capability = deepcopy(capabilities.get(OPERATION))
    if type(capability) is not dict or _digest(capability) != _CAPABILITY_SHA256:
        raise ValueError("documentation capability changed")

    envelope = _single(
        SHORT_BOUNDED_CHOICES,
        lambda item: item.get("choice_id") == LEGACY_ENVELOPE_CHOICE_ID,
        "documentation request envelope",
    )
    if _digest(envelope) != _ENVELOPE_CHOICE_SHA256:
        raise ValueError("documentation request envelope changed")
    return validated, source_record, capability, envelope


def compile_document_request_plan(
    decision: dict,
    decision_provenance: dict,
    packet: dict,
    *,
    d0_source_sha256: str,
) -> dict:
    """Return the sole deterministic plan for the reviewed v0.1.25 D0.

    The keyword-only source commitment is evidence, not caller authority.  It
    must equal the hard-pinned published D0 source digest.  The exact signature
    intentionally leaves no location, method, parameter, header, limit,
    handler, authority or retry field for a caller to supply.
    """

    validated, source_record, capability, envelope = _validate_inputs(
        decision, decision_provenance, packet, d0_source_sha256
    )
    sample_rule = envelope["fixed_sample_rule"]
    sample_contract = capability["sample_contracts"].get(sample_rule)
    if (
        sample_contract
        != {
            "rule_id": "single_registry_document_v1",
            "kind": "single_trusted_registry_document",
            "document_count": 1,
            "source_resolution": "exact_trusted_source_registry_record",
        }
        or capability["constraints"]
        != {"max_requests": 1, "max_provider_cost_usd": "0"}
        or envelope["derived_bounds"]
        != {
            "max_requests": 1,
            "max_bytes": 1_000_000,
            "max_minutes": 5,
            "max_provider_cost_usd": "0",
        }
    ):
        raise ValueError("documentation sample contract or bounds changed")

    plan = {
        "schema": PLAN_SCHEMA,
        "bindings": {
            "cycle_id": D0_CYCLE_ID,
            "decision_id": D0_DECISION_ID,
            "decision_canonical_sha256": D0_DECISION_SHA256,
            "controller_submission_canonical_sha256": D0_SUBMISSION_SHA256,
            "decision_provenance_canonical_sha256": D0_PROVENANCE_SHA256,
            "raw_controller_response_sha256": D0_RAW_RESPONSE_SHA256,
            "packet_canonical_sha256": FROZEN_PACKET_CANONICAL_SHA256,
            "scope_options_canonical_sha256": FROZEN_SCOPE_OPTIONS_SHA256,
            "d0_release_tag": D0_RELEASE_TAG,
            "d0_release_commit": D0_RELEASE_COMMIT,
            "d0_release_tag_object": D0_RELEASE_TAG_OBJECT,
            "d0_controlled_source_sha256": D0_CONTROLLED_SOURCE_SHA256,
        },
        "source_mapping": {
            "mapping_id": MAPPING_ID,
            "opaque_source_registry_entry_id": OPAQUE_SOURCE_ID,
            "opaque_response_class_id": OPAQUE_RESPONSE_ID,
            "scientific_source_id": SCIENTIFIC_SOURCE_ID,
            "registry_record": source_record,
            "registry_record_canonical_sha256": _SOURCE_RECORD_SHA256,
            "registered_capability": capability,
            "registered_capability_canonical_sha256": _CAPABILITY_SHA256,
            "legacy_envelope_choice": envelope,
            "legacy_envelope_choice_canonical_sha256": _ENVELOPE_CHOICE_SHA256,
            "selected_sample_contract": deepcopy(sample_contract),
        },
        "prospective_request": {
            "request_id": REQUEST_ID,
            "method": "GET",
            "url": DOCUMENT_URL,
            "url_sha256": DOCUMENT_URL_SHA256,
            "query_parameters": [],
            "body": None,
            "transport_headers": {
                "Accept": "application/json,text/html,text/plain;q=0.9",
                "User-Agent": "MarketRSI-Public-Research/1.0",
            },
        },
        "limits": {
            "max_documents": 1,
            "max_http_attempts_if_later_authorized": 1,
            "max_response_bytes_if_later_authorized": 1_000_000,
            "max_elapsed_seconds_if_later_authorized": 300,
            "transport_timeout_seconds_if_later_authorized": 15,
            "watchdog_heartbeat_deadline_seconds_if_later_authorized": 20,
            "watchdog_progress_deadline_seconds_if_later_authorized": 30,
            "d0_provider_requests_proposed": 0,
            "d0_provider_raw_bytes_proposed": 0,
            "provider_cost_usd_micros": 0,
        },
        "policy": {
            "redirects_allowed": False,
            "automatic_retries_allowed": False,
            "alternate_host_or_page_allowed": False,
            "link_following_allowed": False,
            "documented_api_call_allowed": False,
            "authentication_allowed": False,
            "credential_use_allowed": False,
            "purchase_allowed": False,
            "source_write_allowed": False,
            "failure_is_terminal_for_attempt": True,
            "preserve_failures_without_retry_expansion": True,
            "stop_on_first_rights_or_authority_unknown": True,
        },
        "response_contract_if_later_authorized": {
            "required_status": 200,
            "final_url_must_equal_request_url": True,
            "redirect_count_must_equal": 0,
            "body_must_be_nonempty_bytes": True,
            "max_body_bytes": 1_000_000,
            "allowed_normalized_content_types": [
                "application/json",
                "text/html",
                "text/markdown",
                "text/plain",
            ],
            "receipt_response_headers_allowlist": ["etag", "last-modified"],
            "max_receipt_header_value_utf8_bytes": 500,
            "external_bytes_are_untrusted_text": True,
        },
        "success_evidence_if_later_authorized": {
            "snapshot_byte_count_required": True,
            "snapshot_sha256_required": True,
            "canonical_receipt_required": True,
            "receipt_file_sha256_required": True,
            "watchdog_input_progress_result_crosslinks_required": True,
            "rights_or_data_admission_not_inferred_from_http_success": True,
        },
        "authority": {
            "plan_only": True,
            "request_executable": False,
            "fetch_admission_present": False,
            "network_fetch_authorized": False,
            "credential_use_authorized": False,
            "purchase_or_spend_authorized": False,
            "snapshot_retention_authorized": False,
            "catalog_or_prediction_data_access_authorized": False,
            "train_admission_authorized": False,
            "train_read_authorized": False,
            "dev_read_authorized": False,
            "final_read_authorized": False,
            "model_training_authorized": False,
            "evaluation_or_scoring_authorized": False,
            "data_redistribution_authorized": False,
            "repository_operation_authorized": False,
            "publication_authorized": False,
        },
        "claim_boundaries": {
            "decision_validated": validated == _EXPECTED_DECISION,
            "request_compiled_offline": True,
            "provider_or_model_called": False,
            "network_request_performed": False,
            "external_bytes_received": False,
            "source_rights_proven": False,
            "snapshot_retained": False,
            "prediction_data_admitted": False,
            "future_role_assigned": False,
            "train_dev_or_final_read": False,
            "training_or_evaluation_performed": False,
            "prediction_improvement_proven": False,
        },
    }
    plan_sha256 = _digest(plan)
    return {
        "schema": BUNDLE_SCHEMA,
        "request_plan": plan,
        "request_plan_canonical_sha256": plan_sha256,
        "future_fetch_admission_requirements": {
            "schema": ADMISSION_REQUIREMENTS_SCHEMA,
            "required": True,
            "fetch_authorized": False,
            "fresh_attempt_id_required": True,
            "same_id_retry_forbidden": True,
            "must_bind_request_plan_canonical_sha256": plan_sha256,
            "must_bind_scientific_source_id": SCIENTIFIC_SOURCE_ID,
            "must_bind_exact_url_sha256": DOCUMENT_URL_SHA256,
            "must_bind_max_requests": 1,
            "must_bind_max_response_bytes": 1_000_000,
            "separate_rights_and_retention_review_required": True,
            "separate_candidate_and_formal_train_admission_required": True,
            "outer_process_and_watchdog_gate_required": True,
        },
        "claim_boundaries": {
            "offline_compilation_only": True,
            "fetch_authorized": False,
            "network_request_performed": False,
            "data_admitted": False,
            "training_or_evaluation_performed": False,
            "publication_authorized": False,
        },
    }
