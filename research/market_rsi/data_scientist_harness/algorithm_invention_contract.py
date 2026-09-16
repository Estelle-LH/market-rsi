"""Contract for controller-authored algorithm designs beyond a fixed library.

The controller may propose a new mechanism, composition, or objective-specific
trainer.  A proposal is archived before implementation and cannot activate
arbitrary code.  Novelty is an exploration requirement, never a substitute for
same-row baselines, ablations, safety checks, or untouched evaluation.
"""
from __future__ import annotations

from market_rsi import digest


ALGORITHM_STAGES = {
    "representation_learning",
    "prediction",
    "training_algorithm",
    "decision_policy",
    "market_mechanism",
    "simulation_model",
    "evaluation_method",
}

TEXT = {"type": "string"}
TEXTS = {"type": "array", "items": TEXT}
SCHEMA = {
    "type": "object",
    "properties": {
        "proposal_id": TEXT,
        "parent_harness_version": TEXT,
        "evidence_refs": TEXTS,
        "research_record": TEXT,
        "problem": TEXT,
        "hypothesis": TEXT,
        "changed_stage": {"type": "string", "enum": sorted(ALGORITHM_STAGES)},
        "closest_methods": TEXTS,
        "source_findings": TEXTS,
        "transfer_limits": TEXTS,
        "novelty_level": {"type": "string", "enum": [
            "new_to_project", "new_composition", "new_mechanism", "new_formulation"
        ]},
        "previously_untried_in_project": {"type": "boolean"},
        "why_existing_library_is_insufficient": TEXT,
        "mechanism_delta": TEXT,
        "mathematical_spec": TEXT,
        "pseudocode": TEXT,
        "input_contract": TEXT,
        "target_contract": TEXT,
        "loss_and_regularization": TEXT,
        "fit_protocol": TEXT,
        "same_data_baselines": TEXTS,
        "ablations": TEXTS,
        "failure_modes": TEXTS,
        "synthetic_tests": TEXTS,
        "maximum_cpu_seconds": {"type": "integer"},
        "maximum_memory_mb": {"type": "integer"},
        "external_dependencies": TEXTS,
        "requests_sealed_data": {"type": "boolean"},
    },
    "required": [],
    "additionalProperties": False,
}


FIELDS = {
    "proposal_id",
    "parent_harness_version",
    "evidence_refs",
    "research_record",
    "problem",
    "hypothesis",
    "changed_stage",
    "closest_methods",
    "source_findings",
    "transfer_limits",
    "novelty_level",
    "previously_untried_in_project",
    "why_existing_library_is_insufficient",
    "mechanism_delta",
    "mathematical_spec",
    "pseudocode",
    "input_contract",
    "target_contract",
    "loss_and_regularization",
    "fit_protocol",
    "same_data_baselines",
    "ablations",
    "failure_modes",
    "synthetic_tests",
    "maximum_cpu_seconds",
    "maximum_memory_mb",
    "external_dependencies",
    "requests_sealed_data",
}

# Keep the served schema and the executable validator on one exact field set.
SCHEMA["required"] = sorted(FIELDS)


def validate_proposal(proposal: dict) -> None:
    if set(proposal) != FIELDS:
        raise ValueError("algorithm proposal must use the exact schema")
    text_fields = (
        "proposal_id", "parent_harness_version", "problem", "hypothesis",
        "mechanism_delta", "mathematical_spec", "pseudocode", "input_contract",
        "target_contract", "loss_and_regularization", "fit_protocol", "research_record",
        "why_existing_library_is_insufficient",
    )
    if any(not isinstance(proposal[key], str) or not proposal[key].strip() for key in text_fields):
        raise ValueError("algorithm mechanism, math and executable protocol must be explicit")
    if not proposal["evidence_refs"]:
        raise ValueError("algorithm must respond to observed trajectory evidence")
    if proposal["changed_stage"] not in ALGORITHM_STAGES:
        raise ValueError("algorithm design must name a supported open research stage")
    if len(proposal["closest_methods"]) < 2:
        raise ValueError("compare against at least two closest methods")
    if len(proposal["source_findings"]) < 2 or len(proposal["transfer_limits"]) < 2:
        raise ValueError("algorithm design requires read-source findings and transfer limits")
    if proposal["novelty_level"] not in {
        "new_to_project", "new_composition", "new_mechanism", "new_formulation"
    }:
        raise ValueError("unknown or overstated novelty level")
    if proposal["previously_untried_in_project"] is not True:
        raise ValueError("exploration slot must be previously untried in this project")
    required_baselines = {"unchanged_parent", "simple_baseline"}
    if not required_baselines.issubset(set(proposal["same_data_baselines"])):
        raise ValueError("new algorithms need an unchanged parent and a simple baseline")
    if len(proposal["ablations"]) < 2 or "remove_new_mechanism" not in proposal["ablations"]:
        raise ValueError("proposal needs at least two ablations including removal of the new mechanism")
    if len(proposal["failure_modes"]) < 2 or len(proposal["synthetic_tests"]) < 2:
        raise ValueError("proposal needs explicit failure modes and synthetic tests")
    if type(proposal["maximum_cpu_seconds"]) is not int or proposal["maximum_cpu_seconds"] <= 0:
        raise ValueError("positive CPU bound required")
    if type(proposal["maximum_memory_mb"]) is not int or proposal["maximum_memory_mb"] <= 0:
        raise ValueError("positive memory bound required")
    if proposal["requests_sealed_data"] is not False:
        raise ValueError("algorithm design cannot request sealed data")
    if not isinstance(proposal["external_dependencies"], list):
        raise ValueError("external dependencies must be declared")


def archive_proposal(proposal: dict) -> dict:
    validate_proposal(proposal)
    result = {
        "schema": "controller_algorithm_design_v1",
        "proposal": proposal,
        "activated": False,
        "implementation_authorized": False,
        "novelty_is_not_selection_evidence": True,
        "required_next_steps": [
            "verify_bound_trainer_research_record_and_closest_methods",
            "sandboxed_reference_implementation",
            "synthetic_positive_and_negative_canaries",
            "same_row_train_comparison",
            "ablation_report",
            "new_harness_version_before_route_dev",
        ],
    }
    result["proposal_sha256"] = digest(result)
    return result
