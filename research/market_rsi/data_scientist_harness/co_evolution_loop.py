"""Fail-closed alternating lineage for experiments and Harness releases.

The Harness may not evolve in a vacuum.  A published Harness H_t first owns a
complete experiment batch E_t.  Only E_t's immutable evidence may open the
outer review that proposes and validates many Harness candidates.  Exactly one
candidate can be linked to a new published H_{t+1}; only then may E_{t+1}
start.  These pure builders return hash-bound records; callers persist them in
append-only artifact directories.
"""
from __future__ import annotations

from market_rsi import digest


SHA_LENGTH = 64
COMPONENTS = {
    "research_question",
    "data_acquisition",
    "data_quality",
    "representation_learning",
    "feature_engineering",
    "target_design",
    "prediction_algorithm",
    "trainer_engineering",
    "decision_policy",
    "market_mechanism",
    "simulation_environment",
    "evaluation_diagnostics",
    "controller_context",
    "tool_interface",
    "archive_format",
}


def _sha(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != SHA_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be a lowercase SHA256")


def _seal(value: dict) -> dict:
    result = dict(value)
    result["record_sha256"] = digest(result)
    return result


def _verify(record: dict) -> None:
    _sha(record.get("record_sha256", ""), "record_sha256")
    if digest({key: value for key, value in record.items() if key != "record_sha256"}) != record["record_sha256"]:
        raise ValueError("co-evolution record was modified")


def begin_experiment_batch(release: dict, claim: dict) -> dict:
    required_release = {
        "harness_version", "release_sha256", "commit", "tag", "published", "canary_sha256"
    }
    required_claim = {
        "experiment_id", "harness_release_sha256", "harness_commit",
        "pre_score_lock_sha256", "planned_inner_rounds", "artifact_root",
        "route_dev_policy", "final_policy",
    }
    if set(release) != required_release or set(claim) != required_claim:
        raise ValueError("exact release and experiment claim schemas required")
    for key in ("release_sha256", "canary_sha256"):
        _sha(release[key], key)
    _sha(claim["pre_score_lock_sha256"], "pre_score_lock_sha256")
    if release["published"] is not True:
        raise ValueError("experiment requires a published Harness release")
    if claim["harness_release_sha256"] != release["release_sha256"]:
        raise ValueError("experiment is not bound to the Harness release")
    if claim["harness_commit"] != release["commit"]:
        raise ValueError("experiment is not bound to the Harness commit")
    if type(claim["planned_inner_rounds"]) is not int or claim["planned_inner_rounds"] <= 0:
        raise ValueError("positive planned inner rounds required")
    if claim["route_dev_policy"] not in {"sealed", "one_shot_after_train_selection"}:
        raise ValueError("explicit Route-Dev policy required")
    if claim["final_policy"] != "sealed_until_terminal_acceptance":
        raise ValueError("Final must remain sealed")
    return _seal({
        "schema": "co_evolution_experiment_batch_v1",
        "state": "experiment_running",
        "release": release,
        "claim": claim,
        "harness_upgrade_allowed": False,
        "next_experiment_allowed": False,
    })


def complete_experiment_batch(batch: dict, completion: dict) -> dict:
    _verify(batch)
    if batch.get("state") != "experiment_running":
        raise ValueError("only a running experiment can complete")
    required = {
        "experiment_id", "harness_release_sha256", "status", "inner_rounds_completed",
        "manifest_sha256", "trajectory_sha256", "artifact_hashes", "cost_usd",
        "route_dev_opened", "sealed_final_opened", "terminal_cleanup_passed",
    }
    if set(completion) != required:
        raise ValueError("exact experiment completion schema required")
    if completion["experiment_id"] != batch["claim"]["experiment_id"]:
        raise ValueError("completion belongs to another experiment")
    if completion["harness_release_sha256"] != batch["release"]["release_sha256"]:
        raise ValueError("completion belongs to another Harness")
    if completion["status"] not in {"complete", "scientific_failure", "infrastructure_failure"}:
        raise ValueError("terminal experiment status required")
    if type(completion["inner_rounds_completed"]) is not int or completion["inner_rounds_completed"] < 0:
        raise ValueError("valid completed round count required")
    for key in ("manifest_sha256", "trajectory_sha256"):
        _sha(completion[key], key)
    if not isinstance(completion["artifact_hashes"], dict) or not completion["artifact_hashes"]:
        raise ValueError("complete artifact hash inventory required")
    for value in completion["artifact_hashes"].values():
        _sha(value, "artifact hash")
    if completion["manifest_sha256"] not in completion["artifact_hashes"].values():
        raise ValueError("manifest missing from artifact inventory")
    if completion["trajectory_sha256"] not in completion["artifact_hashes"].values():
        raise ValueError("trajectory missing from artifact inventory")
    if completion["cost_usd"] < 0:
        raise ValueError("negative experiment cost")
    if completion["sealed_final_opened"] is not False:
        raise ValueError("sealed Final exposure blocks Harness evolution")
    if completion["terminal_cleanup_passed"] is not True:
        raise ValueError("terminal cleanup required before Harness review")
    return _seal({
        "schema": "co_evolution_experiment_completion_v1",
        "state": "experiment_complete",
        "parent_batch_sha256": batch["record_sha256"],
        "release": batch["release"],
        "claim": batch["claim"],
        "completion": completion,
        "harness_upgrade_allowed": False,
        "next_experiment_allowed": False,
    })


def open_harness_review(completed: dict, observations: list[dict]) -> dict:
    _verify(completed)
    if completed.get("state") != "experiment_complete":
        raise ValueError("Harness review requires a terminal experiment")
    if not observations:
        raise ValueError("Harness cannot evolve without experiment observations")
    available = set(completed["completion"]["artifact_hashes"].values())
    seen = set()
    blocking = False
    for observation in observations:
        required = {
            "observation_id", "component", "severity", "evidence_sha256",
            "problem", "blocked_action", "machine_observation", "harness_interpretation",
        }
        if set(observation) != required:
            raise ValueError("exact observation schema required")
        if observation["observation_id"] in seen:
            raise ValueError("duplicate observation id")
        seen.add(observation["observation_id"])
        if observation["component"] not in COMPONENTS:
            raise ValueError("observation names an unknown Harness component")
        if observation["severity"] not in {"minor", "material", "blocking"}:
            raise ValueError("unknown observation severity")
        if observation["evidence_sha256"] not in available:
            raise ValueError("observation is not bound to the completed experiment")
        if not all(observation[key].strip() for key in (
            "problem", "blocked_action", "machine_observation", "harness_interpretation"
        )):
            raise ValueError("observation and interpretation must be explicit")
        blocking = blocking or observation["severity"] == "blocking"
    enough_inner_work = completed["completion"]["inner_rounds_completed"] >= 3
    if not (enough_inner_work or blocking):
        raise ValueError("run more inner rounds unless a blocking observation ended the batch")
    return _seal({
        "schema": "co_evolution_harness_review_v1",
        "state": "candidate_generation",
        "parent_completion_sha256": completed["record_sha256"],
        "parent_release": completed["release"],
        "experiment_id": completed["claim"]["experiment_id"],
        "observations": observations,
        "candidate_generation_may_be_broad": True,
        "selection_may_change_components": 1,
        "predictive_dev_score_available_to_selection": False,
        "harness_upgrade_allowed": False,
        "next_experiment_allowed": False,
    })


def freeze_candidate_portfolio(review: dict, candidates: list[dict]) -> dict:
    _verify(review)
    if review.get("state") != "candidate_generation":
        raise ValueError("candidate portfolio requires an open Harness review")
    if not 2 <= len(candidates) <= 256:
        raise ValueError("generate between 2 and 256 Harness candidates")
    observation_ids = {item["observation_id"] for item in review["observations"]}
    candidate_ids = set()
    exploration_present = False
    for candidate in candidates:
        required = {
            "candidate_id", "observation_ids", "changed_component", "proposal_sha256",
            "previously_untried_in_project", "literature_record_ids", "implementation_scope",
            "validation_plan", "estimated_patch_lines", "estimated_next_round_cost_usd",
            "requests_kernel_change", "requests_sealed_data", "uses_predictive_dev_score",
        }
        if set(candidate) != required:
            raise ValueError("exact Harness candidate schema required")
        if candidate["candidate_id"] in candidate_ids:
            raise ValueError("duplicate Harness candidate id")
        candidate_ids.add(candidate["candidate_id"])
        if not set(candidate["observation_ids"]).issubset(observation_ids) or not candidate["observation_ids"]:
            raise ValueError("candidate must cite this experiment's observations")
        if candidate["changed_component"] not in COMPONENTS:
            raise ValueError("candidate changes an unknown Harness component")
        _sha(candidate["proposal_sha256"], "proposal_sha256")
        if candidate["estimated_patch_lines"] <= 0 or candidate["estimated_next_round_cost_usd"] < 0:
            raise ValueError("candidate needs positive scope and nonnegative cost")
        if candidate["requests_kernel_change"] or candidate["requests_sealed_data"]:
            raise ValueError("candidate cannot alter the protected kernel or open sealed data")
        if candidate["uses_predictive_dev_score"]:
            raise ValueError("Harness selection cannot use predictive Dev score")
        if not candidate["implementation_scope"] or not candidate["validation_plan"]:
            raise ValueError("candidate needs implementation and validation plans")
        if candidate["previously_untried_in_project"]:
            if not candidate["literature_record_ids"]:
                raise ValueError("untried candidate requires actual literature records")
            exploration_present = True
    if not exploration_present:
        raise ValueError("each outer review must consider at least one previously untried candidate")
    return _seal({
        "schema": "co_evolution_candidate_portfolio_v1",
        "state": "candidate_portfolio_frozen",
        "parent_review_sha256": review["record_sha256"],
        "parent_release": review["parent_release"],
        "experiment_id": review["experiment_id"],
        "observations": review["observations"],
        "candidates": candidates,
        "candidate_count": len(candidates),
        "novelty_is_not_a_selection_score": True,
        "harness_upgrade_allowed": False,
        "next_experiment_allowed": False,
    })


def select_harness_candidate(portfolio: dict, selection: dict) -> dict:
    _verify(portfolio)
    if portfolio.get("state") != "candidate_portfolio_frozen":
        raise ValueError("selection requires a frozen candidate portfolio")
    required = {
        "selected_candidate_id", "selection_sha256", "eligible_candidate_ids",
        "validation_receipt_hashes", "selection_rule", "predictive_dev_score_used",
    }
    if set(selection) != required:
        raise ValueError("exact selection schema required")
    candidates = {item["candidate_id"]: item for item in portfolio["candidates"]}
    if selection["selected_candidate_id"] not in candidates:
        raise ValueError("selection must name exactly one portfolio candidate")
    if not set(selection["eligible_candidate_ids"]).issubset(candidates):
        raise ValueError("eligible candidates must come from the frozen portfolio")
    if selection["selected_candidate_id"] not in selection["eligible_candidate_ids"]:
        raise ValueError("selected candidate was not validation-eligible")
    if set(selection["validation_receipt_hashes"]) != set(selection["eligible_candidate_ids"]):
        raise ValueError("every eligible candidate needs one validation receipt")
    for value in selection["validation_receipt_hashes"].values():
        _sha(value, "validation receipt")
    _sha(selection["selection_sha256"], "selection_sha256")
    if selection["predictive_dev_score_used"] is not False:
        raise ValueError("Harness selection cannot use predictive Dev score")
    return _seal({
        "schema": "co_evolution_harness_selection_v1",
        "state": "next_release_required",
        "parent_portfolio_sha256": portfolio["record_sha256"],
        "parent_release": portfolio["parent_release"],
        "experiment_id": portfolio["experiment_id"],
        "selected_candidate": candidates[selection["selected_candidate_id"]],
        "selection": selection,
        "harness_upgrade_allowed": True,
        "next_experiment_allowed": False,
    })


def bind_next_release(selected: dict, new_release: dict) -> dict:
    _verify(selected)
    if selected.get("state") != "next_release_required":
        raise ValueError("new release requires one selected Harness candidate")
    required = {
        "harness_version", "release_sha256", "commit", "tag", "published", "canary_sha256",
        "parent_release_sha256", "selected_candidate_id", "selection_sha256",
    }
    if set(new_release) != required:
        raise ValueError("exact next-release schema required")
    parent = selected["parent_release"]
    for key in ("release_sha256", "canary_sha256", "parent_release_sha256", "selection_sha256"):
        _sha(new_release[key], key)
    if new_release["published"] is not True:
        raise ValueError("next Harness must be committed, tagged and published")
    if new_release["parent_release_sha256"] != parent["release_sha256"]:
        raise ValueError("next release is not linked to its parent Harness")
    if new_release["selected_candidate_id"] != selected["selected_candidate"]["candidate_id"]:
        raise ValueError("next release implements another candidate")
    if new_release["selection_sha256"] != selected["selection"]["selection_sha256"]:
        raise ValueError("next release is not bound to the frozen selection")
    if new_release["commit"] == parent["commit"] or new_release["tag"] == parent["tag"]:
        raise ValueError("Harness upgrade requires a fresh immutable commit and tag")
    return _seal({
        "schema": "co_evolution_release_link_v1",
        "state": "next_experiment_required",
        "parent_selection_sha256": selected["record_sha256"],
        "parent_release": parent,
        "selected_candidate": selected["selected_candidate"],
        "new_release": new_release,
        "harness_upgrade_allowed": False,
        "next_experiment_allowed": True,
    })


def begin_next_experiment(link: dict, claim: dict) -> dict:
    _verify(link)
    if link.get("state") != "next_experiment_required" or not link["next_experiment_allowed"]:
        raise ValueError("next experiment requires a published next Harness")
    release = {
        key: link["new_release"][key]
        for key in ("harness_version", "release_sha256", "commit", "tag", "published", "canary_sha256")
    }
    return begin_experiment_batch(release, claim)
