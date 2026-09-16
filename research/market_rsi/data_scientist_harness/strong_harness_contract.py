"""Fail-closed contract for a co-evolving Codex research harness.

The strong harness may propose and implement changes to the evolvable shell.
It may not rewrite the protected experimental kernel.  Candidate selection is
based on independent replay/canary receipts, never on the next hidden score.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "high"

PROTECTED_KERNEL = (
    "train_dev_final_partition",
    "sealed_final_access",
    "budget_hard_cap",
    "append_only_cost_ledger",
    "retry_for_score_prohibition",
    "artifact_hash_binding",
    "external_side_effect_authorization",
    "provider_terms_and_identity_integrity",
    "independent_grader",
)

EVOLVABLE_COMPONENTS = (
    "data_acquisition",
    "data_quality",
    "feature_engineering",
    "target_design",
    "trainer_engineering",
    "evaluation_diagnostics",
    "controller_context",
    "tool_interface",
    "archive_format",
)

SEVERITY = {"minor": 1, "material": 2, "blocking": 3}


def digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Observation:
    observation_id: str
    severity: str
    component: str
    evidence_refs: tuple[str, ...]
    problem: str
    blocked_action: str

    def validate(self) -> None:
        if not self.observation_id or self.severity not in SEVERITY:
            raise ValueError("observation needs an id and known severity")
        if self.component not in EVOLVABLE_COMPONENTS:
            raise ValueError("observation must name one evolvable component")
        if not self.evidence_refs or not self.problem or not self.blocked_action:
            raise ValueError("observation requires evidence, problem and blocked action")


def validate_proposal(proposal: dict, observations: dict[str, Observation]) -> None:
    required = {
        "candidate_id", "parent_harness_version", "observation_ids",
        "changed_component", "hypothesis", "implementation_scope",
        "replay_cases", "new_canaries", "requested_kernel_changes",
        "external_side_effects", "estimated_patch_lines",
    }
    if set(proposal) != required:
        raise ValueError("proposal must use the exact strong-harness schema")
    if not proposal["candidate_id"] or not proposal["parent_harness_version"]:
        raise ValueError("candidate and parent harness identifiers are required")
    if proposal["changed_component"] not in EVOLVABLE_COMPONENTS:
        raise ValueError("unknown evolvable component")
    if proposal["requested_kernel_changes"]:
        raise ValueError("the protected kernel cannot co-evolve")
    if proposal["external_side_effects"]:
        raise ValueError("proposal validation cannot purchase, message or open sealed data")
    if type(proposal["estimated_patch_lines"]) is not int or proposal["estimated_patch_lines"] <= 0:
        raise ValueError("positive estimated patch size required")
    if not proposal["hypothesis"] or not proposal["implementation_scope"]:
        raise ValueError("proposal needs a falsifiable hypothesis and scope")
    if not proposal["replay_cases"] or not proposal["new_canaries"]:
        raise ValueError("proposal needs historical replay and a new canary")
    if not proposal["observation_ids"]:
        raise ValueError("proposal must address observed trajectory evidence")
    for identifier in proposal["observation_ids"]:
        if identifier not in observations:
            raise ValueError("proposal cites an unknown observation")
    if not any(
        observations[identifier].component == proposal["changed_component"]
        for identifier in proposal["observation_ids"]
    ):
        raise ValueError("changed component does not match the cited bottleneck")


def validate_receipt(receipt: dict, candidate_id: str) -> None:
    required = {
        "candidate_id", "source_compiles", "unit_tests_passed",
        "historical_replays_passed", "historical_replays_total",
        "new_canaries_passed", "new_canaries_total", "negative_canary_passed",
        "unrelated_regressions_passed", "protected_kernel_unchanged",
        "sealed_data_opened", "external_side_effect_executed",
        "measured_patch_lines", "estimated_next_round_cost_usd",
    }
    if set(receipt) != required or receipt["candidate_id"] != candidate_id:
        raise ValueError("validation receipt does not match candidate")
    if type(receipt["measured_patch_lines"]) is not int or receipt["measured_patch_lines"] <= 0:
        raise ValueError("measured patch size required")
    if receipt["estimated_next_round_cost_usd"] < 0:
        raise ValueError("negative cost estimate")
    for passed, total in (
        (receipt["historical_replays_passed"], receipt["historical_replays_total"]),
        (receipt["new_canaries_passed"], receipt["new_canaries_total"]),
    ):
        if type(passed) is not int or type(total) is not int or total <= 0 or not 0 <= passed <= total:
            raise ValueError("invalid replay/canary count")


def eligible(receipt: dict) -> bool:
    return all((
        receipt["source_compiles"],
        receipt["unit_tests_passed"],
        receipt["historical_replays_passed"] == receipt["historical_replays_total"],
        receipt["new_canaries_passed"] == receipt["new_canaries_total"],
        receipt["negative_canary_passed"],
        receipt["unrelated_regressions_passed"],
        receipt["protected_kernel_unchanged"],
        receipt["sealed_data_opened"] is False,
        receipt["external_side_effect_executed"] is False,
    ))


def select_one(
    parent_harness_version: str,
    observations: list[Observation],
    proposals: list[dict],
    receipts: list[dict],
) -> dict:
    """Select one validated patch using a predeclared lexicographic rule.

    Priority: higher-severity evidenced bottleneck, then smaller measured patch,
    then lower next-round cost, then candidate id.  Predictive score is absent.
    """
    observation_map = {item.observation_id: item for item in observations}
    if len(observation_map) != len(observations):
        raise ValueError("duplicate observation id")
    for item in observations:
        item.validate()
    proposal_map = {}
    for proposal in proposals:
        validate_proposal(proposal, observation_map)
        if proposal["parent_harness_version"] != parent_harness_version:
            raise ValueError("proposal has the wrong parent harness")
        if proposal["candidate_id"] in proposal_map:
            raise ValueError("duplicate candidate id")
        proposal_map[proposal["candidate_id"]] = proposal
    receipt_map = {}
    for receipt in receipts:
        identifier = receipt.get("candidate_id")
        if identifier not in proposal_map or identifier in receipt_map:
            raise ValueError("receipt has unknown or duplicate candidate")
        validate_receipt(receipt, identifier)
        receipt_map[identifier] = receipt
    if set(receipt_map) != set(proposal_map):
        raise ValueError("every candidate needs one validation receipt")

    qualified = []
    for identifier, proposal in proposal_map.items():
        receipt = receipt_map[identifier]
        if not eligible(receipt):
            continue
        severity = max(SEVERITY[observation_map[item].severity] for item in proposal["observation_ids"])
        qualified.append((
            -severity,
            receipt["measured_patch_lines"],
            receipt["estimated_next_round_cost_usd"],
            identifier,
        ))
    selected = min(qualified)[3] if qualified else None
    result = {
        "schema": "strong_harness_selection_v1",
        "strong_harness_model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "parent_harness_version": parent_harness_version,
        "selected_candidate_id": selected,
        "selection_rule": (
            "all gates pass; highest observed severity; smallest measured patch; "
            "lowest estimated next-round cost; lexical id"
        ),
        "predictive_score_used_for_selection": False,
        "sealed_data_used_for_selection": False,
        "candidate_count": len(proposals),
        "eligible_candidate_count": len(qualified),
        "protected_kernel": list(PROTECTED_KERNEL),
    }
    result["selection_sha256"] = digest(result)
    return result


def current_data_bottleneck() -> Observation:
    """Machine-readable starting observation from the 2025 NFL Train runs."""
    return Observation(
        observation_id="nfl-effective-sample-and-actionability-20260915",
        severity="blocking",
        component="data_acquisition",
        evidence_refs=(
            "artifacts/nfl-train-method-screen-20260915-02/result.json",
            "artifacts/nfl-train-local-projection-20260915-01/result.json",
            "artifacts/nfl-train-rsi-trajectory-20260915-01/trajectory.json",
        ),
        problem=(
            "Only 163 independent games from one season are available. Seven opened-Train RSI "
            "rounds lowered MSE only 4.59% versus zero-change; the harness can describe this "
            "shortage but cannot yet acquire, align, quality-gate and admit additional seasons."
        ),
        blocked_action=(
            "build a versioned multi-season Train candidate and a game-count learning curve "
            "before another broad trainer sweep"
        ),
    )


def current_algorithm_bottleneck() -> Observation:
    """The fixed catalog cannot express or test a controller-authored mechanism."""
    return Observation(
        observation_id="nfl-new-algorithm-design-gap-20260915",
        severity="material",
        component="trainer_engineering",
        evidence_refs=(
            "artifacts/nfl-train-rsi-trajectory-20260915-01/trajectory.json",
            "data_scientist_harness/sports_method_library.py",
        ),
        problem=(
            "The controller can select named trainers and file a shallow capability request, but "
            "it cannot archive a mathematical mechanism, pseudocode, ablations, failure modes and "
            "same-row verification plan for a genuinely new algorithm candidate."
        ),
        blocked_action=(
            "let the controller propose and sandbox a new prediction mechanism without granting "
            "arbitrary code execution or access to sealed data"
        ),
    )
