"""Controller-authored source-study proposals; declaration NEVER grants admission."""
from datetime import date
from market_rsi import digest, identifier, fresh_json, file_hash, load_json
from data_science_tools.pipeline import BINDINGS
from data_scientist_harness.temporal_contract import bound_probe
from data_scientist_harness import sample_contract

TEXT = {"type": "string", "minLength": 1}
STRINGS = {"type": "array", "items": TEXT}


def obj(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


SCHEMA = obj({
    "proposal_id": TEXT, "current_spec_sha256": TEXT, "finding_sha256": TEXT, "research_record": TEXT,
    "temporal_probe_record": TEXT, "sample_contract_record": TEXT,
    "source": obj({"source_id": TEXT, "raw_manifest_sha256": TEXT, "source_choice_reason": TEXT,
        "clock_basis_and_limits": TEXT, "identity_basis_and_limits": TEXT,
        "sampling_rule": TEXT, "missing_and_quiet_policy": TEXT}),
    "question": TEXT, "hypothesis": TEXT,
    "objective": obj({"quantity": TEXT, "units": TEXT, "horizon_ms": {"type": "integer"},
        "availability_and_label_rule": TEXT}),
    "comparison": obj({"baseline": TEXT, "candidate": TEXT,
        "changed_layer": {"type": "string", "enum": ["data", "features", "trainer", "objective"]},
        "held_fixed": TEXT}),
    "evaluation": obj({"fit_dates": STRINGS, "check_dates": STRINGS, "entity_split_and_purge": TEXT,
        "primary_metric": TEXT, "supports_if": TEXT, "refutes_if": TEXT,
        "claim_limit": TEXT}),
    "missing_evidence": STRINGS, "next_if_unsupported": TEXT,
})


def dates(values):
    if (not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values)
            or values != sorted(set(values))):
        raise ValueError("nonempty sorted unique ISO date list required")
    if any(date.fromisoformat(v).isoformat() != v for v in values):
        raise ValueError("canonical ISO dates required")
    return values


def validate_context(context, quality):
    if context is None: return
    if (not isinstance(context, dict) or set(context) != {"source_id", "raw_manifest_sha256", "opened_diagnostic_dates"}
            or not isinstance(context["source_id"], str) or not context["source_id"].strip()
            or context["raw_manifest_sha256"] != quality["component_bindings"]["raw_manifest"]
            or not isinstance(context["raw_manifest_sha256"], str)):
        raise ValueError("runner-owned planning context must bind current source QA")
    dates(context["opened_diagnostic_dates"])


def missing_definitions(quality):
    return {"unfrozen_components": [k for k in BINDINGS if quality["component_bindings"][k] is None],
        "unresolved_checks": list(quality["blockers"]),
        "interpretation": "A missing component definition is not a failed measurement. More rows cannot define an objective/split or attest a clock. Proposing definitions does not pass checks."}


def register(store, a, research):
    context = store.config.get("planning_context")
    if context is None: raise ValueError("runner has not provisioned a source-planning scope")
    quality = store.quality(); validate_context(context, quality)
    identifier(a["proposal_id"])
    if a["current_spec_sha256"] != quality["spec_sha256"]:
        raise ValueError("proposal must reference the current QA spec")
    if a["finding_sha256"] != digest(load_json(store.root/"findings.json")):
        raise ValueError("proposal must reference current findings")
    source = a["source"]
    if any(source[k] != context[k] for k in ("source_id", "raw_manifest_sha256")):
        raise ValueError("proposal source differs from the current runner-bound scope")
    fit, check = dates(a["evaluation"]["fit_dates"]), dates(a["evaluation"]["check_dates"])
    if not set(fit+check) <= set(context["opened_diagnostic_dates"]):
        raise ValueError("proposal requests dates outside opened diagnostic scope")
    if max(fit) >= min(check): raise ValueError("fit dates must strictly precede check dates")
    if type(a["objective"]["horizon_ms"]) is not int or a["objective"]["horizon_ms"] <= 0:
        raise ValueError("positive explicit prediction horizon required")
    if not a["missing_evidence"] or any(not v.strip() for v in a["missing_evidence"]):
        raise ValueError("diagnostic planning must preserve missing evidence")
    if research["arguments"]["layer"] not in {"data_quality", "evaluation"}:
        raise ValueError("source/objective planning needs data_quality or evaluation research")
    tested=bound_probe(store,a["temporal_probe_record"],a["objective"]["horizon_ms"])
    samples=sample_contract.bound_probe(store,a["sample_contract_record"],tested["contract"])
    target = store.root/"source-study-proposal.json"
    if target.exists(): raise ValueError("first valid source-study proposal is permanent; no resampling within workspace")
    value = {"schema": "controller_source_study_proposal_v1", "proposal": a,
        "typed_temporal_contract":tested,
        "typed_sample_contract":samples,
        "manifest_sha256": store.expected, "planning_context_sha256": digest(context),
        "research_record_sha256": file_hash(store.root/"records"/(a["research_record"]+".json")),
        "review_requirements": missing_definitions(quality), "source_admitted": False,
        "data_science_ready": False, "execution_admitted": False, "new_data_read": False,
        "fits_started": 0, "scientific_contract_approved": False,
        "claim_scope": "proposal on already-opened diagnostics; not an executable approved protocol or OOS result"}
    value["proposal_sha256"] = digest(value)
    fresh_json(target, value)
    return {"registered": True, "proposal": {"path": str(target), "sha256": file_hash(target)},
        "review_requirements": value["review_requirements"], "execution_admitted": False,
        "fits_started": 0, "source_admitted": False, "scientific_contract_approved": False}


def current(store):
    path = store.root/"source-study-proposal.json"
    records = [r for r in store.records("propose_source_study") if r["status"] == "ok"]
    if not records and not path.exists(): return None
    if len(records) != 1 or not path.exists(): raise ValueError("source-study registration is incomplete")
    ref = records[0]["result"]["proposal"]
    value = load_json(path)
    if (ref != {"path": str(path), "sha256": file_hash(path)}
            or value.get("manifest_sha256") != store.expected
            or value.get("proposal_sha256") != digest({k: v for k, v in value.items() if k != "proposal_sha256"})
            or value["proposal"] != records[0]["arguments"]):
        raise ValueError("registered source-study proposal changed")
    return ref
