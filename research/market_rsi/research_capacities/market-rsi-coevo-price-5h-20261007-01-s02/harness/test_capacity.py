"""Synthetic assertions only; not trial results or performance evidence."""

from capacity import apply


def _baseline(context):
    return {
        "role": "harness",
        "process_feedback": context.get("history", {}).get("process_feedback"),
        "scope": "Supplied evidence only; no scorer, permission or pool mutation",
        "capacity_gain_claimed": False,
    }


def _clone(value):
    if isinstance(value, dict):
        return {key: _clone(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone(item) for item in value]
    return value


def _check(context, origin=None, record=None):
    before = _clone(context)
    expected = _baseline(context)
    brief = None
    if origin is not None:
        brief = {"context_origin": origin}
        for field in (
            "execution_outcome", "reason", "observation", "proposal",
            "attempts_entered", "fits_entered", "performance_evidence",
            "scientific_refutation", "next", "same_ID_retry",
        ):
            brief[field] = record.get(field)
    expected["operational_failure_brief"] = brief
    first = apply(context)
    assert first == expected
    assert context == before
    assert apply(context) == first
    assert context == before
    return first


def test_capacity():
    record = {
        "execution_outcome": "pre_source_admission_failed",
        "reason": "Combined source/test 14762 exceeds unchanged12288; source also uses unadmitted dict.pop",
        "proposal": {
            "axis": "researcher",
            "change_id": "R1-VerifiedOutcomeLedger300",
            "status": "proposed; author source rejected before implementation/trial/adoption",
        },
        "attempts_entered": 0,
        "fits_entered": 0,
        "performance_evidence": False,
        "next": (
            "Fresh original decision in next finite slot. "
            "Do not replay unchanged rejected source/test. "
            "Use failure to simplify or change the next proposed capacity; "
            "no scientific conclusion from failure."
        ),
        "same_ID_retry": False,
        "ignored": "must not be emitted",
    }
    for name in ("current", "restart", "success"):
        context = {
            "replay_case": name,
            "history": {"last_operational_failure": _clone(record)},
            "feedback": {
                "candidate_id": "B3-ShrunkMagnitudeRegimes300",
                "decision": "REVERT",
                "execution_outcome": "succeeded",
                "last_operational_failure": _clone(record),
            },
            "memory": {"last_operational_failure": _clone(record)},
        }
        assert _baseline(context)["process_feedback"] is None
        result = _check(context, "history.last_operational_failure", record)
        assert result["process_feedback"] is None
        assert context["feedback"]["decision"] == "REVERT"

    known = {
        "observation": "Known author numeric admission failure before source/training; subsequently repaired",
        "scientific_refutation": False,
        "source": {"path": "synthetic", "sha256": "synthetic"},
    }
    _check(
        {
            "replay_case": "failure",
            "feedback": {"decision": "REVERT"},
            "history": {"known_operational_failure": known},
        },
        "history.known_operational_failure",
        known,
    )
    _check({
        "replay_case": "historical_replay",
        "feedback": {
            "candidate_id": "B3-ShrunkMagnitudeRegimes300",
            "decision": "REVERT",
        },
        "history": {
            "process_feedback": {"decision": "REVERT", "details": [0, False, None]},
        },
    })

    locations = (
        ("history", "last_operational_failure"),
        ("feedback", "last_operational_failure"),
        ("memory", "last_operational_failure"),
        ("history", "known_operational_failure"),
    )
    for index in range(len(locations)):
        context = {"history": {}, "feedback": {}, "memory": {}}
        for position in range(len(locations)):
            section, key = locations[position]
            context[section][key] = (
                None if position < index else {"reason": str(position)}
            )
        section, key = locations[index]
        _check(context, section + "." + key, {"reason": str(index)})

    _check({})
    _check({"history": {"last_operational_failure": None}})
    _check(
        {
            "history": {"last_operational_failure": {}},
            "feedback": {"last_operational_failure": record},
        },
        "history.last_operational_failure",
        {},
    )


if __name__ == "__main__":
    test_capacity()
