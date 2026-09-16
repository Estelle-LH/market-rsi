"""Fail-closed point-in-time contract for derived research features.

The contract separates when an event occurred, when its derived value became
available, when the prediction was made, and when the label window began.  A
feature may be scientifically interesting and still be inadmissible if any of
those clocks are missing or ordered incorrectly.
"""
from __future__ import annotations

from market_rsi import digest


CONTRACT_FIELDS = {
    "contract_id", "feature_names", "clock_domain", "row_id_field",
    "feature_event_time_field", "feature_available_time_field",
    "decision_time_field", "label_start_time_field", "label_end_time_field",
    "required_order", "missing_time_policy", "source_receipt_sha256",
}
REQUIRED_ORDER = "feature_event<=feature_available<=decision<label_start<=label_end"


def _sha(value: object, label: str) -> None:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError(f"{label} must be a lowercase SHA256")


def _seal(value: dict) -> dict:
    result = dict(value)
    result["record_sha256"] = digest(result)
    return result


def _verify(value: dict) -> None:
    _sha(value.get("record_sha256"), "record_sha256")
    body = {key: item for key, item in value.items() if key != "record_sha256"}
    if digest(body) != value["record_sha256"]:
        raise ValueError("feature-availability contract was modified")


def freeze_feature_availability(contract: dict) -> dict:
    """Freeze clock semantics before a feature can be used in an experiment."""
    if set(contract) != CONTRACT_FIELDS:
        raise ValueError("exact feature-availability schema required")
    if not isinstance(contract["contract_id"], str) or not contract["contract_id"]:
        raise ValueError("feature-availability contract id required")
    names = contract["feature_names"]
    if (not isinstance(names, list) or not names or len(names) != len(set(names))
            or not all(isinstance(name, str) and name for name in names)):
        raise ValueError("unique nonempty feature names required")
    if not isinstance(contract["clock_domain"], str) or not contract["clock_domain"]:
        raise ValueError("explicit feature clock domain required")
    field_names = [contract[key] for key in (
        "row_id_field", "feature_event_time_field", "feature_available_time_field",
        "decision_time_field", "label_start_time_field", "label_end_time_field",
    )]
    if not all(isinstance(name, str) and name for name in field_names):
        raise ValueError("every feature clock field must be explicit")
    if contract["required_order"] != REQUIRED_ORDER:
        raise ValueError("feature clock order cannot be weakened")
    if contract["missing_time_policy"] != "fail_closed":
        raise ValueError("missing feature clocks must fail closed")
    _sha(contract["source_receipt_sha256"], "source_receipt_sha256")
    return _seal({
        "schema": "frozen_feature_availability_contract_v1",
        "state": "availability_frozen",
        "contract": dict(contract),
    })


def audit_feature_availability(frozen: dict, rows: list[dict]) -> dict:
    """Prove every row obeys the frozen point-in-time order.

    This function intentionally rejects a whole candidate rather than silently
    dropping rows.  Filtering after seeing which rows fail would change the
    scientific population.
    """
    _verify(frozen)
    if frozen.get("state") != "availability_frozen":
        raise ValueError("frozen feature-availability contract required")
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty feature-availability rows required")
    contract = frozen["contract"]
    fields = {
        "row": contract["row_id_field"],
        "event": contract["feature_event_time_field"],
        "available": contract["feature_available_time_field"],
        "decision": contract["decision_time_field"],
        "label_start": contract["label_start_time_field"],
        "label_end": contract["label_end_time_field"],
    }
    seen = set()
    availability_lag = []
    decision_lag = []
    label_gap = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or not set(fields.values()).issubset(row):
            raise ValueError(f"feature-availability row {position} lacks frozen fields")
        row_id = row[fields["row"]]
        if isinstance(row_id, (dict, list, set)) or row_id in seen:
            raise ValueError("feature-availability rows require unique scalar ids")
        seen.add(row_id)
        times = [row[fields[name]] for name in (
            "event", "available", "decision", "label_start", "label_end")]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in times):
            raise ValueError(f"feature-availability row {row_id} has a missing or noninteger clock")
        event, available, decision, label_start, label_end = times
        if not event <= available <= decision < label_start <= label_end:
            raise ValueError(f"feature-availability row {row_id} violates frozen clock order")
        availability_lag.append(available - event)
        decision_lag.append(decision - available)
        label_gap.append(label_start - decision)
    return _seal({
        "schema": "feature_availability_audit_v1",
        "status": "PASS",
        "contract_sha256": frozen["record_sha256"],
        "rows": len(rows),
        "unique_rows": len(seen),
        "violations": 0,
        "clock_domain": contract["clock_domain"],
        "availability_lag_ns": {"min": min(availability_lag), "max": max(availability_lag)},
        "available_to_decision_lag_ns": {"min": min(decision_lag), "max": max(decision_lag)},
        "decision_to_label_gap_ns": {"min": min(label_gap), "max": max(label_gap)},
    })

