"""Fail-closed alternating lineage for experiments and Harness releases.

The Harness may not evolve in a vacuum.  A published Harness H_t first owns a
complete experiment batch E_t.  Only E_t's immutable evidence may open the
outer review that proposes and validates many Harness candidates.  Exactly one
candidate can be linked to a new published H_{t+1}; only then may E_{t+1}
start.  These pure builders return hash-bound records; callers persist them in
append-only artifact directories.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath

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


# Optional small-step policy. The legacy alternating-release contract above is
# preserved for old records. These pure transitions are persisted by the existing
# ContinuousDiscoveryBatch journal; they neither run code nor grant authority.
MICRO_SCHEMA = "market_rsi_micro_evolution_v1"
MICRO_CONTEXT = frozenset({
    "model_sha256", "data_scope_sha256", "evaluation_sha256",
    "authority_sha256", "resource_policy_sha256",
})
MICRO_CHECKS = frozenset({
    "success_replay", "failure_feedback", "restart", "historical_replay",
    "protected_boundaries", "rollback", "anchor_compatibility", "bounded_trial",
})
MICRO_COMPONENTS = {
    "harness": {"scheduling", "tool_interface", "recovery", "feedback_delivery"},
    "researcher": {"instructions", "memory_policy", "research_policy"},
}
MICRO_ALWAYS_PROTECTED = frozenset({
    ".git", ".codex", ".agents", "artifacts", "paid_budget.py",
    "data_scientist_harness/co_evolution_loop.py",
    "supervisor_harness/global_state_gate.py",
})


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"exact {label} fields required")


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(f"bounded nonblank {label} required")


def _nonzero_sha(value, label):
    _sha(value, label)
    if value == "0" * 64:
        raise ValueError(f"nonzero {label} required")


def _pair(value):
    _exact(value, {"harness_sha256", "researcher_sha256"}, "research pair")
    for key, token in value.items():
        _nonzero_sha(token, key)


def _paths(values):
    if (not isinstance(values, list) or not values
            or any(not isinstance(value, str) for value in values)
            or len(set(values)) != len(values)):
        raise ValueError("nonempty unique exact write paths required")
    for value in values:
        _text(value, "path")
        path = PurePosixPath(value)
        if (path.is_absolute() or str(path) != value or ".." in path.parts
                or value == "." or any(char in value for char in "\\*?[]\n\r\x00")):
            raise ValueError("canonical repository-relative path required")


def _micro(state):
    _verify(state)
    if state.get("schema") != MICRO_SCHEMA:
        raise ValueError("not a small-step evolution state")


def micro_pair_hash(state):
    _micro(state)
    return digest(state["active_pair"])


def initialize_micro_evolution(config):
    """Trusted supervisor config; no runtime authority or filesystem enforcement."""
    _exact(config, {"pair", "fixed_context", "allowed_write_paths", "protected_paths",
                    "reviewer_id"}, "small-step configuration")
    _pair(config["pair"])
    _exact(config["fixed_context"], MICRO_CONTEXT, "fixed context")
    for key, value in config["fixed_context"].items():
        _nonzero_sha(value, key)
    _text(config["reviewer_id"], "reviewer identity")
    _exact(config["allowed_write_paths"], MICRO_COMPONENTS, "axis write scopes")
    _paths(config["protected_paths"])
    protected_paths = sorted(set(config["protected_paths"]) | MICRO_ALWAYS_PROTECTED)
    for values in config["allowed_write_paths"].values():
        _paths(values)
        if any(path == protected or path.startswith(protected + "/")
               for path in values for protected in protected_paths):
            raise ValueError("write scope overlaps protected paths")
    return _seal({
        "schema": MICRO_SCHEMA, "active_pair": deepcopy(config["pair"]),
        "anchor_pair": deepcopy(config["pair"]), "previous_pair": None,
        "fixed_context": deepcopy(config["fixed_context"]),
        "allowed_write_paths": deepcopy(config["allowed_write_paths"]),
        "protected_paths": protected_paths,
        "reviewer_id": config["reviewer_id"], "pending": None,
        "used_candidate_ids": [], "history": [],
    })


def propose_micro_evolution(state, proposal):
    _micro(state)
    if state["pending"] is not None:
        raise ValueError("only one provisional change is allowed")
    _exact(proposal, {
        "candidate_id", "proposer_id", "axis", "component", "behavior_change",
        "problem_evidence_sha256", "parent_pair_sha256", "pair", "fixed_context",
        "write_paths", "patch_sha256",
    }, "small-step proposal")
    for key in ("candidate_id", "proposer_id", "behavior_change"):
        _text(proposal[key], key)
    if proposal["candidate_id"] in state["used_candidate_ids"]:
        raise ValueError("candidate ID cannot be reused")
    axis = proposal["axis"]
    if axis not in MICRO_COMPONENTS or proposal["component"] not in MICRO_COMPONENTS[axis]:
        raise ValueError("one known axis and component required")
    _pair(proposal["pair"])
    changed = {key for key in proposal["pair"]
               if proposal["pair"][key] != state["active_pair"][key]}
    if changed != {axis + "_sha256"}:
        raise ValueError("exactly one axis may change; hold the other fixed")
    if proposal["parent_pair_sha256"] != micro_pair_hash(state):
        raise ValueError("proposal has stale parent pair")
    if proposal["fixed_context"] != state["fixed_context"]:
        raise ValueError("model/data/evaluation/authority/resource context must stay fixed")
    _paths(proposal["write_paths"])
    if not set(proposal["write_paths"]).issubset(state["allowed_write_paths"][axis]):
        raise ValueError("proposal exceeds exact approved write scope")
    for key in ("problem_evidence_sha256", "patch_sha256"):
        _nonzero_sha(proposal[key], key)
    result = deepcopy(state)
    result["pending"] = _seal(deepcopy(proposal))
    result["used_candidate_ids"].append(proposal["candidate_id"])
    result.pop("record_sha256")
    return _seal(result)


def review_micro_evolution(state, review):
    """Validate trusted review evidence; not proof of test truth or actor identity.

    The supervisor must verify receipt artifacts and measured file diffs outside
    the candidate sandbox. This contract never executes or auto-deploys a patch.
    """
    _micro(state)
    pending = state["pending"]
    if pending is None:
        raise ValueError("no provisional change to review")
    _exact(review, {"reviewer_id", "proposal_sha256", "decision", "reason",
                    "tested_pair_sha256", "anchor_pair_sha256", "checks",
                    "benefit_observed", "benefit_evidence_sha256", "actual_write_paths"},
           "small-step review")
    if (review["reviewer_id"] != state["reviewer_id"]
            or review["reviewer_id"] == pending["proposer_id"]):
        raise ValueError("configured independent reviewer required")
    if review["proposal_sha256"] != pending["record_sha256"]:
        raise ValueError("review is not bound to the pending proposal")
    if review["decision"] not in {"accept", "reject"}:
        raise ValueError("accept or reject required")
    _text(review["reason"], "review reason")
    if type(review["benefit_observed"]) is not bool:
        raise ValueError("benefit must be an explicit boolean")
    if review["decision"] == "accept":
        if (review["tested_pair_sha256"] != digest(pending["pair"])
                or review["anchor_pair_sha256"] != digest(state["anchor_pair"])):
            raise ValueError("review tested another candidate or capability anchor")
        _paths(review["actual_write_paths"])
        if set(review["actual_write_paths"]) != set(pending["write_paths"]):
            raise ValueError("measured write scope differs from proposal")
        _exact(review["checks"], MICRO_CHECKS, "compatibility checks")
        for name, check in review["checks"].items():
            _exact(check, {"passed", "evidence_sha256"}, name)
            if check["passed"] is not True:
                raise ValueError(f"compatibility check failed: {name}")
            _nonzero_sha(check["evidence_sha256"], name)
        if review["benefit_observed"] is not True:
            raise ValueError("named benefit must be observed before acceptance")
        _nonzero_sha(review["benefit_evidence_sha256"], "benefit evidence")
    result = deepcopy(state)
    result["history"].append({"proposal": result["pending"], "review": deepcopy(review)})
    if review["decision"] == "accept":
        result["previous_pair"] = deepcopy(state["active_pair"])
        result["active_pair"] = deepcopy(pending["pair"])
    result["pending"] = None
    result.pop("record_sha256")
    return _seal(result)


def rollback_micro_evolution(state, receipt):
    _micro(state)
    _exact(receipt, {"reviewer_id", "reason", "evidence_sha256"}, "rollback receipt")
    if receipt["reviewer_id"] != state["reviewer_id"]:
        raise ValueError("configured reviewer required for rollback")
    if state["pending"] is not None or state["previous_pair"] is None:
        raise ValueError("rollback needs a prior pair and no provisional change")
    _text(receipt["reason"], "rollback reason")
    _nonzero_sha(receipt["evidence_sha256"], "rollback evidence")
    result = deepcopy(state)
    result["history"].append({"rollback": deepcopy(receipt),
                              "from_pair": deepcopy(state["active_pair"])})
    result["active_pair"] = deepcopy(state["previous_pair"])
    result["previous_pair"] = None
    result.pop("record_sha256")
    return _seal(result)
