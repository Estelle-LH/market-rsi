"""Explicit grid adapter; no inferred units, sub-ms order, fixes or source PASS.

The seven-file opened-Train cache is a materialized grid, NOT the raw exchange
feed. Its upstream audit is required separately. Temporal outputs are emitted
at the decision grid time; this does not recover source arrival timestamps.
"""
from dataclasses import asdict, fields
from pathlib import Path
import copy
import numpy as np

from data_scientist_harness.core_dependency import dependency_identity
dependency_identity()
from ds_harness_core.quality_checks import DataSpec, FeatureRule, TimeSeriesSpec, batch_hash
from ds_harness_core.research_gate import PanelInput, guarded_research, persist_quality_report
from historical_recorded_features import derive, contains_recorded, feature_engine_sha256
from market_rsi import digest, file_hash, load_json

CLOCK = "UTC_millisecond_grid_no_recovered_event_order"
SESSION = "UTC_diagnostic_date_not_exchange_session"
CHECKS = ("source_units_clock", "kernel_future_mutation", "preprocessing_parity")
RULE_FIELDS = {f.name for f in fields(FeatureRule)}


def implementation_hash():
    from data_scientist_harness import checked_learning
    root=Path(__file__).resolve().parents[1]
    return digest({"adapter": file_hash(Path(__file__)),
        "learning": file_hash(Path(checked_learning.__file__)),
        "core": dependency_identity(),
        "legacy_helpers":{name:file_hash(root/name) for name in (
            'historical_grid_features.py','historical_feature_composition.py','historical_recorded_features.py',
            'historical_grid_learning.py','historical_delta_evaluation.py','materialize_selected_grid_objective.py')}})


def contract_inputs(source):
    """Return only explicitly pinned small runner receipts to freeze with input."""
    from data_scientist_harness.store import resident
    path = resident(Path(source) / "sanity-contract.json", 8_388_608)
    c = load_json(path)
    if c.get("schema") != "market_grid_sanity_contract_v1" or set(c.get("evidence", {})) != set(CHECKS):
        raise ValueError("explicit runner-owned sanity contract and adapter evidence required")
    result = {"sanity-contract.json": path}
    for key, ref in c["evidence"].items():
        p = resident(Path(ref["path"]), 8_388_608)
        if file_hash(p) != ref["sha256"]:
            raise ValueError("sanity evidence bytes changed")
        result[f"sanity-evidence-{key}.json"] = p
    return result


def read_contract(root, manifest, purpose):
    c = load_json(Path(root) / "sanity-contract.json")
    if (c.get("schema") != "market_grid_sanity_contract_v1"
            or c.get("input_manifest_sha256") != manifest
            or c.get("implementation_sha256") != implementation_hash()
            or c.get("clock_domain") != CLOCK or c.get("session_timezone") != SESSION
            or set(c.get("evidence", {})) != set(CHECKS)):
        raise ValueError("sanity contract belongs to another input/adapter/clock")
    if set(c.get('time_series',{})) != {f.name for f in fields(TimeSeriesSpec)}:
        raise ValueError('all time-series limits, including pairing gap, must be explicit')
    for key in CHECKS:
        path = Path(root) / f"sanity-evidence-{key}.json"
        if file_hash(path) != c["evidence"][key]["sha256"]:
            raise ValueError("frozen sanity evidence changed")
        proof = load_json(path)
        if (proof.get("check") != key or proof.get("status") != "PASS"
                or proof.get("input_manifest_sha256") != manifest
                or proof.get("implementation_sha256") != c["implementation_sha256"]
                or proof.get("evidence_mode") not in {"synthetic_fixture", "runner_verified_open_train"}
                or (purpose != "canary" and proof["evidence_mode"] == "synthetic_fixture")):
            raise ValueError("missing, stale, synthetic or failed real adapter evidence")
        if key == "source_units_clock" and (
                proof.get("units") != c["raw_units"] or proof.get("clock_domain") != CLOCK
                or proof.get("session_timezone") != SESSION):
            raise ValueError("unit/clock declarations lack matching upstream evidence")
    return c


def rules(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError("explicit rule for every field required")
    result = {}
    for name in names:
        if not isinstance(value[name], dict) or set(value[name]) != RULE_FIELDS:
            raise ValueError("all quality limits must be explicit; no hidden defaults")
        result[name] = FeatureRule(**value[name])
    return result


def panel(inputs, values, names, available, units, quality_rules, c):
    x = inputs["x"]; t = x["decision_ms"]
    if (t.dtype != np.dtype("int64") or np.any(t > np.iinfo(np.int64).max // 1_000_000)
            or np.any(t < -(np.iinfo(np.int64).max // 1_000_000))):
        raise ValueError("exact representable int64 millisecond clocks required")
    # A grid has at most one decision per market/ms. Ordinal zero declares only
    # that restricted domain; it is never claimed as a recovered event ordinal.
    order = np.zeros(len(t), dtype=np.int64)
    times = t * 1_000_000
    at = np.broadcast_to(times[:, None], values.shape).copy()
    ao = np.zeros(values.shape, dtype=np.int64)
    at[~available] = -1; ao[~available] = -1
    b = dict(schema="feature_batch_v1", row_id=x["row_id"].copy(), entity_id=x["market"].copy(),
        session_id=x["date"].copy(), decision_ns=times, event_ordinal=order,
        feature_names=list(names), values=values.copy(), available=available.copy(),
        feature_available_ns=at, feature_available_ordinal=ao)
    spec = DataSpec(feature_names=tuple(names), units=units,
        expected_groups=tuple(tuple(g) for g in c["expected_groups"]),
        source_hashes={"opened_train_input_manifest": c["input_manifest_sha256"]},
        clock_domain=CLOCK, session_timezone=SESSION, rules=rules(quality_rules, names),
        implementation_sha256=c["implementation_sha256"],
        allowed_unavailable_reasons=tuple(c["allowed_unavailable_reasons"]),
        min_rows_per_group=c["min_rows_per_group"])
    observed = {k: copy.deepcopy(getattr(spec,k)) for k in
        ("units","source_hashes","clock_domain","session_timezone","implementation_sha256")}
    reasons = np.where(available, "", "unavailable_grid_or_window")
    return PanelInput(b, spec, observed, reasons)


def raw_panel(inputs, c):
    x = inputs["x"]
    return panel(inputs, x["values"], inputs["names"], np.isfinite(x["values"]),
                 c["raw_units"], c["raw_rules"], c)


def lineage(spec):
    if "source" in spec: return [spec["source"]]
    return sorted({source for p in spec["operands"] for source in lineage(p)})


def derived_panel(inputs, plan, experiment, c):
    x = inputs["x"]
    if any(contains_recorded(s) for s in plan["features"]):
        raise ValueError("recorded-event adapter not validated by the grid sanity contract")
    derived = [derive(x["entity"], x["decision_ms"], x["values"], inputs["names"],
        spec=s, cadence_ms=inputs["cadence_ms"]) for s in plan["features"]]
    if any(np.any(d["available"] & (d["feature_available_ms"] > x["decision_ms"])) for d in derived):
        raise ValueError("actual derived feature availability is in the future")
    return panel(inputs, np.column_stack([d["values"] for d in derived]),
        [s["name"] for s in plan["features"]], np.column_stack([d["available"] for d in derived]),
        experiment["feature_units"], experiment["feature_rules"], c)


def guard(*, raw, transformed, c, lineage_map, path, stage, operation):
    evidence = {key: {"implementation_sha256": c["implementation_sha256"], **{
        check: {"status":"PASS", "receipt_sha256": c["evidence"][check]["sha256"]}
        for check in CHECKS}} for key in ("raw","transformed")}
    return guarded_research(stage=stage, raw=raw, transformed=transformed,
        time_series=TimeSeriesSpec(**c["time_series"]), lineage=lineage_map,
        adapter_evidence=evidence, persist=lambda report: persist_quality_report(report, path),
        operation=operation)
