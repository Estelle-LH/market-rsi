"""Open-ended discovery followed by a frozen confirmation contract.

Discovery may change questions, representations, objectives and algorithms on
already-open evidence.  It has a budget and an append-only trace, but no
performance reward or promotion claim.  A selected discovery candidate becomes
testable only after its primary reward, baseline, evaluator and one-shot fresh
data policy are frozen.  Changes after results belong to the next cycle.
"""
from __future__ import annotations

from market_rsi import digest
from data_scientist_harness.co_evolution_loop import begin_experiment_batch
from data_scientist_harness.evaluation_evidence_contract import validate_evaluation_evidence_output


RESEARCH_TYPES = {
    "data_discovery",
    "descriptive_analysis",
    "prediction",
    "causal_question",
    "representation_learning",
    "decision_policy",
    "market_mechanism",
    "simulation",
    "algorithm_design",
    "evaluation_method",
    "research_tooling",
}


def _sha(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} must be a lowercase SHA256")


def _seal(value: dict) -> dict:
    result = dict(value)
    result["record_sha256"] = digest(result)
    return result


def _verify(value: dict) -> None:
    _sha(value.get("record_sha256", ""), "record_sha256")
    if digest({key: item for key, item in value.items() if key != "record_sha256"}) != value["record_sha256"]:
        raise ValueError("research-cycle record was modified")


def begin_discovery(release: dict, plan: dict) -> dict:
    release_fields = {
        "harness_version", "release_sha256", "commit", "tag", "published", "canary_sha256"
    }
    plan_fields = {
        "discovery_id", "broad_problem", "allowed_research_types", "accessible_data_roles",
        "maximum_iterations", "maximum_cost_usd", "required_outputs", "primary_reward",
        "formal_claims_allowed", "route_dev_access", "sealed_final_access",
    }
    if set(release) != release_fields or set(plan) != plan_fields:
        raise ValueError("exact release and discovery schemas required")
    for key in ("release_sha256", "canary_sha256"):
        _sha(release[key], key)
    if release["published"] is not True:
        raise ValueError("discovery requires a published Harness")
    if not plan["discovery_id"] or not plan["broad_problem"]:
        raise ValueError("discovery id and broad problem are required")
    if not set(plan["allowed_research_types"]).issubset(RESEARCH_TYPES) or not plan["allowed_research_types"]:
        raise ValueError("discovery requires known open research types")
    allowed_roles = {"opened_train", "public_literature", "frozen_archive", "synthetic_canary"}
    if not set(plan["accessible_data_roles"]).issubset(allowed_roles):
        raise ValueError("discovery cannot access fresh evaluation data")
    if type(plan["maximum_iterations"]) is not int or plan["maximum_iterations"] <= 0:
        raise ValueError("positive discovery iteration bound required")
    if plan["maximum_cost_usd"] < 0:
        raise ValueError("negative discovery budget")
    if not plan["required_outputs"]:
        raise ValueError("discovery outputs must be explicit")
    if plan["primary_reward"] is not None:
        raise ValueError("open discovery must not optimize a frozen performance reward")
    if plan["formal_claims_allowed"] is not False:
        raise ValueError("discovery cannot make formal improvement claims")
    if plan["route_dev_access"] is not False or plan["sealed_final_access"] is not False:
        raise ValueError("discovery cannot access Route-Dev or Final")
    return _seal({
        "schema": "open_discovery_session_v1",
        "state": "discovery_running",
        "release": release,
        "plan": plan,
        "questions_may_change": True,
        "targets_may_change_on_opened_data": True,
        "horizons_may_change_on_opened_data": True,
        "algorithms_may_be_invented": True,
        "opened_data_becomes_nonfresh": True,
        "confirmation_allowed": False,
    })


def complete_discovery(session: dict, result: dict) -> dict:
    _verify(session)
    if session.get("state") != "discovery_running":
        raise ValueError("only a running discovery can complete")
    fields = {
        "discovery_id", "trace_sha256", "opened_data_hashes", "literature_record_ids",
        "candidate_graphs", "iterations_completed", "cost_usd", "route_dev_opened",
        "sealed_final_opened", "terminal_cleanup_passed",
    }
    if set(result) != fields or result["discovery_id"] != session["plan"]["discovery_id"]:
        raise ValueError("exact matching discovery result required")
    _sha(result["trace_sha256"], "trace_sha256")
    if not isinstance(result["opened_data_hashes"], dict) or not result["opened_data_hashes"]:
        raise ValueError("discovery needs an immutable opened-data inventory")
    for value in result["opened_data_hashes"].values():
        _sha(value, "opened data hash")
    if not result["candidate_graphs"]:
        raise ValueError("discovery must preserve at least one candidate research graph")
    candidate_ids = set()
    for graph in result["candidate_graphs"]:
        required = {
            "candidate_id", "research_type", "question", "method", "evidence_refs",
            "evaluation_idea", "previously_untried_in_project",
        }
        if set(graph) != required:
            raise ValueError("candidate research graph must use the exact schema")
        if graph["candidate_id"] in candidate_ids:
            raise ValueError("duplicate discovery candidate")
        candidate_ids.add(graph["candidate_id"])
        if graph["research_type"] not in RESEARCH_TYPES:
            raise ValueError("unknown research type")
        if not all(graph[key] for key in ("question", "method", "evidence_refs", "evaluation_idea")):
            raise ValueError("candidate question, method, evidence and evaluation are required")
    if not 0 <= result["iterations_completed"] <= session["plan"]["maximum_iterations"]:
        raise ValueError("discovery iteration bound exceeded")
    if not 0 <= result["cost_usd"] <= session["plan"]["maximum_cost_usd"]:
        raise ValueError("discovery budget exceeded")
    if result["route_dev_opened"] or result["sealed_final_opened"]:
        raise ValueError("fresh evaluation exposure invalidates discovery")
    if result["terminal_cleanup_passed"] is not True:
        raise ValueError("terminal cleanup required")
    return _seal({
        "schema": "open_discovery_completion_v1",
        "state": "confirmation_design",
        "parent_discovery_sha256": session["record_sha256"],
        "release": session["release"],
        "plan": session["plan"],
        "result": result,
        "confirmation_allowed": False,
    })


def freeze_confirmation(discovery: dict, contract: dict) -> dict:
    _verify(discovery)
    if discovery.get("state") != "confirmation_design":
        raise ValueError("confirmation can only follow completed discovery")
    fields = {
        "confirmation_id", "selected_candidate_id", "research_question", "claim_type",
        "baseline_id", "primary_metric", "reward_direction", "target_spec_sha256",
        "evaluator_spec_sha256",
        "eligible_data_sha256", "untouched_data_role", "secondary_metrics", "constraints",
        "disqualifiers", "maximum_cost_usd", "maximum_evaluation_uses",
        "reward_locked_before_results", "reward_change_after_results_allowed",
        "evaluation_evidence_output",
    }
    if set(contract) != fields:
        raise ValueError("confirmation reward contract must use the exact schema")
    candidates = {item["candidate_id"] for item in discovery["result"]["candidate_graphs"]}
    if contract["selected_candidate_id"] not in candidates:
        raise ValueError("confirmation must select a discovery candidate")
    if not all(contract[key] for key in (
        "confirmation_id", "research_question", "claim_type", "baseline_id", "primary_metric",
        "untouched_data_role", "constraints", "disqualifiers"
    )):
        raise ValueError("confirmation question, reward, baseline and gates are required")
    if contract["reward_direction"] not in {"minimize", "maximize", "two_sided_test"}:
        raise ValueError("explicit reward direction required")
    _sha(contract["target_spec_sha256"], "target_spec_sha256")
    _sha(contract["evaluator_spec_sha256"], "evaluator_spec_sha256")
    _sha(contract["eligible_data_sha256"], "eligible_data_sha256")
    if contract["eligible_data_sha256"] in discovery["result"]["opened_data_hashes"].values():
        raise ValueError("confirmation data was already opened in discovery")
    if contract["untouched_data_role"] not in {"route_dev_one_shot", "future_holdout"}:
        raise ValueError("confirmation requires untouched data")
    if contract["maximum_cost_usd"] < 0 or contract["maximum_evaluation_uses"] != 1:
        raise ValueError("confirmation has a nonnegative budget and one evaluation use")
    if contract["reward_locked_before_results"] is not True:
        raise ValueError("confirmation reward must be locked before results")
    if contract["reward_change_after_results_allowed"] is not False:
        raise ValueError("reward changes belong to the next research cycle")
    validate_evaluation_evidence_output(contract["evaluation_evidence_output"])
    return _seal({
        "schema": "frozen_confirmation_contract_v1",
        "state": "confirmation_frozen",
        "parent_discovery_completion_sha256": discovery["record_sha256"],
        "release": discovery["release"],
        "contract": contract,
        "confirmation_allowed": True,
    })


def begin_confirmation(frozen: dict, claim: dict) -> dict:
    _verify(frozen)
    if frozen.get("state") != "confirmation_frozen" or frozen["confirmation_allowed"] is not True:
        raise ValueError("confirmation requires a frozen reward contract")
    if claim.get("pre_score_lock_sha256") != frozen["record_sha256"]:
        raise ValueError("experiment claim is not bound to the frozen confirmation reward")
    return begin_experiment_batch(frozen["release"], claim)
