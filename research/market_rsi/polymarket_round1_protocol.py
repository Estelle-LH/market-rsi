"""Fail-closed protocol gate for the first Reset/Archive/Learn comparison.

This module is deliberately local and provider-free.  It fixes the experimental
shape before a :class:`StudyRunner` is allowed to dispatch work, and can bind
that declaration to a created StudyState/StudyRunner/budget.  It does not admit
market data, open Test, call a model, execute candidate code, or authorize spend.
"""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
from pathlib import Path

from glm_canary import RATES, cost
from market_rsi import digest, file_hash, identifier
from researcher_worker import CONTROLLER_REASONING_EFFORT, CONTROLLER_TEMPERATURE


SCHEMA = "polymarket_round1_protocol_v2"
ARMS = ("reset", "archive", "learn")
PHASES = ("learning",) * 6 + ("transfer",) * 3
CAUSAL_STAGES = ("data", "signal", "predictor", "objective", "trading_policy")
SOURCE_BOUNDARY_UTC = "2026-09-07T16:08:41Z"

MEMORY_POLICY = {
    "reset": {
        "current_task_records": "complete_own_experiment_record_with_runner_artifact_commitments",
        "prior_learning_records": "none",
        "prior_transfer_records": "none",
        "guide": "none",
    },
    "archive": {
        "current_task_records": "complete_own_experiment_record_with_runner_artifact_commitments",
        "prior_learning_records": "complete_own_experiment_record_with_runner_artifact_commitments",
        "prior_transfer_records": "none",
        "guide": "none",
    },
    "learn": {
        "current_task_records": "complete_own_experiment_record_with_runner_artifact_commitments",
        "prior_learning_records": "complete_own_experiment_record_with_runner_artifact_commitments",
        "prior_transfer_records": "none",
        "guide": "latest_agent_revision_with_owned_evidence",
    },
}


def _money(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not money")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("nonnegative finite dollar amount required") from None
    if not result.is_finite() or result < 0:
        raise ValueError("nonnegative finite dollar amount required")
    return result


def _positive_int(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"positive integer required for {name}")
    return value


def _sha256(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError("opaque SHA-256 commitment required")
    return value


def _exact_dict(value, keys, message):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(message)
    return value


def _budget_upper(*, limits, proposal_calls, selection_calls,
                  sandbox_upper_per_proposal_usd, fixed_setup_upper_usd,
                  other_metered_upper_usd):
    model_call = cost(limits["max_input_tokens"], limits["max_output_tokens"])
    return (model_call * (proposal_calls + selection_calls)
            + _money(sandbox_upper_per_proposal_usd) * proposal_calls
            + _money(fixed_setup_upper_usd)
            + _money(other_metered_upper_usd))


def build_protocol(*, experiment_id, task_ids, opaque_test_commitment,
                   resource_limits=None, pilot_cap_usd="50",
                   sandbox_upper_per_proposal_usd="0.10",
                   fixed_setup_upper_usd="0.50",
                   other_metered_upper_usd="0"):
    """Create the only accepted Round-1 declaration.

    ``task_ids`` are public opaque task handles, not game IDs, filenames or
    Test identifiers.  The default limits are deliberately conservative enough
    for the complete owned history while retaining a hard price upper bound.
    """
    identifier(experiment_id)
    if not isinstance(task_ids, list) or len(task_ids) != len(PHASES):
        raise ValueError("exactly nine ordered public task handles required")
    for task_id in task_ids:
        identifier(task_id)
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("task handles must be unique")
    _sha256(opaque_test_commitment)
    limits = copy.deepcopy(resource_limits or {
        "max_input_tokens": 48000,
        "max_output_tokens": 4096,
        "max_wall_seconds": 300,
    })
    _exact_dict(limits, {"max_input_tokens", "max_output_tokens", "max_wall_seconds"},
                "exact common researcher limits required")
    for key, value in limits.items():
        _positive_int(value, key)

    tasks = [{"task_id": task_id, "task_index": index, "phase": phase}
             for index, (task_id, phase) in enumerate(zip(task_ids, PHASES))]
    candidate_calls = len(ARMS) * len(tasks) * 2
    diagnostic_calls = len(ARMS) * len(tasks)
    failed_or_replacement_calls = len(ARMS) * len(tasks)
    proposal_calls = candidate_calls + diagnostic_calls + failed_or_replacement_calls
    selection_calls = len(ARMS) * len(tasks)
    total = _budget_upper(limits=limits, proposal_calls=proposal_calls,
        selection_calls=selection_calls,
        sandbox_upper_per_proposal_usd=sandbox_upper_per_proposal_usd,
        fixed_setup_upper_usd=fixed_setup_upper_usd,
        other_metered_upper_usd=other_metered_upper_usd)
    protocol = {
        "schema": SCHEMA,
        "validator_source_sha256": file_hash(__file__),
        "protocol_id": experiment_id + "-round1",
        "experiment_id": experiment_id,
        "exchange": {"name": "polymarket_us", "role": "data_source_only"},
        "roles": {
            "trusted_runner": "fixed_code_schedules_dispatches_and_verifies",
            "researcher": "glm_5_3_selects_one_research_change",
            "coder": "codex_implements_declared_change_only",
            "executor": "harbor_e2b_runs_isolated_candidate",
            "scorer": "fixed_code_scores_common_rows",
        },
        "arms": list(ARMS),
        "tasks": tasks,
        "arm_task_order": {arm: list(task_ids) for arm in ARMS},
        "schedule": {
            "learning_tasks": 6,
            "transfer_tasks": 3,
            "max_candidate_proposals_per_task": 2,
            "max_diagnostics_per_task": 1,
            "max_research_calls_per_task": 4,
            "selection_calls_per_task": 1,
            "maximum_candidate_executions": candidate_calls,
            "maximum_diagnostic_executions": diagnostic_calls,
            "maximum_failed_or_replacement_calls": failed_or_replacement_calls,
        },
        "resource_limits": limits,
        "memory_policy": copy.deepcopy(MEMORY_POLICY),
        "response_policy": {
            "samples_per_claim": 1,
            "automatic_retries": 0,
            "invalid_or_timeout_is_outcome": True,
            "selection_fallback": "common_baseline",
            "concise_json_contract": True,
            "omitted_guide_update": "normalize_to_null",
            "guide_evidence": "independently_scored_experiments_only",
            "candidate_slot_rule": "independently_scored_experiments_only",
            "failure_rule": "consumes_total_call_not_candidate_slot",
            "reasoning_effort": CONTROLLER_REASONING_EFFORT,
            "temperature": CONTROLLER_TEMPERATURE,
        },
        "causal_policy": {
            "changed_stages_per_proposal": 1,
            "allowed_stages": list(CAUSAL_STAGES),
            "external_target_frozen": True,
            "eligible_row_mask_common_within_task": True,
        },
        "visibility_policy": {
            "model_visible_splits": ["train", "dev"],
            "test_representation": "opaque_sha256_only",
            "opaque_test_commitment": opaque_test_commitment,
            "test_open_after": "all_transfer_submissions_frozen",
            "test_open_count": 1,
            "minimum_test_unique_complete_game_ids": 20,
            "prospective_source_boundary_utc": SOURCE_BOUNDARY_UTC,
            "cross_arm_records_visible": False,
        },
        "dispatch_policy": {
            "authority": "study_runner.StudyRunner.tick",
            "single_global_active_claim": True,
            "maximum_concurrent_paid_dispatches": 1,
            "subagents_may_dispatch": False,
            "researcher_tools": [],
            "coder_can_choose_research_direction": False,
            "host_can_select_candidate": False,
        },
        "budget": {
            "pilot_cap_usd": str(_money(pilot_cap_usd)),
            "proposal_model_calls": proposal_calls,
            "selection_model_calls": selection_calls,
            "sandbox_upper_per_proposal_usd": str(_money(sandbox_upper_per_proposal_usd)),
            "fixed_setup_upper_usd": str(_money(fixed_setup_upper_usd)),
            "other_metered_upper_usd": str(_money(other_metered_upper_usd)),
            "model_rates": copy.deepcopy(RATES),
            "total_metered_upper_usd": str(total),
            "codex_subscription_usage": "record_separately_cost_allocation_unknown",
        },
    }
    validate_protocol(protocol)
    return protocol


def validate_protocol(protocol):
    """Validate an immutable Round-1 declaration and return its digest."""
    keys = {"schema", "validator_source_sha256", "protocol_id", "experiment_id",
            "exchange", "roles", "arms", "tasks",
            "arm_task_order", "schedule", "resource_limits", "memory_policy",
            "response_policy", "causal_policy", "visibility_policy", "dispatch_policy",
            "budget"}
    _exact_dict(protocol, keys, "unexpected Round-1 protocol fields")
    if protocol["schema"] != SCHEMA:
        raise ValueError("wrong Round-1 protocol schema")
    if protocol["validator_source_sha256"] != file_hash(__file__):
        raise ValueError("Round-1 validator source changed")
    identifier(protocol["experiment_id"])
    identifier(protocol["protocol_id"])
    if protocol["protocol_id"] != protocol["experiment_id"] + "-round1":
        raise ValueError("protocol identity is not bound to experiment")
    if protocol["exchange"] != {"name": "polymarket_us", "role": "data_source_only"}:
        raise ValueError("exchange must remain a non-causal data-source choice")
    if protocol["roles"] != {
            "trusted_runner": "fixed_code_schedules_dispatches_and_verifies",
            "researcher": "glm_5_3_selects_one_research_change",
            "coder": "codex_implements_declared_change_only",
            "executor": "harbor_e2b_runs_isolated_candidate",
            "scorer": "fixed_code_scores_common_rows"}:
        raise ValueError("runner/researcher/coder/executor/scorer responsibilities changed")
    if protocol["arms"] != list(ARMS):
        raise ValueError("exact Reset/Archive/Learn arms and order required")

    tasks = protocol["tasks"]
    if not isinstance(tasks, list) or len(tasks) != len(PHASES):
        raise ValueError("Round 1 requires six learning and three transfer tasks")
    task_ids = []
    for index, (task, phase) in enumerate(zip(tasks, PHASES)):
        _exact_dict(task, {"task_id", "task_index", "phase"}, "unexpected task fields")
        identifier(task["task_id"])
        if task["task_index"] != index or task["phase"] != phase:
            raise ValueError("task order must be six learning then three transfer")
        task_ids.append(task["task_id"])
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("Round-1 task handles must be unique")
    if (not isinstance(protocol["arm_task_order"], dict)
            or set(protocol["arm_task_order"]) != set(ARMS)
            or any(protocol["arm_task_order"][arm] != task_ids for arm in ARMS)):
        raise ValueError("all arms must use the exact same task order")

    expected_schedule = {"learning_tasks": 6, "transfer_tasks": 3,
        "max_candidate_proposals_per_task": 2, "max_diagnostics_per_task": 1,
        "max_research_calls_per_task": 4, "selection_calls_per_task": 1,
        "maximum_candidate_executions": 54, "maximum_diagnostic_executions": 27,
        "maximum_failed_or_replacement_calls": 27}
    if protocol["schedule"] != expected_schedule:
        raise ValueError("Round-1 6+3, two-candidate plus separate-diagnostic schedule changed")
    limits = _exact_dict(protocol["resource_limits"],
        {"max_input_tokens", "max_output_tokens", "max_wall_seconds"},
        "exact common researcher limits required")
    for key, value in limits.items():
        _positive_int(value, key)
    if protocol["memory_policy"] != MEMORY_POLICY:
        raise ValueError("arm memory contrast changed")
    if protocol["response_policy"] != {"samples_per_claim": 1, "automatic_retries": 0,
            "invalid_or_timeout_is_outcome": True, "selection_fallback": "common_baseline",
            "concise_json_contract": True,
            "omitted_guide_update": "normalize_to_null",
            "guide_evidence": "independently_scored_experiments_only",
            "candidate_slot_rule": "independently_scored_experiments_only",
            "failure_rule": "consumes_total_call_not_candidate_slot",
            "reasoning_effort": CONTROLLER_REASONING_EFFORT,
            "temperature": CONTROLLER_TEMPERATURE}:
        raise ValueError("single-response/no-resample policy changed")
    if protocol["causal_policy"] != {"changed_stages_per_proposal": 1,
            "allowed_stages": list(CAUSAL_STAGES), "external_target_frozen": True,
            "eligible_row_mask_common_within_task": True}:
        raise ValueError("one-stage causal comparison policy changed")

    visibility = protocol["visibility_policy"]
    _exact_dict(visibility, {"model_visible_splits", "test_representation",
        "opaque_test_commitment", "test_open_after", "test_open_count",
        "minimum_test_unique_complete_game_ids", "prospective_source_boundary_utc",
        "cross_arm_records_visible"}, "unexpected visibility fields")
    if (visibility["model_visible_splits"] != ["train", "dev"]
            or visibility["test_representation"] != "opaque_sha256_only"
            or visibility["test_open_after"] != "all_transfer_submissions_frozen"
            or visibility["test_open_count"] != 1
            or visibility["minimum_test_unique_complete_game_ids"] != 20
            or visibility["prospective_source_boundary_utc"] != SOURCE_BOUNDARY_UTC
            or visibility["cross_arm_records_visible"] is not False):
        raise ValueError("Test or arm isolation weakened")
    _sha256(visibility["opaque_test_commitment"])
    if protocol["dispatch_policy"] != {"authority": "study_runner.StudyRunner.tick",
            "single_global_active_claim": True, "maximum_concurrent_paid_dispatches": 1,
            "subagents_may_dispatch": False, "researcher_tools": [],
            "coder_can_choose_research_direction": False,
            "host_can_select_candidate": False}:
        raise ValueError("only the trusted runner may schedule or dispatch")

    budget = protocol["budget"]
    _exact_dict(budget, {"pilot_cap_usd", "proposal_model_calls", "selection_model_calls",
        "sandbox_upper_per_proposal_usd", "fixed_setup_upper_usd",
        "other_metered_upper_usd", "model_rates", "total_metered_upper_usd",
        "codex_subscription_usage"}, "unexpected budget fields")
    if (budget["proposal_model_calls"] != 108 or budget["selection_model_calls"] != 27
            or budget["model_rates"] != RATES
            or budget["codex_subscription_usage"] !=
               "record_separately_cost_allocation_unknown"):
        raise ValueError("complete Round-1 call/cost accounting required")
    total = _budget_upper(limits=limits, proposal_calls=108, selection_calls=27,
        sandbox_upper_per_proposal_usd=budget["sandbox_upper_per_proposal_usd"],
        fixed_setup_upper_usd=budget["fixed_setup_upper_usd"],
        other_metered_upper_usd=budget["other_metered_upper_usd"])
    if _money(budget["total_metered_upper_usd"]) != total:
        raise ValueError("declared total upper does not match frozen worst case")
    if total > _money(budget["pilot_cap_usd"]) or _money(budget["pilot_cap_usd"]) > Decimal("50"):
        raise ValueError("Round-1 worst case exceeds the $50 pilot cap")
    return {"schema": SCHEMA, "protocol_sha256": digest(protocol),
            "total_metered_upper_usd": str(total), "valid": True}


def validate_study_binding(protocol, study_manifest, runner_config, budget_snapshot):
    """Bind a validated declaration to created, still-closed live artifacts.

    This check is necessary but not sufficient for scientific admission: source,
    labels, split receipts, scorer and deadline evidence remain separate gates.
    """
    result = validate_protocol(protocol)
    task_ids = [task["task_id"] for task in protocol["tasks"]]
    if (study_manifest.get("experiment_id") != protocol["experiment_id"]
            or set(study_manifest.get("arms", [])) != set(ARMS)
            or study_manifest.get("max_steps_per_task") != 2
            or study_manifest.get("max_diagnostics_per_task") != 1
            or study_manifest.get("max_research_calls_per_task") != 4
            or study_manifest.get("selection_policy") != {
                "after_scoreable_candidates": 2, "max_diagnostic_attempts": 1,
                "max_research_calls": 4,
                "selection_trigger": "target_scoreable_candidates_or_call_cap",
                "calls_per_task": 1,
                "invalid_output": "common_baseline", "guide_update": False}):
        raise ValueError("StudyState does not implement the Round-1 schedule")
    manifest_tasks = study_manifest.get("tasks")
    if not isinstance(manifest_tasks, list) or len(manifest_tasks) != 9:
        raise ValueError("StudyState task count changed")
    for declared, actual in zip(protocol["tasks"], manifest_tasks):
        if (actual.get("task_id") != declared["task_id"]
                or actual.get("task_index") != declared["task_index"]
                or actual.get("phase") != declared["phase"]
                or actual.get("resource_limits") != protocol["resource_limits"]
                or actual.get("opaque_test_commitment") !=
                   protocol["visibility_policy"]["opaque_test_commitment"]
                or {item.get("split") for item in actual.get("data_catalog", [])} != {"train", "dev"}):
            raise ValueError("StudyState task/order/resource/Test binding changed")
    if [task["task_id"] for task in manifest_tasks] != task_ids:
        raise ValueError("StudyState task order changed")

    source_hashes = runner_config.get("source_hashes", {})
    owned_sources = ("study_runner.py", "study_state.py", "researcher_worker.py",
                     "selection_protocol.py")
    if (runner_config.get("schema") != "market_study_runner_v1"
            or runner_config.get("experiment_id") != protocol["experiment_id"]
            or runner_config.get("study_manifest_sha256") != digest(study_manifest)
            or runner_config.get("live") is not True
            or runner_config.get("scientific_admission") is not False
            or any(source_hashes.get(name) != file_hash(Path(__file__).with_name(name))
                   for name in owned_sources)):
        raise ValueError("live trusted-runner binding is absent or already mutated")
    task_data = runner_config.get("task_data")
    if not isinstance(task_data, dict) or set(task_data) != set(task_ids):
        raise ValueError("runner does not own the exact shared task data")
    for entry in task_data.values():
        if (not isinstance(entry, dict)
                or set(entry) != {"train_id", "train_path", "dev_id", "dev_path"}):
            raise ValueError("runner task data exposes more than Train/Dev")

    if (budget_snapshot.get("experiment_id") != protocol["experiment_id"]
            or _money(budget_snapshot.get("cap_usd")) !=
               _money(protocol["budget"]["pilot_cap_usd"])
            or _money(budget_snapshot.get("effective_cost_usd")) != 0
            or _money(budget_snapshot.get("reserved_usd")) != 0):
        raise ValueError("fresh exact $50 pilot ledger required before Round 1")
    return dict(result, study_manifest_sha256=digest(study_manifest),
                runner_config_sha256=digest(runner_config), bound=True,
                scientific_admission=False)
