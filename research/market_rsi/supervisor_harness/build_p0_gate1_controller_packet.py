"""Build the frozen, nonsealed Gate 1 data-research packet.

This builder does not call a model, fetch data, open an evaluation split, or
admit a source.  It converts already-reviewed aggregate evidence into the only
information a Controller may use to choose one bounded source investigation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from market_rsi import digest


SCHEMA = "market_p0_gate1_controller_packet_v5"
RIGHTS_POLICY = {
    "policy_id": "official_public_research_only_v1",
    "requirements": [
        "use only the selected allowlisted official public source",
        "do not use credentials, purchases, or source writes",
        "do not infer research-use rights from technical accessibility",
        "record rights as unknown unless the official source states them",
        "do not admit fetched material into formal prediction data",
    ],
}
ALLOWED_QUESTIONS = (
    "2023_missing_market_identities",
    "2023_real_fill_sparsity",
    "2025_whole_season_trade_access",
    "pbp_event_clock_quality",
    "research_use_rights",
)
SOURCE_REGISTRY = (
    {
        "source_id": "polymarket_official_market_data",
        "authority": "official",
        "scope": "market metadata, price history, and documented trade interfaces",
        "url": "https://docs.polymarket.com/market-data/prices-order-books",
    },
    {
        "source_id": "polymarket_official_trades",
        "authority": "official",
        "scope": "market-scoped trade query documentation",
        "url": "https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets",
    },
    {
        "source_id": "kalshi_official_historical_data",
        "authority": "official",
        "scope": "historical market and trade endpoint documentation",
        "url": "https://docs.kalshi.com/getting_started/historical_data",
    },
    {
        "source_id": "nflverse_official_pbp_releases",
        "authority": "official_project_release",
        "scope": "versioned play-by-play releases",
        "url": "https://github.com/nflverse/nflverse-pbp/releases",
    },
)
DOCUMENT_SAMPLE_RULES = (
    "Inspect the one frozen official documentation page.",
    "Inspect the single frozen official documentation page.",
)
RELEASE_SAMPLE_RULES = (
    "Inspect the one frozen official project release page.",
    "Inspect the single frozen official project release page.",
)
EXECUTABLE_DOCUMENTATION_CHOICES = [
    {
        "source_id": source["source_id"],
        "requested_operations": ["inspect_official_documentation"],
        "fixed_sample_rule_options": list(
            RELEASE_SAMPLE_RULES if source["source_id"] == "nflverse_official_pbp_releases"
            else DOCUMENT_SAMPLE_RULES
        ),
        "max_requests": 1,
        "max_provider_cost_usd": "0",
    }
    for source in SOURCE_REGISTRY
]
SHORT_BOUNDED_CHOICES = [
    {
        "choice_id": choice_id,
        "source_id": source_id,
        "operation": "inspect_official_documentation",
        "fixed_sample_rule": rule,
        "derived_bounds": {
            "max_requests": 1,
            "max_bytes": 1_000_000,
            "max_minutes": 5,
            "max_provider_cost_usd": "0",
        },
    }
    for choice_id, source_id, rule in (
        ("pm_market_docs_one", "polymarket_official_market_data", DOCUMENT_SAMPLE_RULES[0]),
        ("pm_market_docs_single", "polymarket_official_market_data", DOCUMENT_SAMPLE_RULES[1]),
        ("pm_trades_docs_one", "polymarket_official_trades", DOCUMENT_SAMPLE_RULES[0]),
        ("pm_trades_docs_single", "polymarket_official_trades", DOCUMENT_SAMPLE_RULES[1]),
        ("kalshi_history_docs_one", "kalshi_official_historical_data", DOCUMENT_SAMPLE_RULES[0]),
        ("kalshi_history_docs_single", "kalshi_official_historical_data", DOCUMENT_SAMPLE_RULES[1]),
        ("nflverse_pbp_release_one", "nflverse_official_pbp_releases", RELEASE_SAMPLE_RULES[0]),
        ("nflverse_pbp_release_single", "nflverse_official_pbp_releases", RELEASE_SAMPLE_RULES[1]),
    )
]

# The v5 paid decision is a scope-only D0 choice.  These opaque identifiers
# commit reviewed Controller-facing briefs without carrying a URL, endpoint,
# credential, command, request or data row.  The legacy documentation choices
# remain in the packet as immutable historical context, not as submission tools.
SCOPE_SOURCE_RESPONSE_OPTIONS = (
    {
        "source_registry_entry_id": "src_" + "a" * 26,
        "response_class_id": "rsp_" + "e" * 26,
        "controller_brief": (
            "Official Polymarket market metadata, price-history and order-book "
            "response class; accessibility, rights, timing and coverage remain unknown."
        ),
    },
    {
        "source_registry_entry_id": "src_" + "b" * 26,
        "response_class_id": "rsp_" + "f" * 26,
        "controller_brief": (
            "Official Polymarket market-scoped trade response class; accessibility, "
            "rights, point-in-time timing and whole-season coverage remain unknown."
        ),
    },
    {
        "source_registry_entry_id": "src_" + "c" * 26,
        "response_class_id": "rsp_" + "g" * 26,
        "controller_brief": (
            "Official Kalshi historical market/trade response class; mechanism "
            "comparability, rights, timing and coverage remain unknown."
        ),
    },
    {
        "source_registry_entry_id": "src_" + "d" * 26,
        "response_class_id": "rsp_" + "h" * 26,
        "controller_brief": (
            "Versioned nflverse play-by-play release response class; it supplies "
            "event-clock/game evidence only and no prediction-market response."
        ),
    },
)

SCOPE_SPLIT_POLICY = {
    "split_policy_id": "spl_" + "j" * 26,
    "policy": {
        "name": "prospective_chronological_train_dev_final_v1",
        "roles": [
            "development_candidate", "diagnostic_only", "final_candidate",
            "train_candidate", "unassigned_candidate",
        ],
        "unknown_exposure_policy": "treat_as_exposed",
        "cross_role_reuse_policy": "no_role_reassignment_after_observation",
        "minimum_untouched_final_dates": 20,
        "membership_committed_before_role_open": True,
    },
}
SCOPE_SPLIT_POLICY["split_policy_sha256"] = digest(SCOPE_SPLIT_POLICY["policy"])

SCOPE_CUTOFF_CONTRACT = {
    "cutoff_semantics_id": "cut_" + "k" * 26,
    "contract": {
        "name": "predeclared_forecast_cutoff_and_label_window_v1",
        "availability_formula_id": "max_authenticated_inclusive_upper_bound_us_v2",
        "availability_cutoff_relation": (
            "availability_upper_bound_unix_us_lte_forecast_cutoff_unix_us"
        ),
        "provider_receiver_clocks_separate": True,
        "retrospective_event_clock_is_not_point_in_time": True,
    },
}
SCOPE_CUTOFF_CONTRACT["cutoff_contract_sha256"] = digest(
    SCOPE_CUTOFF_CONTRACT["contract"])

SCOPE_DECISION_OPTIONS = {
    "source_response_options": deepcopy(list(SCOPE_SOURCE_RESPONSE_OPTIONS)),
    "split_policy": deepcopy(SCOPE_SPLIT_POLICY),
    "cutoff_contract": deepcopy(SCOPE_CUTOFF_CONTRACT),
    "intended_use_ids": [
        "derived_dataset_redistribution", "durable_local_retention",
        "external_derived_outputs", "internal_derived_outputs",
        "model_artifact_redistribution", "model_training", "private_research",
        "raw_data_redistribution",
    ],
    "future_roles": [
        "development_candidate", "diagnostic_only", "final_candidate",
        "train_candidate", "unassigned_candidate",
    ],
    "claim_semantics": [
        "descriptive_no_forecast", "prospective_point_in_time",
        "retrospective_event_clock_only",
    ],
    "investigation_modes": [
        "bounded_metadata_canary_proposal", "bounded_response_canary_proposal",
        "first_party_document_review_only", "synthetic_contract_fixture_only",
    ],
    "hard_proposed_caps": {
        "max_documents": 5,
        "max_provider_requests": 1,
        "max_raw_bytes": 1_000_000,
        "max_elapsed_seconds": 600,
        "max_spend_usd_micros": 0,
    },
    "rights_status": "unknown_each_requested_use_requires_later_D2_evidence",
}
PRIOR_CONTROLLER_FEEDBACK = {
    "attempt_id": "market-rsi-gate1-controller-20260922-02",
    "raw_response_sha256": (
        "b34b169ba79b1ecebb55c127c350ef568a982c518f0c4454459bc1c357bcb4bb"
    ),
    "reported_model": "zai-org/GLM-5.3:peft:262144",
    "selected_question_id": "2025_whole_season_trade_access",
    "selected_source_id": "polymarket_official_trades",
    "requested_operations": ["inspect_official_documentation"],
    "requested_max_requests": 1,
    "outcome": "invalid_submission_no_task_or_fetch",
    "observed_failure": (
        "The model emitted malformed <arg_key>/<arg_value> tool tags. The "
        "then-current adapter rejected the parsed field set before any task or "
        "fetch. A later strict parser now rejects those raw tags."
    ),
    "additional_contract_mismatch": (
        "The older -01 attempt paraphrased an exact rule. Both historical "
        "responses remain terminal. The new bounded tool accepts only a short "
        "choice ID and scientific text; trusted code derives the exact rule."
    ),
    "metered_cost_usd_not_invoice": "0.01790424",
    "next_decision": (
        "The previous responses stay immutable. You may revise the idea or "
        "propose a different source or method; no option is preselected. "
        "For a bounded executable submission, select one trusted choice ID."
    ),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("receipt must be a JSON object")
    return value


def build(gate0: dict, live_acceptance: dict) -> dict:
    if (gate0.get("schema") != "market_p0_gate0_verdict_v1"
            or gate0.get("metadata_inventory_passed") is not True
            or gate0.get("2025_formal_final_admitted") is not False):
        raise ValueError("Gate 0 is not the expected closed-data verdict")
    boundaries = live_acceptance.get("claim_boundaries")
    if (live_acceptance.get("schema") != "market_controller_b_live_acceptance_v1"
            or live_acceptance.get("passed") is not True
            or not isinstance(boundaries, dict)
            or boundaries.get("bounded_live_transport_and_accounting_proven") is not True
            or boundaries.get("formal_admission") is not False
            or boundaries.get("prediction_improvement_proven") is not False):
        raise ValueError("bounded live transport acceptance is missing or overstated")
    return {
        "schema": SCHEMA,
        "purpose": (
            "record one complete non-executable Controller D0 source/use/scope "
            "decision; every operational and rights gate remains later"
        ),
        "prior_controller_feedback": deepcopy(PRIOR_CONTROLLER_FEEDBACK),
        "known_aggregate_evidence": {
            "season_2023": {
                "scheduled_games": 285,
                "strict_market_identity_matches": 237,
                "unmatched_games": 48,
                "fixed_fill_diagnostic_regular_season_games": 9,
                "fixed_fill_diagnostic_zero_fill_games": 5,
            },
            "season_2024": {
                "mapped_games": 284,
                "trade_rows": 407225,
                "timed_pbp_plays": 47875,
                "plays_with_future_trade_60s": 32384,
                "plays_with_future_trade_300s": 43506,
            },
            "season_2025": {
                "scheduled_game_identities": 285,
                "directly_checked_games": 1,
                "directly_checked_game_trades": 2148,
                "whole_season_trade_label_audit": "not_completed",
            },
            "evaluation_boundary": {
                "old_final_dates": 11,
                "minimum_formal_final_dates": 20,
                "old_final_admitted": False,
            },
        },
        "allowed_questions": list(ALLOWED_QUESTIONS),
        "allowed_sources": deepcopy(list(SOURCE_REGISTRY)),
        "trusted_rights_policy": deepcopy(RIGHTS_POLICY),
        "required_decision_fields": [
            "investigation_id", "question_id", "source_id",
            "hypothesis", "fixed_sample_rule", "requested_operations",
            "expected_evidence", "max_requests", "max_bytes",
            "max_minutes", "max_provider_cost_usd", "stop_rule",
        ],
        "required_bounded_submission_fields": [
            "choice_id", "question_id", "hypothesis",
            "expected_evidence", "stop_rule",
        ],
        "trusted_bounded_choices": deepcopy(SHORT_BOUNDED_CHOICES),
        "prospective_source_scope_decision": deepcopy(SCOPE_DECISION_OPTIONS),
        "hard_limits": {
            "choose_exactly_one_question": True,
            "choose_exactly_one_source": True,
            "max_requests_ceiling": 20,
            "max_bytes_ceiling": 5000000,
            "max_minutes_ceiling": 30,
            "max_provider_cost_usd_ceiling": "0.05",
            "purchase_allowed": False,
            "sealed_or_scored_rows_allowed": False,
            "benchmark_prompts_or_outcomes_allowed": False,
            "source_write_allowed": False,
            "silent_retry_allowed": False,
            "formal_admission_from_this_decision": False,
        },
        "current_execution_boundary": {
            "controller_transport_accepted": True,
            "arbitrary_research_task_execution_accepted": False,
            "reviewed_real_train_catalog_available": False,
            "instruction": (
                "Return one complete scope-only D0 decision across source/response, "
                "intended uses, future role/split, horizon/cutoff and one bounded "
                "investigation mode. This does not contact, fetch, purchase, retain, "
                "admit, train, score, open Dev/Final or publish anything."
            ),
        },
    }


def run(repo: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Gate 1 packet output must be fresh")
    sources = {
        "gate0_verdict": repo / "artifacts/p0-data-admission-gate0-20260918-01/gate0-verdict.json",
        "live_transport_acceptance": repo / "research/market_rsi/supervisor_harness/P0_CONTROLLER_B_LIVE_ACCEPTANCE_2026-09-19.json",
    }
    before = {name: _sha(path) for name, path in sources.items()}
    packet = build(_load(sources["gate0_verdict"]),
                   _load(sources["live_transport_acceptance"]))
    output.mkdir(parents=True)
    packet_path = output / "controller-input.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True, indent=2) + "\n")
    after = {name: _sha(path) for name, path in sources.items()}
    if before != after:
        raise ValueError("input receipt changed while building Gate 1 packet")
    receipt = {
        "schema": "market_p0_gate1_packet_receipt_v1",
        "source_sha256": before,
        # Keep the historical field as the exact on-disk byte commitment.
        # New consumers must use the explicitly named commitments below.
        "packet_sha256": _sha(packet_path),
        "packet_file_sha256": _sha(packet_path),
        "packet_canonical_sha256": digest(packet),
        "model_called": False,
        "data_fetched": False,
        "sealed_data_read": False,
        "provider_cost_usd": "0",
        "formal_data_admitted": False,
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.repo.resolve(), args.output.resolve()), sort_keys=True))
