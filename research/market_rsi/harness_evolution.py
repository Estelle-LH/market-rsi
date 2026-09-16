"""Bounded, auditable self-editing surface for the research harness.

The outer kernel remains human-reviewed and immutable during an experiment.
An AI may write a new *inner harness profile* that changes research guidance,
Archive retrieval policy and tool guidance.  The profile cannot add tools,
change data access, scoring, budgets, execution isolation or the active session.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json


HERE = Path(__file__).resolve().parent
SCHEMA = "market_evolvable_harness_profile_v1"
EVALUATION_SCHEMA = "market_harness_profile_evaluation_v1"
ZERO_HASH = "0" * 64
MAX_GUIDANCE_CHARS = 32_768
MAX_WORKFLOW_STEPS = 32
MAX_STEP_CHARS = 1_000
MAX_TOOL_GUIDANCE_CHARS = 2_000
MAX_TOOL_PROPOSALS = 8
PROPOSABLE_TOOL_CAPABILITIES = frozenset({
    "read_learning_data",
    "read_archive",
    "search_public_literature",
    "write_inner_workspace",
    "request_runner_candidate_execution",
    "read_aggregate_dev_result",
})

# These files define the authority boundary.  A profile may refer to their
# commitment, but it cannot replace any of them.
KERNEL_FILES = (
    "controller_candidate_harbor.py",
    "controller_execution_service.py",
    "controller_harness_contract.py",
    "controller_tools_mcp.py",
    "controller_workspace.py",
    "data_lifecycle.py",
    "market_scoring.py",
    "paid_budget.py",
    "polymarket_scoring.py",
)


def kernel_manifest() -> dict:
    sources = {}
    for name in KERNEL_FILES:
        path = HERE / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("harness kernel source missing or symlinked")
        sources[name] = file_hash(path)
    return {"schema": "market_harness_kernel_v1", "sources": sources}


def kernel_sha256() -> str:
    return digest(kernel_manifest())


def baseline_profile(allowed_tools: tuple[str, ...] | list[str]) -> dict:
    tools = list(allowed_tools)
    if not tools or len(set(tools)) != len(tools):
        raise ValueError("fixed distinct tool names required")
    profile = {
        "schema": SCHEMA,
        "generation": 0,
        "parent_profile_sha256": ZERO_HASH,
        "kernel_sha256": kernel_sha256(),
        "research_guidance": (
            "Use the complete accessible Archive, inspect evidence, form a falsifiable "
            "hypothesis, run independently verified candidates, preserve failures, and "
            "choose the next action yourself."
        ),
        "workflow_suggestions": [
            "Inspect the available Train data and the current label-free Dev features.",
            "Read relevant prior executions, including failures and costs.",
            "Search literature or inspect algorithms when it helps the current question.",
            "Write and execute immutable candidates, then submit one evidence-linked decision.",
        ],
        "archive_policy": {
            "complete_history_retrievable": True,
            "raw_records_retrievable": True,
            "include_failures": True,
            "include_costs": True,
            "controller_chooses_relevance": True,
            "controller_may_ignore_workflow": True,
        },
        "tool_guidance": {
            name: "Use this tool only when it helps the current research decision; every call is logged."
            for name in tools
        },
        "tool_proposals": [],
        "change_hypothesis": "Human-written baseline inner harness profile.",
        "authority_boundary": {
            "may_change_current_session": False,
            "candidate_applies_next_session_only": True,
            "may_propose_new_tools": True,
            "may_activate_unadmitted_tools": False,
            "may_remove_kernel_tools": False,
            "may_change_kernel": False,
            "may_change_data_lifecycle": False,
            "may_change_scorer": False,
            "may_open_sealed_labels": False,
            "may_change_budget": False,
            "automatic_retry": 0,
        },
    }
    validate_profile(profile, allowed_tools=tools)
    return profile


def _text(value, *, maximum: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"bounded nonempty {field} required")
    return value


def validate_profile(profile: dict, *, allowed_tools: tuple[str, ...] | list[str]) -> dict:
    tools = list(allowed_tools)
    if not isinstance(profile, dict) or set(profile) != {
        "schema", "generation", "parent_profile_sha256", "kernel_sha256",
        "research_guidance", "workflow_suggestions", "archive_policy", "tool_guidance",
        "tool_proposals", "change_hypothesis", "authority_boundary",
    }:
        raise ValueError("unexpected evolvable harness profile fields")
    if profile["schema"] != SCHEMA:
        raise ValueError("wrong evolvable harness profile schema")
    generation = profile["generation"]
    if type(generation) is not int or generation < 0:
        raise ValueError("nonnegative harness generation required")
    parent = profile["parent_profile_sha256"]
    if (
        not isinstance(parent, str)
        or len(parent) != 64
        or any(ch not in "0123456789abcdef" for ch in parent)
        or (generation == 0) != (parent == ZERO_HASH)
    ):
        raise ValueError("harness parent commitment does not match generation")
    if profile["kernel_sha256"] != kernel_sha256():
        raise ValueError("AI harness profile cannot change the frozen kernel")
    _text(profile["research_guidance"], maximum=MAX_GUIDANCE_CHARS,
          field="research guidance")
    _text(profile["change_hypothesis"], maximum=4_000, field="change hypothesis")
    workflow = profile["workflow_suggestions"]
    if (
        not isinstance(workflow, list)
        or not 1 <= len(workflow) <= MAX_WORKFLOW_STEPS
        or any(not isinstance(step, str) or not step.strip() or len(step) > MAX_STEP_CHARS
               for step in workflow)
    ):
        raise ValueError("bounded workflow suggestions required")
    if profile["archive_policy"] != {
        "complete_history_retrievable": True,
        "raw_records_retrievable": True,
        "include_failures": True,
        "include_costs": True,
        "controller_chooses_relevance": True,
        "controller_may_ignore_workflow": True,
    }:
        raise ValueError("AI harness cannot hide Archive evidence or force a workflow")
    guidance = profile["tool_guidance"]
    if (
        not isinstance(guidance, dict)
        or set(guidance) != set(tools)
        or len(guidance) != len(tools)
        or any(not isinstance(value, str) or not value.strip()
               or len(value) > MAX_TOOL_GUIDANCE_CHARS for value in guidance.values())
    ):
        raise ValueError("tool guidance must preserve the exact frozen tool surface")
    proposals = profile["tool_proposals"]
    if not isinstance(proposals, list) or len(proposals) > MAX_TOOL_PROPOSALS:
        raise ValueError("bounded inner-tool proposals required")
    proposal_names = set()
    for proposal in proposals:
        if not isinstance(proposal, dict) or set(proposal) != {
            "tool_name", "description", "source_sha256", "input_schema_sha256",
            "test_receipt_sha256", "requested_capabilities",
        }:
            raise ValueError("unexpected inner-tool proposal fields")
        name = proposal["tool_name"]
        if (
            not isinstance(name, str) or not name
            or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in name)
            or name in tools or name in proposal_names
        ):
            raise ValueError("new inner tool requires a unique safe name")
        proposal_names.add(name)
        _text(proposal["description"], maximum=MAX_TOOL_GUIDANCE_CHARS,
              field="inner-tool description")
        for field in ("source_sha256", "input_schema_sha256", "test_receipt_sha256"):
            value = proposal[field]
            if (not isinstance(value, str) or len(value) != 64
                    or any(ch not in "0123456789abcdef" for ch in value)):
                raise ValueError("inner-tool artifacts require SHA-256 commitments")
        capabilities = proposal["requested_capabilities"]
        if (not isinstance(capabilities, list) or not capabilities
                or len(set(capabilities)) != len(capabilities)
                or not set(capabilities) <= PROPOSABLE_TOOL_CAPABILITIES):
            raise ValueError("inner tool requested a capability outside the outer kernel")
    if profile["authority_boundary"] != {
        "may_change_current_session": False,
        "candidate_applies_next_session_only": True,
        "may_propose_new_tools": True,
        "may_activate_unadmitted_tools": False,
        "may_remove_kernel_tools": False,
        "may_change_kernel": False,
        "may_change_data_lifecycle": False,
        "may_change_scorer": False,
        "may_open_sealed_labels": False,
        "may_change_budget": False,
        "automatic_retry": 0,
    }:
        raise ValueError("AI harness profile crossed the immutable authority boundary")
    return {
        "valid": True,
        "generation": generation,
        "profile_sha256": digest(profile),
        "kernel_sha256": profile["kernel_sha256"],
    }


def make_candidate(parent: dict, changes: dict, *, allowed_tools) -> dict:
    """Create an unadmitted next-generation profile from allowed data fields."""
    parent_receipt = validate_profile(parent, allowed_tools=allowed_tools)
    mutable = {"research_guidance", "workflow_suggestions", "archive_policy",
               "tool_guidance", "tool_proposals", "change_hypothesis"}
    if not isinstance(changes, dict) or not changes or not set(changes) <= mutable:
        raise ValueError("candidate may change only the inner harness profile")
    candidate = copy.deepcopy(parent)
    candidate.update(copy.deepcopy(changes))
    candidate["generation"] = parent["generation"] + 1
    candidate["parent_profile_sha256"] = parent_receipt["profile_sha256"]
    validate_profile(candidate, allowed_tools=allowed_tools)
    return candidate


def freeze_candidate(path: Path, candidate: dict, *, allowed_tools) -> dict:
    receipt = validate_profile(candidate, allowed_tools=allowed_tools)
    fresh_json(path, candidate)
    return receipt


def _metric(value, field: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value < minimum:
        raise ValueError(f"finite {field} required")
    return float(value)


def assess_evaluation(parent: dict, candidate: dict, evaluation: dict, *, allowed_tools) -> dict:
    """Verify comparable one-shot evidence; return eligibility, never mutate H0/H1."""
    parent_receipt = validate_profile(parent, allowed_tools=allowed_tools)
    candidate_receipt = validate_profile(candidate, allowed_tools=allowed_tools)
    if (
        candidate["generation"] != parent["generation"] + 1
        or candidate["parent_profile_sha256"] != parent_receipt["profile_sha256"]
    ):
        raise ValueError("candidate is not the exact next generation of parent")
    if not isinstance(evaluation, dict) or set(evaluation) != {
        "schema", "parent_profile_sha256", "candidate_profile_sha256",
        "same_controller", "same_tasks", "same_budget", "submissions_precommitted",
        "labels_opened_once", "protocol_violations", "parent_metrics", "candidate_metrics",
    }:
        raise ValueError("unexpected harness evaluation fields")
    if (
        evaluation["schema"] != EVALUATION_SCHEMA
        or evaluation["parent_profile_sha256"] != parent_receipt["profile_sha256"]
        or evaluation["candidate_profile_sha256"] != candidate_receipt["profile_sha256"]
        or any(evaluation[key] is not True for key in (
            "same_controller", "same_tasks", "same_budget", "submissions_precommitted",
            "labels_opened_once"))
        or type(evaluation["protocol_violations"]) is not int
        or evaluation["protocol_violations"] < 0
    ):
        raise ValueError("harness comparison is not isolated and comparable")
    metrics = {}
    for side in ("parent", "candidate"):
        value = evaluation[side + "_metrics"]
        if not isinstance(value, dict) or set(value) != {
            "primary_improvement", "valid_experiment_rate", "cost_per_valid_experiment"
        }:
            raise ValueError("unexpected harness metric fields")
        metrics[side] = {
            "primary_improvement": _metric(value["primary_improvement"],
                                            "primary improvement", minimum=-1e100),
            "valid_experiment_rate": _metric(value["valid_experiment_rate"],
                                              "valid experiment rate"),
            "cost_per_valid_experiment": _metric(value["cost_per_valid_experiment"],
                                                  "cost per valid experiment"),
        }
        if metrics[side]["valid_experiment_rate"] > 1:
            raise ValueError("valid experiment rate must be at most one")
    # This is a conservative pilot gate, not a claim of statistical significance.
    eligible = (
        evaluation["protocol_violations"] == 0
        and metrics["candidate"]["primary_improvement"]
            > metrics["parent"]["primary_improvement"]
        and metrics["candidate"]["valid_experiment_rate"]
            >= metrics["parent"]["valid_experiment_rate"]
        and metrics["candidate"]["cost_per_valid_experiment"]
            <= 1.10 * metrics["parent"]["cost_per_valid_experiment"]
    )
    return {
        "valid_comparison": True,
        "promotion_eligible_for_next_session": eligible,
        "automatic_promotion": False,
        "research_claim": False,
        "parent_profile_sha256": parent_receipt["profile_sha256"],
        "candidate_profile_sha256": candidate_receipt["profile_sha256"],
    }
