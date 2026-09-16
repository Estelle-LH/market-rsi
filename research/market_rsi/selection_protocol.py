"""One owned task-submission decision, separate from new experiment proposals.

All arms get one selection response under the task's common token/wall ceiling.
Invalid output falls back to the predeclared baseline, not another sample or a
host-selected best Dev candidate. This is protocol code, not data admission.
"""
from __future__ import annotations

import copy
import json

from market_rsi import canonical, digest, identifier
from researcher_worker import hash_string, prepare_request


INSTRUCTIONS = (
    "Research for this task is complete. Return exactly one JSON object with "
    "selected_candidate_id, reason, and evidence_trial_ids (a list). Choose one "
    "of eligible_candidates using only your supplied permitted evidence. You may "
    "choose the common baseline. You cannot propose code, another experiment, a "
    "new score, another candidate, or a guide revision in this response. No hidden "
    "result is available. Invalid output uses the common baseline without resampling."
)


def prepare_selection(common_manifest, *, arm, task, records, guide, candidates):
    current = [r for r in records if r["task_id"] == task["task_id"]]
    if not current or not isinstance(candidates, list) or not candidates:
        raise ValueError("completed current-task evidence and a common baseline required")
    seen = set()
    for index, item in enumerate(candidates):
        if not isinstance(item, dict) or set(item) != {"candidate_id", "trial_id", "source_sha256"}:
            raise ValueError("exact eligible candidate commitments required")
        candidate_id = identifier(item["candidate_id"])
        hash_string(item["source_sha256"])
        if candidate_id in seen:
            raise ValueError("duplicate candidate")
        seen.add(candidate_id)
        if index == 0:
            if candidate_id != "baseline" or item["trial_id"] is not None:
                raise ValueError("first candidate must be the frozen common baseline")
        elif (item["trial_id"] not in {r["trial_id"] for r in current}
              or candidate_id != "candidate-" + item["trial_id"]):
            raise ValueError("candidate is not from this task's owned evidence")
    prepared = prepare_request(common_manifest, arm=arm, task=task, records=records,
        step_index=max(r["step_index"] for r in current) + 1, guide=guide)
    public = json.loads(prepared["messages"][1]["content"])
    public.update(response_instructions=INSTRUCTIONS, can_revise_guide=False,
                  eligible_candidates=copy.deepcopy(candidates))
    prepared["messages"][1]["content"] = canonical(public)
    prepared["audit"].update(response_kind="task_selection", can_revise_guide=False,
        selection_candidates=copy.deepcopy(candidates), messages_sha256=digest(prepared["messages"]))
    prepared["packet_sha256"] = digest({k: v for k, v in prepared.items() if k != "packet_sha256"})
    return prepared


def assess_selection(text, audit):
    final = text.rsplit("</think>", 1)[-1].strip()
    for marker in ("<|user|>", "<|observation|>", "<|endoftext|>"):
        final = final.removesuffix(marker).strip()
    if final.startswith("```json") and final.endswith("```"):
        final = final[7:-3].strip()
    try:
        decision = json.loads(final)
        if (audit.get("response_kind") != "task_selection" or not isinstance(decision, dict)
                or set(decision) != {"selected_candidate_id", "reason", "evidence_trial_ids"}
                or decision["selected_candidate_id"] not in {c["candidate_id"] for c in audit["selection_candidates"]}
                or not isinstance(decision["reason"], str) or not decision["reason"].strip()
                or not isinstance(decision["evidence_trial_ids"], list)
                or any(not isinstance(x, str) for x in decision["evidence_trial_ids"])
                or len(set(decision["evidence_trial_ids"])) != len(decision["evidence_trial_ids"])
                or not set(decision["evidence_trial_ids"]) <= set(audit["allowed_trial_ids"])):
            raise ValueError("invalid selection or evidence")
        canonical(decision)
        return {"valid": True, "selection": decision, "scientific_merit_verified": False}
    except (ValueError, TypeError):
        return {"valid": False, "reason": "invalid selection or evidence", "scientific_merit_verified": False}
