"""Frozen contract for the next Codex-harnessed market-research controller.

This module is control-plane only.  It does not call Codex, Tinker, E2B, or a
market data source.  A paid v3 run must bind this contract to a fresh run ID and
pass a separate isolation canary before dispatch.
"""
from __future__ import annotations

import copy
from decimal import Decimal

import prospective_data_lifecycle
from glm_canary import MODEL, RATES
from market_rsi import digest, file_hash, identifier
from objective_contract import validate_objective_contract
from time_series_research_harness import harness_contract as time_series_harness_contract
from time_series_split_policy import policy_contract


SCHEMA = "market_controller_harness_v4"
HARNESS = "codex"
MAX_INPUT_TOKENS_PER_TURN = 196_608
MAX_OUTPUT_TOKENS_PER_TURN = 65_536
# Twelve full 64K inputs, or more shorter recovery turns.  The earlier 256K
# cap was exhausted by six valid research turns after Archive carryover and
# several data pages, before the controller could execute any Round 2 child.
MAX_CUMULATIVE_INPUT_TOKENS = 1_572_864
MAX_CUMULATIVE_OUTPUT_TOKENS = 65_536
MAX_CONTEXT_TOKENS = 262_144
# The researcher may spend most of the session on evidence gathering, but it
# must never be offered the final output token without a chance to submit.  The
# adapter switches to a submit-only view at the trigger and keeps this reserve
# out of ordinary research turns.  It never invents or repairs the decision.
TERMINAL_SUBMISSION_OUTPUT_RESERVE = 16_384
TERMINAL_SUBMISSION_TRIGGER_OUTPUT = 32_768
TERMINAL_SUBMISSION_MAX_OUTPUT = 16_384
TERMINAL_SUBMISSION_TOOL_RESERVE = 4
# More turns do not increase the session-wide token or tool budget.  They let
# the workbench return recoverable validation errors without consuming the
# controller's entire research opportunity.
# Match the tool-call ceiling so a controller that uses the full candidate
# allowance can still correct validation mistakes and submit.  The session-wide
# token and dollar ceilings remain unchanged.
MAX_TURNS = 32
MAX_TOOL_CALLS = 32
MAX_CANDIDATE_EXECUTIONS = 3
MAX_WALL_SECONDS = 1_800
MAX_FINAL_DECISION_BYTES = 16_384

ALLOWED_TOOLS = (
    "inspect_train_dev",
    "read_objective_contract",
    "read_harness_profile",
    "read_research_guide",
    "search_public_literature",
    "list_algorithms",
    "inspect_algorithm",
    "write_candidate",
    "run_train_cv_candidate",
    "read_own_research_history",
    "submit_decision",
)

DENIED_CAPABILITIES = (
    "read_future_test",
    "read_current_dev_labels",
    "reuse_consumed_dev_for_evaluation",
    "change_data_lifecycle",
    "read_other_arm",
    "read_host_filesystem",
    "read_credentials",
    "change_scorer",
    "change_eligible_rows",
    "direct_paid_dispatch",
    "unlogged_network",
)


def _usd(input_tokens: int, output_tokens: int) -> Decimal:
    million = Decimal(1_000_000)
    return (
        Decimal(input_tokens) * Decimal(RATES["prefill_per_million"])
        + Decimal(output_tokens) * Decimal(RATES["output_per_million"])
    ) / million


def build_contract(*, experiment_id: str, opaque_test_commitment: str,
                   objective_contract: dict) -> dict:
    """Return the immutable v3 controller envelope for one fresh experiment."""
    identifier(experiment_id)
    if (
        not isinstance(opaque_test_commitment, str)
        or len(opaque_test_commitment) != 64
        or any(ch not in "0123456789abcdef" for ch in opaque_test_commitment)
    ):
        raise ValueError("opaque test commitment must be one lowercase sha256")

    objective = validate_objective_contract(
        copy.deepcopy(objective_contract), experiment_id=experiment_id
    )
    contract = {
        "schema": SCHEMA,
        "experiment_id": experiment_id,
        "controller": {
            "model": MODEL,
            "role": "research_decision_maker",
            "weights_change_during_study": False,
        },
        "harness": {
            "engine": HARNESS,
            "role": "multi_turn_research_workbench",
            "model_adapter": "codex_responses_to_tinker_glm_v2",
            "memory_mode": "archive_only",
            "profile_policy": "one_frozen_h0_for_entire_archive_lineage",
            "profile_changes_during_archive_lineage": 0,
            "tool_proposals_during_archive_lineage": "archive_only_not_activated",
            "controller_writes_learned_guide": False,
            "one_permanent_session_per_arm_task": True,
            "automatic_resampling": 0,
            "allowed_tools": list(ALLOWED_TOOLS),
            "denied_capabilities": list(DENIED_CAPABILITIES),
        },
        "research_budget": {
            "max_input_tokens_per_turn": MAX_INPUT_TOKENS_PER_TURN,
            "max_output_tokens_per_turn": MAX_OUTPUT_TOKENS_PER_TURN,
            "max_cumulative_input_tokens": MAX_CUMULATIVE_INPUT_TOKENS,
            "max_cumulative_output_tokens": MAX_CUMULATIVE_OUTPUT_TOKENS,
            "max_context_tokens": MAX_CONTEXT_TOKENS,
            "terminal_submission_output_reserve": TERMINAL_SUBMISSION_OUTPUT_RESERVE,
            "terminal_submission_trigger_output": TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
            "terminal_submission_max_output": TERMINAL_SUBMISSION_MAX_OUTPUT,
            "terminal_submission_tool_reserve": TERMINAL_SUBMISSION_TOOL_RESERVE,
            "max_turns": MAX_TURNS,
            "max_tool_calls": MAX_TOOL_CALLS,
            "max_candidate_executions": MAX_CANDIDATE_EXECUTIONS,
            "max_wall_seconds": MAX_WALL_SECONDS,
            "worst_case_controller_usd": str(
                _usd(MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS)
            ),
            "accounting": "sum_actual_tokens_across_all_harness_turns",
        },
        "decision_envelope": {
            "max_bytes": MAX_FINAL_DECISION_BYTES,
            "long_notebook_is_separate": True,
            "required_fields": [
                "action",
                "question",
                "hypothesis",
                "evidence",
                "candidate_artifact",
                "expected_failure_condition",
            ],
        },
        "evidence_policy": {
            "objective_contract": objective,
            "controller_may_change_objective": False,
            "visible_splits": ["train", "dev"],
            "controller_learning_access": "all_train_and_consumed_dev_with_labels",
            "current_dev_access": "features_only_until_final_candidate_is_frozen",
            "controller_visible_candidate_scores": "reusable_train_cv_only",
            "sealed_dev_execution": "runner_once_after_controller_session_exits",
            "sealed_dev_score_visibility": "next_round_archive_only",
            "dev_after_score": "atomically_promote_to_next_round_train",
            "consumed_dev_evaluation_reuse": "forbidden",
            "future_test": "opaque_until_all_final_submissions_freeze",
            "opaque_test_commitment": opaque_test_commitment,
            "data_lifecycle_schema": prospective_data_lifecycle.SCHEMA,
            "data_lifecycle_source_sha256": file_hash(
                prospective_data_lifecycle.__file__),
            "time_series_validation": policy_contract(),
            "time_series_research_harness": time_series_harness_contract(),
            "literature_search": "public_results_snapshotted_with_query_url_time_and_hash",
            "candidate_execution": "runner_owned_e2b_only",
            "scoring": "fixed_runner_owned_common_rows",
        },
    }
    validate_contract(contract)
    return copy.deepcopy(contract)


def validate_contract(contract: dict) -> dict:
    """Fail closed if a v3 contract weakens autonomy or evaluation isolation."""
    if not isinstance(contract, dict) or set(contract) != {
        "schema",
        "experiment_id",
        "controller",
        "harness",
        "research_budget",
        "decision_envelope",
        "evidence_policy",
    }:
        raise ValueError("unexpected controller contract fields")
    identifier(contract["experiment_id"])
    if contract["schema"] != SCHEMA:
        raise ValueError("wrong controller contract schema")
    if contract["controller"] != {
        "model": MODEL,
        "role": "research_decision_maker",
        "weights_change_during_study": False,
    }:
        raise ValueError("controller identity or role changed")

    harness = contract["harness"]
    if (
        harness.get("engine") != HARNESS
        or harness.get("role") != "multi_turn_research_workbench"
        or harness.get("model_adapter") != "codex_responses_to_tinker_glm_v2"
        or harness.get("memory_mode") != "archive_only"
        or harness.get("profile_policy") != "one_frozen_h0_for_entire_archive_lineage"
        or harness.get("profile_changes_during_archive_lineage") != 0
        or harness.get("tool_proposals_during_archive_lineage")
        != "archive_only_not_activated"
        or harness.get("controller_writes_learned_guide") is not False
        or harness.get("one_permanent_session_per_arm_task") is not True
        or harness.get("automatic_resampling") != 0
        or harness.get("allowed_tools") != list(ALLOWED_TOOLS)
        or harness.get("denied_capabilities") != list(DENIED_CAPABILITIES)
    ):
        raise ValueError("Codex harness contract changed")

    expected_budget = {
        "max_input_tokens_per_turn": MAX_INPUT_TOKENS_PER_TURN,
        "max_output_tokens_per_turn": MAX_OUTPUT_TOKENS_PER_TURN,
        "max_cumulative_input_tokens": MAX_CUMULATIVE_INPUT_TOKENS,
        "max_cumulative_output_tokens": MAX_CUMULATIVE_OUTPUT_TOKENS,
        "max_context_tokens": MAX_CONTEXT_TOKENS,
        "terminal_submission_output_reserve": TERMINAL_SUBMISSION_OUTPUT_RESERVE,
        "terminal_submission_trigger_output": TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
        "terminal_submission_max_output": TERMINAL_SUBMISSION_MAX_OUTPUT,
        "terminal_submission_tool_reserve": TERMINAL_SUBMISSION_TOOL_RESERVE,
        "max_turns": MAX_TURNS,
        "max_tool_calls": MAX_TOOL_CALLS,
        "max_candidate_executions": MAX_CANDIDATE_EXECUTIONS,
        "max_wall_seconds": MAX_WALL_SECONDS,
        "worst_case_controller_usd": str(
            _usd(MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS)
        ),
        "accounting": "sum_actual_tokens_across_all_harness_turns",
    }
    if contract["research_budget"] != expected_budget:
        raise ValueError("64K research envelope or accounting changed")
    if MAX_INPUT_TOKENS_PER_TURN + MAX_OUTPUT_TOKENS_PER_TURN > MAX_CONTEXT_TOKENS:
        raise ValueError("declared input/output cannot fit the model context")
    if not (
        0 < TERMINAL_SUBMISSION_MAX_OUTPUT
        <= TERMINAL_SUBMISSION_OUTPUT_RESERVE
        <= TERMINAL_SUBMISSION_TRIGGER_OUTPUT
        < MAX_CUMULATIVE_OUTPUT_TOKENS
        and 0 < TERMINAL_SUBMISSION_TOOL_RESERVE < MAX_TOOL_CALLS
    ):
        raise ValueError("invalid terminal submission reserve")

    decision = contract["decision_envelope"]
    if (
        decision.get("max_bytes") != MAX_FINAL_DECISION_BYTES
        or decision.get("long_notebook_is_separate") is not True
        or decision.get("required_fields") != [
            "action",
            "question",
            "hypothesis",
            "evidence",
            "candidate_artifact",
            "expected_failure_condition",
        ]
    ):
        raise ValueError("final decision envelope changed")

    evidence = contract["evidence_policy"]
    commitment = evidence.get("opaque_test_commitment")
    try:
        objective = validate_objective_contract(
            evidence.get("objective_contract"),
            experiment_id=contract["experiment_id"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("frozen objective contract changed") from error
    if (
        objective["selection"]["selected_before_dev_schedule"] is not True
        or evidence.get("controller_may_change_objective") is not False
        or evidence.get("visible_splits") != ["train", "dev"]
        or evidence.get("controller_learning_access")
        != "all_train_and_consumed_dev_with_labels"
        or evidence.get("current_dev_access")
        != "features_only_until_final_candidate_is_frozen"
        or evidence.get("controller_visible_candidate_scores")
        != "reusable_train_cv_only"
        or evidence.get("sealed_dev_execution")
        != "runner_once_after_controller_session_exits"
        or evidence.get("sealed_dev_score_visibility")
        != "next_round_archive_only"
        or evidence.get("dev_after_score")
        != "atomically_promote_to_next_round_train"
        or evidence.get("consumed_dev_evaluation_reuse") != "forbidden"
        or evidence.get("future_test")
        != "opaque_until_all_final_submissions_freeze"
        or evidence.get("data_lifecycle_schema")
        != prospective_data_lifecycle.SCHEMA
        or evidence.get("data_lifecycle_source_sha256")
        != file_hash(prospective_data_lifecycle.__file__)
        or evidence.get("time_series_validation") != policy_contract()
        or evidence.get("time_series_research_harness")
        != time_series_harness_contract()
        or not isinstance(commitment, str)
        or len(commitment) != 64
        or any(ch not in "0123456789abcdef" for ch in commitment)
        or evidence.get("literature_search")
        != "public_results_snapshotted_with_query_url_time_and_hash"
        or evidence.get("candidate_execution") != "runner_owned_e2b_only"
        or evidence.get("scoring") != "fixed_runner_owned_common_rows"
    ):
        raise ValueError("evaluation isolation changed")
    return {
        "valid": True,
        "contract_sha256": digest(contract),
        "worst_case_controller_usd": expected_budget["worst_case_controller_usd"],
    }
