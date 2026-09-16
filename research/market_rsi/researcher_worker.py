"""Common-context-bound research requests and single-dispatch accounting.

This module does not manufacture data-admission evidence. The live transport is
disabled unless the trusted outer worker supplies an independent admission
checker. No such production checker is wired yet. Offline tests use an explicitly
non-live transport and fabricated tasks, never real research-score claims.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import secrets
import time
from pathlib import Path

from glm_canary import MODEL, HF_MODEL, RATES, cost
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from research_context import ARMS, common_system_prompt


TASK_KEYS = {"schema", "experiment_id", "task_id", "task_index", "phase", "objective",
             "data_catalog", "evaluation_contract", "resource_limits", "opaque_test_commitment"}
RECORD_KEYS = {"schema", "experiment_id", "arm", "task_id", "task_index", "step_index", "phase",
               "trial_id", "visibility", "origin", "payload"}
PAYLOAD_KEYS = {"proposal", "candidate_code", "train_dev_results", "usage", "failure"}
GUIDE_KEYS = {"schema", "experiment_id", "arm", "revision_id", "origin", "text", "evidence_trial_ids"}
MEMORY_RECORD_MAX_BYTES = 8 * 1024
MEMORY_PROJECTION_NOTE = (
    "bounded model view; full raw record is runner-archived and committed by record_sha256; "
    "hash references replace repeated source, trace and oversized diagnostic text"
)
MEMORY_INSPECTION_KEYS = (
    "scope", "row_count", "expected_row_count", "anomalies", "input_audit",
    "runner_label_change", "runner_label_references",
    "feature_correlations_with_runner_label_change", "autocorrelation",
    "train_snapshot_reconstruction",
)
PROPOSAL_KEYS = {"action", "question", "changed_stage", "hypothesis", "coding_brief",
                 "expected_evidence", "guide_update"}
REQUIRED_PROPOSAL_KEYS = PROPOSAL_KEYS - {"guide_update"}
PROPOSAL_TEXT_LIMITS = {"question": 240, "hypothesis": 600, "coding_brief": 1800}
MAX_EXPECTED_EVIDENCE_ITEMS = 5
MAX_EXPECTED_EVIDENCE_CHARS = 320
MAX_GUIDE_TEXT_CHARS = 1200
MAX_GUIDE_EVIDENCE_IDS = 8
MAX_PROPOSAL_CHARS = 6000
CONTROLLER_REASONING_EFFORT = "low"
CONTROLLER_TEMPERATURE = 0.2
INSTRUCTIONS = (
    "Return one JSON object with action (experiment, inspect, or reject_measurement), question, "
    "changed_stage (data, signal, predictor, objective, or trading_policy), hypothesis, coding_brief, "
    "expected_evidence (list of strings), and guide_update. Choose your own research proposal; "
    "the coding component can analyze the full permitted Train/Dev artifacts in the sandbox. "
    "You have no direct tools. Keep each A/B to one changed stage. The external evaluation "
    "contract, eligible rows and budget cannot change; a proposed training loss does not change "
    "the external target. Use inspect or reject_measurement when the evidence is insufficient. "
    "When can_revise_guide is false, guide_update must be null. Otherwise it may be null or an "
    "object with text and evidence_trial_ids citing only supplied, independently scored experiment "
    "records. The final JSON must be concise: question <=240 characters, hypothesis <=600, "
    "coding_brief <=1800, at most five expected_evidence strings of <=320 characters each, and "
    "guide text <=1200 characters citing at most eight trial IDs. Keep the complete JSON under "
    "6000 characters. Do not use Markdown fences or add text before or after the JSON. Keep private "
    "reasoning brief so the final JSON is never truncated. No hidden-test result, another "
    "researcher's work or live chat is available."
)


class ProposalValidationError(ValueError):
    """A stable machine-readable reason for rejecting one controller response."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def memory_reference(value, *, note):
    raw = canonical(value).encode()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "memory_projection": note}


def memory_text(value, limit=800):
    if not isinstance(value, str) or len(value) <= limit:
        return copy.deepcopy(value)
    raw = value.encode()
    return {"prefix": value[:limit], "original_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "truncated_for_memory": True}


def memory_proposal(value):
    if value is None:
        return None
    if isinstance(value, str):
        return memory_text(value, 1600)
    if not isinstance(value, dict):
        return memory_reference(value, note="full proposal remains in the runner record")
    result = {}
    for key, item in value.items():
        if key == "raw_response":
            result["raw_response_reference"] = memory_reference(
                item, note="raw selection response remains in the runner record")
        elif key == "expected_evidence" and isinstance(item, list):
            result[key] = [memory_text(entry, 400) for entry in item[:6]]
            if len(item) > 6:
                result["expected_evidence_reference"] = memory_reference(
                    item, note="complete evidence list remains in the runner record")
        elif key == "guide_update" and isinstance(item, dict):
            result[key] = {name: (memory_text(entry, 1000) if name == "text" else copy.deepcopy(entry))
                           for name, entry in item.items()}
        elif isinstance(item, str):
            result[key] = memory_text(item, 1000 if key in {"question", "hypothesis", "coding_brief"} else 600)
        else:
            result[key] = copy.deepcopy(item)
    return result


def memory_numeric(value):
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    value = copy.deepcopy(value)
    # Per-row predictions remain only in the immutable scorer artifact. They are
    # both large and an unnecessary route to memorizing individual Dev labels.
    value.pop("rows", None)
    raw = canonical(value).encode()
    if len(raw) <= 3000:
        return copy.deepcopy(value)
    keep = ("aggregate", "primary_metric", "baseline_rule", "target", "promotion",
            "uncertainty", "net_pnl", "net_pnl_status", "source_admission")
    result = {key: copy.deepcopy(value[key]) for key in keep if key in value}
    for key in ("by_game", "by_day"):
        if key in value:
            result[key + "_reference"] = memory_reference(
                value[key], note="complete breakdown remains in the runner record")
    result["full_numeric_reference"] = memory_reference(
        value, note="complete numeric result remains in the runner record")
    return result


def memory_inspection(value):
    if not isinstance(value, dict):
        return copy.deepcopy(value)

    # The sandbox returns a runner envelope whose actionable output is nested
    # under ``diagnostic``.  Earlier projections looked only at the envelope's
    # top level, so the next research call saw a hash but not the baseline MSE,
    # cadence, or data-quality findings it had just paid to obtain.  Flatten a
    # bounded set of scalar findings instead of copying the potentially large
    # diagnostic or hiding all of it behind a commitment.
    diagnostic = value.get("diagnostic", value)
    priority_terms = (
        ("baseline", "persistence"),
        ("target_minus_mid", "horizon_change", "change_distribution", "changes"),
        ("temporal", "cadence", "gap", "interval", "autocorrelation"),
        ("row_count", "expected_count", "count_checks", "coverage"),
        ("anomal", "missing", "quality", "audit", "contradiction", "contract_check"),
        ("distribution_shift", "feature", "correlation", "dynamics", "candidate"),
    )
    candidates = []
    truncated = False

    def path_priority(path):
        lowered = path.lower()
        semantic_rank = next(
            (rank for rank, terms in enumerate(priority_terms)
             if any(term in lowered for term in terms)),
            len(priority_terms),
        )
        # Public Dev structure is useful, but it must not crowd out Train
        # baselines, target movement, or cadence evidence.
        dev_penalty = 1 if "dev_public" in lowered else 0
        return semantic_rank, dev_penalty, path.count("."), path

    def add_scalars(item, path, depth=0):
        nonlocal truncated
        if len(candidates) >= 4096:
            truncated = True
            return
        if item is None or isinstance(item, (bool, int, float)):
            candidates.append((path, copy.deepcopy(item)))
            return
        if isinstance(item, str):
            candidates.append((path, memory_text(item, 180)))
            return
        if depth >= 5:
            candidates.append((path + ".reference", memory_reference(
                item, note="complete nested diagnostic remains in the runner record")))
            truncated = True
            return
        if isinstance(item, dict):
            for key in sorted(item):
                add_scalars(item[key], f"{path}.{key}" if path else str(key), depth + 1)
                if len(candidates) >= 4096:
                    break
            return
        if isinstance(item, list):
            for index, entry in enumerate(item[:4]):
                add_scalars(entry, f"{path}[{index}]", depth + 1)
                if len(candidates) >= 4096:
                    break
            if len(item) > 4:
                truncated = True
            return
        candidates.append((path, memory_reference(
            item, note="complete diagnostic value remains in the runner record")))

    if isinstance(diagnostic, dict):
        # Rank by the complete path after collecting scalars. This handles
        # diagnostics whose useful evidence is called ``persistence_train`` or
        # ``train_baselines`` rather than an exact top-level ``baseline`` key.
        for key in sorted(diagnostic, key=path_priority):
            add_scalars(diagnostic[key], key)
            if len(candidates) >= 4096:
                break
    else:
        add_scalars(diagnostic, "diagnostic")

    candidates.sort(key=lambda entry: path_priority(entry[0]))
    if len(candidates) > 64:
        truncated = True
    findings = {path: item for path, item in candidates[:64]}

    result = {key: copy.deepcopy(value[key]) for key in
              ("scored", "scientific_admission", "independent_score", "origin") if key in value}
    result["diagnostic_findings"] = findings
    result["diagnostic_summary_truncated"] = truncated
    result["full_inspection_reference"] = memory_reference(
        value, note="complete inspection remains in the runner record")
    while len(canonical(result).encode()) > 3500 and findings:
        findings.pop(next(reversed(findings)))
        result["diagnostic_summary_truncated"] = True
    return result


def memory_trace(value):
    if not isinstance(value, dict):
        return memory_reference(value, note="complete execution trace remains in the runner record")
    result = {}
    if "coding_notes" in value:
        result["coding_notes"] = memory_text(value["coding_notes"], 600)
    if "data_evidence" in value:
        result["data_evidence"] = copy.deepcopy(value["data_evidence"])
    if "candidate_stderr" in value:
        stderr = value["candidate_stderr"]
        if isinstance(stderr, dict):
            result["candidate_stderr"] = {key: copy.deepcopy(stderr[key]) for key in
                ("bytes", "encoding", "independent_diagnosis", "origin", "sha256", "truncated")
                if key in stderr}
        else:
            result["candidate_stderr"] = memory_reference(
                stderr, note="complete stderr remains in the runner record")
    if "research_response" in value:
        result["research_response_reference"] = memory_reference(
            value["research_response"], note="proposal already appears separately; raw response remains archived")
    result["full_trace_reference"] = memory_reference(
        value, note="complete trace remains in the runner record")
    return result


def memory_results(value):
    result = {}
    for split, item in value.items():
        if not isinstance(item, dict):
            result[split] = memory_reference(item, note="complete split result remains in the runner record")
            continue
        projected = {key: copy.deepcopy(item[key]) for key in
                     ("execution_verified", "scientific_admission") if key in item}
        if "numeric" in item:
            projected["numeric"] = memory_numeric(item["numeric"])
        if "inspection" in item:
            projected["inspection"] = memory_inspection(item["inspection"])
        if "available_trace" in item:
            projected["available_trace"] = memory_trace(item["available_trace"])
        projected["full_split_reference"] = memory_reference(
            item, note="complete Train/Dev split result remains in the runner record")
        result[split] = projected
    return result


def memory_usage(value):
    if not isinstance(value, dict):
        return memory_reference(value, note="complete usage remains in the runner record")
    result = {key: (memory_text(value[key], 600) if isinstance(value[key], str)
                    else copy.deepcopy(value[key])) for key in
              ("research_token_metered_estimate_usd", "invoice_complete", "note") if key in value}
    for key in ("coding", "sandbox"):
        if key in value and isinstance(value[key], dict):
            result[key] = {name: copy.deepcopy(value[key][name]) for name in
                ("allocated_cost_usd", "economic_cost_complete", "elapsed_seconds", "model_requested",
                 "provider_request_count", "authentication", "exact_cleanup_acknowledged", "invoiced_usd",
                 "job_state", "metered_usd", "unresolved_hold_usd") if name in value[key]}
    result["full_usage_reference"] = memory_reference(
        value, note="complete usage remains in the runner record")
    return result


def minimal_memory_proposal(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        return memory_text(value, 600)
    keep = ("action", "changed_stage", "question", "hypothesis", "kind", "decision",
            "accepted_candidate_id", "fallback")
    result = {key: (memory_text(value[key], 600) if isinstance(value[key], str)
                    else copy.deepcopy(value[key])) for key in keep if key in value}
    result["full_proposal_reference"] = memory_reference(
        value, note="complete proposal remains in the runner record")
    return result


def minimal_memory_numeric(value):
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    value = copy.deepcopy(value)
    value.pop("rows", None)
    keep = ("aggregate", "primary_metric", "baseline_rule", "target", "promotion",
            "uncertainty", "net_pnl_status", "source_admission")
    result = {}
    for key in keep:
        if key not in value:
            continue
        item = value[key]
        result[key] = (copy.deepcopy(item) if len(canonical(item).encode()) <= 1200 else
                       memory_reference(item, note="complete numeric field remains in the runner record"))
    result["full_numeric_reference"] = memory_reference(
        value, note="complete numeric result remains in the runner record")
    return result


def memory_payload(payload):
    """Deterministic model view of a fully archived experiment record.

    Raw task rows, generated source, event streams and per-row predictions stay
    in runner-owned artifacts committed by ``record_sha256``. Repeating those
    blobs in every later prompt would make Archive/Learn overflow for reasons
    unrelated to research quality. The model retains its complete decision,
    runner score by game/day, execution diagnosis, failure and cost evidence.
    """
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS:
        raise ValueError("complete research payload required")
    code = payload["candidate_code"]
    result = {"proposal": memory_proposal(payload["proposal"]),
              "train_dev_results": memory_results(payload["train_dev_results"]),
              "usage": memory_usage(payload["usage"]),
              "failure": copy.deepcopy(payload["failure"])}
    result["candidate_code_sha256"] = hashlib.sha256(
        (code if isinstance(code, str) else canonical(code)).encode()).hexdigest()
    # The projection note is part of the record sent to the model, so include it
    # before enforcing the byte bound.  Checking first and appending the note
    # afterwards allowed a record that was only a few bytes under the limit to
    # cross it and fall all the way back to a hash-only result, hiding the
    # candidate's numeric score from the selector.
    result["memory_projection"] = MEMORY_PROJECTION_NOTE
    if len(canonical(result).encode()) > MEMORY_RECORD_MAX_BYTES:
        result["train_dev_results"] = {split: {
            "numeric": minimal_memory_numeric(item.get("numeric")) if isinstance(item, dict) else None,
            "full_split_reference": memory_reference(
                item, note="complete Train/Dev split result remains in the runner record")}
            for split, item in payload["train_dev_results"].items()}
        result["proposal"] = minimal_memory_proposal(payload["proposal"])
        result["usage"] = memory_usage(payload["usage"])
        result["failure"] = (copy.deepcopy(payload["failure"])
            if len(canonical(payload["failure"]).encode()) <= 1000
            else memory_reference(payload["failure"], note="complete failure remains in the runner record"))
    if len(canonical(result).encode()) > MEMORY_RECORD_MAX_BYTES:
        result = {"proposal": memory_reference(
                    payload["proposal"], note="complete proposal remains in the runner record"),
                  "candidate_code_sha256": result["candidate_code_sha256"],
                  "train_dev_results": memory_reference(
                    payload["train_dev_results"], note="complete Train/Dev results remain in the runner record"),
                  "usage": memory_usage(payload["usage"]),
                  "failure": (copy.deepcopy(payload["failure"])
                    if len(canonical(payload["failure"]).encode()) <= 1000
                    else memory_reference(payload["failure"], note="complete failure remains in the runner record")),
                  "memory_projection": (
                    "minimal bounded model view; full raw record is runner-archived and committed by "
                    "record_sha256; every oversized component is represented by an immutable hash")}
    if len(canonical(result).encode()) > MEMORY_RECORD_MAX_BYTES:
        raise AssertionError("minimal memory projection violated fixed implementation bound")
    return result


def nonnegative_int(value):
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer index required")


def hash_string(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("SHA-256 commitment required")


def scored_experiment_record(record):
    """Whether a prior owned record may support a Learn guide revision.

    Failures and inspections remain visible in the ordinary history, but they
    cannot become durable research rules.  This keeps a debugging observation
    from silently turning into a cross-task scientific conclusion.
    """
    if not isinstance(record, dict):
        return False
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("failure") is not None:
        return False
    proposal = payload.get("proposal")
    if not isinstance(proposal, dict) or proposal.get("action") != "experiment":
        return False
    dev = payload.get("train_dev_results", {}).get("dev")
    return (isinstance(dev, dict) and dev.get("execution_verified") is True
            and isinstance(dev.get("numeric"), dict))


def _slot_policy(value):
    if value is None:
        return None
    if (not isinstance(value, dict)
            or set(value) != {"scoreable_candidates_remaining", "diagnostic_attempts_remaining",
                              "research_calls_remaining"}
            or any(type(value[key]) is not int or value[key] < 0 for key in value)):
        raise ValueError("exact nonnegative research slot policy required")
    return copy.deepcopy(value)


def prepare_request(common_manifest, *, arm, task, step_index, records, guide=None,
                    slot_policy=None):
    """Project only caller-admitted public task and owned Train/Dev records.

    Content provenance is the trusted artifact producer's responsibility; an
    ownership flag alone is not proof that a payload was correctly materialized.
    This function never reads arbitrary history paths or any hidden-test file.
    """
    if arm not in ARMS or not isinstance(task, dict) or set(task) != TASK_KEYS:
        raise ValueError("known arm and exact public task schema required")
    if task["schema"] != "market_research_task_v1" or task["phase"] not in {"learning", "transfer"}:
        raise ValueError("invalid public task")
    for key in ("experiment_id", "task_id"):
        identifier(task[key])
    nonnegative_int(task["task_index"])
    nonnegative_int(step_index)
    hash_string(task["opaque_test_commitment"])
    if not isinstance(task["data_catalog"], list) or not task["data_catalog"]:
        raise ValueError("public Train/Dev catalog required")
    for item in task["data_catalog"]:
        if (not isinstance(item, dict) or set(item) != {"artifact_id", "split", "sha256", "description"}
                or item["split"] not in {"train", "dev"}):
            raise ValueError("catalog contains nonpublic data or unexpected fields")
        identifier(item["artifact_id"])
        hash_string(item["sha256"])
    if {r["split"] for r in task["data_catalog"]} != {"train", "dev"}:
        raise ValueError("both Train and Dev must be declared")
    limits = task["resource_limits"]
    if not isinstance(limits, dict) or set(limits) != {"max_input_tokens", "max_output_tokens", "max_wall_seconds"}:
        raise ValueError("explicit common request limits required")
    if any(type(n) is not int or n <= 0 for n in limits.values()):
        raise ValueError("positive request bounds required")
    if not isinstance(records, list):
        raise ValueError("explicit owned record list required")
    allowed, seen, scored_evidence, previous_order = [], set(), set(), None
    for record in records:
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            raise ValueError("unexpected research record fields")
        if (record["schema"] != "market_research_record_v1" or record["arm"] != arm
                or record["experiment_id"] != task["experiment_id"]
                or record["visibility"] != "train_dev"
                or record["origin"] != "runner_recorded_train_dev"):
            raise ValueError("wrong owner, hidden evidence or unrecorded human advice")
        for key in ("task_id", "trial_id"):
            identifier(record[key])
        nonnegative_int(record["task_index"])
        nonnegative_int(record["step_index"])
        order = (record["task_index"], record["step_index"])
        if (order >= (task["task_index"], step_index) or record["trial_id"] in seen
                or (previous_order is not None and order <= previous_order)):
            raise ValueError("future, duplicate or reordered research history")
        previous_order = order
        seen.add(record["trial_id"])
        current = record["task_index"] == task["task_index"]
        if current != (record["task_id"] == task["task_id"]):
            raise ValueError("task identity/index mismatch")
        if record["phase"] not in {"learning", "transfer"}:
            raise ValueError("unknown record phase")
        if current and record["phase"] != task["phase"]:
            raise ValueError("task phase mismatch")
        if not current and (arm == "reset" or record["phase"] == "transfer"):
            raise ValueError("forbidden cross-task memory or transfer feedback")
        payload = record["payload"]
        if (not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS
                or not isinstance(payload["train_dev_results"], dict)
                or not set(payload["train_dev_results"]) <= {"train", "dev"}):
            raise ValueError("only Train/Dev feedback payloads are admissible")
        allowed.append({"trial_id": record["trial_id"], "task_id": record["task_id"],
                        "task_index": record["task_index"], "step_index": record["step_index"],
                        "payload": memory_payload(payload)})
        if scored_experiment_record(record):
            scored_evidence.add(record["trial_id"])
    guide_text = None
    if guide is not None:
        if not isinstance(guide, dict) or set(guide) != GUIDE_KEYS:
            raise ValueError("unexpected guide fields")
        if (arm != "learn" or guide["arm"] != arm or guide["experiment_id"] != task["experiment_id"]
                or guide["schema"] != "market_research_guide_v1" or guide["origin"] != "agent_generated"):
            raise ValueError("guide ownership/origin mismatch")
        identifier(guide["revision_id"])
        if (not isinstance(guide["text"], str) or not guide["text"].strip()
                or len(guide["text"]) > MAX_GUIDE_TEXT_CHARS
                or not isinstance(guide["evidence_trial_ids"], list) or not guide["evidence_trial_ids"]
                or len(guide["evidence_trial_ids"]) > MAX_GUIDE_EVIDENCE_IDS
                or not set(guide["evidence_trial_ids"]) <= scored_evidence):
            raise ValueError("guide lacks independently scored experiment evidence")
        guide_text = {"revision_id": guide["revision_id"], "text": guide["text"],
                      "evidence_trial_ids": guide["evidence_trial_ids"]}
    manifest_hash = file_hash(common_manifest)
    common = common_system_prompt(common_manifest, arm)
    if file_hash(common_manifest) != manifest_hash:
        raise ValueError("common initialization changed while preparing request")
    slots = _slot_policy(slot_policy)
    response_instructions = INSTRUCTIONS
    if slots is not None:
        if slots["diagnostic_attempts_remaining"] == 0:
            response_instructions += (
                " The separate diagnostic allowance is exhausted: action must be experiment; "
                "inspect and reject_measurement are invalid for this call.")
        else:
            response_instructions += (
                " At most one remaining diagnostic action may be used without filling a scoreable-candidate slot.")
        response_instructions += (
            f" There are {slots['scoreable_candidates_remaining']} scoreable candidate slots and "
            f"{slots['research_calls_remaining']} total research calls remaining including this call. "
            "Only an experiment that executes and receives an independent score fills a candidate slot; "
            "every response still consumes one total research call.")
    public = {"task": copy.deepcopy(task), "current_step": step_index, "records": allowed,
              "research_guide": guide_text,
              "can_revise_guide": arm == "learn" and task["phase"] == "learning" and bool(scored_evidence),
              "scored_guide_evidence_trial_ids": sorted(scored_evidence),
              "remaining_attempts": slots,
              "response_instructions": response_instructions}
    messages = [{"role": "system", "content": common}, {"role": "user", "content": canonical(public)}]
    prepared = {"messages": messages, "audit": {"arm": arm, "experiment_id": task["experiment_id"],
        "task_id": task["task_id"], "task_index": task["task_index"], "step_index": step_index,
        "phase": task["phase"], "common_manifest_sha256": manifest_hash,
        "common_text_sha256": hashlib.sha256(common.encode()).hexdigest(),
        "task_public_sha256": digest(task), "record_sha256": [digest(r) for r in records],
        "guide_sha256": digest(guide) if guide is not None else None,
        "allowed_trial_ids": sorted(seen), "can_revise_guide": public["can_revise_guide"],
        "scored_guide_evidence_trial_ids": sorted(scored_evidence), "slot_policy": slots,
        "resource_limits": copy.deepcopy(limits), "messages_sha256": digest(messages)}}
    return dict(prepared, packet_sha256=digest(prepared))


def _proposal_json_text(text):
    if not isinstance(text, str):
        raise ProposalValidationError("response_not_text")
    final = text.rsplit("</think>", 1)[-1].strip()
    changed = True
    while changed:
        changed = False
        for marker in ("<|user|>", "<|observation|>", "<|endoftext|>"):
            if final.endswith(marker):
                final = final[:-len(marker)].strip()
                changed = True
    if final.startswith("```json") and final.endswith("```"):
        final = final[7:-3].strip()
    elif final.startswith("```") and final.endswith("```"):
        final = final[3:-3].strip()
    if not final:
        raise ProposalValidationError("empty_final_response")
    if len(final) > MAX_PROPOSAL_CHARS:
        raise ProposalValidationError("proposal_too_long")
    return final


def assess_proposal(text, audit):
    try:
        proposal = json.loads(_proposal_json_text(text))
        if (not isinstance(proposal, dict)
                or not REQUIRED_PROPOSAL_KEYS <= set(proposal)
                or set(proposal) - PROPOSAL_KEYS):
            raise ProposalValidationError("proposal_schema")
        # When omitted, guide_update has exactly one safe interpretation: no
        # cross-task guide mutation.  Normalizing it to null changes no research
        # choice and avoids discarding an otherwise complete proposal.
        proposal.setdefault("guide_update", None)
        if proposal["action"] not in {"experiment", "inspect", "reject_measurement"}:
            raise ProposalValidationError("unknown_action")
        if proposal["changed_stage"] not in {"data", "signal", "predictor", "objective", "trading_policy"}:
            raise ProposalValidationError("unknown_changed_stage")
        for key in ("question", "hypothesis", "coding_brief"):
            if not isinstance(proposal[key], str) or not proposal[key].strip():
                raise ProposalValidationError("missing_" + key)
            if len(proposal[key]) > PROPOSAL_TEXT_LIMITS[key]:
                raise ProposalValidationError(key + "_too_long")
        if (not isinstance(proposal["expected_evidence"], list) or not proposal["expected_evidence"]
                or len(proposal["expected_evidence"]) > MAX_EXPECTED_EVIDENCE_ITEMS
                or any(not isinstance(x, str) or not x.strip()
                       or len(x) > MAX_EXPECTED_EVIDENCE_CHARS
                       for x in proposal["expected_evidence"])):
            raise ProposalValidationError("invalid_expected_evidence")
        slots = audit.get("slot_policy")
        if (proposal["action"] in {"inspect", "reject_measurement"} and slots is not None
                and slots["diagnostic_attempts_remaining"] == 0):
            raise ProposalValidationError("diagnostic_slot_exhausted")
        update = proposal["guide_update"]
        if update is not None:
            if (audit["can_revise_guide"] is not True or not isinstance(update, dict)
                    or set(update) != {"text", "evidence_trial_ids"}
                    or not isinstance(update["text"], str) or not update["text"].strip()
                    or len(update["text"]) > MAX_GUIDE_TEXT_CHARS
                    or not isinstance(update["evidence_trial_ids"], list)
                    or not update["evidence_trial_ids"]
                    or len(update["evidence_trial_ids"]) > MAX_GUIDE_EVIDENCE_IDS
                    or not set(update["evidence_trial_ids"]) <=
                       set(audit.get("scored_guide_evidence_trial_ids", audit["allowed_trial_ids"]))):
                raise ProposalValidationError("invalid_guide_evidence")
        if len(canonical(proposal)) > MAX_PROPOSAL_CHARS:
            raise ProposalValidationError("proposal_too_long")
        canonical(proposal)
        return {"valid": True, "proposal": proposal, "scientific_merit_verified": False}
    except json.JSONDecodeError:
        return {"valid": False, "reason": "invalid_json",
                "scientific_merit_verified": False}
    except ProposalValidationError as error:
        return {"valid": False, "reason": error.code,
                "scientific_merit_verified": False}
    except (ValueError, TypeError):
        return {"valid": False, "reason": "invalid_proposal",
                "scientific_merit_verified": False}


def assess_response(text, audit, *, finish_reason=None):
    if finish_reason == "length":
        return {"valid": False, "reason": "output_truncated",
                "scientific_merit_verified": False}
    if audit.get("response_kind") == "task_selection":
        from selection_protocol import assess_selection
        return assess_selection(text, audit)
    if audit.get("response_kind") is not None:
        raise ValueError("unknown research response protocol")
    return assess_proposal(text, audit)


def dispatch_once(prepared, transport, budget, output, *, admission_check=None,
                  deadline_monotonic=None):
    """One model response only. Live defaults to blocked, not a flag-based bypass.

    An independent trusted outer-worker admission check must verify source/task
    provenance, frozen conditions, exact active claims and deadline before any
    live transport setup. It is NOT supplied by the researcher or loaded from
    model-generated code. No production check has been implemented yet.
    """
    if not isinstance(prepared, dict) or set(prepared) != {"messages", "audit", "packet_sha256"}:
        raise ValueError("prepared research request required")
    prepared = copy.deepcopy(prepared)
    if digest({k: v for k, v in prepared.items() if k != "packet_sha256"}) != prepared["packet_sha256"]:
        raise ValueError("request packet/audit changed after preparation")
    audit = prepared["audit"]
    if digest(prepared["messages"]) != audit["messages_sha256"]:
        raise ValueError("request changed after preparation")
    if getattr(transport, "live", True):
        if admission_check is None or admission_check(copy.deepcopy(audit)) is not True:
            raise RuntimeError("independent live data/worker admission is not complete")
        if type(transport) is not GLMTransport:
            raise RuntimeError("live worker requires the exact bounded GLM transport")
        if (type(deadline_monotonic) not in (int, float)
                or not math.isfinite(deadline_monotonic)):
            raise RuntimeError("live worker requires the runner's shared step deadline")
    max_input_tokens = audit["resource_limits"]["max_input_tokens"]
    max_output_tokens = audit["resource_limits"]["max_output_tokens"]
    max_wall_seconds = audit["resource_limits"]["max_wall_seconds"]
    state = budget.snapshot()
    if state["experiment_id"] != audit["experiment_id"]:
        raise ValueError("wrong experiment budget")
    if not getattr(transport, "live", True) and not state["experiment_id"].startswith("fixture-"):
        raise ValueError("mock transports cannot write non-fixture cost ledgers")
    output = Path(output)
    identifier(output.name)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    fresh_json(output / "claim.json", {"audit": audit, "code_sha256": file_hash(__file__),
               "model": MODEL, "num_samples": 1, "sampling_retries": 0,
               "seed": 23, "temperature": CONTROLLER_TEMPERATURE,
               "reasoning_effort": CONTROLLER_REASONING_EFFORT, "tools": [],
               "transport_source_hashes": {n: file_hash(Path(__file__).with_name(n)) for n in
                   ("bounded_process.py", "glm_process_worker.py", "glm_process_receipts.py")} if getattr(transport, "live", True) else {},
               "max_input_tokens": max_input_tokens, "max_output_tokens": max_output_tokens,
               "live_transport": getattr(transport, "live", True), "nonce": secrets.token_hex(16)})
    began = time.monotonic()
    request_deadline = began + max_wall_seconds
    if deadline_monotonic is not None:
        if type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic):
            raise ValueError("finite shared research deadline required")
        request_deadline = min(request_deadline, deadline_monotonic)
    try:
        if getattr(transport, "live", True):
            transport.bind_process_deadline(output, request_deadline)
        encoded_request = transport.encode(prepared["messages"])
        if set(encoded_request) != {"rendered_prompt", "token_ids", "tokenizer_repo",
                                    "tokenizer_revision", "chat_template_sha256"}:
            raise ValueError("unexpected encoder fields")
        ids = encoded_request["token_ids"]
        if not isinstance(ids, list) or not ids or any(type(t) is not int or t < 0 for t in ids):
            raise ValueError("invalid tokenized input")
        if len(ids) > max_input_tokens:
            raise ValueError("context exceeds frozen allowance; never truncate silently")
        upper = cost(len(ids), max_output_tokens)
        request = {"messages": prepared["messages"], "audit": audit, **encoded_request,
                   "upper_usd": str(upper), "rates": RATES, "max_output_tokens": max_output_tokens}
        fresh_json(output / "request.json", request)
        if getattr(transport, "live", True) and admission_check(copy.deepcopy(audit)) is not True:
            raise RuntimeError("live admission changed during request preparation")
        remaining_seconds = request_deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise TimeoutError("request preparation exhausted wall allowance")
        bucket = "final" if audit["phase"] == "transfer" else "learning"
        budget.reserve(output.name, bucket, str(upper), "tinker", digest(request))
        budget.dispatch(output.name)
        result = transport.sample(ids, max_output_tokens, remaining_seconds)
        if (set(result) != {"text", "output_tokens", "cached_input_tokens", "finish_reason", "provider"}
                or not isinstance(result["text"], str) or not isinstance(result["output_tokens"], list)
                or any(type(t) is not int or t < 0 for t in result["output_tokens"])
                or len(result["output_tokens"]) > max_output_tokens):
            raise ValueError("unexpected provider response; retain hold")
        charge = cost(len(ids), len(result["output_tokens"]), result["cached_input_tokens"])
        receipt = {"terminal": True, "provider": "tinker", "model": MODEL,
                   "input_tokens": len(ids), "output_tokens": len(result["output_tokens"]),
                   "cached_input_tokens": result["cached_input_tokens"], "metered_cost_usd": str(charge),
                   "basis": "returned token quantities times frozen rates; not invoice", "rates": RATES,
                   "provider_receipt": result["provider"], "elapsed_seconds": time.monotonic() - began}
        fresh_json(output / "response.json", result)
        budget.settle_metered(output.name, str(charge), receipt)
        assessment = {**assess_response(result["text"], audit,
                                        finish_reason=result["finish_reason"]),
                      "metered_cost_usd": str(charge),
                      "live_transport": getattr(transport, "live", True), "research_score": None,
                      "wall_limit_exceeded": time.monotonic() > request_deadline}
        if assessment["wall_limit_exceeded"]:
            assessment["valid"] = False
        fresh_json(output / "assessment.json", assessment)
        return assessment
    except Exception as error:
        fresh_json(output / "failure.json", {"error_type": type(error).__name__,
            "elapsed_seconds": time.monotonic() - began,
            "note": "No automatic retry. Check permanent claim and terminal metering; ambiguous dispatch stays held."})
        raise


class GLMTransport:
    """The already-tested pinned Tinker route, with no model-visible tools."""
    live = True
    TOKENIZER_REVISION = "aca966e4e02791568aa6a4ced368624b3d897f42"
    TEMPLATE_SHA256 = "3740abcea51c45830cb3ca562084ad5fb2ef53589376f73332e9886f93ade41c"

    def __init__(self, key, cache_dir):
        self.key, self.cache_dir, self.tokenizer = key, str(cache_dir), None

    def bind_process_deadline(self, output, deadline):
        if hasattr(self, "process_deadline"):
            raise ValueError("one fresh transport per permanent research request")
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("scoped provider credential unavailable before reservation")
        self.process_output, self.process_deadline = Path(output), deadline

    def _isolated(self, operation, **payload):
        import os
        import sys
        from bounded_process import run_bounded_process
        from worker_receipts import read_regular
        if not hasattr(self, "process_deadline"):
            raise ValueError("trusted dispatch must bind a process deadline first")
        remaining = self.process_deadline - time.monotonic() - 2  # Leave bounded local reap time.
        if remaining <= 0:
            raise TimeoutError("no time remains for bounded provider operation")
        if operation == "sample":
            payload["timeout_seconds"] = min(payload["timeout_seconds"], remaining)
        request = {"operation": operation, "cache_dir": self.cache_dir,
            "job_directory": str(self.process_output.absolute()), **payload,
            "source_hashes": {name: file_hash(Path(__file__).with_name(name)) for name in
                              ("glm_process_worker.py", "researcher_worker.py", "glm_canary.py")}}
        env = {"PATH": os.defpath, "LANG": "C.UTF-8", "TOKENIZERS_PARALLELISM": "false"}
        if operation == "sample":
            env["RSI_TINKER_API_KEY"] = self.key
        directory = self.process_output / (operation + "-process")
        receipt = run_bounded_process([sys.executable, "-I", str(Path(__file__).with_name("glm_process_worker.py"))],
            canonical(request).encode(), env, directory, wall_seconds=remaining)
        if (receipt["failure"] is not None or not receipt["process_reaped"] or receipt["exit_code"] != 0
                or not receipt["input_complete"]):
            raise RuntimeError("bounded provider operation failed; no retry or inferred remote cancellation")
        response = json.loads(read_regular(directory / "stdout.bin"))
        if set(response) != {"operation", "result"} or response["operation"] != operation:
            raise ValueError("bound provider response envelope changed")
        return response["result"]

    def encode(self, messages):
        return self._isolated("encode", messages=messages)

    def sample(self, token_ids, max_output, timeout_seconds):
        return self._isolated("sample", token_ids=token_ids, max_output=max_output, timeout_seconds=timeout_seconds)

    def _load_tokenizer(self):
        from transformers import AutoTokenizer
        # In this installed Transformers version, an HF repo ID triggers a
        # Mistral-regex model_info lookup even with local_files_only=True.
        # An explicit frozen local snapshot avoids that unnecessary network path.
        snapshot = Path(self.cache_dir) / "models--zai-org--GLM-5.3" / "snapshots" / self.TOKENIZER_REVISION
        if not snapshot.is_dir():
            raise ValueError("verified tokenizer snapshot is not available locally")
        self.tokenizer = AutoTokenizer.from_pretrained(str(snapshot.resolve()),
            trust_remote_code=False, token=False, local_files_only=True)
        template = self.tokenizer.chat_template
        if not isinstance(template, str):
            template = canonical(template)
        if hashlib.sha256(template.encode()).hexdigest() != self.TEMPLATE_SHA256:
            raise ValueError("frozen GLM template changed")

    def _encode_unbounded(self, messages):
        self._load_tokenizer()
        rendered = self.tokenizer.apply_chat_template(messages, tokenize=False,
            add_generation_prompt=True, reasoning_effort=CONTROLLER_REASONING_EFFORT)
        if "Reasoning Effort: Low" not in rendered:
            raise ValueError("low-effort concise-output template not applied")
        return {"rendered_prompt": rendered, "token_ids": self.tokenizer.encode(rendered, add_special_tokens=False),
                "tokenizer_repo": HF_MODEL, "tokenizer_revision": self.TOKENIZER_REVISION,
                "chat_template_sha256": self.TEMPLATE_SHA256}

    def _sample_unbounded(self, token_ids, max_output, timeout_seconds):
        import tinker
        from tinker import types
        from tinker.lib.retry_handler import RetryConfig
        client = tinker.ServiceClient(api_key=self.key, timeout=min(30, timeout_seconds), max_retries=0)
        sampler = client.create_sampling_client(base_model=MODEL,
            retry_config=RetryConfig(enable_retry_logic=False, progress_timeout=min(300, timeout_seconds)))
        reported = sampler.get_base_model()
        if reported not in {MODEL, HF_MODEL}:
            raise ValueError("provider model mismatch; no substitution")
        response = sampler.sample(prompt=types.ModelInput.from_ints(token_ids), num_samples=1,
            sampling_params=types.SamplingParams(max_tokens=max_output,
                                                 temperature=CONTROLLER_TEMPERATURE, seed=23,
                                                 stop=[self.tokenizer.eos_token_id])).result(timeout=timeout_seconds)
        if len(response.sequences) != 1:
            raise ValueError("expected one response")
        seq = response.sequences[0]
        ids = list(seq.tokens)
        return {"text": self.tokenizer.decode(ids, skip_special_tokens=False), "output_tokens": ids,
                "cached_input_tokens": response.prompt_cache_hit_tokens, "finish_reason": seq.stop_reason,
                "provider": {"reported_model": reported, "session_id": sampler.holder.get_session_id()}}
