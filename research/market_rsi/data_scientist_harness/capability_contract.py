"""Evidence-bound proposals for executable harness capabilities.

A capability proposal is an engineering work order, not evidence that the
capability exists.  Concrete observations must round-trip to an earlier,
successful ledger record so invented fields and measurements fail closed.
"""
import json


TEXT = {"type": "string", "minLength": 1}
EVIDENCE_REF = {
    "type": "object",
    "properties": {
        "record_id": TEXT,
        "json_pointer": TEXT,
        "observed_value_json": TEXT,
        "claim": TEXT,
        "inference_limit": TEXT,
    },
    "required": [
        "record_id", "json_pointer", "observed_value_json", "claim",
        "inference_limit",
    ],
    "additionalProperties": False,
}

OBSERVATION_TOOLS = {
    "inspect_harness",
    "read_archive",
    "read_public_source",
    "read_aggregate_source_evidence",
    "profile_raw_series",
    "profile_candidate_feature",
    "train_candidate",
    "inspect_candidate",
    "probe_temporal_contract",
    "probe_sample_contract",
    "probe_sports_event_contract",
    "probe_live_timing_contract",
    "inspect_sports_method_library",
}
SCHEMA = {
    "type": "object",
    "properties": {
        "name": TEXT,
        "problem": TEXT,
        "research_record": {
            **TEXT,
            "description": (
                "Exact four-digit record_id returned by a successful "
                "record_research call."
            ),
        },
        "evidence_refs": {"type": "array", "items": EVIDENCE_REF},
        "proposed_interface": TEXT,
        "verification_needed": TEXT,
        "unsupported_assumptions": {"type": "array", "items": TEXT},
    },
    "required": [
        "name", "problem", "research_record", "evidence_refs",
        "proposed_interface", "verification_needed",
        "unsupported_assumptions",
    ],
    "additionalProperties": False,
}


def _pointer(document, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("evidence json_pointer must start with /")
    parts = pointer[1:].split("/")
    if not parts or parts[0] != "result":
        raise ValueError("capability evidence json_pointer must stay within /result")
    value = document
    for raw in parts:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError(f"evidence json_pointer does not resolve: {pointer}")
    return value


def _successful_record(store, record_id):
    if not isinstance(record_id, str) or len(record_id) != 4 or not record_id.isdigit():
        raise ValueError("evidence record_id must be an exact four-digit ledger ID")
    records = store.records()
    index = int(record_id) - 1
    if index < 0 or index >= len(records):
        raise ValueError("evidence record_id is not in the append-only ledger")
    record = records[index]
    if record.get("status") != "ok":
        raise ValueError("capability evidence must reference a successful record")
    if record.get("tool") not in OBSERVATION_TOOLS:
        raise ValueError(
            "capability evidence must come from an observational result, not controller-authored prose"
        )
    return record


def archive_proposal(store, proposal):
    """Validate exact evidence values and return a non-activated work order."""
    evidence = proposal.get("evidence_refs")
    assumptions = proposal.get("unsupported_assumptions")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("capability proposal requires at least one exact evidence reference")
    if not isinstance(assumptions, list) or not assumptions:
        raise ValueError("capability proposal must state at least one unsupported assumption")
    if len(evidence) > 12 or len(assumptions) > 12:
        raise ValueError("capability proposal evidence and assumptions are bounded to 12 each")

    verified = []
    for item in evidence:
        record = _successful_record(store, item["record_id"])
        actual = _pointer(record, item["json_pointer"])
        try:
            declared = json.loads(item["observed_value_json"])
        except json.JSONDecodeError as error:
            raise ValueError("observed_value_json must contain one exact JSON value") from error
        if actual != declared or type(actual) is not type(declared):
            raise ValueError(
                "capability evidence value differs from the referenced ledger record"
            )
        verified.append({
            "record_id": item["record_id"],
            "tool": record["tool"],
            "json_pointer": item["json_pointer"],
            "observed_value": actual,
            "claim": item["claim"],
            "inference_limit": item["inference_limit"],
        })

    return {
        "proposal": proposal,
        "verified_evidence": verified,
        "activated": False,
        "reason": "new executable capabilities require human review, implementation and tests",
        "unsupported_assumptions_preserved": True,
        "proposal_is_not_observed_performance": True,
    }
